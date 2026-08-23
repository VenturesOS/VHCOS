"""
Candidate Hygiene — detect and repair cross-contaminated candidate records.

Root cause (fixed Feb 2026): the extension's name+source dedupe shortcut treated
"same name + naukri_extension" as sufficient identity, collapsing distinct real
humans (e.g. 3 different "Pritam Kumar"s) into a single candidate_bank record.
Each subsequent recapture overwrote the previous person's employer / phone /
summary — leading to Frankenstein records with wildly different identities.

Detection: group naukri_capture_logs by candidate_id, flag records where 2+
distinct emails OR phone-last-4s appear across captures.

Repair: /split/{cid} groups captures by dominant email → creates a new
candidate_bank record per email bucket → moves capture_logs to the new
candidate_ids → archives the original polluted record in
merged_conflicts_backup for undo.

Endpoints (admin only):
  GET  /api/admin/candidate-hygiene/conflicts?severity=email|phone|all&limit=100
  GET  /api/admin/candidate-hygiene/detail/{cid}
  POST /api/admin/candidate-hygiene/split/{cid}?dry_run=true|false
  POST /api/admin/candidate-hygiene/undo-split/{backup_id}   (admin@vhc.in only)
"""
from __future__ import annotations
import uuid
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.auth import require_role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/candidate-hygiene", tags=["Candidate Hygiene"])


async def get_db():
    from config import db
    return db


def _phone_last4(v: str) -> str:
    return ''.join(c for c in (v or '') if c.isdigit())[-4:]


async def _build_conflict_index(db, limit: Optional[int] = None):
    """Aggregate every candidate_id's captured identities. Returns
    dict[cid] = {'emails': set, 'phones': set, 'employers': set,
                 'captures': [{email, phone_last4, employer, ts, log_id}]}
    """
    per_cand: dict[str, dict] = {}
    proj = {"candidate_id": 1, "candidate_email": 1, "candidate_phone": 1,
            "candidate_name": 1, "captured_data": 1, "timestamp": 1, "id": 1}
    cursor = db.naukri_capture_logs.find(
        {"candidate_id": {"$exists": True, "$ne": ""}}, proj
    )
    async for l in cursor:
        cid = l.get("candidate_id")
        if not cid:
            continue
        cap = l.get("captured_data") or {}
        email = (l.get("candidate_email") or cap.get("email") or "").strip().lower()
        phone_raw = (l.get("candidate_phone") or cap.get("phone") or "").strip()
        p4 = _phone_last4(phone_raw)
        emp = (cap.get("current_employer") or cap.get("current_company") or "").strip()
        node = per_cand.setdefault(cid, {
            "emails": set(), "phones": set(), "employers": set(),
            "captures": [], "candidate_name": l.get("candidate_name", ""),
        })
        if email: node["emails"].add(email)
        if p4:    node["phones"].add(p4)
        if emp:   node["employers"].add(emp.lower()[:60])
        node["captures"].append({
            "log_id": l.get("id"), "email": email, "phone_last4": p4,
            "employer": emp, "timestamp": l.get("timestamp", ""),
        })
    return per_cand


@router.get("/conflicts")
async def list_conflicts(
    severity: str = Query("all", pattern="^(email|phone|all)$"),
    limit: int = Query(100, ge=1, le=1000),
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """List candidate_bank records where 2+ distinct identities are merged."""
    idx = await _build_conflict_index(db)
    rows = []
    for cid, node in idx.items():
        n_email = len(node["emails"])
        n_phone = len(node["phones"])
        conflict_type = None
        if n_email >= 2:
            conflict_type = "email"
        elif n_phone >= 2:
            conflict_type = "phone"
        else:
            continue
        if severity != "all" and severity != conflict_type:
            continue
        rows.append({
            "candidate_id": cid,
            "candidate_name": node["candidate_name"],
            "conflict_type": conflict_type,
            "n_distinct_emails": n_email,
            "n_distinct_phones": n_phone,
            "n_captures": len(node["captures"]),
            "sample_emails": sorted(node["emails"])[:3],
            "sample_employers": sorted(node["employers"])[:3],
        })
    # sort by damage severity: most distinct identities first
    rows.sort(key=lambda r: (-max(r["n_distinct_emails"], r["n_distinct_phones"]),
                              -r["n_captures"]))
    return {"total": len(rows), "rows": rows[:limit]}


@router.get("/detail/{candidate_id}")
async def conflict_detail(
    candidate_id: str,
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Full capture-log breakdown for one contaminated candidate + current
    bank state, so admin can decide how to split."""
    bank = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not bank:
        raise HTTPException(404, "Candidate not found")

    logs = []
    async for l in db.naukri_capture_logs.find(
        {"candidate_id": candidate_id}, {"_id": 0}
    ).sort("timestamp", -1):
        cap = l.get("captured_data") or {}
        logs.append({
            "log_id": l.get("id"),
            "timestamp": l.get("timestamp", ""),
            "email": (l.get("candidate_email") or cap.get("email") or "").strip().lower(),
            "phone": (l.get("candidate_phone") or cap.get("phone") or "").strip(),
            "phone_last4": _phone_last4(l.get("candidate_phone") or cap.get("phone")),
            "current_employer": (cap.get("current_employer") or
                                  cap.get("current_company") or ""),
            "designation": cap.get("designation") or cap.get("current_designation") or "",
            "captured_by": l.get("captured_by_name") or l.get("captured_by") or "",
            "profile_url": l.get("profile_url", ""),
        })

    # Group into identity buckets by email (primary) or phone_last4 (fallback)
    buckets = defaultdict(list)
    for log in logs:
        key = log["email"] or f"phone:{log['phone_last4']}" or "unknown"
        buckets[key].append(log)
    identity_buckets = [
        {
            "identity_key": k,
            "capture_count": len(v),
            "sample_employers": list({log["current_employer"] for log in v if log["current_employer"]})[:3],
            "log_ids": [log["log_id"] for log in v],
            "latest_capture": max((log["timestamp"] for log in v), default=""),
        }
        for k, v in buckets.items()
    ]
    identity_buckets.sort(key=lambda b: -b["capture_count"])

    return {
        "candidate_bank_state": bank,
        "total_captures": len(logs),
        "captures": logs,
        "identity_buckets": identity_buckets,
        "is_contaminated": len(identity_buckets) > 1 and any(
            b["identity_key"] != "unknown" and not b["identity_key"].startswith("phone:")
            for b in identity_buckets
        ),
    }


@router.post("/split/{candidate_id}")
async def split_candidate(
    candidate_id: str,
    dry_run: bool = Query(True, description="If true, returns plan without executing"),
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Split a contaminated candidate record into N new candidates, one per
    distinct email. The bucket with the MOST recent capture keeps the original
    candidate_id (so any downstream FKs / bookmarks still resolve). Other
    buckets get fresh candidate_ids. All capture logs are re-pointed to the
    right candidate_id."""
    detail = await conflict_detail(candidate_id, db, user)
    buckets = detail["identity_buckets"]

    # Only split when there are 2+ real email buckets (safety guard)
    email_buckets = [b for b in buckets
                     if b["identity_key"] and not b["identity_key"].startswith("phone:")
                     and b["identity_key"] != "unknown"]
    if len(email_buckets) < 2:
        raise HTTPException(400, "Not a splittable conflict (need ≥2 distinct email identities)")

    original = detail["candidate_bank_state"]
    now = datetime.now(timezone.utc).isoformat()

    # Winner bucket (keeps the original candidate_id) = bucket matching
    # the current bank record's email; falls back to bucket with most captures.
    bank_email = (original.get("email") or "").strip().lower()
    winner = next((b for b in email_buckets if b["identity_key"] == bank_email), None) or email_buckets[0]

    plan = {
        "candidate_id": candidate_id,
        "winner_bucket": winner["identity_key"],
        "winner_capture_count": winner["capture_count"],
        "new_candidates_to_create": [
            {"identity_key": b["identity_key"], "capture_count": b["capture_count"],
             "log_ids": b["log_ids"], "sample_employers": b["sample_employers"]}
            for b in email_buckets if b is not winner
        ],
    }

    if dry_run:
        plan["dry_run"] = True
        return plan

    # ─── EXECUTE ───
    # 1. Backup the original candidate + all its capture logs
    backup_id = str(uuid.uuid4())
    log_ids_all = [log["log_id"] for log in detail["captures"]]
    await db.merged_conflicts_backup.insert_one({
        "id": backup_id,
        "created_at": now,
        "created_by": user.get("email", "?"),
        "original_candidate_id": candidate_id,
        "original_candidate": original,
        "capture_log_ids": log_ids_all,
        "plan": plan,
    })

    # 2. For each non-winner bucket, create a NEW candidate + re-point its captures
    created_ids = []
    for bucket in email_buckets:
        if bucket is winner:
            continue
        new_cid = str(uuid.uuid4())
        # Best-effort clone from original (name, source) + override email/employer
        sample_log_id = bucket["log_ids"][0]
        sample = await db.naukri_capture_logs.find_one(
            {"id": sample_log_id}, {"_id": 0, "captured_data": 1, "candidate_email": 1,
                                     "candidate_phone": 1, "candidate_name": 1}
        )
        cap = (sample or {}).get("captured_data") or {}
        new_doc = {
            "id": new_cid,
            "name": (sample or {}).get("candidate_name") or original.get("name", ""),
            "name_lower": ((sample or {}).get("candidate_name") or original.get("name", "")).lower(),
            "email": bucket["identity_key"],
            "phone": (sample or {}).get("candidate_phone") or cap.get("phone", ""),
            "current_employer": cap.get("current_employer") or cap.get("current_company", ""),
            "designation": cap.get("designation") or cap.get("current_designation", ""),
            "source": original.get("source", "naukri_extension"),
            "created_at": now,
            "updated_at": now,
            "split_from": candidate_id,
            "split_backup_id": backup_id,
        }
        await db.candidate_bank.insert_one(new_doc)
        # re-point capture logs
        await db.naukri_capture_logs.update_many(
            {"id": {"$in": bucket["log_ids"]}},
            {"$set": {"candidate_id": new_cid, "split_from": candidate_id}}
        )
        created_ids.append(new_cid)

    # 3. Mark the original as split-repaired (for audit)
    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$set": {"repair_split_at": now, "repair_backup_id": backup_id,
                  "repair_split_created": created_ids}}
    )

    return {
        "ok": True, "backup_id": backup_id,
        "kept_original": candidate_id, "new_candidate_ids": created_ids,
        "captures_repointed": sum(b["capture_count"] for b in email_buckets if b is not winner),
    }


@router.post("/undo-split/{backup_id}")
async def undo_split(
    backup_id: str,
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Restore a split. Restricted to admin@vhc.in — this deletes the
    new-candidate rows created by the split. Backup preserved."""
    if (user.get("email") or "").lower() != "admin@vhc.in":
        raise HTTPException(403, "Undo restricted to admin@vhc.in")
    bk = await db.merged_conflicts_backup.find_one({"id": backup_id})
    if not bk:
        raise HTTPException(404, "Backup not found")
    plan = bk.get("plan") or {}
    orig_cid = bk["original_candidate_id"]

    # Re-point all captures back to original
    await db.naukri_capture_logs.update_many(
        {"id": {"$in": bk.get("capture_log_ids", [])}},
        {"$set": {"candidate_id": orig_cid}, "$unset": {"split_from": ""}}
    )
    # Delete the split-created candidate rows
    orig_meta = await db.candidate_bank.find_one({"id": orig_cid}, {"repair_split_created": 1})
    created_ids = (orig_meta or {}).get("repair_split_created", [])
    if created_ids:
        await db.candidate_bank.delete_many({"id": {"$in": created_ids}})
    # Clear repair markers on original
    await db.candidate_bank.update_one(
        {"id": orig_cid},
        {"$unset": {"repair_split_at": "", "repair_backup_id": "",
                    "repair_split_created": ""}}
    )
    return {"ok": True, "restored_candidate_id": orig_cid,
            "deleted_new_candidates": len(created_ids)}
