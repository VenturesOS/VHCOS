#!/usr/bin/env python3
"""
MongoDB cost + performance cleanup (v2, Feb 2026)

WHAT IT DOES (safe, no schema changes, no feature impact):
  1. Adds missing hot-path indexes (kills the Atlas "Scanned/Returned > 1000" alert):
       - extraction_tracking:  timestamp desc + (date, source, success) compound
       - job_suggestions:      job_id (used by /api/jobs/{id}/suggestions upsert)
  2. Adds TTL indexes where the timestamp field is a real BSON Date.
     For collections that store timestamps as ISO strings (most of ours),
     TTL doesn't work — we fall back to a one-time delete + a scheduled prune.
  3. Prunes old telemetry/log rows using the CORRECT field names observed
     in production:
       - activity_logs           timestamp (str)   > 30d
       - naukri_capture_logs     timestamp (str)   > 30d
       - system_health_checks    timestamp (str)   >  7d
       - analytics_pageviews     ts (datetime)     > 90d  ← TTL eligible
       - security_events         timestamp (str)   > 90d
       - extraction_tracking     timestamp (str)   > 30d
       - job_suggestions         completed_at (str)> 14d  (LLM cache)
       - notifications           created_at (str)  > 60d  (only is_read=True)
  4. Runs compact on affected collections to reclaim disk.
  5. Prints before / after sizes and doc counts.

WHAT IT DOES NOT DO:
  - Does not touch candidate_bank, candidate_embeddings, applications, jobs,
    users, or any business data.
  - Does not drop existing indexes (only creates missing ones).

USAGE:
  DRY-RUN (default):
      python3 backend/scripts/mongo_cost_reduction.py

  APPLY:
      python3 backend/scripts/mongo_cost_reduction.py --apply
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

load_dotenv("/app/backend/.env")

# Collection -> pruning plan
# field_type: "iso"  -> string like "2026-08-06T05:29:31+00:00" (lexicographic compare works)
#             "date" -> BSON datetime (TTL index eligible)
PRUNE_PLAN = {
    "activity_logs":         {"days": 30, "field": "timestamp",    "field_type": "iso"},
    "naukri_capture_logs":   {"days": 30, "field": "timestamp",    "field_type": "iso"},
    "system_health_checks":  {"days": 7,  "field": "timestamp",    "field_type": "iso"},
    "analytics_pageviews":   {"days": 90, "field": "ts",           "field_type": "date"},
    "security_events":       {"days": 90, "field": "timestamp",    "field_type": "iso"},
    "extraction_tracking":   {"days": 30, "field": "timestamp",    "field_type": "iso"},
    "job_suggestions":       {"days": 14, "field": "completed_at", "field_type": "iso"},
    "notifications":         {"days": 60, "field": "created_at",   "field_type": "iso",
                              "extra_filter": {"is_read": True}},
}

# Missing indexes flagged by Atlas Query Targeting alert (scanned/returned > 1000)
MISSING_INDEXES = [
    # extraction_tracking: 121K docs, only _id index — everything full-scans
    ("extraction_tracking", [("timestamp", DESCENDING)], {"name": "timestamp_-1"}),
    ("extraction_tracking",
        [("date", ASCENDING), ("source", ASCENDING), ("success", ASCENDING)],
        {"name": "date_source_success"}),
    # job_suggestions: 82MB of LLM cache with only _id — every read of
    #   db.job_suggestions.find_one({"job_id": X}) full-scans 928 huge docs
    ("job_suggestions", [("job_id", ASCENDING)], {"name": "job_id_1"}),
    ("job_suggestions", [("completed_at", ASCENDING)], {"name": "completed_at_1"}),
]


async def show_sizes(db, header):
    print(f"\n=== {header} ===")
    total_mb = 0
    for coll in PRUNE_PLAN:
        try:
            s = await db.command("collStats", coll, scale=1024 * 1024)
            count = s.get("count", 0)
            size = s.get("storageSize", 0)
            total_mb += size
            print(f"  {coll:<28}  {count:>10,} docs   {size:>7.1f} MB storage")
        except Exception as e:
            print(f"  {coll:<28}  (not found: {e})")
    print(f"  {'TOTAL':<28}  {'':>10}       {total_mb:>7.1f} MB")


async def ensure_missing_indexes(db, apply):
    print("\n=== 1) Missing hot-path indexes ===")
    for coll, keys, opts in MISSING_INDEXES:
        try:
            existing = await db[coll].list_indexes().to_list(100)
            if any(i.get("name") == opts["name"] for i in existing):
                print(f"  [{coll}] index {opts['name']} already exists — skip")
                continue
            if apply:
                await db[coll].create_index(keys, background=True, **opts)
                print(f"  [{coll}] ✓ created index {opts['name']} on {keys}")
            else:
                print(f"  [{coll}] would create {opts['name']} on {keys}")
        except Exception as e:
            print(f"  [{coll}] index create failed: {e}")


async def ensure_ttl(db, coll, plan, apply):
    """Add TTL index only when the field is a real BSON Date."""
    if plan["field_type"] != "date":
        return
    field = plan["field"]
    idx_name = f"{field}_ttl"
    existing = await db[coll].list_indexes().to_list(100)
    if any(i["name"] == idx_name for i in existing):
        print(f"  [{coll}] TTL index already exists — skip")
        return
    seconds = plan["days"] * 86400
    if apply:
        try:
            await db[coll].create_index(
                [(field, ASCENDING)], name=idx_name,
                expireAfterSeconds=seconds, background=True,
            )
            print(f"  [{coll}] ✓ TTL created ({plan['days']}d on {field})")
        except Exception as e:
            print(f"  [{coll}] TTL create failed: {e}")
    else:
        print(f"  [{coll}] would create TTL ({plan['days']}d on {field})")


async def one_time_prune(db, coll, plan, apply):
    field = plan["field"]
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=plan["days"])
    if plan["field_type"] == "date":
        cutoff = cutoff_dt
    else:  # iso string; lexicographic compare works for ISO 8601 with Z or +00:00
        cutoff = cutoff_dt.isoformat()

    query = {field: {"$lt": cutoff}}
    if plan.get("extra_filter"):
        query.update(plan["extra_filter"])

    try:
        to_delete = await db[coll].count_documents(query)
    except Exception as e:
        print(f"  [{coll}] count failed: {e}")
        return 0
    if to_delete == 0:
        print(f"  [{coll}] 0 rows older than {plan['days']}d")
        return 0

    if not apply:
        print(f"  [{coll}] would delete {to_delete:,} rows older than {plan['days']}d")
        return to_delete

    res = await db[coll].delete_many(query)
    print(f"  [{coll}] ✓ deleted {res.deleted_count:,} rows older than {plan['days']}d")
    return res.deleted_count


async def compact(db, coll, apply):
    if not apply:
        return
    try:
        await db.command("compact", coll)
        print(f"  [{coll}] ✓ compacted")
    except Exception as e:
        msg = str(e).lower()
        if any(w in msg for w in ("not authorized", "not supported", "shared")):
            print(f"  [{coll}] compact not allowed on this tier")
        else:
            print(f"  [{coll}] compact failed: {e}")


async def main(apply: bool):
    if not os.environ.get("MONGO_URL"):
        print("ERROR: MONGO_URL not set."); sys.exit(1)

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    mode = "APPLY (writing to DB)" if apply else "DRY-RUN (nothing will change)"
    print(f"MongoDB cost-reduction v2 — {mode}")
    print(f"DB: {os.environ['DB_NAME']}")

    await show_sizes(db, "BEFORE")

    await ensure_missing_indexes(db, apply)

    print("\n=== 2) TTL indexes (BSON Date fields only) ===")
    for coll, plan in PRUNE_PLAN.items():
        await ensure_ttl(db, coll, plan, apply)

    print("\n=== 3) One-time prune of old rows ===")
    total_deleted = 0
    for coll, plan in PRUNE_PLAN.items():
        total_deleted += await one_time_prune(db, coll, plan, apply)
    print(f"\n  Total rows {'deleted' if apply else 'would be deleted'}: {total_deleted:,}")

    print("\n=== 4) Compact ===")
    for coll in PRUNE_PLAN:
        await compact(db, coll, apply)

    await show_sizes(db, "AFTER" if apply else "AFTER (projected)")
    print("\nDone." + ("" if apply else "\nRe-run with --apply to make it real."))
    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    asyncio.run(main(args.apply))
