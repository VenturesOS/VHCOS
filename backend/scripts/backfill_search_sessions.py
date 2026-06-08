"""
Backfill search_sessions from historical application stage_history (Phase 56.6, 2026-06).

Per `/app/memory/XGBOOST_LTR_SCOPING.md` Phase 4: mine `applications` to
reconstruct labeled (recruiter, candidate, action) triplets from BEFORE
the LTR auto-capture telemetry was wired (2026-06-03).

For each application stage transition whose stage maps to an LTR action
(via STAGE_TO_LTR_ACTION), we synthesize a minimal `search_sessions`
document — single-candidate slate, single labeled action — tagged with
`source="backfill_stage_history"` so it's distinguishable from real
search-driven sessions.

Properties
----------
- Idempotent: each synthesized session is keyed by
  (application_id, stage, timestamp) — repeat runs replace, not duplicate.
- TTL-aware: sessions inherit the 180-day TTL via `expires_at`, but
  backfilled docs are likely older. We extend `expires_at` to 365 days
  from NOW so the training pipeline has time to consume them before
  MongoDB sweeps.
- Best-effort: skips stages not in STAGE_TO_LTR_ACTION, skips events
  with no `moved_by` (synthetic / system moves).

Usage
-----
    # Dry-run (default — counts only, NO writes)
    python -m scripts.backfill_search_sessions

    # Apply
    python -m scripts.backfill_search_sessions --apply

    # Limit (for testing)
    python -m scripts.backfill_search_sessions --apply --limit 100

Exit codes
----------
0 — success; non-zero on hard error.
"""
import argparse
import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, "/app/backend")

from config import db, initialize_db  # noqa: E402
from services.ltr_telemetry import STAGE_TO_LTR_ACTION  # noqa: E402

initialize_db()

logger = logging.getLogger("ltr_backfill")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


SOURCE_TAG = "backfill_stage_history"
TTL_DAYS_FROM_NOW = 365


def _parse_ts(raw) -> Optional[datetime]:
    """Stage history timestamps are stored as ISO strings in this app."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        # Strip trailing 'Z' if present
        s = raw.rstrip("Z") if isinstance(raw, str) and raw.endswith("Z") else raw
        return datetime.fromisoformat(s) if isinstance(s, str) else None
    except Exception:
        return None


async def _fetch_user_meta(user_ids: List[str]) -> Dict[str, dict]:
    """Bulk-fetch user role/email so each synthesized session is properly tagged."""
    if not user_ids:
        return {}
    cursor = db.users.find(
        {"id": {"$in": list(set(user_ids))}},
        {"_id": 0, "id": 1, "email": 1, "role": 1},
    )
    out: Dict[str, dict] = {}
    async for u in cursor:
        out[u["id"]] = u
    return out


async def backfill(apply: bool, limit: Optional[int]) -> dict:
    expires_at = datetime.now(timezone.utc) + timedelta(days=TTL_DAYS_FROM_NOW)

    # Schema reality (Jun 2026): `stage_history` only stores the initial
    # `sourced` entry. Subsequent stage transitions update `application.stage`
    # but don't append to history. So we mine from the CURRENT stage instead.
    # The current stage + updated_at IS the most recent labeled signal.
    #
    # Attribution chain for the actor:
    #   1. updated_by_id (if set by /applications endpoints — preferred)
    #   2. assigned_to (mandate assignee — owns subsequent moves typically)
    #   3. stage_history[0].moved_by (initial sourcer — final fallback)
    match_stages = list(STAGE_TO_LTR_ACTION.keys())
    pipeline = [
        {"$match": {"stage": {"$in": match_stages}}},
        {"$project": {
            "_id": 0,
            "application_id": "$id",
            "candidate_id": 1,
            "stage": 1,
            "updated_at": 1,
            "created_at": 1,
            "updated_by_id": 1,
            "assigned_to": 1,
            "stage_history": {"$slice": ["$stage_history", 1]},
        }},
    ]
    if limit:
        pipeline.append({"$limit": limit})

    cursor = db.applications.aggregate(pipeline, allowDiskUse=True)

    rows: List[dict] = []
    user_ids: List[str] = []
    async for r in cursor:
        # Resolve actor via attribution chain
        uid = r.get("updated_by_id") or r.get("assigned_to")
        if not uid:
            sh = (r.get("stage_history") or [{}])[0]
            uid = sh.get("moved_by")
        if not uid:
            continue
        r["_actor_id"] = uid
        rows.append(r)
        user_ids.append(uid)

    user_meta = await _fetch_user_meta(user_ids)
    logger.info(f"Loaded {len(user_meta)} user records for {len(set(user_ids))} unique ids")

    counts = {
        "events_total": len(rows),
        "skipped_no_user": 0,
        "skipped_no_ts": 0,
        "skipped_no_candidate": 0,
        "skipped_unknown_user": 0,
        "writes_planned": 0,
        "writes_applied": 0,
        "by_action": {},
    }

    ops: List[dict] = []
    for r in rows:
        uid = r["_actor_id"]
        cand_id = r.get("candidate_id")
        stage = r.get("stage")
        # Use updated_at as the action timestamp (when the stage was set);
        # fall back to created_at for very old records.
        ts = _parse_ts(r.get("updated_at")) or _parse_ts(r.get("created_at"))
        action = STAGE_TO_LTR_ACTION.get(stage)
        if not cand_id:
            counts["skipped_no_candidate"] += 1
            continue
        if not ts:
            counts["skipped_no_ts"] += 1
            continue
        if not action:
            continue
        user = user_meta.get(uid)
        if not user:
            counts["skipped_unknown_user"] += 1
            continue

        # Deterministic id keyed by (application, stage) — repeat runs
        # land on the same doc, so upsert is idempotent.
        backfill_key = f"{r['application_id']}|{stage}"
        sid = "bf-" + str(uuid.uuid5(uuid.NAMESPACE_DNS, backfill_key))

        doc = {
            "id": sid,
            "user_id": uid,
            "user_email": (user.get("email") or "").lower(),
            "user_role": user.get("role"),
            "ts": ts,
            "expires_at": expires_at,
            "source": SOURCE_TAG,
            "query": "",
            "query_meta": {
                "backfill_application_id": r["application_id"],
                "backfill_stage": stage,
            },
            "slate": [
                {"rank": 0, "candidate_id": cand_id, "score": None},
            ],
            "actions": [
                {
                    "candidate_id": cand_id,
                    "action": action,
                    "rank": 0,
                    "ts": ts,
                },
            ],
        }
        ops.append(doc)
        counts["writes_planned"] += 1
        counts["by_action"][action] = counts["by_action"].get(action, 0) + 1

    logger.info(f"Planned writes: {counts['writes_planned']} | skipped(no_user)={counts['skipped_no_user']} skipped(no_ts)={counts['skipped_no_ts']} skipped(unknown_user)={counts['skipped_unknown_user']}")
    logger.info(f"By action: {counts['by_action']}")

    if not apply:
        logger.info("DRY-RUN — no writes. Re-run with --apply to commit.")
        return counts

    # Bulk upsert in chunks
    from pymongo import ReplaceOne
    CHUNK = 1000
    applied = 0
    for i in range(0, len(ops), CHUNK):
        batch = ops[i : i + CHUNK]
        bulk = [ReplaceOne({"id": d["id"]}, d, upsert=True) for d in batch]
        if not bulk:
            continue
        res = await db.search_sessions.bulk_write(bulk, ordered=False)
        applied += (res.upserted_count or 0) + (res.modified_count or 0)
        logger.info(f"  chunk {i // CHUNK + 1}: upserted={res.upserted_count} modified={res.modified_count}")
    counts["writes_applied"] = applied
    logger.info(f"APPLIED {applied} writes.")
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write to MongoDB. Default = dry run.")
    parser.add_argument("--limit", type=int, default=None, help="Cap events processed (for testing).")
    args = parser.parse_args()
    result = asyncio.run(backfill(apply=args.apply, limit=args.limit))
    print()
    print("=" * 60)
    print(f"Backfill {'APPLIED' if args.apply else 'DRY-RUN'}")
    print("=" * 60)
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
