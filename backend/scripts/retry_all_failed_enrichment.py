"""Read-only inventory of missed enrichments. Backfill is NOT authorized.

This former retry utility deliberately cannot call an LLM or change candidates.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.parse_args()
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        count = await client[os.environ["DB_NAME"]].candidate_bank.count_documents({
            "source": {"$in": ["naukri_extension", "linkedin_extension", "naukri_mailer_extension", "foundit_extension"]},
            "enrichment_status": "failed",
        })
        print(json.dumps({"failed_extension_profiles": count, "dry_run": True, "retry_enabled": False}))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())