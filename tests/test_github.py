import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.api.application import create_app
from backend.contracts import Error
from backend.db import all_rows, get, put
from backend.github import GitHubMCP, GITHUB_TOOLS, repository_name
from tests import test_workspace


class GitHubTransportTests(unittest.TestCase):
    def test_repository_input_is_a_name_or_github_url_not_an_arbitrary_endpoint(self):
        self.assertEqual(repository_name("https://github.com/team/project.git/"), "team/project")
        self.assertEqual(repository_name("another/second-repo"), "another/second-repo")
        for invalid in (None, "https://github.com.evil.test/a/b", "http://localhost/a/b",
                        "https://user:password@github.com/a/b", "a/../b", "https://github.com/a/b/tree/main",
                        "https://github.com/a/b?token=secret"):
            with self.subTest(invalid=invalid), self.assertRaises(Error):
                repository_name(invalid)

    def test_real_rpc_sequence_supports_sse_and_session_headers(self):
        client = GitHubMCP({"GITHUB_PERSONAL_ACCESS_TOKEN": "test-secret"})
        seen = []

        class EventResponse(io.BytesIO):
            def readline(self, limit=-1):
                if self.tell() == len(self.getvalue()):
                    raise AssertionError("Client waited for EOF after receiving its SSE result")
                return super().readline(limit)

        def response(request, timeout):
            body = json.loads(request.data)
            headers = {k.lower(): v for k, v in request.header_items()}
            seen.append((body, headers))
            self.assertEqual(request.full_url, GitHubMCP.URL)
            self.assertEqual(headers["x-mcp-readonly"], "true")
            if body["method"] == "initialize":
                out = {"protocolVersion": "2025-03-26"}
            elif body["method"] == "notifications/initialized":
                self.assertNotIn("id", body)
                result = io.BytesIO(b"")
                result.headers = {"Content-Type": "application/json"}
                return result
            else:
                self.assertEqual(body["method"], "tools/call")
                self.assertEqual(body["params"]["arguments"], {"owner": "team", "repo": "repo", "path": "README.md"})
                self.assertEqual(headers["mcp-session-id"], "test-session")
                out = {"content": [{"type": "resource", "resource": {"text": "# Project overview"}}]}
            message = {"jsonrpc": "2.0", "id": body["id"], "result": out}
            if body["method"] == "initialize":
                result = io.BytesIO(json.dumps(message).encode())
                content_type = "application/json"
            else:
                raw = ("event: message\ndata: " + json.dumps(message) + "\n\n").encode()
                result = EventResponse(raw)
                content_type = "text/event-stream"
            result.headers = {"Content-Type": content_type, "Mcp-Session-Id": "test-session"}
            return result

        with patch("backend.github.urllib.request.build_opener") as build:
            build.return_value.open.side_effect = response
            result = client.call("github_read_file", {"path": "README.md"}, "team/repo")
        self.assertEqual(len(seen), 3)
        self.assertEqual(result["text"], "# Project overview")
        self.assertEqual(result["repository"], "team/repo")

    def test_http_failure_does_not_echo_token_or_provider_body(self):
        client = GitHubMCP({"GITHUB_PERSONAL_ACCESS_TOKEN": "secret-value"})
        exc = urllib.error.HTTPError(client.URL, 401, "secret-value", {}, io.BytesIO(b"secret-value"))
        with patch("backend.github.urllib.request.build_opener") as build:
            build.return_value.open.side_effect = exc
            with self.assertRaises(Error) as caught:
                client.discover()
        self.assertNotIn("secret-value", str(caught.exception))
        self.assertEqual(caught.exception.code, "github_error")

    def test_only_allowlisted_reads_are_executable_and_output_is_bounded(self):
        client = GitHubMCP({"GITHUB_PERSONAL_ACCESS_TOKEN": "secret-value"})
        with patch.object(client, "_session", return_value={"content": [{"type": "text", "text": "secret-value" + "x" * 31000}]}) as rpc:
            result = client.call("github_list_issues", {"state": "OPEN"}, "team/repo")
            self.assertEqual(rpc.call_args.args[1]["arguments"]["perPage"], 10)
            self.assertTrue(result["truncated"])
            self.assertEqual(len(result["text"]), 30000)
            self.assertNotIn("secret-value", result["text"])
            for name, args in (("create_issue", {}), ("github_read_file", {"path": "../.env"}),
                               ("github_list_issues", {"state": "OPEN", "owner": "other"})):
                with self.assertRaises(Error):
                    client.call(name, args, "team/repo")
            self.assertEqual(rpc.call_count, 1)

    def test_missing_permissions_or_tool_error_fail_closed(self):
        client = GitHubMCP({"GITHUB_PERSONAL_ACCESS_TOKEN": "test"})
        with patch.object(client, "_session", return_value={"tools": [{"name": "get_file_contents"}]}):
            with self.assertRaises(Error):
                client.discover()
        with patch.object(client, "_session", return_value={"isError": True, "content": [{"text": "secret"}]}):
            with self.assertRaises(Error) as caught:
                client.call("github_read_file", {"path": "/"}, "team/repo")
            self.assertNotIn("secret", str(caught.exception))

    def test_missing_token_does_not_make_network_requests(self):
        with patch("backend.github.urllib.request.build_opener") as build:
            with self.assertRaises(Error) as caught:
                GitHubMCP({}).discover()
            self.assertEqual(caught.exception.code, "github_not_configured")
            build.assert_not_called()


class GitHubWorkflowTests(unittest.TestCase):
    setUp = test_workspace.WorkspaceTests.setUp
    tearDown = test_workspace.WorkspaceTests.tearDown
    call = test_workspace.WorkspaceTests.call
    hire = test_workspace.WorkspaceTests.hire

    def connect(self, repository="team/first", publish=True):
        self.app.github.token = "fake-github-token"
        with patch.object(self.app.github, "discover", return_value=list(GITHUB_TOOLS.values())), \
             patch.object(self.app.github, "call", return_value={"text": "README.md"}):
            result = self.call("POST", "integrations/github/connect", {"repository": repository, "department_id": "support"}, user="amol")
        if publish:
            return self.call("POST", "capabilities", {"source": "github", "name": "Repository Reader",
                "description": "Explain repository architecture and issues", "department_id": "support"},
                user="amol", key="publish:" + repository)
        return result

    def test_preparing_a_connection_adds_the_default_library_tool_once(self):
        self.assertNotIn("github-reading", [c["id"] for c in self.call("GET", "capabilities")])
        with patch.object(self.app.github, "discover") as discover:
            with self.assertRaises(Error):
                self.call("POST", "integrations/github/connect", {"repository": "team/repo", "department_id": "support"})
            discover.assert_not_called()
        self.app.github.token = "test"
        with patch.object(self.app.github, "discover", side_effect=Error("Unavailable")):
            with self.assertRaises(Error):
                self.call("POST", "integrations/github/connect", {"repository": "team/repo", "department_id": "support"}, user="amol")
        self.assertNotIn("github-reading", [c["id"] for c in self.call("GET", "capabilities")])
        self.connect(publish=False)
        default = [c for c in self.call("GET", "capabilities") if c["id"] == "github-reading"]
        self.assertEqual([c["name"] for c in default], ["Read GitHub repositories"])
        self.assertEqual(sorted(default[0]["tools"]), sorted(GITHUB_TOOLS))
        self.connect(publish=False, repository="team/other")  # preparing again never duplicates it
        self.assertEqual(sum(c["id"] == "github-reading" for c in self.call("GET", "capabilities")), 1)
        created = self.connect()
        self.assertEqual(created["name"], "Repository Reader")
        self.assertIn("Explain repository architecture and issues", created["skill"])
        self.connect("team/second")
        self.assertEqual(sum(c["id"] == "github-reading" for c in self.call("GET", "capabilities")), 1)
        self.assertTrue(self.call("GET", "integrations/github")["connected"])
        public = json.dumps(self.call("GET", "connections"))
        self.assertNotIn("fake-github-token", public)
        self.assertNotIn("credential_version", public)
        with self.app.db.transaction() as c:
            connections = [row for row in all_rows(c, "connections") if row["kind"] == "github_mcp"]
            self.assertEqual(len(connections), 1)

    def test_publishing_requires_a_prepared_connection_and_authorized_role_and_retries_are_safe(self):
        data = {"source": "github", "name": "Repo Reader", "description": "Explain the README", "department_id": "support"}
        with self.assertRaises(Error):
            self.call("POST", "capabilities", data, user="amol", key="publish")
        self.connect(publish=False)
        with self.assertRaises(Error) as caught:
            self.call("POST", "capabilities", data, user="shaun", key="not-manager")
        self.assertEqual(caught.exception.status, 403)
        first = self.call("POST", "capabilities", data, user="amol", key="publish")
        self.assertEqual(first, self.call("POST", "capabilities", data, user="amol", key="publish"))
        data["name"] = "Second tool"
        second = self.call("POST", "capabilities", data, user="amol", key="second")
        self.assertNotEqual(first["id"], second["id"])

    def test_manager_can_add_tools_but_cannot_prepare_connectors_or_bypass_department_access(self):
        self.connect(publish=False)
        with TestClient(create_app(self.app, start_worker=False), base_url="http://localhost") as client:
            headers = {"X-Dev-User": "tarun", "Idempotency-Key": "manager-create"}
            data = {"source": "github", "name": "Manager Repo Reader",
                    "description": "Read repository code and explain likely bugs", "department_id": "support"}
            result = client.post("/api/capabilities", json=data, headers=headers)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["creator_id"], "tarun")
            bundle = client.post("/api/capabilities", json={"name": "Brief kit", "description": "Create briefs", "tools": ["create_document"]}, headers=headers)
            self.assertEqual(bundle.status_code, 200, bundle.text)
            with patch.object(self.app.github, "discover") as discover:
                setup = client.post("/api/integrations/github/connect", json={"repository": "team/repo", "department_id": "support"}, headers=headers)
                self.assertEqual(setup.status_code, 403)
                discover.assert_not_called()
            with self.app.db.transaction(True) as c:
                manager = get(c, "users", "tarun")
                manager["department_ids"] = ["engineering"]
                put(c, "users", manager)
            denied = client.post("/api/capabilities", json=data,
                                 headers={"X-Dev-User": "tarun", "Idempotency-Key": "denied-department"})
            self.assertEqual(denied.status_code, 403)

    def test_github_reading_and_slides_run_together_for_user_selected_repositories(self):
        self.connect()
        self.app.config["MODEL_API_KEY"] = "fake-model-key"
        self.call("PATCH", "policy", {"approval_scope": "agent"}, user="amol")
        with patch.object(self.app.github, "discover", return_value=list(GITHUB_TOOLS.values())):
            _, agent = self.hire("Read GitHub and create slides", ["github-reading", "make-slideshow"], model_profile_id="meta")
        captured = []

        def read(name, args, repository):
            captured.append(repository)
            return {"source": "github_mcp", "repository": repository, "text": "# Project\nA tool for teams."}

        for repository in ("team/first", "different/second"):
            calls = [
                {"role": "model", "parts": [{"functionCall": {"name": "github_read_file", "args": {"path": "README.md"}, "id": "read"}}]},
                {"role": "model", "parts": [{"functionCall": {"name": "create_slideshow", "args": {"title": "Repository briefing", "outline": "# Project\n- A tool for teams\n# Next steps\n- Review the README"}, "id": "slides"}}]},
                {"role": "model", "parts": [{"text": "Saved the deck using the repository README."}]},
            ]
            with patch("backend.runtime.model.generate", side_effect=[(message, {}) for message in calls]) as generate, \
                 patch.object(self.app.github, "call", side_effect=read):
                run = self.call("POST", f"agents/{agent['id']}/runs", {"task": "Read the README and save slides", "repository": repository}, key=repository)
                for _ in range(12):
                    self.app.runtime.tick()
                final = self.call("GET", "runs/" + run["id"])
                self.assertEqual(final["status"], "completed", final)
                self.assertIn(repository, generate.call_args.args[2])
                self.assertIn("explain its purpose, code and next steps", generate.call_args.args[2])
                steps = self.call("GET", "runs/" + run["id"] + "/steps")
                self.assertEqual([s["label"] for s in steps if s["kind"] == "tool"], ["github_read_file", "create_slideshow"])
                self.assertTrue(any(s.get("data", {}).get("result", {}).get("kind") == "slideshow" for s in steps))
        self.assertEqual(captured, ["team/first", "different/second"])

    def test_live_model_repository_and_connection_permissions_are_required(self):
        self.connect()
        with patch.object(self.app.github, "discover", return_value=list(GITHUB_TOOLS.values())):
            with self.assertRaises(Error) as blocked:
                self.hire("GitHub", ["github-reading"])
            self.assertEqual(blocked.exception.code, "github_requires_live_model")
            _, agent = self.hire("GitHub", ["github-reading"], model_profile_id="meta")
        # An older agent that was already saved on the Demo model still can't run GitHub reads.
        test_workspace.use_model(self.app, agent["id"], "demo")
        with self.assertRaises(Error) as caught:
            self.call("POST", f"agents/{agent['id']}/runs", {"task": "Read README", "repository": "team/repo"}, key="demo")
        self.assertEqual(caught.exception.code, "github_requires_live_model")
        test_workspace.use_model(self.app, agent["id"], "meta")
        self.app.config["MODEL_API_KEY"] = "fake"
        with self.assertRaises(Error):
            self.call("POST", f"agents/{agent['id']}/runs", {"task": "Read README"}, key="missing")
        self.call("PATCH", "connections/github:hacktx", {"active": False}, user="amol")
        with self.assertRaises(Error) as caught:
            self.call("POST", f"agents/{agent['id']}/runs", {"task": "Read README", "repository": "team/repo"}, key="inactive")
        self.assertEqual(caught.exception.code, "connection_denied")

    def test_http_contract_and_admin_only_setup(self):
        with TestClient(create_app(self.app, start_worker=False), base_url="http://localhost") as client:
            self.assertEqual(client.get("/api/integrations/github").status_code, 200)
            self.assertEqual(client.post("/api/integrations/github/connect", json={"repository": "team/repo", "department_id": "support"}).status_code, 403)
            self.assertEqual(client.post("/api/integrations/github/connect", json={"repository": "team/repo", "department_id": "support", "token": "do-not-accept"}, headers={"X-Dev-User": "amol"}).status_code, 422)

    def test_department_grants_and_credential_rotation_are_enforced(self):
        self.connect()
        with patch.object(self.app.github, "discover", return_value=list(GITHUB_TOOLS.values())):
            with self.assertRaises(Error) as caught:
                self.hire("Read GitHub", ["github-reading"], department_id="engineering", model_profile_id="meta")
            self.assertEqual(caught.exception.code, "connection_denied")
            self.app.github.token = "rotated-token"
            self.assertFalse(self.call("GET", "integrations/github")["connected"])
            with self.assertRaises(Error) as caught:
                self.hire("Read GitHub", ["github-reading"], model_profile_id="meta")
            self.assertEqual(caught.exception.code, "connection_denied")

    def test_repository_changes_require_a_new_conversation(self):
        self.connect()
        self.app.config["MODEL_API_KEY"] = "fake"
        with patch.object(self.app.github, "discover", return_value=list(GITHUB_TOOLS.values())):
            _, agent = self.hire("Read GitHub", ["github-reading"], model_profile_id="meta")
        first = self.call("POST", f"agents/{agent['id']}/runs", {"task": "Read README", "repository": "team/first"}, key="first")
        with self.app.db.transaction(True) as c:
            run = get(c, "runs", first["id"])
            run.update(status="completed", contents=[])
            put(c, "runs", run)
        with self.assertRaises(Error) as caught:
            self.call("POST", f"agents/{agent['id']}/runs", {"task": "Continue", "repository": "team/second", "follow_up_of": first["id"]}, key="switch")
        self.assertEqual(caught.exception.code, "repository_changed")
