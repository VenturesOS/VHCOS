"""Recover captures that were parked as identity observations and never saved.

From 28 Sept the capture endpoint only wrote an `identity_observations` row and
returned action="pending_review" with candidate_id=None, so ~8.8k profiles never
reached candidate_bank and no `sourced` pipeline row was created. The snapshot on
each observation IS the full candidate template (it carries mandate_id and
linked_mandates), so each one can be replayed.

Dedup mirrors the live capture path, oldest observation first, re-checking the
bank after every insert so the same person captured on three days collapses into
one record with three pipeline rows.

    python3 -m scripts.recover_parked_observations            # dry run
    python3 -m scripts.recover_parked_observations --apply
"""
import asyncio
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone

import pathlib

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

sys.path.insert(0, "/app/backend")
from services.extension_service import _names_are_similar, normalize_phone  # noqa: E402

STRIP = ("_id", "id", "identity", "_identity_trusted_anchors", "identity_evidence")


async def find_existing(db, snap: dict):
    """The same three signals the live capture uses, in the same order."""
    naukri_id = snap.get("naukri_profile_id")
    name = snap.get("name") or ""
    if naukri_id:
        hit = await db.candidate_bank.find_one({"naukri_profile_id": naukri_id},
                                               {"_id": 0, "id": 1, "name": 1})
        if hit and _names_are_similar(name, hit.get("name", "")):
            return hit, "naukri_id"

    phone = snap.get("phone_normalized") or normalize_phone(snap.get("phone") or "")
    email = (snap.get("email") or "").lower().strip()
    name_lower = snap.get("name_lower") or name.lower().strip()
    if not name_lower:
        return None, ""

    for q, why in (({"phone_normalized": phone} if phone else None, "phone"),
                   ({"email": email} if email else None, "email")):
        if not q:
            continue
        async for hit in db.candidate_bank.find({**q, "name_lower": name_lower},
                                                {"_id": 0, "id": 1, "name": 1}).limit(5):
            return hit, why

    # Name + source alone is never enough — require employer corroboration,
    # exactly like the capture path, or three different people with the same
    # name collapse into one record.
    emp = (snap.get("current_employer") or "").lower().strip()
    if emp:
        async for hit in db.candidate_bank.find(
            {"name_lower": name_lower, "source": {"$regex": "_extension$"}},
            {"_id": 0, "id": 1, "name": 1, "current_employer": 1},
        ).limit(20):
            if (hit.get("current_employer") or "").lower().strip() == emp:
                return hit, "employer"
    return None, ""


async def main(apply: bool, limit: int):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    stats = Counter()
    cursor = db.identity_observations.find({"status": "unresolved"}).sort("observed_at", 1)
    if limit:
        cursor = cursor.limit(limit)

    n = 0
    async for obs in cursor:
        n += 1
        snap = obs.get("snapshot") or {}
        name = (snap.get("name") or "").strip()
        if not name:
            stats["skipped_no_name"] += 1
            continue

        existing, why = await find_existing(db, snap)
        if existing:
            candidate_id = existing["id"]
            stats[f"linked_{why}"] += 1
        else:
            candidate_id = str(uuid.uuid4())
            doc = {k: v for k, v in snap.items() if k not in STRIP}
            doc.update({"_id": candidate_id, "id": candidate_id,
                        "identity_origin_observation_id": obs["_id"],
                        "recovered_from_observation": True})
            doc.setdefault("created_at", obs.get("observed_at"))
            doc["updated_at"] = datetime.now(timezone.utc).isoformat()
            if apply:
                await db.candidate_bank.insert_one(doc)
            stats["created"] += 1

        mandate_id = snap.get("mandate_id") or next(iter(snap.get("linked_mandates") or []), None)
        if mandate_id:
            dup = await db.applications.find_one(
                {"candidate_id": candidate_id, "job_id": mandate_id}, {"_id": 0, "id": 1})
            if dup:
                stats["app_existed"] += 1
            else:
                owner = snap.get("created_by") or obs.get("owner_id") or ""
                app = {
                    "id": str(uuid.uuid4()), "job_id": mandate_id, "candidate_id": candidate_id,
                    "candidate_name": name, "candidate_email": snap.get("email") or "",
                    "candidate_phone": snap.get("phone") or "",
                    "stage": "sourced", "status": "active", "source": "extension_capture",
                    "created_by": owner, "created_at": obs.get("observed_at"),
                    "updated_at": obs.get("observed_at"),
                    "recovered_from_observation": True,
                    "stage_history": [{"stage": "sourced", "moved_by": owner,
                                       "moved_by_name": "", "timestamp": obs.get("observed_at")}],
                }
                if apply:
                    await db.applications.insert_one(app)
                stats["app_created"] += 1
        else:
            stats["no_mandate"] += 1

        if apply:
            await db.identity_observations.update_one(
                {"_id": obs["_id"], "revision": obs.get("revision", 0)},
                {"$set": {"status": "linked", "candidate_id": candidate_id},
                 "$inc": {"revision": 1},
                 "$push": {"review_history": {
                     "decision": "recovered", "reason": "Capture parked by the 28 Sept "
                     "observation-only write; replayed into the bank and the sourced pipeline.",
                     "reviewer_id": "system", "reviewed_at": datetime.now(timezone.utc).isoformat(),
                     "candidate_id": candidate_id}}},
            )
        if n % 500 == 0:
            print(f"  …{n} processed {dict(stats)}", flush=True)

    print(("APPLIED " if apply else "DRY RUN ") + f"{n} observations: {dict(stats)}")
    c.close()


asyncio.run(main("--apply" in sys.argv,
                 int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), 0))))
