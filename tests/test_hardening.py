import json
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests import test_workspace
from backend.contracts import Error
from backend.db import all_rows, get, put


class HardeningTests(unittest.TestCase):
    setUp = test_workspace.WorkspaceTests.setUp
    tearDown = test_workspace.WorkspaceTests.tearDown
    hire = test_workspace.WorkspaceTests.hire
    drain = test_workspace.WorkspaceTests.drain
    start = test_workspace.WorkspaceTests.start
    call = test_workspace.WorkspaceTests.call

    def analysis_job(self, caps=None):
        _, agent = self.hire("Analyze data", caps=caps or ["analyze-data"])
        self.app.config["MODEL_API_KEY"] = "mock"
        run = self.start(
            agent, "Analyze:\nchannel,signups\na,10\nb,20", mode="meta"
        )
        return None, agent, run["id"]

    def test_live_scope_rejects_extra_agent_tool(self):
        item, agent, ident = self.analysis_job(["analyze-data"])

        def response(config, contents, instruction, tools, **kw):
            self.assertEqual([t["name"] for t in tools], ["analyze_data"])
            return {
                "role": "model",
                "parts": [
                    {
                        "functionCall": {
                            "name": "read_url",
                            "args": {"url": "https://example.com"},
                        }
                    }
                ],
            }, {}

        with patch("backend.runtime.model.generate", side_effect=response):
            self.app.runtime.tick()
            self.app.runtime.tick()
        run = self.call("GET", "runs/" + ident)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_code"], "tool_denied")
        with self.app.db.transaction() as c:
            self.assertFalse(
                [a for a in all_rows(c, "actions") if a["run_id"] == ident]
            )

    def test_provider_retry_is_durable_and_cancellable(self):
        _, _, ident = self.analysis_job()
        error = Error(
            "Temporary failure",
            502,
            "provider_error",
            {"retryable": True, "retry_after": 4},
        )
        with patch("backend.runtime.model.generate", side_effect=error) as generate:
            self.app.runtime.tick()
            self.app.runtime.tick()
        self.assertEqual(generate.call_count, 1)
        run = self.call("GET", "runs/" + ident)
        self.assertEqual(run["status"], "queued")
        self.assertEqual(run["retry_count"], 1)
        self.assertIn("next_attempt_at", run)
        self.call("POST", "runs/" + ident + "/cancel", {})
        self.assertEqual(self.call("GET", "runs/" + ident)["status"], "cancelled")

    def test_slow_job_does_not_block_other_job(self):
        _, agent = self.hire("Strategy", caps=["write-document"])
        self.app.config["MODEL_API_KEY"] = "mock"
        self.start(agent, "Slow one", mode="meta")
        self.start(agent, "Slow two", mode="meta")
        entered, release = threading.Event(), threading.Event()
        count, guard = [0], threading.Lock()

        def generate(*args, **kwargs):
            with guard:
                count[0] += 1
                if count[0] >= 2:
                    entered.set()
            release.wait(5)
            return {"role": "model", "parts": [{"text": "Done."}]}, {}

        try:
            with patch("backend.runtime.model.generate", side_effect=generate):
                self.app.runtime.launch()
                self.assertTrue(
                    entered.wait(3), "Both jobs should enter the provider independently"
                )
                release.set()
                self.app.runtime.close()
        finally:
            release.set()
            self.app.runtime.close()

    def test_retry_exhaustion_preserves_bounded_attempts(self):
        _, _, ident = self.analysis_job()
        error = Error("Temporary failure", 502, "provider_error", {"retryable": True})
        with patch("backend.runtime.model.generate", side_effect=error) as generate:
            for attempt in range(4):
                with self.app.db.transaction(True) as c:
                    run = get(c, "runs", ident)
                    run.pop("next_attempt_at", None)
                    put(c, "runs", run)
                self.app.runtime.tick()
        self.assertEqual(generate.call_count, 4)
        self.assertEqual(
            self.call("GET", "runs/" + ident)["error_code"], "retry_exhausted"
        )

    def test_queue_admission_limit_does_not_create_an_extra_run(self):
        _, agent = self.hire("Strategy", caps=["write-document"])
        self.app.config["MAX_ACTIVE_RUNS_PER_USER"] = 1
        self.start(agent, "First task")
        with self.assertRaises(Error) as error:
            self.start(agent, "Second task")
        self.assertEqual(error.exception.status, 429)
        self.assertEqual(error.exception.code, "queue_full")
        self.assertEqual(len(self.call("GET", "runs")), 1)

    def test_revoked_execution_role_discards_model_response(self):
        item, agent, ident = self.analysis_job()

        def generate(*args, **kwargs):
            with self.app.db.transaction(True) as c:
                actor = get(c, "users", "pavan")
                actor["roles"] = ["auditor"]
                put(c, "users", actor)
            return {"role": "model", "parts": [{"text": "Late answer"}]}, {}

        with patch("backend.runtime.model.generate", side_effect=generate):
            self.app.runtime.tick()
        with self.app.db.transaction() as c:
            run = get(c, "runs", ident)
        self.assertEqual(run["status"], "failed")
        self.assertIsNone(run["result"])

    def test_revoked_reviewer_role_invalidates_prior_approval(self):
        _, agent = self.hire("Strategy", caps=["write-document"])
        run = self.start(agent, "Write a decision brief")
        self.app.runtime.tick()
        approval = next(
            a for a in self.call("GET", "approvals") if a["status"] == "pending"
        )
        self.call(
            "POST",
            "approvals/" + approval["id"] + "/decision",
            {"decision": "approve", "comment": "Checked"},
            key="approve",
        )
        with self.app.db.transaction(True) as c:
            actor = get(c, "users", "pavan")
            actor["roles"] = ["builder"]
            put(c, "users", actor)
        self.app.runtime.tick()
        self.assertEqual(
            self.call("GET", "runs/" + run["id"])["error_code"], "stale_approval"
        )
        with self.app.db.transaction() as c:
            self.assertFalse(
                [
                    a
                    for a in all_rows(c, "actions")
                    if a["run_id"] == run["id"] and a["status"] == "executed"
                ]
            )
