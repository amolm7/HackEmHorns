import json
from ..contracts import *
from ..db import *
from ..registry import capability, check_bindings, validate, list_catalog
from ..runtime import model


def check_manager(c, actor, department_id, manager_id):
    dept = get(c, "departments", department_id)
    in_org(actor, dept)
    department_access(actor, department_id)
    manager = get(c, "users", manager_id)
    in_org(actor, manager)
    require(
        "manager" in manager["roles"] or "admin" in manager["roles"],
        "Assigned user is not a manager.",
    )
    department_access(manager, department_id)


def new_agent(c, actor, spec, status="active"):
    check_manager(c, actor, spec.get("department_id"), spec.get("manager_id"))
    agent = {
        "id": uid(),
        "org_id": actor["org_id"],
        "creator_id": actor["id"],
        "department_id": spec["department_id"],
        "manager_id": spec["manager_id"],
        "name": string(spec.get("name"), "name", 100),
        "job_description": string(spec.get("job_description"), "job_description", 4000),
        "instructions": string(spec.get("instructions"), "instructions", 8000),
        "model_profile_id": spec.get("model_profile_id", "demo"),
        "bindings": spec.get("bindings", []),
        "level": "intern",
        "spec_version": 1,
        "status": status,
        "created_at": now(),
        "updated_at": now(),
    }
    require(
        agent["model_profile_id"] in ["demo", "gemini", "meta"],
        "Unknown model profile.",
    )
    put(c, "agents", agent)
    put(
        c,
        "versions",
        {
            "id": agent["id"] + ":1",
            "org_id": actor["org_id"],
            "agent_id": agent["id"],
            "spec_version": 1,
            "spec": agent,
            "created_at": now(),
        },
    )
    audit(c, actor, "agent.created", agent["id"], {"status": status, "level": "intern"})
    return agent


INTENTS = {
    "make-slideshow": ["slide", "deck", "presentation", "powerpoint", "pitch"],
    "write-document": ["document", "memo", "report", "brief", "proposal", "essay", "write up", "one-pager", "plan for"],
    "analyze-data": ["data", "csv", "spreadsheet", "analy", "chart", "metrics", "numbers"],
    "research-web": ["research", "summar", "article", "web page", "website", "url", "http", "look up"],
}
SUPPORT_WORDS = ["ticket", "support", "triage", "customer", "reply", "replies"]
SUPPORT_INSTRUCTIONS = "Triage support tickets, flag urgent issues, and prepare helpful local reply drafts using help-document evidence. Cite ticket and document IDs. Never claim drafts were sent."


def infer_capabilities(lower):
    picks = [cap for cap, words in INTENTS.items() if any(w in lower for w in words)]
    if picks:
        return picks
    if not any(w in lower for w in SUPPORT_WORDS + ["draft"]):
        raise Error(
            "I couldn't match that to a capability. Pick one from the list, or say what the agent should make or analyze: a slideshow, a document, data, or web research.",
            422,
            "unsupported_capability",
        )
    base = ["ticket-search", "help-docs"]
    if any(w in lower for w in ["draft", "reply", "triage"]):
        base.append("reply-drafts")
    return base


def default_name(caps):
    if len(caps) == 1:
        return caps[0].get("agent_name") or caps[0]["name"]
    if all(c.get("group") == "Support sandbox" for c in caps):
        return "Ticket Triage"
    return "Workspace Assistant"


def default_instructions(caps):
    if all(c.get("group") == "Support sandbox" for c in caps):
        return SUPPORT_INSTRUCTIONS
    names = ", ".join(c["name"].lower() for c in caps)
    return (
        f"You are a capable assistant with these capabilities: {names}. Do the user's task with your tools instead of describing what you would do. "
        "Ask one short clarifying question only when you cannot proceed without the answer. Cite any pages you read. "
        "Saving a deck or document only saves it in the workspace; never claim you sent or published anything."
    )


def conversation(c, actor):
    roles(actor, "admin", "manager", "builder")
    return put(
        c,
        "conversations",
        {
            "id": uid(),
            "org_id": actor["org_id"],
            "actor_id": actor["id"],
            "messages": [],
            "proposal_id": None,
            "created_at": now(),
        },
    )


def proposal_access(actor, p):
    in_org(actor, p)
    require(
        "admin" in actor["roles"]
        or actor["id"] == p["actor_id"]
        or ("manager" in actor["roles"] and actor["id"] == p["spec"].get("manager_id")),
        "Proposal not available to this actor.",
        403,
    )


def message(c, app, actor, id, data):
    roles(actor, "admin", "manager", "builder")
    conv = get(c, "conversations", id)
    in_org(actor, conv)
    require(
        conv["actor_id"] == actor["id"], "Conversation belongs to another actor.", 403
    )
    msg = string(data.get("message"), "message", 4000)
    conv["messages"].append({"role": "user", "text": msg, "created_at": now()})
    old = get(c, "proposals", conv["proposal_id"]) if conv.get("proposal_id") else None
    previous = old["spec"] if old and old["status"] == "draft" else {}
    mode = data.get("mode", "demo")
    require(mode in ["demo", "gemini", "meta"], "Unknown helper mode.")
    parsed = {}
    provider = "guided"
    if mode != "demo":
        content, _ = model.generate(
            app.config,
            [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "conversation": conv["messages"],
                                    "current_draft": previous,
                                }
                            )
                        }
                    ],
                }
            ],
            "You are a Recruiter setup helper. Available capabilities: "
            + "; ".join(
                f"{x['id']} ({x['description']})" for x in list_catalog(c, actor)
            )
            + ". Return JSON with name, job_description, instructions, capability_ids (array of catalog IDs), and kind (hire or capability). Only use capability to add tools when a target_agent_id has been explicitly supplied by the application. Do not invent connections, permissions, roles, departments or managers. Never claim a test or hire occurred. No GitHub, email sending or other external integrations are connected.",
            structured=True,
            provider=mode,
        )
        try:
            parsed = json.loads("".join(p.get("text", "") for p in content["parts"]))
        except ValueError:
            raise Error("Recruiter returned invalid JSON.", 502, "provider_error")
        require(
            isinstance(parsed, dict), "Recruiter returned an invalid proposal.", 502
        )
        provider = mode
    lower = msg.lower()
    if mode == "demo" and any(
        w in lower
        for w in [
            "github",
            "salesforce",
            "send email",
            "slack",
            "calendar",
            "study",
            "exam",
        ]
    ):
        raise Error(
            "This sandbox supports support-ticket search, help documents, and local reply drafts. External integrations and study content are not connected.",
            422,
            "unsupported_capability",
        )
    # Capabilities the person ticked in the app win over the helper model's suggestion.
    requested = data.get("capability_ids") or parsed.get("capability_ids")
    if requested is None:
        requested = previous.get("capability_ids") or infer_capabilities(lower)
    require(
        isinstance(requested, list) and 0 < len(requested) <= 10,
        "Choose 1–10 capability IDs.",
    )
    chosen = [capability(c, actor, id_) for id_ in requested]
    target_id = data.get("target_agent_id") or (
        old.get("target_agent_id") if old and old["status"] == "draft" else None
    )
    target = get(c, "agents", target_id) if target_id else None
    if target:
        manage(actor, target)
    spec = {
        **previous,
        "name": data.get("name")
        or parsed.get("name")
        or previous.get("name")
        or default_name(chosen),
        "job_description": parsed.get("job_description")
        or data.get("job_description")
        or previous.get("job_description")
        or msg,
        "instructions": parsed.get("instructions")
        or data.get("instructions")
        or previous.get("instructions")
        or default_instructions(chosen),
        "department_id": data.get("department_id")
        or previous.get("department_id")
        or (target["department_id"] if target else None),
        "manager_id": data.get("manager_id")
        or previous.get("manager_id")
        or (target["manager_id"] if target else None),
        "model_profile_id": data.get("model_profile_id")
        or previous.get("model_profile_id", "demo"),
        "capability_ids": requested,
        "bindings": [],
        "level": "intern",
    }
    if target:
        spec.update(
            name=target["name"],
            job_description=target["job_description"],
            instructions=target["instructions"],
            model_profile_id=target["model_profile_id"],
        )
        spec["capability_ids"] = list(
            dict.fromkeys([b["capability_id"] for b in target["bindings"]] + requested)
        )
    missing = [k for k in ["department_id", "manager_id"] if not spec.get(k)]
    if not missing:
        check_manager(c, actor, spec["department_id"], spec["manager_id"])
        for cap_id in spec["capability_ids"]:
            connection_id = (
                data.get("connection_id")
                or capability(c, actor, cap_id).get("connection_id")
                or "support-local"
            )
            v = validate(
                c,
                app,
                actor,
                cap_id,
                {
                    "connection_id": connection_id,
                    "department_id": spec["department_id"],
                },
            )
            spec["bindings"].append(
                {
                    "capability_id": cap_id,
                    "connection_id": connection_id,
                    "validation_id": v["id"],
                }
            )
    p = {
        "id": old["id"] if old and old["status"] == "draft" else uid(),
        "org_id": actor["org_id"],
        "actor_id": actor["id"],
        "kind": "capability" if target else "hire",
        "target_agent_id": target_id,
        "target_spec_version": target["spec_version"] if target else None,
        "revision": old["revision"] + 1 if old and old["status"] == "draft" else 1,
        "status": "draft",
        "spec": spec,
        "missing_fields": missing,
        "provider": provider,
        "created_at": now(),
        "resource_id": None,
    }
    put(c, "proposals", p)
    conv["proposal_id"] = p["id"]
    response = (
        "Please provide " + ", ".join(missing) + "."
        if missing
        else "Review this card. An authorized manager must confirm it. "
        + (
            "Existing autonomy will reset to Intern when capabilities change."
            if target
            else "The new hire starts as an Intern."
        )
    )
    conv["messages"].append(
        {"role": "assistant", "text": response, "created_at": now()}
    )
    put(c, "conversations", conv)
    return {"message": response, "proposal": p, "conversation_id": conv["id"]}


def confirm(c, actor, id, data):
    p = get(c, "proposals", id)
    proposal_access(actor, p)
    require(
        p["revision"] == data.get("revision"),
        "Review card revision is stale. Reload the proposal.",
        409,
        "stale_proposal",
    )
    spec = p["spec"]
    manage(actor, {"org_id": p["org_id"], "manager_id": spec.get("manager_id")})
    if p["status"] == "confirmed":
        return get(c, "agents", p["resource_id"])
    require(not p["missing_fields"], "Complete missing fields first.", 409)
    check_manager(c, actor, spec["department_id"], spec["manager_id"])
    check_bindings(c, actor, spec["department_id"], spec["bindings"])
    if p["kind"] == "hire":
        agent = new_agent(c, actor, spec)
    else:
        agent = get(c, "agents", p["target_agent_id"])
        manage(actor, agent)
        require(
            agent["spec_version"] == p["target_spec_version"],
            "Target agent changed. Create a fresh proposal.",
            409,
            "stale_spec",
        )
        agent.update(
            bindings=spec["bindings"],
            level="intern",
            spec_version=agent["spec_version"] + 1,
            status="active",
            updated_at=now(),
        )
        put(c, "agents", agent)
        put(
            c,
            "versions",
            {
                "id": agent["id"] + ":" + str(agent["spec_version"]),
                "org_id": agent["org_id"],
                "agent_id": agent["id"],
                "spec_version": agent["spec_version"],
                "spec": agent,
                "created_at": now(),
            },
        )
    p.update(status="confirmed", resource_id=agent["id"])
    put(c, "proposals", p)
    audit(
        c,
        actor,
        "proposal.confirmed",
        id,
        {"resource_id": agent["id"], "revision": p["revision"]},
    )
    return agent


def patch_agent(c, actor, id, data):
    roles(actor, "admin", "manager", "builder")
    agent = get(c, "agents", id)
    visible_agent(actor, agent)
    require(
        "admin" in actor["roles"]
        or actor["id"] in [agent["creator_id"], agent["manager_id"]],
        "Cannot edit this agent.",
        403,
    )
    allowed = {
        "name",
        "job_description",
        "instructions",
        "model_profile_id",
        "department_id",
        "manager_id",
        "bindings",
        "expected_spec_version",
    }
    require(
        not (set(data) - allowed),
        "Use dedicated review endpoints to change autonomy or status.",
    )
    require(
        data.get("expected_spec_version") == agent["spec_version"],
        "Spec version conflict.",
        409,
        "stale_spec",
    )
    new = {**agent, **{k: v for k, v in data.items() if k != "expected_spec_version"}}
    check_manager(c, actor, new["department_id"], new["manager_id"])
    for field, limit in [
        ("name", 100),
        ("job_description", 4000),
        ("instructions", 8000),
    ]:
        new[field] = string(new[field], field, limit)
    require(
        new["model_profile_id"] in ["demo", "gemini", "meta"], "Unknown model profile."
    )
    if new["bindings"]:
        required = [x["id"] for x in agent.get("required_capabilities", [])] or None
        check_bindings(c, actor, new["department_id"], new["bindings"], required)
        for expected in agent.get("required_capabilities", []):
            require(
                capability(c, actor, expected["id"])["version"] == expected["version"],
                "Template capability version changed. Install a current template.",
                409,
                "stale_binding",
            )
    # Builder edits require manager activation. Any spec change resets autonomy and invalidates old pending runs.
    can_activate = "admin" in actor["roles"] or (
        "manager" in actor["roles"] and actor["id"] == new["manager_id"]
    )
    new.update(
        status=(
            "active"
            if new["bindings"] and can_activate
            else "draft" if new["bindings"] else "needs_connections"
        ),
        level="intern",
        spec_version=agent["spec_version"] + 1,
        updated_at=now(),
    )
    put(c, "agents", new)
    put(
        c,
        "versions",
        {
            "id": id + ":" + str(new["spec_version"]),
            "org_id": actor["org_id"],
            "agent_id": id,
            "spec_version": new["spec_version"],
            "spec": new,
            "created_at": now(),
        },
    )
    audit(c, actor, "agent.spec_changed", id, {"spec_version": new["spec_version"]})
    return new
