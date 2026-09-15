"""
Backfill `skills_lc` / `current_company_lc` / `location_lc` on candidate_bank.

These lowercased mirrors back the /candidate-bank/facets prefix search. A
case-sensitive `^prefix` regex against them is index-backed, versus a
full-collection scan when running case-insensitive regex on the raw
skills / current_company / location fields.

Idempotent — only touches docs where any of the three mirrors is missing.
Batched via bulk_write(500) to keep memory bounded on the 170 k row bank.

Can be run three ways:

    # 1) directly (dev / EC2)
    ./venv/bin/python -m scripts.backfill_candidate_lc

    # 2) via the async trigger inside admin endpoint
    from scripts.backfill_candidate_lc import run_backfill
    await run_backfill(db, progress_cb=my_cb)

    # 3) via the admin endpoint
    POST /api/admin/backfill-candidate-lc
    GET  /api/admin/backfill-candidate-lc/status
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable, Optional

from pymongo import UpdateOne

logger = logging.getLogger(__name__)

BATCH = 500


def _skills_lc(doc) -> list[str]:
    raw = doc.get("skills") or doc.get("key_skills") or []
    if not isinstance(raw, list):
        return []
    out = []
    for s in raw:
        if isinstance(s, str) and s.strip():
            out.append(s.strip().lower())
        elif isinstance(s, dict) and s.get("name"):
            out.append(str(s["name"]).strip().lower())
    return out


def _str_lc(*vals) -> Optional[str]:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return None


async def run_backfill(
    db,
    progress_cb: Optional[Callable[[dict], Awaitable[None]]] = None,
    batch: int = BATCH,
) -> dict:
    """Backfill lowercased mirrors for every doc missing any of them.

    progress_cb, if supplied, is awaited with a dict of counters every
    time a batch commits. Used by the admin endpoint to publish live
    status back to Mongo (`backfill_jobs` collection).
    """
    coll = db.candidate_bank

    # We deliberately skip a pre-count. `count_documents({$or: [{$exists:false}]})`
    # cannot use any index on a 170 k row bank and times out on the shared
    # Atlas tier. Instead we stream every doc in `id`-order (index-backed
    # cursor sort), decide per-doc whether it needs the mirrors, and
    # publish progress as we go. `total` in the status payload is the
    # estimated document count — good enough for a progress bar.
    total = await coll.estimated_document_count()
    logger.info(f"[Backfill LC] scanning ~{total} docs")
    if progress_cb:
        await progress_cb({"total": total, "processed": 0, "updated": 0, "phase": "running"})

    projection = {
        "_id": 0,
        "id": 1,
        "skills": 1,
        "key_skills": 1,
        "current_company": 1,
        "current_employer": 1,
        "location": 1,
        "current_location": 1,
        "skills_lc": 1,
        "current_company_lc": 1,
        "location_lc": 1,
    }
    # `no_cursor_timeout=True` keeps the server-side cursor alive for the
    # full 170 k row sweep (default is 10 min server-side idle). We close
    # explicitly in `finally` so the cursor never leaks.
    cursor = coll.find({}, projection).batch_size(batch)

    ops: list[UpdateOne] = []
    processed = 0
    updated = 0
    try:
        async for d in cursor:
            processed += 1
            cid = d.get("id")
            if not cid:
                continue
            # Skip docs that already carry all three mirrors — idempotency
            # short-circuit so re-runs don't rewrite the entire bank.
            if (
                "skills_lc" in d
                and "current_company_lc" in d
                and "location_lc" in d
            ):
                continue
            set_doc = {
                "skills_lc":          _skills_lc(d),
                "current_company_lc": _str_lc(d.get("current_company"), d.get("current_employer")),
                "location_lc":        _str_lc(d.get("location"), d.get("current_location")),
            }
            ops.append(UpdateOne({"id": cid}, {"$set": set_doc}))

            if len(ops) >= batch:
                res = await coll.bulk_write(ops, ordered=False)
                updated += res.modified_count
                ops = []
                if progress_cb:
                    await progress_cb({
                        "total": total, "processed": processed, "updated": updated, "phase": "running",
                    })
                await asyncio.sleep(0)

        if ops:
            res = await coll.bulk_write(ops, ordered=False)
            updated += res.modified_count
    finally:
        await cursor.close()

    logger.info(f"[Backfill LC] complete — processed={processed}, updated={updated}")
    if progress_cb:
        await progress_cb({
            "total": total, "processed": processed, "updated": updated, "phase": "done",
        })
    return {"total": total, "processed": processed, "updated": updated}


async def _main() -> None:
    from motor.motor_asyncio import AsyncIOMotorClient
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        raise RuntimeError("MONGO_URL environment variable is required.")
    db_name = os.environ.get("DB_NAME", "vhc_talent_os")
    client = AsyncIOMotorClient(mongo_url)
    try:
        await run_backfill(client[db_name])
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(_main())
