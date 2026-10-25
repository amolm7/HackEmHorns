"""Apply the ORBIT demo team's employee/manager assignments without changing passwords."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.db import Database, get, put, all_rows, audit


def configure(db):
    with db.transaction(True) as c:
        pavan, shaun = get(c, "users", "pavan"), get(c, "users", "shaun")
        pavan.update(roles=["builder"], manager_id="shaun")
        shaun.update(roles=["manager", "builder"], department_ids=["support", "engineering"])
        put(c, "users", pavan)
        put(c, "users", shaun)
        transferred = 0
        for agent in all_rows(c, "agents"):
            if agent["org_id"] == pavan["org_id"] and agent["manager_id"] == "pavan":
                agent["manager_id"] = "shaun"
                put(c, "agents", agent)
                transferred += 1
        for approval in all_rows(c, "approvals"):
            if approval["org_id"] == pavan["org_id"] and approval.get("assigned_manager_id") == "pavan" and approval["status"] == "pending":
                approval["assigned_manager_id"] = "shaun"
                put(c, "approvals", approval)
        audit(c, shaun, "team.roles_configured", "pavan", {"employee": "pavan", "manager": "shaun", "transferred_agents": transferred})
        accounts = {a["actor_id"] for a in all_rows(c, "password_accounts")}
        return transferred, "shaun" in accounts


if __name__ == "__main__":
    db = Database(Path(__file__).resolve().parents[1] / "data" / "workforce.sqlite3")
    count, has_login = configure(db)
    print(f"Pavan: developer/employee. Shaun: manager/developer. Transferred {count} agents.")
    print("Shaun login exists." if has_login else "Shaun still needs a password account: .venv/bin/python scripts/create_user.py --username shaun --actor shaun")
