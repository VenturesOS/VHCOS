"""
VHC Talent OS — Candidate Clustering MVP (Phase 56)

Reads `candidate_embeddings` → reduces 384-dim BGE vectors to 32 dims via PCA
→ partitions into K clusters with k-Means → labels each cluster from its
most-frequent skills/titles → writes back:
  • `candidate_embeddings.cluster_id` (int)
  • `candidate_clusters` (one doc per cluster: centroid, size, label, samples)

Run manually:
    cd /home/ubuntu/vhc-platform/backend && \
      venv/bin/python -m scripts.cluster_candidates --k 25

Run via background scheduler (added in services/scheduler.py).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cluster_candidates")

DEFAULT_K = 25
DEFAULT_PCA_DIM = 32
EMBEDDINGS_COLL = "candidate_embeddings"
CLUSTERS_COLL = "candidate_clusters"


def _norm(s: Any) -> str:
    return (str(s) if s is not None else "").strip().lower()


def _label_from_samples(samples: List[Dict[str, Any]]) -> str:
    """Best-effort label using top skills + top designation."""
    skills = Counter()
    desigs = Counter()
    for s in samples:
        for sk in (s.get("skills") or []):
            t = _norm(sk)
            if t and len(t) > 1:
                skills[t] += 1
        d = _norm(s.get("designation") or s.get("current_designation"))
        if d:
            desigs[d] += 1

    top_skill = (skills.most_common(1) or [(None, 0)])[0][0]
    top_desig = (desigs.most_common(1) or [(None, 0)])[0][0]

    if top_desig and top_skill:
        return f"{top_desig.title()} · {top_skill}"
    if top_desig:
        return top_desig.title()
    if top_skill:
        return top_skill
    return "Mixed"


async def _load_embeddings(db, limit: Optional[int]) -> tuple[np.ndarray, List[str]]:
    cursor = db[EMBEDDINGS_COLL].find(
        {"embedding": {"$exists": True, "$ne": None}},
        {"_id": 0, "candidate_id": 1, "embedding": 1},
    )
    if limit:
        cursor = cursor.limit(limit)

    ids: List[str] = []
    vecs: List[List[float]] = []
    async for d in cursor:
        emb = d.get("embedding")
        if not emb or not isinstance(emb, list):
            continue
        ids.append(d["candidate_id"])
        vecs.append(emb)

    if not vecs:
        return np.zeros((0, 0)), []
    return np.asarray(vecs, dtype=np.float32), ids


async def _enrich_samples(db, cand_ids: List[str]) -> List[Dict[str, Any]]:
    if not cand_ids:
        return []
    cursor = db.candidate_bank.find(
        {"id": {"$in": cand_ids}},
        {"_id": 0, "id": 1, "name": 1, "designation": 1,
         "current_designation": 1, "skills": 1, "current_employer": 1},
    )
    return [d async for d in cursor]


async def cluster_candidates(
    *, k: int = DEFAULT_K, pca_dim: int = DEFAULT_PCA_DIM, limit: Optional[int] = None
) -> Dict[str, Any]:
    # Heavy ML imports inside the function to keep server.py import-time cheap.
    from sklearn.decomposition import PCA
    from sklearn.cluster import MiniBatchKMeans

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "vhc_talent_os")
    if not mongo_url:
        raise RuntimeError("MONGO_URL not set")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    t0 = datetime.now(timezone.utc)
    X, ids = await _load_embeddings(db, limit)
    if X.size == 0:
        logger.warning("No embeddings found — abort.")
        return {"status": "empty", "n": 0}

    logger.info(f"Loaded {X.shape[0]} embeddings, dim={X.shape[1]}")

    # Don't over-cluster if we have few candidates
    k_eff = max(2, min(k, max(2, X.shape[0] // 20)))

    # PCA down to a manageable dimension (384 → 32 typically)
    pca_dim_eff = min(pca_dim, X.shape[1], X.shape[0])
    pca = PCA(n_components=pca_dim_eff, random_state=42)
    Xp = pca.fit_transform(X)
    var_explained = float(pca.explained_variance_ratio_.sum())
    logger.info(f"PCA done: {X.shape[1]}→{pca_dim_eff}, variance retained={var_explained:.2%}")

    # MiniBatchKMeans — fast, handles large N
    km = MiniBatchKMeans(
        n_clusters=k_eff, random_state=42, batch_size=1024, n_init=5, max_iter=100
    )
    labels = km.fit_predict(Xp)
    logger.info(f"k-Means done: {k_eff} clusters, inertia={km.inertia_:.0f}")

    # Persist cluster_id on each embedding doc (bulk update)
    bulk_ops: List[Dict[str, Any]] = []
    for cid, lbl in zip(ids, labels):
        bulk_ops.append(
            {
                "filter": {"candidate_id": cid},
                "update": {"$set": {"cluster_id": int(lbl)}},
            }
        )
    # Apply via raw motor operations in small batches to avoid huge writes
    BATCH = 500
    updated = 0
    for i in range(0, len(bulk_ops), BATCH):
        chunk = bulk_ops[i : i + BATCH]
        from pymongo import UpdateOne
        ops = [UpdateOne(o["filter"], o["update"]) for o in chunk]
        if ops:
            res = await db[EMBEDDINGS_COLL].bulk_write(ops, ordered=False)
            updated += res.modified_count or 0
    logger.info(f"Tagged {updated} embeddings with cluster_id")

    # Build cluster docs (centroid + size + label + sample candidates)
    await db[CLUSTERS_COLL].delete_many({})
    cluster_docs: List[Dict[str, Any]] = []
    for cluster_idx in range(k_eff):
        member_ids = [cid for cid, lbl in zip(ids, labels) if lbl == cluster_idx]
        if not member_ids:
            continue
        # Pick up to 30 samples for label inference
        sample_cand_ids = member_ids[:30]
        samples = await _enrich_samples(db, sample_cand_ids)
        label = _label_from_samples(samples)
        cluster_docs.append(
            {
                "cluster_id": cluster_idx,
                "label": label,
                "size": len(member_ids),
                "sample_candidates": [
                    {
                        "id": s.get("id"),
                        "name": s.get("name"),
                        "designation": s.get("designation") or s.get("current_designation"),
                        "current_employer": s.get("current_employer"),
                    }
                    for s in samples[:8]
                ],
                "updated_at": datetime.now(timezone.utc),
            }
        )
    if cluster_docs:
        await db[CLUSTERS_COLL].insert_many(cluster_docs)
    await db[CLUSTERS_COLL].create_index("cluster_id", unique=True)

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    summary = {
        "status": "ok",
        "n": int(X.shape[0]),
        "k": k_eff,
        "pca_dim": pca_dim_eff,
        "variance_retained": var_explained,
        "elapsed_sec": elapsed,
        "updated_embeddings": updated,
        "cluster_count": len(cluster_docs),
    }
    logger.info(f"DONE in {elapsed:.1f}s: {summary}")
    client.close()
    return summary


def _parse():
    p = argparse.ArgumentParser(description="VHC candidate clustering")
    p.add_argument("--k", type=int, default=DEFAULT_K, help="target k for k-means")
    p.add_argument("--pca-dim", type=int, default=DEFAULT_PCA_DIM, help="PCA dim")
    p.add_argument("--limit", type=int, default=None, help="max embeddings to load")
    return p.parse_args()


def main():
    args = _parse()
    # ensure dotenv on standalone run
    try:
        from dotenv import load_dotenv
        load_dotenv("/home/ubuntu/vhc-platform/backend/.env", override=False)
        load_dotenv(".env", override=False)
    except Exception:
        pass
    result = asyncio.run(
        cluster_candidates(k=args.k, pca_dim=args.pca_dim, limit=args.limit)
    )
    print(result)
    sys.exit(0 if result.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
