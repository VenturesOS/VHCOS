"""
Admin Monitoring Dashboards.

Endpoints:
- GET /api/admin/runpod/health           — Live RunPod + vLLM health (auto-sync snapshot)
- POST /api/admin/runpod/sync-now        — Force a manual sync cycle
- GET /api/admin/llm/failure-stats       — Qwen JSON decode failure rate + fallback chain breakdown
- GET /api/admin/llm/live-banner         — Compact status for the header red-banner widget
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pymongo import DESCENDING

from utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin Monitoring"])

ADMIN_EMAIL = "admin@vhc.in"


def _require_admin(user: dict):
    if not user:
        raise HTTPException(401, "Not authenticated")
    if (user.get("role") or "").lower() != "admin":
        raise HTTPException(403, "Admin access required")


async def get_db():
    from config import db
    return db


# ─────────────────────────────────────────────────────────────────────────────
# RunPod auto-sync
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/runpod/health")
async def runpod_health(current_user=Depends(get_current_user)):
    """Return the auto-sync daemon's latest snapshot of the pod + vLLM state."""
    _require_admin(current_user)
    from services.runpod_sync_service import get_snapshot
    return get_snapshot()


@router.post("/runpod/sync-now")
async def runpod_sync_now(current_user=Depends(get_current_user)):
    """Force an immediate poll of the RunPod API (bypasses the 2-min cadence)."""
    _require_admin(current_user)
    from services.runpod_sync_service import manual_sync_now
    return await manual_sync_now()


# ─────────────────────────────────────────────────────────────────────────────
# Qwen JSON failure / LLM fallback dashboard
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/llm/failure-stats")
async def llm_failure_stats(
    hours: int = 24,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Breakdown of which LLM layer handled captures in the last N hours.

    Uses `extraction_traces` (admin debug trace) which records `llm_source` per call.
    """
    _require_admin(current_user)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$llm_source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_source = await db.extraction_traces.aggregate(pipeline).to_list(100)
    total = sum(r["count"] for r in by_source) or 0

    # Interesting buckets
    runpod_ok = sum(r["count"] for r in by_source if r.get("_id") in ("runpod_qwen14b", "runpod_qwen14b_retry"))
    qwen_retry = sum(r["count"] for r in by_source if r.get("_id") == "runpod_qwen14b_retry")
    anthropic_fallback = sum(r["count"] for r in by_source if (r.get("_id") or "").startswith("anthropic"))
    regex_only = sum(r["count"] for r in by_source if r.get("_id") == "regex_only")

    return {
        "window_hours": hours,
        "total_extractions": total,
        "by_source": [{"source": r["_id"] or "unknown", "count": r["count"]} for r in by_source],
        "summary": {
            "runpod_qwen14b_pct": round(runpod_ok / total * 100, 1) if total else 0,
            "anthropic_fallback_pct": round(anthropic_fallback / total * 100, 1) if total else 0,
            "regex_only_pct": round(regex_only / total * 100, 1) if total else 0,
            "qwen_retry_rescues": qwen_retry,
            "anthropic_fallback_count": anthropic_fallback,
        },
        "health_grade": _grade(runpod_ok, anthropic_fallback, total),
    }


def _grade(runpod_ok: int, anthropic: int, total: int) -> str:
    if not total:
        return "unknown"
    runpod_pct = runpod_ok / total
    anth_pct = anthropic / total
    if anth_pct > 0.3:
        return "critical"  # >30% on paid fallback
    if anth_pct > 0.1:
        return "warning"  # >10% on paid fallback
    if runpod_pct >= 0.7 or runpod_ok == 0:
        return "healthy"
    return "ok"


@router.get("/llm/live-banner")
async def llm_live_banner(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Compact status for the admin header red-banner widget.

    Returns {state: 'healthy'|'warning'|'critical', message: '...', details: {...}}
    Designed to be cheap — cached in the frontend for 60s.
    """
    _require_admin(current_user)
    from services.runpod_sync_service import get_snapshot
    snap = get_snapshot()

    # Quick look at last 10 min of traces
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    recent = await db.extraction_traces.find(
        {"created_at": {"$gte": cutoff}},
        {"llm_source": 1, "_id": 0},
    ).limit(200).to_list(200)
    total = len(recent)
    anth = sum(1 for r in recent if (r.get("llm_source") or "").startswith("anthropic"))
    anth_pct = (anth / total * 100) if total else 0

    # Decision tree
    if not snap.get("runpod_url"):
        return {"state": "warning", "message": "RunPod URL not configured", "details": snap}
    if not snap.get("vllm_reachable"):
        return {
            "state": "critical",
            "message": f"RunPod unreachable — captures falling back to Anthropic",
            "details": snap,
        }
    if anth_pct > 30:
        return {
            "state": "critical",
            "message": f"{anth}/{total} last-10-min captures used paid Anthropic fallback",
            "details": {**snap, "anthropic_pct_10min": round(anth_pct, 1)},
        }
    if anth_pct > 10:
        return {
            "state": "warning",
            "message": f"{round(anth_pct, 1)}% Anthropic fallback in last 10 min",
            "details": {**snap, "anthropic_pct_10min": round(anth_pct, 1)},
        }
    return {
        "state": "healthy",
        "message": "Qwen 14B primary, all systems green",
        "details": snap,
    }
