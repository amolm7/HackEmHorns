"""A failed task ends only itself; budgets leave room to save; claims need evidence."""
import json
import threading
import time
import unittest
from unittest.mock import patch

from backend.contracts import Error
from backend.db import get, put, all_rows
from backend.runtime import deliverables, history, model
from backend.github import GitHubMCP
from tests import test_workspace
from tests.recruit import propose


def fn(name, args, ident=None):
    call = {"name": name, "args": args}
    if ident:
        call["id"] = ident
    return {"role": "model", "parts": [{"functionCall": call}]}


def text(value):
    return {"role": "model", "parts": [{"text": value}]}


CSV = "channel,signups\nAmbassadors,180\nSocial,240"
DECK = {"title": "Signups", "outline": "# Recommendation\n- Invest in social\n# Risks\n- Small sample\n# Next steps\n- Re-run next month"}


class ReliabilityTests(unittest.TestCase):
    setUp = test_workspace.WorkspaceTests.setUp
    tearDown = test_workspace.WorkspaceTests.tearDown
    hire = test_workspace.WorkspaceTests.hire
    call = test_workspace.WorkspaceTests.call

    def agent(self, caps, model_id="meta"):
        self.app.config["MODEL_API_KEY"] = "fake"
        # Agent-level approval: a manager approves the agent once, tasks then run on their own.
        self.call("PATCH", "policy", {"approval_scope": "agent"}, user="amol")
        _, agent = self.hire("Helper", caps, model_profile_id=model_id)
        return agent

    def run_task(self, agent, task, replies, key, **extra):
        with patch("backend.runtime.model.generate", side_effect=[(r, {}) for r in replies]):
            run = self.call("POST", f"agents/{agent['id']}/runs", {"task": task, **extra}, key=key)
            for _ in range(20):
                self.app.runtime.tick()
        return self.call("GET", "runs/" + run["id"])

    # --- a failed task must not kill the agent or its conversation -------------------
    def test_failed_and_cancelled_tasks_do_not_block_the_conversation(self):
        agent = self.agent(["write-document"])
        conv = self.call("POST", f"agents/{agent['id']}/conversations", {}, key="c")
        boom = Error("Provider rejected the request", 502, "provider_error", {"retryable": False})
        with patch("backend.runtime.model.generate", side_effect=boom):
            first = self.call("POST", f"agents/{agent['id']}/runs", {"task": "Say hi", "conversation_id": conv["id"]}, key="r1")
            for _ in range(3):
                self.app.runtime.tick()
        self.assertEqual(self.call("GET", "runs/" + first["id"])["status"], "failed")
        second = self.run_task(agent, "Say hi again", [text("Hello again.")], "r2", conversation_id=conv["id"])
        self.assertEqual(second["status"], "completed", second)
        self.assertEqual(second["conversation_id"], conv["id"])
        # cancelled tasks behave the same
        with patch("backend.runtime.model.generate", side_effect=[(text("never"), {})]):
            third = self.call("POST", f"agents/{agent['id']}/runs", {"task": "Wait", "conversation_id": conv["id"]}, key="r3")
            self.call("POST", f"runs/{third['id']}/cancel", {})
        fourth = self.run_task(agent, "Say hi once more", [text("Hi.")], "r4", conversation_id=conv["id"])
        self.assertEqual(fourth["status"], "completed", fourth)

    def test_an_unfinished_task_still_blocks_a_parallel_message(self):
        agent = self.agent(["write-document"])
        conv = self.call("POST", f"agents/{agent['id']}/conversations", {}, key="c")
        self.call("POST", f"agents/{agent['id']}/runs", {"task": "First", "conversation_id": conv["id"]}, key="a")
        with self.assertRaises(Error) as caught:
            self.call("POST", f"agents/{agent['id']}/runs", {"task": "Second", "conversation_id": conv["id"]}, key="b")
        self.assertEqual(caught.exception.code, "task_in_progress")

    # --- tool budget keeps room for the deliverable ------------------------------------
    def test_reading_cannot_use_up_the_calls_needed_to_save_the_deck(self):
        agent = self.agent(["analyze-data", "make-slideshow"])
        reads = [fn("analyze_data", {"table": CSV, "question": f"q{i}"}, f"r{i}")["parts"][0] for i in range(6)]
        replies = [
            {"role": "model", "parts": reads},
            fn("create_slideshow", DECK, "deck"),
            text("Saved the deck."),
        ]
        run = self.run_task(agent, "Analyze this CSV and turn it into slides\n" + CSV, replies, "k", max_steps=4)
        self.assertEqual(run["status"], "completed", run)
        with self.app.db.transaction() as c:
            executed = [a["tool_id"] for a in all_rows(c, "actions") if a["run_id"] == run["id"] and a["status"] == "executed"]
        self.assertEqual(executed.count("create_slideshow"), 1)
        self.assertEqual(executed.count("analyze_data"), 3)
        self.assertLessEqual(len(executed), 4)
        steps = self.call("GET", "runs/" + run["id"] + "/steps")
        self.assertTrue(any(s["label"] == "Skipped a read to keep room for saving" for s in steps))

    def test_exhausting_every_call_fails_only_that_task_with_a_clear_message(self):
        agent = self.agent(["analyze-data"])
        reads = [fn("analyze_data", {"table": CSV, "question": f"q{i}"}, f"r{i}")["parts"][0] for i in range(3)]
        run = self.run_task(agent, "Look at this data\n" + CSV, [{"role": "model", "parts": reads}], "k", max_steps=2)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_code"], "step_limit")
        self.assertIn("narrower request", run["error"])
        follow = self.run_task(agent, "Just count the rows\n" + CSV, [text("2 rows.")], "k2")
        self.assertEqual(follow["status"], "completed")

    # --- a claim of "saved" needs a saved artifact --------------------------------------
    def test_claiming_a_saved_deck_without_saving_is_repaired_once_then_fails(self):
        agent = self.agent(["make-slideshow"])
        run = self.run_task(agent, "Make a slideshow about launch plans",
                            [text("I saved the slideshow."), text("It is saved, honestly.")], "k")
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_code"], "deliverable_missing")
        self.assertIn("slideshow", run["error"])
        with self.app.db.transaction() as c:
            self.assertFalse([a for a in all_rows(c, "actions") if a["run_id"] == run["id"]])

    def test_the_repair_attempt_can_really_save_it(self):
        agent = self.agent(["make-slideshow"])
        run = self.run_task(agent, "Make a slideshow about launch plans",
                            [text("I saved the slideshow."), fn("create_slideshow", DECK, "d"), text("Saved.")], "k")
        self.assertEqual(run["status"], "completed", run)

    def test_plain_questions_do_not_demand_a_deliverable(self):
        agent = self.agent(["make-slideshow", "write-document"])
        run = self.run_task(agent, "What is a good structure for a decision memo?", [text("Lead with the ask.")], "k")
        self.assertEqual(run["status"], "completed")

    def test_requested_deliverables_are_detected_from_the_task(self):
        held = {"create_slideshow", "create_document", "draft_email"}
        self.assertEqual(deliverables.requested("Turn this into a 5-slide deck and a brief", held), ["create_slideshow", "create_document"])
        self.assertEqual(deliverables.requested("What does this repo do?", held), [])
        self.assertEqual(deliverables.requested("Make a deck", {"create_document"}), [])
        self.assertEqual(deliverables.reserve("Make a deck", held), 1)
        self.assertEqual(deliverables.reserve("Explain it", {"analyze_data"}), 0)

    # --- history compaction keeps provider history valid -------------------------------
    def test_history_compaction_shortens_old_results_but_keeps_pairing(self):
        big = {"text": "x" * 40000}
        contents = [{"role": "user", "parts": [{"text": "go"}]}]
        for i in range(4):
            contents.append(fn("github_read_file", {"path": f"f{i}"}, f"id{i}"))
            contents.append({"role": "user", "parts": [{"functionResponse": {"name": "github_read_file", "id": f"id{i}", "response": big}}]})
        out = history.compact(contents, budget=60000)
        self.assertLess(history.size(out), history.size(contents))
        ids = [p["functionResponse"]["id"] for m in out for p in m["parts"] if "functionResponse" in p]
        self.assertEqual(ids, ["id0", "id1", "id2", "id3"])
        self.assertTrue(out[2]["parts"][0]["functionResponse"]["response"]["compacted"])
        self.assertEqual(history.compact(contents[:3], budget=10 ** 6), contents[:3])

    # --- GitHub failures: retry the transient, recover the fixable ---------------------
    def test_transient_tool_failure_is_retried_not_fatal(self):
        # GitHub and model errors flagged retryable share one durable, bounded retry path.
        self.app.runtime.max_retries = 3
        agent = self.agent(["analyze-data"])
        transient = Error("GitHub rate limit reached.", 502, "github_error", {"retryable": True, "retry_after": 0})
        done = {"kind": "analysis", "highlights": []}
        replies = [fn("analyze_data", {"table": CSV}, "a"), text("Done.")]
        with patch.object(self.app.mcp, "call", side_effect=[transient, done]), \
             patch("backend.runtime.model.generate", side_effect=[(r, {}) for r in replies]):
            run = self.call("POST", f"agents/{agent['id']}/runs", {"task": "Look at this\n" + CSV}, key="k")
            for _ in range(10):
                with self.app.db.transaction(True) as c:
                    row = get(c, "runs", run["id"])
                    row.pop("next_attempt_at", None)
                    put(c, "runs", row)
                self.app.runtime.tick()
        final = self.call("GET", "runs/" + run["id"])
        self.assertEqual(final["status"], "completed", final)
        self.assertEqual(final["retry_count"], 1)

    def test_github_http_errors_are_classified(self):
        import io
        import urllib.error

        def fail(status, headers=None):
            headers = headers or {}
            err = urllib.error.HTTPError("https://x", status, "err", headers, io.BytesIO(b"{}"))
            gh = GitHubMCP({"GITHUB_PERSONAL_ACCESS_TOKEN": "tkn"})
            opener = type("O", (), {"open": lambda self_, *a, **k: (_ for _ in ()).throw(err)})()
            with patch("urllib.request.build_opener", return_value=opener):
                with self.assertRaises(Error) as caught:
                    gh.discover()
            return caught.exception.details

        self.assertTrue(fail(503)["retryable"])
        self.assertTrue(fail(429, {"Retry-After": "7"})["retryable"])
        self.assertEqual(fail(429, {"Retry-After": "7"})["retry_after"], 7)
        self.assertTrue(fail(403, {"X-RateLimit-Remaining": "0"})["retryable"])
        self.assertFalse(fail(401)["retryable"])
        self.assertFalse(fail(404)["retryable"])
        self.assertFalse(fail(403)["retryable"])

    def test_a_guessed_missing_file_is_recoverable(self):
        gh = GitHubMCP({"GITHUB_PERSONAL_ACCESS_TOKEN": "tkn"})
        missing = {"isError": True, "content": [{"type": "text", "text": "Not Found: path README.mdx does not exist"}]}
        with patch.object(gh, "_session", return_value=missing):
            result = gh.call("github_read_file", {"path": "README.mdx"}, "team/repo")
        self.assertEqual(result["error"], "path_not_found")
        self.assertIn("Do not retry the same path", result["message"])
        denied = {"isError": True, "content": [{"type": "text", "text": "Resource access forbidden"}]}
        with patch.object(gh, "_session", return_value=denied):
            with self.assertRaises(Error) as caught:
                gh.call("github_read_file", {"path": "README.md"}, "team/repo")
        self.assertFalse(caught.exception.details["retryable"])

    # --- setup model calls never hold the database lock --------------------------------
    def test_slow_setup_model_does_not_freeze_other_requests(self):
        self.app.config["MODEL_API_KEY"] = "fake"
        entered, release = threading.Event(), threading.Event()

        def slow(*args, **kwargs):
            entered.set()
            release.wait(10)
            return {"role": "model", "parts": [{"text": json.dumps({"name": "Slow", "instructions": "Do the job.", "capability_ids": ["write-document"], "kind": "hire"})}]}, {}

        result = {}

        def create():
            result["agent"] = self.call("POST", "agents/quick-create",
                                        {"description": "Write briefs for executives", "model_profile_id": "meta", "name": "Slow agent",
                                         "capability_ids": ["write-document"]}, key="slow")

        with patch("backend.runtime.model.generate", side_effect=slow):
            thread = threading.Thread(target=create)
            thread.start()
            self.assertTrue(entered.wait(5))
            started = time.monotonic()
            self.call("GET", "agents")
            self.call("POST", "agents/quick-create", {"capability_ids": ["write-document"], "name": "Fast one"}, key="fast")
            self.assertLess(time.monotonic() - started, 3, "other writes must not wait for the model")
            release.set()
            thread.join(10)
        self.assertEqual(result["agent"]["status"], "created")

    def test_setup_model_has_a_hard_time_limit(self):
        self.app.config["SETUP_TIMEOUT"] = 1
        self.app.config["MODEL_API_KEY"] = "fake"
        gate = threading.Event()

        def hang(*args, **kwargs):
            gate.wait(5)
            raise Error("late", 502, "provider_error")

        with patch("backend.runtime.model.generate", side_effect=hang):
            started = time.monotonic()
            with self.assertRaises(Error) as caught:
                self.call("POST", "agents/quick-create",
                          {"description": "Write briefs", "model_profile_id": "meta", "name": "Hung"}, key="hung")
        gate.set()
        self.assertEqual(caught.exception.code, "provider_timeout")
        self.assertLess(time.monotonic() - started, 4)

    def test_demo_model_cannot_be_combined_with_github(self):
        with self.assertRaises(Error) as caught:
            propose(self.app, {"message": "Read GitHub", "department_id": "support", "manager_id": "pavan",
                               "capability_ids": ["github-reading"]})
        self.assertIn(caught.exception.code, ("github_requires_live_model", "github_not_connected", "not_found"))


if __name__ == "__main__":
    unittest.main()


class ProposalRejectTests(unittest.TestCase):
    setUp = test_workspace.WorkspaceTests.setUp
    tearDown = test_workspace.WorkspaceTests.tearDown
    call = test_workspace.WorkspaceTests.call

    def waiting(self):
        self.call("PATCH", "policy", {"approval_scope": "agent"}, user="amol")
        result = self.call(
            "POST",
            "agents/quick-create",
            {"model_profile_id": "demo", "department_id": "support", "manager_id": "pavan",
             "capability_ids": ["draft-email"], "description": "Draft emails.", "name": "Relay"},
            user="shaun",
            key="quick-relay",
        )
        self.assertEqual(result["status"], "awaiting_confirmation")
        return result["proposal"]

    def test_manager_can_turn_down_a_request_and_it_cannot_be_confirmed(self):
        p = self.waiting()
        out = self.call("POST", f"recruiter/proposals/{p['id']}/reject", {"reason": "Not needed"}, user="pavan", key="rej1")
        self.assertEqual(out["status"], "rejected")
        with self.assertRaises(Error) as ctx:
            self.call("POST", f"recruiter/proposals/{p['id']}/confirm", {"revision": p["revision"]}, user="pavan", key="conf1")
        self.assertEqual(ctx.exception.code, "proposal_rejected")
        agents = self.call("GET", "agents", user="pavan")
        self.assertFalse([a for a in agents if a["name"] == "Relay"])

    def test_asker_can_withdraw_their_own_request(self):
        p = self.waiting()
        out = self.call("POST", f"recruiter/proposals/{p['id']}/reject", {}, user="shaun", key="rej2")
        self.assertEqual(out["status"], "rejected")

    def test_other_users_cannot_turn_down_someone_elses_request(self):
        p = self.waiting()
        with self.assertRaises(Error):
            self.call("POST", f"recruiter/proposals/{p['id']}/reject", {}, user="member", key="rej3")

    def test_only_waiting_requests_can_be_turned_down(self):
        p = self.waiting()
        self.call("POST", f"recruiter/proposals/{p['id']}/reject", {}, user="pavan", key="rej4")
        with self.assertRaises(Error) as ctx:
            self.call("POST", f"recruiter/proposals/{p['id']}/reject", {}, user="pavan", key="rej5")
        self.assertEqual(ctx.exception.code, "proposal_not_waiting")
