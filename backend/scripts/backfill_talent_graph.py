#!/usr/bin/env python3
"""
Backfill candidate_embeddings collection from candidate_bank.

Run on EC2:
    cd /home/ubuntu/vhc-platform/backend
    source venv/bin/activate
    python3 scripts/backfill_talent_graph.py --limit 6000 --concurrency 8

Strategies:
  • Skips candidates whose text_hash matches the stored embedding (fast resume)
  • Embeddings are batched in groups of 32 for ~5x speedup vs one-by-one
  • Summary generation is per-candidate via Qwen 14B; falls back to rule-based
    if Qwen unreachable
  • Progress is logged every 50 candidates
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Ensure backend modules are importable when run from /backend or /backend/scripts
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_talent_graph")


async def run(limit: int, concurrency: int, force: bool, only_missing: bool, fast_summary: bool, skip_cold_days: int):
    # Import via the backend's `config` module so we pick up production
    # MONGO_URL overrides (mongo_production_override.py on EC2). Reading
    # os.environ directly would use the stale .env value and fail auth.
    from config import db, initialize_db
    from services.talent_graph_service import (
        EMBEDDINGS_COLL,
        ensure_embeddings_indexes,
        fallback_rule_summary,
        upsert_candidate_embedding,
    )

    # The lazy db proxy is only wired up after initialize_db() runs;
    # gunicorn does this on startup, but we need to do it manually for the script.
    initialize_db()

    await ensure_embeddings_indexes(db)

    # Build query
    query = {}
    if only_missing:
        # Only candidates that don't yet have an embedding
        existing_ids = await db[EMBEDDINGS_COLL].distinct("candidate_id")
        if existing_ids:
            query["id"] = {"$nin": existing_ids}

    # ── Stale-skip filter (Phase 52, 2026-05-06) ───────────────────────────
    # Cold candidates have:
    #   • no application linkage (never assigned to a mandate), AND
    #   • created > N days ago, AND
    #   • already enriched (enrichment_status=enriched)
    # These represent one-time recruiter captures that nobody acted on.
    # Skipping them in the backfill is purely a CPU/Qwen cost saver — when a
    # recruiter does eventually engage one, the live capture flow re-embeds
    # automatically (raw_text_hash check in extension.py).
    cold_skipped = 0
    if skip_cold_days > 0:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=skip_cold_days)).isoformat()
        # Get candidates that DO have applications (the "warm" set)
        warm_ids = set(await db.applications.distinct("candidate_id"))
        # Build the cold filter: enriched + no application + older than cutoff
        cold_query = {
            "enrichment_status": "enriched",
            "id": {"$nin": list(warm_ids)} if warm_ids else {"$exists": True},
            "created_at": {"$lt": cutoff},
        }
        cold_ids = set(await db.candidate_bank.distinct("id", cold_query))
        if cold_ids:
            existing_nin = query.get("id", {}).get("$nin", [])
            query["id"] = {"$nin": list(set(existing_nin) | cold_ids)}
            cold_skipped = len(cold_ids)
            logger.info(
                f"Stale-skip: excluding {cold_skipped} cold candidates "
                f"(enriched + no applications + created < {skip_cold_days}d ago)"
            )

    total = await db.candidate_bank.count_documents(query)
    logger.info(
        f"Backfill scope: {total} candidates "
        f"(limit={limit}, force={force}, only_missing={only_missing}, "
        f"cold_skipped={cold_skipped})"
    )

    if total == 0:
        logger.info("Nothing to do.")
        return

    cursor = db.candidate_bank.find(query, {"_id": 0}).limit(limit)

    sem = asyncio.Semaphore(concurrency)
    stats = {"embedded": 0, "skipped": 0, "failed": 0}
    t0 = time.time()
    processed = 0

    async def _worker(doc):
        nonlocal processed
        async with sem:
            try:
                # Fast mode: precompute the rule-based summary and pass it in,
                # which makes upsert_candidate_embedding skip the Qwen RunPod call.
                # 5-10x faster for bulk backfill. Recruiters can refresh to a richer
                # AI summary on-demand via /api/talent-graph/refresh/{id}.
                pre_summary = fallback_rule_summary(doc) if fast_summary else None
                res = await upsert_candidate_embedding(
                    db, doc, force=force, summary=pre_summary
                )
                status = res.get("status", "failed")
                stats[status] = stats.get(status, 0) + 1
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"  ✗ {doc.get('id')}: {e}")
            finally:
                processed += 1
                if processed % 50 == 0:
                    elapsed = time.time() - t0
                    rate = processed / elapsed if elapsed else 0
                    eta = (total - processed) / rate if rate else 0
                    logger.info(
                        f"  Progress: {processed}/{total} "
                        f"({stats['embedded']}/{stats['skipped']}/{stats['failed']} emb/skip/fail) "
                        f"@ {rate:.1f}/s, ETA {eta/60:.1f}m"
                    )

    tasks = []
    async for d in cursor:
        tasks.append(asyncio.create_task(_worker(d)))
        if len(tasks) >= 200:
            await asyncio.gather(*tasks)
            tasks = []
    if tasks:
        await asyncio.gather(*tasks)

    elapsed = time.time() - t0
    logger.info(
        f"Backfill DONE: {stats['embedded']} embedded, "
        f"{stats['skipped']} skipped, {stats['failed']} failed in {elapsed:.1f}s"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1000000,
                    help="Max candidates to process this run (default 1M = effectively unlimited)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--force", action="store_true",
                    help="Re-embed even if text_hash unchanged")
    ap.add_argument("--all", action="store_true",
                    help="Process all candidates (default: only those without an embedding)")
    ap.add_argument("--fast-summary", action="store_true",
                    help="Use rule-based summary (skips Qwen) for 5-10x speedup. "
                         "Embeddings unaffected. Recruiters can refresh on-demand later.")
    ap.add_argument("--skip-cold-days", type=int, default=90,
                    help="Skip candidates that are enriched + have no applications + "
                         "were created > N days ago (cold/dormant captures). "
                         "Default 90. Set to 0 to disable.")
    args = ap.parse_args()

    asyncio.run(run(
        limit=args.limit,
        concurrency=args.concurrency,
        force=args.force,
        only_missing=not args.all,
        fast_summary=args.fast_summary,
        skip_cold_days=args.skip_cold_days,
    ))


if __name__ == "__main__":
    main()
