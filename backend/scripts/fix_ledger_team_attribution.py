"""Put every tracker row on the team its recruiter actually belongs to.

Three 2026 rows still carried the team they were imported under (Bengaluru)
while the recruiter had moved — Madhuri Singh's ₹74,970 sat on Bengaluru but
counted towards Faridabad in the targets roll-up, so the employer's Joining
List and their target card disagreed by exactly that amount. Targets
attribute revenue by recruiter, so the ledger follows the recruiter.
"""
import asyncio
import os
import sys

import pathlib

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main(apply: bool):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    from services import targets_service as ts
    teams = await ts.live_teams(db)
    names = {t["id"]: t.get("name") for t in teams}
    owner = {uid: tid for tid, ids in ts.canonical_team_members(teams).items() for uid in ids}

    # The branch column is what the branch revenue dashboard groups by, so it
    # has to move with the team or the two views disagree again. Read each
    # team's branch from the rows it already owns.
    branch_of: dict = {}
    for tid in names:
        agg = await db.placement_ledger.aggregate([
            {"$match": {"team_id": tid, "void": {"$ne": True}, "branch": {"$nin": [None, ""]}}},
            {"$group": {"_id": "$branch", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}, {"$limit": 1},
        ]).to_list(1)
        if agg:
            branch_of[tid] = agg[0]["_id"]

    fixed = 0
    async for r in db.placement_ledger.find(
        {"void": {"$ne": True}},
        {"_id": 0, "id": 1, "candidate_name": 1, "revenue": 1, "team_id": 1, "branch": 1,
         "recruiter_id": 1, "recruiter_name": 1, "doj": 1},
    ):
        own = owner.get(r.get("recruiter_id") or "")
        if not own or r.get("team_id") == own:
            continue
        branch = branch_of.get(own) or r.get("branch") or ""
        print(f"{r.get('doj')} {r.get('candidate_name')!r} {r.get('recruiter_name')} "
              f"₹{r.get('revenue')} : {names.get(r.get('team_id')) or r.get('team_id')!r}"
              f"/{r.get('branch')} → {names.get(own)}/{branch}")
        fixed += 1
        if apply:
            await db.placement_ledger.update_one(
                {"id": r["id"]},
                {"$set": {"team_id": own, "team_name": names.get(own) or "", "branch": branch,
                          "team_fixed_from": r.get("team_id") or ""}},
            )
    print(("fixed " if apply else "would fix ") + str(fixed) + " rows")
    c.close()


asyncio.run(main("--apply" in sys.argv))
