"""Find near-duplicate hires the exact name match misses.

`unified_joinings` matches a tracker row to a pipeline application on the
candidate's name with the letters normalised. A transposed letter — "Deepak
Muadillar" vs "Deepak Maudillar" — slips through and the same hire is listed
twice. No money is double-counted while the pipeline copy has no revenue, but
it would be the moment someone fills it in.
"""
import asyncio
import os
import sys
from difflib import SequenceMatcher

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from services.branch_revenue import norm_name  # noqa: E402

THRESHOLD = 0.85


def close(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    ledger = await db.placement_ledger.find(
        {}, {"_id": 0, "id": 1, "candidate_name": 1, "recruiter_name": 1, "recruiter_id": 1,
             "organization": 1, "doj": 1, "revenue": 1, "payment_status": 1, "branch": 1},
    ).to_list(1000)
    apps = await db.applications.find(
        {"stage": "joined"}, {"_id": 0, "id": 1, "candidate_name": 1, "created_by": 1, "join_date": 1},
    ).to_list(1000)

    exact = {norm_name(r["candidate_name"]) for r in ledger}

    print("=== pipeline rows that are probably a tracker hire under a different spelling")
    pairs = 0
    for a in apps:
        n = norm_name(a.get("candidate_name"))
        if not n or n in exact:
            continue
        for r in ledger:
            rn = norm_name(r["candidate_name"])
            score = close(n, rn)
            same_person = score >= THRESHOLD
            if not same_person and sorted(n) == sorted(rn):
                same_person, score = True, 1.0   # anagram = transposed letters
            if same_person:
                pairs += 1
                print(f"  {score:.2f}  pipeline '{a.get('candidate_name')}' (app {a['id'][:8]})"
                      f"  ~  tracker '{r['candidate_name']}' | {r['branch']} | {r['recruiter_name']}"
                      f" | {r['organization']} | {r['doj']} | ₹{r['revenue']:,.0f} {r['payment_status']}")
                break
    print(f"  → {pairs} likely duplicates across the two systems")

    print("=== the same person twice inside the tracker itself")
    seen = {}
    dupes = 0
    for r in ledger:
        key = norm_name(r["candidate_name"])
        if key in seen:
            other = seen[key]
            dupes += 1
            print(f"  '{r['candidate_name']}' ×2 | {other['organization']} ₹{other['revenue']:,.0f}"
                  f" vs {r['organization']} ₹{r['revenue']:,.0f} | {other['doj']} / {r['doj']}")
        else:
            seen[key] = r
    for i, a in enumerate(ledger):
        for b in ledger[i + 1:]:
            na, nb = norm_name(a["candidate_name"]), norm_name(b["candidate_name"])
            if na == nb:
                continue
            if sorted(na) == sorted(nb) or close(na, nb) >= 0.92:
                dupes += 1
                print(f"  near: '{a['candidate_name']}' ({a['organization']}, {a['doj']}, ₹{a['revenue']:,.0f})"
                      f"  ~  '{b['candidate_name']}' ({b['organization']}, {b['doj']}, ₹{b['revenue']:,.0f})")
    print(f"  → {dupes} duplicate / near-duplicate pairs inside the tracker")


if __name__ == "__main__":
    asyncio.run(main())
