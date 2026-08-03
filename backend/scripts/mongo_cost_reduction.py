#!/usr/bin/env python3
"""
MongoDB cost-reduction cleanup — one-time bloat prune + TTL indexes.

WHAT IT DOES (safe, no schema changes, no feature impact):
  1. Adds TTL indexes to collections that grow forever (log/telemetry/cache):
       - activity_logs             30 days
       - naukri_capture_logs       30 days
       - system_health_checks       7 days
       - analytics_pageviews       90 days
       - security_events           90 days
       - extraction_tracking       30 days
       - job_suggestions           14 days   (LLM cache — regenerates on demand)
       - notifications             60 days   (only delivered/read ones)
  2. One-time delete of rows already past the TTL cutoff (TTL indexes only
     affect future rows and take ~24h to sweep — this shrinks the DB now).
  3. Runs collMod compact on affected collections to reclaim disk.
  4. Prints before / after collection sizes.

WHAT IT DOES NOT DO:
  - Does not touch candidate_bank, applications, jobs, users (business data).
  - Does not touch candidate_embeddings (needs code changes to compress —
    separate PR).
  - Does not delete anything you have to keep for compliance / audit.

USAGE:
  DRY-RUN (default — shows what would happen):
      python3 backend/scripts/mongo_cost_reduction.py

  APPLY (actually prune + create TTLs):
      python3 backend/scripts/mongo_cost_reduction.py --apply
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING

load_dotenv("/app/backend/.env")

# Collection -> (ttl_seconds, ttl_field, extra_filter)
# ttl_field must be a BSON Date OR a numeric epoch — TTL only works on those.
# If the collection stores timestamps as ISO strings we skip that config and
# fall back to a one-time delete by a range predicate.
TTL_PLAN = {
    "activity_logs":         {"days": 30,  "field": "created_at",  "field_type": "iso"},
    "naukri_capture_logs":   {"days": 30,  "field": "created_at",  "field_type": "iso"},
    "system_health_checks":  {"days": 7,   "field": "checked_at",  "field_type": "iso"},
    "analytics_pageviews":   {"days": 90,  "field": "created_at",  "field_type": "iso"},
    "security_events":       {"days": 90,  "field": "created_at",  "field_type": "iso"},
    "extraction_tracking":   {"days": 30,  "field": "created_at",  "field_type": "iso"},
    "job_suggestions":       {"days": 14,  "field": "generated_at","field_type": "iso"},
    "notifications":         {"days": 60,  "field": "created_at",  "field_type": "iso",
                              "extra_filter": {"read": True}},
}


async def show_sizes(db, header):
    print(f"\n=== {header} ===")
    total_mb = 0
    for coll in TTL_PLAN:
        try:
            s = await db.command("collStats", coll, scale=1024 * 1024)
            count = s.get("count", 0)
            size = s.get("storageSize", 0)
            total_mb += size
            print(f"  {coll:<28}  {count:>10,} docs   {size:>7.1f} MB storage")
        except Exception as e:
            print(f"  {coll:<28}  (not found: {e})")
    print(f"  {'TOTAL':<28}  {'':>10}       {total_mb:>7.1f} MB")


async def probe_field(db, coll, field):
    """Return one sample doc's field value + inferred type."""
    doc = await db[coll].find_one({field: {"$exists": True}}, {field: 1, "_id": 0})
    if not doc or field not in doc:
        return None, None
    v = doc[field]
    return v, type(v).__name__


async def ensure_ttl_index(db, coll, plan, apply):
    """Add TTL index only when the field type is BSON Date. For ISO-string
    timestamps we rely on the one-time delete instead (TTL doesn't index strings)."""
    field = plan["field"]
    sample, kind = await probe_field(db, coll, field)
    if sample is None:
        print(f"  [{coll}] field '{field}' not found on any doc — skip TTL")
        return

    if kind == "datetime":
        idx_name = f"{field}_ttl"
        existing = await db[coll].list_indexes().to_list(50)
        if any(i["name"] == idx_name for i in existing):
            print(f"  [{coll}] TTL index already exists — skip")
            return
        seconds = plan["days"] * 86400
        if apply:
            await db[coll].create_index(
                [(field, ASCENDING)], name=idx_name,
                expireAfterSeconds=seconds, background=True,
            )
            print(f"  [{coll}] ✓ TTL index created ({plan['days']}d on {field})")
        else:
            print(f"  [{coll}] would create TTL ({plan['days']}d on {field})")
    else:
        print(f"  [{coll}] field '{field}' is {kind} — TTL not applicable, one-time delete only")


async def one_time_prune(db, coll, plan, apply):
    """Delete rows older than the cutoff, whatever the field type is."""
    field = plan["field"]
    sample, kind = await probe_field(db, coll, field)
    if sample is None:
        return 0

    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=plan["days"])
    if kind == "datetime":
        cutoff = cutoff_dt
    elif kind == "str":
        cutoff = cutoff_dt.isoformat()
    elif kind in ("int", "float"):
        cutoff = cutoff_dt.timestamp()
    else:
        print(f"  [{coll}] can't compare — unsupported type {kind}, skip prune")
        return 0

    query = {field: {"$lt": cutoff}}
    if plan.get("extra_filter"):
        query.update(plan["extra_filter"])

    to_delete = await db[coll].count_documents(query)
    if to_delete == 0:
        print(f"  [{coll}] 0 rows older than {plan['days']}d — nothing to prune")
        return 0

    if not apply:
        print(f"  [{coll}] would delete {to_delete:,} rows older than {plan['days']}d ({field} < {cutoff_dt.date()})")
        return 0

    res = await db[coll].delete_many(query)
    print(f"  [{coll}] ✓ deleted {res.deleted_count:,} rows older than {plan['days']}d")
    return res.deleted_count


async def compact(db, coll, apply):
    """Reclaim on-disk space. Atlas M0/M2/M5 doesn't allow compact — we log and skip."""
    if not apply:
        return
    try:
        await db.command("compact", coll)
        print(f"  [{coll}] ✓ compacted")
    except Exception as e:
        msg = str(e).lower()
        if "not authorized" in msg or "not supported" in msg or "shared" in msg:
            print(f"  [{coll}] compact not allowed on this tier (Atlas reclaims on its own)")
        else:
            print(f"  [{coll}] compact failed: {e}")


async def main(apply: bool):
    if not os.environ.get("MONGO_URL"):
        print("ERROR: MONGO_URL not set. Aborting.")
        sys.exit(1)

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    mode = "APPLY (writing to DB)" if apply else "DRY-RUN (nothing will change)"
    print(f"MongoDB cost-reduction cleanup — {mode}")
    print(f"DB: {os.environ['DB_NAME']}")

    await show_sizes(db, "BEFORE")

    print("\n=== 1) TTL indexes ===")
    for coll, plan in TTL_PLAN.items():
        await ensure_ttl_index(db, coll, plan, apply)

    print("\n=== 2) One-time prune of old rows ===")
    total_deleted = 0
    for coll, plan in TTL_PLAN.items():
        total_deleted += await one_time_prune(db, coll, plan, apply)
    print(f"\n  Total rows {'deleted' if apply else 'would be deleted'}: {total_deleted:,}")

    print("\n=== 3) Compact (best-effort) ===")
    for coll in TTL_PLAN:
        await compact(db, coll, apply)

    await show_sizes(db, "AFTER" if apply else "AFTER (projected)")

    print("\nDone.")
    if not apply:
        print("Re-run with --apply to actually make changes.")
    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Actually write to DB (default: dry-run)")
    args = p.parse_args()
    asyncio.run(main(args.apply))
