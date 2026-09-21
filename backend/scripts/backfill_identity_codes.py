"""Explicit, resumable identity-index migration; dry-run unless --apply is set.

Example (use a local/staging database first):
  python backend/scripts/backfill_identity_codes.py --uri mongodb://localhost:27017 --database vhcos_test

Pass --apply to write signatures/dictionary entries and create indexes. Resume
with --after-id using the exact Extended JSON value printed as resume_after_id.
This script never imports application config or reads production environment
variables. Dry-run performs reads only and prints counts, not candidate data.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Script invocation from either repository root or backend/ is supported.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))

# Direct sibling imports intentionally avoid services/__init__.py, which
# initializes unrelated production clients even for an innocent --help.
from identity_resolution import build_identity_signature  # noqa: E402
from identity_store import bootstrap_identity_indexes, persist_candidate_identity, refresh_identity_frequencies  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--uri", required=True, help="Explicit MongoDB URI; never read from app configuration")
    parser.add_argument("--database", required=True, help="Explicit database name")
    parser.add_argument("--apply", action="store_true", help="Write code entries/signatures and create indexes")
    parser.add_argument("--refresh-frequencies", action="store_true", help="After a successful --apply, publish corpus code frequencies; skipped in dry-run")
    parser.add_argument("--after-id", help="Resume strictly after this BSON Extended JSON _id")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=0, help="Maximum candidates; zero scans the rest")
    return parser


async def run(args: argparse.Namespace) -> int:
    from bson import json_util
    from motor.motor_asyncio import AsyncIOMotorClient

    if not 1 <= args.batch_size <= 1000 or args.limit < 0:
        raise ValueError("batch-size must be 1..1000 and limit must be non-negative")
    query = {}
    if args.after_id is not None:
        query["_id"] = {"$gt": json_util.loads(args.after_id)}
    client = AsyncIOMotorClient(args.uri, serverSelectionTimeoutMS=10000)
    counts = {"scanned": 0, "updated": 0, "unchanged": 0, "would_update": 0, "stale": 0, "failed": 0}
    last_id = None
    try:
        db = client[args.database]
        if args.apply:
            await bootstrap_identity_indexes(db)
        cursor = db.candidate_bank.find(query).sort("_id", 1).batch_size(args.batch_size)
        if args.limit:
            cursor = cursor.limit(args.limit)
        async for candidate in cursor:
            counts["scanned"] += 1
            try:
                if args.apply:
                    result = await persist_candidate_identity(db, candidate)
                    if result["status"] == "stale":
                        fresh = await db.candidate_bank.find_one({"_id": candidate["_id"]})
                        if fresh is not None:
                            result = await persist_candidate_identity(db, fresh)
                    counts[result["status"]] += 1
                else:
                    signature = build_identity_signature(candidate)
                    counts["unchanged" if candidate.get("identity") == signature else "would_update"] += 1
            except Exception as exc:
                counts["failed"] += 1
                # Exception text can contain connection credentials or profile
                # contents; only emit the exception type.
                print(json.dumps({"error_type": type(exc).__name__, "position": counts["scanned"]}), file=sys.stderr)
                # Do not advance the checkpoint past a failed record.
                break
            if counts["stale"]:
                # Resume must retry a concurrently changing record too.
                break
            last_id = candidate["_id"]
            if counts["scanned"] % args.batch_size == 0:
                print(json.dumps({
                    "event": "checkpoint", "scanned": counts["scanned"],
                    "resume_after_id": json_util.dumps(last_id),
                }), flush=True)
        frequencies = {"status": "not_requested"}
        frequency_failed = False
        if args.refresh_frequencies:
            if not args.apply:
                frequencies = {"status": "skipped", "reason": "dry-run"}
            elif counts["failed"] or counts["stale"]:
                frequencies = {"status": "skipped", "reason": "backfill_incomplete"}
            else:
                try:
                    frequencies = {"status": "published", **await refresh_identity_frequencies(db)}
                except Exception as exc:
                    frequency_failed = True
                    frequencies = {"status": "failed", "error_type": type(exc).__name__}
        print(json.dumps({
            "mode": "apply" if args.apply else "dry-run",
            **counts,
            "resume_after_id": json_util.dumps(last_id) if last_id is not None else args.after_id,
            "frequencies": frequencies,
        }))
        return 1 if counts["failed"] or counts["stale"] or frequency_failed else 0
    finally:
        client.close()


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__, "message": "Backfill did not complete; check the explicit connection and arguments."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
