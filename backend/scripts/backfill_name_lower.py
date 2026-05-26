"""
Backfill `name_lower` field on candidate_bank.

`name_lower` is a lowercased copy of `name` used by the indexed query in
`routes/extension_check.py` (the Naukri "Already in DB" badge check).
Without this field the regex falls back to case-insensitive matching on
`name`, which cannot use any index and triggers a 126k-doc COLLSCAN per
candidate — 25 cards × 1 COLLSCAN = ~2-3s per page on a shared Atlas tier.

Run once, on EC2:

    cd ~/vhc-platform/backend
    ./venv/bin/python -c "
    from dotenv import load_dotenv; load_dotenv()
    import runpy
    runpy.run_path('scripts/backfill_name_lower.py', run_name='__main__')
    "

The script is idempotent (re-running is safe). Uses bulk_write with batch
size 500 to keep memory bounded.
"""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL")
if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable is required.")
DB_NAME = os.environ.get("DB_NAME", "vhc_talent_os")

BATCH = 500


async def backfill() -> None:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    coll = db.candidate_bank

    # Only process docs that don't already have name_lower
    query = {"name_lower": {"$exists": False}}
    total = await coll.count_documents(query)
    if total == 0:
        print("✅ Nothing to backfill — every doc already has name_lower")
        return

    print(f"Found {total} docs missing name_lower. Backfilling in batches of {BATCH}…")

    from pymongo import UpdateOne

    cursor = coll.find(query, {"_id": 0, "id": 1, "name": 1}).batch_size(BATCH)
    ops: list[UpdateOne] = []
    processed = 0
    async for d in cursor:
        cid = d.get("id")
        name = d.get("name") or ""
        if not cid:
            continue
        ops.append(
            UpdateOne(
                {"id": cid},
                {"$set": {"name_lower": name.lower()}},
            )
        )
        if len(ops) >= BATCH:
            res = await coll.bulk_write(ops, ordered=False)
            processed += res.modified_count
            print(f"  …{processed}/{total} updated")
            ops = []
    if ops:
        res = await coll.bulk_write(ops, ordered=False)
        processed += res.modified_count

    print(f"✅ Backfill complete. {processed}/{total} docs updated.")


if __name__ == "__main__":
    asyncio.run(backfill())
