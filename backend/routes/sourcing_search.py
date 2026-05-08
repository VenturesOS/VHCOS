"""
Sourcing Search Endpoint — vector search → LTR re-rank → diversify.

Single new endpoint to power the AI-powered candidate search and Advanced
Search pages. Wraps the existing talent_graph semantic search with the
Phase 54 ML re-ranker (`services.sourcing_ml`).

POST /api/sourcing/rerank
{
  "job_id":   "<mandate id>",         # optional — if omitted, uses query only
  "query":    "Senior SAP MM Pune",   # optional — if omitted, uses job_id only
  "top_k":    25,                     # default 25, max 100
  "diversify": true                   # default true (k-Means cluster spread)
}

Response:
{
  "candidates":     [...],
  "total_pool":     <int>,
  "model_loaded":   <bool>,
  "model_meta":     {...},
  "timing_ms": {
    "vector_search": <int>,
    "ltr_rerank":    <int>,
    "diversify":     <int>,
    "total":         <int>
  },
  "memory_mb": {
    "rss_before":    <int>,
    "rss_after":     <int>,
    "delta":         <int>
  }
}
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import db
from services.sourcing_ml import sourcing_ml
from services.talent_graph_service import (
    build_job_text,
    find_candidates_by_text,
)
from utils.auth import get_current_user

logger = logging.getLogger(__name__)
sourcing_router = APIRouter(prefix="/api/sourcing", tags=["Sourcing"])

_PROCESS = psutil.Process()


class RerankRequest(BaseModel):
    job_id: Optional[str] = None
    query: Optional[str] = None
    top_k: int = Field(default=25, ge=1, le=100)
    diversify: bool = True


@sourcing_router.post("/rerank")
async def rerank_candidates(
    req: RerankRequest,
    current_user: dict = Depends(get_current_user),
):
    """ML-powered candidate sourcing for a job.

    Pipeline:
      1. Vector search (BGE cosine via Atlas $vectorSearch) → top 200 pool
      2. XGBoost LTR re-rank using past applications progression signal
      3. (Optional) k-Means cluster diversification → final top_k

    Falls through gracefully if ML bundle is missing — returns vector-only
    rankings (current behaviour) so the endpoint NEVER hard-errors.
    """
    if not req.job_id and not req.query:
        raise HTTPException(
            status_code=400,
            detail="Provide either `job_id` or `query` (or both).",
        )

    rss_before = _PROCESS.memory_info().rss // (1024 * 1024)
    timing = {}
    t0 = time.time()

    # Resolve job document — used by the LTR feature extractor + as
    # fallback query text when only job_id is provided.
    job_doc = {}
    if req.job_id:
        job_doc = await db.jobs.find_one({"id": req.job_id}, {"_id": 0}) or {}

    query_text = req.query or build_job_text(job_doc)
    if not query_text:
        raise HTTPException(
            status_code=400,
            detail="Job has no searchable text and no `query` provided.",
        )

    # ── Stage 1: Vector search (top 200) ──────────────────────────────────
    t = time.time()
    pool = await find_candidates_by_text(db, query_text, limit=200, min_score=0.30)
    timing["vector_search"] = int((time.time() - t) * 1000)

    # ── Stage 2 + 3: LTR re-rank + diversify ──────────────────────────────
    t = time.time()
    ranked = sourcing_ml.rerank(
        job_doc=job_doc,
        pool=pool,
        top_k=req.top_k,
        diversify=req.diversify,
    )
    timing["ltr_and_diversify"] = int((time.time() - t) * 1000)
    timing["total"] = int((time.time() - t0) * 1000)

    rss_after = _PROCESS.memory_info().rss // (1024 * 1024)

    # Log search for analytics + future model retraining (opt-in via stage progression)
    try:
        await db.sourcing_search_logs.insert_one({
            "user_id": current_user.get("id"),
            "user_role": current_user.get("role"),
            "job_id": req.job_id,
            "query": req.query,
            "top_k": req.top_k,
            "diversify": req.diversify,
            "pool_size": len(pool),
            "model_loaded": sourcing_ml.is_loaded,
            "timing_ms": timing,
            "memory_mb_delta": rss_after - rss_before,
            "result_candidate_ids": [
                c.get("candidate_id") or c.get("id") for c in ranked[:25]
            ],
            "created_at": time.time(),
        })
    except Exception as e:
        logger.warning(f"[Sourcing] log write failed (non-fatal): {e}")

    return {
        "candidates": ranked,
        "total_pool": len(pool),
        "model_loaded": sourcing_ml.is_loaded,
        "model_meta": sourcing_ml.meta if sourcing_ml.is_loaded else {},
        "timing_ms": timing,
        "memory_mb": {
            "rss_before": rss_before,
            "rss_after": rss_after,
            "delta": rss_after - rss_before,
        },
    }


@sourcing_router.get("/health")
async def sourcing_health(current_user: dict = Depends(get_current_user)):
    """Live status for the sourcing ML bundle.
    Useful for the Admin dashboard to show 'ML re-ranker: active / not trained'.
    """
    rss_mb = _PROCESS.memory_info().rss // (1024 * 1024)
    cpu = _PROCESS.cpu_percent(interval=0.1)
    return {
        "model_loaded": sourcing_ml.is_loaded,
        "model_meta": sourcing_ml.meta if sourcing_ml.is_loaded else {},
        "process": {
            "rss_mb": rss_mb,
            "cpu_percent": cpu,
        },
    }
