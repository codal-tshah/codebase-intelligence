"""FastAPI app: middleware (request id, API key, gzip, CORS), error shapes and router wiring.

Routes live in ``ci_api.routers`` (system, projects, graph, chat); this module only assembles
them. URLs are unchanged from earlier versions.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from ci_api import __version__
from ci_api.autorefresh import run_forever as auto_refresh_loop
from ci_api.routers import chat, graph, projects, system
from ci_core.db import GraphStore
from ci_core.logging_setup import configure_logging, request_id
from ci_core.registry import load_registry
from ci_core.settings import get_settings

_settings = get_settings()  # fails fast on invalid configuration (e.g. CI_MODE=server without a key)
configure_logging(_settings.log_level, _settings.log_json)
log = logging.getLogger("ci_api")


def _reconcile_orphaned_index_jobs() -> None:
    n = 0
    for p in load_registry():
        n += GraphStore(p.id).fail_orphaned_running_jobs()
    if n:
        log.warning("marked %d orphaned index job(s) as failed on startup", n)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _reconcile_orphaned_index_jobs()
    task = asyncio.create_task(auto_refresh_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Codebase Intelligence API", version=__version__, lifespan=_lifespan)

# Local-first: only the dev UI origins by default. Extend with CI_CORS_ORIGINS="https://a,https://b".
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

# Graph payloads repeat 64-char node ids in every edge; gzip cuts them ~8x. SSE (chat) is excluded
# by Starlette's default, so streamed answers are not buffered.
app.add_middleware(GZipMiddleware, minimum_size=2048)


@app.middleware("http")
async def request_context(request, call_next):
    """Correlation id on every request/response and, in server mode, API-key authentication."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id.set(rid)
    try:
        settings = get_settings()
        # Under `ci serve --ui` the API is mounted at /api, so the path arrives as /api/health.
        path = request.url.path.removeprefix(request.scope.get("root_path", "") or "")
        if settings.mode == "server" and request.method != "OPTIONS" and path not in ("/health", "/api/health"):
            supplied = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not settings.api_key or not hmac.compare_digest(supplied, settings.api_key):
                return JSONResponse({"detail": "invalid or missing API key", "request_id": rid}, status_code=401, headers={"X-Request-ID": rid})
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    except Exception:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "internal error", "request_id": rid}, status_code=500, headers={"X-Request-ID": rid})
    finally:
        request_id.reset(token)


# One error shape everywhere: {"detail": <string or validation list>, "request_id": "..."}.
@app.exception_handler(HTTPException)
async def _http_error(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail, "request_id": request_id.get()}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{k: v for k, v in e.items() if k in ("loc", "msg", "type")} for e in exc.errors()]
    return JSONResponse({"detail": errors, "request_id": request_id.get()}, status_code=422)


# Order matters: `{project_ref:path}` is greedy, so fixed paths (/projects/resolve, /projects/overview)
# are registered before the per-project routes, and the graph routes after the project routes.
app.include_router(system.router)
app.include_router(projects.router)
app.include_router(graph.router)
app.include_router(chat.router)


def create_app(ui_dir: Path | None = None) -> FastAPI:
    """The API app; with `ui_dir`, a combined app serving the dashboard at / and the API at /api."""
    if ui_dir is None:
        return app
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    # Starlette doesn't run a mounted sub-app's lifespan, so the combined app runs it itself.
    root = FastAPI(title="Codebase Intelligence", version=app.version, lifespan=_lifespan)
    root.mount("/api", app)
    ui_dir = ui_dir.resolve()
    if (ui_dir / "assets").is_dir():
        root.mount("/assets", StaticFiles(directory=ui_dir / "assets"), name="assets")

    @root.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (ui_dir / path).resolve()
        if path and candidate.is_file() and ui_dir in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(ui_dir / "index.html")  # client-side routes (deep links)

    return root
