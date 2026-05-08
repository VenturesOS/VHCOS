"""
Admin-only Extraction Trace Endpoint.

Purpose: Capture a structured audit trail for every AI extraction (regex input,
regex output, LLM source, final merged profile) so admins can pinpoint why a
specific capture leaked data without guessing or asking the user for raw payloads.

Writes go to `extraction_traces` collection (capped via TTL index, 72 hrs).
Reads are restricted to admin@vhc.in.
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, Any
from pymongo import DESCENDING

from utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug/extraction-trace", tags=["Extraction Trace (Admin)"])

# Role gate — only admin@vhc.in has access to avoid leaking raw resume content.
ADMIN_EMAIL = "admin@vhc.in"


async def get_db():
    from config import db
    return db


def _is_authorized_admin(user: dict) -> bool:
    if not user:
        return False
    email = (user.get("email") or "").lower().strip()
    role = (user.get("role") or "").lower().strip()
    if role != "admin":
        return False
    # Config-driven allow-list so additional admins can be granted read access
    # without code changes. Defaults to ADMIN_EMAIL for backward compat.
    import os as _os
    allowed = _os.environ.get("DEBUG_TRACE_ADMINS", ADMIN_EMAIL)
    allow_list = {e.strip().lower() for e in allowed.split(",") if e.strip()}
    return email in allow_list


@router.get("")
async def list_traces(
    limit: int = Query(25, ge=1, le=200),
    candidate_name: Optional[str] = Query(None, description="Filter by candidate name (substring match)"),
    source: Optional[str] = Query(None, description="Filter by endpoint: ai-extract | capture | re-enrich"),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return the last N extraction traces with the regex+LLM output side-by-side.
    Admin-only (admin@vhc.in). Use this to diagnose data-leakage issues.
    """
    if not _is_authorized_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")

    query: Dict[str, Any] = {}
    if candidate_name:
        query["candidate_name"] = {"$regex": candidate_name, "$options": "i"}
    if source:
        query["endpoint"] = source

    docs = await db.extraction_traces.find(query, {"_id": 0}).sort(
        "created_at", DESCENDING
    ).limit(limit).to_list(limit)

    return {
        "count": len(docs),
        "filter": {"candidate_name": candidate_name, "source": source},
        "traces": docs,
    }


@router.get("/{trace_id}")
async def get_trace(
    trace_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Fetch full trace (including raw_text) by id. Admin-only."""
    if not _is_authorized_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    doc = await db.extraction_traces.find_one({"id": trace_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Trace not found")
    return doc


@router.delete("/{trace_id}")
async def delete_trace(
    trace_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a single trace. Admin-only."""
    if not _is_authorized_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    r = await db.extraction_traces.delete_one({"id": trace_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"deleted": True}


@router.post("/_ensure-ttl")
async def ensure_ttl_index(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create TTL index on created_at (72 h) so traces auto-expire. Admin-only.
    Safe to call repeatedly — idempotent.
    """
    if not _is_authorized_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    await db.extraction_traces.create_index("created_at", expireAfterSeconds=72 * 3600)
    return {"index": "created_at TTL 72h ensured"}


# ─────────────────────────────────────────────────────────────────────────────
# Helper used by extension.py to write trace rows. Kept here so callers import
# a single module; failures are swallowed (this endpoint is purely diagnostic).
# ─────────────────────────────────────────────────────────────────────────────
import uuid  # noqa: E402


async def record_trace_async(
    db,
    endpoint: str,
    candidate_name: Optional[str],
    raw_text: str,
    regex_output: Optional[dict],
    llm_output: Optional[dict],
    merged_output: Optional[dict],
    llm_source: Optional[str] = None,
    user_email: Optional[str] = None,
):
    """Persist a single extraction trace. Safe to call from any async context;
    errors are logged and swallowed.
    """
    try:
        trace = {
            "id": str(uuid.uuid4()),
            "endpoint": endpoint,
            "candidate_name": candidate_name,
            "user_email": user_email,
            "raw_text_length": len(raw_text or ""),
            "raw_text_head": (raw_text or "")[:4000],
            "regex_output": _compact(regex_output),
            "llm_output": _compact(llm_output),
            "llm_source": llm_source,
            "merged_output": _compact(merged_output),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.extraction_traces.insert_one(trace)
    except Exception as e:
        logger.warning(f"[Trace] Failed to record: {e}")


def _compact(d: Optional[dict]) -> Optional[dict]:
    """Pick only the diagnostic keys to keep trace docs small."""
    if not isinstance(d, dict):
        return d
    keep = (
        "candidate_name", "name", "candidate_email", "email", "candidate_phone", "phone",
        "experience_years", "total_experience_years",
        "current_ctc", "current_salary", "expected_ctc", "expected_salary",
        "notice_period", "notice_period_days",
        "location", "current_employer", "current_company",
        "current_designation", "headline",
        "_extraction_source", "_exp_source", "source", "_fallback_chain",
    )
    out = {k: d.get(k) for k in keep if k in d}
    # Also show counts for list-shaped fields
    for k in ("key_skills", "work_experience", "education"):
        v = d.get(k)
        if isinstance(v, list):
            out[f"{k}_count"] = len(v)
    return out


def record_trace_sync(
    endpoint: str,
    candidate_name: Optional[str],
    raw_text: str,
    regex_output: Optional[dict],
    llm_output: Optional[dict],
    merged_output: Optional[dict],
    llm_source: Optional[str] = None,
    user_email: Optional[str] = None,
):
    """Synchronous variant for background-task callers that lack an event loop.
    Uses pymongo MongoClient from config (same pattern as _apply_bg_enrichment).
    """
    try:
        from pymongo import MongoClient
        from config import mongodb_uri as _mongo_uri, db_name as _db_name
        client = MongoClient(_mongo_uri, tlsAllowInvalidCertificates=True)
        try:
            client[_db_name].extraction_traces.insert_one({
                "id": str(uuid.uuid4()),
                "endpoint": endpoint,
                "candidate_name": candidate_name,
                "user_email": user_email,
                "raw_text_length": len(raw_text or ""),
                "raw_text_head": (raw_text or "")[:4000],
                "regex_output": _compact(regex_output),
                "llm_output": _compact(llm_output),
                "llm_source": llm_source,
                "merged_output": _compact(merged_output),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        finally:
            client.close()
    except Exception as e:
        logger.warning(f"[Trace-Sync] Failed to record: {e}")
