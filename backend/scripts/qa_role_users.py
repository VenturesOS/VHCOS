"""Throwaway QA logins for the revenue/joining scoping tests.

Creates one `accounts` and one `employer` user so the role-scoping rules can
be exercised through the UI without touching a real person's password. The
QA employer is added to the Faridabad team as a co-manager.

    python3 -m scripts.qa_role_users create
    python3 -m scripts.qa_role_users remove     # deletes them + restores the team
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from utils.auth import hash_password  # noqa: E402

PASSWORD = "QaRevenue@2026"
USERS = [
    {"email": "qa_accounts_tmp@vhc.in", "name": "QA Accounts (temp)", "role": "accounts"},
    {"email": "qa_employer_tmp@vhc.in", "name": "QA Employer (temp)", "role": "employer"},
]
TEAM = "Faridabad team"


async def main(action: str):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    team = await db.teams.find_one({"name": TEAM}, {"_id": 0})

    if action == "remove":
        res = await db.users.delete_many({"email": {"$in": [u["email"] for u in USERS]}})
        if team:
            await db.teams.update_one(
                {"id": team["id"]},
                {"$pull": {"additional_employer_ids": {"$in": [
                    u["id"] for u in await db.users.find(
                        {"email": {"$in": [x["email"] for x in USERS]}}, {"_id": 0, "id": 1}).to_list(5)]}}},
            )
            # any id that no longer resolves to a user is dropped too
            ids = team.get("additional_employer_ids") or []
            alive = []
            for uid in ids:
                if await db.users.find_one({"id": uid}, {"_id": 1}):
                    alive.append(uid)
            await db.teams.update_one({"id": team["id"]}, {"$set": {"additional_employer_ids": alive}})
        print(f"removed {res.deleted_count} QA users; {TEAM} co-managers cleaned")
        return

    for spec in USERS:
        existing = await db.users.find_one({"email": spec["email"]}, {"_id": 0, "id": 1})
        uid = existing["id"] if existing else str(uuid.uuid4())
        await db.users.update_one(
            {"email": spec["email"]},
            {"$set": {
                "id": uid, "email": spec["email"], "name": spec["name"], "role": spec["role"],
                "password": hash_password(PASSWORD), "is_active": True,
                "requires_password_reset": False, "qa_temp": True, "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        print(f"{spec['role']:9} {spec['email']} / {PASSWORD}")
        if spec["role"] == "employer" and team:
            await db.teams.update_one({"id": team["id"]}, {"$addToSet": {"additional_employer_ids": uid}})
            print(f"           → co-manager of {TEAM}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "create"))
