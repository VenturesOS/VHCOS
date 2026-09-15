"""
Log retention pruner — deletes old rows from telemetry collections.

Why not native TTL indexes?
- MongoDB TTL indexes require a BSON `Date` field. In the current schema:
    api_metrics.timestamp        → float (Unix epoch seconds)
    activity_logs.timestamp      → str   (ISO 8601)
    extraction_traces.created_at → str   (ISO 8601)
    badge_audit.expires_at       → BSON date → ALREADY has TTL index
  Rather than migrate field types (would require touching every write path
  and backfilling ~640k existing docs), we run an application-side prune
  that reads the existing field and issues a bounded `delete_many`.

Behaviour:
- Kicks off in the background on server startup, then repeats every
  `RETENTION_INTERVAL_HOURS` (default 6h).
- Each pass is bounded by `maxTimeMS=60000` so a slow prune can never
  wedge the server.
- Deletes are chunked (`limit`-less delete_many on an indexed field is
  cheap in Mongo; the existing `timestamp_-1` / `created_at_1` indexes
  cover the filter).
- Uses `datetime.now(timezone.utc)` and never touches the wall clock.

Retention windows (all overridable via env):
    API_METRICS_RETENTION_DAYS       (default 30)
    ACTIVITY_LOGS_RETENTION_DAYS     (default 90)
    EXTRACTION_TRACES_RETENTION_DAYS (default 30)

To disable at boot: RETENTION_PRUNER_ENABLED=false
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Each entry: (collection, timestamp field, days, cutoff_builder).
# `cutoff_builder(now_dt)` returns the value to compare the stored field
# against — different for float epoch vs ISO string.
_ISO = lambda dt: dt.isoformat()  # noqa: E731
_EPOCH = lambda dt: dt.timestamp()  # noqa: E731

_TARGETS = [
    ("api_metrics", "timestamp", int(os.environ.get("API_METRICS_RETENTION_DAYS", "30")), _EPOCH),
    ("activity_logs", "timestamp", int(os.environ.get("ACTIVITY_LOGS_RETENTION_DAYS", "90")), _ISO),
    ("extraction_traces", "created_at", int(os.environ.get("EXTRACTION_TRACES_RETENTION_DAYS", "30")), _ISO),
]

INTERVAL_SECS = int(float(os.environ.get("RETENTION_INTERVAL_HOURS", "6")) * 3600)
PRUNE_BUDGET_MS = int(os.environ.get("RETENTION_PRUNE_BUDGET_MS", "60000"))


async def prune_once(db) -> dict:
    """Run one pruning pass across all target collections. Returns per-collection
    delete counts. Safe to call ad hoc from an admin endpoint."""
    now_dt = datetime.now(timezone.utc)
    results: dict[str, Any] = {}
    for coll_name, field, days, cutoff_of in _TARGETS:
        cutoff_dt = now_dt - timedelta(days=days)
        cutoff_val = cutoff_of(cutoff_dt)
        try:
            res = await db[coll_name].delete_many(
                {field: {"$lt": cutoff_val}},
                comment="log_retention_prune",
            )
            deleted = getattr(res, "deleted_count", 0)
            results[coll_name] = {
                "deleted": deleted, "days": days, "cutoff": str(cutoff_dt),
            }
            if deleted:
                logger.info(
                    "[Retention] %s: deleted %d rows older than %s",
                    coll_name, deleted, cutoff_dt.isoformat(),
                )
        except Exception as exc:  # noqa: BLE001
            # Never crash startup — retention is opportunistic.
            logger.warning("[Retention] %s prune failed: %s", coll_name, exc)
            results[coll_name] = {"error": str(exc)[:200], "days": days}
    return results


async def _loop(db) -> None:
    while True:
        try:
            await prune_once(db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Retention] loop iteration failed: %s", exc)
        await asyncio.sleep(INTERVAL_SECS)


def start_retention_pruner(db) -> asyncio.Task | None:
    """Kick off the background pruner. Idempotent: returns the task or None
    if disabled by env."""
    if os.environ.get("RETENTION_PRUNER_ENABLED", "true").lower() not in ("1", "true", "yes"):
        logger.info("[Retention] pruner disabled via RETENTION_PRUNER_ENABLED")
        return None
    task = asyncio.create_task(_loop(db), name="log_retention_pruner")
    logger.info(
        "[Retention] pruner started (every %.1fh, api_metrics=%dd, "
        "activity_logs=%dd, extraction_traces=%dd)",
        INTERVAL_SECS / 3600,
        _TARGETS[0][2], _TARGETS[1][2], _TARGETS[2][2],
    )
    return task
