"""Data-driven contract for every registered tool.

Adding a tool to backend/registry needs no new test file: the loops below pick it up. They fail
with an actionable message until the tool has a valid schema, a risk level and a fixture call.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import Application
from backend.registry import TOOLS
from backend.runtime import mcp as mcp_module

RISKS = {"read", "local_write", "always_approve"}

# One valid call per tool that works offline. Add an entry when you add a tool.
FIXTURES = {
    "search_tickets": {"query": "login"},
    "search_docs": {"query": "refund"},
    "create_draft": None,  # needs a real ticket id: filled in from the sample data below
    "create_slideshow": {"title": "Deck", "outline": "# One\n- a\n# Two\n- b"},
    "create_document": {"title": "Doc", "body": "# Heading\nBody text."},
    "schedule_meeting": {"title": "Sync", "start": "2030-01-01T10:00:00Z"},
    "draft_email": {"subject": "Hi", "body": "Hello there."},
    "create_task_list": {"title": "Todo", "tasks": "- one\n- two"},
    "analyze_data": {"table": "a,b\n1,2\n3,4", "question": "total of b"},
}
# Tools that reach the network. They are covered by mocked tests, never called here.
NETWORK = {"read_url"} | {n for n in TOOLS if n.startswith("github_")}


class RegistryContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(Path(self.tmp.name) / "t.db", {"ALLOW_TEST_ORG": True})

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def test_every_tool_is_well_formed(self):
        for name, tool in TOOLS.items():
            with self.subTest(tool=name):
                self.assertEqual(tool["name"], name)
                self.assertTrue(tool["description"].strip(), "needs a description")
                self.assertIn(tool["risk"], RISKS)
                schema = tool["inputSchema"]
                self.assertEqual(schema["type"], "object")
                self.assertIs(schema["additionalProperties"], False)
                self.assertTrue(set(schema["required"]) <= set(schema["properties"]))
                for field, spec in schema["properties"].items():
                    self.assertEqual(spec["type"], "string", field)
                    self.assertIsInstance(spec["maxLength"], int, field)
                json.dumps(tool)  # must be serialisable for MCP tools/list

    def test_write_tools_are_flagged_consistently(self):
        write = mcp_module.WRITE_TOOLS
        self.assertTrue(write <= set(TOOLS), "WRITE_TOOLS names an unknown tool")
        for name, tool in TOOLS.items():
            with self.subTest(tool=name):
                if name in write:
                    self.assertNotEqual(tool["risk"], "read", "saves data but is marked read")
                else:
                    self.assertEqual(tool["risk"], "read", "not in WRITE_TOOLS but not read-only")

    def test_every_tool_has_a_fixture_or_is_marked_network(self):
        covered = set(FIXTURES) | NETWORK
        missing = sorted(set(TOOLS) - covered)
        self.assertEqual(missing, [], f"Add a FIXTURES entry in tests/test_registry_contract.py for: {missing}")
        self.assertEqual(sorted(set(FIXTURES) - set(TOOLS)), [], "FIXTURES names a removed tool")

    def test_fixture_calls_succeed_and_write_tools_are_idempotent(self):
        from backend.registry import TICKETS

        fixtures = dict(FIXTURES, create_draft={"ticket_id": TICKETS[0]["id"], "body": "Thanks for waiting."})
        for name, args in fixtures.items():
            with self.subTest(tool=name):
                first = mcp_module.perform(self.app.db, name, args, "exec-" + name)
                self.assertIsInstance(first, dict)
                if name in mcp_module.WRITE_TOOLS:
                    again = mcp_module.perform(self.app.db, name, args, "exec-" + name)
                    self.assertEqual(first, again, "same execution id must not save twice")

    def test_schema_violations_are_rejected(self):
        for name in FIXTURES:
            with self.subTest(tool=name):
                with self.assertRaises(Exception):
                    mcp_module.perform(self.app.db, name, {"unexpected": "x"}, "bad-" + name)

    def test_network_tools_never_run_unmocked(self):
        # Guard: if someone moves a tool out of NETWORK without a fixture the test above fails; here we
        # make sure the network set only contains real tools.
        self.assertTrue(NETWORK <= set(TOOLS))


if __name__ == "__main__":
    unittest.main()
