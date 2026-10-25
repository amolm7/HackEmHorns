"""Self-service sign-up for the hosted demo, and the first-boot bootstrap."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app import Application
from backend.api.application import create_app
from backend.auth import provision
from backend.db import all_rows, get

PASSWORD = "Demo long password 123!"


def make(tmp, **config):
    service = Application(Path(tmp) / "s.db", {"AUTH_MODE": "password", **config})
    provision(service, "owner", PASSWORD, "pavan")
    client = TestClient(create_app(service, start_worker=False), base_url="http://localhost")
    client.__enter__()
    return service, client


class SignupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def close(self, service, client):
        client.__exit__(None, None, None)
        service.close()

    def test_disabled_by_default(self):
        service, client = make(self.tmp.name)
        try:
            self.assertEqual(client.get("/api/auth/config").json()["signup"], False)
            r = client.post("/api/auth/signup", json={"username": "newbie", "password": PASSWORD})
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.json()["error"]["code"], "signup_disabled")
        finally:
            self.close(service, client)

    def test_signup_creates_a_member_who_approves_their_own_hires(self):
        service, client = make(self.tmp.name, ALLOW_SIGNUP="1")
        try:
            self.assertEqual(client.get("/api/auth/config").json()["signup"], True)
            r = client.post("/api/auth/signup", json={"username": "Tester-One", "password": PASSWORD})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["user"]["id"], "u-tester-one")
            self.assertEqual(client.get("/api/me").json()["id"], "u-tester-one")
            user = r.json()["user"]
            self.assertEqual(user["roles"], ["manager", "builder"])
            self.assertEqual(user["org_id"], "hacktx")
            self.assertNotIn("admin", user["roles"])
            # Their own quick-create is confirmed straight away: they are their own manager.
            csrf = r.json()["csrf_token"]
            made = client.post(
                "/api/agents/quick-create",
                json={"description": "Write short documents for me", "name": "Notes helper", "capability_ids": ["write-document"],
                      "department_id": "support", "model_profile_id": "demo"},
                headers={"Idempotency-Key": "k1", "X-CSRF-Token": csrf},
            )
            self.assertEqual(made.status_code, 200, made.text)
            self.assertEqual(made.json()["status"], "created")
            # They can sign in again with the same password, and the password is never stored in clear.
            client.cookies.clear()
            again = client.post("/api/auth/login", json={"username": "tester-one", "password": PASSWORD})
            self.assertEqual(again.status_code, 200)
            with service.db.transaction() as c:
                self.assertNotIn(PASSWORD, str(all_rows(c, "password_accounts")))
        finally:
            self.close(service, client)

    def test_admin_only_actions_stay_closed_to_signups(self):
        service, client = make(self.tmp.name, ALLOW_SIGNUP="1")
        try:
            r = client.post("/api/auth/signup", json={"username": "visitor", "password": PASSWORD})
            csrf = r.json()["csrf_token"]
            denied = client.post(
                "/api/integrations/github/connect",
                json={"repository": "a/b", "department_id": "support"},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(denied.status_code, 403)
        finally:
            self.close(service, client)

    def test_rejects_bad_or_duplicate_usernames_and_short_passwords(self):
        service, client = make(self.tmp.name, ALLOW_SIGNUP="1")
        try:
            for name, password, status in [
                ("ab", PASSWORD, 400),
                ("bad name!", PASSWORD, 400),
                ("fine-name", "short", 400),
                ("owner", PASSWORD, 409),
                ("pavan", PASSWORD, 409),
                ("Amol", PASSWORD, 409),
                ("admin", PASSWORD, 409),
            ]:
                with self.subTest(name=name):
                    r = client.post("/api/auth/signup", json={"username": name, "password": password})
                    self.assertEqual(r.status_code, status, r.text)
            self.assertEqual(client.post("/api/auth/signup", json={"username": "x" * 5, "password": PASSWORD, "extra": 1}).status_code, 422)
        finally:
            self.close(service, client)

    def test_invite_code_is_required_when_configured(self):
        service, client = make(self.tmp.name, ALLOW_SIGNUP="1", SIGNUP_CODE="orbit-demo")
        try:
            self.assertEqual(client.get("/api/auth/config").json()["invite_code"], True)
            body = {"username": "guest", "password": PASSWORD}
            self.assertEqual(client.post("/api/auth/signup", json=body).status_code, 403)
            self.assertEqual(client.post("/api/auth/signup", json={**body, "code": "wrong"}).status_code, 403)
            self.assertEqual(client.post("/api/auth/signup", json={**body, "code": "orbit-demo"}).status_code, 200)
        finally:
            self.close(service, client)

    def test_signups_are_rate_limited_and_capped(self):
        service, client = make(self.tmp.name, ALLOW_SIGNUP="1", SIGNUPS_PER_HOUR="2", SIGNUP_LIMIT="3")
        try:
            codes = [client.post("/api/auth/signup", json={"username": f"user{i}", "password": PASSWORD}).status_code for i in range(3)]
            self.assertEqual(codes, [200, 200, 429])
        finally:
            self.close(service, client)
        service, client = make(tempfile.mkdtemp(), ALLOW_SIGNUP="1", SIGNUP_LIMIT="2")
        try:
            self.assertEqual(client.post("/api/auth/signup", json={"username": "first", "password": PASSWORD}).status_code, 200)
            full = client.post("/api/auth/signup", json={"username": "second", "password": PASSWORD})
            self.assertEqual(full.status_code, 403)
            self.assertEqual(full.json()["error"]["code"], "signup_full")
        finally:
            self.close(service, client)


class BootstrapTests(unittest.TestCase):
    def test_creates_admin_once_and_connects_github_for_both_departments(self):
        from backend import bootstrap

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "b.db")
            settings = {"ADMIN_USERNAME": "Demo-Admin", "ADMIN_PASSWORD": PASSWORD,
                        "GITHUB_DEMO_REPO": "me/click", "GITHUB_PERSONAL_ACCESS_TOKEN": "t"}
            calls = []

            def fake_connect(app, actor, data):
                calls.append((actor, data["department_id"], data["repository"]))
                from backend.db import put
                with app.db.transaction(True) as c:
                    put(c, "connections", {"id": "github:hacktx", "org_id": "hacktx", "active": True})

            with patch.object(bootstrap, "connect_github", fake_connect):
                first = bootstrap.run(settings, path)
                second = bootstrap.run(settings, path)
            self.assertEqual(first, {"admin": "created", "github": "connected"})
            self.assertEqual(second, {"admin": "exists", "github": "exists"})
            self.assertEqual(calls[0], ("amol", "support", "me/click"))
            self.assertEqual({c[1] for c in calls}, {"support", "engineering"})
            service = Application(path, {"AUTH_MODE": "password"})
            try:
                with service.db.transaction() as c:
                    account = next(a for a in all_rows(c, "password_accounts") if a["username"] == "demo-admin")
                    self.assertEqual(account["actor_id"], "amol")
            finally:
                service.close()

    def test_failures_never_raise_and_nothing_configured_is_a_no_op(self):
        from backend import bootstrap

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "b.db")
            self.assertEqual(bootstrap.run({}, path), {"admin": "skipped", "github": "skipped"})
            settings = {"ADMIN_USERNAME": "a", "ADMIN_PASSWORD": "short", "GITHUB_DEMO_REPO": "me/click",
                        "GITHUB_PERSONAL_ACCESS_TOKEN": "t"}
            with patch.object(bootstrap, "connect_github", side_effect=RuntimeError("offline")):
                status = bootstrap.run(settings, path)
            self.assertEqual(status, {"admin": "failed", "github": "failed"})


if __name__ == "__main__":
    unittest.main()
