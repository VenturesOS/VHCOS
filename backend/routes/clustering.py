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
