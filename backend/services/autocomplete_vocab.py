"""
autocomplete_vocab.py — precomputed suggestion vocabulary for
/api/candidate-bank/autocomplete.

The old endpoint ran 6 unanchored case-insensitive $regex aggregations
directly on candidate_bank (170K docs) per keystroke → 200s+ responses.
This service maintains a small `autocomplete_vocab` collection
({field, value, value_lower, count}) rebuilt in the background at most
once a day, so a suggestion query scans ~50K tiny docs in milliseconds.
"""
import asyncio
import logging
import re
import time

logger = logging.getLogger(__name__)

FIELDS = {
    "skills":      {"path": "skills",           "unwind": True},
    "designation": {"path": "designation",      "unwind": False},
    "company":     {"path": "current_employer", "unwind": False},
    "location":    {"path": "location",         "unwind": False},
    "industry":    {"path": "industry",         "unwind": False},
    "smart_tags":  {"path": "smart_tags",       "unwind": True},
}
VOCAB_COLL = "autocomplete_vocab"
META_ID = "_meta"
MAX_TERMS_PER_FIELD = 20000
REBUILD_AFTER_SECONDS = 24 * 3600
_rebuilding = False


async def get_suggestions(db, q: str, field: str = "all", limit: int = 10):
    """Returns (suggestions, seen_lowercase_set). Kicks off a background
    rebuild if the vocab is missing or stale — never blocks the request."""
    q_lower = (q or "").lower().strip()
    fields = list(FIELDS) if field == "all" else ([field] if field in FIELDS else ["skills"])

    asyncio.ensure_future(_maybe_rebuild(db))

    # Two-phase lookup: (1) prefix-anchored regex — uses the
    # (field, value_lower) index; (2) if short of results, word-boundary
    # match ("weld" → "MIG Welding") over the small vocab collection.
    base = {"field": {"$in": fields}}
    proj = {"_id": 0, "field": 1, "value": 1, "count": 1}
    fetch_n = limit * 5
    rows = await db[VOCAB_COLL].find(
        {**base, "value_lower": {"$regex": "^" + re.escape(q_lower)}}, proj
    ).sort("count", -1).limit(fetch_n).to_list(fetch_n)
    if len(rows) < fetch_n:
        rows += await db[VOCAB_COLL].find(
            {**base, "value_lower": {"$regex": r"\b" + re.escape(q_lower)}}, proj
        ).sort("count", -1).limit(fetch_n).to_list(fetch_n)

    seen, out = set(), []
    for r in rows:
        key = str(r["value"]).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": r["value"], "count": r["count"], "type": r["field"]})
    return out[:limit], seen


async def _maybe_rebuild(db):
    global _rebuilding
    if _rebuilding:
        return
    try:
        meta = await db[VOCAB_COLL].find_one({"_id": META_ID})
        now = time.time()
        if meta and (now - meta.get("built_at", 0)) < REBUILD_AFTER_SECONDS:
            return
        if meta and (now - meta.get("building_since", 0)) < 900:
            return  # another worker already claimed the rebuild
        _rebuilding = True
        await db[VOCAB_COLL].update_one(
            {"_id": META_ID}, {"$set": {"building_since": now}}, upsert=True
        )
        await _rebuild(db)
        await db[VOCAB_COLL].update_one(
            {"_id": META_ID},
            {"$set": {"built_at": time.time(), "building_since": 0}},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"[AutocompleteVocab] rebuild failed: {e}")
    finally:
        _rebuilding = False


async def _rebuild(db):
    t0 = time.time()
    await db[VOCAB_COLL].create_index([("field", 1), ("value_lower", 1)])
    await db[VOCAB_COLL].create_index([("field", 1), ("count", -1)])
    for fname, cfg in FIELDS.items():
        path = cfg["path"]
        pipeline = []
        if cfg["unwind"]:
            pipeline.append({"$unwind": f"${path}"})
        pipeline += [
            {"$match": {path: {"$type": "string", "$ne": ""}}},
            {"$group": {"_id": f"${path}", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": MAX_TERMS_PER_FIELD},
        ]
        rows = await db.candidate_bank.aggregate(
            pipeline, allowDiskUse=True
        ).to_list(MAX_TERMS_PER_FIELD)
        docs = [
            {
                "field": fname,
                "value": r["_id"],
                "value_lower": str(r["_id"]).lower(),
                "count": r["count"],
            }
            for r in rows
            if r["_id"] and isinstance(r["_id"], str)
        ]
        await db[VOCAB_COLL].delete_many({"field": fname})
        for i in range(0, len(docs), 5000):
            await db[VOCAB_COLL].insert_many(docs[i:i + 5000], ordered=False)
        logger.info(f"[AutocompleteVocab] {fname}: {len(docs)} terms")
    logger.info(f"[AutocompleteVocab] rebuilt in {time.time() - t0:.1f}s")
