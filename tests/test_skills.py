import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.app import Application
from backend.registry import CAPS, playbooks_for, TOOLS
from backend.runtime import mcp, demo


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(Path(self.tmp.name) / "t.db", {"ALLOW_TEST_ORG": True})

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def call(self, method, path, data=None, user="pavan", key=None):
        return self.app.handle(method, "/api/" + path, data, user, key)

    def test_every_capability_has_a_playbook_and_it_is_served(self):
        served = {c["id"]: c for c in self.call("GET", "capabilities")}
        for cap in CAPS:
            self.assertTrue(cap["skill"].strip(), cap["id"])
            self.assertEqual(served[cap["id"]]["skill"], cap["skill"])
            for tool in cap["tools"]:
                self.assertIn(tool, TOOLS)

    def test_playbooks_follow_the_tools_an_agent_holds(self):
        names = [n for n, _ in playbooks_for(["create_slideshow", "schedule_meeting"])]
        self.assertEqual(names, ["Make a slideshow", "Schedule meetings"])
        self.assertEqual(playbooks_for([]), [])

    def test_live_prompt_includes_playbooks(self):
        seen = {}

        def fake(config, contents, instruction, declarations, provider="demo"):
            seen["instruction"] = instruction
            return {"role": "model", "parts": [{"text": "Done."}]}, {}

        conv = self.call("POST", "recruiter/conversations", {})
        p = self.call(
            "POST",
            f"recruiter/conversations/{conv['id']}/messages",
            {"message": "slides", "department_id": "support", "manager_id": "pavan",
             "capability_ids": ["make-slideshow", "schedule-meetings"], "model_profile_id": "meta"},
        )["proposal"]
        agent = self.call("POST", f"recruiter/proposals/{p['id']}/confirm", {"revision": p["revision"]}, key="h")
        self.app.config["MODEL_API_KEY"] = "test-key"
        with patch("backend.runtime.model.generate", fake):
            self.call("POST", f"agents/{agent['id']}/runs", {"task": "Plan a launch", "mode": "meta"}, key="r")
            for _ in range(6):
                self.app.runtime.tick()
        self.assertIn("[Make a slideshow]", seen["instruction"])
        self.assertIn("[Schedule meetings]", seen["instruction"])
        self.assertIn("takeaway", seen["instruction"])
        self.assertNotIn("[Draft emails]", seen["instruction"])
        self.assertIn("approved you only to build slide decks and prepare meeting invites", seen["instruction"])
        self.assertIn("do not substitute a plain-text answer", seen["instruction"])

    def test_outline_layouts_stats_notes_and_theme(self):
        slides = mcp.parse_outline("# Deck\n> A promise\n# Win\nstat: 38% | faster\nstat: 5 days | to onboard\nnotes: say this\n# Quote\n> Big idea\n# List\n- a\n- b")
        self.assertEqual([s["layout"] for s in slides], ["cover", "stats", "statement", "list"])
        self.assertEqual(slides[1]["stats"][0], {"value": "38%", "label": "faster"})
        self.assertEqual(slides[1]["notes"], "say this")

    def test_meeting_invite_has_times_attendees_and_ics_and_is_not_sent(self):
        r = mcp.meeting_result({"title": "Kickoff, Q4", "start": "2026-11-03T14:00", "duration_minutes": "45",
                                "attendees": "sam@acme.com, Lee, sam@acme.com", "agenda": "- Goal\n- Decide"})
        self.assertEqual(r["end"], "2026-11-03T14:45")
        self.assertEqual(r["attendees"], ["sam@acme.com", "Lee"])
        self.assertFalse(r["sent"])
        self.assertIn("DTSTART:20261103T140000", r["ics"])
        self.assertIn("SUMMARY:Kickoff\\, Q4", r["ics"])
        self.assertEqual(r["ics"].count("ATTENDEE"), 1)  # only real email addresses are invited

    def test_meeting_rejects_bad_time_and_duration(self):
        with self.assertRaises(Exception):
            mcp.meeting_result({"title": "x", "start": "next tuesday"})
        with self.assertRaises(Exception):
            mcp.meeting_result({"title": "x", "start": "2026-11-03T14:00", "duration_minutes": "9999"})

    def test_task_list_parses_owner_and_due(self):
        r = mcp.task_list_result({"title": "Launch", "tasks": "- Call Sam | Amy | Fri\n- [ ] Send deck"})
        self.assertEqual(r["tasks"][0], {"text": "Call Sam", "owner": "Amy", "due": "Fri"})
        self.assertEqual(r["task_count"], 2)

    def test_demo_reads_obvious_details_from_the_request(self):
        from datetime import datetime
        a = demo.meeting_args("Set up a 30-minute kickoff with sam@acme.com next Tuesday at 2pm", datetime(2026, 10, 25))
        self.assertEqual((a["title"], a["start"], a["attendees"]), ("Kickoff", "2026-10-27T14:00", "sam@acme.com"))

    def agent(self, caps, user="pavan", model="demo"):
        conv = self.call("POST", "recruiter/conversations", {}, user)
        p = self.call(
            "POST",
            f"recruiter/conversations/{conv['id']}/messages",
            {"message": "agent", "department_id": "support", "manager_id": "pavan",
             "capability_ids": caps, "model_profile_id": model},
            user,
        )["proposal"]
        return self.call("POST", f"recruiter/proposals/{p['id']}/confirm", {"revision": p["revision"]}, key="h:" + p["id"])

    def run_task(self, agent, task, key, **extra):
        run = self.call("POST", f"agents/{agent['id']}/runs", {"task": task, **extra}, key=key)
        for _ in range(10):
            self.app.runtime.tick()
        return self.call("GET", f"runs/{run['id']}")

    def test_approved_agent_runs_tasks_without_per_action_review(self):
        agent = self.agent(["schedule-meetings", "draft-email"])
        run = self.run_task(agent, "Schedule a 30-minute kickoff with sam@acme.com tomorrow at 3pm", "r1")
        self.assertEqual(run["status"], "completed")
        self.assertEqual(self.call("GET", "approvals?status=pending"), [])
        kinds = [s["data"]["result"]["kind"] for s in self.call("GET", f"runs/{run['id']}/steps") if s["kind"] == "tool"]
        self.assertEqual(kinds, ["meeting", "email"])
        self.assertEqual(self.call("GET", "policy")["approval_scope"], "agent")

    def test_admin_can_switch_back_to_per_action_review(self):
        self.call("PATCH", "policy", {"approval_scope": "action"}, user="amol")
        agent = self.agent(["schedule-meetings", "draft-email"])
        run = self.call("POST", f"agents/{agent['id']}/runs", {"task": "Schedule a kickoff tomorrow at 3pm"}, key="r2")
        for _ in range(4):
            self.app.runtime.tick()
        pending = self.call("GET", "approvals?status=pending")
        self.assertEqual([a["action"]["tool_id"] for a in pending], ["schedule_meeting"])
        self.assertIn("meeting invite", pending[0]["action"]["summary"].lower())
        with self.assertRaises(Exception):
            self.call("PATCH", "policy", {"approval_scope": "action"}, user="pavan")

    def test_hiring_still_needs_manager_approval(self):
        conv = self.call("POST", "recruiter/conversations", {}, "shaun")
        p = self.call(
            "POST",
            f"recruiter/conversations/{conv['id']}/messages",
            {"message": "slides", "department_id": "support", "manager_id": "pavan", "capability_ids": ["make-slideshow"]},
            "shaun",
        )["proposal"]
        with self.assertRaises(Exception):
            self.call("POST", f"recruiter/proposals/{p['id']}/confirm", {"revision": p["revision"]}, user="shaun", key="s1")
        agent = self.call("POST", f"recruiter/proposals/{p['id']}/confirm", {"revision": p["revision"]}, key="s2")
        self.assertEqual((agent["creator_id"], agent["approved_by"]), ("shaun", "pavan"))
        return agent

    def test_model_is_fixed_when_the_agent_is_created(self):
        agent = self.agent(["write-document"])
        run = self.run_task(agent, "Write a brief about onboarding", "m1")
        self.assertEqual(run["mode"], "demo")
        self.app.config["MODEL_API_KEY"] = "test-key"
        with self.assertRaises(Exception) as caught:
            self.call("POST", f"agents/{agent['id']}/runs", {"task": "Again", "mode": "meta"}, key="m2")
        self.assertEqual(getattr(caught.exception, "code", None) or caught.exception.args[-1], "model_fixed")

    def test_agent_tools_are_limited_to_its_skills(self):
        agent = self.agent(["make-slideshow"])
        run = self.run_task(agent, "Make a 3-slide deck about onboarding and email it to sam@acme.com", "t1")
        tools = [s["label"] for s in self.call("GET", f"runs/{run['id']}/steps") if s["kind"] == "tool"]
        self.assertEqual(tools, ["create_slideshow"])

    def test_creator_manager_or_admin_can_remove_an_agent(self):
        agent = self.test_hiring_still_needs_manager_approval()
        with self.assertRaises(Exception):
            self.call("DELETE", f"agents/{agent['id']}", user="member")
        removed = self.call("DELETE", f"agents/{agent['id']}", user="shaun")
        self.assertEqual(removed["status"], "archived")
        self.assertNotIn(agent["id"], [a["id"] for a in self.call("GET", "agents")])

    def test_gemini_function_schemas_drop_fields_gemini_rejects(self):
        from backend.runtime.model import gemini_schema
        for tool in TOOLS.values():
            cleaned = gemini_schema(tool["inputSchema"])
            text = repr(cleaned)
            for banned in ("additionalProperties", "maxLength", "minLength"):
                self.assertNotIn(banned, text, tool["name"])
            self.assertEqual(cleaned["required"], tool["inputSchema"]["required"])
            self.assertEqual(set(cleaned["properties"]), set(tool["inputSchema"]["properties"]))
        self.assertIn("additionalProperties", repr(TOOLS["create_slideshow"]["inputSchema"]))

    def test_provider_error_includes_a_short_provider_message(self):
        import io, json, urllib.error
        from backend.runtime.model import provider_error
        body = json.dumps({"error": {"message": "Invalid JSON payload.\n Unknown name \"x\""}}).encode()
        exc = urllib.error.HTTPError("https://x", 400, "Bad", {}, io.BytesIO(body))
        err = provider_error("Gemini", exc)
        self.assertIn("HTTP 400: Invalid JSON payload. Unknown name", str(err))
        self.assertNotIn("\n", str(err))


if __name__ == "__main__":
    unittest.main()
