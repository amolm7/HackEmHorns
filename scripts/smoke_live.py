"""Check a deployed copy of the app from the outside.

    python scripts/smoke_live.py https://your-app.onrender.com [--wait 240] [--expect-version GIT_SHA]

Waits for the site to come up (a free host may be waking from sleep), then checks health, the
sign-in config and static files (and, with --expect-version, that the new build is the one answering), signs up a throwaway account when sign-up is on, and hires and
runs one offline agent. Exits non-zero on any failure, so a deploy workflow can fail on it.
"""

import argparse
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4


def client():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def call(base, path, method="GET", body=None, csrf=None):
        headers = {"Content-Type": "application/json", "Idempotency-Key": str(uuid4())}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = urllib.request.Request(
            base + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=headers
        )
        try:
            with opener.open(request, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
        except urllib.error.HTTPError as error:
            raw = error.read()
            return error.code, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)

    return call


def wait_ready(call, base, seconds, version=None):
    end = time.monotonic() + seconds
    last = None
    while time.monotonic() < end:
        try:
            status, body = call(base, "/api/ready")
            if status == 200 and body.get("ready"):
                if not version:
                    return body
                _, health = call(base, "/api/health")
                if health.get("version") == version:
                    return {**body, "version": version}
                last = f"still serving version {health.get('version')!r}, waiting for {version!r}"
            else:
                last = (status, body)
        except OSError as error:
            last = error
        time.sleep(5)
    raise SystemExit(f"never became ready within {seconds}s: {last}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--wait", type=int, default=240, help="seconds to wait for a cold start")
    parser.add_argument("--expect-version", help="wait until /api/health reports this commit, so an old build cannot pass")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    call = client()
    ready = wait_ready(call, base, args.wait, args.expect_version)
    print("ready:", ready)
    status, config = call(base, "/api/auth/config")
    assert status == 200 and config["mode"] == "password", f"expected password sign-in, got {config}"
    for path, marker in (("/", b"ORBIT"), ("/app.js", b"function"), ("/style.css", b"{")):
        status, body = call(base, path)
        assert status == 200 and marker in body, f"static {path} failed"
    print("static files served")
    if not config.get("signup"):
        print("sign-up is off; skipping the account check")
    elif config.get("invite_code"):
        print("sign-up needs an invite code; skipping the account check")
    else:
        name = "ci-smoke-" + uuid4().hex[:8]
        status, session = call(base, "/api/auth/signup", "POST", {"username": name, "password": "Smoke test pw " + uuid4().hex})
        assert status == 200, f"sign-up failed: {status} {session}"
        csrf = session["csrf_token"]
        status, me = call(base, "/api/me")
        assert status == 200 and me["id"] == "u-" + name, f"session not kept: {me}"
        status, made = call(base, "/api/agents/quick-create", "POST", {
            "description": "Write short documents", "name": "Live smoke", "capability_ids": ["write-document"],
            "department_id": "support", "model_profile_id": "demo"}, csrf)
        assert status == 200 and made.get("status") == "created", f"hire failed: {status} {made}"
        agent = made["agent"]["id"]
        status, run = call(base, f"/api/agents/{agent}/runs", "POST", {"task": "Write a one-line note"}, csrf)
        assert status in (200, 201, 202), f"run failed to start: {status} {run}"
        end = time.monotonic() + 60
        while True:
            status, current = call(base, "/api/runs/" + run["id"])
            if current["status"] in ("completed", "failed", "cancelled", "awaiting_approval"):
                break
            assert time.monotonic() < end, "run never finished"
            time.sleep(1)
        assert current["status"] in ("completed", "awaiting_approval"), f"run {current['status']}: {current.get('error')}"
        print(f"signed up {name}, hired an agent, run {current['status']}")
        status, gh = call(base, "/api/integrations/github")
        print("github connector:", gh.get("status") or gh if status == 200 else status)
    print("LIVE SMOKE PASS")


if __name__ == "__main__":
    sys.exit(main())
