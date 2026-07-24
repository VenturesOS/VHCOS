"""
report_slow_endpoints.py — Health check helper

Prints the top slow / high-traffic / error-prone endpoints from the
`api_metrics` collection.

IMPORTANT schema notes (this is where the prior script failed):
  • `timestamp` is stored as an epoch float (produced by `time.time()`),
    NOT as a BSON `Date`. Match filters MUST use a numeric `$gte`,
    otherwise the query returns zero rows.
  • The latency field is `duration_ms` (float, milliseconds).

Usage:
    python3 -m backend.scripts.report_slow_endpoints          # last 1h
    python3 -m backend.scripts.report_slow_endpoints --hours 6
    python3 -m backend.scripts.report_slow_endpoints --hours 24 --limit 25
"""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Allow running as a bare script: python3 backend/scripts/report_slow_endpoints.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main(hours: float, limit: int) -> None:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL / DB_NAME missing from environment", file=sys.stderr)
        sys.exit(1)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    cutoff = time.time() - hours * 3600
    total = await db.api_metrics.count_documents({"timestamp": {"$gte": cutoff}})
    print(f"\nWindow: last {hours}h   |   total requests: {total:,}\n")

    if total == 0:
        # Diagnostic: was there ANY data at all?
        sample = await db.api_metrics.find_one({}, sort=[("timestamp", -1)])
        if sample:
            print("(no rows in window — most recent row is:")
            print(f"   endpoint={sample.get('endpoint')} "
                  f"ts={sample.get('timestamp')} "
                  f"duration_ms={sample.get('duration_ms')})")
        else:
            print("(api_metrics collection is empty)")
        return

    # ── Top slow endpoints by avg duration ──
    print("=" * 78)
    print(f"TOP {limit} SLOW ENDPOINTS (by avg duration_ms)")
    print("=" * 78)
    print(f"{'AVG ms':>8}  {'P95 ms':>8}  {'MAX ms':>8}  {'HITS':>7}  {'ERR%':>5}  ENDPOINT")

    pipeline_slow = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"endpoint": "$endpoint", "method": "$method"},
            "hits": {"$sum": 1},
            "errors": {"$sum": {"$cond": ["$is_error", 1, 0]}},
            "avg_ms": {"$avg": "$duration_ms"},
            "max_ms": {"$max": "$duration_ms"},
            "p95_ms": {"$percentile": {"input": "$duration_ms",
                                       "p": [0.95],
                                       "method": "approximate"}},
        }},
        {"$match": {"hits": {"$gte": 5}}},  # ignore endpoints hit <5 times
        {"$sort": {"avg_ms": -1}},
        {"$limit": limit},
    ]
    async for r in db.api_metrics.aggregate(pipeline_slow, allowDiskUse=True):
        p95 = r.get("p95_ms")
        if isinstance(p95, list):
            p95 = p95[0] if p95 else 0
        err_pct = (r["errors"] / r["hits"]) * 100 if r["hits"] else 0
        ep = f"{r['_id']['method']} {r['_id']['endpoint']}"
        print(f"{r['avg_ms']:>8.1f}  {p95 or 0:>8.1f}  {r['max_ms']:>8.1f}  "
              f"{r['hits']:>7,}  {err_pct:>4.1f}%  {ep}")

    # ── Top hit endpoints (traffic hogs) ──
    print()
    print("=" * 78)
    print(f"TOP {limit} HIGH-TRAFFIC ENDPOINTS (by hit count)")
    print("=" * 78)
    print(f"{'HITS':>7}  {'% OF TOTAL':>10}  {'AVG ms':>8}  ENDPOINT")

    pipeline_traffic = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"endpoint": "$endpoint", "method": "$method"},
            "hits": {"$sum": 1},
            "avg_ms": {"$avg": "$duration_ms"},
        }},
        {"$sort": {"hits": -1}},
        {"$limit": limit},
    ]
    async for r in db.api_metrics.aggregate(pipeline_traffic, allowDiskUse=True):
        pct = (r["hits"] / total) * 100 if total else 0
        ep = f"{r['_id']['method']} {r['_id']['endpoint']}"
        print(f"{r['hits']:>7,}  {pct:>9.1f}%  {r['avg_ms']:>8.1f}  {ep}")

    # ── Top error-prone endpoints ──
    print()
    print("=" * 78)
    print(f"TOP {limit} ERROR-PRONE ENDPOINTS (by error count, min 3 errors)")
    print("=" * 78)
    print(f"{'ERRORS':>7}  {'HITS':>7}  {'ERR%':>5}  ENDPOINT")

    pipeline_errors = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"endpoint": "$endpoint", "method": "$method"},
            "hits": {"$sum": 1},
            "errors": {"$sum": {"$cond": ["$is_error", 1, 0]}},
        }},
        {"$match": {"errors": {"$gte": 3}}},
        {"$sort": {"errors": -1}},
        {"$limit": limit},
    ]
    printed = 0
    async for r in db.api_metrics.aggregate(pipeline_errors, allowDiskUse=True):
        err_pct = (r["errors"] / r["hits"]) * 100 if r["hits"] else 0
        ep = f"{r['_id']['method']} {r['_id']['endpoint']}"
        print(f"{r['errors']:>7,}  {r['hits']:>7,}  {err_pct:>4.1f}%  {ep}")
        printed += 1
    if printed == 0:
        print("(no endpoints with >=3 errors — good!)")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=1.0,
                        help="Look-back window in hours (default: 1)")
    parser.add_argument("--limit", type=int, default=15,
                        help="Rows per section (default: 15)")
    args = parser.parse_args()
    asyncio.run(main(args.hours, args.limit))
