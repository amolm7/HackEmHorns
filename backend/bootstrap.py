"""First-boot setup for a hosted demo, safe to run on every start.

On a host whose disk is wiped on restart (Render's free plan) the database comes back empty.
This recreates what the demo needs from environment variables: the admin account, and the GitHub
connector for one repository. It does nothing for parts that already exist, and a failure here
never stops the server from starting.
"""

import logging

from .app import Application
from .auth import provision
from .db import all_rows
from .integrations import connect_github

log = logging.getLogger("backend.bootstrap")
DEPARTMENTS = ("support", "engineering")


def run(settings, database_path):
    username = (settings.get("ADMIN_USERNAME") or "").strip().lower()
    password = settings.get("ADMIN_PASSWORD") or ""
    repository = (settings.get("GITHUB_DEMO_REPO") or "").strip()
    if not (username and password) and not repository:
        return {"admin": "skipped", "github": "skipped"}
    status = {"admin": "skipped", "github": "skipped"}
    app = Application(database_path, settings)
    try:
        if username and password:
            with app.db.transaction() as c:
                exists = any(a["username"] == username for a in all_rows(c, "password_accounts"))
            if exists:
                status["admin"] = "exists"
            else:
                try:
                    provision(app, username, password, settings.get("ADMIN_ACTOR", "amol"))
                    status["admin"] = "created"
                except Exception as error:  # noqa: BLE001 - report and carry on
                    status["admin"] = "failed"
                    log.error("Admin bootstrap failed: %s", error)
        if repository and settings.get("GITHUB_PERSONAL_ACCESS_TOKEN"):
            with app.db.transaction() as c:
                connected = any(c_["id"] == "github:hacktx" for c_ in all_rows(c, "connections"))
            if connected:
                status["github"] = "exists"
            else:
                try:
                    for department in DEPARTMENTS:
                        connect_github(
                            app,
                            settings.get("ADMIN_ACTOR", "amol"),
                            {"repository": repository, "department_id": department},
                        )
                    status["github"] = "connected"
                except Exception as error:  # noqa: BLE001
                    status["github"] = "failed"
                    log.error("GitHub bootstrap failed: %s", error)
    finally:
        app.close()
    return status
