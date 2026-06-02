"""
LTR Admin endpoints — Phase 56.5 (Jun 2026)

Powers the LTR data-accumulation dashboard tile + receives action
events from the frontend (when user clicks/shortlists/etc on a search
result, the UI calls /api/ltr/action with the session_id from the
preceding search).

Public endpoints
----------------
  POST /api/ltr/action          → record a user interaction with a slate
  GET  /api/admin/ltr/stats     → admin: see accumulation progress
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import db
from utils.auth import get_current_user, require_role
from services.ltr_telemetry import log_action

logger = logging.getLogger(__name__)

ltr_router = APIRouter(prefix="/api/ltr", tags=["LTR Telemetry"])
ltr_admin_router = APIRouter(prefix="/api/admin/ltr", tags=["LTR Admin"])


_ALLOWED_ACTIONS = {
    "click_profile",
    "shortlist",
    "contact",
    "add_to_pipeline",
    "reject",
    "download_resume",
    "send_message",
    "dismiss",
}


class ActionPayload(BaseModel):
    session_id: str
    candidate_id: str
    action: str
    rank: Optional[int] = None


@ltr_router.post("/action")
async def record_action(
    payload: ActionPayload,
    user: dict = Depends(get_current_user),
):
    """Frontend posts here when a recruiter interacts with a search result.
    Fire-and-forget on the client side — failures must not block the UX,
    so we always return 200 except for hard validation errors."""
    if payload.action not in _ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action must be one of {sorted(_ALLOWED_ACTIONS)}",
        )
    ok = await log_action(
        session_id=payload.session_id,
        candidate_id=payload.candidate_id,
        action=payload.action,
        rank=payload.rank,
    )
    return {"ok": ok}


@ltr_admin_router.get("/stats")
async def ltr_stats(
    days: int = 30,
    user: dict = Depends(require_role(["admin"])),
):
    """Roll-up for the admin dashboard. Tells you whether enough data has
    accumulated to attempt LTR training (target: ≥5,000 labeled triplets
    per scoping doc)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline: List[dict] = [
        {"$match": {"ts": {"$gte": since}}},
        {"$facet": {
            "totals": [
                {"$group": {
                    "_id": None,
                    "n_sessions": {"$sum": 1},
                    "n_impressions": {"$sum": {"$size": "$slate"}},
                    "n_actions": {"$sum": {"$size": "$actions"}},
                }},
            ],
            "by_source": [
                {"$group": {"_id": "$source", "n": {"$sum": 1}}},
                {"$sort": {"n": -1}},
            ],
            "by_action": [
                {"$unwind": "$actions"},
                {"$group": {"_id": "$actions.action", "n": {"$sum": 1}}},
                {"$sort": {"n": -1}},
            ],
            "sessions_with_actions": [
                {"$match": {"$expr": {"$gt": [{"$size": "$actions"}, 0]}}},
                {"$count": "n"},
            ],
        }},
    ]
    agg = await db.search_sessions.aggregate(pipeline).to_list(1)
    if not agg:
        return {
            "days": days,
            "n_sessions": 0, "n_impressions": 0, "n_actions": 0,
            "by_source": [], "by_action": [],
            "sessions_with_actions": 0,
            "ready_for_training": False,
            "progress_pct": 0,
        }
    a = agg[0]
    totals = (a["totals"] or [{}])[0] if a.get("totals") else {}
    n_imp = totals.get("n_impressions", 0)
    n_act = totals.get("n_actions", 0)
    n_sess_with_act = (a["sessions_with_actions"] or [{}])[0].get("n", 0)
    # Heuristic — "positive triplet" ≈ a sessions_with_actions * avg actions
    # Rough lower bound on training-eligible positives.
    triplet_estimate = n_act
    progress = min(100, int(100 * triplet_estimate / 5000))
    return {
        "days": days,
        "n_sessions": totals.get("n_sessions", 0),
        "n_impressions": n_imp,
        "n_actions": n_act,
        "by_source": a.get("by_source") or [],
        "by_action": a.get("by_action") or [],
        "sessions_with_actions": n_sess_with_act,
        "triplet_estimate": triplet_estimate,
        "ready_for_training": triplet_estimate >= 5000,
        "progress_pct": progress,
        "target_triplets": 5000,
    }
