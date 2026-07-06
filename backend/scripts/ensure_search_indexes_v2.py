#!/usr/bin/env python3
"""
ensure_search_indexes_v2.py — VHC Talent OS search index migration
===================================================================

WHY THIS EXISTS
---------------
The quick-search path in routes/candidates.py fans every search word out
to 12 unanchored case-insensitive $regex conditions (× synonym
expansion). Unanchored /i regex can never use a B-tree index, so every
keystroke-search is a full collection scan over 139k+ candidate docs —
then the same filter runs AGAIN for the count. This script makes the
index-backed replacement (services/fast_search.py) possible.

WHAT IT DOES
------------
1. candidate_bank: drops the old narrow text index (name/email/skills)
   and creates ONE weighted text index across 13 fields the search
   actually queries.
2. Adds compound B-tree indexes matching real filter shapes.
3. Backfills `name_lower` / `email_lower` / `phone_normalized` mirror
   fields in resumable batches.
4. jobs: widens the job text index to include skills + location.

SAFE BY DEFAULT
---------------
Dry-run unless --apply is passed. Prints every action first.
Index builds run in the background (Mongo 4.2+) — no write lock.

USAGE
-----
    export MONGO_URL="mongodb+srv://..."   # never hardcode
    python ensure_search_indexes_v2.py            # dry run
    python ensure_search_indexes_v2.py --apply    # execute
    python ensure_search_indexes_v2.py --apply --skip-backfill
"""
import argparse
import asyncio
import os
import re
import sys
import time

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, TEXT, UpdateOne

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "vhc_talent_os")

if not MONGO_URL:
    sys.exit("MONGO_URL environment variable is required (never hardcode it).")

CANDIDATE_TEXT_INDEX = {
    "name": "candidate_search_text",
    "keys": [
        ("name", TEXT), ("key_skills", TEXT), ("skills", TEXT),
        ("current_designation", TEXT), ("designation", TEXT),
        ("headline", TEXT),
        ("current_employer", TEXT), ("current_company", TEXT), ("company", TEXT),
        ("current_location", TEXT), ("location", TEXT),
        ("profile_summary", TEXT), ("summary", TEXT),
    ],
    "weights": {
        "name": 10,
        "key_skills": 8, "skills": 8,
        "current_designation": 6, "designation": 6,
        "headline": 5,
        "current_employer": 4, "current_company": 4, "company": 4,
        "current_location": 3, "location": 3,
        "profile_summary": 2, "summary": 2,
    },
    "default_language": "none",
}

OLD_TEXT_INDEX_NAMES = ["text_search_idx"]

CANDIDATE_BTREE_INDEXES = [
    ([("total_experience_years", ASCENDING), ("created_at", DESCENDING)], {"name": "exp_total_created"}),
    ([("experience_years", ASCENDING), ("created_at", DESCENDING)], {"name": "exp_alias_created"}),
    ([("current_location", ASCENDING)], {"name": "cur_location", "sparse": True}),
    ([("smart_tags", ASCENDING)], {"name": "smart_tags_multikey", "sparse": True}),
    ([("notice_period_days", ASCENDING)], {"name": "notice_days", "sparse": True}),
    ([("enriched_seniority", ASCENDING), ("created_at", DESCENDING)], {"name": "seniority_created", "sparse": True}),
    ([("enriched_function", ASCENDING), ("created_at", DESCENDING)], {"name": "function_created", "sparse": True}),
    ([("name_lower", ASCENDING)], {"name": "name_lower_idx", "sparse": True}),
    ([("phone_normalized", ASCENDING)], {"name": "phone_norm_idx", "sparse": True}),
    ([("email_lower", ASCENDING)], {"name": "email_lower_idx", "sparse": True}),
]

JOB_TEXT_INDEX = {
    "name": "job_search_text",
    "keys": [("title", TEXT), ("description", TEXT), ("skills", TEXT), ("location", TEXT)],
    "weights": {"title": 10, "skills": 6, "location": 4, "description": 1},
    "default_language": "none",
}
OLD_JOB_TEXT_INDEX_NAMES = ["job_text_idx"]


async def existing_index_names(coll):
    return {ix["name"] async for ix in coll.list_indexes()}


async def ensure_text_index(coll, spec, old_names, apply):
    names = await existing_index_names(coll)
    for old in old_names:
        if old in names:
            print(f"  [-] drop {coll.name}.{old} (narrow text index — one text index allowed per collection)")
            if apply:
                await coll.drop_index(old)
    if spec["name"] in names:
        print(f"  [=] {coll.name}.{spec['name']} already present")
        return
    print(f"  [+] create {coll.name}.{spec['name']} (weighted, {len(spec['keys'])} fields)")
    if apply:
        await coll.create_index(
            spec["keys"], name=spec["name"],
            weights=spec["weights"], default_language=spec["default_language"],
        )


async def ensure_btree_indexes(coll, index_list, apply):
    names = await existing_index_names(coll)
    for keys, kwargs in index_list:
        if kwargs["name"] in names:
            print(f"  [=] {coll.name}.{kwargs['name']} already present")
            continue
        print(f"  [+] create {coll.name}.{kwargs['name']}  {keys}")
        if apply:
            try:
                await coll.create_index(keys, **kwargs)
            except Exception as e:
                print(f"      skipped ({e})")


DIGITS = re.compile(r"\D+")

async def backfill_mirrors(db, apply, batch=1000):
    coll = db.candidate_bank
    query = {"$or": [
        {"name": {"$type": "string"}, "name_lower": {"$exists": False}},
        {"email": {"$type": "string"}, "email_lower": {"$exists": False}},
        {"phone": {"$type": "string"}, "phone_normalized": {"$exists": False}},
    ]}
    total = await coll.count_documents(query)
    print(f"\n  Backfill needed on {total:,} documents "
          f"({'executing' if apply else 'dry run — not writing'})")
    if not apply or total == 0:
        return

    done = 0
    t0 = time.time()
    cursor = coll.find(query, {"_id": 1, "name": 1, "email": 1, "phone": 1})
    ops = []
    async for doc in cursor:
        s = {}
        if isinstance(doc.get("name"), str):
            s["name_lower"] = doc["name"].strip().lower()
        if isinstance(doc.get("email"), str):
            s["email_lower"] = doc["email"].strip().lower()
        if isinstance(doc.get("phone"), str):
            digits = DIGITS.sub("", doc["phone"])
            if digits:
                s["phone_normalized"] = digits[-10:] if len(digits) >= 10 else digits
        if s:
            ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": s}))
        if len(ops) >= batch:
            await coll.bulk_write(ops, ordered=False)
            done += len(ops)
            ops = []
            print(f"    ...{done:,}/{total:,} ({done / max(time.time() - t0, 1):,.0f} docs/s)")
    if ops:
        await coll.bulk_write(ops, ordered=False)
        done += len(ops)
    print(f"  Backfill complete: {done:,} documents in {time.time() - t0:,.1f}s")


async def main(apply: bool, skip_backfill: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    mode = "APPLY" if apply else "DRY RUN (pass --apply to execute)"
    print(f"\n{'=' * 68}\nVHC search index migration v2 — {mode}\nDatabase: {DB_NAME}\n{'=' * 68}")

    print("\ncandidate_bank — text index")
    await ensure_text_index(db.candidate_bank, CANDIDATE_TEXT_INDEX, OLD_TEXT_INDEX_NAMES, apply)

    print("\ncandidate_bank — B-tree indexes")
    await ensure_btree_indexes(db.candidate_bank, CANDIDATE_BTREE_INDEXES, apply)

    print("\njobs — text index")
    await ensure_text_index(db.jobs, JOB_TEXT_INDEX, OLD_JOB_TEXT_INDEX_NAMES, apply)

    if not skip_backfill:
        print("\ncandidate_bank — mirror-field backfill")
        await backfill_mirrors(db, apply)

    print(f"\n{'=' * 68}\nDone. Verify with: db.candidate_bank.getIndexes()\n"
          f"Then enable the new search path with FAST_SEARCH=1 (see\n"
          f"services/fast_search.py + docs/SEARCH_INTEGRATION_PATCH.md).\n{'=' * 68}\n")
    client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="execute (default: dry run)")
    ap.add_argument("--skip-backfill", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.apply, args.skip_backfill))
