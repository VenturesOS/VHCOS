"""Fold the single-manager teams into the branch team they really belong to.

Client instruction (2026-09-20): Delhi is run by Maneet AND Manorma; Gurgaon
by Ajit, Jatin AND Rohit. Their revenue, joinings and targets must roll up as
ONE team per branch.

  • the branch team gains `additional_employer_ids` — every manager listed
    there sees that team's numbers, and can be counted as a contributor;
  • the now-redundant one-person teams are marked `status="merged"` (kept for
    history, excluded from every roll-up via `targets_service.TEAM_LIVE`).

Idempotent. Run:  python3 -m scripts.merge_branch_teams
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# branch team name → managers (by email) that must be counted with it
MERGES = {
    "Delhi Team": ["manorma@vhc.in"],
    "Gurgaon Team": ["ajit@vhc.in", "jatin@vhc.in", "rohit@vhc.in"],
}
# one-person teams that disappear into the branch team above
RETIRE = {"Manorma yadav Team": "Delhi Team", "Jatin Yadav Team": "Gurgaon Team"}


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()

    users = {}
    async for u in db.users.find({}, {"_id": 0, "id": 1, "email": 1, "name": 1}):
        users[str(u.get("email") or "").lower()] = u

    teams = {}
    async for t in db.teams.find({}, {"_id": 0}):
        teams[t["name"]] = t

    for team_name, manager_emails in MERGES.items():
        team = teams.get(team_name)
        if not team:
            print(f"!! team not found: {team_name}")
            continue
        ids, names = [], []
        for email in manager_emails:
            u = users.get(email)
            if not u:
                print(f"!! user not found: {email}")
                continue
            if u["id"] == team.get("employer_id"):
                continue
            ids.append(u["id"])
            names.append(u.get("name") or email)
        await db.teams.update_one(
            {"id": team["id"]},
            {"$set": {"additional_employer_ids": ids, "updated_at": now}},
        )
        print(f"{team_name}: co-managers → {names or 'none'}")

    for old_name, into in RETIRE.items():
        old, target = teams.get(old_name), teams.get(into)
        if not old or not target:
            continue
        if old.get("recruiter_ids"):
            print(f"!! {old_name} still has {len(old['recruiter_ids'])} recruiters — not retiring it")
            continue
        await db.teams.update_one(
            {"id": old["id"]},
            {"$set": {"status": "merged", "merged_into": target["id"], "updated_at": now}},
        )
        print(f"{old_name}: marked merged into {into}")


if __name__ == "__main__":
    asyncio.run(main())
