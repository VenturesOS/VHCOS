"""Persist derived identity signatures without replacing newer profile evidence.

No connection or index creation happens at import time. Callers supply a database
and a complete stored candidate snapshot; request payloads are not snapshots.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

if __package__:
    from .identity_resolution import SIGNATURE_VERSION, build_identity_signature
else:
    # Standalone migration/test tools load this file from services/ directly.
    # Importing services.__init__ would initialize unrelated live clients.
    from identity_resolution import SIGNATURE_VERSION, build_identity_signature


# Keep this aligned with the raw fields consumed by build_identity_signature.
# Guards include absent fields: a concurrent enrichment adding a previously
# absent company must prevent an old signature from being written over it.
IDENTITY_INPUT_FIELDS = (
    "name", "full_name", "current_employer", "current_company", "company",
    "designation", "current_designation", "current_title", "title",
    "location", "current_location", "current_city", "career_preferences",
    "skills", "technical_skills", "key_skills", "education", "education_details",
    "highest_degree", "highest_qualification",
    "experience", "work_experience", "employment_history", "company_history",
    "previous_employers", "title_history", "location_history",
    "certifications", "certification", "projects", "project", "languages", "language",
    "experience_years", "total_experience_years", "total_experience",
    "naukri_profile_id", "naukri_id", "naukri_profile_url",
    "linkedin_id", "linkedin_profile_id", "linkedin_url", "linkedin_profile_url", "profile_url",
    "source_profile_url", "source_details",
    "identity_evidence", "_identity_trusted_anchors", "source", "source_platform",
    "updated_at", "identity",
)


def _snapshot_filter(candidate: dict[str, Any]) -> dict[str, Any]:
    if "_id" in candidate:
        target = {"_id": candidate["_id"]}
    elif candidate.get("id"):
        target = {"id": candidate["id"]}
    else:
        raise ValueError("A stored candidate id is required")
    clauses = [target]
    for field in IDENTITY_INPUT_FIELDS:
        if field in candidate:
            # $eq prevents a raw dict from being interpreted as an operator.
            clauses.append({field: {"$eq": candidate[field], "$exists": True}})
        else:
            clauses.append({field: {"$exists": False}})
    return {"$and": clauses}


async def persist_candidate_identity(db: Any, candidate: dict[str, Any]) -> dict[str, Any]:
    """Write one signature using compare-and-set against its source snapshot.

    Returns ``{status: updated|unchanged|stale, signature: {...}}``. A stale
    result includes deleted candidates; callers may fetch a new snapshot and
    retry. Dictionary entries use immutable code strings as unique ``_id``s,
    so concurrent captures cannot assign different IDs to the same value.

    Neither this helper nor the signature promotes scraped identifiers to
    verified evidence. Raw fields and server-owned evidence are never changed.
    """
    query = _snapshot_filter(candidate)
    signature = build_identity_signature(candidate)
    first_seen = datetime.now(timezone.utc).isoformat()

    async def register_code(code: str) -> None:
        namespace, _, canonical_value = code.partition(":")
        await db.identity_codes.update_one(
            {"_id": code},
            {"$setOnInsert": {
                "namespace": namespace,
                "canonical_value": canonical_value,
                "normalization_version": signature["version"],
                "first_seen_at": first_seen,
            }},
            upsert=True,
        )

    # Bound dictionary I/O so profiles with many skills do not add one network
    # round trip per token to capture latency or exhaust the connection pool.
    codes = signature["codes"]
    for start in range(0, len(codes), 16):
        await asyncio.gather(*(register_code(code) for code in codes[start:start + 16]))
    result = await db.candidate_bank.update_one(query, {"$set": {"identity": signature}})
    if not result.matched_count:
        status = "stale"
    else:
        status = "updated" if result.modified_count else "unchanged"
    return {"status": status, "signature": signature}


async def refresh_candidate_identity(db: Any, candidate_id: str, *, retries: int = 2) -> dict[str, Any]:
    """Read the effective merged profile after capture and retry a racing writer."""
    if retries < 1:
        raise ValueError("retries must be positive")
    for _ in range(retries):
        candidate = await db.candidate_bank.find_one({"id": candidate_id})
        if candidate is None:
            return {"status": "missing", "signature": None}
        result = await persist_candidate_identity(db, candidate)
        if result["status"] != "stale":
            return result
    return result


def refresh_candidate_identity_sync(
    db: Any, candidate_id: str, *, retries: int = 2, timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    """Refresh after a synchronous enrichment write using its existing DB client.

    The worker must not reuse the web application's Motor client across event
    loops. This variant performs the same raw-field snapshot CAS through the
    worker's supplied PyMongo database, with a bounded client-side deadline.
    Dictionary writes are batched and append-only. No connection is created.
    """
    from pymongo import UpdateOne, timeout

    if retries < 1 or timeout_seconds <= 0:
        raise ValueError("retries and timeout_seconds must be positive")
    with timeout(timeout_seconds):
        for _ in range(retries):
            candidate = db.candidate_bank.find_one({"id": candidate_id})
            if candidate is None:
                return {"status": "missing", "signature": None}
            query = _snapshot_filter(candidate)
            signature = build_identity_signature(candidate)
            first_seen = datetime.now(timezone.utc).isoformat()
            writes = []
            for code in signature["codes"]:
                namespace, _, canonical_value = code.partition(":")
                writes.append(UpdateOne(
                    {"_id": code},
                    {"$setOnInsert": {
                        "namespace": namespace, "canonical_value": canonical_value,
                        "normalization_version": signature["version"], "first_seen_at": first_seen,
                    }},
                    upsert=True,
                ))
            if writes:
                db.identity_codes.bulk_write(writes, ordered=False)
            applied = db.candidate_bank.update_one(query, {"$set": {"identity": signature}})
            if applied.matched_count:
                return {"status": "updated" if applied.modified_count else "unchanged", "signature": signature}
        return {"status": "stale", "signature": signature}


async def bootstrap_identity_indexes(db: Any) -> None:
    """Explicit migration step; never run this implicitly on a web request."""
    await db.candidate_bank.create_index("identity.codes", name="candidate_identity_codes_v1")
    await db.candidate_bank.create_index("identity.version", name="candidate_identity_version_v1")
    await db.candidate_bank.create_index("identity.source_ids.naukri", name="candidate_identity_naukri_v1")
    await db.candidate_bank.create_index("identity.source_ids.linkedin", name="candidate_identity_linkedin_v1")
    await db.identity_codes.create_index("namespace", name="identity_code_namespace_v1")
    await db.identity_observations.create_index(
        [("status", 1), ("observed_at", -1)], name="identity_observation_review_v1",
    )
    await db.identity_observations.create_index(
        [("status", 1), ("identity.codes", 1)], name="identity_observation_codes_v1",
    )
    await db.identity_observations.create_index(
        [("candidate_id", 1), ("status", 1), ("observed_at", -1)], name="identity_observation_person_v1",
    )
    await db.identity_code_stats.create_index(
        [("snapshot_id", 1), ("code", 1)], name="identity_frequency_snapshot_code_v1", unique=True,
    )


async def refresh_identity_frequencies(db: Any) -> dict[str, Any]:
    """Explicitly publish corpus document frequencies for ranking hints.

    A code counts at most once per indexed candidate. Repeated captures never
    increment a frequency. Work is streamed in bounded batches and metadata is
    published only after all new snapshot records were successfully persisted.
    An interrupted refresh leaves the previous published snapshot available.

    This is a rolling corpus measurement, not a transaction spanning concurrent
    captures; consumers must use the same snapshot ID/population for all codes
    and use frequency only as ranking evidence, never as identity verification.
    """
    population = await db.candidate_bank.count_documents({"identity.version": SIGNATURE_VERSION})
    snapshot_id = uuid4().hex
    computed_at = datetime.now(timezone.utc).isoformat()
    pipeline = [
        {"$match": {"identity.version": SIGNATURE_VERSION}},
        {"$project": {"codes": {"$setUnion": [
            {"$cond": [{"$isArray": "$identity.codes"}, "$identity.codes", []]}, [],
        ]}}},
        {"$unwind": "$codes"},
        {"$match": {"codes": {"$type": "string"}}},
        {"$group": {"_id": "$codes", "document_count": {"$sum": 1}}},
    ]
    cursor = db.candidate_bank.aggregate(pipeline, allowDiskUse=True, batchSize=100)
    code_count = 0
    pending = []

    async def write_frequency(row: dict[str, Any]) -> None:
        code = row["_id"]
        count = int(row["document_count"])
        if count < 0 or count > population:
            raise RuntimeError("Corpus changed during frequency refresh; retry the explicit refresh")
        await db.identity_code_stats.update_one(
            {"_id": f"{snapshot_id}:{code}"},
            {"$setOnInsert": {
                "snapshot_id": snapshot_id, "code": code,
                "document_count": count, "population_size": population,
                "computed_at": computed_at,
            }},
            upsert=True,
        )

    async for row in cursor:
        pending.append(row)
        if len(pending) == 16:
            await asyncio.gather(*(write_frequency(item) for item in pending))
            code_count += len(pending)
            pending.clear()
    if pending:
        await asyncio.gather(*(write_frequency(item) for item in pending))
        code_count += len(pending)
    metadata = {
        "snapshot_id": snapshot_id, "population_size": population,
        "version": SIGNATURE_VERSION, "signature_version": SIGNATURE_VERSION,
        "computed_at": computed_at, "codes": code_count,
    }
    await db.identity_code_stats.update_one(
        {"_id": "__meta__"}, {"$set": metadata}, upsert=True,
    )
    return metadata
