"""Admin endpoint to view + reset the BGE sidecar circuit breaker.

  GET  /api/admin/embed-breaker          → breaker state + sidecar health
  POST /api/admin/embed-breaker/reset    → force CLOSED state (use after
                                            verifying the sidecar is actually
                                            back up — skips the 5-min wait)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from services.embed_client import breaker_state, health_check, reset_breaker
from utils.auth import get_current_user

embed_admin_router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    role = (user or {}).get("role") or ""
    if role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


@embed_admin_router.get("/embed-breaker")
async def get_embed_breaker(_user: dict = Depends(_require_admin)):
    """Snapshot of the BGE sidecar circuit breaker + live health probe."""
    return {
        "breaker": breaker_state(),
        "sidecar_health": health_check(),
    }


@embed_admin_router.post("/embed-breaker/reset")
async def post_reset_embed_breaker(_user: dict = Depends(_require_admin)):
    """Manually force the breaker back to CLOSED state.
    Use after restarting the sidecar so you don't wait for the 5-min cooldown."""
    reset_breaker()
    return {"ok": True, "breaker": breaker_state()}
