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
app = create_app(settings=settings)

if __name__ == "__main__":
    import uvicorn

    port = int(settings.get("PORT", "8000"))
    print(
        f"Hire an Agent: http://localhost:{port} · Swagger: http://localhost:{port}/docs",
        flush=True,
    )
    print("Local development identities only; fictional support sandbox.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, workers=1)
