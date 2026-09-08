"""
Admin Monitoring Dashboards.

Endpoints:
- GET /api/admin/runpod/health           — Retired-service compatibility response, no network calls
- POST /api/admin/runpod/sync-now        — Retired-service compatibility response, no network calls
- GET /api/admin/llm/provider-status     — Approved provider configuration
- GET /api/admin/llm/failure-stats       — Approved provider routing breakdown
- GET /api/admin/llm/live-banner         — Compact status for the header red-banner widget
"""
import logging
import os
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
# Retired-service compatibility endpoints (no sync process)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/runpod/health")
async def runpod_health(current_user=Depends(get_current_user)):
    """Return the explicit retired status for older monitoring clients."""
    _require_admin(current_user)
    from services.runpod_sync_service import get_snapshot
    return get_snapshot()


@router.post("/runpod/sync-now")
async def runpod_sync_now(current_user=Depends(get_current_user)):
    """Compatibility no-op: the retired service must never be contacted."""
    _require_admin(current_user)
    from services.runpod_sync_service import manual_sync_now
    return await manual_sync_now()


# ─────────────────────────────────────────────────────────────────────────────
# LLM extraction / fallback dashboard
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

    nvidia_ok = sum(r["count"] for r in by_source if r.get("_id") == "nvidia_nemotron_550b")
    gpt_ok = sum(r["count"] for r in by_source if r.get("_id") == "nvidia_nemotron_super_120b")
    anthropic_fallback = sum(r["count"] for r in by_source if r.get("_id") in ("emergent_haiku_4_5", "claude_haiku_4_5_emergent"))
    regex_only = sum(r["count"] for r in by_source if r.get("_id") == "regex_only")

    return {
        "window_hours": hours,
        "total_extractions": total,
        "by_source": [{"source": r["_id"] or "unknown", "count": r["count"]} for r in by_source],
        "summary": {
            "nvidia_nemotron_pct": round(nvidia_ok / total * 100, 1) if total else 0,
            "nemotron_super_pct": round(gpt_ok / total * 100, 1) if total else 0,
            "anthropic_fallback_pct": round(anthropic_fallback / total * 100, 1) if total else 0,
            "regex_only_pct": round(regex_only / total * 100, 1) if total else 0,
            "anthropic_fallback_count": anthropic_fallback,
        },
        "health_grade": _grade(nvidia_ok + gpt_ok, anthropic_fallback, total),
    }


def _grade(nvidia_ok: int, anthropic: int, total: int) -> str:
    if not total:
        return "unknown"
    nvidia_pct = nvidia_ok / total
    anth_pct = anthropic / total
    if anth_pct > 0.3:
        return "critical"  # >30% on paid fallback
    if anth_pct > 0.1:
        return "warning"  # >10% on paid fallback
    if nvidia_pct >= 0.7 or nvidia_ok == 0:
        return "healthy"
    return "ok"


@router.get("/llm/provider-status")
async def llm_provider_status(current_user=Depends(get_current_user)):
    """Configuration only; deliberately does not contact inference endpoints."""
    _require_admin(current_user)
    nvidia = bool(os.environ.get("NEMOTRON_API_KEY") and os.environ.get("NEMOTRON_BASE_URL"))
    return {"providers": [
        {"id": "nemotron", "name": "NVIDIA Nemotron 550B", "configured": nvidia and bool(os.environ.get("NEMOTRON_MODEL"))},
        {"id": "nemotron_super", "name": "Nemotron Super 120B", "configured": nvidia and bool(os.environ.get("NVIDIA_FALLBACK_MODEL"))},
        {"id": "emergent", "name": "Emergent Claude Haiku 4.5", "configured": bool(os.environ.get("EMERGENT_LLM_KEY"))},
    ]}


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
    # Inspect real recent capture outcomes, not a retired provider's health probe.
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    recent = await db.candidate_bank.find(
        {"created_at": {"$gte": cutoff}},
        {"enrichment_status": 1, "_id": 0},
    ).limit(200).to_list(200)
    total = len(recent)
    failed = sum(1 for r in recent if r.get("enrichment_status") == "failed")
    pending = sum(1 for r in recent if r.get("enrichment_status") == "pending")
    details = {"sampled_captures": total, "failed": failed, "pending": pending, "window_minutes": 10}
    if failed:
        return {"state": "warning", "message": f"{failed}/{total} recent profiles have failed AI enrichment", "details": details}
    if not total:
        return {"state": "unknown", "message": "No captures in the last 10 minutes", "details": details}
    return {
        "state": "healthy",
        "message": f"NVIDIA → Nemotron Super 120B → Emergent; {pending} recent profiles pending",
        "details": details,
    }



# ─────────────────────────────────────────────────────────────────────────────
# Atlas storage — read-only analysis + one-shot prune
# ─────────────────────────────────────────────────────────────────────────────

# Fields safe to strip on already-enriched documents. Kept in sync with
# scripts/atlas_storage_cleanup.py::DISPOSABLE_FIELDS.
_DISPOSABLE_FIELDS = [
    "raw_profile_text",
    "raw_text_for_enrichment",
    "ai_full_text",
    "resume_latex",
    "profile_update_audit",
]
_ENRICHED_FILTER = {"enrichment_status": "enriched"}


@router.get("/atlas/storage-analysis")
async def atlas_storage_analysis(current_user=Depends(get_current_user), db=Depends(get_db)):
    """Return collection storage + reclaimable field counts.

    Read-only. Meant to power the admin UI's storage widget so operators
    know what --prune-raw will actually free without SSHing to prod.
    """
    _require_admin(current_user)
    stats = await db.command("collStats", "candidate_bank")

    reclaimable: dict[str, int] = {}
    for f in _DISPOSABLE_FIELDS:
        reclaimable[f] = await db.candidate_bank.count_documents({
            **_ENRICHED_FILTER,
            f: {"$exists": True, "$ne": None},
        })

    return {
        "count":            stats.get("count", 0),
        "storage_size":     stats.get("storageSize", 0),
        "uncompressed_size": stats.get("size", 0),
        "index_size":       stats.get("totalIndexSize", 0),
        "avg_doc_size":     stats.get("avgObjSize", 0),
        "enriched_docs":    await db.candidate_bank.count_documents(_ENRICHED_FILTER),
        "reclaimable":      reclaimable,
        "disposable_fields": _DISPOSABLE_FIELDS,
    }


@router.post("/atlas/prune-raw-fields")
async def atlas_prune_raw_fields(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    dry_run: bool = True,
):
    """Strip disposable raw/derived text fields on enriched documents.

    Set `dry_run=false` (query param) to actually apply. Defaults to true
    so a stray curl doesn't torch data. Only touches docs where
    `enrichment_status == 'enriched'` — pending / all_failed / None docs
    keep their raw text so retries can still work.
    """
    _require_admin(current_user)

    reclaimable: dict[str, int] = {}
    for f in _DISPOSABLE_FIELDS:
        reclaimable[f] = await db.candidate_bank.count_documents({
            **_ENRICHED_FILTER,
            f: {"$exists": True, "$ne": None},
        })

    if dry_run:
        return {
            "dry_run": True,
            "would_prune": reclaimable,
            "total_field_removals": sum(reclaimable.values()),
        }

    results: dict[str, dict] = {}
    for f in _DISPOSABLE_FIELDS:
        if reclaimable[f] == 0:
            results[f] = {"matched": 0, "modified": 0, "skipped": True}
            continue
        res = await db.candidate_bank.update_many(
            {**_ENRICHED_FILTER, f: {"$exists": True}},
            {"$unset": {f: ""}},
        )
        results[f] = {"matched": res.matched_count, "modified": res.modified_count}

    return {
        "dry_run": False,
        "results": results,
        "note": "Atlas M0 does not expose `compact`; storageSize drops lazily via WiredTiger.",
    }
