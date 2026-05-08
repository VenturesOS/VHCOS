#!/usr/bin/env python3
"""
Plugs two AI-enrichment leaks identified on 2026-04-30:

1. **No-tag candidates** (ai_enrichment_source is None) — tag them as
   `all_failed` / `legacy_untagged` so they become queryable & re-enrichable.
2. **all_failed / emergent_haiku candidates** — re-attempt Qwen via the
   existing `extract_full_profile_fallback` so they move back to
   `runpod_qwen14b` tag and don't count as leakage.

Usage (on EC2):

  # 1. Tag-only (no re-enrichment) — fast, idempotent
  python3 backend/scripts/backfill_and_retry_ai_tags.py --tag-only

  # 2. Re-enrich everything tagged emergent / anthropic / all_failed
  python3 backend/scripts/backfill_and_retry_ai_tags.py --retry --limit 500 \
      --since-days 7

  # 3. Dry run (see what would be touched)
  python3 backend/scripts/backfill_and_retry_ai_tags.py --retry --dry-run
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make backend importable regardless of cwd
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

def _resolve_mongo_credentials() -> tuple[str, str]:
    """Resolve MONGO_URL + DB_NAME using the SAME priority as backend/config.py:
       1. mongo_production_override.py (survives .env overwrites)
       2. backend/.env (raw line parse, no shell interpolation)
       3. /home/ubuntu/.env fallback
    """
    # 1. Override file takes priority
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        from mongo_production_override import MONGO_URL as _ovr_url, DB_NAME as _ovr_db  # type: ignore
        if _ovr_url and "mongodb" in _ovr_url:
            return _ovr_url, (_ovr_db or "vhc_talent_os")
    except Exception:
        pass

    # 2/3. Raw-parse .env files (systemd EnvironmentFile semantics: no
    # variable interpolation; strip wrapping quotes; first wins).
    for candidate in (BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env", Path.home() / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            os.environ.setdefault(key, val)

    url = os.environ.get("MONGO_URL") or os.environ.get("MONGODB_URI") or ""
    db = os.environ.get("DB_NAME") or "vhc_talent_os"
    return url, db


MONGO_URL, DB_NAME = _resolve_mongo_credentials()
if MONGO_URL:
    os.environ["MONGO_URL"] = MONGO_URL
    os.environ["DB_NAME"] = DB_NAME

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

# Targets we consider "leaked" and want to retry on Qwen
RETRY_SOURCES = {
    "emergent_haiku_4_5", "anthropic_direct_haiku",
    "all_failed", "exception",
    "qwen_reachable_unrecovered",  # Qwen failed but pod was up — typically
                                    # recoverable on a later retry once Qwen
                                    # settles / raw_text is re-scraped.
}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag-only", action="store_true",
                        help="Only backfill missing ai_enrichment_source tags — don't call any LLM")
    parser.add_argument("--retry", action="store_true",
                        help="Re-run Qwen on candidates tagged emergent/anthropic/all_failed")
    parser.add_argument("--report", action="store_true",
                        help="Print AI-source breakdown for the last N days and exit (no writes)")
    parser.add_argument("--since-days", type=int, default=7,
                        help="Only touch candidates created in the last N days")
    parser.add_argument("--limit", type=int, default=200,
                        help="Max candidates to retry in this run (safety net). "
                             "Retry loop is serial (concurrency=1 by design) to prevent "
                             "OOM cascades like the May-05 incident.")
    parser.add_argument("--skip-cold", action="store_true",
                        help="Skip candidates with no application linkage AND created > 90d ago. "
                             "Saves Qwen calls on dormant captures nobody ever used.")
    parser.add_argument("--continuous", action="store_true",
                        help="With --retry: loop until no more leaked candidates are queueable "
                             "(or three passes make no progress, as a safety stop)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show counts without writing")
    args = parser.parse_args()

    if not args.tag_only and not args.retry and not args.report:
        parser.error("Pass at least one of --tag-only, --retry, or --report")

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL / DB_NAME not set in environment", file=sys.stderr)
        return 2

    client = AsyncIOMotorClient(mongo_url, tlsAllowInvalidCertificates=True)
    db = client[db_name]
    since = (datetime.now(timezone.utc) - timedelta(days=args.since_days)).isoformat()

    print(f"[backfill-ai-tags] DB={db_name}  since={since}  dry_run={args.dry_run}")

    # ── 0. REPORT: print breakdown and exit ──────────────────────────────────
    if args.report:
        total = await db.candidate_bank.count_documents({"created_at": {"$gte": since}})
        print(f"\nTotal captured in last {args.since_days}d: {total}\n")
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {"_id": "$ai_enrichment_source", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
        ]
        qwen = 0
        async for r in db.candidate_bank.aggregate(pipeline):
            pct = round(r["n"] / total * 100, 1) if total else 0
            src = str(r["_id"])
            if src.startswith("runpod_qwen"):
                qwen += r["n"]
            print(f"  {src:<30} {r['n']:>5}  ({pct}%)")
        print(f"\nQwen share: {round(qwen/total*100,1) if total else 0}%")
        client.close()
        return 0

    # ── 1. TAG-ONLY: backfill None tags ──────────────────────────────────────
    untagged_q = {
        "created_at": {"$gte": since},
        "ai_enrichment_source": {"$in": [None, ""]},
    }
    n_untagged = await db.candidate_bank.count_documents(untagged_q)
    print(f"  untagged (ai_enrichment_source=None): {n_untagged}")

    if n_untagged and args.tag_only and not args.dry_run:
        # Split by enrichment_status so the tag reflects the actual historical path:
        #   enrichment_status == 'failed' → 'all_failed'
        #   enrichment_status ∈ ('enriched', 'pending', None) → 'legacy_untagged'
        res1 = await db.candidate_bank.update_many(
            {**untagged_q, "enrichment_status": "failed"},
            {"$set": {"ai_enrichment_source": "all_failed"}},
        )
        res2 = await db.candidate_bank.update_many(
            {**untagged_q, "enrichment_status": {"$ne": "failed"}},
            {"$set": {"ai_enrichment_source": "legacy_untagged"}},
        )
        print(f"  tagged as all_failed      : {res1.modified_count}")
        print(f"  tagged as legacy_untagged : {res2.modified_count}")

    # ── 2. RETRY: push leaked candidates back through Qwen ───────────────────
    if args.retry:
        retry_q = {
            "created_at": {"$gte": since},
            "ai_enrichment_source": {"$in": list(RETRY_SOURCES)},
            "raw_text_for_enrichment": {"$ne": None},
        }

        # Phase 52: optionally skip cold candidates (enriched + never-applied
        # + created > 90d ago). Saves Qwen calls on captures nobody ever used.
        cold_excluded = 0
        if args.skip_cold:
            cold_cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            warm_ids = set(await db.applications.distinct("candidate_id"))
            cold_query = {
                "id": {"$nin": list(warm_ids)} if warm_ids else {"$exists": True},
                "created_at": {"$lt": cold_cutoff},
            }
            cold_ids = set(await db.candidate_bank.distinct("id", cold_query))
            if cold_ids:
                retry_q["id"] = {"$nin": list(cold_ids)}
                cold_excluded = len(cold_ids)
                print(f"  cold-skipped (no apps + > 90d old): {cold_excluded}")

        n_retry = await db.candidate_bank.count_documents(retry_q)
        print(f"  retry candidates (emergent/anthropic/all_failed): {n_retry}")

        if args.dry_run:
            # Breakdown by source for visibility
            pipeline = [
                {"$match": retry_q},
                {"$group": {"_id": "$ai_enrichment_source", "n": {"$sum": 1}}},
            ]
            async for r in db.candidate_bank.aggregate(pipeline):
                print(f"    {r['_id']:<25} {r['n']}")
            return 0

        # Import AFTER env is loaded
        from services.llm_fallback_service import extract_full_profile_fallback

        # Track which IDs we've already attempted in this run so --continuous
        # doesn't rescan the same still-leaked rows forever.
        attempted_ids: set[str] = set()
        pass_num = 0
        no_progress_passes = 0
        grand_processed = grand_moved = grand_still = 0

        while True:
            pass_num += 1
            pass_q = {**retry_q}
            if attempted_ids:
                pass_q["id"] = {"$nin": list(attempted_ids)}

            processed = 0
            moved_to_qwen = 0
            still_leaked = 0
            cursor = db.candidate_bank.find(
                pass_q,
                {"_id": 0, "id": 1, "name": 1, "raw_text_for_enrichment": 1,
                 "ai_enrichment_source": 1},
            ).limit(args.limit)

            async for c in cursor:
                cid = c["id"]
                attempted_ids.add(cid)
                name = c.get("name") or "(unknown)"
                raw = c.get("raw_text_for_enrichment") or ""
                if len(raw) < 200:
                    # Not enough text to re-extract meaningfully
                    continue
                try:
                    result = await extract_full_profile_fallback(raw_text=raw, candidate_name=name)
                except Exception as e:
                    print(f"    ❌ {name[:30]:<30}  exception: {e}")
                    still_leaked += 1
                    continue
                processed += 1
                if not result or result.get("error"):
                    still_leaked += 1
                    continue
                new_source = result.get("_extraction_source") or result.get("source") or "unknown"
                if new_source.startswith("runpod_qwen"):
                    moved_to_qwen += 1
                # Only update the tag — DO NOT blindly overwrite the candidate's
                # fields (the original enrichment from emergent/anthropic may be
                # better on malformed records).
                await db.candidate_bank.update_one(
                    {"id": cid},
                    {"$set": {
                        "ai_enrichment_source": new_source,
                        "ai_reextracted_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                if processed % 20 == 0:
                    print(f"    progress pass {pass_num}: {processed} processed, "
                          f"{moved_to_qwen} recovered by Qwen")

            grand_processed += processed
            grand_moved += moved_to_qwen
            grand_still += still_leaked
            print(f"[retry] pass {pass_num} done: processed={processed} "
                  f"recovered_by_qwen={moved_to_qwen} still_leaked={still_leaked}")

            if not args.continuous:
                break

            # Stop when no more candidates are queueable
            remaining = await db.candidate_bank.count_documents({
                **retry_q,
                "id": {"$nin": list(attempted_ids)},
            })
            if remaining == 0:
                print(f"[retry] queue drained after {pass_num} passes")
                break
            if moved_to_qwen == 0:
                no_progress_passes += 1
                if no_progress_passes >= 3:
                    print(f"[retry] 3 consecutive passes moved 0 to Qwen — "
                          f"stopping ({remaining} still queueable, likely genuinely unrecoverable)")
                    break
            else:
                no_progress_passes = 0

        print(f"[retry] TOTAL: processed={grand_processed} "
              f"recovered_by_qwen={grand_moved} still_leaked={grand_still}")

    client.close()
    return 0


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc or 0)
