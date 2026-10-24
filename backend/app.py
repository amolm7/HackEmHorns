import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .contracts import *
from .db import *
from . import registry, recruiter, reviews, workqueue
from .runtime import Runtime, start, public_run, cancel
from .runtime.mcp import MCP


class Application:
    def __init__(self, path, config=None, worker=False):
        self.config = config or {}
        self.db = Database(path)
        registry.seed(self.db)
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
                (
                    len(parts) >= 2
                    and parts[-1] in ["confirm", "install", "runs", "decision"]
                )
                or (len(parts) == 4 and parts[-1] == "outcome")
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
            return {**actor, "identity_mode": "local_development_only"}
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
                    "name": self.config.get("GEMINI_MODEL", "gemini-2.5-flash"),
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
            if len(p) == 3 and method == "GET":
                return registry.capability(c, actor, p[2])
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
                    set(d) == {"require_all_approvals"}
                    and type(d["require_all_approvals"]) is bool,
                    "Provide require_all_approvals:boolean.",
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
        if path == "recruiter/conversations" and method == "POST":
            return recruiter.conversation(c, actor)
        if len(p) == 4 and p[1:3] == ["recruiter", "conversations"] and method == "GET":
            conv = get(c, "conversations", p[3])
            in_org(actor, conv)
            require(
                conv["actor_id"] == actor["id"],
                "Conversation belongs to another actor.",
                403,
            )
            return conv
        if (
            len(p) == 5
            and p[1:3] == ["recruiter", "conversations"]
            and p[4] == "messages"
            and method == "POST"
        ):
            return recruiter.message(c, self, actor, p[3], d)
        if len(p) >= 4 and p[1:3] == ["recruiter", "proposals"]:
            if len(p) == 4 and method == "GET":
                proposal = get(c, "proposals", p[3])
                recruiter.proposal_access(actor, proposal)
                return proposal
            if len(p) == 5 and p[4] == "confirm" and method == "POST":
                return recruiter.confirm(c, actor, p[3], d)
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
                if (
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
            if len(p) == 4:
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
                    result.append({**public_run(run), "outcome": outcomes.get(run["id"])})
            return result
        if len(p) >= 3 and p[1] == "runs":
            run = get(c, "runs", p[2])
            in_org(actor, run)
            visible_agent(actor, get(c, "agents", run["agent_id"]))
            if len(p) == 3 and method == "GET":
                outcome = next(
                    (o for o in all_rows(c, "outcomes") if o["run_id"] == run["id"]), None
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
            if len(p) == 3 and method == "GET":
                return reviews.detail(c, actor, p[2])
            if len(p) == 4 and p[3] == "decision" and method == "POST":
                return reviews.decide(c, actor, p[2], d)
        if path == "leaderboard" and method == "GET":
            return reviews.leaderboard(c, actor)
        if path == "audit" and method == "GET":
            roles(actor, "admin", "auditor")
            return [e for e in all_rows(c, "audit") if e["org_id"] == actor["org_id"]]
        raise Error("Endpoint not found.", 404, "not_found")
