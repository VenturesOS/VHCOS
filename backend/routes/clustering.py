"""
VHC Talent OS — Clustering API (Phase 56)

Endpoints to browse candidate clusters produced by scripts/cluster_candidates.py

  GET  /api/clustering/clusters                          → all clusters with size + label + samples
  GET  /api/clustering/clusters/{cluster_id}/candidates  → candidates in one cluster (paginated)
  POST /api/clustering/run                               → admin: trigger re-clustering (async)

The heavy ML work happens in scripts/cluster_candidates.py — this module only
serves the cached results.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from config import db
from utils.auth import require_role

logger = logging.getLogger(__name__)

clustering_router = APIRouter(prefix="/api/clustering", tags=["Clustering"])


@clustering_router.get("/clusters")
async def list_clusters(
    current_user: dict = Depends(require_role(["admin", "account_manager"])),
):
    cursor = db.candidate_clusters.find({}, {"_id": 0}).sort("size", -1)
    clusters: List[Dict[str, Any]] = []
    async for c in cursor:
        if isinstance(c.get("updated_at"), datetime):
            c["updated_at"] = c["updated_at"].isoformat()
        clusters.append(c)
    return {"clusters": clusters, "count": len(clusters)}


@clustering_router.get("/clusters/{cluster_id}/candidates")
async def cluster_candidates(
    cluster_id: int,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    current_user: dict = Depends(require_role(["admin", "account_manager"])),
):
    # Find candidate_ids in this cluster
    emb_cursor = db.candidate_embeddings.find(
        {"cluster_id": cluster_id},
        {"_id": 0, "candidate_id": 1},
    ).skip(skip).limit(limit)
    ids = [d["candidate_id"] async for d in emb_cursor]
    if not ids:
        return {"cluster_id": cluster_id, "candidates": [], "count": 0}

    cands_cursor = db.candidate_bank.find(
        {"id": {"$in": ids}},
        {
            "_id": 0, "id": 1, "name": 1, "designation": 1,
            "current_designation": 1, "current_employer": 1,
            "total_experience": 1, "current_location": 1, "skills": 1,
        },
    )
    candidates = [c async for c in cands_cursor]
    return {"cluster_id": cluster_id, "candidates": candidates, "count": len(candidates)}


def _run_clustering_blocking(k: int, pca_dim: int):
    """Wrapper that runs the async clusterer in its own event loop.
    Lives in a background task so the request thread returns immediately."""
    from scripts.cluster_candidates import cluster_candidates as _do_cluster
    try:
        result = asyncio.run(_do_cluster(k=k, pca_dim=pca_dim))
        logger.warning(f"[Clustering] Re-cluster done: {result}")
    except Exception as e:
        logger.exception(f"[Clustering] Re-cluster failed: {e}")


@clustering_router.post("/run")
async def trigger_clustering(
    background_tasks: BackgroundTasks,
    k: int = Query(25, ge=2, le=100),
    pca_dim: int = Query(32, ge=4, le=128),
    current_user: dict = Depends(require_role(["admin"])),
):
    # Track that a run was kicked off, so we can debounce repeated clicks
    await db.candidate_clusters_meta.update_one(
        {"_id": "last_run"},
        {"$set": {
            "kicked_at": datetime.now(timezone.utc),
            "by": current_user.get("email"),
            "k": k, "pca_dim": pca_dim,
        }},
        upsert=True,
    )
    background_tasks.add_task(_run_clustering_blocking, k, pca_dim)
    return {"ok": True, "started": True, "k": k, "pca_dim": pca_dim}


@clustering_router.get("/status")
async def clustering_status(
    current_user: dict = Depends(require_role(["admin", "account_manager"])),
):
    meta = await db.candidate_clusters_meta.find_one({"_id": "last_run"}, {"_id": 0})
    cluster_count = await db.candidate_clusters.count_documents({})
    embedded_count = await db.candidate_embeddings.count_documents({"cluster_id": {"$exists": True}})
    if meta and isinstance(meta.get("kicked_at"), datetime):
        meta["kicked_at"] = meta["kicked_at"].isoformat()
    return {
        "last_run": meta or None,
        "cluster_count": cluster_count,
        "embeddings_tagged": embedded_count,
    }


# ── Find more candidates like this (Phase 56.4, June 2026) ───────────
# Given a seed candidate, return the N most similar candidates by:
#   1. Look up the seed's `cluster_id` from `candidate_embeddings`
#   2. Pull all other members of that cluster (capped at 500 for speed)
#   3. Rank them by cosine similarity of their embedding to the seed's
#   4. Return the top N with key fields for display

def _cosine(a: List[float], b: List[float]) -> float:
    """Tiny pure-Python cosine. Vectors are already L2-normalised by the
    BGE sidecar (normalize_embeddings=True), so this is just dot product."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


@clustering_router.get("/similar/{candidate_id}")
async def similar_candidates(
    candidate_id: str,
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(require_role(["admin", "account_manager", "recruiter"])),
):
    """Return the top-N candidates most similar to the given seed candidate.
    Uses the cluster as a fast pre-filter (skip 99% of the DB), then ranks
    cluster members by cosine of their BGE embedding to the seed's.

    If the seed has no embedding or cluster yet → returns empty.
    """
    # 1. Get seed embedding + cluster_id
    seed = await db.candidate_embeddings.find_one(
        {"candidate_id": candidate_id},
        {"_id": 0, "embedding": 1, "cluster_id": 1},
    )
    if not seed or not seed.get("embedding") or seed.get("cluster_id") is None:
        return {"seed_id": candidate_id, "similar": [], "reason": "no embedding or cluster"}

    seed_vec: List[float] = seed["embedding"]
    cluster_id = seed["cluster_id"]

    # 2. Pull cluster members (cap at 500 — bigger clusters get random sample)
    cluster_size = await db.candidate_embeddings.count_documents({"cluster_id": cluster_id})
    if cluster_size > 500:
        # Random subset — sample stage in aggregation
        pipeline: List[Dict[str, Any]] = [
            {"$match": {"cluster_id": cluster_id, "candidate_id": {"$ne": candidate_id}}},
            {"$sample": {"size": 500}},
            {"$project": {"_id": 0, "candidate_id": 1, "embedding": 1}},
        ]
        members = await db.candidate_embeddings.aggregate(pipeline).to_list(500)
    else:
        cursor = db.candidate_embeddings.find(
            {"cluster_id": cluster_id, "candidate_id": {"$ne": candidate_id}},
            {"_id": 0, "candidate_id": 1, "embedding": 1},
        )
        members = await cursor.to_list(500)

    # 3. Score by cosine similarity
    scored: List[tuple[str, float]] = []
    for m in members:
        emb = m.get("embedding")
        if not emb:
            continue
        scored.append((m["candidate_id"], _cosine(seed_vec, emb)))
    scored.sort(key=lambda x: x[1], reverse=True)
    top_ids = [cid for cid, _ in scored[:limit]]
    if not top_ids:
        return {"seed_id": candidate_id, "similar": []}

    # 4. Fetch display fields for the top-N
    cands_cursor = db.candidate_bank.find(
        {"id": {"$in": top_ids}},
        {
            "_id": 0, "id": 1, "name": 1, "designation": 1, "current_designation": 1,
            "current_employer": 1, "current_location": 1, "location": 1,
            "total_experience": 1, "experience_years": 1, "annual_ctc": 1,
            "skills": 1,
        },
    )
    cand_by_id = {c["id"]: c async for c in cands_cursor}

    # Stitch in same order as scored list, attach similarity score
    similar: List[Dict[str, Any]] = []
    for cid, score in scored[:limit]:
        c = cand_by_id.get(cid)
        if not c:
            continue
        c["similarity"] = round(float(score), 4)
        similar.append(c)

    return {
        "seed_id": candidate_id,
        "cluster_id": cluster_id,
        "cluster_size": cluster_size,
        "scanned": len(members),
        "similar": similar,
    }
