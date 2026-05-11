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


# ─────────────────────────────────────────────────────────────────────
# DEBUG / Audit endpoint — admin only, helps diagnose missing data
# ─────────────────────────────────────────────────────────────────────
@digest_router.get("/daily-digest/_audit/today")
async def audit_today(
    current_user: dict = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """One-shot audit of today's raw data — used to debug why the
    digest shows 0 captures / wrong counts."""
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from services.team_digest_service import IST_OFFSET, _ist_day_bounds_utc, _ist_now

    ist = _ist_now()
    start_utc, end_utc = _ist_day_bounds_utc(ist)
    week_ago = (_dt.now(_tz.utc) - _td(days=7)).isoformat()

    out: Dict[str, Any] = {
        "ist_today": ist.strftime("%Y-%m-%d %H:%M"),
        "utc_window": [start_utc, end_utc],
    }

    # A) Source values last 7d
    out["sources_7d"] = []
    async for r in db.candidate_bank.aggregate([
        {"$match": {"created_at": {"$gte": week_ago}}},
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]):
        out["sources_7d"].append({"source": r["_id"], "count": r["count"]})

    # B) Today by source
    out["sources_today"] = []
    out["total_today"] = 0
    async for r in db.candidate_bank.aggregate([
        {"$match": {"created_at": {"$gte": start_utc, "$lte": end_utc}}},
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]):
        out["sources_today"].append({"source": r["_id"], "count": r["count"]})
        out["total_today"] += r["count"]

    # C) 5 sample docs
    out["samples"] = []
    async for s in db.candidate_bank.find(
        {"created_at": {"$gte": start_utc, "$lte": end_utc}},
        {"_id": 0, "source": 1, "captured_by": 1, "created_by": 1, "source_details": 1, "mandate_id": 1},
    ).limit(5):
        sd = s.get("source_details") or {}
        out["samples"].append({
            "source": s.get("source"),
            "captured_by": s.get("captured_by"),
            "created_by": s.get("created_by"),
            "sd_captured_by": sd.get("captured_by"),
            "sd_source": sd.get("source"),
            "mandate_id": s.get("mandate_id") or sd.get("mandate_id"),
        })

    # D) Top 10 users who added candidates today (by best-effort user field)
    uid_to_name: Dict[str, str] = {}
    async for u in db.users.find({}, {"_id": 0, "id": 1, "name": 1}):
        uid_to_name[u["id"]] = u.get("name") or "(unnamed)"
    out["top_adders"] = []
    async for r in db.candidate_bank.aggregate([
        {"$match": {"created_at": {"$gte": start_utc, "$lte": end_utc}}},
        {"$addFields": {"_uid": {"$ifNull": [
            "$source_details.captured_by",
            {"$ifNull": ["$captured_by", "$created_by"]},
        ]}}},
        {"$group": {
            "_id": "$_uid",
            "count": {"$sum": 1},
            "sources": {"$addToSet": "$source"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]):
        out["top_adders"].append({
            "user_id": r["_id"],
            "name": uid_to_name.get(r["_id"], "(unknown)"),
            "count": r["count"],
            "sources": r["sources"],
        })

    # E) Today's tracker_events stages
    out["stages_today"] = []
    async for r in db.tracker_events.aggregate([
        {"$match": {"timestamp": {"$gte": start_utc, "$lte": end_utc}}},
        {"$group": {"_id": "$new_stage", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]):
        out["stages_today"].append({"stage": r["_id"], "count": r["count"]})

    # F) Bhumika's pipeline today
    bhumika = await db.users.find_one(
        {"name": {"$regex": "Bhumika", "$options": "i"}}, {"_id": 0, "id": 1, "name": 1},
    )
    out["bhumika_events"] = []
    if bhumika:
        out["bhumika"] = {"id": bhumika["id"], "name": bhumika.get("name")}
        async for ev in db.tracker_events.find(
            {"user_id": bhumika["id"], "timestamp": {"$gte": start_utc, "$lte": end_utc}},
            {"_id": 0, "new_stage": 1, "previous_stage": 1, "timestamp": 1, "mandate_id": 1},
        ):
            out["bhumika_events"].append(ev)

    return out
