"""
One-time backlog merge — Feb 2026 (Phase 54.22)

Scans the candidate_bank for groups of records that share the same email
OR same normalized phone, and merges each group into one master record
using the same logic as the existing `/api/candidates/merge-duplicates`
endpoint (the one wired into the "Merge All" button).

Safe to re-run — idempotent. Each merge is logged to `merge_audit_log`
with `source: bulk_backfill_phase54_22`.

Usage on EC2:
    cd /home/ubuntu/vhc-platform/backend
    source venv/bin/activate
    python scripts/merge_backlog_duplicates.py            # dry-run (default)
    python scripts/merge_backlog_duplicates.py --apply    # actually merge
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List


def _bootstrap() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    backend_root = os.path.dirname(here)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)


_bootstrap()
from config import db, initialize_db  # noqa: E402 (deferred import)
from services.candidate_merge import normalize_phone  # noqa: E402
from services.extension_service import _names_are_similar  # noqa: E402


SKIP_FIELDS = {"_id", "id", "created_at"}


def _match_score(a: Dict, b: Dict) -> int:
    """Returns 0-3: name_similar + email_exact + phone_exact."""
    score = 0
    if a.get("name") and b.get("name") and _names_are_similar(a["name"], b["name"]):
        score += 1
    ea = (a.get("email") or "").strip().lower()
    eb = (b.get("email") or "").strip().lower()
    if ea and eb and ea == eb:
        score += 1
    pa = a.get("phone_normalized") or normalize_phone(a.get("phone") or "")
    pb = b.get("phone_normalized") or normalize_phone(b.get("phone") or "")
    if pa and pb and pa == pb:
        score += 1
    return score


def _completeness(d: Dict) -> int:
    score = 0
    for k, v in d.items():
        if k.startswith("_") or k in ("id", "created_at", "updated_at"):
            continue
        if v and v != "" and v != [] and v != {}:
            score += 1
    return score


async def _find_groups() -> List[Dict]:
    """Same aggregation as /find-all-duplicates."""
    groups: List[Dict] = []

    # 1) duplicate emails
    keys = await db.candidate_bank.aggregate([
        {"$match": {"email": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": {"$toLower": "$email"}, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 500},
    ]).to_list(500)
    for k in keys:
        cands = await db.candidate_bank.find(
            {"email": {"$regex": f"^{k['_id']}$", "$options": "i"}},
            {"_id": 0},
        ).to_list(20)
        if len(cands) >= 2:
            groups.append({"reason": "email", "key": k["_id"], "members": cands})

    # 2) duplicate phones (skip ones we already merged via email)
    keys = await db.candidate_bank.aggregate([
        {"$match": {"phone_normalized": {
            "$exists": True, "$nin": [None, "", "0000000000"],
            "$regex": "^[0-9]{10}$",
        }}},
        {"$group": {"_id": "$phone_normalized", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 500},
    ]).to_list(500)
    for k in keys:
        cands = await db.candidate_bank.find(
            {"phone_normalized": k["_id"]},
            {"_id": 0},
        ).to_list(20)
        if len(cands) >= 2:
            groups.append({"reason": "phone", "key": k["_id"], "members": cands})

    return groups


async def _merge_group(group: Dict, apply: bool) -> Dict:
    docs = list(group["members"])
    if len(docs) < 2:
        return {"merged": 0, "skipped": []}

    # Pick the provisional master FIRST so we can score each donor against it.
    docs.sort(
        key=lambda d: (d.get("updated_at") or d.get("created_at") or "", _completeness(d)),
        reverse=True,
    )
    master_doc = dict(docs[0])
    master_id = master_doc["id"]

    actual_donors: List[Dict] = []
    skipped: List[Dict] = []
    for donor in docs[1:]:
        s = _match_score(master_doc, donor)
        if s >= 2:
            actual_donors.append(donor)
        else:
            skipped.append({
                "id": donor["id"],
                "name": donor.get("name"),
                "email": donor.get("email"),
                "phone": donor.get("phone"),
                "match_score": s,
                "reason": "needs 2-of-3 match (name+email+phone)",
            })

    if not actual_donors:
        return {
            "master_id": master_id, "master_name": master_doc.get("name"),
            "donor_ids": [], "donor_count": 0,
            "skipped": skipped, "merged": False,
        }

    # Merge fields from passing donors only
    for donor in actual_donors:
        for key, value in donor.items():
            if key in SKIP_FIELDS:
                continue
            master_val = master_doc.get(key)
            if not master_val and value:
                master_doc[key] = value
            elif isinstance(master_val, list) and isinstance(value, list):
                combined = list(master_val)
                existing = set(str(x) for x in combined)
                for item in value:
                    if str(item) not in existing:
                        combined.append(item)
                        existing.add(str(item))
                master_doc[key] = combined
            elif key in ("key_skills", "skills") and isinstance(master_val, str) and isinstance(value, str):
                existing_skills = set(s.strip().lower() for s in master_val.split(",") if s.strip())
                new_skills = [
                    s.strip() for s in value.split(",")
                    if s.strip() and s.strip().lower() not in existing_skills
                ]
                if new_skills:
                    master_doc[key] = master_val + ", " + ", ".join(new_skills)

    master_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    donor_ids = [d["id"] for d in actual_donors]

    master_doc["merge_history"] = master_doc.get("merge_history", [])
    master_doc["merge_history"].append({
        "merged_ids": donor_ids,
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "merged_by": "bulk_backfill_phase54_22",
        "reason": group["reason"],
        "key": group["key"],
        "skipped": skipped or None,
    })

    if not apply:
        return {
            "master_id": master_id, "master_name": master_doc.get("name"),
            "donor_ids": donor_ids, "donor_count": len(donor_ids),
            "skipped": skipped, "would_merge": True,
        }

    update_doc = {k: v for k, v in master_doc.items() if k != "_id"}
    await db.candidate_bank.replace_one({"id": master_id}, update_doc)
    if donor_ids:
        await db.candidate_bank.delete_many({"id": {"$in": donor_ids}})
        await db.applications.update_many(
            {"candidate_id": {"$in": donor_ids}},
            {"$set": {"candidate_id": master_id}},
        )

    try:
        await db.merge_audit_log.insert_one({
            "type": "bulk_backfill",
            "source": "bulk_backfill_phase54_22",
            "reason": group["reason"], "key": group["key"],
            "master_id": master_id, "master_name": master_doc.get("name"),
            "donor_ids": donor_ids, "skipped": skipped,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

    return {
        "master_id": master_id, "master_name": master_doc.get("name"),
        "donor_ids": donor_ids, "donor_count": len(donor_ids),
        "skipped": skipped, "merged": True,
    }


async def main(apply: bool) -> None:
    initialize_db()
    groups = await _find_groups()
    print(f"Found {len(groups)} duplicate group(s)\n")

    total_donors = 0
    total_skipped = 0
    for i, g in enumerate(groups, 1):
        names = ", ".join(sorted({m.get("name") or "?" for m in g["members"]}))
        prefix = "[APPLY]" if apply else "[DRY]"
        print(f"{prefix} Group {i:>2} ({g['reason']}={g['key']}): {names} "
              f"× {len(g['members'])}")
        res = await _merge_group(g, apply=apply)
        donors = res.get("donor_count", 0)
        skipped = res.get("skipped") or []
        total_donors += donors
        total_skipped += len(skipped)
        if donors:
            if apply:
                print(f"      → master='{res.get('master_name')}' "
                      f"id={(res.get('master_id') or '')[:12]} "
                      f"deleted {donors} donor(s)")
            else:
                print(f"      → would-merge {donors} donor(s) into "
                      f"'{res.get('master_name')}'")
        for sk in skipped:
            print(f"      ⚠ SKIPPED donor '{sk.get('name')}' "
                  f"(match_score={sk.get('match_score')}/3) — manual review needed")

    print()
    print(f"Records {'WERE' if apply else 'WOULD BE'} removed: {total_donors}")
    print(f"Donors skipped (low match score): {total_skipped}")
    if not apply:
        print("\nRe-run with --apply to actually perform the merges.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Actually perform merges (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
