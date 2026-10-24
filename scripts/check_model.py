"""Verify local provider credentials without printing keys or full provider responses."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import config
from backend.contracts import Error
from backend.runtime.model import generate

parser = argparse.ArgumentParser()
parser.add_argument("--provider", choices=["meta", "gemini"], default="meta")
args = parser.parse_args()
settings = config()
try:
    content, _ = generate(
        settings,
        [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "Draft a job card named Test Agent for support-ticket search. Return name, job_description, instructions, capability_ids containing ticket-search, and kind hire."
                    }
                ],
            }
        ],
        "You are a setup helper. Return the requested JSON object only.",
        structured=True,
        provider=args.provider,
    )
    proposal = json.loads("".join(p.get("text", "") for p in content["parts"]))
    if not isinstance(proposal, dict) or "name" not in proposal:
        raise Error("Structured output did not produce a job card.")
    print("PASS: authenticated structured Recruiter response.")
    tool = {
        "name": "lookup_demo_status",
        "description": "Return the current readiness of a harmless fictional local sandbox. Use this function to answer readiness questions.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    }
    contents = [
        {
            "role": "user",
            "parts": [
                {
                    "text": "Call lookup_demo_status to check whether the sandbox is ready. Do not guess."
                }
            ],
        }
    ]
    content, _ = generate(
        settings,
        contents,
        "Use the provided tool to check readiness.",
        [tool],
        provider=args.provider,
    )
    contents.append(content)
    calls = [p["functionCall"] for p in content["parts"] if "functionCall" in p]
    if not calls or any(f["name"] != "lookup_demo_status" for f in calls):
        raise Error("Provider did not return the expected sandbox tool call.")
    responses = []
    for fn in calls:
        response = {
            "name": fn["name"],
            "response": {"ready": True, "sample_data": True},
        }
        if fn.get("id"):
            response["id"] = fn["id"]
        responses.append({"functionResponse": response})
    contents.append({"role": "user", "parts": responses})
    final, _ = generate(
        settings,
        contents,
        "Report the tool result briefly.",
        [tool],
        provider=args.provider,
    )
    if not any(p.get("text") for p in final["parts"]):
        raise Error("No final answer returned after the tool result.")
    print("PASS: function call → local result → final answer.")
except (Error, ValueError) as exc:
    print("FAILED:", str(exc), file=sys.stderr)
    raise SystemExit(1)
