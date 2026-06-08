"""
Talent Graph API — semantic candidate operations.

Routes:
  • GET  /api/talent-graph/similar/{candidate_id}  — find similar candidates
  • POST /api/talent-graph/search                  — free-form semantic search
  • GET  /api/talent-graph/match-job/{job_id}      — candidates matching a job
  • POST /api/talent-graph/refresh/{candidate_id}  — regenerate summary + embedding
  • GET  /api/talent-graph/summary/{candidate_id}  — fetch the cached summary
  • GET  /api/talent-graph/stats                   — admin: index health
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user, require_role
from services.talent_graph_service import (
    EMBEDDINGS_COLL,
    find_candidates_by_text,
    find_matching_candidates_for_job,
    find_similar_candidates,
    upsert_candidate_embedding,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/talent-graph", tags=["Talent Graph"])


async def get_db():
    from config import db
    return db


# ──────────────────────────────────────────────────────────────────────────────
# Read endpoints — available to recruiters + admins
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/similar/{candidate_id}")
async def similar_candidates(
    candidate_id: str,
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Top-K candidates whose profile vector is closest to the seed candidate."""
    role = (user.get("role") or "").lower()
    if role not in ("admin", "recruiter", "employer"):
        raise HTTPException(403, "Talent Graph requires recruiter/admin role")

    results = await find_similar_candidates(db, candidate_id, limit=limit)
    return {"seed": candidate_id, "matches": results, "count": len(results)}


class SemanticSearchPayload(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    limit: int = Field(20, ge=1, le=100)
    min_score: Optional[float] = Field(0.40, ge=0.0, le=1.0)


@router.post("/search")
async def semantic_search(
    payload: SemanticSearchPayload,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Free-form semantic search across the candidate bank."""
    role = (user.get("role") or "").lower()
    if role not in ("admin", "recruiter", "employer"):
        raise HTTPException(403, "Talent Graph requires recruiter/admin role")

    results = await find_candidates_by_text(
        db, payload.query, limit=payload.limit, min_score=payload.min_score or 0.40,
        routing_key=f"{user.get('id') or ''}|{payload.query}",
    )
    # Detect which rerank arm actually ran (set per-row by the service)
    rerank_source = (results[0].get("match_type") if results else None) or "unknown"
    # ── LTR Phase 1 telemetry (fire-and-forget) ───────────────────────
    # Capture the slate so future actions on these results (click /
    # shortlist / contact) can be tied back to (query, rank) labels.
    session_id = None
    try:
        from services.ltr_telemetry import log_slate
        session_id = await log_slate(
            user=user,
            source="talent_graph_search",
            query=payload.query,
            slate=results,
            query_meta={
                "limit": payload.limit,
                "min_score": payload.min_score,
                "rerank_source": rerank_source,
            },
        )
    except Exception:
        pass  # telemetry must never break search
    return {
        "query": payload.query,
        "matches": results,
        "count": len(results),
        "ltr_session_id": session_id,  # frontend round-trips this with actions
        "rerank_source": rerank_source,
    }


@router.get("/match-job/{job_id}")
async def match_job(
    job_id: str,
    limit: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Candidates ranked by semantic match to a job's requirements."""
    role = (user.get("role") or "").lower()
    if role not in ("admin", "recruiter", "employer"):
        raise HTTPException(403, "Talent Graph requires recruiter/admin role")

    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    matches = await find_matching_candidates_for_job(db, job, limit=limit)
    return {
        "job_id": job_id,
        "job_title": job.get("title") or job.get("job_title"),
        "matches": matches,
        "count": len(matches),
    }


@router.get("/summary/{candidate_id}")
async def get_summary(
    candidate_id: str,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Return the cached AI summary for a candidate. If missing, returns 404 —
    caller can hit POST /refresh/{id} to generate it on demand."""
    role = (user.get("role") or "").lower()
    if role not in ("admin", "recruiter", "employer"):
        raise HTTPException(403, "Talent Graph requires recruiter/admin role")
    doc = await db[EMBEDDINGS_COLL].find_one(
        {"candidate_id": candidate_id},
        {"_id": 0, "summary": 1, "updated_at": 1, "embedding_model": 1},
    )
    if not doc:
        raise HTTPException(404, "No summary indexed yet")
    return doc


# ──────────────────────────────────────────────────────────────────────────────
# Write endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/refresh/{candidate_id}")
async def refresh_candidate(
    candidate_id: str,
    force: bool = Query(False, description="Re-embed even if text unchanged"),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Regenerate the embedding + summary for a single candidate."""
    role = (user.get("role") or "").lower()
    if role not in ("admin", "recruiter", "employer"):
        raise HTTPException(403, "Talent Graph requires recruiter/admin role")

    doc = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, f"Candidate {candidate_id} not found")

    result = await upsert_candidate_embedding(db, doc, force=force)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Admin diagnostics
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def talent_graph_stats(
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """How many candidates have an embedding, model in use, last update."""
    total_candidates = await db.candidate_bank.count_documents({})
    indexed = await db[EMBEDDINGS_COLL].count_documents({})
    coverage = round((indexed / total_candidates) * 100, 2) if total_candidates else 0.0

    latest = await db[EMBEDDINGS_COLL].find_one(
        {}, {"_id": 0, "updated_at": 1, "embedding_model": 1}, sort=[("updated_at", -1)]
    )
    has_summary = await db[EMBEDDINGS_COLL].count_documents({"summary": {"$exists": True, "$ne": None}})

    return {
        "total_candidates": total_candidates,
        "indexed": indexed,
        "with_summary": has_summary,
        "coverage_pct": coverage,
        "embedding_model": (latest or {}).get("embedding_model"),
        "last_indexed_at": (latest or {}).get("updated_at"),
    }
