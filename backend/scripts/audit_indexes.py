"""
MongoDB Index Audit — read-only.

Reports per-collection index usage statistics from MongoDB's `$indexStats`
aggregation, then flags candidates for removal:
  • size on disk
  • access count since last server restart
  • access rate per day (since `since` timestamp returned by $indexStats)
  • recommendation tag: KEEP / WATCH / DROP_CANDIDATE

DROP_CANDIDATE rules (configurable via CLI):
  • not the `_id` index (those can never be dropped)
  • size on disk > MIN_SIZE_KB (default 64 KB — tiny indexes aren't worth the noise)
  • zero accesses since the last restart of THIS member, OR
  • daily access rate < MIN_DAILY_OPS (default 5/day)

Run on EC2 (read-only, safe at any time):

    cd /home/ubuntu/vhc-platform/backend
    source venv/bin/activate
    python3 scripts/audit_indexes.py                  # full audit
    python3 scripts/audit_indexes.py --collection candidate_bank
    python3 scripts/audit_indexes.py --json > /tmp/index_audit.json

NOTE: $indexStats counters reset on every mongod restart. If your Atlas
cluster was rolled recently, an index can look "unused" simply because
not enough time has passed. Aim for ≥ 7 days of uptime before trusting
the DROP_CANDIDATE flag — the script prints uptime so you can verify.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

# Resolve backend path so we can re-use the existing config / db client
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from config import db, initialize_db  # noqa: E402

# Collections we don't audit (system / ephemeral / transient).
_SKIP_COLLECTIONS = {
    "system.indexes",
    "system.profile",
    "system.users",
    "fs.files",
    "fs.chunks",
}

# Indexes we never recommend dropping even if they look idle (safety lists).
_NEVER_DROP_INDEX_NAMES = {"_id_"}
_NEVER_DROP_FIELDS = {
    # Anything covering these fields is load-bearing for hot reads.
    "id",
    "candidate_id",
    "user_id",
    "employer_id",
    "team_id",
    "mandate_id",
    "job_id",
    "naukri_id",
    "email",
    "phone",
}


def _index_size_kb(stats_for_coll: dict, idx_name: str) -> float:
    """Pull index size (KB) out of `collStats.indexSizes`. Returns 0 if absent."""
    sizes = (stats_for_coll or {}).get("indexSizes", {}) or {}
    return round(sizes.get(idx_name, 0) / 1024.0, 1)


def _classify(
    idx: dict,
    size_kb: float,
    days_since_reset: float,
    min_size_kb: float,
    min_daily_ops: float,
) -> tuple[str, str]:
    """Return (tag, reason)."""
    name = idx.get("name", "")
    key_fields = set((idx.get("key") or {}).keys())

    if name in _NEVER_DROP_INDEX_NAMES:
        return "KEEP", "system index"

    if key_fields & _NEVER_DROP_FIELDS:
        # Hot path — keep regardless of access count
        return "KEEP", f"covers hot field(s): {sorted(key_fields & _NEVER_DROP_FIELDS)}"

    ops = (idx.get("accesses") or {}).get("ops", 0)
    daily = ops / max(days_since_reset, 0.1)

    if size_kb < min_size_kb:
        return "WATCH", f"too small to matter ({size_kb} KB)"

    if ops == 0:
        return "DROP_CANDIDATE", "0 ops since last reset"

    if daily < min_daily_ops:
        return "DROP_CANDIDATE", f"only {daily:.1f} ops/day (< {min_daily_ops})"

    if daily < min_daily_ops * 5:
        return "WATCH", f"low usage: {daily:.1f} ops/day"

    return "KEEP", f"active: {daily:.1f} ops/day"


async def _audit_collection(
    coll_name: str,
    *,
    min_size_kb: float,
    min_daily_ops: float,
    server_uptime_days: float,
) -> list[dict]:
    coll = db[coll_name]
    coll_stats = await db.command("collStats", coll_name)

    rows: list[dict] = []
    async for idx in coll.aggregate([{"$indexStats": {}}]):
        name = idx.get("name", "")
        size_kb = _index_size_kb(coll_stats, name)
        ops = (idx.get("accesses") or {}).get("ops", 0)
        since = (idx.get("accesses") or {}).get("since")

        days_since = server_uptime_days
        if since:
            try:
                if isinstance(since, datetime):
                    delta = datetime.now(timezone.utc) - (
                        since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                    )
                    days_since = max(delta.total_seconds() / 86400.0, 0.1)
            except Exception:
                pass

        tag, reason = _classify(idx, size_kb, days_since, min_size_kb, min_daily_ops)

        rows.append({
            "collection": coll_name,
            "index": name,
            "key": idx.get("key", {}),
            "size_kb": size_kb,
            "ops": ops,
            "days_observed": round(days_since, 1),
            "ops_per_day": round(ops / max(days_since, 0.1), 1),
            "tag": tag,
            "reason": reason,
            "drop_command": (
                f"db.{coll_name}.dropIndex('{name}')"
                if tag == "DROP_CANDIDATE" else None
            ),
        })

    return rows


async def _server_uptime_days() -> float:
    info = await db.command("serverStatus")
    return round(info.get("uptime", 0) / 86400.0, 1)


async def run(
    only_collection: str | None,
    min_size_kb: float,
    min_daily_ops: float,
    as_json: bool,
):
    initialize_db()
    uptime_days = await _server_uptime_days()

    if only_collection:
        coll_names = [only_collection]
    else:
        coll_names = sorted([
            c for c in await db.list_collection_names()
            if c not in _SKIP_COLLECTIONS and not c.startswith("system.")
        ])

    all_rows: list[dict] = []
    for c in coll_names:
        try:
            rows = await _audit_collection(
                c,
                min_size_kb=min_size_kb,
                min_daily_ops=min_daily_ops,
                server_uptime_days=uptime_days,
            )
            all_rows.extend(rows)
        except Exception as e:
            print(f"  [WARN] {c}: {e}", file=sys.stderr)

    if as_json:
        print(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "server_uptime_days": uptime_days,
            "min_size_kb": min_size_kb,
            "min_daily_ops": min_daily_ops,
            "rows": all_rows,
        }, indent=2, default=str))
        return

    # ── Pretty terminal report ────────────────────────────────────────────
    print("═" * 100)
    print(f"  MongoDB Index Audit — server uptime: {uptime_days} days")
    print(f"  Thresholds: drop if size > {min_size_kb} KB AND < {min_daily_ops} ops/day")
    print("═" * 100)

    by_tag: dict[str, list[dict]] = {}
    for r in all_rows:
        by_tag.setdefault(r["tag"], []).append(r)

    drops = by_tag.get("DROP_CANDIDATE", [])
    watch = by_tag.get("WATCH", [])
    keep = by_tag.get("KEEP", [])

    if drops:
        total_kb = sum(r["size_kb"] for r in drops)
        print(f"\n🔴 DROP_CANDIDATE — {len(drops)} indexes, {total_kb:.0f} KB reclaimable")
        print("-" * 100)
        for r in sorted(drops, key=lambda x: -x["size_kb"]):
            print(
                f"  {r['collection']:30s} {r['index']:40s} "
                f"{r['size_kb']:>8.1f} KB  {r['ops_per_day']:>6.1f} ops/d  "
                f"({r['reason']})"
            )
        print("\n  Suggested mongo shell commands (REVIEW BEFORE RUNNING):")
        for r in drops:
            print(f"    {r['drop_command']}")
    else:
        print("\n✅ DROP_CANDIDATE — none. All indexes look load-bearing.")

    if watch:
        print(f"\n🟡 WATCH — {len(watch)} low-usage indexes (re-check next month)")
        for r in sorted(watch, key=lambda x: -x["size_kb"])[:15]:
            print(
                f"  {r['collection']:30s} {r['index']:40s} "
                f"{r['size_kb']:>8.1f} KB  {r['ops_per_day']:>6.1f} ops/d  "
                f"({r['reason']})"
            )

    print(f"\n🟢 KEEP — {len(keep)} healthy indexes")
    print("═" * 100)

    if uptime_days < 7:
        print(
            "\n⚠️  Server uptime < 7 days. $indexStats counters reset on every "
            "restart, so DROP_CANDIDATE flags may be unreliable.\n"
            "   Re-run this audit after the cluster has been up for ≥ 7 days "
            "of normal traffic before dropping anything."
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--collection", "-c", default=None,
                    help="Audit just this one collection (default: all)")
    ap.add_argument("--min-size-kb", type=float, default=64.0,
                    help="Ignore indexes smaller than this (KB). Default 64.")
    ap.add_argument("--min-daily-ops", type=float, default=5.0,
                    help="Mark as DROP_CANDIDATE if used < N times/day. Default 5.")
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON instead of pretty report")
    args = ap.parse_args()

    asyncio.run(run(
        only_collection=args.collection,
        min_size_kb=args.min_size_kb,
        min_daily_ops=args.min_daily_ops,
        as_json=args.json,
    ))


if __name__ == "__main__":
    main()
