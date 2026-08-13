"""FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import airports, health, reference, search, trends
from app.config import settings
from app.db.base import dispose_engine, init_models
from app.providers.registry import close_provider, get_provider
from app.services.events import event_bus
from app.services.search_service import SearchFailed

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
# These emit a line per SQL statement at DEBUG and drown out everything else.
for noisy in ("aiosqlite", "asyncio", "httpcore", "httpx"):
    logging.getLogger(noisy).setLevel(logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_models()
    provider = get_provider()
    logger.info(
        "%s ready | provider=%s database=%s web=%s",
        settings.app_name,
        provider.name,
        "postgresql" if settings.is_postgres else "sqlite",
        "compiled" if HAS_COMPILED_WEB else "preview-only",
    )
    if provider.name == "mock":
        logger.warning(
            "Running on SYNTHETIC flight data. For live fares run "
            "'python scripts/setup_provider.py duffel' (or amadeus)."
        )
    try:
        yield
    finally:
        await event_bus.aclose()
        await close_provider()
        await dispose_engine()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Multi-segment price-anomaly detection. Finds itineraries A->C that stop "
        "at your real destination B and cost less than flying A->B directly."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SearchFailed)
async def _search_failed_handler(request: Request, exc: SearchFailed) -> JSONResponse:
    """A run that could not produce a comparison is a gateway problem, not a bug."""
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc), "type": "search_failed"},
    )


for module in (health, airports, reference, search, trends):
    app.include_router(module.router, prefix=settings.api_prefix)


# ---------------------------------------------------------------- frontends --
# Two UIs, in priority order:
#
#   /         the compiled React app, when it has been built into static/web
#             (the Docker image does this). Falls back to the preview UI so a
#             source checkout still serves something useful at the root.
#   /preview  the zero-build UI, always available. It needs no Node toolchain,
#             which is what makes the backend demonstrable on its own.
WEB_DIR = STATIC_DIR / "web"
HAS_COMPILED_WEB = (WEB_DIR / "index.html").is_file()

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/preview", include_in_schema=False)
    async def preview_ui() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

if HAS_COMPILED_WEB:
    # Hashed asset filenames, so they are safe to cache aggressively.
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def web_ui() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

elif STATIC_DIR.is_dir():

    @app.get("/", include_in_schema=False)
    async def root_ui() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")
