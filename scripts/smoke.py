"""Boot the real server on a throwaway database and exercise every offline tool through the API.

    python scripts/smoke.py

Uses the offline demo model, so it needs no API keys and is safe in CI. Exits non-zero on any failure.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
import json
import urllib.request
from uuid import uuid4
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read()


def api(base, path, method="GET", body=None):
    request = urllib.request.Request(
        base + "/api/" + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json", "X-Dev-User": "pavan", "Idempotency-Key": str(uuid4())},
    )
    with urllib.request.urlopen(request, timeout=15) as r:
        return json.load(r)


def exercise_every_tool(base):
    """Hire one agent per offline capability and give it a task. A tool or integration added to the
    catalog is picked up automatically; network-only ones (web, GitHub) are covered by mocked tests."""
    ran = 0
    for cap in api(base, "capabilities"):
        if any(t == "read_url" or t.startswith("github_") for t in cap["tools"]):
            continue
        agent = api(base, "agents/quick-create", "POST", {
            "capability_ids": [cap["id"]], "name": "Smoke " + cap["id"], "model_profile_id": "demo"})["agent"]
        run = api(base, f"agents/{agent['id']}/runs", "POST", {"task": "Please do your job: " + cap["name"]})
        end = time.monotonic() + 30
        while True:
            current = api(base, "runs/" + run["id"])
            if current["status"] in ("completed", "failed", "cancelled", "awaiting_approval"):
                break
            if time.monotonic() > end:
                raise SystemExit(f"{cap['id']}: run never finished")
            time.sleep(0.3)
        if current["status"] not in ("completed", "awaiting_approval"):
            raise SystemExit(f"{cap['id']}: run {current['status']}: {current.get('error')}")
        print(f"  {cap['id']}: {current['status']}")
        ran += 1
    assert ran, "no capabilities exercised"


def main():
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **os.environ,
            "PORT": str(port),
            "APP_ENV": "development",
            "AUTH_MODE": "development",
            "DATABASE_PATH": str(Path(tmp) / "smoke.sqlite3"),
            "DEMO_BASE_URL": base,
        }
        for key in ("APP_ORIGIN", "GEMINI_API_KEY", "OPENAI_API_KEY"):
            env.pop(key, None)
        log = open(Path(tmp) / "server.log", "w+")
        server = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while True:
                if server.poll() is not None:
                    raise SystemExit("server exited early:\n" + Path(log.name).read_text())
                try:
                    if get(base + "/api/ready")[0] == 200:
                        break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise SystemExit("server never became ready:\n" + Path(log.name).read_text())
                time.sleep(0.3)
            print("ready")
            for path, marker in (("/", b"ORBIT"), ("/app.js", b"function"), ("/style.css", b"{")):
                status, body = get(base + path)
                assert status == 200 and marker in body, f"static {path} failed"
            print("static files served")
            exercise_every_tool(base)
            print("SMOKE PASS")
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    main()
