import tempfile
from pathlib import Path
import unittest
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api.application import create_app
from backend.app import Application


class FastAPITransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = Application(Path(self.tmp.name) / "api.db", {"APPROVAL_SCOPE": "action"})
        self.api = create_app(self.service, start_worker=False)
        self.client = TestClient(self.api, base_url="http://localhost")
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.service.close()
        self.tmp.cleanup()

    def post(self, path, data, key=None, user="pavan"):
        return self.client.post(
            "/api/" + path,
            json=data,
            headers={"X-Dev-User": user, "Idempotency-Key": key or str(uuid4())},
        )

    def hire(self):
        conversation = self.post("recruiter/conversations", {}).json()
        result = self.post(
            f"recruiter/conversations/{conversation['id']}/messages",
            {
                "message": "Hire a support agent to triage and draft replies",
                "department_id": "support",
                "manager_id": "pavan",
            },
        )
        self.assertEqual(result.status_code, 200, result.text)
        proposal = result.json()["proposal"]
        result = self.post(
            f"recruiter/proposals/{proposal['id']}/confirm",
            {"revision": proposal["revision"]},
        )
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_work_queue_http_assignment(self):
        agent = self.hire()
        batch = self.post("work-queue/sample-batch", {"workflow": "support"})
        self.assertEqual(batch.status_code, 200, batch.text)
        item = batch.json()[0]
        response = self.post(
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "demo"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        repeated = self.post(
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "demo"},
        )
        self.assertEqual(repeated.status_code, 409)
        bad = self.post(
            "work-queue", {"workflow": "unknown", "title": "test", "task": "test"}
        )
        self.assertEqual(bad.status_code, 422)

    def test_real_fastapi_routes_and_openapi_contract(self):
        self.assertIsInstance(self.api, FastAPI)
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(
            sum(
                method in ["get", "post", "patch", "delete"]
                for path in schema["paths"].values()
                for method in path
            ),
            59,
        )
        run = schema["paths"]["/api/agents/{agent_id}/runs"]["post"]
        self.assertEqual(
            run["requestBody"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/RunCreate",
        )
        self.assertTrue(
            next(h for h in run["parameters"] if h["name"] == "Idempotency-Key")[
                "required"
            ]
        )
        self.assertEqual(
            schema["components"]["schemas"]["RunCreate"]["additionalProperties"], False
        )
        self.assertIn("ErrorResponse", schema["components"]["schemas"])

    def test_strict_typed_requests_and_safe_validation_errors(self):
        agent = self.hire()
        for payload in [
            {"task": "login", "max_steps": "2"},
            {"task": "login", "max_steps": 21},
            {"task": "login", "mode": "fake"},
            {"task": "login", "roles": ["admin"]},
            {"task": "login", "max_steps": True},
        ]:
            response = self.post(f"agents/{agent['id']}/runs", payload)
            self.assertEqual(response.status_code, 422, response.text)
        response = self.post(
            f"agents/{agent['id']}/runs",
            {"task": "login", "max_steps": "private-input-do-not-echo"},
        )
        self.assertNotIn("private-input-do-not-echo", response.text)
        self.assertEqual(response.json()["error"]["code"], "validation_error")
        self.assertEqual(self.client.get("/api/runs/not-a-uuid").status_code, 422)
        self.assertEqual(self.client.get("/api/runs?status=invalid").status_code, 422)

    def test_role_checks_remain_in_services(self):
        response = self.post("departments", {"name": "Not permitted"}, user="member")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "permission_denied")
        response = self.post("departments", {"name": "Operations"}, user="amol")
        self.assertEqual(response.status_code, 200)

    def test_transport_limits_host_origin_and_content_type(self):
        self.assertEqual(
            self.client.get("/api/me", headers={"Host": "evil.example"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/me", headers={"Origin": "https://evil.example"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/recruiter/conversations",
                content="{}",
                headers={"Content-Type": "text/plain"},
            ).status_code,
            415,
        )
        result = self.client.post(
            "/api/recruiter/conversations",
            content=b"x" * 50001,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(result.status_code, 413)
        result = self.client.post(
            "/api/recruiter/conversations",
            content=iter([b"x" * 25000, b"x" * 25001]),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(result.status_code, 413)
        self.assertEqual(
            self.client.post(
                "/api/recruiter/conversations",
                content="{broken",
                headers={"Content-Type": "application/json"},
            ).status_code,
            422,
        )

    def test_docs_static_and_error_headers(self):
        docs = self.client.get("/docs")
        self.assertEqual(docs.status_code, 200)
        self.assertIn("SwaggerUIBundle", docs.text)
        self.assertIn("nonce=", docs.text)
        self.assertIn("cdn.jsdelivr.net", docs.headers["content-security-policy"])
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("script-src 'self'", page.headers["content-security-policy"])
        self.assertNotIn("unsafe-inline", page.headers["content-security-policy"])
        self.assertEqual(self.client.get("/api/health").json()["transport"], "fastapi")
        response = self.client.get("/api/not-found")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("error", response.json())

    def test_full_hire_run_approval_replay_over_fastapi(self):
        agent = self.hire()
        result = self.post(
            f"agents/{agent['id']}/runs",
            {"task": "Triage the login outage", "max_steps": 8},
            key="submit",
        )
        self.assertEqual(result.status_code, 200, result.text)
        run = result.json()
        self.service.runtime.tick()
        review = self.client.get("/api/approvals?status=pending").json()[0]
        steps = self.client.get(f"/api/runs/{run['id']}/steps").json()
        self.assertFalse(any(s["kind"] == "tool" for s in steps))
        path = f"approvals/{review['id']}/decision"
        first = self.post(path, {"decision": "approve"}, key="review")
        second = self.post(path, {"decision": "approve"}, key="review")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), second.json())
        self.service.runtime.tick()
        steps = self.client.get(f"/api/runs/{run['id']}/steps").json()
        self.assertEqual(sum(s["kind"] == "tool" for s in steps), 1)

    def test_patch_contract_disallows_privilege_fields_and_nulls(self):
        agent = self.hire()
        for body in [
            {"expected_spec_version": 1, "level": "associate"},
            {"expected_spec_version": 1, "name": None},
            {"expected_spec_version": "1", "name": "New name"},
        ]:
            response = self.client.patch("/api/agents/" + agent["id"], json=body)
            self.assertEqual(response.status_code, 422, response.text)

    def test_lifespan_owns_worker_and_mcp_cleanup(self):
        api = create_app(
            settings={"DATABASE_PATH": str(Path(self.tmp.name) / "lifespan.db")}
        )
        with TestClient(api, base_url="http://localhost") as client:
            current = api.state.service
            self.assertTrue(current.runtime.thread.is_alive())
            self.assertEqual(client.get("/api/me").status_code, 200)
        self.assertFalse(current.runtime.thread.is_alive())
        self.assertEqual(current.mcp.server.socket.fileno(), -1)
        self.assertFalse(hasattr(api.state, "service"))


if __name__ == "__main__":
    unittest.main()
