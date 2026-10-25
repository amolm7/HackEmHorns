"""Regression tests for calendar, provider, and cached-response boundaries."""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from backend.contracts import Error, manage
from backend.db import get, put
from backend.runtime import mcp, model
from backend.registry import TOOLS
from tests import test_workspace


class SecurityReviewTests(unittest.TestCase):
    setUp = test_workspace.WorkspaceTests.setUp
    tearDown = test_workspace.WorkspaceTests.tearDown
    call = test_workspace.WorkspaceTests.call
    hire = test_workspace.WorkspaceTests.hire

    def test_calendar_cannot_inject_properties_with_carriage_returns(self):
        result = mcp.meeting_result({
            "title": "Review\rATTACH:https://evil.example/payload",
            "location": "Office\r\nBEGIN:VEVENT",
            "start": "2026-11-03T14:00",
            "attendees": "sam@example.com\rATTACH:https://evil.example, bad@example.com:payload",
        })
        lines = result["ics"].split("\r\n")
        self.assertEqual(lines.count("BEGIN:VEVENT"), 1)
        self.assertFalse(any(line.startswith("ATTACH:") for line in lines))
        self.assertTrue(all("\r" not in line and "\n" not in line for line in lines))
        self.assertEqual([line for line in lines if line.startswith("ATTENDEE")],
                         ["ATTENDEE;RSVP=TRUE:mailto:sam@example.com"])

    def test_calendar_preserves_explicit_timezone(self):
        result = mcp.meeting_result({"title": "Review", "start": "2026-11-03T14:00-06:00"})
        self.assertIn("DTSTART:20261103T200000Z\r\n", result["ics"])
        self.assertIn("DTEND:20261103T203000Z\r\n", result["ics"])
        self.assertEqual(result["start"], "2026-11-03T14:00-06:00")

    def test_calendar_requires_time(self):
        with self.assertRaises(Error):
            mcp.meeting_result({"title": "Review", "start": "2026-11-03"})

    def test_both_provider_adapters_redact_echoed_credentials(self):
        for provider, invoke in (("gemini", model.gemini_generate), ("meta", model.meta_generate)):
            with self.subTest(provider=provider):
                secret = "private-test-credential"
                body = json.dumps({"error": {"message": "Invalid key " + secret + " Bearer another-token"}}).encode()
                exc = urllib.error.HTTPError("https://provider.example", 400, "Bad", {}, io.BytesIO(body))
                with patch("backend.runtime.model.urllib.request.urlopen", side_effect=exc):
                    with self.assertRaises(Error) as caught:
                        invoke({"GEMINI_API_KEY": secret, "MODEL_API_KEY": secret}, [], "Test")
                self.assertNotIn(secret, str(caught.exception))
                self.assertNotIn("another-token", str(caught.exception))
                self.assertIn("[redacted]", str(caught.exception))

    def test_cached_run_rejects_department_transfer(self):
        _, agent = self.hire("Search tickets", ["ticket-search"])
        path = f"agents/{agent['id']}/runs"
        payload = {"task": "Find ticket T-101"}
        first = self.call("POST", path, payload, user="shaun", key="same-run")
        self.assertEqual(first, self.call("POST", path, payload, user="shaun", key="same-run"))
        with self.app.db.transaction(True) as c:
            current = get(c, "agents", agent["id"])
            current["department_id"] = "engineering"
            put(c, "agents", current)
        with self.assertRaises(Error) as caught:
            self.call("POST", path, payload, user="shaun", key="same-run")
        self.assertEqual(caught.exception.code, "replay_access_changed")

    def test_cached_confirmation_rejects_manager_reassignment(self):
        proposal, agent = self.hire("Search tickets", ["ticket-search"])
        with self.app.db.transaction(True) as c:
            current = get(c, "agents", agent["id"])
            current["manager_id"] = "someone-else"
            put(c, "agents", current)
        with self.assertRaises(Error) as caught:
            self.call("POST", f"recruiter/proposals/{proposal['id']}/confirm",
                      {"revision": proposal["revision"]}, key="hire:" + proposal["id"])
        self.assertEqual(caught.exception.code, "replay_access_changed")

    def test_manager_needs_current_department_access(self):
        manager = {"id": "manager", "org_id": "org", "roles": ["manager"], "department_ids": ["support"]}
        agent = {"org_id": "org", "manager_id": "manager", "department_id": "engineering"}
        with self.assertRaises(Error) as caught:
            manage(manager, agent)
        self.assertEqual(caught.exception.status, 403)

    def test_confirmed_proposal_with_new_key_rechecks_current_manager(self):
        proposal, agent = self.hire("Search tickets", ["ticket-search"])
        with self.app.db.transaction(True) as c:
            current = get(c, "agents", agent["id"])
            current["manager_id"] = "tarun"
            put(c, "agents", current)
        with self.assertRaises(Error) as caught:
            self.call("POST", f"recruiter/proposals/{proposal['id']}/confirm",
                      {"revision": proposal["revision"]}, key="fresh-key")
        self.assertEqual(caught.exception.status, 403)

    def test_approval_reads_respect_revoked_department_access(self):
        _, agent = self.hire("Search tickets", ["ticket-search"])
        self.call("POST", f"agents/{agent['id']}/runs", {"task": "Find T-101"}, key="run")
        self.app.runtime.tick()
        approval = self.call("GET", "approvals")[0]
        with self.app.db.transaction(True) as c:
            actor = get(c, "users", "pavan")
            actor["department_ids"] = []
            put(c, "users", actor)
        self.assertEqual(self.call("GET", "approvals"), [])
        with self.assertRaises(Error):
            self.call("POST", "approvals/" + approval["id"] + "/decision",
                      {"decision": "approve", "comment": "Reviewed"}, key="denied-decision")
        self.assertEqual(self.call("GET", "recruiter/proposals"), [])

    def test_capability_registration_matches_ten_tool_http_contract(self):
        names = list(TOOLS)
        result = self.call("POST", "capabilities", {
            "name": "Workspace kit", "description": "Approved bundled tools", "tools": names,
        }, user="amol")
        self.assertEqual(result["tools"], names)

    def test_invalid_url_port_returns_controlled_error_before_dns(self):
        with patch("backend.runtime.mcp.socket.getaddrinfo") as resolve:
            for url in ("https://example.com:invalid", "https://example.com:99999", "http://[broken"):
                with self.subTest(url=url), self.assertRaises(Error):
                    mcp.public_address(url)
            resolve.assert_not_called()
