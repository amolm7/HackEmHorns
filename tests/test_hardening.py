import json
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests import test_workspace
from backend.contracts import Error
from backend.db import all_rows, get, put
from backend.quality import check


class HardeningTests(unittest.TestCase):
    setUp = test_workspace.WorkspaceTests.setUp
    tearDown = test_workspace.WorkspaceTests.tearDown
    hire = test_workspace.WorkspaceTests.hire
    drain = test_workspace.WorkspaceTests.drain
    start = test_workspace.WorkspaceTests.start

    def call(self, method, path, data=None, user="pavan", key=None):
        if method == "POST" and path.startswith("work-queue"):
            key = key or str(uuid4())
            if path.endswith("/assign") and data and data.get("mode"):
                test_workspace.use_model(self.app, data["agent_id"], data["mode"])
        return test_workspace.WorkspaceTests.call(self, method, path, data, user, key)

    def analysis_job(self, caps=None):
        _, agent = self.hire("Analyze data", caps=caps or ["analyze-data"])
        item = self.call(
            "POST",
            "work-queue",
            {
                "workflow": "analysis",
                "title": "Growth",
                "task": "Analyze:\nchannel,signups\na,10\nb,20",
            },
        )
        self.app.config["MODEL_API_KEY"] = "mock"
        assigned = self.call(
            "POST",
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "meta"},
        )
        return item, agent, assigned["run_id"]

    def test_live_scope_rejects_extra_agent_tool(self):
        item, agent, ident = self.analysis_job(["analyze-data", "research-web"])

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

    def test_missing_deliverables_repair_once_then_fail(self):
        _, _, ident = self.analysis_job()
        response = (
            {"role": "model", "parts": [{"text": "Done without creating anything."}]},
            {},
        )
        with patch("backend.runtime.model.generate", return_value=response) as generate:
            self.app.runtime.tick()
            self.app.runtime.tick()
        run = self.call("GET", "runs/" + ident)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_code"], "deliverable_validation")
        self.assertFalse(run["quality"]["passed"])
        self.assertEqual(run["repair_attempts"], 1)

    def test_changed_source_data_fails_quality(self):
        item, agent, ident = self.analysis_job()
        with self.app.db.transaction(True) as c:
            put(
                c,
                "actions",
                {
                    "id": str(uuid4()),
                    "run_id": ident,
                    "tool_id": "analyze_data",
                    "status": "executed",
                    "arguments": {"table": "channel,signups\na,999"},
                    "result": {"kind": "analysis", "rows": 1},
                },
            )
            report = check(c, get(c, "runs", ident))
        self.assertFalse(report["passed"])
        self.assertFalse(
            next(x for x in report["checks"] if x["name"] == "analysis_source")[
                "passed"
            ]
        )

    def test_structural_document_and_slide_checks(self):
        item = self.call("POST", "work-queue/sample-batch", {"workflow": "launch"})[0]
        _, agent = self.hire(
            "Launch", caps=["analyze-data", "write-document", "make-slideshow"]
        )
        row = self.call(
            "POST",
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "demo"},
        )
        self.drain()
        with self.app.db.transaction(True) as c:
            run = get(c, "runs", row["run_id"])
            self.assertTrue(run["quality"]["passed"])
            actions = [a for a in all_rows(c, "actions") if a["run_id"] == run["id"]]
            slides = next(a for a in actions if a["tool_id"] == "create_slideshow")
            slides["result"]["slides"].pop()
            put(c, "actions", slides)
            doc = next(a for a in actions if a["tool_id"] == "create_document")
            doc["result"]["body"] = "# A short unrelated document"
            put(c, "actions", doc)
            report = check(c, run)
        self.assertFalse(report["passed"])
        with self.assertRaises(Error):
            self.call(
                "POST",
                "runs/" + run["id"] + "/outcome",
                {"success": True, "comment": "Bypass"},
                key="outcome",
            )

    def test_queue_replay_and_changed_payload(self):
        body = {
            "workflow": "brief",
            "title": "Decision",
            "task": "Write a decision brief",
        }
        first = self.call("POST", "work-queue", body, key="create")
        self.assertEqual(first, self.call("POST", "work-queue", body, key="create"))
        with self.assertRaises(Error):
            self.call("POST", "work-queue", {**body, "title": "Changed"}, key="create")
        with self.assertRaises(Error):
            self.app.handle("POST", "/api/work-queue", body, "pavan")
        self.assertEqual(len(self.call("GET", "work-queue")), 1)

    def test_revision_includes_prior_artifacts(self):
        item = self.call(
            "POST",
            "work-queue",
            {
                "workflow": "brief",
                "title": "Decision",
                "task": "Write a decision brief",
            },
        )
        _, agent = self.hire("Strategy", caps=["write-document"])
        first = self.call(
            "POST",
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "demo"},
        )
        self.drain()
        self.call(
            "POST",
            "work-queue/" + item["id"] + "/review",
            {"success": False, "comment": "Include the risk of a delayed launch."},
        )
        self.app.config["MODEL_API_KEY"] = "mock"
        second = self.call(
            "POST",
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "meta"},
        )
        with self.app.db.transaction() as c:
            run = get(c, "runs", second["run_id"])
        self.assertEqual(run["revision_context"]["previous_run_id"], first["run_id"])
        self.assertTrue(run["revision_context"]["deliverables"])
        self.assertIn("delayed launch", run["revision_context"]["feedback"])

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

    def test_idempotent_assignment_returns_original_and_permission_changes_reject(self):
        item = self.call(
            "POST",
            "work-queue",
            {
                "workflow": "brief",
                "title": "Decision",
                "task": "Write a decision brief",
            },
        )
        _, agent = self.hire("Strategy", caps=["write-document"])
        path, body = (
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "demo"},
        )
        first = self.call("POST", path, body, key="stable-assignment")
        self.assertEqual(self.call("POST", path, body, key="stable-assignment"), first)
        with self.app.db.transaction(True) as c:
            actor = get(c, "users", "pavan")
            actor["department_ids"] = []
            put(c, "users", actor)
        with self.assertRaises(Error) as error:
            self.call("POST", path, body, key="stable-assignment")
        self.assertEqual(error.exception.code, "replay_access_changed")

    def test_queue_admission_limit_does_not_create_an_extra_run(self):
        _, agent = self.hire("Strategy", caps=["write-document"])
        self.app.config["MAX_ACTIVE_RUNS_PER_USER"] = 1
        self.start(agent, "First task")
        with self.assertRaises(Error) as error:
            self.start(agent, "Second task")
        self.assertEqual(error.exception.status, 429)
        self.assertEqual(error.exception.code, "queue_full")
        self.assertEqual(len(self.call("GET", "runs")), 1)

    def test_acceptance_names_and_slide_bounds(self):
        from backend.quality import acceptance_for

        for requested in [{"required_sections": ["!!!"]}, {"slide_count": 30}]:
            with self.assertRaises(Error):
                acceptance_for("launch", "Launch package", requested)
        criteria = acceptance_for(
            "brief", "Decision brief", {"required_sections": ["风险"]}
        )
        self.assertEqual(criteria["required_sections"], ["风险"])

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
