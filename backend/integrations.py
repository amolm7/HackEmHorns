"""Admin setup for the pre-registered GitHub adapter, without holding a write lock over network I/O."""
from .contracts import roles, department_access, digest, now, require, string, uid
from .db import all_rows, get, put, audit
from .github import GITHUB_TOOLS, GITHUB_SKILL, repository_name


def github_status(c, app, actor):
    connections = [row for row in all_rows(c, "connections")
                   if row["org_id"] == actor["org_id"] and row.get("kind") == "github_mcp"
                   and ("admin" in actor["roles"] or set(row["department_ids"]) & set(actor["department_ids"]))]
    ready = [row for row in connections if row["active"] and app.github.configured
             and row.get("credential_version") == digest(app.github.token)]
    return {"configured": app.github.configured, "connected": bool(ready),
            "department_ids": sorted({dept for row in ready for dept in row["department_ids"]}),
            "capability_id": "github-reading", "read_only": True}


def connect_github(app, actor_id, data):
    repository = repository_name(data.get("repository"))
    department = data.get("department_id")
    with app.db.transaction() as c:
        actor = app.actor(c, actor_id)
        roles(actor, "admin")
        department_access(actor, department)
        require(get(c, "departments", department)["org_id"] == actor["org_id"], "Department not found.", 404)
    app.github.discover()
    app.github.call("github_read_file", {"path": "/"}, repository)
    with app.db.transaction(True) as c:
        actor = app.actor(c, actor_id)
        roles(actor, "admin")
        department_access(actor, department)
        ident = "github:" + actor["org_id"]
        existing = next((row for row in all_rows(c, "connections") if row["id"] == ident), None)
        departments = sorted(set((existing or {}).get("department_ids", [])) | {department})
        put(c, "connections", {
            "id": ident, "org_id": actor["org_id"], "name": "GitHub (read only)",
            "kind": "github_mcp", "active": True, "department_ids": departments,
            "creator_id": (existing or {}).get("creator_id", actor["id"]),
            "secret_ref": "env:GITHUB_PERSONAL_ACCESS_TOKEN",
            "credential_version": digest(app.github.token), "tested_repository": repository,
            "validated_at": now(),
        })
        audit(c, actor, "github.connected", ident, {"department_id": department, "repository": repository})
        return {"status": "connected", "repository": repository,
                "message": "GitHub connector prepared. Create a named tool from the bottom of Library."}


def publish_github(c, app, actor, data):
    roles(actor, "admin", "manager")
    department = data.get("department_id")
    department_access(actor, department)
    connection = get(c, "connections", "github:" + actor["org_id"])
    require(connection["active"] and department in connection["department_ids"]
            and app.github.configured and connection.get("credential_version") == digest(app.github.token)
            and connection.get("validated_at"),
            "The GitHub connector must be prepared for this department before adding a tool.",
            409, "github_not_connected")
    existing = any(row["id"] == "github-reading" for row in all_rows(c, "capabilities"))
    name = string(data.get("name"), "name", 100)
    description = string(data.get("description"), "description", 1000)
    cap = put(c, "capabilities", {
        "id": uid() if existing else "github-reading", "org_id": actor["org_id"],
        "name": name, "description": description, "agent_name": name,
        "group": "Connected services", "icon": "book", "creator_id": actor["id"],
        "connection_id": connection["id"], "tools": list(GITHUB_TOOLS),
        "tool_contracts": list(GITHUB_TOOLS.values()),
        "skill": GITHUB_SKILL + "\n\nPurpose of this tool: " + description,
        "example": "Read the README and open issues, then create a briefing with source links.",
        "approved": True, "version": 1, "sample_data": False, "test_recipe": "github-read-v1",
        "config_schema": {}, "created_at": now(),
    })
    audit(c, actor, "capability.registered", cap["id"], {"connector": "github"})
    return cap
