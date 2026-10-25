import unittest
from uuid import uuid4
from tests import test_workspace
from backend.contracts import Error


class WorkQueueTests(unittest.TestCase):
    setUp = test_workspace.WorkspaceTests.setUp
    tearDown = test_workspace.WorkspaceTests.tearDown

    def call(self, method, path, data=None, user="pavan", key=None):
        if method == "POST" and path.startswith("work-queue"):
            key = key or str(uuid4())
        return test_workspace.WorkspaceTests.call(self, method, path, data, user, key)

    hire = test_workspace.WorkspaceTests.hire
    drain = test_workspace.WorkspaceTests.drain

    def test_queue_assignment_approval_and_outcome(self):
        items = self.call("POST", "work-queue/sample-batch", {})
        self.assertEqual(len(items), 3)
        self.assertEqual(len(self.call("POST", "work-queue/sample-batch", {})), 3)
        _, agent = self.hire(
            "Support queue agent", caps=["ticket-search", "help-docs", "reply-drafts"]
        )
        item = items[1]
        path = "work-queue/" + item["id"]
        assigned = self.call(
            "POST", path + "/assign", {"agent_id": agent["id"], "mode": "demo"}
        )
        with self.assertRaises(Error):
            self.call(
                "POST", path + "/assign", {"agent_id": agent["id"], "mode": "demo"}
            )
        self.drain(approve=False)
        for i in range(3):
            approvals = [
                a for a in self.call("GET", "approvals") if a["status"] == "pending"
            ]
            self.assertEqual(len(approvals), 1)
            self.call(
                "POST",
                "approvals/" + approvals[0]["id"] + "/decision",
                {"decision": "approve", "comment": "Checked policy"},
                key="approve" + str(i),
            )
            self.drain(approve=False)
        row = next(w for w in self.call("GET", "work-queue") if w["id"] == item["id"])
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["draft"]["ticket_id"], "T-102")
        self.assertIn("30 minutes", row["draft"]["body"])
        self.assertFalse(row["draft"]["sent"])
        self.call(
            "POST",
            path + "/review",
            {"success": True, "comment": "Accurate reset policy"},
        )
        row = next(w for w in self.call("GET", "work-queue") if w["id"] == item["id"])
        self.assertEqual(row["status"], "accepted")

    def test_queue_requires_support_capabilities_and_manager(self):
        item = self.call("POST", "work-queue/sample-batch", {})[0]
        _, agent = self.hire("Research", caps=["research-web"])
        with self.assertRaises(Error):
            self.call(
                "POST",
                "work-queue/" + item["id"] + "/assign",
                {"agent_id": agent["id"], "mode": "demo"},
            )
        with self.assertRaises(Error):
            self.call(
                "POST",
                "work-queue/" + item["id"] + "/assign",
                {"agent_id": agent["id"], "mode": "demo"},
                user="amol",
            )

    def test_launch_job_produces_three_deliverables(self):
        item = self.call("POST", "work-queue/sample-batch", {"workflow": "launch"})[0]
        self.assertEqual(item["workflow"], "launch")
        _, agent = self.hire(
            "Launch strategist",
            caps=["analyze-data", "write-document", "make-slideshow"],
        )
        self.call(
            "POST",
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "demo"},
        )
        self.drain()
        row = self.call("GET", "work-queue")[0]
        self.assertEqual(row["status"], "completed")
        self.assertTrue(row["deliverables_ready"])
        self.assertEqual(
            {x["result"]["kind"] for x in row["artifacts"]},
            {"analysis", "document", "slideshow"},
        )
        analysis = next(
            x["result"] for x in row["artifacts"] if x["tool"] == "analyze_data"
        )
        self.assertEqual(analysis["rows"], 3)
        self.call(
            "POST",
            "work-queue/" + item["id"] + "/review",
            {"success": False, "comment": "Tighten the recommendation"},
        )
        self.assertEqual(
            self.call("GET", "work-queue")[0]["status"], "needs_correction"
        )
        revised = self.call(
            "POST",
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "demo"},
        )
        self.assertEqual(len(revised["previous_run_ids"]), 1)
        self.assertNotEqual(revised["run_id"], revised["previous_run_ids"][0])

    def test_custom_work_persists_and_accept_requires_deliverables(self):
        item = self.call(
            "POST",
            "work-queue",
            {
                "workflow": "brief",
                "title": "Budget decision",
                "task": "Write a brief. No spending authorized.",
            },
        )
        self.assertFalse(item["sample_data"])
        _, agent = self.hire("Strategy", caps=["write-document"])
        assigned = self.call(
            "POST",
            "work-queue/" + item["id"] + "/assign",
            {"agent_id": agent["id"], "mode": "demo"},
        )
        with self.assertRaises(Error):
            self.call(
                "POST",
                "work-queue/" + item["id"] + "/review",
                {"success": True, "comment": "Early"},
            )
        self.drain()
        self.call(
            "POST",
            "work-queue/" + item["id"] + "/review",
            {"success": True, "comment": "Reviewed the brief"},
        )
        self.assertEqual(self.call("GET", "work-queue")[0]["status"], "accepted")
