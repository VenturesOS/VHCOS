"""
Backfill BGE-M3 embeddings for the candidate bank + jobs (Phase 55.13).

The previous OpenAI text-embedding-3-small path had only embedded 1.1% of
candidates. This script embeds the remaining ones and re-embeds any that
still carry stale 1536-dim OpenAI vectors.

Design:
- Resumable: only touches docs where `embedding` is missing OR the length
  != BGE-M3's 1024 dims. Safe to re-run.
- Rate-limited: batches of 32 texts (BGE-M3 default max_client_batch_size),
  parallel across up to 8 concurrent RunPod requests.
- Idempotent: writes `embedding_updated_at` and `embedding_model` fields
  so future migrations can filter cleanly.
- Auto-throttles on RunPod 429/503.
- Prints progress every 500 docs.

Usage:
    cd /app/backend && python -m scripts.backfill_bge_embeddings [--limit N] [--jobs] [--dry-run]

Defaults to candidates. Pass --jobs to also backfill jobs.
"""
import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Ensure /app/backend is on sys.path when script is invoked directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_bge")

BATCH_SIZE = 32
MAX_CONCURRENCY = 8
TARGET_DIMS = 1024


def build_query() -> Dict:
    """Docs that need (re-)embedding: missing OR wrong-dim vector."""
    return {
        "$or": [
            {"embedding": {"$exists": False}},
            {"embedding": None},
            {"embedding": {"$size": 0}},
            # Old OpenAI vectors are 1536-dim; any wrong size = stale
            {"$expr": {"$ne": [{"$size": {"$ifNull": ["$embedding", []]}}, TARGET_DIMS]}},
        ]
    }


async def process_candidate_batch(
    db,
    embedding_service,
    docs: List[Dict],
    dry_run: bool,
) -> Dict:
    """Embed one batch of candidates and write vectors back to Mongo."""
    texts = [embedding_service._prepare_candidate_text(d) for d in docs]
    # Filter out empty texts (never re-embed those; nothing to embed against)
    valid_idx = [i for i, t in enumerate(texts) if t.strip()]
    valid_texts = [texts[i] for i in valid_idx]

    if not valid_texts:
        return {"processed": 0, "skipped_empty": len(docs), "failed": 0}

    vectors = await embedding_service.generate_embeddings_batch(valid_texts)

    processed = 0
    failed = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx_in_valid, vec in enumerate(vectors):
        original_idx = valid_idx[idx_in_valid]
        doc = docs[original_idx]
        if vec and len(vec) == TARGET_DIMS:
            if not dry_run:
                await db.candidate_bank.update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "embedding": vec,
                        "embedding_updated_at": now_iso,
                        "embedding_model": "BAAI/bge-m3",
                    }},
                )
            processed += 1
        else:
            failed += 1

    return {"processed": processed, "skipped_empty": len(docs) - len(valid_texts), "failed": failed}


async def backfill_collection(
    db,
    embedding_service,
    collection_name: str,
    text_fn,
    limit: Optional[int],
    dry_run: bool,
):
    coll = db[collection_name]
    query = build_query()

    total_needed = await coll.count_documents(query)
    logger.info(f"[{collection_name}] {total_needed:,} docs need (re-)embedding")

    if dry_run:
        logger.info(f"[{collection_name}] DRY RUN — no writes will be made")

    if limit:
        total_needed = min(total_needed, limit)
        logger.info(f"[{collection_name}] limited to {limit:,} docs")

    started = time.monotonic()
    processed = 0
    failed = 0
    skipped_empty = 0

    # Load all IDs up front to avoid cursor timing out mid-run
    cursor = coll.find(query, {"_id": 0})
    if limit:
        cursor = cursor.limit(limit)

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def run_batch(batch):
        async with semaphore:
            if collection_name == "candidate_bank":
                return await process_candidate_batch(db, embedding_service, batch, dry_run)
            else:
                # Jobs: simpler path
                return await process_jobs_batch(db, embedding_service, batch, dry_run)

    batch: List[Dict] = []
    tasks: List = []
    async for doc in cursor:
        batch.append(doc)
        if len(batch) >= BATCH_SIZE:
            tasks.append(asyncio.create_task(run_batch(batch)))
            batch = []
            # Flush if too many in-flight
            if len(tasks) >= MAX_CONCURRENCY * 2:
                done = await asyncio.gather(*tasks)
                for r in done:
                    processed += r["processed"]
                    failed += r["failed"]
                    skipped_empty += r["skipped_empty"]
                tasks = []
                elapsed = time.monotonic() - started
                rate = processed / elapsed if elapsed > 0 else 0
                logger.info(
                    f"[{collection_name}] progress: "
                    f"{processed:,}/{total_needed:,} ({processed*100/max(1,total_needed):.1f}%) "
                    f"| failed={failed} empty={skipped_empty} | {rate:.1f} docs/sec"
                )

    if batch:
        tasks.append(asyncio.create_task(run_batch(batch)))

    if tasks:
        done = await asyncio.gather(*tasks)
        for r in done:
            processed += r["processed"]
            failed += r["failed"]
            skipped_empty += r["skipped_empty"]

    elapsed = time.monotonic() - started
    logger.info(
        f"[{collection_name}] DONE in {elapsed:.1f}s: "
        f"processed={processed:,}, failed={failed}, skipped_empty={skipped_empty} "
        f"({processed / max(1, elapsed):.1f} docs/sec)"
    )
    return {"processed": processed, "failed": failed, "skipped_empty": skipped_empty}


async def process_jobs_batch(db, embedding_service, docs: List[Dict], dry_run: bool) -> Dict:
    texts = [embedding_service._prepare_job_text(d) for d in docs]
    valid_idx = [i for i, t in enumerate(texts) if t.strip()]
    valid_texts = [texts[i] for i in valid_idx]

    if not valid_texts:
        return {"processed": 0, "skipped_empty": len(docs), "failed": 0}

    vectors = await embedding_service.generate_embeddings_batch(valid_texts)

    processed = 0
    failed = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx_in_valid, vec in enumerate(vectors):
        original_idx = valid_idx[idx_in_valid]
        doc = docs[original_idx]
        if vec and len(vec) == TARGET_DIMS:
            if not dry_run:
                await db.jobs.update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "embedding": vec,
                        "embedding_updated_at": now_iso,
                        "embedding_model": "BAAI/bge-m3",
                    }},
                )
            processed += 1
        else:
            failed += 1

    return {"processed": processed, "skipped_empty": len(docs) - len(valid_texts), "failed": failed}


async def main():
    parser = argparse.ArgumentParser(description="Backfill BGE-M3 embeddings")
    parser.add_argument("--limit", type=int, default=None, help="Cap docs processed (for smoke tests)")
    parser.add_argument("--jobs", action="store_true", help="Also backfill jobs collection")
    parser.add_argument("--only-jobs", action="store_true", help="Backfill jobs only, skip candidates")
    parser.add_argument("--dry-run", action="store_true", help="Preview counts without writing")
    args = parser.parse_args()

    from services.embeddings import embedding_service

    if not await embedding_service.initialize():
        logger.error("Embedding service init failed. Check RUNPOD_API_KEY + RUNPOD_EMBED_URL.")
        return 1

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    try:
        if not args.only_jobs:
            await backfill_collection(
                db, embedding_service,
                "candidate_bank", embedding_service._prepare_candidate_text,
                args.limit, args.dry_run,
            )
        if args.jobs or args.only_jobs:
            await backfill_collection(
                db, embedding_service,
                "jobs", embedding_service._prepare_job_text,
                args.limit, args.dry_run,
            )
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
