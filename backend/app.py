import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .contracts import *
from .db import *
from . import registry, recruiter, reviews, workqueue
from .runtime import Runtime, start, public_run, cancel, conversations
from .runtime.mcp import MCP


def replay_access(c, parts, result):
    """Track resource authority, independently of mutable execution/status fields.

    A cached response must not bypass a department transfer or manager reassignment.
    Follow references so a run/approval also depends on its current agent's scope.
    """
    tables = (
        "agents", "runs", "approvals", "proposals", "work_items", "agent_conversations",
    )
    authority_fields = (
        "org_id", "department_id", "manager_id", "assigned_manager_id",
        "creator_id", "actor_id", "user_id", "agent_id", "target_agent_id",
        "run_id", "resource_id",
    )
    pending = set(parts[2:])

    def references(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if (key == "id" or key.endswith("_id")) and isinstance(item, str):
                    pending.add(item)
                elif isinstance(item, (dict, list)):
                    references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)

    references(result)
    seen, scopes = set(), {}
    while pending:
        ident = pending.pop()
        if ident in seen:
            continue
        seen.add(ident)
        for table in tables:
            row = c.execute(f"SELECT body FROM {table} WHERE id=?", (ident,)).fetchone()
            if row is None:
                continue
            obj = json.loads(row["body"])
            scopes[table + ":" + ident] = {key: obj.get(key) for key in authority_fields}
            if table == "proposals":
                scopes[table + ":" + ident]["spec_scope"] = {
                    key: obj.get("spec", {}).get(key)
                    for key in ("department_id", "manager_id", "agent_id")
                }
            for key in ("agent_id", "target_agent_id", "run_id", "resource_id"):
                if isinstance(obj.get(key), str):
                    pending.add(obj[key])
    return digest(scopes)


class Application:
    def __init__(self, path, config=None, worker=False):
        self.config = config or {}
        self.db = Database(path)
        registry.seed(self.db, self.config.get("APPROVAL_SCOPE", "agent"))
        self.mcp = MCP(self.db)
        self.runtime = Runtime(self)
        if worker:
            self.runtime.launch()

    def close(self):
        self.runtime.close()
        self.mcp.close()

    def actor(self, c, user_id):
        actor = get(c, "users", user_id)
        require(
            actor["org_id"] == "hacktx" or self.config.get("ALLOW_TEST_ORG"),
            "Unknown local development identity.",
            401,
            "unauthorized",
        )
        require(
            actor.get("active", True),
            "This account is disabled.",
            403,
            "account_disabled",
        )
        return actor

    def handle(self, method, url, data=None, user_id="pavan", key=None):
        parsed = urlsplit(url)
        parts = parsed.path.strip("/").split("/")
        query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        data = data or {}
        with self.db.transaction(method != "GET") as c:
            actor = self.actor(c, user_id)
            require(isinstance(data, dict), "JSON body must be an object.")
            idem = method == "POST" and (
                parts[1:2] == ["work-queue"]
                or (
                    len(parts) >= 2
                    and parts[-1] in ["confirm", "install", "runs", "decision", "quick-create"]
                )
                or (len(parts) == 4 and parts[-1] in ["outcome", "capabilities", "conversations"])
            )
            permission_hash = digest(
                {
                    k: actor.get(k)
                    for k in ["org_id", "roles", "department_ids", "active"]
                }
            )
            idem_id = None
            if idem:
                require(
                    isinstance(key, str) and 1 <= len(key) <= 200,
                    "Provide an Idempotency-Key header.",
                    400,
                    "idempotency_required",
                )
                idem_id = digest(
                    [actor["org_id"], actor["id"], method, parsed.path, key]
                )
                payload_hash = digest(data)
                old = next(
                    (i for i in all_rows(c, "idempotency") if i["id"] == idem_id), None
                )
                if old:
                    require(
                        old["payload_hash"] == payload_hash,
                        "Idempotency key was already used with a different request.",
                        409,
                        "idempotency_conflict",
                    )
                    require(
                        old.get("permission_hash") == permission_hash,
                        "Permissions changed since this request. Refresh before continuing.",
                        409,
                        "replay_access_changed",
                    )
                    require(
                        old.get("resource_access_hash") == replay_access(c, parts, old["result"]),
                        "Resource access changed since this request. Refresh before continuing.",
                        409,
                        "replay_access_changed",
                    )
                    return old["result"]
            result = self.route(c, actor, method, parts, query, data)
            if idem_id:
                put(
                    c,
                    "idempotency",
                    {
                        "id": idem_id,
                        "org_id": actor["org_id"],
                        "payload_hash": payload_hash,
                        "permission_hash": permission_hash,
                        "resource_access_hash": replay_access(c, parts, result),
                        "result": result,
                        "created_at": now(),
                    },
                )
            return result

    def route(self, c, actor, method, p, q, d):
        require(p[0] == "api", "Endpoint not found.", 404, "not_found")
        path = "/".join(p[1:])
        if p[1:2] == ["work-queue"]:
            return workqueue.route(c, self, actor, method, p, d)
        if method == "GET" and path == "me":
            return {
                **actor,
                "identity_mode": "password"
                if self.config.get("AUTH_MODE") == "password"
                else "local_development_only",
            }
        if method == "GET" and path == "dev/users":
            return [u for u in all_rows(c, "users") if u["org_id"] == actor["org_id"]]
        if method == "GET" and path == "model-profiles":
            return [
                {
                    "id": "demo",
                    "name": "Deterministic support sandbox",
                    "enabled": True,
                    "is_ai": False,
                },
                {
                    "id": "meta",
                    "name": self.config.get("META_MODEL", "muse-spark-1.3"),
                    "enabled": bool(
                        self.config.get("MODEL_API_KEY")
                        or self.config.get("META_API_KEY")
                    ),
                    "is_ai": True,
                },
                {
                    "id": "gemini",
                    "name": self.config.get("GEMINI_MODEL", "gemini-3.8-flash"),
                    "enabled": bool(self.config.get("GEMINI_API_KEY")),
                    "is_ai": True,
                },
            ]
        if path == "departments":
            if method == "GET":
                return [
                    x
                    for x in all_rows(c, "departments")
                    if x["org_id"] == actor["org_id"]
                    and (
                        "admin" in actor["roles"]
                        or "auditor" in actor["roles"]
                        or x["id"] in actor["department_ids"]
                    )
                ]
            if method == "POST":
                roles(actor, "admin")
                result = put(
                    c,
                    "departments",
                    {
                        "id": uid(),
                        "org_id": actor["org_id"],
                        "name": string(d.get("name"), "name", 100),
                    },
                )
                audit(c, actor, "department.created", result["id"])
                return result
        if path == "capabilities":
            if method == "GET":
                return registry.list_catalog(c, actor)
            if method == "POST":
                return registry.register(c, actor, d)
        if len(p) >= 3 and p[1] == "capabilities":
            if len(p) == 4 and p[3] == "validate" and method == "POST":
                return registry.validate(c, self, actor, p[2], d)
        if path == "connections" and method == "GET":
            return [
                registry.public_connection(x)
                for x in all_rows(c, "connections")
                if x["org_id"] == actor["org_id"]
                and (
                    "admin" in actor["roles"]
                    or set(x["department_ids"]) & set(actor["department_ids"])
                )
            ]
        if len(p) == 3 and p[1] == "connections" and method == "PATCH":
            roles(actor, "admin")
            conn = get(c, "connections", p[2])
            in_org(actor, conn)
            require(
                set(d) == {"active"} and type(d["active"]) is bool,
                "Only active:boolean can be changed.",
            )
            conn["active"] = d["active"]
            put(c, "connections", conn)
            audit(c, actor, "connection.active_changed", conn["id"], d)
            return registry.public_connection(conn)
        if path == "policy":
            policy = get(c, "settings", "policy:" + actor["org_id"])
            if method == "GET":
                return policy
            if method == "PATCH":
                roles(actor, "admin")
                require(
                    bool(d)
                    and set(d) <= {"require_all_approvals", "approval_scope"}
                    and type(d.get("require_all_approvals", False)) is bool
                    and d.get("approval_scope", "agent") in registry.APPROVAL_SCOPES,
                    "Provide require_all_approvals:boolean and/or approval_scope: agent or action.",
                )
                policy.update(**d, revision=policy["revision"] + 1)
                put(c, "settings", policy)
                audit(c, actor, "policy.changed", policy["id"], d)
                return policy
        if path == "marketplace":
            if method == "GET":
                return registry.listing_view(c, actor)
            if method == "POST":
                return registry.listing(c, actor, d)
        if (
            len(p) == 4
            and p[1] == "marketplace"
            and p[3] == "install"
            and method == "POST"
        ):
            return registry.install(c, self, actor, p[2], d)
        if path == "recruiter/proposals" and method == "GET":
            result = []
            for proposal in all_rows(c, "proposals"):
                try:
                    recruiter.proposal_access(actor, proposal)
                    result.append(proposal)
                except Error:
                    pass
            return result
        if len(p) >= 4 and p[1:3] == ["recruiter", "proposals"]:
            if len(p) == 5 and p[4] == "confirm" and method == "POST":
                return recruiter.confirm(c, actor, p[3], d)
        if path == "agents/quick-create" and method == "POST":
            return recruiter.quick_create(c, self, actor, d)
        if path == "agents" and method == "GET":
            result = []
            for agent in all_rows(c, "agents"):
                try:
                    visible_agent(actor, agent)
                    result.append(agent)
                except Error:
                    pass
            return [
                a
                for a in result
                if (a["status"] != "archived" or q.get("include_archived") == "true")
                and (
                    not q.get("department_id")
                    or q["department_id"] == a["department_id"]
                )
                and (not q.get("manager_id") or q["manager_id"] == a["manager_id"])
            ]
        if len(p) >= 3 and p[1] == "agents":
            id = p[2]
            agent = get(c, "agents", id)
            visible_agent(actor, agent)
            if len(p) == 3:
                if method == "GET":
                    return agent
                if method == "PATCH":
                    return recruiter.patch_agent(c, actor, id, d)
                if method == "DELETE":
                    return recruiter.archive(c, actor, id)
            if len(p) == 4:
                if p[3] == "capabilities" and method == "POST":
                    return recruiter.add_capabilities(c, self, actor, id, d)
                if p[3] == "conversations":
                    if method == "POST":
                        return conversations.create(c, actor, agent)
                    if method == "GET":
                        return conversations.list_for(c, actor, agent)
                if p[3] == "runs" and method == "GET":
                    return self.route(c, actor, "GET", ["api", "runs"], {**q, "agent_id": id}, {})
                if p[3] == "activity" and method == "GET":
                    runs = self.route(c, actor, "GET", ["api", "runs"], {"agent_id": id}, {})
                    run_ids = {r["id"] for r in runs}
                    return {
                        "agent": agent, "runs": runs,
                        "steps": [x for x in all_rows(c, "steps") if x["org_id"] == actor["org_id"] and x["run_id"] in run_ids],
                        "approvals": [x for x in reviews.inbox(c, actor) if x["agent_id"] == id] if set(actor["roles"]) & {"admin", "manager", "auditor"} else [],
                        "conversations": conversations.list_for(c, actor, agent),
                    }
                if p[3] == "versions" and method == "GET":
                    return [
                        v
                        for v in all_rows(c, "versions")
                        if v["agent_id"] == id and v["org_id"] == actor["org_id"]
                    ]
                if p[3] == "runs" and method == "POST":
                    return start(c, self, actor, id, d)
                if p[3] == "level" and method == "POST":
                    return reviews.level(c, actor, id, d)
                if p[3] == "performance" and method == "GET":
                    return reviews.performance(c, actor, id)
        if path == "runs" and method == "GET":
            result = []
            outcomes = {
                o["run_id"]: o
                for o in all_rows(c, "outcomes")
                if o["org_id"] == actor["org_id"]
            }
            for run in all_rows(c, "runs"):
                try:
                    visible_agent(actor, get(c, "agents", run["agent_id"]))
                except Error:
                    continue
                if (not q.get("agent_id") or run["agent_id"] == q["agent_id"]) and (
                    not q.get("status") or run["status"] == q["status"]
                ):
                    result.append(
                        {**public_run(run), "outcome": outcomes.get(run["id"])}
                    )
            return result
        if len(p) >= 3 and p[1] == "runs":
            run = get(c, "runs", p[2])
            in_org(actor, run)
            visible_agent(actor, get(c, "agents", run["agent_id"]))
            if len(p) == 3 and method == "GET":
                outcome = next(
                    (o for o in all_rows(c, "outcomes") if o["run_id"] == run["id"]),
                    None,
                )
                return {**public_run(run), "outcome": outcome}
            if len(p) == 4:
                if p[3] == "steps" and method == "GET":
                    return [
                        s
                        for s in all_rows(c, "steps")
                        if s["run_id"] == run["id"] and s["org_id"] == actor["org_id"]
                    ]
                if p[3] == "cancel" and method == "POST":
                    return cancel(c, actor, run["id"])
                if p[3] == "outcome" and method == "POST":
                    return reviews.outcome(c, actor, run["id"], d)
        if path == "approvals" and method == "GET":
            return reviews.inbox(c, actor, q.get("status"))
        if len(p) >= 3 and p[1] == "approvals":
            if len(p) == 4 and p[3] == "decision" and method == "POST":
                return reviews.decide(c, actor, p[2], d)
        if path == "employees" and method == "GET":
            return reviews.employees(c, actor)
        if path == "leaderboard" and method == "GET":
            return reviews.leaderboard(c, actor)
        if path == "audit" and method == "GET":
            roles(actor, "admin", "auditor")
            return [e for e in all_rows(c, "audit") if e["org_id"] == actor["org_id"]]
        raise Error("Endpoint not found.", 404, "not_found")
