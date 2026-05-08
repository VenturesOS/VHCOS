"""
VHC Talent OS — One-time backfill migration script.

PURPOSE
-------
Normalizes all existing candidate_bank documents to the dual-write schema:

  Canonical field       Alias field (backward compat)
  ──────────────────────────────────────────────────
  key_skills         ↔  skills
  profile_summary    ↔  summary
  work_experience    ↔  experience
  total_experience_years ↔ experience_years

After this script completes, every document in candidate_bank will contain
BOTH field names with identical values, so queries using either name return
the same result set.

USAGE
-----
  # From the backend/ directory:
  python -m scripts.backfill_normalize_candidates

  # With options:
  python -m scripts.backfill_normalize_candidates --dry-run
  python -m scripts.backfill_normalize_candidates --batch-size 200
  python -m scripts.backfill_normalize_candidates --limit 1000

SAFETY
------
- Idempotent: safe to run multiple times.
- Read-safe: existing queries continue to work during the migration.
- Interruptible: re-run from the beginning, already-normalized docs are
  detected by the query filter and skipped (fast).
- Run during off-peak hours for large collections.

PRE-REQUISITES
--------------
1. Deploy the fixed application code first (it writes both field names
   on all NEW documents from that point forward).
2. Run this script to normalize historical documents.
3. After the script completes successfully, optionally add the unique
   email index (see post_migration_indexes.js).
"""
import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def run_backfill(dry_run: bool = False, batch_size: int = 100, limit: int = 0):
    # Import here so the script can be run standalone
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from motor.motor_asyncio import AsyncIOMotorClient
    from services.schema_normalizer import normalize_candidate
    import certifi

    mongodb_uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL")
    if not mongodb_uri:
        logger.error("MONGODB_URI environment variable not set")
        sys.exit(1)

    db_name = os.environ.get("MONGODB_DB_NAME", "vhc_talent_os")
    client  = AsyncIOMotorClient(mongodb_uri, tlsCAFile=certifi.where())
    db      = client[db_name]

    # Find documents missing any canonical field OR still using only the alias
    query = {
        "$or": [
            {"key_skills":             {"$exists": False}},
            {"profile_summary":        {"$exists": False}},
            {"total_experience_years": {"$exists": False}},
            {"work_experience":        {"$exists": False}},
        ]
    }

    total_to_fix = await db.candidate_bank.count_documents(query)
    logger.info(f"Documents to normalize: {total_to_fix}")

    if total_to_fix == 0:
        logger.info("All documents already normalized. Nothing to do.")
        client.close()
        return

    if dry_run:
        logger.info(f"[DRY RUN] Would normalize {total_to_fix} documents. Exiting.")
        client.close()
        return

    processed    = 0
    errors       = 0
    start_time   = datetime.now(timezone.utc)

    cursor = db.candidate_bank.find(query, {"_id": 1})
    if limit > 0:
        cursor = cursor.limit(limit)

    async for id_doc in cursor:
        try:
            # Fetch full doc (not just _id)
            full_doc = await db.candidate_bank.find_one(
                {"_id": id_doc["_id"]}, {"_id": 0}
            )
            if not full_doc:
                continue

            normalized = normalize_candidate(full_doc)

            await db.candidate_bank.update_one(
                {"_id": id_doc["_id"]},
                {"$set": normalized},
            )

            processed += 1

            if processed % batch_size == 0:
                elapsed  = (datetime.now(timezone.utc) - start_time).total_seconds()
                rate     = processed / elapsed if elapsed > 0 else 0
                remaining = (total_to_fix - processed) / rate if rate > 0 else 0
                logger.info(
                    f"Progress: {processed}/{total_to_fix} "
                    f"({rate:.1f}/s, ~{remaining:.0f}s remaining)"
                )

        except Exception as e:
            logger.error(f"Error normalizing document {id_doc['_id']}: {e}")
            errors += 1

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        f"\n{'=' * 50}\n"
        f"Backfill complete.\n"
        f"  Processed : {processed}\n"
        f"  Errors    : {errors}\n"
        f"  Time      : {elapsed:.1f}s\n"
        f"{'=' * 50}"
    )

    client.close()


def main():
    parser = argparse.ArgumentParser(description="Normalize candidate_bank schema")
    parser.add_argument(
        "--dry-run",   action="store_true",
        help="Count affected documents without writing",
    )
    parser.add_argument(
        "--batch-size", type=int, default=100,
        help="Log progress every N documents (default: 100)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Process at most N documents (0 = all, default: 0)",
    )
    args = parser.parse_args()

    asyncio.run(run_backfill(
        dry_run    = args.dry_run,
        batch_size = args.batch_size,
        limit      = args.limit,
    ))


if __name__ == "__main__":
    main()
