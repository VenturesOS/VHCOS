"""
Precomputed facet cache for the Salary Benchmarking page (fix.docx 2026-09-15).

The dropdowns need up to ~500 alphabetically-sorted options per field
(location, company, skills, designation, industry). Doing a $group over
the 178 k-row candidate_bank on Atlas M10 exceeds every reasonable
timeout (> 30 s even on the indexed `_lc` mirror). We instead stream
every doc once via cursor — the same trick the `_lc` backfill uses —
count values in-process, and stash the top 500 per field into a small
`facet_cache` collection so the API can serve dropdowns in ~10 ms.

Rebuild strategy:
  1. Admin endpoint `/api/admin/rebuild-facet-cache` kicks off a
     background rebuild. Idempotent.
  2. On startup the lifespan hook rebuilds if the newest cache doc is
     older than `FACET_CACHE_TTL_HOURS`.
  3. The suggestions endpoint reads directly from the collection.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

FACET_CACHE_COLL = "facet_cache"
# Refresh no more than once a day — dropdown values are extremely stable.
FACET_CACHE_TTL_HOURS = 24
# Cap emitted per field. 500 covers every realistic dropdown on a
# 178 k-row bank (top-500 city / company by frequency).
TOP_N = 500


def _skill_tokens(doc) -> list[str]:
    raw = doc.get("skills_lc") or []
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, str) and s]
    return []


async def rebuild_facet_cache(
    db,
    progress_cb: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """Stream every candidate_bank doc once, count values per field,
    write top-N per field into `facet_cache`."""
    t0 = time.time()
    projection = {
        "_id": 0,
        "location_lc": 1, "location": 1, "current_location": 1,
        "current_company_lc": 1, "current_company": 1, "current_employer": 1,
        "skills_lc": 1,
        "designation": 1,
        "industry": 1,
    }

    # value_lc → (Counter of raw display strings, total count)
    counters: dict[str, dict[str, Counter]] = {
        "location":    {"c": Counter(), "d": {}},
        "company":     {"c": Counter(), "d": {}},
        "skills":      {"c": Counter(), "d": {}},
        "designation": {"c": Counter(), "d": {}},
        "industry":    {"c": Counter(), "d": {}},
    }

    cursor = db.candidate_bank.find({}, projection).batch_size(500)
    processed = 0
    try:
        async for d in cursor:
            processed += 1
            # Location
            k = d.get("location_lc")
            if k:
                counters["location"]["c"][k] += 1
                if k not in counters["location"]["d"]:
                    counters["location"]["d"][k] = d.get("location") or d.get("current_location") or k
            # Company
            k = d.get("current_company_lc")
            if k:
                counters["company"]["c"][k] += 1
                if k not in counters["company"]["d"]:
                    counters["company"]["d"][k] = d.get("current_company") or d.get("current_employer") or k
            # Skills (multi)
            for tok in _skill_tokens(d):
                counters["skills"]["c"][tok] += 1
                if tok not in counters["skills"]["d"]:
                    counters["skills"]["d"][tok] = tok  # already lowercased canonical
            # Designation (raw)
            v = (d.get("designation") or "").strip()
            if v:
                lc = v.lower()
                counters["designation"]["c"][lc] += 1
                if lc not in counters["designation"]["d"]:
                    counters["designation"]["d"][lc] = v
            # Industry (raw)
            v = (d.get("industry") or "").strip()
            if v:
                lc = v.lower()
                counters["industry"]["c"][lc] += 1
                if lc not in counters["industry"]["d"]:
                    counters["industry"]["d"][lc] = v

            if processed % 20000 == 0:
                if progress_cb:
                    await progress_cb({"processed": processed, "phase": "streaming"})
                await asyncio.sleep(0)
    finally:
        await cursor.close()

    now_iso = datetime.now(timezone.utc).isoformat()
    written = 0
    coll = db[FACET_CACHE_COLL]
    for field, buckets in counters.items():
        top = buckets["c"].most_common(TOP_N)
        values = [
            {"value": buckets["d"].get(lc, lc), "value_lc": lc, "count": n}
            for lc, n in top
        ]
        # Alphabetize AFTER top-N pick so the UI drops the list in A→Z order.
        values.sort(key=lambda x: x["value"].lower())
        await coll.replace_one(
            {"_id": f"salary__{field}"},
            {
                "_id": f"salary__{field}",
                "field": field,
                "values": values,
                "generated_at": now_iso,
                "source_count": buckets["c"].total() if hasattr(buckets["c"], "total") else sum(buckets["c"].values()),
                "distinct_count": len(buckets["c"]),
            },
            upsert=True,
        )
        written += len(values)

    dt = time.time() - t0
    logger.info(f"[FacetCache] rebuilt {written} rows across 5 fields — scanned {processed} docs in {dt:.1f}s")
    if progress_cb:
        await progress_cb({"processed": processed, "phase": "done", "written": written, "elapsed_s": round(dt, 1)})
    return {"processed": processed, "written": written, "elapsed_s": round(dt, 1)}


async def get_cached_facet(db, field: str) -> Optional[dict]:
    return await db[FACET_CACHE_COLL].find_one({"_id": f"salary__{field}"})


async def is_cache_stale(db) -> bool:
    """True if any facet doc is missing or older than TTL."""
    now = datetime.now(timezone.utc)
    for field in ("location", "company", "skills", "designation", "industry"):
        doc = await db[FACET_CACHE_COLL].find_one({"_id": f"salary__{field}"}, {"generated_at": 1})
        if not doc:
            return True
        try:
            gen = datetime.fromisoformat(doc["generated_at"])
        except Exception:
            return True
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=timezone.utc)
        if (now - gen).total_seconds() > FACET_CACHE_TTL_HOURS * 3600:
            return True
    return False
