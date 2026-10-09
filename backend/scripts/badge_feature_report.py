"""Evidence snapshot for the "Already in Database" badge feature.

Prints the numbers in /app/memory/ALREADY_IN_DATABASE_REVIEW.md so a reviewer
can reproduce them: code coverage across the bank, whether the rarity snapshot
exists, the daily badge telemetry, request latency and the indexes retrieval
depends on.

    python3 -m scripts.badge_feature_report
"""
import asyncio
import os
import pathlib

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    total = await db.candidate_bank.estimated_document_count()
    print(f"candidate_bank: {total}")
    for label, q in (("identity.codes present", {"identity.codes": {"$exists": True}}),
                     ("name_lower present", {"name_lower": {"$exists": True}})):
        n = await db.candidate_bank.count_documents(q, maxTimeMS=120000)
        print(f"  {label:26} {n:7} ({n * 100 / max(total, 1):.1f}%)")

    print(f"\nidentity_code_stats docs: {await db.identity_code_stats.estimated_document_count()}"
          f"  | frequency snapshot meta: {await db.identity_code_stats.find_one({'_id': '__meta__'})}")

    print("\nbadge telemetry (one row per day, written by the extension):")
    print(f"  {'day':12} {'scan calls':>11} {'cards scanned':>14} {'badges shown':>13}")
    for d in await db.badge_view_stats.find({}, {"_id": 0}).sort("day", -1).to_list(14):
        print(f"  {d.get('day', '?'):12} {d.get('scan_calls', 0):>11} "
              f"{d.get('scanned_count', 0):>14} {d.get('shown_count', 0):>13}")

    rows = await db.badge_audit.find(
        {}, {"_id": 0, "took_ms": 1, "batch_size": 1, "n_exists": 1}
    ).sort("ts", -1).limit(3000).to_list(3000)
    took = sorted(r["took_ms"] for r in rows if isinstance(r.get("took_ms"), int))
    if took:
        print(f"\nrequest latency over last {len(took)} audited calls: "
              f"median {took[len(took) // 2]} ms | p90 {took[int(len(took) * 0.9)]} ms "
              f"| max {took[-1]} ms")
    print(f"cards checked: {sum(r.get('batch_size') or 0 for r in rows)} | "
          f"n_exists total: {sum(r.get('n_exists') or 0 for r in rows)}")

    idx = await db.candidate_bank.index_information()
    print("\nindexes retrieval depends on:")
    for name, spec in idx.items():
        if any(k[0].startswith("identity") or k[0] in ("name_lower", "phone_normalized", "email")
               for k in spec.get("key", [])):
            print(f"  {name:34} {spec.get('key')}")
    c.close()


asyncio.run(main())
