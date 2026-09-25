"""Immutable profile observations and explicit, revision-guarded identity review.

An observation is not a person. Capturing does not create or overwrite a bank
record. Only a deliberate administrator decision can create a new person.
"""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import json
from uuid import NAMESPACE_URL, uuid4, uuid5

from pymongo.errors import DuplicateKeyError

if __package__:
    from .identity_resolution import build_identity_signature, normalize_text
    from .identity_lookup import lookup_one, unavailable_result
else:
    from identity_resolution import build_identity_signature, normalize_text
    from identity_lookup import lookup_one, unavailable_result


class ObservationConflict(ValueError):
    """The review is stale, already resolved, or reuses an operation incorrectly."""


class ObservationMissing(LookupError):
    """Observation or proposed canonical person is no longer available."""


PUBLIC_FIELDS = (
    "name", "full_name", "current_employer", "current_company", "designation",
    "current_designation", "title", "current_title", "location", "current_location",
    "skills", "key_skills", "technical_skills", "experience_years", "total_experience_years",
    "education", "education_details", "highest_degree", "highest_qualification",
    "experience", "work_experience", "employment_history", "certifications", "projects", "languages",
)
NESTED_FIELDS = (
    "name", "company", "company_name", "employer", "organization", "organisation",
    "title", "job_title", "designation", "role", "position", "location", "city",
    "degree", "course", "qualification", "specialization", "institution", "institute",
    "university", "college", "school", "language", "issuer", "certificate",
    "start_date", "end_date", "start_year", "end_year", "from", "to", "graduation_year",
    "is_current", "currently_working",
)


def _bounded(value, depth=0):
    if depth > 3:
        return None
    if isinstance(value, str):
        return value[:1000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        return [_bounded(item, depth + 1) for item in value[:30]]
    if isinstance(value, dict):
        return {key: _bounded(value[key], depth + 1) for key in NESTED_FIELDS if key in value}
    return None


def public_snapshot(snapshot: dict) -> dict:
    return {key: _bounded(snapshot[key]) for key in PUBLIC_FIELDS if key in snapshot}


def lookup_input(snapshot: dict) -> dict:
    """Adapt canonical bank fields to the public, untrusted lookup contract."""
    return {
        "name": snapshot.get("name", ""),
        "current_employer": snapshot.get("current_employer") or snapshot.get("current_company"),
        "designation": snapshot.get("designation") or snapshot.get("current_designation"),
        "location": snapshot.get("location") or snapshot.get("current_location"),
        "experience_years": (snapshot.get("experience_years") if snapshot.get("experience_years") is not None
                             else snapshot.get("total_experience_years")),
        "skills": snapshot.get("skills") or snapshot.get("key_skills") or [],
        "education": snapshot.get("education") or snapshot.get("highest_degree"),
        "education_details": snapshot.get("education_details") or [],
        "experience": snapshot.get("experience") or snapshot.get("work_experience") or [],
        "certifications": snapshot.get("certifications") or [],
        "projects": snapshot.get("projects") or [],
        "languages": snapshot.get("languages") or [],
    }


async def observation_suggestions(db, snapshot: dict) -> dict:
    try:
        return await asyncio.wait_for(lookup_one(db, lookup_input(snapshot)), timeout=6)
    except Exception:
        return unavailable_result("observation_lookup_unavailable")


def public_observation(doc: dict, *, detail=False) -> dict:
    resolution = doc.get("resolution") or {}
    snapshot = public_snapshot(doc.get("snapshot") or {})
    result = {
        key: doc.get(key) for key in (
            "id", "status", "observed_at", "source", "name", "revision", "candidate_id",
        )
    }
    result.update({
        "reason_codes": resolution.get("reason_codes", []),
        "top_match": resolution.get("top_match"),
        "ranked_matches": resolution.get("ranked_matches", []),
        "observation_summary": snapshot,
    })
    if detail:
        result.update({
            "snapshot": snapshot, "resolution": resolution,
            "submitted_snapshot": public_snapshot(doc.get("submitted_snapshot") or {}),
            "provenance": doc.get("provenance", {}),
            "review_history": doc.get("review_history", [])[-100:],
        })
        pending = doc.get("pending_review")
        if isinstance(pending, dict):
            result["pending_review"] = {key: pending.get(key) for key in ("decision", "reason", "candidate_id")}
    return result


async def record_capture_observation(db, submitted: dict, template: dict, user: dict, now: datetime) -> dict:
    """Persist evidence before returning success. Retries never edit its snapshot."""
    user_id = user.get("id")
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("Authenticated user id required")
    key = submitted.get("capture_request_id")
    observation_id = str(uuid5(NAMESPACE_URL, json.dumps(
        ["vhcos-observation-v1", user_id, key], separators=(",", ":"),
    ))) if key else str(uuid4())
    fingerprint = hashlib.sha256(json.dumps(
        submitted, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode()).hexdigest()
    # Quick replay lookup avoids running matching again or replacing the capture
    # timestamp after a lost response. _id is unique without an index migration.
    previous = await db.identity_observations.find_one({"_id": observation_id, "owner_id": user_id})
    if previous:
        if previous.get("payload_hash") != fingerprint:
            raise ObservationConflict("Capture operation reused with different data")
        return previous
    snapshot = copy.deepcopy(template)
    for field in ("id", "_id", "identity", "_identity_trusted_anchors", "identity_evidence"):
        snapshot.pop(field, None)
    # All automatic links stay disabled until independently labelled evaluation
    # supports a release policy. Soft rank is never a write/identity decision.
    resolution = await observation_suggestions(db, snapshot)
    doc = {
        "_id": observation_id, "id": observation_id, "owner_id": user_id,
        "payload_hash": fingerprint, "capture_request_id": key,
        "name": snapshot.get("name", ""), "source": submitted.get("source_platform") or "extension",
        "observed_at": now.isoformat(), "snapshot": snapshot,
        "submitted_snapshot": public_snapshot(submitted),
        "identity": build_identity_signature(snapshot),
        "provenance": {
            "kind": "extension_capture", "received_at": now.isoformat(),
            "client_reported_scraped_at": submitted.get("scraped_at"),
            "extraction": "dom_and_server_validation" if submitted.get("dom_scraped") else "mixed_unverified",
        },
        "status": "unresolved", "candidate_id": None, "revision": 0,
        "resolution": resolution, "review_history": [],
    }
    try:
        await db.identity_observations.insert_one(doc)
        return doc
    except DuplicateKeyError:
        previous = await db.identity_observations.find_one({"_id": observation_id, "owner_id": user_id})
        if not previous or previous.get("payload_hash") != fingerprint:
            raise ObservationConflict("Capture operation conflict") from None
        return previous


async def review_observation(db, observation_id: str, request: dict, reviewer: dict) -> dict:
    """CAS review; links never copy captured values over the canonical record.

    New-person creation reserves one deterministic ID before insertion. An
    interrupted insert/finalize can be resumed without creating another person.
    """
    if reviewer.get("role") != "admin":
        raise PermissionError("Administrator access required")
    doc = await db.identity_observations.find_one({"_id": observation_id})
    if not doc:
        raise ObservationMissing("Observation not found")
    if request.get("revision") != doc.get("revision"):
        raise ObservationConflict("Review changed; reload it")
    decision = request.get("decision")
    reason = (request.get("reason") or "").strip()
    if decision not in {"link", "new_person", "defer"} or not 10 <= len(reason) <= 2000:
        raise ValueError("An explicit decision and a 10–2000 character reason are required")
    now = datetime.now(timezone.utc).isoformat()
    if doc["status"] == "resolving":
        if decision != "new_person" or doc.get("pending_review", {}).get("decision") != "new_person":
            raise ObservationConflict("Resume the pending new-person decision first")
        pending = doc["pending_review"]
    elif decision == "new_person":
        if doc["status"] not in {"unresolved", "deferred"}:
            raise ObservationConflict("Observation already linked")
        if not normalize_text(doc["snapshot"].get("name")):
            raise ValueError("A usable name is required to create a candidate")
        pending = {
            "decision": decision, "candidate_id": str(uuid5(NAMESPACE_URL, "vhcos-reviewed-person:" + observation_id)),
            "reason": reason, "reviewer_id": reviewer["id"], "reviewed_at": now,
        }
        claim = await db.identity_observations.update_one(
            {"_id": observation_id, "revision": doc["revision"], "status": doc["status"]},
            {"$set": {"status": "resolving", "pending_review": pending}, "$inc": {"revision": 1}},
        )
        if claim.matched_count != 1:
            raise ObservationConflict("Another reviewer changed this observation")
        doc = {**doc, "status": "resolving", "revision": doc["revision"] + 1, "pending_review": pending}
    else:
        pending = None

    if decision == "new_person":
        candidate_id = pending["candidate_id"]
        candidate = copy.deepcopy(doc["snapshot"])
        candidate.update({
            "_id": candidate_id, "id": candidate_id,
            "identity_origin_observation_id": observation_id,
            "created_at": pending["reviewed_at"], "updated_at": pending["reviewed_at"],
            "identity": build_identity_signature(doc["snapshot"]),
        })
        try:
            await db.candidate_bank.insert_one(candidate)
        except DuplicateKeyError:
            existing = await db.candidate_bank.find_one({
                "_id": candidate_id, "identity_origin_observation_id": observation_id,
            })
            if not existing:
                raise ObservationConflict("Candidate creation conflicted; manual reconciliation required") from None
        reason = pending["reason"]
    elif decision == "link":
        if doc["status"] not in {"unresolved", "deferred"}:
            raise ObservationConflict("Unlink the previous decision before relinking")
        candidate_id = request.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id or len(candidate_id) > 256:
            raise ValueError("Existing candidate id required")
        if not await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 1}):
            raise ObservationMissing("Candidate not found")
    else:
        candidate_id = None

    event = {
        "decision": decision, "reason": reason, "reviewer_id": reviewer["id"], "reviewed_at": now,
        "previous_candidate_id": doc.get("candidate_id"), "candidate_id": candidate_id,
    }
    result = await db.identity_observations.update_one(
        {"_id": observation_id, "revision": doc["revision"], "status": doc["status"]},
        {"$set": {"status": "linked" if candidate_id else "deferred", "candidate_id": candidate_id},
         "$unset": {"pending_review": ""},
         "$inc": {"revision": 1}, "$push": {"review_history": event}},
    )
    if result.matched_count != 1:
        raise ObservationConflict("Review changed; reload to see the saved decision")
    return await db.identity_observations.find_one({"_id": observation_id})
