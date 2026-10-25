import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend.app import Application
from backend.contracts import Error
from backend.db import Database, all_rows, get, put
from backend.registry import seed
from backend.runtime import mcp as mcp_module


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.db"
        self.app = Application(self.path, {"ALLOW_TEST_ORG": True})

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def call(self, method, path, data=None, user="pavan", key=None):
        return self.app.handle(method, "/api/" + path, data, user, key)

    def hire(self, message, caps=None, **extra):
        conv = self.call("POST", "recruiter/conversations", {})
        data = {
            "message": message,
            "department_id": "support",
            "manager_id": "pavan",
            **extra,
        }
        if caps is not None:
            data["capability_ids"] = caps
        p = self.call("POST", f"recruiter/conversations/{conv['id']}/messages", data)[
            "proposal"
        ]
        agent = self.call(
            "POST",
            f"recruiter/proposals/{p['id']}/confirm",
            {"revision": p["revision"]},
            key="hire:" + p["id"],
        )
        return p, agent

    def start(self, agent, task, **extra):
        return self.call(
            "POST",
            f"agents/{agent['id']}/runs",
            {"task": task, **extra},
            key="run:" + str(len(self.call("GET", "runs"))),
        )

    def drain(self, approve=True, n=25):
        for _ in range(n):
            self.app.runtime.tick()
            if approve:
                for a in self.call("GET", "approvals?status=pending"):
                    self.call(
                        "POST",
                        f"approvals/{a['id']}/decision",
                        {"decision": "approve", "comment": ""},
                        key="d:" + a["id"],
                    )

    def tool_results(self, run):
        return [
            s["data"]["result"]
            for s in self.call("GET", f"runs/{run['id']}/steps")
            if s["kind"] == "tool"
        ]

    def test_catalog_has_general_capabilities_with_working_connections(self):
        caps = {c["id"]: c for c in self.call("GET", "capabilities")}
        for cap in ["make-slideshow", "write-document", "analyze-data", "research-web"]:
            self.assertEqual(caps[cap]["connection_id"], "workspace-local")
            v = self.call(
                "POST",
                f"capabilities/{cap}/validate",
                {"connection_id": "workspace-local", "department_id": "engineering"},
            )
            self.assertTrue(v["passed"], cap)
        self.assertEqual(
            self.call(
                "POST",
                "capabilities/analyze-data/validate",
                {"connection_id": "workspace-local", "department_id": "support"},
            )["evidence"]["rows"],
            3,
        )

    def test_old_databases_gain_new_capabilities_without_losing_old_ones(self):
        db = Database(Path(self.tmp.name) / "old.db")
        seed(db)
        with db.transaction(True) as c:
            for cap in [
                "make-slideshow",
                "write-document",
                "analyze-data",
                "research-web",
            ]:
                c.execute("DELETE FROM capabilities WHERE id=?", (cap,))
            c.execute("DELETE FROM connections WHERE id='workspace-local'")
            ticket = get(c, "capabilities", "ticket-search")
            for key in ["group", "icon", "example", "connection_id"]:
                ticket.pop(key, None)
            put(c, "capabilities", ticket)
        seed(db)
        with db.transaction() as c:
            ids = {x["id"] for x in all_rows(c, "capabilities")}
            self.assertEqual(len(ids), 7)
            self.assertEqual(
                get(c, "capabilities", "ticket-search")["group"], "Support sandbox"
            )
            self.assertEqual(get(c, "connections", "workspace-local")["active"], True)

    def test_recruiter_infers_workspace_capabilities_and_names(self):
        p, agent = self.hire("Make a slideshow about our launch")
        self.assertEqual(p["spec"]["capability_ids"], ["make-slideshow"])
        self.assertEqual(agent["name"], "Slide Builder")
        self.assertEqual(agent["bindings"][0]["connection_id"], "workspace-local")
        self.assertNotIn(
            "support", agent["instructions"].lower().split("capabilities")[0]
        )
        p, agent = self.hire("Hire an agent that triages tickets and drafts replies")
        self.assertIn("ticket-search", p["spec"]["capability_ids"])
        self.assertEqual(agent["name"], "Ticket Triage")

    def test_mixed_capabilities_use_each_capabilitys_own_connection(self):
        _, agent = self.hire("Support deck", caps=["make-slideshow", "ticket-search"])
        used = {b["capability_id"]: b["connection_id"] for b in agent["bindings"]}
        self.assertEqual(
            used,
            {"make-slideshow": "workspace-local", "ticket-search": "support-local"},
        )

    def test_demo_slideshow_intern_waits_then_saves_deck(self):
        _, agent = self.hire("Make slides", caps=["make-slideshow"])
        run = self.start(agent, "Make a 4-slide deck about customer onboarding")
        self.drain(approve=False)
        self.assertEqual(
            self.call("GET", f"runs/{run['id']}")["status"], "awaiting_approval"
        )
        self.assertEqual(self.tool_results(run), [])
        approval = self.call("GET", "approvals?status=pending")[0]
        self.assertEqual(approval["policy"]["risk"], "local_write")
        self.assertIn("outline", approval["action"]["arguments"])
        self.drain()
        done = self.call("GET", f"runs/{run['id']}")
        self.assertEqual(done["status"], "completed")
        deck = self.tool_results(run)[0]
        self.assertEqual(deck["kind"], "slideshow")
        self.assertEqual(deck["slide_count"], len(deck["slides"]))
        self.assertGreaterEqual(deck["slide_count"], 4)
        self.assertFalse(deck["published"])
        self.assertEqual(deck["title"], "Customer onboarding")

    def test_runs_alone_mode_skips_approval_for_reads_and_local_saves_but_not_drafts(
        self,
    ):
        _, agent = self.hire(
            "Everything", caps=["make-slideshow", "analyze-data", "reply-drafts"]
        )
        self.call(
            "POST",
            f"agents/{agent['id']}/level",
            {"level": "associate", "reason": "Reviewed"},
        )
        run = self.start(
            agent,
            "Analyze this data: a,b\nx,1\ny,2\nthen make a deck and draft a reply",
        )
        self.drain(approve=False)
        pending = self.call("GET", "approvals?status=pending")
        self.assertEqual([a["action"]["tool_id"] for a in pending], ["create_draft"])
        kinds = [r.get("kind") for r in self.tool_results(run)]
        self.assertEqual(kinds, ["analysis", "slideshow"])

    def test_analyze_data_computes_real_numbers_and_chart(self):
        _, agent = self.hire("Data", caps=["analyze-data"])
        run = self.start(
            agent, "Analyze this data:\nmonth,revenue\nJan,100\nFeb,300\nMar,200"
        )
        self.drain()
        result = self.tool_results(run)[0]
        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["numeric"]["revenue"]["sum"], 600)
        self.assertEqual(result["numeric"]["revenue"]["max"], 300)
        self.assertEqual(result["chart"]["points"][1], {"label": "Feb", "value": 300.0})
        self.assertIn("Highest revenue: Feb (300)", result["highlights"])

    def test_document_accepts_essay_and_rejects_oversized_content(self):
        body = "A historical essay. " * 400
        result = mcp_module.perform(self.app.db, "create_document", {"title": "Essay", "body": body}, "essay")
        self.assertEqual(result["body"], body.strip())
        from backend.registry import TOOLS
        self.assertEqual(TOOLS["create_document"]["inputSchema"]["properties"]["body"]["maxLength"], 40000)
        with self.assertRaises(Error):
            mcp_module.perform(self.app.db, "create_document", {"title": "Essay", "body": "x" * 40001}, "oversized")

    def test_document_tool_saves_once_per_execution_id(self):
        args = {"title": "Plan", "body": "# Plan\n- one"}
        first = mcp_module.perform(self.app.db, "create_document", args, "exec-1")
        again = mcp_module.perform(self.app.db, "create_document", args, "exec-1")
        self.assertEqual(first["artifact_id"], again["artifact_id"])
        with self.assertRaises(Error):
            mcp_module.perform(
                self.app.db, "create_document", {**args, "title": "Other"}, "exec-1"
            )

    def test_research_needs_a_link_in_demo_mode_and_blocks_private_addresses(self):
        _, agent = self.hire("Research", caps=["research-web"])
        run = self.start(agent, "Summarize the news")
        self.drain()
        failed = self.call("GET", f"runs/{run['id']}")
        self.assertEqual(failed["status"], "failed")
        self.assertIn("Add a web address", failed["error"])
        for url in [
            "http://127.0.0.1:8000/api/me",
            "http://localhost/",
            "file:///etc/passwd",
            "http://user:pw@example.com/",
        ]:
            with self.assertRaises(Error):
                mcp_module.perform(self.app.db, "read_url", {"url": url}, "x")

    def test_read_url_extracts_text_and_follows_only_public_redirects(self):
        page = (
            b"<html><head><title>Hello &amp; welcome</title><style>p{}</style></head>"
            b"<body><script>evil()</script><p>First paragraph.</p><p>Second.</p></body></html>"
        )

        class Response:
            def __init__(self, body):
                self.body = body
                self.headers = type(
                    "H",
                    (),
                    {
                        "get_content_type": lambda s: "text/html",
                        "get_content_charset": lambda s: "utf-8",
                    },
                )()

            def read(self, n):
                return self.body[:n]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class Opener:
            def open(self, request, timeout=0):
                return Response(page)

        with (
            patch.object(mcp_module, "public_address", return_value=["93.184.216.34"]),
            patch.object(
                mcp_module.urllib.request, "build_opener", return_value=Opener()
            ),
        ):
            out = mcp_module.perform(
                self.app.db, "read_url", {"url": "https://example.com/a"}, "x"
            )
        self.assertEqual(out["title"], "Hello & welcome")
        self.assertEqual(out["text"], "First paragraph. Second.")
        self.assertNotIn("evil", out["text"])

    def test_article_extraction_omits_page_navigation(self):
        parser = mcp_module._PageText()
        parser.feed(
            "<html><body><header>Menu</header><nav>Jump to content</nav>"
            "<main><nav>Contents</nav><article><p>Kobe won five championships.</p>"
            "<script>noise()</script></article></main><footer>Donate</footer></body></html>"
        )
        self.assertEqual(parser.text(), "Kobe won five championships.")

    def test_missing_page_returns_recoverable_tool_result(self):
        failure = mcp_module.urllib.error.HTTPError(
            "https://example.com/missing", 404, "Missing", {}, None
        )
        with (
            patch.object(mcp_module, "public_address", return_value=["93.184.216.34"]),
            patch.object(
                mcp_module.urllib.request.OpenerDirector, "open", side_effect=failure
            ),
        ):
            result = mcp_module.read_page("https://example.com/missing")
        self.assertEqual(result["kind"], "page_error")
        self.assertEqual(result["http_status"], 404)
        self.assertNotIn("text", result)

    def test_tool_arguments_reject_unknown_or_non_text_fields(self):
        _, agent = self.hire("Data", caps=["analyze-data"])
        self.call(
            "POST",
            f"agents/{agent['id']}/level",
            {"level": "associate", "reason": "ok"},
        )
        run = self.start(agent, "Analyze this data:\na,b\n1,2")
        with self.app.db.transaction(True) as c:
            row = get(c, "runs", run["id"])
            row["contents"] = [{"role": "user", "parts": [{"text": "x"}]}]
            row["queue"] = [
                {"name": "analyze_data", "args": {"table": "a\n1", "extra": "no"}}
            ]
            row["mode"] = "demo"
            put(c, "runs", row)
        self.drain()
        self.assertEqual(self.call("GET", f"runs/{run['id']}")["status"], "failed")

    def test_follow_up_continues_live_conversation_only(self):
        _, agent = self.hire("Docs", caps=["write-document"])
        first = self.start(agent, "Write a brief about onboarding")
        self.drain()
        with self.assertRaises(Error):
            self.start(agent, "Make it shorter", follow_up_of=first["id"])
        with self.app.db.transaction(True) as c:
            row = get(c, "runs", first["id"])
            row.update(
                mode="meta",
                contents=[
                    {"role": "user", "parts": [{"text": "hi"}]},
                    {"role": "model", "parts": [{"text": "Done."}]},
                ],
            )
            put(c, "runs", row)
        self.app.config["MODEL_API_KEY"] = "test-key"
        follow = self.call(
            "POST",
            f"agents/{agent['id']}/runs",
            {"task": "Make it shorter", "mode": "meta", "follow_up_of": first["id"]},
            key="follow-1",
        )
        self.assertEqual(follow["thread_id"], first["thread_id"])
        with self.app.db.transaction() as c:
            stored = get(c, "runs", follow["id"])
        self.assertEqual(len(stored["contents"]), 3)
        self.assertEqual(stored["contents"][-1]["parts"][0]["text"], "Make it shorter")

    def test_leaderboard_reports_result_ratings_with_a_minimum(self):
        _, agent = self.hire("Docs", caps=["write-document"])
        for n in range(3):
            run = self.start(agent, f"Write a brief about topic {n}")
            self.drain()
            row = [
                r
                for r in self.call("GET", "leaderboard")["agents"]
                if r["agent_id"] == agent["id"]
            ][0]
            self.assertIsNone(row["task_success_rate"])
            self.call(
                "POST",
                f"runs/{run['id']}/outcome",
                {"success": n != 2, "comment": "Rated"},
                key=f"o{n}",
            )
        board = self.call("GET", "leaderboard")
        row = [r for r in board["agents"] if r["agent_id"] == agent["id"]][0]
        self.assertEqual(board["minimum_rated_tasks"], 3)
        self.assertTrue(row["result_eligible"])
        self.assertAlmostEqual(row["task_success_rate"], 2 / 3)
        self.assertEqual(row["rated_tasks"], 3)
        self.assertEqual(
            board["capability_usage"][0]["capability_id"], "write-document"
        )
        self.assertEqual(board["capability_usage"][0]["agents"], 1)
        self.assertEqual(
            board["creator_usage"][0], {"creator_id": "shaun", "agents": 1}
        )
        runs = {r["id"]: r for r in self.call("GET", "runs")}
        self.assertTrue(all(r["outcome"] for r in runs.values()))
        self.assertTrue(
            self.call("GET", f"runs/{list(runs)[0]}")["outcome"]["success"]
            in (True, False)
        )


if __name__ == "__main__":
    unittest.main()
