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


def new_agent(c, actor, spec, status="active", creator_id=None):
    check_manager(c, actor, spec.get("department_id"), spec.get("manager_id"))
    agent = {
        "id": uid(),
        "org_id": actor["org_id"],
        # The person who asked for the agent, even when a manager approved it.
        "creator_id": creator_id or actor["id"],
        "approved_by": actor["id"],
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
    "github-reading": ["github", "repository", "repo issues"],
    "make-slideshow": ["slide", "deck", "presentation", "powerpoint", "pitch"],
    "write-document": ["document", "memo", "report", "brief", "proposal", "essay", "write up", "one-pager", "plan for"],
    "analyze-data": ["data", "csv", "spreadsheet", "analy", "chart", "metrics", "numbers"],
    "research-web": ["research", "summar", "article", "web page", "website", "url", "http", "look up"],
    "schedule-meetings": ["meeting", "schedule", "calendar", "invite", "kickoff", "1:1", "standup"],
    "draft-email": ["email", "e-mail", "outreach", "follow-up note", "follow up note"],
    "plan-tasks": ["task list", "to-do", "todo", "action item", "checklist"],
}
SUPPORT_WORDS = ["ticket", "support", "triage", "customer", "reply", "replies"]
SUPPORT_INSTRUCTIONS = "Triage support tickets, flag urgent issues, and prepare helpful local reply drafts using help-document evidence. Cite ticket and document IDs. Never claim drafts were sent."


def infer_capabilities(lower):
    picks = [cap for cap, words in INTENTS.items() if any(w in lower for w in words)]
    if picks:
        return picks
    if not any(w in lower for w in SUPPORT_WORDS + ["draft"]):
        raise Error(
            "I couldn't match that to a capability. Pick tools from the list, or say what the agent should do: slides, documents, data, web research, meetings, emails or tasks.",
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
    return " & ".join(c.get("agent_name") or c["name"] for c in caps)[:90]


def unique_name(c, actor, base):
    names = {a["name"].casefold() for a in all_rows(c, "agents") if a["org_id"] == actor["org_id"]}
    names.update(p["spec"]["name"].casefold() for p in all_rows(c, "proposals") if p["org_id"] == actor["org_id"] and p["status"] == "draft")
    base = string(base, "name", 100)
    candidate, n = base, 2
    while candidate.casefold() in names:
        suffix = f" {n}"
        candidate = base[:100 - len(suffix)] + suffix
        n += 1
    return candidate


def default_instructions(caps, job_description=None):
    if all(c.get("group") == "Support sandbox" for c in caps):
        instructions = SUPPORT_INSTRUCTIONS
    else:
        names = ", ".join(c["name"].lower() for c in caps)
        instructions = (
            f"You are a capable assistant with these capabilities: {names}. Do the user's task with your tools instead of describing what you would do. "
            "Ask one short clarifying question only when you cannot proceed without the answer. Cite any pages you read. "
            "Saving a deck or document only saves it in the workspace; never claim you sent or published anything."
        )
    if job_description:
        instructions += (
            "\n\nAssigned job: " + job_description
            + "\nAdapt the content, audience, tone and output structure to this job, within your approved skills and company rules. "
            "Do not invent missing company facts, metrics or requirements."
        )
    return instructions


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
    if p.get("spec", {}).get("department_id"):
        department_access(actor, p["spec"]["department_id"])
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
        # Resolve explicit selections before sending anything to the setup model.
        selected = data.get("capability_ids")
        if selected is not None:
            require(isinstance(selected, list) and 0 < len(selected) <= 10, "Choose 1–10 capability IDs.")
            for cap_id in selected:
                capability(c, actor, cap_id)
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
                                    "selected_capability_ids": selected,
                                    "job_description": data.get("job_description"),
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
            + ". Tailor the instructions to the described job: define its purpose, audience, content priorities, tone, and expected output when supplied. Do not simply repeat the tool descriptions or invent unspecified business details. When selected_capability_ids is supplied, keep exactly those capabilities; the job description does not grant extra tools or permissions. Return JSON with name, job_description, instructions, capability_ids (array of catalog IDs), and kind (hire or capability). Only use capability to add tools when a target_agent_id has been explicitly supplied by the application. Do not invent connections, permissions, roles, departments or managers. Never claim a test or hire occurred. No GitHub, email sending or other external integrations are connected.",
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
    if "github" in lower:
        require(any(item["id"] == "github-reading" for item in list_catalog(c, actor)),
                "Ask an admin to add GitHub from Library before creating a GitHub agent.",
                409, "github_not_connected")
    if mode == "demo" and any(
        w in lower
        for w in [
            "salesforce",
            "slack",
            "study",
            "exam",
        ]
    ):
        raise Error(
            "That needs an outside integration that is not connected. Agents can make slides, documents, data analysis, web summaries, meeting invites, email drafts and task lists; nothing is sent.",
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
        require(target["status"] != "archived", "Archived agents cannot be changed.", 409)
    spec = {
        **previous,
        "name": data.get("name")
        or previous.get("name")
        or unique_name(c, actor, parsed.get("name") or default_name(chosen)),
        "job_description": data.get("job_description")
        or parsed.get("job_description")
        or previous.get("job_description")
        or msg,
        "instructions": parsed.get("instructions")
        or data.get("instructions")
        or previous.get("instructions")
        or default_instructions(chosen, data.get("job_description")),
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
            existing_connection = next(
                (b["connection_id"] for b in target["bindings"] if b["capability_id"] == cap_id),
                None,
            ) if target else None
            connection_id = (
                data.get("connection_id")
                or existing_connection
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
        agent = get(c, "agents", p["resource_id"])
        manage(actor, agent)
        return agent
    require(not p["missing_fields"], "Complete missing fields first.", 409)
    check_manager(c, actor, spec["department_id"], spec["manager_id"])
    check_bindings(c, actor, spec["department_id"], spec["bindings"])
    if p["kind"] == "hire":
        agent = new_agent(c, actor, spec, creator_id=p.get("actor_id"))
    else:
        agent = get(c, "agents", p["target_agent_id"])
        manage(actor, agent)
        require(agent["status"] != "archived", "Archived agents cannot be changed.", 409)
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
    require(agent["status"] != "archived", "Archived agents cannot be changed.", 409)
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


def quick_create(c, app, actor, data):
    """Use the same validated recruiter policy, in one replay-protected transaction."""
    conv = conversation(c, actor)
    payload = {
        "message": data.get("description") or "Create an agent with the selected capabilities.",
        "department_id": data.get("department_id") or next(iter(actor["department_ids"]), "support"),
        "manager_id": data.get("manager_id") or (
            actor["id"] if set(actor["roles"]) & {"admin", "manager"} else "pavan"
        ),
        "model_profile_id": data.get("model_profile_id", "demo"),
        # A written job needs tailoring even when skills were selected explicitly.
        # Skill-only creation stays deterministic and makes no unnecessary model call.
        "mode": (
            "demo" if data.get("capability_ids") and not data.get("description")
            else data.get("model_profile_id", "demo")
        ),
    }
    if data.get("description"):
        payload["job_description"] = data["description"]
    for key in ("name", "capability_ids"):
        if data.get(key):
            payload[key] = data[key]
    result = message(c, app, actor, conv["id"], payload)
    proposal = result["proposal"]
    can_confirm = "admin" in actor["roles"] or (
        "manager" in actor["roles"] and proposal["spec"]["manager_id"] == actor["id"]
    )
    if not can_confirm:
        audit(c, actor, "proposal.awaiting_confirmation", proposal["id"], {"manager_id": proposal["spec"]["manager_id"]})
        return {"status": "awaiting_confirmation", "proposal": proposal}
    agent = confirm(c, actor, proposal["id"], {"revision": proposal["revision"]})
    return {"status": "created", "agent": agent}


def add_capabilities(c, app, actor, id, data):
    agent = get(c, "agents", id)
    manage(actor, agent)
    require(agent["status"] != "archived", "Archived agents cannot be changed.", 409)
    require(data.get("expected_spec_version") == agent["spec_version"], "Spec version conflict.", 409, "stale_spec")
    requested = data.get("capability_ids") or [data.get("capability_id")]
    require(isinstance(requested, list) and 0 < len(requested) <= 10 and all(isinstance(x, str) for x in requested), "Choose 1–10 capability IDs.")
    existing = {b["capability_id"] for b in agent["bindings"]}
    if set(requested) <= existing:
        return agent
    conv = conversation(c, actor)
    result = message(c, app, actor, conv["id"], {
        "message": "Add the selected capabilities.", "target_agent_id": id,
        "capability_ids": requested, "mode": "demo",
    })
    p = result["proposal"]
    return confirm(c, actor, p["id"], {"revision": p["revision"]})


def archive(c, actor, id):
    from ..runtime import TERMINAL, cancel

    agent = get(c, "agents", id)
    in_org(actor, agent)
    # The assigned manager, an admin, or the person who created the agent may remove it.
    require(
        "admin" in actor["roles"]
        or ("manager" in actor["roles"] and actor["id"] == agent["manager_id"])
        or actor["id"] == agent.get("creator_id"),
        "Only the agent's creator, its manager or an admin can remove it.",
        403,
        "permission_denied",
    )
    if agent["status"] == "archived":
        return agent
    # cancel refuses in-flight tool calls. The transaction rolls back all changes on refusal.
    for run in all_rows(c, "runs"):
        if run["agent_id"] == id and run["status"] not in TERMINAL:
            cancel(c, actor, run["id"])
    agent.update(status="archived", archived_at=now(), updated_at=now())
    put(c, "agents", agent)
    audit(c, actor, "agent.archived", id)
    return agent
