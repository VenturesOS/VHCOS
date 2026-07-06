#!/usr/bin/env python3
"""
canonicalize_aliases.py — one-time migration to eliminate alias-field duality.

The candidate_bank schema evolved through several import pipelines and now
carries three overlapping name families:
  • skills / key_skills               (Naukri vs LinkedIn import)
  • location / current_location       (JD vs candidate view)
  • company / current_company / current_employer   (three names for one thing)

Every query today has to $or across the alias set, every filter has to know
about both, and every index has to be duplicated. This script picks ONE
canonical field per family and copies missing values into it — non-destructive
(aliases are left in place so old code paths keep reading), dry-run by
default, resumable.

Canonical choices (matches what services/fast_search.py's LIST_PROJECTION
already returns first):
  • skills            (drop key_skills into skills if skills is missing)
  • current_location  (widely already used; drop location into it)
  • current_employer  (drop current_company and company into it)

Usage:
    python scripts/canonicalize_aliases.py            # dry run
    python scripts/canonicalize_aliases.py --apply    # execute
    python scripts/canonicalize_aliases.py --apply --batch 2000

Once the writing side is updated (candidate create/update handlers should
also set only the canonical field going forward), a follow-up sweep can
drop the alias fields entirely with a second pass — but that's a separate
ship because it changes read-path expectations.
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "vhc_talent_os")
if not MONGO_URL:
    sys.exit("MONGO_URL is required.")


# canonical <- fallback list (first non-empty alias wins)
ALIAS_MAP = {
    "skills":            ["key_skills"],
    "current_location":  ["location"],
    "current_employer":  ["current_company", "company"],
}


def _empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, (list, tuple)) and len(v) == 0:
        return True
    return False


async def run(apply: bool, batch: int):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    coll = db.candidate_bank
    mode = "APPLY" if apply else "DRY RUN"
    print(f"\n{'=' * 60}\ncandidate_bank canonicalization — {mode}\n{'=' * 60}")

    # Find docs where any canonical is missing/empty AND at least one alias
    # has a value. `$expr` would be cleaner but this simple $or is index-
    # friendly and easy to reason about.
    or_clauses = []
    for canonical, fallbacks in ALIAS_MAP.items():
        for fb in fallbacks:
            or_clauses.append({
                "$and": [
                    {canonical: {"$in": [None, "", []]}},
                    {fb: {"$nin": [None, "", []]}},
                ]
            })
    query = {"$or": or_clauses}

    total = await coll.count_documents(query)
    print(f"\nCandidates needing canonicalization: {total:,}")
    if total == 0:
        print("Nothing to do.")
        client.close()
        return
    if not apply:
        # Preview a handful.
        print("\nSample (first 3 docs and what would change):")
        async for doc in coll.find(query).limit(3):
            for canonical, fallbacks in ALIAS_MAP.items():
                if _empty(doc.get(canonical)):
                    for fb in fallbacks:
                        v = doc.get(fb)
                        if not _empty(v):
                            print(f"  {doc.get('id', doc['_id'])}: {canonical} <- {fb} = {v!r:.80}")
                            break
        print("\nRun again with --apply to execute.")
        client.close()
        return

    done = 0
    t0 = time.time()
    ops = []
    projection = {"_id": 1, "id": 1}
    for canonical, fbs in ALIAS_MAP.items():
        projection[canonical] = 1
        for fb in fbs:
            projection[fb] = 1

    async for doc in coll.find(query, projection):
        set_ops = {}
        for canonical, fallbacks in ALIAS_MAP.items():
            if _empty(doc.get(canonical)):
                for fb in fallbacks:
                    v = doc.get(fb)
                    if not _empty(v):
                        set_ops[canonical] = v
                        break
        if set_ops:
            ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": set_ops}))
        if len(ops) >= batch:
            await coll.bulk_write(ops, ordered=False)
            done += len(ops)
            ops = []
            rate = done / max(time.time() - t0, 1)
            print(f"  ...{done:,}/{total:,} ({rate:,.0f} docs/s)")
    if ops:
        await coll.bulk_write(ops, ordered=False)
        done += len(ops)
    print(f"\nDone: {done:,} documents canonicalized in {time.time() - t0:.1f}s.")
    client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=1000)
    args = ap.parse_args()
    asyncio.run(run(args.apply, args.batch))
