"""
VHC Talent OS — Main Application Entry Point

Thin entry: create the FastAPI app, wire lifespan / middleware / routers,
that's it. Everything else lives in `bootstrap/`, `routes/`, `services/`.

Split from the original 517-line server.py on 2026-08 (Phase 55.12).
"""
import logging

from fastapi import FastAPI

# Boot-time barrel validation — importing these triggers every model /
# util / service module to be parsed. If any downstream file has a
# top-level import error we want the server to fail LOUDLY at boot, not
# silently later when a route is hit.
import models  # noqa: F401
import utils  # noqa: F401
import services  # noqa: F401

from bootstrap.lifespan import lifespan
from bootstrap.middleware import register_middleware, register_exception_handler
from bootstrap.routers import all_routers, route_import_failures


# ── Logging (configure BEFORE app creation so lifespan logs are formatted) ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ── App ──
app = FastAPI(title="VHC Talent OS API", lifespan=lifespan)


# ── Routers ──
for _router in all_routers:
    if _router is not None:
        app.include_router(_router)

if route_import_failures:
    logger.error(f"[STARTUP] {len(route_import_failures)} route(s) failed to import:")
    for _failure in route_import_failures:
        logger.error(f"  - {_failure}")


# ── Middleware + CORS + security headers + global exception handler ──
register_middleware(app)
register_exception_handler(app)
