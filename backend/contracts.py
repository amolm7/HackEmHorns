import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4


class Error(Exception):
    def __init__(self, message, status=400, code="invalid_request", details=None):
        super().__init__(message)
        self.status, self.code, self.details = status, code, details or {}


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def require(condition, message, status=400, code="invalid_request"):
    if not condition:
        raise Error(message, status, code)


def string(value, name, limit=8000):
    require(
        isinstance(value, str) and 0 < len(value.strip()) <= limit,
        f"{name} must be text between 1 and {limit} characters.",
    )
    return value.strip()


def roles(actor, *allowed):
    require(
        bool(set(actor["roles"]) & set(allowed)),
        "Your role does not permit this operation.",
        403,
        "permission_denied",
    )


def in_org(actor, obj):
    require(actor["org_id"] == obj["org_id"], "Resource not found.", 404, "not_found")


def department_access(actor, department_id):
    require(
        "admin" in actor["roles"] or department_id in actor["department_ids"],
        "Department access denied.",
        403,
        "permission_denied",
    )


def visible_agent(actor, agent):
    in_org(actor, agent)
    if "auditor" not in actor["roles"]:
        department_access(actor, agent["department_id"])


def manage(actor, agent):
    in_org(actor, agent)
    require(
        "admin" in actor["roles"]
        or ("manager" in actor["roles"] and actor["id"] == agent["manager_id"]),
        "Only the assigned manager or an organization admin may do this.",
        403,
        "permission_denied",
    )
