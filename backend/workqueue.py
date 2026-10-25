"""Durable support intake linked to normal permission-checked agent executions."""

from .contracts import *
from .db import *
from .registry import TICKETS
from .runtime import start, allowed_tools, demo
from .quality import acceptance_for, check as check_quality
from . import reviews

POLICY = {
    "T-101": (
        "Engineering on-call",
        "login",
        "Acknowledge the outage and request the affected account and time window. The case needs engineering on-call review. Do not promise a resolution time.",
    ),
    "T-102": (
        "Support",
        "password",
        "Password reset links expire after 30 minutes. Request a new link from the sign-in page. Never share your password.",
    ),
    "T-103": (
        "Billing",
        "invoice",
        "Account administrators can download invoices from Billing > Invoice history. Refer missing invoices to the billing team.",
    ),
}

WORKFLOWS = {
    "launch": {
        "name": "Product launch",
        "tools": ["analyze_data", "create_document", "create_slideshow"],
        "caps": ["analyze-data", "write-document", "make-slideshow"],
        "route_to": "Launch owner",
    },
    "analysis": {
        "name": "Business analysis",
        "tools": ["analyze_data"],
        "caps": ["analyze-data"],
        "route_to": "Operations lead",
    },
    "brief": {
        "name": "Decision brief",
        "tools": ["create_document"],
        "caps": ["write-document"],
        "route_to": "Project owner",
    },
    "support": {
        "name": "Support response",
        "tools": ["search_tickets", "search_docs", "create_draft"],
        "caps": ["ticket-search", "help-docs", "reply-drafts"],
        "route_to": "Support",
    },
}
SAMPLES = {
    "launch": (
        "Launch Orbit on campus",
        "Prepare a launch decision package for Orbit, a fictional campus event discovery app. Analyze the pilot data below, save a decision brief and a 5-slide pitch deck. Company rules: total launch budget is $2000; do not invent market statistics; distinguish evidence from assumptions; include risks and a go/no-go recommendation. Do not spend money, send messages or publish anything.\nchannel,spend,signups\nAmbassadors,500,180\nPosters,300,45\nSocial,800,240",
    ),
    "analysis": (
        "Which growth channel deserves next week’s budget?",
        "Analyze the fictional campaign data below. Compare spend and signups by channel. Do not assume signups are paying customers or claim ROI without revenue data. Highlight limitations.\nchannel,spend,signups\nAmbassadors,500,180\nPosters,300,45\nSocial,800,240",
    ),
    "brief": (
        "Decide how to recover a delayed launch",
        "Write a decision brief for a fictional product launch delayed by one week. Options: reduce scope, postpone, or add a contractor. Company constraints: no new spend may be authorized; customer data must remain internal; manager must approve any launch date. Identify tradeoffs, open questions and a recommendation. Save the brief locally; do not contact anyone.",
    ),
}


def create(
    c,
    actor,
    workflow,
    title,
    task,
    sample=False,
    ident=None,
    department_id="support",
    acceptance=None,
):
    roles(actor, "admin", "manager", "builder")
    department_access(actor, department_id)
    require(workflow in SAMPLES, "Choose launch, analysis or brief.")
    item = {
        "id": ident or uid(),
        "org_id": actor["org_id"],
        "department_id": department_id,
        "workflow": workflow,
        "title": string(title, "title", 100),
        "task": string(task, "task", 4000),
        "sample_data": sample,
        "route_to": WORKFLOWS[workflow]["route_to"],
        "required_tools": WORKFLOWS[workflow]["tools"],
        "run_id": None,
        "agent_id": None,
        "created_at": now(),
    }
    item["acceptance"] = acceptance_for(workflow, task, acceptance)
    if "analyze_data" in item["required_tools"]:
        item["source_table"] = demo.table(task, fallback=False)
    put(c, "work_items", item)
    audit(c, actor, "work.created", item["id"])
    return item


def visible(actor, item):
    in_org(actor, item)
    department_access(actor, item["department_id"])


def listing(c, actor):
    result = []
    outcomes = {o["run_id"]: o for o in all_rows(c, "outcomes")}
    actions_by_run, steps_by_run = {}, {}
    for action in all_rows(c, "actions"):
        actions_by_run.setdefault(action["run_id"], []).append(action)
    for step in all_rows(c, "steps"):
        steps_by_run.setdefault(step["run_id"], []).append(step)
    for item in all_rows(c, "work_items"):
        try:
            visible(actor, item)
        except Error:
            continue
        run = get(c, "runs", item["run_id"]) if item.get("run_id") else None
        outcome = outcomes.get(run["id"]) if run else None
        actions = actions_by_run.get(run["id"], []) if run else []
        drafts = [
            a["result"]
            for a in actions
            if a["tool_id"] == "create_draft" and a.get("result")
        ]
        steps = steps_by_run.get(run["id"], []) if run else []
        successful = {
            a["tool_id"]
            for a in actions
            if a["status"] == "executed" and a.get("result")
        }
        artifacts = [
            {"tool": a["tool_id"], "result": a["result"]}
            for a in actions
            if a.get("result") and a["status"] == "executed"
        ]
        required = item.get("required_tools", WORKFLOWS["support"]["tools"])
        result.append(
            {
                **item,
                "title": item.get(
                    "title", item.get("ticket", {}).get("subject", "Work item")
                ),
                "workflow": item.get("workflow", "support"),
                "required_tools": required,
                "quality": run.get("quality") if run else None,
                "deliverables_ready": bool(
                    run and (run.get("quality") or check_quality(c, run))["passed"]
                ),
                "artifacts": artifacts,
                "status": ("accepted" if outcome["success"] else "needs_correction")
                if outcome
                else run["status"]
                if run
                else "unassigned",
                "outcome": outcome,
                "draft": drafts[-1] if drafts else None,
                "answer": run.get("result") if run else None,
                "error": run.get("error") if run else None,
                "finished_at": run.get("finished_at", run["updated_at"])
                if run and run["status"] in ["completed", "failed", "cancelled"]
                else None,
                "revision_count": sum(s.get("kind") == "revision" for s in steps),
            }
        )
    return result


def route(c, app, actor, method, p, d):
    if len(p) == 2 and method == "GET":
        return listing(c, actor)
    if len(p) == 2 and method == "POST":
        return create(
            c,
            actor,
            d.get("workflow"),
            d.get("title"),
            d.get("task"),
            department_id=d.get("department_id", "support"),
            acceptance={
                k: v for k, v in (d.get("acceptance") or {}).items() if v is not None
            },
        )
    if len(p) == 3 and p[2] == "sample-batch" and method == "POST":
        roles(actor, "manager", "admin", "builder")
        department_access(actor, "support")
        workflow = d.get("workflow", "support")
        if workflow != "support":
            require(workflow in SAMPLES, "Unknown workflow.")
            ident = actor["org_id"] + ":sample:" + workflow
            if not any(w["id"] == ident for w in all_rows(c, "work_items")):
                title, task = SAMPLES[workflow]
                create(c, actor, workflow, title, task, True, ident)
            return listing(c, actor)
        for ticket in TICKETS:
            ident = actor["org_id"] + ":support:" + ticket["id"]
            if any(w["id"] == ident for w in all_rows(c, "work_items")):
                continue
            team, query, reply = POLICY[ticket["id"]]
            put(
                c,
                "work_items",
                {
                    "id": ident,
                    "org_id": actor["org_id"],
                    "department_id": "support",
                    "ticket": ticket,
                    "sample_data": True,
                    "route_to": team,
                    "policy_query": query,
                    "demo_reply": reply,
                    "run_id": None,
                    "agent_id": None,
                    "created_at": now(),
                },
            )
        audit(c, actor, "queue.sample_loaded", "support")
        return listing(c, actor)
    if len(p) == 4 and p[3] == "assign" and method == "POST":
        item = get(c, "work_items", p[2])
        visible(actor, item)
        agent = get(c, "agents", d.get("agent_id"))
        manage(actor, agent)
        require(
            agent["department_id"] == item["department_id"],
            "Choose an agent in the queue department.",
            403,
        )
        feedback = None
        if item["run_id"]:
            previous = get(c, "runs", item["run_id"])
            feedback = next(
                (o for o in all_rows(c, "outcomes") if o["run_id"] == previous["id"]),
                None,
            )
            require(
                previous["status"] in ["failed", "cancelled"]
                or (feedback and not feedback["success"]),
                "This job is already assigned. Review the outcome before reassigning.",
                409,
            )
            item.setdefault("previous_run_ids", []).append(previous["id"])
        tools = allowed_tools(c, actor, agent)
        required = item.get("required_tools", WORKFLOWS["support"]["tools"])
        require(
            all(t in tools for t in required),
            "Agent is missing required workflow capabilities.",
            409,
        )
        if item.get("ticket"):
            ticket = item["ticket"]
            task = f"Handle support ticket {ticket['id']}: {ticket['subject']}. Customer: {ticket['customer']}. {ticket['body']} Read the ticket and approved policy, then save a reply draft for this ticket only. Proposed internal routing: {item['route_to']}. Do not send a message or claim routing has been delivered. Cite the policy used."
        else:
            task = item["task"]
        context = []
        if feedback:
            for action in all_rows(c, "actions"):
                if (
                    action["run_id"] == previous["id"]
                    and action["status"] == "executed"
                    and action.get("result")
                ):
                    context.append(
                        {"tool": action["tool_id"], "result": action["result"]}
                    )
        run = start(
            c,
            app,
            actor,
            agent["id"],
            {
                "task": task,
                "mode": d.get("mode", agent.get("model_profile_id", "demo")),
                "max_steps": 8,
            },
        )
        stored = get(c, "runs", run["id"])
        stored["work_item_id"] = item["id"]
        stored["workflow_tools"] = required
        stored["revision_context"] = (
            {
                "previous_run_id": previous["id"],
                "feedback": feedback["comment"],
                "deliverables": context,
            }
            if feedback
            else None
        )
        stored["acceptance"] = item.get(
            "acceptance", acceptance_for(item.get("workflow"), task)
        )
        if item.get("ticket"):
            stored["support_ticket"] = item["ticket"]
            stored["policy_query"] = item["policy_query"]
            stored["demo_reply"] = item["demo_reply"]
        put(c, "runs", stored)
        item.update(run_id=run["id"], agent_id=agent["id"], assigned_at=now())
        put(c, "work_items", item)
        audit(
            c,
            actor,
            "queue.assigned",
            item["id"],
            {"agent_id": agent["id"], "run_id": run["id"]},
        )
        return item
    if len(p) == 4 and p[3] == "review" and method == "POST":
        item = get(c, "work_items", p[2])
        visible(actor, item)
        require(bool(item["run_id"]), "Assign this ticket first.", 409)
        if d.get("success"):
            run = get(c, "runs", item["run_id"])
            successful = {
                a["tool_id"]
                for a in all_rows(c, "actions")
                if a["run_id"] == run["id"]
                and a["status"] == "executed"
                and a.get("result")
            }
            quality = check_quality(c, run)
            require(
                run["status"] == "completed" and quality and quality["passed"],
                "Accept only work that passes the deliverable checks.",
                409,
            )
        return reviews.outcome(c, actor, item["run_id"], d)
    raise Error("Endpoint not found.", 404, "not_found")
