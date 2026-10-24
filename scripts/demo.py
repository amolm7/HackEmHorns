"""Run a real local HTTP workflow. Requires python3 server.py in another terminal."""

import json
import os
import time
import urllib.request
from uuid import uuid4

BASE = os.environ.get("DEMO_BASE_URL", "http://localhost:8000") + "/api/"


def api(path, method="GET", body=None):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Dev-User": "pavan",
            "Idempotency-Key": str(uuid4()),
        },
    )
    with urllib.request.urlopen(request, timeout=10) as r:
        return json.load(r)


def finish(run, approve):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        current = api("runs/" + run["id"])
        if current["status"] in ["completed", "failed", "cancelled"]:
            if current["status"] != "completed":
                raise RuntimeError(current.get("error") or current["status"])
            return current
        if approve:
            for review in api("approvals?status=pending"):
                if review["run_id"] == run["id"]:
                    api(
                        "approvals/" + review["id"] + "/decision",
                        "POST",
                        {
                            "decision": "approve",
                            "comment": "HTTP demo: checked action scope.",
                        },
                    )
        time.sleep(0.1)
    raise RuntimeError("Timed out waiting for the run.")


conv = api("recruiter/conversations", "POST", {})
proposal = api(
    "recruiter/conversations/" + conv["id"] + "/messages",
    "POST",
    {
        "message": "Hire a support triage agent to draft replies",
        "name": "HTTP demo triage",
        "department_id": "support",
        "manager_id": "pavan",
        "mode": "demo",
    },
)["proposal"]
agent = api(
    "recruiter/proposals/" + proposal["id"] + "/confirm",
    "POST",
    {"revision": proposal["revision"]},
)
assert agent["level"] == "intern"
print("1. Hired Intern:", agent["id"])
run = api(
    "agents/" + agent["id"] + "/runs",
    "POST",
    {"task": "Triage the urgent login outage and draft a reply", "mode": "demo"},
)
end = time.monotonic() + 5
while (
    time.monotonic() < end and api("runs/" + run["id"])["status"] != "awaiting_approval"
):
    time.sleep(0.1)
assert api("runs/" + run["id"])["status"] == "awaiting_approval"
assert not [s for s in api("runs/" + run["id"] + "/steps") if s["kind"] == "tool"]
print("2. Paused with zero executed tools.")
finish(run, True)
steps = api("runs/" + run["id"] + "/steps")
calls = [s for s in steps if s["kind"] == "tool"]
assert len(calls) == 3
print("3. Manager approved 3 real MCP actions; local draft saved, not sent.")
api(
    "runs/" + run["id"] + "/outcome",
    "POST",
    {
        "success": True,
        "comment": "Demo fixture results checked against known source material.",
    },
)
api(
    "agents/" + agent["id"] + "/level",
    "POST",
    {
        "level": "associate",
        "reason": "Reviewed fixture reads and explicit approval boundaries.",
    },
)
read_run = api(
    "agents/" + agent["id"] + "/runs",
    "POST",
    {"task": "Find the urgent login outage", "mode": "demo"},
)
finish(read_run, False)
assert not [a for a in api("approvals") if a["run_id"] == read_run["id"]]
print("4. Associate reads completed without approval.")
listing = api("marketplace", "POST", {"kind": "agent", "source_id": agent["id"]})
assert "bindings" not in listing["payload"] and "level" not in listing["payload"]
install = api(
    "marketplace/" + listing["id"] + "/install",
    "POST",
    {"department_id": "support", "manager_id": "pavan"},
)["resource"]
assert (
    install["level"] == "intern"
    and not install["bindings"]
    and install["status"] == "needs_connections"
)
print("5. Installed template resets to Intern with no connections.")
bindings = []
for cap in install["required_capabilities"]:
    v = api(
        "capabilities/" + cap["id"] + "/validate",
        "POST",
        {"department_id": "support", "connection_id": "support-local"},
    )
    bindings.append(
        {
            "capability_id": cap["id"],
            "connection_id": "support-local",
            "validation_id": v["id"],
        }
    )
copy = api(
    "agents/" + install["id"],
    "PATCH",
    {"bindings": bindings, "expected_spec_version": 1},
)
assert copy["status"] == "active" and copy["level"] == "intern"
print("6. New install locally revalidated and activated as Intern.")
print("PASS: hire → pause → approve → execute → promote → publish → install → rebind.")
