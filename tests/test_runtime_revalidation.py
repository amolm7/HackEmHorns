import unittest
from unittest.mock import patch

from tests import test_workspace
from backend.db import get, put


class RuntimeRevalidationTests(unittest.TestCase):
    setUp = test_workspace.WorkspaceTests.setUp
    tearDown = test_workspace.WorkspaceTests.tearDown
    call = test_workspace.WorkspaceTests.call
    hire = test_workspace.WorkspaceTests.hire
    start = test_workspace.WorkspaceTests.start

    def test_model_response_is_discarded_if_spec_or_access_changes(self):
        changes = ["spec", "connection", "department", "status"]
        for change in changes:
            for tool_call in [False, True]:
                with self.subTest(change=change, tool_call=tool_call):
                    _, agent = self.hire("Write a document", caps=["write-document"])
                    self.app.config["MODEL_API_KEY"] = "mock-only"
                    run = self.start(agent, "Write a brief", mode="meta")

                    def generate(*args, **kwargs):
                        if change == "spec":
                            self.call("PATCH", f'agents/{agent["id"]}', {
                                "expected_spec_version": 1,
                                "instructions": "Changed while the model was running",
                            })
                        else:
                            with self.app.db.transaction(True) as c:
                                if change == "connection":
                                    connection = get(c, "connections", agent["bindings"][0]["connection_id"])
                                    connection["active"] = False
                                    put(c, "connections", connection)
                                elif change == "department":
                                    actor = get(c, "users", "pavan")
                                    actor["department_ids"] = []
                                    put(c, "users", actor)
                                else:
                                    current = get(c, "agents", agent["id"])
                                    current["status"] = "draft"
                                    put(c, "agents", current)
                        part = {"functionCall": {"name": "create_document", "args": {"title": "Old", "body": "Old"}}} if tool_call else {"text": "Old answer"}
                        return {"role": "model", "parts": [part]}, {}

                    with patch("backend.runtime.model.generate", side_effect=generate):
                        self.app.runtime.tick()
                    with self.app.db.transaction() as c:
                        stored = get(c, "runs", run["id"])
                    self.assertEqual(stored["status"], "failed")
                    self.assertIsNone(stored["result"])
                    self.assertEqual(stored["queue"], [])
                    self.assertEqual(stored["model_turns"], 0)
                    self.assertEqual(len(stored["contents"]), 1)
                    # Restore shared seed records before the next independent run.
                    with self.app.db.transaction(True) as c:
                        connection = get(c, "connections", agent["bindings"][0]["connection_id"])
                        connection["active"] = True
                        put(c, "connections", connection)
                        actor = get(c, "users", "pavan")
                        actor["department_ids"] = ["support"]
                        put(c, "users", actor)

    def test_cancellation_during_model_call_remains_cancelled(self):
        _, agent = self.hire("Write a document", caps=["write-document"])
        self.app.config["MODEL_API_KEY"] = "mock-only"
        run = self.start(agent, "Write a brief", mode="meta")

        def generate(*args, **kwargs):
            self.call("POST", f'runs/{run["id"]}/cancel', {})
            return {"role": "model", "parts": [{"text": "Late answer"}]}, {}

        with patch("backend.runtime.model.generate", side_effect=generate):
            self.app.runtime.tick()
        result = self.call("GET", f'runs/{run["id"]}')
        self.assertEqual(result["status"], "cancelled")
        self.assertIsNone(result["result"])
