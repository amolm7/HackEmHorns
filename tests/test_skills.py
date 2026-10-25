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
             "capability_ids": ["make-slideshow", "schedule-meetings"]},
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

    def test_demo_run_saves_meeting_and_waits_for_email_approval(self):
        conv = self.call("POST", "recruiter/conversations", {})
        p = self.call(
            "POST",
            f"recruiter/conversations/{conv['id']}/messages",
            {"message": "meetings and email", "department_id": "support", "manager_id": "pavan",
             "capability_ids": ["schedule-meetings", "draft-email"], "mode": "demo"},
        )["proposal"]
        agent = self.call("POST", f"recruiter/proposals/{p['id']}/confirm", {"revision": p["revision"]}, key="h2")
        run = self.call("POST", f"agents/{agent['id']}/runs",
                        {"task": "Schedule a 30-minute kickoff with sam@acme.com tomorrow at 3pm", "mode": "demo"}, key="r2")
        for _ in range(4):
            self.app.runtime.tick()
        first = self.call("GET", "approvals?status=pending")
        self.assertEqual([a["action"]["tool_id"] for a in first], ["schedule_meeting"])
        self.assertIn("meeting invite", first[0]["action"]["summary"].lower())
        self.call("POST", f"approvals/{first[0]['id']}/decision", {"decision": "approve", "comment": ""}, key="d1")
        for _ in range(6):
            self.app.runtime.tick()
        second = self.call("GET", "approvals?status=pending")
        self.assertEqual([a["action"]["tool_id"] for a in second], ["draft_email"])
        meeting = [s["data"]["result"] for s in self.call("GET", f"runs/{run['id']}/steps") if s["kind"] == "tool"][0]
        self.assertEqual(meeting["kind"], "meeting")
        self.assertFalse(meeting["sent"])
        self.assertEqual(meeting["attendees"], ["sam@acme.com"])


if __name__ == "__main__":
    unittest.main()
