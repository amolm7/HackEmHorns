import concurrent.futures
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from backend.app import Application
from backend.contracts import Error, digest
from backend.db import get, put, all_rows
from backend.runtime import model
from backend.api.application import create_app
from fastapi.testclient import TestClient


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.db"
        self.app = Application(self.path, {"ALLOW_TEST_ORG": True})

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def call(self, method, path, data=None, user="pavan", key=None):
        return self.app.handle(method, "/api/" + path, data, user, key)

    def proposal(
        self,
        user="pavan",
        manager="pavan",
        message="Hire a support triage agent and draft replies",
        caps=None,
    ):
        conv = self.call("POST", "recruiter/conversations", {}, user)
        data = {"message": message, "department_id": "support", "manager_id": manager}
        if caps is not None:
            data["capability_ids"] = caps
        return self.call(
            "POST", f'recruiter/conversations/{conv["id"]}/messages', data, user
        )["proposal"]

    def hire(self, **kwargs):
        p = self.proposal(**kwargs)
        return self.call(
            "POST",
            f'recruiter/proposals/{p["id"]}/confirm',
            {"revision": p["revision"]},
            key="hire:" + p["id"],
        )

    def start_run(
        self, agent, task="Triage the urgent login outage and draft a reply", **extra
    ):
        return self.call(
            "POST",
            f'agents/{agent["id"]}/runs',
            {"task": task, **extra},
            key="run:" + str(len(self.call("GET", "runs"))),
        )

    def pending(self):
        return self.call("GET", "approvals?status=pending")

    def approve(self, a, key=None, decision="approve", comment=""):
        return self.call(
            "POST",
            f'approvals/{a["id"]}/decision',
            {"decision": decision, "comment": comment},
            key=key or "decision:" + a["id"],
        )

    def drain(self, auto=True, n=20):
        for _ in range(n):
            self.app.runtime.tick()
            if auto:
                for a in self.pending():
                    self.approve(a)

    def steps(self, run):
        return self.call("GET", f'runs/{run["id"]}/steps')

    def test_registry_discovery_and_real_read_validation(self):
        self.assertEqual(len(self.call("GET", "capabilities")), 3)
        self.assertEqual(len(self.app.mcp.discover()), 3)
        v = self.call(
            "POST",
            "capabilities/ticket-search/validate",
            {"connection_id": "support-local", "department_id": "support"},
        )
        self.assertTrue(v["passed"])
        self.assertEqual(v["evidence"]["tickets"][0]["id"], "T-101")
        self.assertNotIn("secret_ref", json.dumps(self.call("GET", "connections")))

    def test_hire_defaults_intern_and_confirm_idempotency(self):
        p = self.proposal()
        path = f'recruiter/proposals/{p["id"]}/confirm'
        body = {"revision": 1, "level": "associate"}
        a = self.call("POST", path, body, key="same")
        b = self.call("POST", path, body, key="same")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(a["level"], "intern")
        self.assertEqual(len(self.call("GET", "agents")), 1)
        with self.assertRaises(Error) as e:
            self.call("POST", path, {"revision": 2}, key="same")
        self.assertEqual(e.exception.code, "idempotency_conflict")

    def test_builder_needs_assigned_manager_confirmation(self):
        p = self.proposal(user="shaun")
        with self.assertRaises(Error):
            self.call(
                "POST",
                f'recruiter/proposals/{p["id"]}/confirm',
                {"revision": 1},
                user="shaun",
                key="builder",
            )
        self.assertEqual(len(self.call("GET", "agents")), 0)
        a = self.call(
            "POST",
            f'recruiter/proposals/{p["id"]}/confirm',
            {"revision": 1},
            key="manager",
        )
        self.assertEqual(a["status"], "active")

    def test_missing_fields_and_stale_proposal(self):
        conv = self.call("POST", "recruiter/conversations", {})
        first = self.call(
            "POST",
            f'recruiter/conversations/{conv["id"]}/messages',
            {"message": "Hire support help"},
        )["proposal"]
        self.assertIn("manager_id", first["missing_fields"])
        latest = self.call(
            "POST",
            f'recruiter/conversations/{conv["id"]}/messages',
            {
                "message": "Use Support with Pavan",
                "department_id": "support",
                "manager_id": "pavan",
            },
        )["proposal"]
        self.assertEqual(latest["revision"], 2)
        with self.assertRaises(Error) as e:
            self.call(
                "POST",
                f'recruiter/proposals/{first["id"]}/confirm',
                {"revision": 1},
                key="stale",
            )
        self.assertEqual(e.exception.code, "stale_proposal")

    def test_unsupported_connector_and_model_configuration(self):
        conv = self.call("POST", "recruiter/conversations", {})
        with self.assertRaises(Error):
            self.call(
                "POST",
                f'recruiter/conversations/{conv["id"]}/messages',
                {"message": "Connect GitHub"},
            )
        with self.assertRaises(Error):
            self.call(
                "POST",
                f'recruiter/conversations/{conv["id"]}/messages',
                {"message": "Hire support", "mode": "gemini"},
            )

    def test_intern_has_zero_tool_calls_before_review(self):
        a = self.hire()
        r = self.start_run(a)
        self.app.runtime.tick()
        self.assertEqual(
            self.call("GET", f'runs/{r["id"]}')["status"], "awaiting_approval"
        )
        self.assertEqual([s for s in self.steps(r) if s["kind"] == "tool"], [])
        review = self.pending()[0]
        self.assertEqual(review["action"]["tool_id"], "search_tickets")
        self.approve(review)
        self.app.runtime.tick()
        self.assertEqual(len([s for s in self.steps(r) if s["kind"] == "tool"]), 1)

    def test_duplicate_and_concurrent_approvals_do_not_execute_twice(self):
        a = self.hire()
        r = self.start_run(a)
        self.app.runtime.tick()
        review = self.pending()[0]

        def decide(_):
            return self.approve(review, key="same-review")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(decide, range(4)))
        self.assertEqual(len({x["approval"]["id"] for x in results}), 1)
        self.app.runtime.tick()
        self.app.runtime.tick()
        self.assertEqual(len([s for s in self.steps(r) if s["kind"] == "tool"]), 1)
        with self.assertRaises(Error):
            self.approve(review, key="different-review")

    def test_rejection_and_cancel_do_not_run_tool(self):
        a = self.hire()
        r = self.start_run(a)
        self.app.runtime.tick()
        self.approve(self.pending()[0], decision="reject")
        self.drain(False, 2)
        self.assertEqual(self.call("GET", f'runs/{r["id"]}')["status"], "failed")
        self.assertFalse(any(s["kind"] == "tool" for s in self.steps(r)))
        r = self.start_run(a)
        self.app.runtime.tick()
        review = self.pending()[0]
        self.call("POST", f'runs/{r["id"]}/cancel', {})
        with self.assertRaises(Error):
            self.approve(review)
        self.assertEqual(self.call("GET", f'runs/{r["id"]}')["status"], "cancelled")

    def test_revision_creates_fresh_approval(self):
        a = self.hire()
        r = self.start_run(a)
        self.app.runtime.tick()
        old = self.pending()[0]
        self.approve(old, decision="request_revision", comment="password reset")
        self.app.runtime.tick()
        new = self.pending()[0]
        self.assertNotEqual(old["id"], new["id"])
        self.assertEqual(new["action"]["arguments"]["query"], "password reset")
        self.assertFalse(any(s["kind"] == "tool" for s in self.steps(r)))
        self.approve(new)
        self.app.runtime.tick()
        self.assertTrue(any(s["kind"] == "tool" for s in self.steps(r)))

    def test_wrong_manager_member_and_auditor_cannot_decide(self):
        a = self.hire()
        self.start_run(a)
        self.app.runtime.tick()
        approval = self.pending()[0]
        for user in ["tarun", "member", "auditor", "shaun"]:
            with self.assertRaises(Error):
                self.call(
                    "POST",
                    f'approvals/{approval["id"]}/decision',
                    {"decision": "approve"},
                    user,
                    key="bad-" + user,
                )
        self.assertEqual(len(self.call("GET", "approvals", user="auditor")), 1)

    def test_promotion_reads_run_but_draft_still_waits(self):
        a = self.hire()
        self.call(
            "POST",
            f'agents/{a["id"]}/level',
            {"level": "associate", "reason": "Reviewed read behavior"},
        )
        r = self.start_run(a)
        self.drain(False, 5)
        steps = [s for s in self.steps(r) if s["kind"] == "tool"]
        self.assertEqual(len(steps), 2)
        self.assertEqual(self.pending()[0]["action"]["tool_id"], "create_draft")
        self.approve(self.pending()[0])
        self.drain(False, 3)
        run = self.call("GET", f'runs/{r["id"]}')
        self.assertEqual(run["status"], "completed")
        draft = [s for s in self.steps(r) if s["label"] == "create_draft"][0]["data"][
            "result"
        ]
        self.assertFalse(draft["sent"])

    def test_demotion_and_org_policy_checked_before_next_action(self):
        a = self.hire()
        self.call(
            "POST",
            f'agents/{a["id"]}/level',
            {"level": "associate", "reason": "Testing scoped reads"},
        )
        r = self.start_run(a)
        self.app.runtime.tick()
        self.call(
            "POST",
            f'agents/{a["id"]}/level',
            {"level": "intern", "reason": "More supervision needed"},
        )
        self.app.runtime.tick()
        self.assertEqual(self.pending()[0]["action"]["tool_id"], "search_docs")
        self.assertEqual(len([s for s in self.steps(r) if s["kind"] == "tool"]), 1)

    def test_revoked_connection_blocks_already_approved_action(self):
        a = self.hire()
        r = self.start_run(a)
        self.app.runtime.tick()
        self.approve(self.pending()[0])
        self.call("PATCH", "connections/support-local", {"active": False}, user="amol")
        self.app.runtime.tick()
        run = self.call("GET", f'runs/{r["id"]}')
        self.assertEqual(run["status"], "failed")
        self.assertFalse(any(s["kind"] == "tool" for s in self.steps(r)))

    def test_spec_change_invalidates_pending_approval_and_resets_level(self):
        a = self.hire()
        r = self.start_run(a)
        self.app.runtime.tick()
        review = self.pending()[0]
        new = self.call(
            "PATCH",
            f'agents/{a["id"]}',
            {"name": "New job", "expected_spec_version": 1},
        )
        self.assertEqual(new["spec_version"], 2)
        self.assertEqual(new["level"], "intern")
        with self.assertRaises(Error):
            self.approve(review)
        with self.assertRaises(Error):
            self.call(
                "PATCH",
                f'agents/{a["id"]}',
                {"level": "associate", "expected_spec_version": 2},
            )

    def test_pause_survives_restart_then_approval_executes(self):
        a = self.hire()
        r = self.start_run(a)
        self.app.runtime.tick()
        review = self.pending()[0]
        self.app.close()
        self.app = Application(self.path, {"ALLOW_TEST_ORG": True})
        self.app.runtime.recover()
        self.assertEqual(
            self.call("GET", f'runs/{r["id"]}')["status"], "awaiting_approval"
        )
        self.approve(review)
        self.app.runtime.tick()
        self.assertEqual(len([s for s in self.steps(r) if s["kind"] == "tool"]), 1)

    def test_write_crash_recovery_uses_same_durable_execution_id(self):
        a = self.hire()
        self.call(
            "POST",
            f'agents/{a["id"]}/level',
            {"level": "associate", "reason": "Read tests passed"},
        )
        r = self.start_run(a)
        self.drain(False, 3)
        review = self.pending()[0]
        self.approve(review)
        with self.app.db.transaction(True) as c:
            action = get(c, "actions", review["action_id"])
            action["status"] = "executing"
            put(c, "actions", action)
        first = self.app.mcp.call("create_draft", action["arguments"], action["id"])
        self.app.close()
        self.app = Application(self.path, {"ALLOW_TEST_ORG": True})
        self.app.runtime.recover()
        self.drain(False, 3)
        draft = [s for s in self.steps(r) if s["label"] == "create_draft"][0]["data"][
            "result"
        ]
        self.assertEqual(first["draft_id"], draft["draft_id"])
        with self.app.db.transaction() as c:
            self.assertEqual(len(all_rows(c, "tool_executions")), 1)

    def test_marketplace_portability_reset_and_rebinding(self):
        a = self.hire()
        self.call(
            "POST",
            f'agents/{a["id"]}/level',
            {"level": "associate", "reason": "Reviewed"},
        )
        listing = self.call(
            "POST", "marketplace", {"kind": "agent", "source_id": a["id"]}
        )
        payload = json.dumps(listing["payload"])
        self.assertNotIn("support-local", payload)
        self.assertNotIn("validation_id", payload)
        self.assertNotIn("level", listing["payload"])
        install = self.call(
            "POST",
            f'marketplace/{listing["id"]}/install',
            {"department_id": "support", "manager_id": "pavan"},
            key="install",
        )["resource"]
        self.assertEqual(install["level"], "intern")
        self.assertEqual(install["bindings"], [])
        self.assertEqual(install["status"], "needs_connections")
        with self.assertRaises(Error):
            self.start_run(install)
        bindings = []
        for cap in install["required_capabilities"]:
            v = self.call(
                "POST",
                f'capabilities/{cap["id"]}/validate',
                {"department_id": "support", "connection_id": "support-local"},
            )
            bindings.append(
                {
                    "capability_id": cap["id"],
                    "connection_id": "support-local",
                    "validation_id": v["id"],
                }
            )
        new = self.call(
            "PATCH",
            f'agents/{install["id"]}',
            {"bindings": bindings, "expected_spec_version": 1},
        )
        self.assertEqual(new["status"], "active")
        self.assertEqual(new["level"], "intern")
        self.assertEqual(self.call("GET", "marketplace")[0]["installation_count"], 1)

    def test_forged_validation_and_department_are_rejected(self):
        a = self.hire()
        binding = dict(a["bindings"][0])
        binding["connection_id"] = "not-real"
        with self.assertRaises(Error):
            self.call(
                "PATCH",
                f'agents/{a["id"]}',
                {"bindings": [binding], "expected_spec_version": 1},
            )
        with self.assertRaises(Error):
            self.call(
                "POST",
                "capabilities/ticket-search/validate",
                {"connection_id": "support-local", "department_id": "engineering"},
            )

    def test_capability_install_copies_no_connection(self):
        l = self.call(
            "POST", "marketplace", {"kind": "capability", "source_id": "ticket-search"}
        )
        i = self.call("POST", f'marketplace/{l["id"]}/install', {}, key="cap-install")
        self.assertEqual(i["resource"]["status"], "needs_connection")
        self.assertIsNone(i["resource"]["connection_id"])

    def test_metrics_do_not_invent_task_success(self):
        a = self.hire()
        r = self.start_run(a)
        self.drain()
        p = self.call("GET", f'agents/{a["id"]}/performance')
        self.assertEqual(p["approved_actions"], 3)
        self.assertEqual(p["evaluated_tasks"], 0)
        self.assertIsNone(p["task_success_rate"])
        self.assertIsNone(self.call("GET", "leaderboard")["agents"][0]["approval_rate"])
        self.call(
            "POST",
            f'runs/{r["id"]}/outcome',
            {"success": True, "comment": "Checked answer and sources"},
            key="outcome",
        )
        self.assertEqual(
            self.call("GET", f'agents/{a["id"]}/performance')["task_success_rate"], 1
        )

    def test_organization_isolation(self):
        a = self.hire()
        r = self.start_run(a)
        self.assertEqual(self.call("GET", "agents", user="other-org"), [])
        self.assertEqual(self.call("GET", "marketplace", user="other-org"), [])
        for path in [f'agents/{a["id"]}', f'runs/{r["id"]}']:
            with self.assertRaises(Error):
                self.call("GET", path, user="other-org")

    def test_step_limit_and_model_tool_allowlist(self):
        a = self.hire()
        r = self.start_run(a, max_steps=1)
        self.drain()
        self.assertEqual(self.call("GET", f'runs/{r["id"]}')["status"], "failed")
        self.app.config["GEMINI_API_KEY"] = "test-not-a-real-key"
        content = {
            "role": "model",
            "parts": [{"functionCall": {"name": "send_email", "args": {}}}],
        }
        r = self.start_run(a, mode="gemini")
        with patch.object(model, "generate", return_value=(content, {})):
            self.drain(False, 3)
        self.assertEqual(self.call("GET", f'runs/{r["id"]}')["status"], "failed")

    def test_gemini_call_metadata_and_usage_survive_pause(self):
        a = self.hire()
        self.app.config["GEMINI_API_KEY"] = "test-not-a-real-key"
        r = self.start_run(a, mode="gemini")
        response = (
            {
                "role": "model",
                "parts": [
                    {
                        "functionCall": {
                            "name": "search_tickets",
                            "args": {"query": "login"},
                            "id": "call-1",
                        },
                        "thoughtSignature": "opaque-signature",
                    }
                ],
            },
            {"promptTokenCount": 11, "candidatesTokenCount": 4},
        )
        with patch.object(model, "generate", return_value=response):
            self.app.runtime.tick()
        self.app.runtime.tick()
        self.approve(self.pending()[0])
        self.app.runtime.tick()
        with patch.object(
            model,
            "generate",
            return_value=(
                {"role": "model", "parts": [{"text": "Urgent outage [T-101]."}]},
                {"promptTokenCount": 9, "candidatesTokenCount": 5},
            ),
        ) as generate:
            self.app.runtime.tick()
            contents = generate.call_args.args[1]
            self.assertEqual(
                contents[1]["parts"][0]["thoughtSignature"], "opaque-signature"
            )
            self.assertEqual(
                contents[2]["parts"][0]["functionResponse"]["id"], "call-1"
            )
        run = self.call("GET", f'runs/{r["id"]}')
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["usage"], {"input_tokens": 20, "output_tokens": 9})

    def test_capability_recruiter_attaches_only_after_confirmation(self):
        a = self.hire(message="Search support tickets", caps=["ticket-search"])
        conv = self.call("POST", "recruiter/conversations", {})
        p = self.call(
            "POST",
            f'recruiter/conversations/{conv["id"]}/messages',
            {
                "message": "Add help documents",
                "target_agent_id": a["id"],
                "capability_ids": ["help-docs"],
            },
        )["proposal"]
        self.assertEqual(len(self.call("GET", f'agents/{a["id"]}')["bindings"]), 1)
        new = self.call(
            "POST",
            f'recruiter/proposals/{p["id"]}/confirm',
            {"revision": p["revision"]},
            key="attach",
        )
        self.assertEqual(len(new["bindings"]), 2)
        self.assertEqual(new["spec_version"], 2)
        self.assertEqual(new["level"], "intern")

    def test_http_transport_origin_errors_and_idempotency_header(self):
        with TestClient(
            create_app(self.app, start_worker=False), base_url="http://localhost"
        ) as client:
            self.assertEqual(client.get("/api/me").json()["id"], "pavan")
            for body, headers, status in [
                (
                    "{}",
                    {
                        "Content-Type": "application/json",
                        "Origin": "https://evil.example",
                    },
                    403,
                ),
                ("[]", {"Content-Type": "application/json"}, 422),
                ("{}", {"Content-Type": "text/plain"}, 415),
            ]:
                response = client.post(
                    "/api/recruiter/conversations", content=body, headers=headers
                )
                self.assertEqual(response.status_code, status)
                self.assertIn("code", response.json()["error"])
            agent = self.hire()
            response = client.post(
                f'/api/agents/{agent["id"]}/runs', json={"task": "login"}
            )
            self.assertEqual(response.status_code, 422)

    def test_org_policy_overrides_associate_reads(self):
        agent = self.hire()
        self.call(
            "POST",
            f'agents/{agent["id"]}/level',
            {"level": "associate", "reason": "Read behavior reviewed"},
        )
        self.call("PATCH", "policy", {"require_all_approvals": True}, user="amol")
        run = self.start_run(agent)
        self.app.runtime.tick()
        self.assertEqual(
            self.call("GET", f'runs/{run["id"]}')["status"], "awaiting_approval"
        )
        self.assertFalse(any(s["kind"] == "tool" for s in self.steps(run)))
        self.assertEqual(self.pending()[0]["policy"]["policy_revision"], 2)

    def test_changed_approved_arguments_are_not_executed(self):
        agent = self.hire()
        run = self.start_run(agent)
        self.app.runtime.tick()
        review = self.pending()[0]
        self.approve(review)
        with self.app.db.transaction(True) as c:
            action = get(c, "actions", review["action_id"])
            action["arguments"]["query"] = "tampered"
            put(c, "actions", action)
        self.app.runtime.tick()
        current = self.call("GET", f'runs/{run["id"]}')
        self.assertEqual(current["status"], "failed")
        self.assertIn("snapshot", current["error"])
        self.assertFalse(any(s["kind"] == "tool" for s in self.steps(run)))

    def test_capability_reuse_credits_original_creator(self):
        listing = self.call(
            "POST", "marketplace", {"kind": "capability", "source_id": "ticket-search"}
        )
        self.assertEqual(listing["publisher_id"], "pavan")
        self.assertEqual(listing["creator_id"], "amol")
        self.call(
            "POST", f'marketplace/{listing["id"]}/install', {}, key="creator-test"
        )
        board = self.call("GET", "leaderboard")
        self.assertEqual(
            board["creator_reuse"][0], {"creator_id": "amol", "installations": 1}
        )
        self.assertEqual(board["capability_reuse"][0]["creator_id"], "amol")


if __name__ == "__main__":
    unittest.main()
