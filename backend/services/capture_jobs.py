"""Idempotency for capture operations, never identity resolution for people.

The authenticated user and a persisted client operation key identify one job.
Mongo's unique _id permits only one dispatch while the job is retained.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import hashlib
import json
import re
from uuid import NAMESPACE_URL, uuid4, uuid5

from pymongo.errors import DuplicateKeyError


class CaptureRequestConflict(ValueError):
    """An operation key was reused for different content."""


async def submit_capture_job(db, profile: dict, user: dict, now: datetime):
    user_id = user.get("id")
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("Authenticated user id required")
    request_id = profile.get("capture_request_id")
    if request_id is not None and (
            not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_id)):
        raise ValueError("Invalid capture request id")
    fingerprint = hashlib.sha256(json.dumps(
        profile, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")).hexdigest()
    job_id = str(uuid5(NAMESPACE_URL, json.dumps(
        ["vhcos-capture-operation-v1", user_id, request_id], separators=(",", ":"),
    ))) if request_id else str(uuid4())
    job = {
        "_id": job_id, "status": "pending", "user_id": user_id,
        "user_email": user.get("email", ""),
        "candidate_name": str(profile.get("name") or "")[:200],
        "naukri_profile_id": profile.get("naukri_profile_id"),
        "capture_request_id": request_id, "payload_hash": fingerprint,
        "created_at": now.isoformat(), "updated_at": now.isoformat(),
        "expires_at": now + timedelta(days=7),
    }
    try:
        await asyncio.wait_for(db.extension_capture_jobs.insert_one(job), timeout=3)
        return job, True
    except DuplicateKeyError:
        # An unrelated unique-index failure must not authorize redispatch.
        existing = await asyncio.wait_for(db.extension_capture_jobs.find_one(
            {"_id": job_id, "user_id": user_id},
        ), timeout=3)
        if existing is None:
            raise RuntimeError("Capture operation could not be recovered") from None
        if existing.get("payload_hash") != fingerprint:
            raise CaptureRequestConflict("Capture request id already used") from None
        return existing, False
