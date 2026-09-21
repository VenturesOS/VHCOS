"""Bounded, read-only candidate retrieval. No config import or implicit network setup.

Canonical indexes narrow the pool; each current or linked historical observation
is scored independently. Legacy name paths keep an unbackfilled bank usable. A
capped or failed path is explicitly incomplete, never evidence of absence.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime
from urllib.parse import quote

if __package__:
    from .identity_resolution import (
        build_identity_signature, canonical_code, normalize_text, resolve_profile,
    )
else:
    from identity_resolution import (
        build_identity_signature, canonical_code, normalize_text, resolve_profile,
    )

MATCHER_VERSION = "identity-resolution-1"
PATH_LIMIT = 100
QUERY_TIMEOUT_S = 5
MAX_CONCURRENT_PROFILES = 5
BATCH_TIMEOUT_S = 8
OBSERVATION_VIEW_LIMIT = 8
OBSERVATION_PROJECTION = {key: 1 for key in (
    "id", "candidate_id", "status", "snapshot", "identity", "observed_at", "revision",
)}
OBSERVATION_PROJECTION["_id"] = 0

# Only fields used for matching/authorized bank links. Never send contacts, resumes,
# or internal anchor verification to the client.
PROJECTION = {key: 1 for key in (
    "id", "name", "full_name", "name_lower", "first_name", "last_name", "current_employer",
    "current_company", "company", "designation", "current_designation", "current_title", "title",
    "location", "current_location", "skills", "key_skills", "technical_skills", "education",
    "company_history", "previous_employers", "title_history", "location_history",
    "highest_degree", "highest_qualification", "certification", "project", "language",
    "education_details", "experience", "work_experience", "employment_history",
    "certifications", "projects", "languages", "experience_years", "total_experience",
    "total_experience_years", "headline", "resume_headline", "source", "source_platform",
    "created_at", "updated_at", "captured_at",
    "naukri_id", "naukri_profile_id", "naukri_profile_url", "profile_url", "linkedin_url", "linkedin_profile_url",
    "source_profile_url", "source_details", "identity",
)}
PROJECTION["_id"] = 0

# Context returned with a decision is intentionally smaller than the stored
# profile.  It helps a recruiter inspect why a record was suggested, while
# keeping contacts, resumes, raw page text, and internal verification metadata
# out of this endpoint.
_CONTEXT_LIST_LIMIT = 12
_CONTEXT_TEXT_LIMIT = 240


def _safe_timestamp(value):
    """Return a JSON-safe timestamp without leaking arbitrary object values."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        return value
    return None


def _context_values(value, *, limit=_CONTEXT_LIST_LIMIT):
    """Flatten common bank shapes into bounded, non-sensitive display values."""
    values = []
    if isinstance(value, str):
        values = re.split(r"[,;|\n]", value)
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                values.extend(re.split(r"[,;|\n]", item))
            elif isinstance(item, dict):
                values.extend(item[key] for key in (
                    "name", "company", "employer", "organization", "organisation",
                    "title", "designation", "role", "position", "degree",
                    "institution", "institute", "university", "college", "school",
                    "location", "city", "work_location", "language",
                ) if isinstance(item.get(key), str))
    elif isinstance(value, dict):
        values = [value[key] for key in (
            "name", "company", "employer", "organization", "organisation",
            "title", "designation", "role", "position", "degree",
            "institution", "institute", "university", "college", "school",
            "location", "city", "work_location", "language",
        ) if isinstance(value.get(key), str)]
    out = []
    seen = set()
    for item in values:
        item = " ".join(str(item).split()).strip()[:_CONTEXT_TEXT_LIMIT]
        if not item:
            continue
        key = normalize_text(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def compact_candidate_context(doc: dict) -> dict:
    """Build the safe context packet attached to top/alternative matches."""
    context = {}
    for output, keys in {
        "employer": ("current_employer", "current_company", "company"),
        "designation": ("current_designation", "designation", "current_title", "title"),
        "location": ("current_location", "location"),
        "headline": ("headline", "resume_headline"),
    }.items():
        value = next((doc.get(key) for key in keys if isinstance(doc.get(key), str) and doc.get(key).strip()), None)
        if value:
            context[output] = " ".join(value.split())[:_CONTEXT_TEXT_LIMIT]
    for output, keys in {
        "skills": ("skills", "key_skills", "it_skills", "technical_skills"),
        "education": ("education", "education_details", "highest_degree", "highest_qualification"),
        "work_history": ("experience", "work_experience", "employment_history"),
        "certifications": ("certifications", "certification"),
        "projects": ("projects", "project"),
        "languages": ("languages", "language"),
    }.items():
        values = []
        for key in keys:
            values.extend(_context_values(doc.get(key)))
            if values:
                break
        if values:
            context[output] = values[:_CONTEXT_LIST_LIMIT]
    for output, keys in {
        "experience_years": ("experience_years", "total_experience_years", "total_experience"),
        "captured_at": ("captured_at", "created_at", "updated_at"),
    }.items():
        value = next((doc.get(key) for key in keys if doc.get(key) not in (None, "")), None)
        safe_value = _safe_timestamp(value) if output == "captured_at" else value
        if safe_value is not None and (
                output == "captured_at"
                or (isinstance(safe_value, (int, float, str)) and not isinstance(safe_value, bool))):
            context[output] = safe_value
    # Keep each job's company, role, place and dates together for human review.
    # The legacy flat summary remains available for older extension displays.
    for key in ("experience", "work_experience", "employment_history"):
        jobs = doc.get(key)
        if not isinstance(jobs, list):
            continue
        details = []
        for job in jobs[:_CONTEXT_LIST_LIMIT]:
            if not isinstance(job, dict):
                continue
            safe = {field: value[:_CONTEXT_TEXT_LIMIT] if isinstance(value, str) else value
                    for field, value in job.items() if field in (
                        "company", "employer", "organization", "designation", "title", "role",
                        "location", "city", "start_date", "end_date", "start_year", "end_year",
                        "is_current", "currently_working",
                    ) and isinstance(value, (str, int, bool))}
            if safe:
                details.append(safe)
        if details:
            context["work_history_details"] = details
            break
    source = doc.get("source_platform") or doc.get("source")
    if isinstance(source, str) and source.strip():
        context["source"] = source.strip()[:80]
    return context


def public_profile(profile: dict) -> dict:
    """Whitelist transport fields before constructing internal evidence.

    Payload flags such as `verified`, `_identity_trusted_anchors`, and an incoming
    identity signature must never cross the server trust boundary.
    """
    allowed = (
        "name", "headline", "location", "source", "source_id_kind", "naukri_id",
        "profile_url", "profileUrl", "current_employer", "designation",
        "experience_years", "annual_ctc", "skills", "education", "notice_period",
        "experience", "work_experience", "employment_history", "certifications",
        "projects", "languages", "education_details",
    )
    clean = {key: profile[key] for key in allowed if key in profile}
    url = clean.get("profile_url") or clean.get("profileUrl")
    clean["profile_url"] = url
    # URLs can rotate within hours. They are navigation metadata, never
    # retrieval or identity evidence. Drop URL-derived/untyped IDs from older
    # extensions too. Only an explicitly observed DOM marker can retrieve a
    # candidate as an unverified hint; it cannot establish identity.
    if clean.get("source_id_kind") != "data-target-id":
        clean.pop("naukri_id", None)
    return clean


def retrieval_paths(profile: dict) -> list[tuple[str, dict]]:
    signature = build_identity_signature(profile)
    fields = signature["fields"]
    paths: list[tuple[str, dict]] = []
    nid = profile.get("naukri_id")
    if (profile.get("source_id_kind") == "data-target-id"
            and isinstance(nid, str) and re.fullmatch(r"[A-Za-z0-9_-]{3,256}", nid)):
        raw = nid.removeprefix("naukri_")
        ids = sorted({raw, "naukri_" + raw})
        paths.append(("source_id", {"$or": [
            {"naukri_profile_id": {"$in": ids}}, {"naukri_id": {"$in": ids}},
            {"identity.source_ids.naukri": {"$in": ids}},
        ]}))
    names = fields.get("name", [])
    if names:
        paths.append(("full_name_code", {"identity.codes": canonical_code("name", names[0])}))
    tokens = fields.get("name_token", [])

    def context_codes(field, values):
        # A past employer can explain an old saved current employer. Keep the
        # namespaces separate in storage, but retrieve both before the engine
        # checks whether employer, role and location belong to the same job.
        scopes = {
            "company": ("company", "experience_company"),
            "title": ("title", "experience_title"),
            "location": ("location", "experience_location"),
            "experience_company": ("experience_company", "company"),
            "experience_title": ("experience_title", "title"),
            "experience_location": ("experience_location", "location"),
        }.get(field, (field,))
        return [canonical_code(scope, value) for scope in scopes for value in values[:8]]
    # Compound intersections are the important escape hatch for popular names:
    # a single name bucket may be capped, while name+employer+city (or the
    # equivalent skill/title combination) is selective enough to retrieve the
    # right record. Each code is field-scoped, so a value in one namespace can
    # never satisfy another namespace. The raw document is still rescored
    # after retrieval; codes only narrow the candidate set.
    compound_fields = (
        ("company", "location"),
        ("company", "title"),
        ("company", "skill"),
        ("location", "skill"),
        ("title", "skill"),
        ("experience_company", "institution"),
    )
    for fields_for_path in compound_fields:
        if not tokens or not all(fields.get(field) for field in fields_for_path):
            continue
        code_filters = [
            {"identity.codes": {"$in": [
                canonical_code("name_token", token) for token in tokens
            ]}},
            *({"identity.codes": {"$in": context_codes(field, fields[field])}}
              for field in fields_for_path),
        ]
        paths.append(("name_" + "_".join(fields_for_path), {"$and": code_filters}))
    for label, field in (("name_company", "company"), ("name_location", "location")):
        values = fields.get(field, [])
        if tokens and values:
            paths.append((label, {"$and": [
                {"identity.codes": {"$in": [canonical_code("name_token", t) for t in tokens]}},
                {"identity.codes": {"$in": context_codes(field, values)}},
            ]}))
    for field in ("title", "skill", "education", "experience_company",
                  "experience_title", "experience_location", "institution",
                  "certification", "project", "language"):
        values = fields.get(field, [])
        if not tokens or not values:
            continue
        paths.append((f"name_{field}", {"$and": [
            {"identity.codes": {"$in": [canonical_code("name_token", token) for token in tokens]}},
            {"identity.codes": {"$in": context_codes(field, values)}},
        ]}))
    if fields.get("company") and fields.get("title") and fields.get("skill"):
        paths.append(("company_title_skill", {"$and": [
            {"identity.codes": {"$in": [canonical_code(field, v) for v in fields[field]]}}
            for field in ("company", "title", "skill")
        ]}))

    # Legacy records may have no identity.codes yet.  Give them selective
    # context paths before the broad name fallback, so a popular first name
    # does not consume the entire quota while the exact employer/location
    # evidence is still available.  These are bounded, best-effort lookups;
    # current raw values are always rescored after retrieval.
    raw_name = normalize_text(profile.get("name"))
    raw_tokens = [token for token in raw_name.split() if len(token) >= 2]

    def raw_name_query(token: str) -> dict:
        pattern = r"^" + re.escape(token) + r"(?:\b|$)"
        return {"$or": [
            {"name_lower": {"$regex": pattern}},
            {"name": {"$regex": pattern, "$options": "i"}},
        ]}

    def first_raw(*keys):
        for key in keys:
            value = profile.get(key)
            if isinstance(value, str) and normalize_text(value):
                return value
            if isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, str) and normalize_text(item):
                        return item
        return None

    context_specs = (
        ("company", ("current_employer", "current_company", "company"),
         ("current_employer", "current_company", "company")),
        ("location", ("location", "current_location", "city"),
         ("location", "current_location", "current_city")),
        ("title", ("designation", "current_designation", "current_title", "title"),
         ("designation", "current_designation", "current_title", "title")),
        ("skill", ("skills", "key_skills", "technical_skills"),
         ("skills", "key_skills", "it_skills", "technical_skills")),
    )
    for field, input_keys, stored_keys in context_specs:
        value = first_raw(*input_keys)
        if not value or not raw_tokens:
            continue
        value_pattern = r".*" + re.escape(normalize_text(value)) + r".*"
        field_queries = [{key: {"$regex": value_pattern, "$options": "i"}}
                         for key in stored_keys]
        # First/last token scans are both needed for reversed display names;
        # duplicate paths are removed while preserving deterministic order.
        for token in dict.fromkeys((raw_tokens[0], raw_tokens[-1])):
            paths.append((f"legacy_name_{field}:{token}", {"$and": [
                raw_name_query(token), {"$or": field_queries},
            ]}))
    # Transitional fallback also finds updated raw values with stale stored codes.
    # Separate forward/reversed paths avoid one common prefix starving another.
    for token in dict.fromkeys([raw_tokens[0], raw_tokens[-1]] if raw_tokens else []):
        if len(token) < 2:
            continue
        pattern = r"^" + re.escape(token) + r"(?:\b|$)"
        paths.append(("legacy_name:" + token, {"$or": [
            {"name_lower": {"$regex": pattern}},
            {"name": {"$regex": pattern, "$options": "i"}},
        ]}))
    return paths


def stored_profile(doc: dict) -> dict:
    # Never trust stale `identity.fields` or flags from old browser writes.
    effective = dict(doc)
    effective.pop("_identity_trusted_anchors", None)
    # A completed capture is an observation, not verification of source-ID
    # semantics. In particular Naukri captures include pid/sid and URL hashes.
    # Ignore both identity_observation and the earlier automatic identity_anchor
    # shape. Source URLs can rotate and are never identity references. This
    # endpoint currently has no independently verified provider-ID adapter.
    effective["_identity_trusted_anchors"] = []
    return effective


def linked_observation_paths(profile: dict) -> list[tuple[str, dict]]:
    """Only name/context code paths may retrieve historical evidence.

    Reuse field-scoped intersections, not URLs, source IDs, or a broad scan of
    the observation collection. Review states never count as resolved people.
    """
    return [("linked_observation:" + label, {"$and": [
        {"status": "linked", "candidate_id": {"$regex": r"\S"}}, query,
    ]}) for label, query in retrieval_paths(profile)
        if label == "full_name_code" or label.startswith("name_")]


async def _load_linked_observations(db, profile, docs, path_names, path_status,
                                    incomplete, *, path_limit):
    """Load at most eight relevant views per real person, within one deadline.

    Each path has its own quota so a large common-name bucket cannot starve a
    selective employer/location intersection. Canonical bank hydration is
    mandatory: an orphaned observation cannot invent an existing candidate.
    """
    stats = {"observations_retrieved": 0, "observation_views_loaded": 0}
    # Older offline adapters do not expose this collection. A real Motor DB
    # always does, including before the first observation has been saved.
    collection = getattr(db, "identity_observations", None)
    paths = linked_observation_paths(profile)
    if collection is None or not paths:
        return 0, stats
    deadline = asyncio.get_running_loop().time() + QUERY_TIMEOUT_S
    succeeded = 0
    observations = {}
    observation_paths = {}

    async def query_rows(collection, label, query, projection, limit):
        nonlocal succeeded
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            path_status[label] = {"status": "failed", "returned": 0}
            incomplete.append("observation_deadline_exceeded:" + label)
            return []
        try:
            cursor = (collection.find(query, projection).sort("id", 1)
                      .limit(limit + 1).max_time_ms(max(1, int(remaining * 1000))))
            rows = await asyncio.wait_for(cursor.to_list(limit + 1), remaining)
            succeeded += 1
        except Exception:
            path_status[label] = {"status": "failed", "returned": 0}
            incomplete.append("query_failed:" + label)
            return []
        capped = len(rows) > limit
        path_status[label] = {"status": "capped" if capped else "complete",
                              "returned": min(len(rows), limit)}
        if capped:
            incomplete.append("retrieval_capped:" + label)
        return rows[:limit]

    for label, query in paths:
        rows = await query_rows(collection, label, query, OBSERVATION_PROJECTION, path_limit)
        for row in rows:
            oid, cid = row.get("id"), row.get("candidate_id")
            if (row.get("status") != "linked" or not isinstance(oid, str) or not oid.strip()
                    or not isinstance(cid, str) or not cid.strip()
                    or not isinstance(row.get("snapshot"), dict)):
                incomplete.append("invalid_linked_observation")
                continue
            if oid in observations and observations[oid] != row:
                incomplete.append("inconsistent_observation_snapshot")
                continue
            observations[oid] = row
            observation_paths.setdefault(oid, set()).add(label)

    stats["observations_retrieved"] = len(observations)
    candidate_ids = sorted({row["candidate_id"] for row in observations.values()})
    missing_ids = [cid for cid in candidate_ids if cid not in docs]
    for offset in range(0, len(missing_ids), path_limit):
        requested = missing_ids[offset:offset + path_limit]
        label = "linked_candidate_records:" + str(offset // path_limit)
        rows = await query_rows(db.candidate_bank, label, {"id": {"$in": requested}},
                                PROJECTION, path_limit)
        for row in rows:
            cid = row.get("id")
            if cid not in requested:
                incomplete.append("invalid_observation_candidate")
                continue
            if cid in docs and row != docs[cid]:
                incomplete.append("inconsistent_candidate_snapshot")
            docs[cid] = row
        if any(cid not in docs for cid in requested):
            incomplete.append("linked_observation_candidate_missing")

    incoming_codes = set(build_identity_signature(profile)["codes"])
    grouped = {}
    for oid, observation in observations.items():
        cid = observation["candidate_id"]
        if cid not in docs:
            continue
        grouped.setdefault(cid, []).append(observation)
        path_names.setdefault(cid, []).extend(sorted(observation_paths[oid]))
    for cid, views in grouped.items():
        # Retrieval priority only; the resolver still scores whole snapshots
        # independently. Rebuild codes so a stale observation index never
        # chooses the eight-view window using stale profile fields.
        views.sort(key=lambda row: (
            -len(incoming_codes & set(build_identity_signature(row["snapshot"])["codes"])),
            row["id"],
        ))
        if len(views) > OBSERVATION_VIEW_LIMIT:
            label = "linked_observation_views:" + cid
            path_status[label] = {"status": "capped", "returned": OBSERVATION_VIEW_LIMIT}
            incomplete.append("retrieval_capped:" + label)
        docs[cid]["_identity_observations"] = [
            {"id": row["id"], "observed_at": row.get("observed_at"), "snapshot": row["snapshot"]}
            for row in views[:OBSERVATION_VIEW_LIMIT]
        ]
        stats["observation_views_loaded"] += len(docs[cid]["_identity_observations"])
        path_names[cid] = list(dict.fromkeys(path_names[cid]))
    return succeeded, stats


def _match_context(match, docs):
    """Display the same historical view the engine used, not a blended person."""
    doc = docs.get(match["candidate_id"])
    if not doc:
        return
    observation_id = match.get("evidence_observation_id")
    observation = next((row for row in doc.get("_identity_observations", [])
                        if row["id"] == observation_id), None)
    if observation:
        match["context"] = compact_candidate_context(observation["snapshot"])
        match["current_context"] = compact_candidate_context(doc)
        match["context"]["observed_at"] = _safe_timestamp(observation.get("observed_at"))
    else:
        match["context"] = compact_candidate_context(doc)


async def lookup_one(db, profile: dict, *, path_limit: int = PATH_LIMIT,
                     code_frequencies=None, population_size=None) -> dict:
    clean = public_profile(profile)
    paths = retrieval_paths(clean)
    docs: dict[str, dict] = {}
    path_names: dict[str, list[str]] = {}
    path_status: dict[str, dict] = {}
    incomplete: list[str] = []
    succeeded = 0
    # Sequential per-profile queries keep the database fanout bounded by the batch
    # semaphore; each path gets its own quota so result order cannot starve others.
    for label, query in paths:
        try:
            cursor = (db.candidate_bank.find(query, PROJECTION).sort("id", 1)
                      .limit(path_limit + 1).max_time_ms(QUERY_TIMEOUT_S * 1000))
            rows = await asyncio.wait_for(cursor.to_list(path_limit + 1), QUERY_TIMEOUT_S)
            succeeded += 1
        except Exception:
            path_status[label] = {"status": "failed", "returned": 0}
            incomplete.append("query_failed:" + label)
            continue
        if len(rows) > path_limit:
            path_status[label] = {"status": "capped", "returned": path_limit}
            incomplete.append("retrieval_capped:" + label)
        else:
            path_status[label] = {"status": "complete", "returned": len(rows)}
        for row in rows[:path_limit]:
            cid = row.get("id")
            if not isinstance(cid, str) or not cid:
                incomplete.append("missing_candidate_id")
                continue
            if cid in docs and row != docs[cid]:
                incomplete.append("inconsistent_candidate_snapshot")
            docs[cid] = row
            path_names.setdefault(cid, []).append(label)
    observation_successes, observation_stats = await _load_linked_observations(
        db, clean, docs, path_names, path_status, incomplete, path_limit=path_limit,
    )
    succeeded += observation_successes
    if paths and succeeded == 0:
        return unavailable_result("database_unavailable")
    result = resolve_profile(
        clean, [stored_profile(d) for d in docs.values()],
        retrieval_complete=not incomplete,
        code_frequencies=code_frequencies, population_size=population_size,
    )
    result["retrieval_complete"] = not incomplete
    result["retrieval_paths"] = list(path_status)
    signature = build_identity_signature(clean)
    result["context_fields_observed"] = [field for field, values in signature["fields"].items()
                                         if field != "name_token" and values]
    result["retrieval_stats"] = {
        "paths_attempted": sum(not label.startswith("linked_observation_views:")
                               for label in path_status), "paths_succeeded": succeeded,
        "paths_failed": sum(item["status"] == "failed" for item in path_status.values()),
        "paths_capped": sum(item["status"] == "capped" for item in path_status.values()),
        "candidates_retrieved": len(docs),
        "authoritative_paths": [],
        "path_status": path_status,
        **observation_stats,
    }
    result["reason_codes"] = list(dict.fromkeys(result.get("reason_codes", []) + incomplete))
    for match in result.get("ranked_matches", []):
        if not match:
            continue
        match["retrieval_paths"] = path_names.get(match["candidate_id"], [])
        _match_context(match, docs)
    result["matcher_version"] = MATCHER_VERSION
    result["score_kind"] = "evidence_points"
    for key in ("top_match", "second_match"):
        match = result.get(key)
        if match:
            match["retrieval_paths"] = path_names.get(match["candidate_id"], [])
            _match_context(match, docs)
    top = result.get("top_match")
    if top:
        doc = docs[top["candidate_id"]]
        result["candidate_id"] = top["candidate_id"]
        captured_at = _safe_timestamp(doc.get("captured_at") or doc.get("created_at"))
        result["captured_at"] = str(captured_at) if captured_at is not None else None
    result["exists"] = result.get("decision") == "confirmed_duplicate"
    result["match_confidence"] = "high" if result["exists"] else None
    return result


def unavailable_result(reason: str) -> dict:
    return {
        "decision": "unavailable", "exists": False, "matcher_version": MATCHER_VERSION,
        "score_kind": "evidence_points", "reason_codes": [reason],
        "retrieval_complete": False,
        "match_score": 0.0, "matched_signals": [], "conflicts": [], "missing_fields": [],
    }


async def lookup_profiles(db, profiles: list[dict], web_base: str) -> list[dict]:
    sem = asyncio.Semaphore(MAX_CONCURRENT_PROFILES)
    # Missing/stale corpus statistics never prevent lookup; no counts are
    # inferred from the biased retrieved subset. Only a published epoch is used.
    frequencies, population = await load_frequency_snapshot(db, profiles)

    async def one(index, profile):
        async with sem:
            try:
                result = await lookup_one(db, profile, code_frequencies=frequencies,
                                          population_size=population)
            except Exception:
                result = unavailable_result("matching_failed")
            result["index"] = index
            if result.get("candidate_id"):
                result["profile_url"] = web_base.rstrip("/") + "/candidate-bank?candidateId=" + quote(result["candidate_id"], safe="")
            for key in ("top_match", "second_match"):
                if result.get(key):
                    result[key]["profile_url"] = web_base.rstrip("/") + "/candidate-bank?candidateId=" + quote(result[key]["candidate_id"], safe="")
            for match in result.get("ranked_matches", []):
                if match.get("candidate_id"):
                    match["profile_url"] = web_base.rstrip("/") + "/candidate-bank?candidateId=" + quote(match["candidate_id"], safe="")
            return result

    if not profiles:
        return []
    tasks = [asyncio.create_task(one(i, p)) for i, p in enumerate(profiles)]
    try:
        _, pending = await asyncio.wait(tasks, timeout=BATCH_TIMEOUT_S)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return [dict(index=i, **unavailable_result("lookup_deadline_exceeded"))
                if task in pending else task.result() for i, task in enumerate(tasks)]
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def load_frequency_snapshot(db, profiles):
    async def read():
        meta = await db.identity_code_stats.find_one({"_id": "__meta__"})
        if not meta or meta.get("version") != "identity-v1":
            return None, None
        size = meta.get("population_size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 1 or not meta.get("snapshot_id"):
            return None, None
        codes = sorted({code for profile in profiles
                        for code in build_identity_signature(public_profile(profile))["codes"]})
        if not codes:
            return None, None
        rows = await db.identity_code_stats.find(
            {"snapshot_id": meta["snapshot_id"], "code": {"$in": codes}},
            {"_id": 0, "code": 1, "document_count": 1},
        ).to_list(len(codes))
        counts = {row["code"]: row["document_count"] for row in rows
                  if isinstance(row.get("document_count"), int)
                  and not isinstance(row["document_count"], bool)
                  and 0 <= row["document_count"] <= size and row.get("code") in codes}
        return counts, size
    try:
        return await asyncio.wait_for(read(), timeout=1)
    except Exception:
        return None, None
