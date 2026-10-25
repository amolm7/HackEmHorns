"""Provision an account without putting a password in arguments, logs, or environment."""

import argparse
import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app import Application
from backend.auth import provision, password_hash, set_account_active
from backend.contracts import Error, digest, now
from backend.db import all_rows, get, put, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--actor",
        help="Existing role-bearing user ID (pavan, amol, tarun, shaun). Required for new accounts.",
    )
    parser.add_argument(
        "--database",
        default=str(Path(__file__).resolve().parents[1] / "data" / "workforce.sqlite3"),
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--reset-password",
        action="store_true",
        help="Replace the password and invalidate all existing sessions.",
    )
    actions.add_argument(
        "--disable",
        action="store_true",
        help="Disable this user and revoke existing sessions.",
    )
    actions.add_argument(
        "--enable",
        action="store_true",
        help="Enable this user; a fresh sign-in is required.",
    )
    args = parser.parse_args()
    if not (args.disable or args.enable):
        password = getpass.getpass("Password (12–256 characters): ")
        if password != getpass.getpass("Confirm password: "):
            parser.error("Passwords do not match.")
    app = Application(args.database)
    try:
        if args.disable or args.enable:
            set_account_active(app, args.username, args.enable)
            print(
                "Account enabled."
                if args.enable
                else "Account disabled and sessions revoked."
            )
        elif args.reset_password:
            encoded = password_hash(password)
            with app.db.transaction(True) as c:
                account = next(
                    (
                        a
                        for a in all_rows(c, "password_accounts")
                        if a["username"] == args.username.strip().lower()
                    ),
                    None,
                )
                if not account:
                    parser.error("Account not found.")
                account["password_hash"] = encoded
                put(c, "password_accounts", account)
                audit(
                    c,
                    get(c, "users", account["actor_id"]),
                    "auth.password_reset",
                    account["id"],
                )
            print("Password updated. Existing sessions are invalidated.")
        else:
            if not args.actor:
                parser.error("--actor is required for a new account.")
            provision(app, args.username, password, args.actor)
            print(
                "Account created. Set AUTH_MODE=password in .env and restart the server."
            )
    except Error as exc:
        parser.error(str(exc))
    finally:
        app.close()


if __name__ == "__main__":
    main()
