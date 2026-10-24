import io
import json
import unittest
from unittest.mock import patch
from backend.runtime import model
from backend.contracts import Error
from backend.registry import TOOLS


class MetaAdapterTests(unittest.TestCase):
    def response(self, obj):
        return io.BytesIO(json.dumps(obj).encode())

    def test_meta_tool_call_and_result_roundtrip(self):
        native = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-meta",
                    "type": "function",
                    "function": {
                        "name": "search_tickets",
                        "arguments": '{"query":"login"}',
                    },
                }
            ],
        }
        response = {
            "choices": [{"message": native}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        }
        config = {"MODEL_API_KEY": "placeholder-only"}
        with patch.object(
            model.urllib.request, "urlopen", return_value=self.response(response)
        ) as send:
            content, usage = model.generate(
                config,
                [{"role": "user", "parts": [{"text": "Find the outage"}]}],
                "Use tools.",
                [TOOLS["search_tickets"]],
                provider="meta",
            )
            req = send.call_args.args[0]
            body = json.loads(req.data)
            self.assertEqual(req.full_url, "https://api.meta.ai/v1/chat/completions")
            self.assertEqual(body["tools"][0]["function"]["name"], "search_tickets")
            self.assertEqual(content["parts"][0]["functionCall"]["id"], "call-meta")
            self.assertEqual(usage["promptTokenCount"], 12)
        contents = [
            {"role": "user", "parts": [{"text": "Find the outage"}]},
            content,
            {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": "search_tickets",
                            "id": "call-meta",
                            "response": {"tickets": [{"id": "T-101"}]},
                        }
                    }
                ],
            },
        ]
        with patch.object(
            model.urllib.request,
            "urlopen",
            return_value=self.response(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Urgent outage [T-101].",
                            }
                        }
                    ]
                }
            ),
        ) as send:
            content, _ = model.generate(config, contents, "Use tools.", provider="meta")
            msgs = json.loads(send.call_args.args[0].data)["messages"]
            self.assertEqual(msgs[2], native)
            self.assertEqual(msgs[3]["role"], "tool")
            self.assertEqual(msgs[3]["tool_call_id"], "call-meta")
            self.assertIn("T-101", content["parts"][0]["text"])

    def test_meta_recruiter_uses_json_schema(self):
        obj = {
            "name": "Triage",
            "job_description": "Triage support",
            "instructions": "Use evidence",
            "capability_ids": ["ticket-search"],
            "kind": "hire",
        }
        response = {
            "choices": [{"message": {"role": "assistant", "content": json.dumps(obj)}}]
        }
        with patch.object(
            model.urllib.request, "urlopen", return_value=self.response(response)
        ) as send:
            model.generate(
                {"MODEL_API_KEY": "placeholder-only"},
                [{"role": "user", "parts": [{"text": "Hire support"}]}],
                "Return JSON.",
                structured=True,
                provider="meta",
            )
            payload = json.loads(send.call_args.args[0].data)
            self.assertEqual(payload["response_format"]["type"], "json_schema")

    def test_missing_key_and_malformed_args_fail_closed(self):
        with self.assertRaises(Error):
            model.generate({}, [], "Hello", provider="meta")
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "x",
                                "type": "function",
                                "function": {
                                    "name": "search_tickets",
                                    "arguments": "invalid",
                                },
                            }
                        ],
                    }
                }
            ]
        }
        with patch.object(
            model.urllib.request, "urlopen", return_value=self.response(response)
        ):
            with self.assertRaises(Error):
                model.generate(
                    {"MODEL_API_KEY": "placeholder-only"}, [], "Hello", provider="meta"
                )


if __name__ == "__main__":
    unittest.main()
