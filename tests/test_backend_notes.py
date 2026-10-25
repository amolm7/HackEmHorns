"""Integration coverage for the backend contracts required by the redesigned UI."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from backend.app import Application
from backend.api.application import create_app
from backend.api.runtime import activity_events
from backend.db import all_rows, get, put


class BackendNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "notes.db"
        self.app = Application(self.path, {"MODEL_API_KEY": "test-only"})
        self.client = TestClient(create_app(self.app, start_worker=False), base_url="http://localhost")
        self.client.__enter__()

    def test_employee_reporting_is_manager_only_and_scoped(self):
        self.assertEqual(self.client.get("/api/employees", headers={"X-Dev-User": "shaun"}).status_code, 403)
        response = self.client.get("/api/employees", headers={"X-Dev-User": "pavan"})
        self.assertEqual(response.status_code, 200)
        rows = response.json()["employees"]
        self.assertIn("shaun", [r["id"] for r in rows])
        self.assertNotIn("other-org", [r["id"] for r in rows])
        self.assertTrue(all("password_hash" not in r for r in rows))

    def test_configured_employee_and_manager_roles(self):
        from scripts.configure_team import configure
        configure(self.app.db)
        self.assertEqual(self.client.get("/api/employees", headers={"X-Dev-User": "pavan"}).status_code, 403)
        response = self.client.get("/api/employees", headers={"X-Dev-User": "shaun"})
        self.assertEqual(response.status_code, 200)
        pavan = next(r for r in response.json()["employees"] if r["id"] == "pavan")
        self.assertEqual(pavan["roles"], ["builder"])

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.app.close()
        self.tmp.cleanup()

    def post(self, path, data, user="pavan", key=None):
        return self.client.post("/api/" + path, json=data, headers={"X-Dev-User": user, "Idempotency-Key": key or str(uuid4())})

    def quick(self, caps=None, **extra):
        r = self.post("agents/quick-create", {"capability_ids": caps or ["write-document"], **extra})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["agent"]

    def task_run(self, agent, user="pavan", **extra):
        r = self.post(f'agents/{agent["id"]}/runs', {"task": "Write a brief about a launch", **extra}, user=user)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def finish(self):
        for _ in range(20):
            self.app.runtime.tick()
            for a in self.app.handle("GET", "/api/approvals?status=pending"):
                r = self.post(f'approvals/{a["id"]}/decision', {"decision": "approve"})
                self.assertEqual(r.status_code, 200, r.text)

    def test_atomic_creation_replay_defaults_and_rollback(self):
        body = {"capability_ids": ["write-document", "make-slideshow"]}
        first = self.post("agents/quick-create", body, key="quick")
        again = self.post("agents/quick-create", body, key="quick")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), again.json())
        other = self.quick(["write-document", "make-slideshow"])
        self.assertNotEqual(first.json()["agent"]["name"], other["name"])
        self.assertEqual(other["level"], "intern")
        with self.app.db.transaction() as c:
            before = {t: len(all_rows(c, t)) for t in ["agents", "proposals", "conversations", "validations"]}
        bad = self.post("agents/quick-create", {"capability_ids": ["write-document"], "manager_id": "member"})
        self.assertEqual(bad.status_code, 400)
        with self.app.db.transaction() as c:
            self.assertEqual(before, {t: len(all_rows(c, t)) for t in before})
        self.assertEqual(self.post("agents/quick-create", {"capability_ids": ["analyze-data"]}, key="quick").status_code, 409)

    def test_builder_still_needs_manager_confirmation(self):
        r = self.post("agents/quick-create", {"capability_ids": ["write-document"]}, user="shaun")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "awaiting_confirmation")
        p = r.json()["proposal"]
        self.assertEqual(self.client.get("/api/agents").json(), [])
        body = {"revision": p["revision"]}
        self.assertEqual(self.post(f'recruiter/proposals/{p["id"]}/confirm', body, user="shaun").status_code, 403)
        self.assertEqual(self.post(f'recruiter/proposals/{p["id"]}/confirm', body).status_code, 200)

    def test_add_tools_is_atomic_versioned_and_always_resets_new_authority(self):
        agent = self.quick()
        self.post(f'agents/{agent["id"]}/level', {"level": "associate", "reason": "Reviewed"})
        path = f'agents/{agent["id"]}/capabilities'
        body = {"capability_ids": ["analyze-data"], "expected_spec_version": 1}
        self.assertEqual(self.post(path, body, user="member").status_code, 403)
        r = self.post(path, body, key="add")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["level"], "intern")
        self.assertEqual(r.json()["spec_version"], 2)
        self.assertEqual(len(r.json()["bindings"]), 2)
        self.assertEqual(self.post(path, body, key="add").json(), r.json())
        self.assertEqual(self.post(path, body).status_code, 409)

    def test_adding_tools_preserves_an_existing_nondefault_connection(self):
        agent = self.quick()
        with self.app.db.transaction(True) as c:
            connection = get(c, "connections", "workspace-local")
            connection["id"] = "workspace-alternative"
            put(c, "connections", connection)
        validation = self.post("capabilities/write-document/validate", {
            "connection_id": "workspace-alternative", "department_id": "support",
        }).json()
        binding = {"capability_id": "write-document", "connection_id": "workspace-alternative", "validation_id": validation["id"]}
        response = self.client.patch(f'/api/agents/{agent["id"]}', json={"bindings": [binding], "expected_spec_version": 1})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.post(f'agents/{agent["id"]}/capabilities', {"capability_ids": ["analyze-data"], "expected_spec_version": 2})
        self.assertEqual(response.status_code, 200, response.text)
        bindings = {b["capability_id"]: b["connection_id"] for b in response.json()["bindings"]}
        self.assertEqual(bindings["write-document"], "workspace-alternative")
        self.assertEqual(bindings["analyze-data"], "workspace-local")

    def test_demo_answer_and_frozen_action_summary(self):
        agent = self.quick()
        run = self.task_run(agent)
        self.app.runtime.tick()
        self.app.runtime.tick()
        review = self.app.handle("GET", "/api/approvals?status=pending")[0]
        self.assertIn("Save a document", review["action"]["summary"])
        self.finish()
        result = self.client.get(f'/api/runs/{run["id"]}').json()
        self.assertEqual(result["status"], "completed")
        self.assertIn("saved a document", result["result"]["answer"])
        self.assertNotIn("slideshow", result["result"]["answer"])
        self.assertIn("No AI model", result["result"]["answer"])

    def test_action_summary_is_part_of_approval_integrity(self):
        agent = self.quick()
        run = self.task_run(agent)
        for _ in range(3):
            self.app.runtime.tick()
        review = self.app.handle("GET", "/api/approvals?status=pending")[0]
        self.post(f'approvals/{review["id"]}/decision', {"decision": "approve"})
        with self.app.db.transaction(True) as c:
            action = get(c, "actions", review["action_id"])
            action["summary"] = "Changed after review"
            put(c, "actions", action)
        self.app.runtime.tick()
        self.assertEqual(self.client.get(f'/api/runs/{run["id"]}').json()["status"], "failed")

    def test_conversation_survives_reload_and_is_owned_by_user_and_agent(self):
        agent, other = self.quick(), self.quick()
        path = f'agents/{agent["id"]}/conversations'
        conv = self.post(path, {}, key="conversation").json()
        self.assertEqual(self.post(path, {}, key="conversation").json(), conv)
        run = self.task_run(agent, conversation_id=conv["id"])
        self.assertEqual(run["thread_id"], conv["id"])
        self.assertEqual(run["conversation_id"], conv["id"])
        self.assertEqual(self.client.get("/api/" + path).json()[-1]["last_run_id"], run["id"])
        payload = {"task": "Continue", "conversation_id": conv["id"]}
        self.assertEqual(self.post(f'agents/{agent["id"]}/runs', payload, user="member").status_code, 403)
        self.assertEqual(self.post(f'agents/{other["id"]}/runs', payload).status_code, 409)
        fresh = self.post(path, {}).json()
        self.assertIsNone(fresh["last_run_id"])
        self.assertEqual(self.client.get("/api/" + path).json()[-1]["id"], fresh["id"])
        self.assertEqual(self.client.get(f'/api/agents/{agent["id"]}/runs').json()[0]["id"], run["id"])

    def test_live_conversation_auto_continues_and_rejects_parallel_messages(self):
        agent = self.quick(model_profile_id="meta")
        conv = self.post(f'agents/{agent["id"]}/conversations', {}).json()
        first = self.task_run(agent, conversation_id=conv["id"], mode="meta")
        with patch("backend.runtime.model.generate", return_value=({"parts": [{"text": "Ready"}]}, {})):
            self.finish()
        second = self.task_run(agent, conversation_id=conv["id"], mode="meta")
        with self.app.db.transaction() as c:
            stored = get(c, "runs", second["id"])
        self.assertEqual(len(stored["contents"]), 3)
        self.assertEqual(stored["thread_id"], first["thread_id"])
        self.assertEqual(self.post(f'agents/{agent["id"]}/runs', {"task": "Parallel", "mode": "meta", "conversation_id": conv["id"]}).status_code, 409)

    def test_archive_preserves_history_cancels_waiting_and_cannot_reactivate(self):
        agent = self.quick()
        run = self.task_run(agent)
        self.app.runtime.tick()
        self.app.runtime.tick()
        path = f'/api/agents/{agent["id"]}'
        self.assertEqual(self.client.delete(path, headers={"X-Dev-User": "member"}).status_code, 403)
        archived = self.client.delete(path)
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(archived.json()["status"], "archived")
        self.assertEqual(self.client.get("/api/agents").json(), [])
        self.assertEqual(len(self.client.get("/api/agents?include_archived=true").json()), 1)
        self.assertEqual(self.client.get(f'/api/runs/{run["id"]}').json()["status"], "cancelled")
        self.assertEqual(self.client.get("/api/approvals?status=pending").json(), [])
        self.assertTrue(self.client.get(path + "/versions").json())
        self.assertEqual(self.post(f'agents/{agent["id"]}/runs', {"task": "No"}).status_code, 409)
        self.assertEqual(self.client.patch(path, json={"name": "Revive", "expected_spec_version": 1}).status_code, 409)

    def test_archive_refuses_in_flight_work_and_rolls_back_prior_cancellations(self):
        agent = self.quick()
        first = self.task_run(agent)
        second = self.task_run(agent)
        with self.app.db.transaction(True) as c:
            put(c, "actions", {"id": "in-flight", "run_id": second["id"], "status": "executing"})
        response = self.client.delete(f'/api/agents/{agent["id"]}')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "action_in_flight")
        self.assertEqual(self.client.get(f'/api/runs/{first["id"]}').json()["status"], "queued")
        self.assertEqual(self.client.get(f'/api/agents/{agent["id"]}').json()["status"], "active")

    def test_activity_stream_rechecks_access_and_streams_durable_state(self):
        agent = self.quick()
        self.task_run(agent)
        request = type("Request", (), {"is_disconnected": AsyncMock(return_value=False)})()
        async def inspect():
            stream = activity_events(self.app, "pavan", agent["id"], request)
            first = await anext(stream)
            self.assertTrue(first.startswith("event: snapshot"))
            payload = json.loads(first.split("data: ", 1)[1])
            self.assertEqual(payload["runs"][0]["agent_id"], agent["id"])
            self.assertNotIn("contents", payload["runs"][0])
            with self.app.db.transaction(True) as c:
                actor = get(c, "users", "pavan")
                actor["department_ids"] = []
                put(c, "users", actor)
            with patch("backend.api.runtime.asyncio.sleep", new_callable=AsyncMock):
                self.assertIn("event: access-lost", await anext(stream))
            await stream.aclose()
        asyncio.run(inspect())
        self.assertEqual(self.client.get(f'/api/agents/{agent["id"]}/events').status_code, 403)

    def test_new_http_contracts_reject_untrusted_fields(self):
        self.assertEqual(self.post("agents/quick-create", {}).status_code, 422)
        self.assertEqual(self.post("agents/quick-create", {"capability_ids": ["write-document"], "level": "associate"}).status_code, 422)
        self.assertEqual(self.client.post("/api/agents/quick-create", json={"capability_ids": ["write-document"]}).status_code, 422)
