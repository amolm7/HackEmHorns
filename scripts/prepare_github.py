"""Prepare the GitHub connector from a terminal (same as Prepare GitHub in Library)."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import Application
from backend.integrations import connect_github
from backend.contracts import Error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="Repository used only to test access")
    parser.add_argument("--department", action="append", required=True)
    parser.add_argument("--actor", default="amol", help="Existing organization admin")
    args = parser.parse_args()
    settings = dict(os.environ)
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                settings.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    app = Application(settings.get("DATABASE_PATH") or ROOT / "data" / "workforce.sqlite3", settings)
    try:
        for department in args.department:
            connect_github(app, args.actor, {"repository": args.repository, "department_id": department})
        print("GitHub connector tested and prepared. Read GitHub repositories is now in the Library tools.")
        print("Optional: Library > Add a tool > GitHub adds another named tool.")
    except Error as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
