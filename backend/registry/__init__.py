from ..contracts import *
from ..db import get, put, all_rows, audit

TOOLS = {
    "search_tickets": {
        "name": "search_tickets",
        "description": "Search fictional support tickets by query. Read only.",
        "risk": "read",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    "search_docs": {
        "name": "search_docs",
        "description": "Search fictional company help documents. Read only.",
        "risk": "read",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    "create_draft": {
        "name": "create_draft",
        "description": "Save a local reply draft for a support ticket. Does not send a message. Requires human approval at every level.",
        "risk": "always_approve",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "body": {"type": "string"}},
            "required": ["ticket_id", "body"],
        },
    },
}
CAPS = [
    {
        "id": "ticket-search",
        "name": "Support ticket search",
        "tools": ["search_tickets"],
        "creator_id": "amol",
        "description": "Find customer tickets and urgency indicators.",
    },
    {
        "id": "help-docs",
        "name": "Support knowledge",
        "tools": ["search_docs"],
        "creator_id": "shaun",
        "description": "Find approved source material for support replies.",
    },
    {
        "id": "reply-drafts",
        "name": "Reply drafting",
        "tools": ["create_draft"],
        "creator_id": "tarun",
        "description": "Prepare local reply drafts. Human review always required.",
    },
]
TICKETS = [
    {
        "id": "T-101",
        "subject": "Production login outage",
        "customer": "Acme",
        "priority": "urgent",
        "body": "Our entire team cannot log in. This is blocking production.",
    },
    {
        "id": "T-102",
        "subject": "Password reset link expired",
        "customer": "Maple",
        "priority": "normal",
        "body": "My password reset link expired. How can I request another?",
    },
    {
        "id": "T-103",
        "subject": "Invoice copy request",
        "customer": "Birch",
        "priority": "normal",
        "body": "Please provide a copy of our invoice.",
    },
]
DOCS = [
    {
        "id": "D-101",
        "title": "Login incident response",
        "text": "For a production login outage, escalate to the on-call engineer. Acknowledge the incident and request the affected account and time window. Do not promise a resolution time.",
    },
    {
        "id": "D-102",
        "title": "Password reset",
        "text": "Password reset links expire after 30 minutes. Request a new link from the sign-in page. Never ask a customer to share their password.",
    },
    {
        "id": "D-103",
        "title": "Billing invoices",
        "text": "Account administrators can download invoices from Billing > Invoice history. For missing invoices, refer the request to the billing team.",
    },
]


def seed(db):
    with db.transaction(True) as c:
        if any(x["id"] == "seed-v1" for x in all_rows(c, "settings")):
            return
        for id, name in [("support", "Support"), ("engineering", "Engineering")]:
            put(c, "departments", {"id": id, "org_id": "hacktx", "name": name})
        people = [
            ("amol", "Amol", ["admin", "manager"], ["support", "engineering"]),
            ("tarun", "Tarun", ["manager"], ["support", "engineering"]),
            ("shaun", "Shaun", ["builder"], ["support"]),
            ("pavan", "Pavan", ["manager", "builder"], ["support", "engineering"]),
            ("member", "Demo Member", ["member"], ["support"]),
            ("auditor", "Demo Auditor", ["auditor"], []),
        ]
        for id, name, rs, depts in people:
            put(
                c,
                "users",
                {
                    "id": id,
                    "name": name,
                    "org_id": "hacktx",
                    "roles": rs,
                    "department_ids": depts,
                },
            )
        put(
            c,
            "users",
            {
                "id": "other-org",
                "name": "Isolation test actor",
                "org_id": "other-org",
                "roles": ["admin", "manager"],
                "department_ids": [],
            },
        )
        put(
            c,
            "settings",
            {
                "id": "policy:hacktx",
                "org_id": "hacktx",
                "revision": 1,
                "require_all_approvals": False,
            },
        )
        put(
            c,
            "settings",
            {
                "id": "policy:other-org",
                "org_id": "other-org",
                "revision": 1,
                "require_all_approvals": False,
            },
        )
        put(
            c,
            "connections",
            {
                "id": "support-local",
                "org_id": "hacktx",
                "name": "Fictional support sandbox",
                "department_ids": ["support"],
                "active": True,
                "kind": "bundled_mcp",
                "secret_ref": "process:local-mcp",
            },
        )
        for cap in CAPS:
            put(
                c,
                "capabilities",
                {
                    **cap,
                    "org_id": "hacktx",
                    "version": 1,
                    "approved": True,
                    "tool_contracts": [TOOLS[t] for t in cap["tools"]],
                    "created_at": now(),
                    "config_schema": {"type": "object", "properties": {}},
                    "test_recipe": "support-sandbox-v1",
                    "sample_data": True,
                },
            )
        put(c, "settings", {"id": "seed-v1", "created_at": now()})


def public_connection(conn):
    return {k: v for k, v in conn.items() if k != "secret_ref"}


def resolve(c, actor, connection_id, department_id):
    conn = get(c, "connections", connection_id)
    in_org(actor, conn)
    department_access(actor, department_id)
    require(
        conn["active"] and department_id in conn["department_ids"],
        "Connection is inactive or not permitted for this department.",
        403,
        "connection_denied",
    )
    return conn


def capability(c, actor, id):
    cap = get(c, "capabilities", id)
    in_org(actor, cap)
    require(cap["approved"], "Capability is not approved.", 409)
    return cap


def validate(c, app, actor, cap_id, data):
    roles(actor, "admin", "manager", "builder")
    cap = capability(c, actor, cap_id)
    conn_id = string(data.get("connection_id"), "connection_id", 100)
    dept = string(data.get("department_id"), "department_id", 100)
    resolve(c, actor, conn_id, dept)
    discovered = app.mcp.discover()
    checks = [
        {
            "name": "MCP tool discovery",
            "passed": all(t in [x["name"] for x in discovered] for t in cap["tools"]),
        }
    ]
    # Write capabilities are validated by schema/discovery and a read-only fixture, never by an unreviewed write.
    out = app.mcp.call("search_tickets", {"query": "login"}, "validation:" + uid())
    checks.append(
        {
            "name": "Known support fixture retrieved",
            "passed": any(t["id"] == "T-101" for t in out["tickets"]),
        }
    )
    result = put(
        c,
        "validations",
        {
            "id": uid(),
            "org_id": actor["org_id"],
            "capability_id": cap_id,
            "capability_version": cap["version"],
            "connection_id": conn_id,
            "department_id": dept,
            "passed": all(x["passed"] for x in checks),
            "checks": checks,
            "evidence": out,
            "created_at": now(),
            "test_scope": "Discovery and read-only fixture. No draft-write behavior or general answer quality is certified.",
        },
    )
    audit(
        c,
        actor,
        "capability.validated",
        cap_id,
        {"validation_id": result["id"], "passed": result["passed"]},
    )
    return result


def check_bindings(c, actor, department_id, bindings, required_ids=None):
    require(
        isinstance(bindings, list) and 0 < len(bindings) <= 10,
        "Provide 1–10 capability bindings.",
    )
    require(all(isinstance(b, dict) for b in bindings), "Invalid binding.")
    require(
        len({b.get("capability_id") for b in bindings}) == len(bindings),
        "Duplicate capability binding.",
    )
    for b in bindings:
        require(isinstance(b, dict), "Invalid binding.")
        cap = capability(c, actor, b.get("capability_id"))
        resolve(c, actor, b.get("connection_id"), department_id)
        v = get(c, "validations", b.get("validation_id"))
        in_org(actor, v)
        require(
            v["passed"]
            and v["capability_id"] == cap["id"]
            and v["capability_version"] == cap["version"]
            and v["connection_id"] == b.get("connection_id")
            and v["department_id"] == department_id,
            "Binding needs a passed validation for this exact capability, version, connection and department.",
            409,
            "validation_required",
        )
    if required_ids is not None:
        require(
            set(required_ids) == {b["capability_id"] for b in bindings},
            "Bindings must match the template capabilities.",
        )


def list_catalog(c, actor):
    return [x for x in all_rows(c, "capabilities") if x["org_id"] == actor["org_id"]]


def register(c, actor, data):
    roles(actor, "admin")
    names = data.get("tools")
    require(
        isinstance(names, list)
        and 0 < len(names) <= 3
        and all(t in TOOLS for t in names),
        "Only curated sandbox tools can be registered.",
    )
    cap = put(
        c,
        "capabilities",
        {
            "id": uid(),
            "org_id": actor["org_id"],
            "name": string(data.get("name"), "name", 100),
            "description": string(data.get("description"), "description", 1000),
            "tools": list(dict.fromkeys(names)),
            "tool_contracts": [TOOLS[t] for t in dict.fromkeys(names)],
            "creator_id": actor["id"],
            "version": 1,
            "approved": True,
            "config_schema": {},
            "test_recipe": "support-sandbox-v1",
            "sample_data": True,
            "created_at": now(),
        },
    )
    audit(c, actor, "capability.registered", cap["id"])
    return cap


def listing(c, actor, data):
    roles(actor, "admin", "manager", "builder")
    kind = data.get("kind")
    require(kind in ["agent", "capability"], "kind must be agent or capability.")
    source_id = data.get("source_id")
    if kind == "agent":
        agent = get(c, "agents", source_id)
        visible_agent(actor, agent)
        require(
            "admin" in actor["roles"]
            or actor["id"] == agent["manager_id"]
            or actor["id"] == agent["creator_id"],
            "Cannot publish this agent.",
            403,
        )
        payload = {
            k: agent[k]
            for k in ["name", "job_description", "instructions", "model_profile_id"]
        }
        payload["capabilities"] = [
            {
                "id": b["capability_id"],
                "version": capability(c, actor, b["capability_id"])["version"],
            }
            for b in agent["bindings"]
        ]
        if not payload["capabilities"]:
            payload["capabilities"] = agent.get("required_capabilities", [])
    else:
        cap = capability(c, actor, source_id)
        payload = {
            k: cap[k]
            for k in [
                "id",
                "name",
                "description",
                "version",
                "tools",
                "tool_contracts",
                "config_schema",
                "test_recipe",
            ]
        }
    cap_ids = (
        [x["id"] for x in payload["capabilities"]]
        if kind == "agent"
        else [payload["id"]]
    )
    contracts = [
        t for id in cap_ids for t in capability(c, actor, id)["tool_contracts"]
    ]
    tests = [
        v
        for v in all_rows(c, "validations")
        if v["org_id"] == actor["org_id"] and v["capability_id"] in cap_ids
    ]
    label = {
        "tools": contracts,
        "data_access": "Selected authorized support sandbox connection",
        "validation_count": len(tests),
        "passed_validation_count": sum(v["passed"] for v in tests),
        "sample_data": True,
        "security_scan": None,
        "publisher_verification": None,
    }
    out = put(
        c,
        "listings",
        {
            "id": uid(),
            "org_id": actor["org_id"],
            "kind": kind,
            "payload": payload,
            "publisher_id": actor["id"],
            "creator_id": agent["creator_id"] if kind == "agent" else cap["creator_id"],
            "scope": "company",
            "source_id": source_id,
            "version": 1,
            "nutrition_label": label,
            "created_at": now(),
        },
    )
    audit(c, actor, "marketplace.published", out["id"])
    return out


def listing_view(c, actor):
    installs = [i for i in all_rows(c, "installs") if i["org_id"] == actor["org_id"]]
    return [
        {**l, "installation_count": sum(i["listing_id"] == l["id"] for i in installs)}
        for l in all_rows(c, "listings")
        if l["org_id"] == actor["org_id"]
    ]


def install(c, app, actor, id, data):
    roles(actor, "admin", "manager", "builder")
    l = get(c, "listings", id)
    in_org(actor, l)
    if l["kind"] == "agent":
        from ..recruiter import new_agent

        department_id = string(data.get("department_id"), "department_id", 100)
        department_access(actor, department_id)
        resource = new_agent(
            c,
            actor,
            {
                **l["payload"],
                "department_id": department_id,
                "manager_id": data.get("manager_id"),
                "bindings": [],
            },
            status="needs_connections",
        )
        resource["required_capabilities"] = l["payload"]["capabilities"]
        put(c, "agents", resource)
        # Store the complete spec after adding portable requirements.
        put(
            c,
            "versions",
            {
                "id": resource["id"] + ":1",
                "org_id": actor["org_id"],
                "agent_id": resource["id"],
                "spec_version": 1,
                "spec": resource,
                "created_at": now(),
            },
        )
    else:
        # Same-company capability recipe install: reference portable capability; no active connection is inherited.
        resource = {
            "id": uid(),
            "capability_id": l["payload"]["id"],
            "capability_version": l["payload"]["version"],
            "status": "needs_connection",
            "connection_id": None,
        }
    record = put(
        c,
        "installs",
        {
            "id": uid(),
            "org_id": actor["org_id"],
            "listing_id": id,
            "actor_id": actor["id"],
            "resource_id": resource["id"],
            "created_at": now(),
        },
    )
    audit(c, actor, "marketplace.installed", id, {"resource_id": resource["id"]})
    return {"install": record, "resource": resource}
