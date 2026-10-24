from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from .contracts import Error, uid, now

TABLES = {
    "work_items",
    "agent_conversations",
    "users",
    "departments",
    "capabilities",
    "connections",
    "validations",
    "listings",
    "installs",
    "agents",
    "versions",
    "conversations",
    "proposals",
    "runs",
    "actions",
    "approvals",
    "steps",
    "audit",
    "outcomes",
    "tool_executions",
    "idempotency",
    "settings",
}


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as c:
            c.execute("PRAGMA journal_mode=WAL")
            for table in sorted(TABLES):
                c.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, body TEXT NOT NULL)"
                )

    @contextmanager
    def transaction(self, write=False):
        c = sqlite3.connect(self.path, timeout=60)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA busy_timeout=60000")
            if write:
                c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()


def put(c, table, obj):
    assert table in TABLES
    c.execute(
        f"INSERT INTO {table} (id,body) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
        (obj["id"], json.dumps(obj)),
    )
    return obj


def get(c, table, id):
    assert table in TABLES
    row = c.execute(f"SELECT body FROM {table} WHERE id=?", (str(id),)).fetchone()
    if row is None:
        raise Error("Resource not found.", 404, "not_found")
    return json.loads(row["body"])


def all_rows(c, table):
    assert table in TABLES
    return [
        json.loads(r["body"])
        for r in c.execute(f"SELECT body FROM {table} ORDER BY rowid")
    ]


def audit(c, actor, event, target, detail=None):
    put(
        c,
        "audit",
        {
            "id": uid(),
            "org_id": actor["org_id"],
            "actor_id": actor["id"],
            "event": event,
            "target_id": target,
            "detail": detail or {},
            "created_at": now(),
        },
    )
