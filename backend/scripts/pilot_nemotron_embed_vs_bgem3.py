"""
Pilot: nemotron-3-embed-1b (NVIDIA NIM, 2048-dim) vs BAAI/bge-m3 (RunPod, 1024-dim)

Objective:
  Decide whether to migrate embeddings from RunPod BGE-M3 to NVIDIA Nemotron-Embed-1b
  (free tier, kills RunPod serverless embed cost). Migration is GO only if the two
  models rank candidate similarity ~equivalently — measured as top-K neighbour
  overlap on the same query set.

Method:
  1. Sample N candidates (default 100) that already have BGE-M3 embeddings in
     Mongo (`embeddings.bgem3.vector` and `embedding_model="bge-m3"`).
  2. Regenerate their prepared_text using the same `EmbeddingService._prepare_candidate_text`
     used by the live indexer.
  3. Generate a Nemotron-Embed-1b vector for each of the 100 candidates.
  4. For each candidate:
        • Compute cosine similarity vs all other 99 candidates in BGE-M3 space
        • Compute cosine similarity vs all other 99 candidates in Nemotron space
        • Take top-20 nearest neighbours in each space
        • Compute Jaccard overlap of the two top-20 sets
  5. Report:
        • mean_overlap, median_overlap
        • top1_match_rate (same closest neighbour in both spaces)
        • top5_match_rate
        • Recommend MIGRATE if mean_overlap ≥ 0.95, HOLD otherwise.

Run:
  cd /app/backend && python -m scripts.pilot_nemotron_embed_vs_bgem3 --sample 100

Notes:
  • Read-only against production Mongo. Writes nothing except a report file
    at /tmp/nemotron_embed_pilot_<ts>.json for later review.
  • Uses NEMOTRON_API_KEY + NEMOTRON_BASE_URL (same NVIDIA NIM account as LLMs).
"""
import os
import sys
import json
import time
import asyncio
import argparse
import logging
import statistics
from datetime import datetime, timezone
from typing import List, Dict, Tuple

# Add backend root to sys.path so this script runs both as `python -m scripts.xxx`
# and as `python scripts/xxx.py`.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_HERE)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_BACKEND_ROOT, ".env"))

from motor.motor_asyncio import AsyncIOMotorClient
from openai import AsyncOpenAI
import numpy as np

from services.embeddings import EmbeddingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("embed_pilot")

NEMOTRON_EMBED_MODEL = os.environ.get("NEMOTRON_EMBED_MODEL", "nvidia/nemotron-3-embed-1b")


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def top_k_indices(query: np.ndarray, matrix: np.ndarray, self_idx: int, k: int) -> List[int]:
    """Return indices of top-k rows in `matrix` most similar to `query`, excluding self_idx."""
    # Normalise once for fast cosine via dot product
    m_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-12)
    q_norm = query / (np.linalg.norm(query) + 1e-12)
    sims = m_norm @ q_norm
    sims[self_idx] = -np.inf
    return list(np.argsort(-sims)[:k])


async def fetch_sample(db, sample_size: int) -> List[Dict]:
    """Fetch candidates that have BGE-M3 embeddings already stored."""
    query = {
        "embedding_model": "bge-m3",
        "embeddings.bgem3.vector": {"$exists": True, "$ne": []},
    }
    # Project just what we need — full docs used by _prepare_candidate_text
    cursor = db.candidate_bank.find(query).limit(sample_size)
    docs = []
    async for d in cursor:
        docs.append(d)
    logger.info(f"[Pilot] Fetched {len(docs)} candidates with BGE-M3 embeddings")
    return docs


async def generate_nemotron_embeddings(texts: List[str]) -> List[List[float]]:
    """Batch-generate Nemotron embeddings. NVIDIA NIM /embeddings accepts a list."""
    client = AsyncOpenAI(
        api_key=os.environ["NEMOTRON_API_KEY"],
        base_url=os.environ.get("NEMOTRON_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    )
    # NIM has per-request token/list-size limits — chunk into 8s to be safe.
    out: List[List[float]] = []
    chunk = 8
    for i in range(0, len(texts), chunk):
        batch = texts[i:i + chunk]
        try:
            r = await client.embeddings.create(model=NEMOTRON_EMBED_MODEL, input=batch)
            # OpenAI SDK preserves index ordering
            for item in sorted(r.data, key=lambda x: x.index):
                out.append(item.embedding)
        except Exception as e:
            logger.error(f"[Pilot] Nemotron batch {i}..{i+len(batch)} failed: {e}")
            # pad with zeros so downstream indexing lines up
            out.extend([[0.0] * 2048] * len(batch))
        # gentle pacing to stay under 40 rpm free tier
        await asyncio.sleep(0.4)
    return out


def compare_rankings(bge_matrix: np.ndarray, nemo_matrix: np.ndarray, k: int = 20) -> Dict:
    n = bge_matrix.shape[0]
    overlaps: List[float] = []
    top1_match = 0
    top5_match = 0
    per_candidate: List[Dict] = []

    for i in range(n):
        bge_top = set(top_k_indices(bge_matrix[i], bge_matrix, i, k))
        nem_top = set(top_k_indices(nemo_matrix[i], nemo_matrix, i, k))
        overlap = len(bge_top & nem_top) / k
        overlaps.append(overlap)

        bge_top_ord = top_k_indices(bge_matrix[i], bge_matrix, i, k)
        nem_top_ord = top_k_indices(nemo_matrix[i], nemo_matrix, i, k)
        if bge_top_ord[0] == nem_top_ord[0]:
            top1_match += 1
        if bge_top_ord[0] in nem_top_ord[:5]:
            top5_match += 1

        per_candidate.append({
            "idx": i,
            "overlap": overlap,
            "bge_top1": bge_top_ord[0],
            "nem_top1": nem_top_ord[0],
        })

    return {
        "sample_size": n,
        "top_k": k,
        "mean_overlap": statistics.mean(overlaps),
        "median_overlap": statistics.median(overlaps),
        "min_overlap": min(overlaps),
        "max_overlap": max(overlaps),
        "top1_match_rate": top1_match / n,
        "top5_match_rate": top5_match / n,
        "per_candidate": per_candidate,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    docs = await fetch_sample(db, args.sample)
    if len(docs) < 5:
        logger.error(f"[Pilot] Only {len(docs)} candidates with BGE-M3 embeddings — not enough")
        return 1

    embed_svc = EmbeddingService()
    await embed_svc.initialize()

    # Build text corpus using the SAME preparation as the live indexer
    texts = [embed_svc._prepare_candidate_text(d) for d in docs]

    # Pull stored BGE-M3 vectors from the docs (avoids a 100-call refresh)
    bge_vecs = []
    for d in docs:
        v = (d.get("embeddings") or {}).get("bgem3", {}).get("vector") or []
        bge_vecs.append(v)

    # Sanity: keep only rows where both a BGE vector exists AND the text is non-empty
    keep = [i for i, (v, t) in enumerate(zip(bge_vecs, texts)) if len(v) == 1024 and t.strip()]
    if len(keep) < len(bge_vecs):
        logger.warning(f"[Pilot] Dropping {len(bge_vecs) - len(keep)} rows with missing vectors/text")

    docs = [docs[i] for i in keep]
    texts = [texts[i] for i in keep]
    bge_vecs = [bge_vecs[i] for i in keep]

    logger.info(f"[Pilot] Generating {len(texts)} Nemotron embeddings...")
    t0 = time.time()
    nem_vecs = await generate_nemotron_embeddings(texts)
    logger.info(f"[Pilot] Nemotron embeddings done in {time.time()-t0:.1f}s")

    bge_mat = np.array(bge_vecs, dtype=np.float32)
    nem_mat = np.array(nem_vecs, dtype=np.float32)

    logger.info(f"[Pilot] BGE-M3 matrix: {bge_mat.shape}, Nemotron matrix: {nem_mat.shape}")

    report = compare_rankings(bge_mat, nem_mat, k=args.top_k)
    report["timestamp"] = datetime.now(timezone.utc).isoformat()
    report["nemotron_model"] = NEMOTRON_EMBED_MODEL
    report["bge_model"] = "BAAI/bge-m3"
    report["decision"] = (
        "MIGRATE" if report["mean_overlap"] >= 0.95
        else "HOLD — quality drop unacceptable" if report["mean_overlap"] < 0.85
        else "REVIEW — borderline, inspect per-candidate outliers"
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = f"/tmp/nemotron_embed_pilot_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print("=" * 60)
    print("NEMOTRON EMBED vs BGE-M3 — PILOT REPORT")
    print("=" * 60)
    print(f"Sample size       : {report['sample_size']}")
    print(f"Top-K             : {report['top_k']}")
    print(f"Mean overlap      : {report['mean_overlap']*100:.1f}%")
    print(f"Median overlap    : {report['median_overlap']*100:.1f}%")
    print(f"Min / Max overlap : {report['min_overlap']*100:.1f}% / {report['max_overlap']*100:.1f}%")
    print(f"Top-1 match rate  : {report['top1_match_rate']*100:.1f}%")
    print(f"Top-5 match rate  : {report['top5_match_rate']*100:.1f}%")
    print(f"Decision          : {report['decision']}")
    print(f"Full report       : {out_path}")
    print("=" * 60)

    client.close()
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code or 0)
