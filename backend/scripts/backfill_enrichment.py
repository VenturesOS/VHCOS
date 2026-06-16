"""
Backfill enrichment for the top-N companies in the candidate bank.

Runs `services.profile_enricher.enrich_candidate` against every candidate
who works at one of the top-N most-common employers in the bank. The
top-N strategy keeps the first run focused — once these candidates are
covered, the lazy enrichment hook in `/api/talent/search` will handle
the long tail.

Usage
-----
    cd /app/backend
    python scripts/backfill_enrichment.py            # default: top 50, all candidates
    python scripts/backfill_enrichment.py --top 100  # top 100 companies
    python scripts/backfill_enrichment.py --no-llm   # rules-only (free)
    python scripts/backfill_enrichment.py --dry-run  # print what would change

Logs progress every 100 candidates and writes a summary at the end.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, List

# Make /app/backend imports work when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from services.profile_enricher import enrich_candidate  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_enrichment")


async def _top_companies(db, n: int) -> List[str]:
    pipeline = [
        {"$match": {
            "$or": [
                {"current_employer": {"$exists": True, "$nin": [None, ""]}},
                {"current_company": {"$exists": True, "$nin": [None, ""]}},
            ]
        }},
        {"$group": {
            "_id": {"$ifNull": ["$current_employer", "$current_company"]},
            "n": {"$sum": 1},
        }},
        {"$sort": {"n": -1}},
        {"$limit": n},
    ]
    rows = await db.candidate_bank.aggregate(pipeline).to_list(n)
    return [r["_id"] for r in rows if r.get("_id")]


async def main(top: int, allow_llm: bool, dry_run: bool, limit: int) -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], tlsAllowInvalidCertificates=True)
    db = client[os.environ["DB_NAME"]]

    companies = await _top_companies(db, top)
    logger.info(f"Top {len(companies)} companies → {companies[:10]}…")

    query = {
        "$or": [
            {"current_employer": {"$in": companies}},
            {"current_company": {"$in": companies}},
        ]
    }
    total = await db.candidate_bank.count_documents(query)
    logger.info(f"Candidates in top-{top} companies: {total:,}")
    if limit:
        logger.info(f"--limit set → processing only {limit:,} of {total:,}")
        total = min(total, limit)

    t0 = time.time()
    seen = 0
    updated = 0
    field_counts: Dict[str, int] = {}

    PROJ = {
        "_id": 0, "id": 1, "name": 1,
        "current_employer": 1, "current_company": 1,
        "industry": 1, "current_industry": 1,
        "current_designation": 1, "designation": 1, "headline": 1,
        "key_skills": 1, "skills": 1,
        "current_location": 1, "location": 1,
        "summary": 1, "profile_summary": 1, "notice_period_days": 1,
        "enriched_seniority": 1, "enriched_function": 1, "enriched_location": 1,
    }

    cursor = db.candidate_bank.find(query, PROJ)
    if limit:
        cursor = cursor.limit(limit)

    async for doc in cursor:
        seen += 1
        try:
            updates = await enrich_candidate(doc, db, allow_llm=allow_llm)
        except Exception as e:
            logger.exception(f"[Enricher] candidate {doc.get('id')} failed: {e}")
            continue

        if updates:
            updated += 1
            for k in updates:
                if k in ("enrichment_meta", "enriched_at"):
                    continue
                field_counts[k] = field_counts.get(k, 0) + 1
            if not dry_run:
                await db.candidate_bank.update_one(
                    {"id": doc["id"]}, {"$set": updates}
                )

        if seen % 100 == 0:
            rate = seen / max(time.time() - t0, 1e-6)
            logger.info(
                f"  progress: {seen:,}/{total:,} "
                f"({100*seen/max(total,1):5.1f}%)  updated={updated:,}  "
                f"rate={rate:.1f}/s"
            )

    elapsed = int(time.time() - t0)
    logger.info("=" * 60)
    logger.info(f"DONE in {elapsed}s | seen={seen:,} updated={updated:,}")
    for k, v in sorted(field_counts.items(), key=lambda kv: -kv[1]):
        logger.info(f"  • {k:30s}: {v:>6,}  ({100*v/max(seen,1):5.1f}%)")
    if dry_run:
        logger.info("DRY RUN — no DB writes performed")
    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="cap candidates processed (0 = all)")
    args = p.parse_args()
    asyncio.run(main(args.top, allow_llm=not args.no_llm, dry_run=args.dry_run, limit=args.limit))
