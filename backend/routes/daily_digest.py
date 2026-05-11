"""
Admin Daily Team Digest API — Phase 54.15

Endpoints:
  GET  /api/admin/daily-digest               → today's stored digest
  GET  /api/admin/daily-digest/{date}        → digest for a specific YYYY-MM-DD
  POST /api/admin/daily-digest/regenerate    → recompute today live
  POST /api/admin/daily-digest/{date}/regenerate → recompute any IST date

All restricted to role=admin.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from config import db
from utils import require_role
from services.team_digest_service import (
    IST_OFFSET,
    build_daily_digest,
    get_stored_digest,
    store_digest,
)

logger = logging.getLogger(__name__)
digest_router = APIRouter(prefix="/api/admin", tags=["Daily Team Digest"])


def _parse_ist_date(date_str: str) -> datetime:
    """Parse 'YYYY-MM-DD' into a midnight-IST naive datetime."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid date '{date_str}'. Use YYYY-MM-DD."
        )


def _today_ist_str() -> str:
    return (datetime.now(timezone.utc) + IST_OFFSET).strftime("%Y-%m-%d")


@digest_router.get("/daily-digest")
async def get_today_digest(
    current_user: dict = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Return today's (IST) stored digest. If not generated yet, builds + stores it."""
    today = _today_ist_str()
    stored = await get_stored_digest(db, today)
    if stored:
        return stored
    # Lazy generation
    digest = await build_daily_digest(db)
    await store_digest(db, digest)
    return digest


@digest_router.get("/daily-digest/recent")
async def list_recent_digests(
    days: int = 7,
    current_user: dict = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """List the last N days of digests (lightweight summary only)."""
    days = max(1, min(days, 30))
    cursor = (
        db.daily_team_digests
        .find({}, {"_id": 0, "date": 1, "pretty_date": 1, "weekday": 1,
                   "recruiter_count": 1, "top_overall": 1, "generated_at": 1})
        .sort("date", -1)
        .limit(days)
    )
    items = await cursor.to_list(length=days)
    # Trim top_overall to just names+scores to keep response light
    for it in items:
        it["top_overall"] = [
            {"name": t.get("name"), "activity_score": t.get("activity_score")}
            for t in (it.get("top_overall") or [])
        ]
    return {"items": items, "count": len(items)}


@digest_router.get("/daily-digest/{date_str}")
async def get_digest_by_date(
    date_str: str,
    current_user: dict = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    _parse_ist_date(date_str)
    stored = await get_stored_digest(db, date_str)
    if not stored:
        raise HTTPException(
            status_code=404, detail=f"No digest stored for {date_str}. "
            f"Use /regenerate to compute it on the fly."
        )
    return stored


@digest_router.post("/daily-digest/regenerate")
async def regenerate_today(
    current_user: dict = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Force-recompute today's digest now (does not wait for 18:00 IST cron)."""
    digest = await build_daily_digest(db)
    await store_digest(db, digest)
    return digest


@digest_router.post("/daily-digest/{date_str}/regenerate")
async def regenerate_for_date(
    date_str: str,
    current_user: dict = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Recompute for any IST date (backfill / debugging)."""
    target_ist = _parse_ist_date(date_str)
    digest = await build_daily_digest(db, target_ist)
    await store_digest(db, digest)
    return digest
