import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import Application
from backend.api.application import create_app
from backend.auth import Authentication, provision, password_hash, password_matches
from backend.contracts import Error
from backend.db import get, put, all_rows

PASSWORD = "Test-only long password 123!"


class PasswordAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = Application(
            Path(self.tmp.name) / "auth.db", {"AUTH_MODE": "password"}
        )
        provision(self.service, "owner", PASSWORD, "pavan")
        self.client = TestClient(
            create_app(self.service, start_worker=False), base_url="http://localhost"
        )
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.service.close()
        self.tmp.cleanup()

    def login(self):
        response = self.client.post(
            "/api/auth/login", json={"username": "owner", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_sessions_ignore_development_impersonation(self):
        self.assertEqual(
            self.client.get("/api/me", headers={"X-Dev-User": "amol"}).status_code, 401
        )
        response = self.login()
        self.assertEqual(
            self.client.get("/api/me", headers={"X-Dev-User": "amol"}).json()["id"],
            "pavan",
        )
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertNotIn(PASSWORD, response.text)
        token = self.client.cookies.get("agent_session")
        with self.service.db.transaction() as c:
            stored = all_rows(c, "auth_sessions")
            self.assertNotIn(token, str(stored))
            account = all_rows(c, "password_accounts")[0]
            self.assertNotIn(PASSWORD, str(account))
            self.assertTrue(password_matches(PASSWORD, account["password_hash"]))
        self.assertEqual(
            self.client.get("/api/auth/session").json()["csrf_token"],
            response.json()["csrf_token"],
        )

    def test_mutations_require_csrf_and_logout_revokes(self):
        response = self.login()
        csrf = response.json()["csrf_token"]
        self.assertEqual(
            self.client.post(
                "/api/agents/quick-create",
                json={"description": "Summarize notes", "name": "Notes"},
                headers={"Idempotency-Key": "a"},
            ).status_code,
            403,
        )
        good = self.client.post(
            "/api/agents/quick-create",
            json={"description": "Summarize notes", "name": "Notes"},
            headers={"Idempotency-Key": "a", "X-CSRF-Token": csrf},
        )
        self.assertEqual(good.status_code, 200, good.text)
        token = self.client.cookies.get("agent_session")
        out = self.client.post(
            "/api/auth/logout", json={}, headers={"X-CSRF-Token": csrf}
        )
        self.assertEqual(out.status_code, 200)
        self.client.cookies.set("agent_session", token)
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_bad_password_and_unknown_user_have_same_error(self):
        responses = [
            self.client.post(
                "/api/auth/login", json={"username": name, "password": "wrong"}
            ).json()["error"]["message"]
            for name in ["owner", "unknown"]
        ]
        self.assertEqual(responses[0], responses[1])
        self.assertNotIn("wrong", responses[0])

    def test_login_rate_limit(self):
        for _ in range(10):
            self.client.post(
                "/api/auth/login", json={"username": "owner", "password": "wrong"}
            )
        self.assertEqual(
            self.client.post(
                "/api/auth/login", json={"username": "owner", "password": PASSWORD}
            ).status_code,
            429,
        )

    def test_disabled_account_password_reset_and_expiry_invalidate_sessions(self):
        self.login()
        with self.service.db.transaction(True) as c:
            account = all_rows(c, "password_accounts")[0]
            account["password_hash"] = password_hash("Replacement password 456!")
            put(c, "password_accounts", account)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        with self.service.db.transaction(True) as c:
            account["password_hash"] = password_hash(PASSWORD)
            put(c, "password_accounts", account)
        self.login()
        with self.service.db.transaction(True) as c:
            session = all_rows(c, "auth_sessions")[-1]
            session["expires_at"] = "2000-01-01T00:00:00+00:00"
            put(c, "auth_sessions", session)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.login()
        with self.service.db.transaction(True) as c:
            account["active"] = False
            put(c, "password_accounts", account)
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_production_guard_and_secure_cookie(self):
        self.service.config.update(
            APP_ENV="production", APP_ORIGIN="http://example.com"
        )
        with self.assertRaises(Error):
            Authentication(self.service)
        self.service.config["APP_ORIGIN"] = "https://example.com"
        auth = Authentication(self.service)
        auth.close()
        self.service.config["AUTH_MODE"] = "development"
        with self.assertRaises(Error):
            Authentication(self.service)

    def test_password_spaces_are_preserved(self):
        password = "  leading and trailing spaces  "
        provision(self.service, "spaces", password, "tarun")
        response = self.client.post(
            "/api/auth/login", json={"username": "spaces", "password": password}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/api/me").json()["id"], "tarun")

    def test_unknown_origin_and_host_rejected(self):
        self.assertEqual(
            self.client.get(
                "/api/auth/config", headers={"Origin": "https://evil.test"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/", headers={"Host": "evil.test"}).status_code, 403
        )
        self.assertIn("x-request-id", self.client.get("/").headers)
        self.assertEqual(self.client.get("/api/ready").status_code, 200)

    def test_production_cookie_is_secure_and_host_scoped(self):
        self.service.config.update(
            APP_ENV="production", APP_ORIGIN="https://example.com"
        )
        api = create_app(self.service, start_worker=False)
        with TestClient(api, base_url="https://example.com") as client:
            response = client.post(
                "/api/auth/login", json={"username": "owner", "password": PASSWORD}
            )
            self.assertEqual(response.status_code, 200)
            cookie = response.headers["set-cookie"].lower()
            self.assertIn("__host-agent_session=", cookie)
            self.assertIn("secure", cookie)
            self.assertIn("path=/", cookie)
            self.assertNotIn("domain=", cookie)
            self.assertEqual(client.get("/api/me").status_code, 200)
            self.assertEqual(
                client.get("/", headers={"Host": "attacker.test"}).status_code, 403
            )
            # Only the liveness probe is exempt, so a host's internal health check can pass.
            self.assertEqual(client.get("/api/health", headers={"Host": "10.0.0.5:10000"}).status_code, 200)
            self.assertEqual(client.get("/api/ready", headers={"Host": "10.0.0.5:10000"}).status_code, 403)
            self.assertEqual(
                client.get(
                    "/api/me", headers={"Cookie": "agent_session=spoofed"}
                ).status_code,
                401,
            )

    def test_disabling_and_reenabling_does_not_restore_old_session(self):
        from backend.auth import set_account_active

        self.login()
        set_account_active(self.service, "owner", False)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        set_account_active(self.service, "owner", True)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.login()
        self.assertEqual(self.client.get("/api/me").status_code, 200)
