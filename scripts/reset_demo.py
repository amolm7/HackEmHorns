"""Clear demo data before a demo: self-service accounts, the agents, runs and files they made.

    python scripts/reset_demo.py [--database PATH] [--yes]

Keeps the seeded people, the admin account, the audit log, tools and the GitHub connection. On a host with an ephemeral
disk, restarting the service does the same and bootstrap rebuilds the rest.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Tables whose rows belong to people and what they created.
OWNED = ["agents", "versions", "conversations", "agent_conversations", "proposals", "runs", "actions", "approvals", "steps",
         "outcomes", "tool_executions", "work_items", "idempotency"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(ROOT / "data" / "workforce.sqlite3"))
    parser.add_argument("--yes", action="store_true", help="do not ask first")
    args = parser.parse_args()
    db = sqlite3.connect(args.database)
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    members = [(r[0], json.loads(r[1])) for r in db.execute("SELECT id, body FROM users")] if "users" in tables else []
    members = [i for i, u in members if u.get("self_service")]
    counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in OWNED if t in tables}
    print(f"{len(members)} self-service users; rows: {counts}")
    if not args.yes and input("Delete them? [y/N] ").strip().lower() != "y":
        return print("Nothing changed.")
    with db:
        for t in counts:
            db.execute(f"DELETE FROM {t}")
        if "auth_sessions" in tables:
            for r in db.execute("SELECT id, body FROM auth_sessions").fetchall():
                if json.loads(r[1]).get("actor_id") in members:
                    db.execute("DELETE FROM auth_sessions WHERE id=?", (r[0],))
        if "password_accounts" in tables:
            for r in db.execute("SELECT id, body FROM password_accounts").fetchall():
                if json.loads(r[1]).get("actor_id") in members:
                    db.execute("DELETE FROM password_accounts WHERE id=?", (r[0],))
        for m in members:
            db.execute("DELETE FROM users WHERE id=?", (m,))
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())
