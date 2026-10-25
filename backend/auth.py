"""Password authentication, opaque revocable sessions, and explicit role provisioning."""

import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from .contracts import Error, require, digest, now, string
from .db import all_rows, get, put, audit

COOKIE = "agent_session"
SESSION_SECONDS = 8 * 60 * 60


def password_hash(password):
    require(
        isinstance(password, str) and 12 <= len(password) <= 256,
        "Use a password between 12 and 256 characters.",
    )
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(
        password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024
    )
    return "scrypt$32768$8$1$" + salt.hex() + "$" + value.hex()


def password_matches(password, encoded):
    if not isinstance(password, str) or len(password) > 256:
        return False
    try:
        kind, n, r, p, salt, expected = encoded.split("$")
        if kind != "scrypt" or (n, r, p) != ("32768", "8", "1"):
            return False
        actual = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def provision(service, username, password, actor_id):
    username = string(username, "username", 100).lower()
    require(
        all(ch.isascii() and (ch.isalnum() or ch in "._-") for ch in username),
        "Username may contain letters, numbers, dots, underscores and hyphens.",
    )
    hashed = password_hash(password)
    with service.db.transaction(True) as c:
        actor = service.actor(c, actor_id)
        existing = next(
            (a for a in all_rows(c, "password_accounts") if a["username"] == username),
            None,
        )
        require(not existing, "That username already exists.", 409)
        account = {
            "id": digest(username),
            "username": username,
            "actor_id": actor["id"],
            "org_id": actor["org_id"],
            "password_hash": hashed,
            "active": True,
            "created_at": now(),
        }
        put(c, "password_accounts", account)
        audit(c, actor, "auth.account_provisioned", account["id"])
    return {k: v for k, v in account.items() if k != "password_hash"}


class Authentication:
    def __init__(self, service):
        self.service = service
        self.mode = service.config.get("AUTH_MODE", "development")
        self.production = service.config.get("APP_ENV") == "production"
        self.origin = service.config.get("APP_ORIGIN", "")
        self.cookie_name = "__Host-agent_session" if self.production else COOKIE
        self.cookie_path = "/" if self.production else "/api"
        require(
            self.mode in {"development", "password"},
            "AUTH_MODE must be development or password.",
        )
        if self.production:
            require(
                self.mode == "password",
                "Production requires password authentication; development impersonation cannot be deployed.",
            )
            parsed = urlsplit(self.origin)
            require(
                parsed.scheme == "https"
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment,
                "Production requires an HTTPS APP_ORIGIN.",
            )
        self.lock = threading.Lock()
        self.attempts = {}
        self.dummy_hash = (
            password_hash(secrets.token_urlsafe(24))
            if self.mode == "password"
            else None
        )
        self.login_slots = threading.BoundedSemaphore(2)
        if self.production:
            with service.db.transaction() as c:
                require(
                    any(a.get("active") for a in all_rows(c, "password_accounts")),
                    "Provision a password account locally before production startup.",
                )

    def close(self):
        pass

    def config(self):
        return {"mode": self.mode}

    def limit_login(self, username, address):
        current = int(time.monotonic() // 300)
        with self.lock:
            self.attempts = {k: v for k, v in self.attempts.items() if v[0] == current}
            for key, limit in [
                ("ip:" + address, 30),
                ("account:" + digest(username), 10),
            ]:
                entry = self.attempts.get(key, (current, 0))
                require(
                    entry[1] < limit,
                    "Too many sign-in attempts. Try again in a few minutes.",
                    429,
                    "rate_limited",
                )
            for key in ["ip:" + address, "account:" + digest(username)]:
                self.attempts[key] = (
                    current,
                    self.attempts.get(key, (current, 0))[1] + 1,
                )

    def login(self, username, password, address):
        require(self.mode == "password", "Password sign-in is not enabled.", 409)
        normalized = username.strip().lower()
        self.limit_login(normalized, address)
        require(
            self.login_slots.acquire(blocking=False),
            "Sign-in is busy. Try again shortly.",
            429,
            "rate_limited",
        )
        try:
            with self.service.db.transaction() as c:
                try:
                    account = get(c, "password_accounts", digest(normalized))
                except Error as error:
                    if error.status != 404:
                        raise
                    account = None
            matches = password_matches(
                password, account["password_hash"] if account else self.dummy_hash
            )
        finally:
            self.login_slots.release()
        require(
            matches and account and account.get("active"),
            "Incorrect username or password.",
            401,
            "unauthorized",
        )
        verified_hash = account["password_hash"]
        token = secrets.token_urlsafe(32)
        expires = (
            datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS)
        ).isoformat()
        with self.service.db.transaction(True) as c:
            account = get(c, "password_accounts", account["id"])
            require(
                account.get("active") and account["password_hash"] == verified_hash,
                "Incorrect username or password.",
                401,
                "unauthorized",
            )
            actor = self.service.actor(c, account["actor_id"])
            require(
                actor.get("active", True),
                "This account is disabled.",
                403,
                "account_disabled",
            )
            put(
                c,
                "auth_sessions",
                {
                    "id": digest(token),
                    "account_id": account["id"],
                    "actor_id": actor["id"],
                    "credential_version": digest(account["password_hash"]),
                    "created_at": now(),
                    "expires_at": expires,
                    "revoked": False,
                },
            )
            audit(c, actor, "auth.signed_in", account["id"])
        return token, {
            "user": actor,
            "csrf_token": self.csrf(token),
            "expires_at": expires,
        }

    @staticmethod
    def csrf(token):
        return hmac.new(
            token.encode(), b"hire-an-agent:csrf:v1", hashlib.sha256
        ).hexdigest()

    def session(self, request):
        token = request.cookies.get(self.cookie_name, "")
        require(0 < len(token) <= 100, "Sign in to continue.", 401, "unauthorized")
        with self.service.db.transaction() as c:
            session_row = c.execute(
                "SELECT body FROM auth_sessions WHERE id=?", (digest(token),)
            ).fetchone()
            import json

            session = json.loads(session_row["body"]) if session_row else None
            require(
                session
                and not session.get("revoked")
                and session["expires_at"] > now(),
                "Your session has expired. Sign in again.",
                401,
                "unauthorized",
            )
            account = get(c, "password_accounts", session["account_id"])
            require(
                account.get("active")
                and digest(account["password_hash"]) == session["credential_version"],
                "Sign in again.",
                401,
                "unauthorized",
            )
            actor = self.service.actor(c, account["actor_id"])
            require(
                actor.get("active", True),
                "This account is disabled.",
                403,
                "account_disabled",
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            require(
                hmac.compare_digest(
                    request.headers.get("x-csrf-token", ""), self.csrf(token)
                ),
                "Refresh the page before submitting this request.",
                403,
                "csrf_failed",
            )
        return actor, token, session

    def actor(self, request, development_actor):
        if self.mode == "development":
            return development_actor
        return self.session(request)[0]["id"]

    def logout(self, request):
        actor, token, session = self.session(request)
        with self.service.db.transaction(True) as c:
            session["revoked"] = True
            put(c, "auth_sessions", session)
            audit(c, actor, "auth.signed_out", session["account_id"])


def set_account_active(service, username, active):
    """Operator-only helper: disable also revokes sessions and the actor's queued work access."""
    with service.db.transaction(True) as c:
        account = get(c, "password_accounts", digest(username.strip().lower()))
        actor = get(c, "users", account["actor_id"])
        account["active"] = bool(active)
        actor["active"] = bool(active)
        put(c, "password_accounts", account)
        put(c, "users", actor)
        if not active:
            for session in all_rows(c, "auth_sessions"):
                if session["actor_id"] == actor["id"]:
                    session["revoked"] = True
                    put(c, "auth_sessions", session)
        audit(
            c,
            actor,
            "auth.account_enabled" if active else "auth.account_disabled",
            account["id"],
        )
