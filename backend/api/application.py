"""FastAPI lifecycle, transport policy, errors, static workbench and API docs."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
import secrets
import time
import json
from uuid import uuid4
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException
from starlette.concurrency import run_in_threadpool
from ..app import Application
from ..auth import Authentication, COOKIE, SESSION_SECONDS
from ..contracts import Error
from . import registry, recruiter, runtime, reviews, workqueue
from .schemas import ErrorResponse, Input
from pydantic import Field, ConfigDict
from typing import Annotated

ROOT = Path(__file__).resolve().parents[2]
SECURITY = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"


def error_response(status, code, message, details=None):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


class LocalTransportPolicy:
    """Check local Host/Origin and bound request size before parsing JSON."""

    def __init__(self, app, settings=None):
        self.app = app
        self.settings = settings or {}
        self.windows = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.monotonic()
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope["headers"]
        }

        async def secure_send(message):
            if message["type"] == "http.response.start":
                values = list(message.get("headers", []))
                existing = {k.lower() for k, v in values}
                for key, value in [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"content-security-policy", SECURITY.encode()),
                    (b"referrer-policy", b"same-origin"),
                    (
                        b"permissions-policy",
                        b"camera=(), microphone=(), geolocation=()",
                    ),
                ]:
                    if key not in existing:
                        values.append((key, value))
                values.append((b"x-request-id", request_id.encode()))
                if self.settings.get("APP_ENV") == "production":
                    values.append((b"strict-transport-security", b"max-age=31536000"))
                if self.settings.get("APP_ENV") == "production":
                    logging.getLogger("backend.requests").info(
                        json.dumps(
                            {
                                "request_id": request_id,
                                "method": scope["method"],
                                "path": scope["path"],
                                "status": message["status"],
                                "duration_ms": round(
                                    (time.monotonic() - started) * 1000
                                ),
                            }
                        )
                    )
                message = {**message, "headers": values}
            await send(message)

        async def reject(status, code, message):
            await error_response(status, code, message)(scope, receive, secure_send)

        window = int(time.monotonic() // 60)
        client = scope.get("client") or ("unknown", 0)
        old = self.windows.get(client[0], (window, 0))
        count = old[1] if old[0] == window else 0
        if count >= int(self.settings.get("REQUESTS_PER_MINUTE", 1800)):
            return await reject(
                429, "rate_limited", "Request limit reached. Try again shortly."
            )
        self.windows = {k: v for k, v in self.windows.items() if v[0] == window}
        self.windows[client[0]] = (window, count + 1)
        host = headers.get("host", "")
        try:
            address = urlsplit("http://" + host)
            valid = (
                address.hostname in {"localhost", "127.0.0.1"}
                and address.username is None
                and address.password is None
                and address.path == ""
            )
            port = address.port
        except ValueError:
            valid = False
            port = None
        origin = self.settings.get("APP_ORIGIN", "").rstrip("/")
        production = self.settings.get("APP_ENV") == "production"
        if production:
            valid = bool(origin) and host == urlsplit(origin).netloc
        if not valid:
            return await reject(403, "forbidden_origin", "Untrusted Host.")
        suffix = ":" + str(port) if port is not None else ""
        origins = (
            {origin}
            if production
            else {"http://localhost" + suffix, "http://127.0.0.1" + suffix}
        )
        if headers.get("origin") and headers["origin"] not in origins:
            return await reject(403, "forbidden_origin", "Cross-origin request denied.")
        if scope["method"] in {"POST", "PATCH", "PUT"}:
            if (
                headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                return await reject(
                    415, "invalid_request", "JSON content type required."
                )
            try:
                n = int(headers.get("content-length", "0"))
            except ValueError:
                return await reject(400, "invalid_request", "Invalid Content-Length.")
            if n < 0 or n > 50000:
                return await reject(
                    413, "invalid_request", "Request body exceeds 50000 bytes."
                )
            body = b""
            while True:
                chunk = await receive()
                if chunk["type"] == "http.disconnect":
                    return
                body += chunk.get("body", b"")
                if len(body) > 50000:
                    return await reject(
                        413, "invalid_request", "Request body exceeds 50000 bytes."
                    )
                if not chunk.get("more_body", False):
                    break
            delivered = False
            original_receive = receive

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await original_receive()

            receive = buffered_receive
        await self.app(scope, receive, secure_send)


def create_app(
    service: Application | None = None,
    settings: dict | None = None,
    *,
    start_worker=True,
) -> FastAPI:
    settings = dict(settings or (service.config if service else {}))
    if service is not None:
        service.config.update(settings)
    if settings.get("APP_ENV") == "production":
        logger = logging.getLogger("backend.requests")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    @asynccontextmanager
    async def lifespan(api):
        owned = service is None
        current = service or await run_in_threadpool(
            Application,
            settings.get("DATABASE_PATH", str(ROOT / "data" / "workforce.sqlite3")),
            settings,
        )
        api.state.service = current
        try:
            api.state.auth = Authentication(current)
            api.state.worker_required = start_worker
            if start_worker:
                await run_in_threadpool(current.runtime.launch)
            yield
        finally:
            if hasattr(api.state, "auth"):
                api.state.auth.close()
                del api.state.auth
            if owned:
                await run_in_threadpool(current.close)
            elif start_worker:
                await run_in_threadpool(current.runtime.close)
            del api.state.service

    errors = {
        status: {"model": ErrorResponse, "description": description}
        for status, description in {
            400: "Invalid operation or state input",
            401: "Authentication required or expired",
            429: "Login, request, or work queue limit reached",
            503: "Application not ready",
            403: "Permission or local transport denied",
            404: "Resource not found",
            409: "Version, state, or replay conflict",
            413: "Request too large",
            415: "JSON content type required",
            422: "Request validation failed",
            502: "Provider or MCP failure",
        }.items()
    }
    api = FastAPI(
        title="Hire an Agent API",
        version="0.3.0",
        description="Role-scoped agent jobs with validated deliverables, manager approvals and audit traces. Authentication mode: "
        + settings.get("AUTH_MODE", "development")
        + ". Development impersonation must remain local. Live provider credentials stay backend-only.",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        responses=errors,
    )
    api.add_middleware(
        LocalTransportPolicy, settings=settings or (service.config if service else {})
    )

    @api.exception_handler(Error)
    async def platform_error(request: Request, exc: Error):
        return error_response(
            exc.status,
            exc.code,
            str(exc),
            {**exc.details, "request_id": getattr(request.state, "request_id", None)},
        )

    @api.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Never echo body/input values (which could contain credentials) in errors.
        issues = [
            {
                "location": list(item["loc"]),
                "type": item["type"],
                "message": item["msg"],
            }
            for item in exc.errors()
        ]
        return error_response(
            422, "validation_error", "Request validation failed.", {"issues": issues}
        )

    @api.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(exc.status_code, "http_error", str(exc.detail))

    @api.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger(__name__).error(
            "Unhandled HTTP exception: %s", type(exc).__name__
        )
        return error_response(
            500, "internal_error", "Unexpected server error. Check local server logs."
        )

    for router in [
        registry.router,
        recruiter.router,
        runtime.router,
        reviews.router,
        workqueue.router,
    ]:
        api.include_router(router)

    @api.get("/api/auth/config", tags=["Authentication"])
    def auth_config(request: Request) -> dict:
        return request.app.state.auth.config()

    class Login(Input):
        model_config = ConfigDict(
            extra="forbid", strict=True, str_strip_whitespace=False
        )
        username: Annotated[str, Field(min_length=1, max_length=100)]
        password: Annotated[str, Field(min_length=1, max_length=256)]

    @api.post("/api/auth/login", tags=["Authentication"])
    def login(body: Login, request: Request):
        token, result = request.app.state.auth.login(
            body.username,
            body.password,
            request.client.host if request.client else "unknown",
        )
        response = JSONResponse(result)
        response.set_cookie(
            request.app.state.auth.cookie_name,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=request.app.state.auth.production,
            samesite="strict",
            path=request.app.state.auth.cookie_path,
        )
        return response

    @api.get("/api/auth/session", tags=["Authentication"])
    def session(request: Request):
        actor, token, current = request.app.state.auth.session(request)
        return {
            "user": actor,
            "csrf_token": request.app.state.auth.csrf(token),
            "expires_at": current["expires_at"],
        }

    @api.post("/api/auth/logout", tags=["Authentication"])
    def logout(body: dict, request: Request):
        request.app.state.auth.logout(request)
        response = JSONResponse({"signed_out": True})
        response.delete_cookie(
            request.app.state.auth.cookie_name,
            path=request.app.state.auth.cookie_path,
            secure=request.app.state.auth.production,
            httponly=True,
            samesite="strict",
        )
        return response

    @api.get("/api/ready", tags=["Health"])
    def ready(request: Request):
        current = request.app.state.service
        try:
            with current.db.transaction() as connection:
                connection.execute("SELECT 1").fetchone()
            worker_ok = not request.app.state.worker_required or bool(
                current.runtime.thread
                and current.runtime.thread.is_alive()
                and not current.runtime.stop_event.is_set()
            )
            return JSONResponse(
                {
                    "ready": worker_ok,
                    "database": "ok",
                    "worker": "ok" if worker_ok else "unavailable",
                    "authentication": request.app.state.auth.mode,
                },
                status_code=200 if worker_ok else 503,
            )
        except Exception:
            return JSONResponse({"ready": False}, status_code=503)

    @api.get("/api/health", tags=["Health"])
    def health() -> dict:
        return {"status": "ok", "transport": "fastapi"}

    @api.get("/docs", include_in_schema=False)
    def swagger_docs():
        nonce = secrets.token_urlsafe(24)
        page = get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="Hire an Agent — API docs",
            swagger_favicon_url="data:,",
            swagger_ui_parameters={"validatorUrl": None},
        )
        html = page.body.decode().replace("<script>", f'<script nonce="{nonce}">')
        # Only documentation needs the Swagger CDN and its nonce-protected initializer.
        policy = f"default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}'; style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return HTMLResponse(html, headers={"Content-Security-Policy": policy})

    @api.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "static" / "index.html", media_type="text/html")

    @api.get("/app.js", include_in_schema=False)
    def javascript():
        return FileResponse(ROOT / "static" / "app.js", media_type="text/javascript")

    @api.get("/style.css", include_in_schema=False)
    def stylesheet():
        return FileResponse(ROOT / "static" / "style.css", media_type="text/css")

    FONTS = {"unbounded.woff2", "hanken-grotesk.woff2"}

    @api.get("/fonts/{name}", include_in_schema=False)
    def font(name: str):
        # Self-hosted OFL fonts; whitelisted names only.
        if name not in FONTS:
            return JSONResponse(
                {
                    "error": {
                        "code": "not_found",
                        "message": "Not found.",
                        "details": {},
                    }
                },
                status_code=404,
            )
        return FileResponse(ROOT / "static" / "fonts" / name, media_type="font/woff2")

    return api
