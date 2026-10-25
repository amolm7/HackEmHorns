from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from .contracts import Error, uid, now

TABLES = {
    "password_accounts",
    "auth_sessions",
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
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        for candidate in [self.path, self.path + "-wal", self.path + "-shm"]:
            if Path(candidate).exists():
                os.chmod(candidate, 0o600)
        with self.transaction() as c:
            c.execute("PRAGMA journal_mode=WAL")
            for table in sorted(TABLES):
                c.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, body TEXT NOT NULL)"
                )

            # Additive, repeatable migration: existing JSON documents need no rewrite.
            for table, field in [
                ("runs", "status"),
                ("runs", "agent_id"),
                ("actions", "run_id"),
                ("approvals", "run_id"),
                ("steps", "run_id"),
                ("outcomes", "run_id"),
                ("work_items", "org_id"),
                ("auth_sessions", "expires_at"),
            ]:
                c.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table}_{field} ON {table}(json_extract(body, '$.{field}'))"
                )
            c.execute("PRAGMA user_version=1")

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


def rows_for(c, table, field, value):
    assert table in TABLES
    assert field in {
        "run_id",
        "agent_id",
        "org_id",
        "status",
        "account_id",
        "expires_at",
    }
    return [
        json.loads(row["body"])
        for row in c.execute(
            f"SELECT body FROM {table} WHERE json_extract(body, '$.{field}')=? ORDER BY rowid",
            (value,),
        )
    ]
