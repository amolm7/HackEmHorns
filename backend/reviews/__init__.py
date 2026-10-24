from ..contracts import *
from ..db import *
from ..runtime import TERMINAL, public_run, add_step


def inbox(c, actor, status=None):
    roles(actor, "admin", "manager", "auditor")
    return [
        a
        for a in all_rows(c, "approvals")
        if a["org_id"] == actor["org_id"]
        and (
            "admin" in actor["roles"]
            or "auditor" in actor["roles"]
            or a["assigned_manager_id"] == actor["id"]
        )
        and (not status or a["status"] == status)
    ]


def detail(c, actor, id):
    approval = get(c, "approvals", id)
    in_org(actor, approval)
    require(
        "admin" in actor["roles"]
        or "auditor" in actor["roles"]
        or (
            "manager" in actor["roles"]
            and approval["assigned_manager_id"] == actor["id"]
        ),
        "This approval belongs to another manager.",
        403,
    )
    steps = [
        s
        for s in all_rows(c, "steps")
        if s["run_id"] == approval["run_id"] and s["kind"] == "tool"
    ]
    return {**approval, "prior_tool_evidence": steps}


def decide(c, actor, id, data):
    approval = get(c, "approvals", id)
    agent = get(c, "agents", approval["agent_id"])
    manage(actor, agent)
    require(
        approval["status"] == "pending",
        "This review has already been decided or cancelled.",
        409,
        "review_closed",
    )
    require(
        approval["assigned_manager_id"] == agent["manager_id"],
        "Manager assignment changed. Start a new run.",
        409,
    )
    run = get(c, "runs", approval["run_id"])
    require(
        run["status"] == "awaiting_approval",
        "Run is no longer awaiting this review.",
        409,
    )
    require(
        run["spec_version"] == agent["spec_version"],
        "Agent changed after this action was proposed. Cancel and start a new run.",
        409,
        "stale_spec",
    )
    decision = data.get("decision")
    require(
        decision in ["approve", "reject", "request_revision"],
        "decision must be approve, reject, or request_revision.",
    )
    comment = data.get("comment", "")
    require(isinstance(comment, str) and len(comment) <= 2000, "Invalid comment.")
    if decision == "request_revision":
        string(comment, "Revision feedback", 2000)
    action = get(c, "actions", approval["action_id"])
    require(action["status"] == "proposed", "Action is no longer reviewable.", 409)
    approval.update(
        status={
            "approve": "approved",
            "reject": "rejected",
            "request_revision": "revision_requested",
        }[decision],
        decision={
            "kind": decision,
            "comment": comment,
            "actor_id": actor["id"],
            "created_at": now(),
        },
    )
    put(c, "approvals", approval)
    if decision == "approve":
        run["status"] = "queued"
    elif decision == "reject":
        action["status"] = "rejected"
        run.update(status="failed", error="Manager rejected the proposed action.")
    else:
        action["status"] = "rejected"
        run["status"] = "queued"
        if run["mode"] == "demo":
            fn = run["queue"][0]
            fn["args"] = dict(fn.get("args", {}))
            if fn["name"] == "create_draft":
                fn["args"]["body"] = (
                    fn["args"]["body"] + "\nManager-requested revision: " + comment
                )[:4000]
            else:
                fn["args"]["query"] = comment[:1000]
            add_step(
                c,
                run,
                "revision",
                "New action required",
                {
                    "feedback": comment,
                    "note": "Deterministic demo revision. A new approval is required.",
                },
            )
        else:
            responses = run["batch_responses"][:]
            for fn in run["queue"]:
                r = {
                    "name": fn["name"],
                    "response": {
                        "not_executed": True,
                        "manager_feedback": comment,
                        "requires_revision": True,
                    },
                }
                if fn.get("id"):
                    r["id"] = fn["id"]
                responses.append({"functionResponse": r})
            run["contents"].append(
                {
                    "role": "user",
                    "parts": responses
                    + [{"text": "Manager requested a revised action: " + comment}],
                }
            )
            run["queue"] = []
            run["batch_responses"] = []
    put(c, "actions", action)
    run["updated_at"] = now()
    put(c, "runs", run)
    audit(
        c,
        actor,
        "approval." + decision,
        id,
        {"action_id": action["id"], "run_id": run["id"]},
    )
    return {"approval": approval, "run": public_run(run)}


def level(c, actor, id, data):
    agent = get(c, "agents", id)
    manage(actor, agent)
    require(agent["status"] != "archived", "Archived agents cannot change autonomy.", 409)
    target = data.get("level")
    require(
        target in ["intern", "associate"], "MVP supports intern and associate only."
    )
    reason = string(data.get("reason"), "reason", 2000)
    previous = agent["level"]
    agent.update(level=target, updated_at=now())
    put(c, "agents", agent)
    audit(
        c,
        actor,
        "agent.level_changed",
        id,
        {"from": previous, "to": target, "reason": reason},
    )
    return agent


def performance(c, actor, id):
    agent = get(c, "agents", id)
    visible_agent(actor, agent)
    reviews = [r for r in all_rows(c, "approvals") if r["agent_id"] == id]
    decisions = [
        r
        for r in reviews
        if r["status"] in ["approved", "rejected", "revision_requested"]
    ]
    approved = sum(r["status"] == "approved" for r in decisions)
    runs = [r for r in all_rows(c, "runs") if r["agent_id"] == id]
    outcomes = [o for o in all_rows(c, "outcomes") if o["agent_id"] == id]
    return {
        "agent_id": id,
        "reviewed_actions": len(decisions),
        "approved_actions": approved,
        "rejected_actions": sum(r["status"] == "rejected" for r in decisions),
        "revision_requests": sum(
            r["status"] == "revision_requested" for r in decisions
        ),
        "approval_rate": approved / len(decisions) if decisions else None,
        "run_count": len(runs),
        "completed_runs": sum(r["status"] == "completed" for r in runs),
        "failed_runs": sum(r["status"] == "failed" for r in runs),
        "evaluated_tasks": len(outcomes),
        "successful_tasks": sum(o["success"] for o in outcomes),
        "task_success_rate": (
            sum(o["success"] for o in outcomes) / len(outcomes) if outcomes else None
        ),
        "note": "Action approval, execution completion, and manager-assessed task success are separate measures.",
    }


def outcome(c, actor, id, data):
    run = get(c, "runs", id)
    agent = get(c, "agents", run["agent_id"])
    manage(actor, agent)
    require(
        run["status"] in ["completed", "failed"],
        "Review task outcome after execution finishes.",
        409,
    )
    require(type(data.get("success")) is bool, "success must be a boolean.")
    require(
        not any(o["run_id"] == id for o in all_rows(c, "outcomes")),
        "Task outcome already recorded.",
        409,
    )
    if data['success'] and run.get('work_item_id'):
        item = get(c, 'work_items', run['work_item_id'])
        required = item.get('required_tools', ['search_tickets', 'search_docs', 'create_draft'])
        successful = {a['tool_id'] for a in all_rows(c, 'actions') if a['run_id'] == run['id'] and a['status'] == 'executed' and a.get('result')}
        require(run['status'] == 'completed' and all(t in successful for t in required), 'Accept only completed work with all required deliverables.', 409)
    result = put(
        c,
        "outcomes",
        {
            "id": uid(),
            "org_id": actor["org_id"],
            "agent_id": agent["id"],
            "run_id": id,
            "success": data["success"],
            "comment": string(data.get("comment"), "comment", 2000),
            "actor_id": actor["id"],
            "created_at": now(),
        },
    )
    audit(c, actor, "run.outcome_recorded", id)
    return result


def leaderboard(c, actor):
    rows = []
    for a in all_rows(c, "agents"):
        if a["org_id"] != actor["org_id"] or a["status"] == "archived":
            continue
        try:
            visible_agent(actor, a)
        except Error:
            continue
        p = performance(c, actor, a["id"])
        rows.append(
            {
                "agent_id": a["id"],
                "name": a["name"],
                "reviewed_actions": p["reviewed_actions"],
                "approval_rate": (
                    p["approval_rate"] if p["reviewed_actions"] >= 5 else None
                ),
                "eligible": p["reviewed_actions"] >= 5,
                "rated_tasks": p["evaluated_tasks"],
                "successful_tasks": p["successful_tasks"],
                "task_success_rate": (
                    p["task_success_rate"] if p["evaluated_tasks"] >= 3 else None
                ),
                "result_eligible": p["evaluated_tasks"] >= 3,
            }
        )
    rows.sort(key=lambda x: (x["eligible"], x["approval_rate"] or 0), reverse=True)
    listing_ids = {
        l["id"]: l for l in all_rows(c, "listings") if l["org_id"] == actor["org_id"]
    }
    creators = {}
    original_creators = {}
    capability_reuse = {}
    for i in all_rows(c, "installs"):
        if i["org_id"] == actor["org_id"] and i["listing_id"] in listing_ids:
            listing = listing_ids[i["listing_id"]]
            publisher = listing["publisher_id"]
            creators[publisher] = creators.get(publisher, 0) + 1
            creator = listing.get("creator_id", publisher)
            original_creators[creator] = original_creators.get(creator, 0) + 1
            cap_ids = (
                [x["id"] for x in listing["payload"]["capabilities"]]
                if listing["kind"] == "agent"
                else [listing["payload"]["id"]]
            )
            for cap_id in set(cap_ids):
                cap = get(c, "capabilities", cap_id)
                capability_reuse[cap_id] = {
                    "capability_id": cap_id,
                    "creator_id": cap["creator_id"],
                    "installations": capability_reuse.get(cap_id, {}).get(
                        "installations", 0
                    )
                    + 1,
                }
    usage = {}
    for a in all_rows(c, "agents"):
        if a["org_id"] != actor["org_id"] or a["status"] != "active":
            continue
        try:
            visible_agent(actor, a)
        except Error:
            continue
        for b in a["bindings"]:
            usage.setdefault(b["capability_id"], set()).add(a["id"])
    capability_usage, creator_usage = [], {}
    for cap_id, agent_ids in usage.items():
        cap = get(c, "capabilities", cap_id)
        capability_usage.append(
            {"capability_id": cap_id, "creator_id": cap["creator_id"], "agents": len(agent_ids)}
        )
        creator_usage[cap["creator_id"]] = creator_usage.get(cap["creator_id"], 0) + len(agent_ids)
    return {
        "minimum_reviewed_actions": 5,
        "minimum_rated_tasks": 3,
        "agents": rows,
        "publisher_reuse": [
            {"publisher_id": id, "installations": n}
            for id, n in sorted(creators.items(), key=lambda x: -x[1])
        ],
        "creator_reuse": [
            {"creator_id": id, "installations": n}
            for id, n in sorted(original_creators.items(), key=lambda x: -x[1])
        ],
        "capability_reuse": sorted(
            capability_reuse.values(), key=lambda x: -x["installations"]
        ),
        "capability_usage": sorted(capability_usage, key=lambda x: -x["agents"]),
        "creator_usage": [
            {"creator_id": id, "agents": n}
            for id, n in sorted(creator_usage.items(), key=lambda x: -x[1])
        ],
        "hours_saved": None,
    }
