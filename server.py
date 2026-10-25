"""FastAPI/Uvicorn entry point. See README for local setup and deployment limits."""

import os
from pathlib import Path
from backend.api.application import create_app

ROOT = Path(__file__).resolve().parent


def config():
    settings = dict(os.environ)
    file = ROOT / ".env"
    if file.exists():
        for line in file.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                settings.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return settings


settings = config()
# Render and similar hosts publish the public URL themselves; production mode needs it as the trusted origin.
if not settings.get("APP_ORIGIN") and settings.get("RENDER_EXTERNAL_URL"):
    settings["APP_ORIGIN"] = settings["RENDER_EXTERNAL_URL"]
if settings.get("RENDER") and not settings.get("APP_ENV"):
    settings["APP_ENV"] = "production"
if settings.get("APP_ENV") == "production":
    settings.setdefault("AUTH_MODE", "password")
    from backend import bootstrap

    print("Bootstrap:", bootstrap.run(settings, settings.get("DATABASE_PATH", str(ROOT / "data" / "workforce.sqlite3"))), flush=True)
app = create_app(settings=settings)

if __name__ == "__main__":
    import uvicorn

    port = int(settings.get("PORT", "8000"))
    print(
        f"Hire an Agent: http://localhost:{port} · Swagger: http://localhost:{port}/docs",
        flush=True,
    )
    print(
        "Authentication: "
        + settings.get("AUTH_MODE", "development")
        + " · Local workspace",
        flush=True,
    )
    # Behind a host's proxy every request arrives from the proxy; trust X-Forwarded-For so per-client limits work.
    behind_proxy = bool(settings.get("TRUST_PROXY") or settings.get("RENDER"))
    uvicorn.run(
        app,
        host=settings.get("HOST", "0.0.0.0" if behind_proxy else "127.0.0.1"),
        port=port,
        workers=1,
        proxy_headers=behind_proxy,
        forwarded_allow_ips="*" if behind_proxy else None,
    )
