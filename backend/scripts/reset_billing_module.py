"""Reset the billing module to a clean slate and (re)enable accounts@vhc.in.

User-confirmed 2026-09-17: wipe every billing artefact (bills, invoices,
bank accounts, revenue entries, expenses, tally receipts) so invoice
numbering and all billing totals restart from zero, and make sure the
accounts@vhc.in login works with Bills & Invoices access.

Run: python3 -m scripts.reset_billing_module [--keep-data]
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from utils.auth import hash_password  # noqa: E402

BILLING_COLLECTIONS = [
    "bills",
    "invoices",
    "bill_bank_accounts",
    "revenue",
    "expenses",
    "tally_receipts",
]

ACCOUNTS_EMAIL = os.environ.get("BILLING_ACCOUNTS_EMAIL") or "accounts@vhc.in"
ACCOUNTS_PASSWORD = os.environ.get("ACCOUNTS_USER_PASSWORD") or "VhcAccounts@2026"


async def main(wipe: bool = True) -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    if wipe:
        for name in BILLING_COLLECTIONS:
            before = await db[name].count_documents({})
            res = await db[name].delete_many({})
            print(f"{name}: {before} -> {before - res.deleted_count} (deleted {res.deleted_count})")
        # Revenue captured inline on joined applications
        res = await db.applications.update_many(
            {"$or": [{"revenue": {"$exists": True}}, {"final_revenue": {"$exists": True}}]},
            {"$unset": {"revenue": "", "final_revenue": "", "revenue_status": ""}},
        )
        print(f"applications: cleared inline revenue on {res.modified_count}")

    now = datetime.now(timezone.utc).isoformat()
    existing = await db.users.find_one({"email": ACCOUNTS_EMAIL})
    doc = {
        "email": ACCOUNTS_EMAIL,
        "name": "VHC Accounts",
        "role": "accounts",
        "is_active": True,
        "password": hash_password(ACCOUNTS_PASSWORD),
        "requires_password_reset": False,
        "updated_at": now,
    }
    if existing:
        await db.users.update_one({"email": ACCOUNTS_EMAIL}, {"$set": doc})
        print(f"user {ACCOUNTS_EMAIL}: updated (role=accounts, password reset)")
    else:
        import uuid

        doc.update({"id": str(uuid.uuid4()), "created_at": now})
        await db.users.insert_one(doc)
        print(f"user {ACCOUNTS_EMAIL}: created")

    client.close()


if __name__ == "__main__":
    asyncio.run(main(wipe="--keep-data" not in sys.argv))
