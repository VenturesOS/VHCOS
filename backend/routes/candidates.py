"""
Candidate routes for VHC Talent OS.

FIXED: The duplicate parse_resume_with_ai() implementation that existed
in this file (lines 130-175) has been removed. All resume parsing now
routes through the single canonical implementation in
services/matching_engine.py which applies normalize_candidate() and
produces the dual-write schema (canonical + alias field names).

The import below preserves backward compatibility — any code in this
file that called the local parse_resume_with_ai() continues to work
unchanged.
"""
import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── Single canonical parser — do NOT re-implement here ───────────────────
from services.matching_engine import (
    parse_resume_with_ai,          # canonical, normalizes output
    extract_text_from_file,        # text extraction helper
    find_similar_candidate,        # dedup helper
    generate_resume_fingerprint,   # fingerprint helper
)
from services.schema_normalizer import (
    normalize_candidate,
    get_skills,
    get_summary,
    get_experience_years,
)
from services.embeddings import embedding_service, process_candidate_embedding
from services.cache import cache
from services.candidate_bank_service import SEARCH_FIELDS, parse_boolean_query, _term_to_mongo

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/candidate-bank", tags=["candidate-bank"])
candidates_router = router


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

async def get_db():
    from config import db
    return db


from utils.auth import get_current_user, require_role


# ---------------------------------------------------------------------------
# Batch CV parse + save
# ---------------------------------------------------------------------------

@router.post("/batch-parse")
async def batch_parse_cvs(
    files: List[UploadFile] = File(...),
    current_user=Depends(require_role(["admin", "employer", "recruiter"])),
):
    """Parse multiple CV files in one request. Uses parallel processing with retries."""
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files per batch")

    results = []
    parsed = 0
    failed = 0

    # Semaphore to limit concurrent AI calls (avoid rate limits)
    sem = asyncio.Semaphore(3)

    async def parse_single_file(file: UploadFile):
        temp_id = str(uuid.uuid4())[:8]
        ext = Path(file.filename or "").suffix.lower()

        if ext not in (".pdf", ".doc", ".docx"):
            return {
                "temp_id": temp_id,
                "filename": file.filename,
                "status": "failed",
                "error": f"Unsupported file type: {ext}",
                "parsed_data": None,
                "duplicate_check": None,
            }

        try:
            content = await file.read()
            if len(content) > 10 * 1024 * 1024:
                raise ValueError("File too large (max 10MB)")

            # Run blocking text extraction in thread pool to avoid blocking the event loop
            # (blocking the event loop kills Gunicorn worker heartbeat → WORKER TIMEOUT)
            loop = asyncio.get_event_loop()
            resume_text = await loop.run_in_executor(
                None, extract_text_from_file, content, file.filename or "resume"
            )
            if not resume_text or len(resume_text.strip()) < 30:
                raise ValueError(
                    f"Could not extract readable text from {ext} file. "
                    "The file may be image-based/scanned or password-protected. "
                    "Try re-saving as a text-based PDF."
                )

            # AI parsing with semaphore concurrency control
            parse_result = None
            last_error = None
            for attempt in range(3):
                try:
                    async with sem:
                        parse_result = await asyncio.wait_for(
                            parse_resume_with_ai(resume_text[:8000]),
                            timeout=90.0,
                        )
                    if parse_result.get("success"):
                        break
                    last_error = parse_result.get("error", "AI parsing failed")
                except asyncio.TimeoutError:
                    last_error = "AI parsing timed out (90s)"
                    logger.warning(f"[Batch Parse] Attempt {attempt+1}/3 timed out for {file.filename}")
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"[Batch Parse] Attempt {attempt+1}/3 failed for {file.filename}: {e}")
                if attempt < 2:
                    await asyncio.sleep(1)

            if not parse_result or not parse_result.get("success"):
                raise ValueError(f"AI parsing failed after 3 attempts: {last_error}")

            data = parse_result["data"]

            # Check for duplicates
            from config import db
            dup_check = None
            email = data.get("email") or data.get("personal_email")
            name = data.get("name") or data.get("candidate_name")
            if email:
                existing = await db.candidate_bank.find_one(
                    {"email": email.lower().strip()}, {"_id": 0, "id": 1, "name": 1, "email": 1, "source": 1}
                )
                if existing:
                    dup_check = {"is_duplicate": True, "existing_candidate": existing}
            if not dup_check and name:
                import re
                name_regex = re.compile(f"^{re.escape(name.strip())}$", re.IGNORECASE)
                existing = await db.candidate_bank.find_one(
                    {"name": name_regex}, {"_id": 0, "id": 1, "name": 1, "email": 1, "source": 1}
                )
                if existing:
                    dup_check = {"is_duplicate": True, "existing_candidate": existing}

            return {
                "temp_id": temp_id,
                "filename": file.filename,
                "status": "parsed",
                "error": None,
                "parsed_data": {
                    "name": name,
                    "email": email,
                    "phone": data.get("phone") or data.get("mobile"),
                    "skills": get_skills(data),
                    "experience_summary": get_summary(data),
                    "experience_years": get_experience_years(data),
                    "location": data.get("location") or data.get("current_location"),
                    "current_company": data.get("current_company") or data.get("current_employer"),
                    "designation": data.get("designation") or data.get("current_designation"),
                    "work_experience": data.get("work_experience") or data.get("experience") or [],
                    "education": data.get("education") or [],
                    "headline": data.get("headline") or data.get("resume_headline"),
                },
                "duplicate_check": dup_check,
                "raw_parsed": data,
            }

        except Exception as e:
            logger.error(f"[Batch Parse] Failed {file.filename}: {e}")
            return {
                "temp_id": temp_id,
                "filename": file.filename,
                "status": "failed",
                "error": str(e),
                "parsed_data": None,
                "duplicate_check": None,
            }

    # Process all files in parallel (bounded by semaphore)
    results = await asyncio.gather(*[parse_single_file(f) for f in files])
    results = list(results)

    parsed = sum(1 for r in results if r["status"] == "parsed")
    failed = sum(1 for r in results if r["status"] == "failed")

    return {"total": len(files), "parsed": parsed, "failed": failed, "results": results}


@router.post("/batch-save")
async def batch_save_candidates(
    data: dict,
    current_user=Depends(require_role(["admin", "employer", "recruiter"])),
):
    """Save a batch of reviewed/edited parsed candidates to the candidate bank.
    Uses the same non-destructive merge logic as single CV upload.
    """
    from config import db
    from routes.extension import normalize_phone, build_team_visibility
    from routes.cv_upload import _build_cv_document, _merge_cv_into_existing

    candidates = data.get("candidates", [])
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates to save")

    mandate_id = data.get("mandate_id")  # Optional: link all candidates to this job
    saved = 0
    updated = 0
    linked = 0
    errors = []
    now = datetime.now(timezone.utc).isoformat()
    saved_candidate_ids = []  # Track IDs for mandate linking

    visibility_data = await build_team_visibility(current_user)
    visibility = visibility_data.get("visibility", {"employer_ids": [], "recruiter_ids": []})

    for c in candidates:
        try:
            editing = c.get("editing", c)
            name = (editing.get("name") or "").strip()
            if not name:
                errors.append({"temp_id": c.get("temp_id"), "error": "Name is required"})
                continue

            email = (editing.get("email") or "").lower().strip() or None
            phone = editing.get("phone")
            candidate_id = c.get("existing_candidate_id")
            existing = None

            # Check for existing record to merge into
            if candidate_id:
                existing = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})

            if not existing and email:
                existing = await db.candidate_bank.find_one({"email": email}, {"_id": 0})

            if not existing and name:
                import re
                name_regex = re.compile(f"^{re.escape(name)}$", re.IGNORECASE)
                existing = await db.candidate_bank.find_one({"name": name_regex}, {"_id": 0})

            if existing:
                candidate_id = existing["id"]
                # Build CV doc from the editing data for merge
                profile = {
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "key_skills": editing.get("skills", []),
                    "headline": editing.get("headline"),
                    "profile_summary": editing.get("experience_summary"),
                    "location": editing.get("location"),
                    "total_experience_years": editing.get("experience_years"),
                    "current_company": editing.get("current_company"),
                    "current_designation": editing.get("designation"),
                    "work_experience": c.get("raw_parsed", {}).get("work_experience") or c.get("raw_parsed", {}).get("experience") or [],
                    "education": c.get("raw_parsed", {}).get("education") or [],
                }
                cv_doc = _build_cv_document(profile, {"filename": c.get("filename")}, current_user, candidate_id, now)
                merged = _merge_cv_into_existing(existing, cv_doc, profile)
                merged["updated_at"] = now
                merged["has_resume"] = True
                merged.setdefault("source_history", existing.get("source_history", []))
                merged["source_history"].append({
                    "source": "batch_upload",
                    "filename": c.get("filename", "unknown"),
                    "uploaded_by": current_user.get("email"),
                    "uploaded_at": now,
                })

                # Apply user-edited mandatory fields (override merge for these)
                if editing.get("current_salary"):
                    try:
                        merged["current_salary"] = int(editing["current_salary"])
                    except (ValueError, TypeError):
                        pass
                if editing.get("notice_period"):
                    merged["notice_period"] = editing["notice_period"]
                if editing.get("location"):
                    merged["location"] = editing["location"]
                if editing.get("experience_years"):
                    try:
                        merged["experience_years"] = float(editing["experience_years"])
                    except (ValueError, TypeError):
                        pass

                await db.candidate_bank.update_one({"id": candidate_id}, {"$set": merged})
                saved_candidate_ids.append({"id": candidate_id, "name": merged.get("name", name)})
                updated += 1
            else:
                # New candidate
                candidate_id = str(uuid.uuid4())
                doc = {
                    "id": candidate_id,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "phone_normalized": normalize_phone(phone) if phone else None,
                    "skills": editing.get("skills", []),
                    "skills_display": ", ".join(editing.get("skills", [])),
                    "headline": editing.get("headline"),
                    "summary": editing.get("experience_summary"),
                    "location": editing.get("location"),
                    "experience_years": float(editing.get("experience_years") or 0) if editing.get("experience_years") else None,
                    "current_employer": editing.get("current_company"),
                    "designation": editing.get("designation"),
                    "experience": c.get("raw_parsed", {}).get("work_experience") or c.get("raw_parsed", {}).get("experience") or [],
                    "education": c.get("raw_parsed", {}).get("education") or [],
                    "has_resume": True,
                    "resume_title": c.get("filename"),
                    "source": "batch_upload",
                    "source_details": {
                        "upload_method": "batch_upload",
                        "filename": c.get("filename", "unknown"),
                        "captured_by": current_user["id"],
                        "captured_by_email": current_user.get("email"),
                        "captured_at": now,
                    },
                    "visibility": visibility,
                    "created_by": current_user["id"],
                    "created_at": now,
                    "updated_at": now,
                }

                if editing.get("current_salary"):
                    try:
                        doc["current_salary"] = int(editing["current_salary"])
                    except (ValueError, TypeError):
                        pass
                if editing.get("notice_period"):
                    doc["notice_period"] = editing["notice_period"]

                await db.candidate_bank.insert_one(doc)
                saved_candidate_ids.append({"id": candidate_id, "name": name})
                saved += 1

        except Exception as e:
            logger.error(f"[Batch Save] Error saving {c.get('filename', '?')}: {e}")
            errors.append({"temp_id": c.get("temp_id"), "error": str(e)})

    # Link all saved candidates to mandate if specified
    if mandate_id and saved_candidate_ids:
        job = await db.jobs.find_one({"id": mandate_id}, {"_id": 0, "id": 1})
        if job:
            for sc in saved_candidate_ids:
                try:
                    existing_app = await db.applications.find_one(
                        {"candidate_id": sc["id"], "job_id": mandate_id}, {"_id": 0, "id": 1}
                    )
                    if not existing_app:
                        app_id = str(uuid.uuid4())
                        cand = await db.candidate_bank.find_one({"id": sc["id"]}, {"_id": 0, "name": 1, "email": 1, "phone": 1})
                        await db.applications.insert_one({
                            "id": app_id,
                            "job_id": mandate_id,
                            "candidate_id": sc["id"],
                            "candidate_name": (cand or {}).get("name", sc.get("name", "")),
                            "candidate_email": (cand or {}).get("email", ""),
                            "candidate_phone": (cand or {}).get("phone", ""),
                            "stage": "sourced",
                            "status": "active",
                            "source": "batch_upload",
                            "created_by": current_user["id"],
                            "created_at": now,
                            "updated_at": now,
                            "stage_history": [{"stage": "sourced", "moved_by": current_user["id"], "moved_by_name": current_user.get("name", ""), "timestamp": now}],
                        })
                        linked += 1
                except Exception as link_err:
                    logger.warning(f"[Batch Save] Failed to link {sc['id']} to mandate {mandate_id}: {link_err}")

    return {
        "success": True,
        "saved": saved,
        "updated": updated,
        "linked": linked,
        "mandate_id": mandate_id,
        "errors": errors,
        "total": len(candidates),
    }


# ---------------------------------------------------------------------------
# Upload and parse a single CV
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_candidate_cv(
    file: UploadFile = File(...),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Upload a single CV file, parse it with AI, and create/update a candidate.
    Idempotent: duplicate emails are updated, not duplicated.
    """
    allowed_extensions = {".pdf", ".doc", ".docx"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(allowed_extensions)}",
        )

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    # Security: validate file content (magic bytes + threat scan)
    from services.security_service import validate_upload as _sec_validate
    sec_check = await _sec_validate(content, file.filename or "resume", current_user.get("email", "internal"))
    if not sec_check["valid"]:
        raise HTTPException(status_code=400, detail=sec_check["reason"])

    resume_text = None
    try:
        # PDF/DOCX parsing is CPU-bound — run off the event loop so a slow file
        # doesn't time out the gunicorn worker (causes Cloudflare 502 HTML →
        # frontend sees "Unexpected token '<' — not valid JSON").
        loop = asyncio.get_event_loop()
        resume_text = await loop.run_in_executor(
            None, extract_text_from_file, content, file.filename or "resume"
        )
    except Exception as e:
        logger.error(f"[candidate-bank/upload] text extraction failed: {e}")
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse file: {str(e)[:200]}. The file may be corrupted or unsupported.",
        )
    if not resume_text or len(resume_text.strip()) < 30:
        raise HTTPException(
            status_code=422,
            detail="Could not extract readable text from the file. The file may be image-based (scanned PDF), password-protected, or corrupted.",
        )

    # Parse with canonical parser — output is already normalized
    parse_result = await parse_resume_with_ai(resume_text[:8000])
    if not parse_result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Resume parsing failed: {parse_result.get('error', 'Unknown error')}",
        )

    candidate_data = parse_result["data"]  # normalized by parse_resume_with_ai()

    now            = datetime.now(timezone.utc).isoformat()
    candidate_id   = str(uuid.uuid4())
    fingerprint    = generate_resume_fingerprint(resume_text)

    # ── Upload CV to R2 so download works from the profile ──
    # Without this, /candidate-bank/{id}/download-resume returns 404 and the
    # "Download Resume" button never appears. Mirrors bulk-import/attach-cv logic.
    file_id = str(uuid.uuid4())
    try:
        from services.r2_storage import generate_r2_key, upload_to_r2
        content_type_map = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        r2_key = generate_r2_key("candidate-cv", file.filename or "resume")
        r2_result = await upload_to_r2(content, r2_key, content_type_map.get(ext, "application/octet-stream"))
        resume_version = {
            "id": file_id,
            "fingerprint": fingerprint,
            "uploaded_at": now,
            "uploaded_by": current_user["id"],
            "is_active": True,
            "r2_metadata": r2_result,
            "original_filename": file.filename or "resume",
        }
    except Exception as _r2_err:
        logger.warning(f"[candidate-bank/upload] R2 upload failed (non-fatal, will save parsed data only): {_r2_err}")
        resume_version = None

    candidate_data.update({
        "id":                  candidate_id,
        "created_by":          current_user["id"],
        "created_at":          now,
        "updated_at":          now,
        "source":              "cv_upload",
        "resume_fingerprints": [fingerprint],
    })
    if resume_version:
        candidate_data["active_resume_id"] = file_id
        # Store as single dict on candidate_data; persisted via $push below so
        # existing candidates accumulate versions instead of being overwritten.
        candidate_data["_pending_resume_version"] = resume_version
        candidate_data["cv_attached"] = True

    # ── Idempotent upsert ─────────────────────────────────────────────────
    email = candidate_data.get("email")
    if email:
        upsert_filter = {"email": email}
    else:
        phone_norm = candidate_data.get("phone_normalized")
        if phone_norm and len(phone_norm) == 10:
            upsert_filter = {"phone_normalized": phone_norm}
        else:
            upsert_filter = {"id": candidate_id}

    # Separate fields for $set vs $setOnInsert to avoid MongoDB path conflicts
    # Resume-version array: handle carefully so existing candidates accumulate
    # versions instead of being overwritten. Pull it out of $set and append
    # via $push (or $setOnInsert on first create).
    _new_version = candidate_data.pop("_pending_resume_version", None)
    _has_cv = candidate_data.pop("cv_attached", False)
    _new_active_id = candidate_data.pop("active_resume_id", None)

    set_data = {k: v for k, v in candidate_data.items() if k not in ("created_at", "id", "resume_fingerprints")}
    set_data["updated_at"] = now
    if _has_cv and _new_active_id:
        set_data["cv_attached"] = True
        set_data["active_resume_id"] = _new_active_id

    update_doc = {
        "$set":         set_data,
        "$setOnInsert": {"created_at": now, "id": candidate_id},
        "$addToSet":    {"resume_fingerprints": fingerprint},
    }
    if _new_version:
        # Append new version to the array on both insert and update
        update_doc["$push"] = {"resume_versions": _new_version}

    await db.candidate_bank.update_one(
        upsert_filter,
        update_doc,
        upsert=True,
    )

    # Invalidate search cache so new candidate appears in searches
    cache.invalidate_search_cache()

    # Generate embedding (non-blocking)
    try:
        await process_candidate_embedding(candidate_id, candidate_data, db)
    except Exception as e:
        logger.warning(f"Embedding generation failed for {candidate_id}: {e}")

    return {
        "success":      True,
        "candidate_id": candidate_id,
        "name":         candidate_data.get("name"),
        "email":        candidate_data.get("email"),
        "skills_count": len(get_skills(candidate_data)),
        "experience_years": get_experience_years(candidate_data),
    }


# ---------------------------------------------------------------------------
# List candidates
# ---------------------------------------------------------------------------


@router.get("/filter-options")
async def get_filter_options(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return distinct values for filter dropdowns."""
    locations = await db.candidate_bank.distinct("location")
    companies = await db.candidate_bank.distinct("current_company")
    sources = await db.candidate_bank.distinct("source")

    def clean_list(lst):
        return sorted(set(str(v).strip() for v in lst if v and str(v).strip()))

    return {
        "locations": clean_list(locations)[:50],
        "companies": clean_list(companies)[:50],
        "sources": clean_list(sources),
        "notice_periods": ["Immediate", "15 days", "30 days", "45 days", "60 days", "90 days", "90+ days"],
    }


# ── Data Quality ──

CRITICAL_FIELDS = ["email", "phone"]
IMPORTANT_FIELDS = ["skills", "current_employer", "designation", "location", "industry"]

def _empty_check(field):
    """MongoDB filter for empty/missing field."""
    return {"$or": [
        {field: {"$exists": False}},
        {field: None},
        {field: ""},
        {field: []},
    ]}


@router.get("/data-quality/stats")
async def data_quality_stats(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return data quality stats: missing fields breakdown by source."""
    total = await db.candidate_bank.count_documents({})
    if total == 0:
        return {"total": 0, "fields": {}, "by_source": {}, "score": 100}

    all_fields = CRITICAL_FIELDS + IMPORTANT_FIELDS

    # Single aggregation to count missing values for all fields at once
    group_stage = {"_id": None, "total": {"$sum": 1}}
    for f in all_fields:
        group_stage[f"miss_{f}"] = {
            "$sum": {"$cond": [
                {"$or": [
                    {"$eq": [{"$ifNull": [f"${f}", None]}, None]},
                    {"$eq": [f"${f}", ""]},
                    {"$eq": [f"${f}", []]},
                ]},
                1, 0
            ]}
        }

    pipeline_result = await db.candidate_bank.aggregate([{"$group": group_stage}]).to_list(1)
    counts = pipeline_result[0] if pipeline_result else {}

    field_stats = {}
    for f in all_fields:
        missing = counts.get(f"miss_{f}", 0)
        field_stats[f] = {
            "missing": missing,
            "filled": total - missing,
            "pct_filled": round((total - missing) / total * 100, 1),
        }

    # Source breakdown - single aggregation for critical fields by source
    source_pipeline = [
        {"$group": {
            "_id": "$source",
            "total": {"$sum": 1},
            **{
                f"miss_{f}": {"$sum": {"$cond": [
                    {"$or": [
                        {"$eq": [{"$ifNull": [f"${f}", None]}, None]},
                        {"$eq": [f"${f}", ""]},
                    ]},
                    1, 0
                ]}}
                for f in CRITICAL_FIELDS
            }
        }},
        {"$sort": {"total": -1}},
    ]
    source_results = await db.candidate_bank.aggregate(source_pipeline).to_list(20)

    by_source = {}
    for sr in source_results:
        src = sr.get("_id")
        if not src:
            continue
        missing_critical = {}
        for f in CRITICAL_FIELDS:
            cnt = sr.get(f"miss_{f}", 0)
            if cnt > 0:
                missing_critical[f] = cnt
        by_source[src] = {"total": sr["total"], "missing_critical": missing_critical}

    # Overall score
    critical_score = sum(field_stats[f]["pct_filled"] for f in CRITICAL_FIELDS) / len(CRITICAL_FIELDS)
    important_score = sum(field_stats[f]["pct_filled"] for f in IMPORTANT_FIELDS) / len(IMPORTANT_FIELDS)
    overall = round(critical_score * 0.6 + important_score * 0.4, 1)

    return {
        "total": total,
        "fields": field_stats,
        "by_source": by_source,
        "score": overall,
    }


@router.get("/data-quality/team-stats")
async def data_quality_team_stats(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Per-recruiter data quality stats: capture counts and field fill rates."""
    all_check_fields = CRITICAL_FIELDS + IMPORTANT_FIELDS

    # Aggregate capture stats per user
    pipeline = [
        {"$match": {"created_by": {"$ne": None}}},
        {"$group": {
            "_id": "$created_by",
            "total": {"$sum": 1},
            **{
                f"miss_{f}": {"$sum": {"$cond": [
                    {"$or": [
                        {"$eq": [{"$ifNull": [f"${f}", None]}, None]},
                        {"$eq": [f"${f}", ""]},
                        {"$eq": [f"${f}", []]},
                    ]},
                    1, 0
                ]}}
                for f in all_check_fields
            },
            "ext_count": {"$sum": {"$cond": [
                {"$regexMatch": {"input": {"$ifNull": ["$source", ""]}, "regex": "extension"}}, 1, 0
            ]}},
            "excel_count": {"$sum": {"$cond": [
                {"$eq": ["$source", "naukri_excel_import"]}, 1, 0
            ]}},
            "manual_count": {"$sum": {"$cond": [
                {"$in": ["$source", ["admin", "recruiter", "employer", "cv_upload", "bulk_import"]]}, 1, 0
            ]}},
            "latest_capture": {"$max": "$created_at"},
        }},
        {"$sort": {"total": -1}},
    ]

    results = await db.candidate_bank.aggregate(pipeline).to_list(500)
    capture_map = {r["_id"]: r for r in results}

    # Fetch ALL users with relevant roles
    all_users = await db.users.find(
        {"role": {"$in": ["admin", "recruiter", "employer"]}, "deleted_at": None},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(500)

    team_stats = []
    for user in all_users:
        uid = user["id"]
        r = capture_map.get(uid)
        total = r["total"] if r else 0

        field_rates = {}
        if total > 0:
            for f in all_check_fields:
                missing = r.get(f"miss_{f}", 0)
                field_rates[f] = round((total - missing) / total * 100, 1)
        else:
            for f in all_check_fields:
                field_rates[f] = 0

        if total > 0:
            critical_avg = sum(field_rates[f] for f in CRITICAL_FIELDS) / len(CRITICAL_FIELDS)
            important_avg = sum(field_rates[f] for f in IMPORTANT_FIELDS) / len(IMPORTANT_FIELDS)
            score = round(critical_avg * 0.6 + important_avg * 0.4, 1)
        else:
            score = 0

        team_stats.append({
            "user_id": uid,
            "name": user.get("name", "Unknown"),
            "email": user.get("email", ""),
            "role": user.get("role", ""),
            "total": total,
            "field_rates": field_rates,
            "score": score,
            "sources": {
                "extension": r.get("ext_count", 0) if r else 0,
                "excel": r.get("excel_count", 0) if r else 0,
                "manual": r.get("manual_count", 0) if r else 0,
            },
            "latest_capture": r.get("latest_capture") if r else None,
        })

    team_stats.sort(key=lambda x: x["score"], reverse=True)
    return {"team": team_stats}


@router.get("/data-quality/incomplete")
async def data_quality_incomplete(
    field: str = Query(..., description="Field to filter by"),
    source: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List candidates missing a specific field."""
    allowed = CRITICAL_FIELDS + IMPORTANT_FIELDS
    if field not in allowed:
        raise HTTPException(400, f"Field must be one of: {allowed}")

    query = _empty_check(field)
    if source:
        query = {"$and": [query, {"source": source}]}

    total = await db.candidate_bank.count_documents(query)
    skip = (page - 1) * limit
    candidates = await db.candidate_bank.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "source": 1,
         "current_employer": 1, "designation": 1, "location": 1, "skills": 1,
         "created_at": 1, "industry": 1},
        allow_disk_use=True,
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    return {"total": total, "page": page, "pages": (total + limit - 1) // limit, "candidates": candidates}


@router.put("/data-quality/update/{candidate_id}")
async def data_quality_update(
    candidate_id: str,
    updates: dict,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Quick-edit a candidate's missing fields."""
    allowed_fields = {"email", "phone", "skills", "current_employer", "designation",
                      "location", "industry", "headline", "current_salary", "notice_period"}
    clean = {k: v for k, v in updates.items() if k in allowed_fields and v is not None}
    if not clean:
        raise HTTPException(400, "No valid fields to update")

    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    clean["last_updated_by"] = current_user.get("id", "unknown")

    result = await db.candidate_bank.update_one({"id": candidate_id}, {"$set": clean})
    if result.matched_count == 0:
        raise HTTPException(404, "Candidate not found")
    return {"message": "Updated", "fields_updated": list(clean.keys())}



# ---------------------------------------------------------------------------
# PHONE NUMBER BLOCKLIST (Data Quality — Admin Only)
# ---------------------------------------------------------------------------

INITIAL_BLOCKLIST = [
    "8882924190", "9015895757", "8859988527", "9466863285", "8882924151",
    "9560994589", "8950766572", "8397909062", "8882924147", "9810918181",
    "9810557983", "8595198477", "9810557485", "8076891442", "8882924188",
    "6362868049", "8076859021", "9306419180", "9654727639", "9211845705",
    "8882924185", "9063681730", "9671803766", "9740365955", "9354941064",
]


async def _get_blocklist(db) -> list:
    """Get all blocked phone numbers."""
    doc = await db.phone_blocklist.find_one({"type": "blocklist"}, {"_id": 0})
    if not doc:
        # Seed initial blocklist
        await db.phone_blocklist.insert_one({"type": "blocklist", "numbers": INITIAL_BLOCKLIST})
        return INITIAL_BLOCKLIST
    return doc.get("numbers", [])


async def is_phone_blocked(db, phone: str) -> bool:
    """Check if a phone number is in the blocklist."""
    if not phone:
        return False
    clean = phone.strip().replace(" ", "").replace("-", "").replace("+91", "")[-10:]
    blocklist = await _get_blocklist(db)
    return clean in blocklist


async def _cleanup_numbers_from_candidate_bank(db, numbers: list) -> int:
    """Null out phone fields on any candidate currently holding one of the
    given blocked numbers. Used by:
      • POST /phone-blocklist (auto-clean on add)
      • POST /phone-blocklist/cleanup (manual full sweep)
    Returns modified_count.
    """
    if not numbers:
        return 0
    patterns = []
    for n in numbers:
        patterns.append({"phone": {"$regex": n}})
        patterns.append({"phone_normalized": n})
        patterns.append({"mobile": {"$regex": n}})
    result = await db.candidate_bank.update_many(
        {"$or": patterns},
        {"$set": {"phone": None, "phone_normalized": None, "mobile": None, "phone_blocked": True}},
    )
    return result.modified_count


@router.get("/data-quality/phone-blocklist")
async def get_phone_blocklist(
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Get all blocked phone numbers. Admin only."""
    numbers = await _get_blocklist(db)
    return {"numbers": numbers, "count": len(numbers)}


@router.post("/data-quality/phone-blocklist")
async def add_to_blocklist(
    body: dict,
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Add phone numbers to blocklist. Body: {"numbers": ["1234567890", ...]}"""
    new_numbers = body.get("numbers", [])
    if not new_numbers:
        raise HTTPException(status_code=400, detail="No numbers provided")

    # Clean numbers
    cleaned = []
    for n in new_numbers:
        clean = str(n).strip().replace(" ", "").replace("-", "").replace("+91", "")[-10:]
        if len(clean) == 10 and clean.isdigit():
            cleaned.append(clean)

    if not cleaned:
        raise HTTPException(status_code=400, detail="No valid 10-digit numbers found")

    await db.phone_blocklist.update_one(
        {"type": "blocklist"},
        {"$addToSet": {"numbers": {"$each": cleaned}}},
        upsert=True,
    )

    # Auto-cleanup: immediately null the phone/mobile on any candidate that
    # currently holds one of the just-blocked numbers. No more waiting on the
    # manual "Clean Existing Profiles" button.
    cleaned_count = await _cleanup_numbers_from_candidate_bank(db, cleaned)

    return {
        "message": f"Added {len(cleaned)} numbers to blocklist",
        "added": cleaned,
        "auto_cleaned_candidates": cleaned_count,
    }


@router.delete("/data-quality/phone-blocklist/{phone}")
async def remove_from_blocklist(
    phone: str,
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Remove a phone number from blocklist."""
    clean = phone.strip().replace(" ", "").replace("-", "").replace("+91", "")[-10:]
    await db.phone_blocklist.update_one(
        {"type": "blocklist"},
        {"$pull": {"numbers": clean}},
    )
    return {"message": f"Removed {clean} from blocklist"}


@router.post("/data-quality/phone-blocklist/cleanup")
async def cleanup_blocked_numbers(
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Remove blocked phone numbers from ALL existing candidate profiles.

    Kept for the rare case someone wants to do a full-bank sweep (e.g. after
    manually editing Mongo). The `POST /phone-blocklist` endpoint now runs
    this automatically on each new number added.
    """
    blocklist = await _get_blocklist(db)
    if not blocklist:
        return {"message": "Blocklist is empty", "cleaned": 0}
    cleaned_count = await _cleanup_numbers_from_candidate_bank(db, blocklist)
    return {
        "message": f"Cleaned {cleaned_count} candidate profiles",
        "cleaned": cleaned_count,
        "blocklist_size": len(blocklist),
    }


@router.post("/data-quality/fix-work-experience-durations")
async def fix_work_experience_durations(
    dry_run: bool = Query(False, description="Preview without writing"),
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Recompute duration ('Xy Ym') for work_experience entries that were stored
    as '0y 0m' or empty. Uses from_date/to_date (or today for current roles).
    """
    from services.llm_fallback_service import _fix_work_experience_durations

    # Find candidates with any experience entry missing/zero duration
    query = {
        "$or": [
            {"experience.duration": {"$in": ["", None, "0y 0m", "0 y 0 m"]}},
            {"experience.duration": {"$exists": False}},
        ]
    }
    cursor = db.candidate_bank.find(query, {"id": 1, "experience": 1, "_id": 0})

    scanned = 0
    updated = 0
    total_entries_fixed = 0
    async for doc in cursor:
        scanned += 1
        exp_list = doc.get("experience") or []
        if not exp_list:
            continue
        before_snapshot = [(e or {}).get("duration") for e in exp_list]
        wrapped = {"work_experience": exp_list}
        _fix_work_experience_durations(wrapped)
        after_snapshot = [(e or {}).get("duration") for e in wrapped["work_experience"]]
        entry_fixes = sum(1 for a, b in zip(before_snapshot, after_snapshot) if a != b)
        if entry_fixes == 0:
            continue
        total_entries_fixed += entry_fixes
        updated += 1
        if not dry_run:
            await db.candidate_bank.update_one(
                {"id": doc["id"]},
                {"$set": {"experience": wrapped["work_experience"]}},
            )

    return {
        "message": f"{'DRY RUN — ' if dry_run else ''}Fixed {total_entries_fixed} work-experience durations across {updated} candidates",
        "scanned_candidates": scanned,
        "candidates_updated": updated,
        "durations_recomputed": total_entries_fixed,
        "dry_run": dry_run,
    }


@router.post("/data-quality/fix-ctc-outliers")
async def fix_ctc_outliers(
    dry_run: bool = Query(False, description="Preview without writing"),
    max_sane_ctc: int = Query(50_000_000, description="Upper bound in rupees — values above this will be nulled"),
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Null out current_salary/expected_salary values that are corrupted (above the sane cap).
    Default cap is ₹5 Cr (50,000,000 rupees/year). Any value above is treated as extraction garbage.
    """
    # Only scan candidates with at least one out-of-range CTC value
    query = {
        "$or": [
            {"current_salary": {"$gt": max_sane_ctc}},
            {"expected_salary": {"$gt": max_sane_ctc}},
        ]
    }

    total = await db.candidate_bank.count_documents(query)

    if dry_run:
        # Surface a few samples for visibility
        sample = await db.candidate_bank.find(
            query,
            {"id": 1, "name": 1, "current_salary": 1, "expected_salary": 1, "_id": 0},
        ).limit(10).to_list(10)
        return {
            "message": f"DRY RUN — {total} candidates have CTC values above ₹{max_sane_ctc:,}",
            "cap": max_sane_ctc,
            "candidates_to_clean": total,
            "sample": sample,
            "dry_run": True,
        }

    # Null current_salary if > cap
    res_curr = await db.candidate_bank.update_many(
        {"current_salary": {"$gt": max_sane_ctc}},
        {"$set": {"current_salary": None}},
    )
    # Null expected_salary if > cap
    res_exp = await db.candidate_bank.update_many(
        {"expected_salary": {"$gt": max_sane_ctc}},
        {"$set": {"expected_salary": None}},
    )
    return {
        "message": f"Cleaned {total} candidates: nulled {res_curr.modified_count} current_salary + {res_exp.modified_count} expected_salary values above ₹{max_sane_ctc:,}",
        "cap": max_sane_ctc,
        "candidates_matched": total,
        "current_salary_nulled": res_curr.modified_count,
        "expected_salary_nulled": res_exp.modified_count,
        "dry_run": False,
    }


@router.post("/data-quality/bulk-re-enrich")
async def bulk_re_enrich(
    background_tasks: BackgroundTasks,
    since_hours: int = Query(24, ge=1, le=720, description="Look-back window in hours (default 24h)"),
    exclude_source: str = Query("runpod_qwen14b", description="Skip candidates already enriched by this source"),
    limit: int = Query(500, ge=1, le=5000, description="Max candidates to process in this run"),
    concurrency: int = Query(4, ge=1, le=16, description="Parallel extraction calls"),
    gaps_only: bool = Query(True, description="Only re-enrich candidates with missing top-card fields (exp=0, ctc=null, notice=null)"),
    dry_run: bool = Query(False),
    force: bool = Query(False, description="Skip RunPod health check (use only if you know what you're doing)"),
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Bulk re-enrich candidates through the full LLM pipeline (RunPod-first).
    Runs asynchronously in the background. Poll progress via GET /data-quality/bulk-re-enrich/status.
    Aborts if RunPod is unreachable (unless force=true) to avoid wasting fallback LLM credits.

    Filter modes:
    - gaps_only=true (default): only candidates missing exp/ctc/notice/location
    - gaps_only=false: everything in the since_hours window
    """
    from datetime import datetime, timezone, timedelta
    import asyncio
    import os
    import httpx
    from services.llm_fallback_service import extract_full_profile_fallback

    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    cutoff_iso = cutoff.isoformat()

    # Base: candidates captured in the window that have raw_text to re-process
    base_filters = [
        {"created_at": {"$gte": cutoff_iso}},
        {"ai_enrichment_source": {"$ne": exclude_source}},
        {"$or": [
            {"raw_text_for_enrichment": {"$exists": True, "$ne": ""}},
            {"raw_page_text": {"$exists": True, "$ne": ""}},
            {"raw_profile_text": {"$exists": True, "$ne": ""}},
        ]},
    ]

    if gaps_only:
        # "Has at least one missing top-card field" — most common re-enrich target
        gap_clause = {"$or": [
            {"experience_years": {"$in": [None, 0, 0.0]}},
            {"experience_years": {"$exists": False}},
            {"total_experience_years": {"$in": [None, 0, 0.0]}},
            {"current_salary": {"$in": [None, 0]}},
            {"current_salary": {"$exists": False}},
            {"current_ctc": {"$in": [None, 0]}},
            {"notice_period": {"$in": [None, ""]}},
            {"notice_period": {"$exists": False}},
            {"location": {"$in": [None, ""]}},
        ]}
        base_filters.append(gap_clause)

    query = {"$and": base_filters}

    total_matched = await db.candidate_bank.count_documents(query)

    if dry_run:
        pipeline = [
            {"$match": query},
            {"$group": {"_id": "$ai_enrichment_source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        breakdown = await db.candidate_bank.aggregate(pipeline).to_list(50)
        # Also probe RunPod health for visibility
        runpod_url = os.environ.get("RUNPOD_VLLM_URL", "")
        runpod_status = "unknown"
        if runpod_url:
            try:
                # Use same auth derivation logic as the LLM caller
                from services.llm_fallback_service import RUNPOD_API_KEY as _rk
                _hdrs = {"Authorization": f"Bearer {_rk}"} if _rk else {}
                async with httpx.AsyncClient(timeout=8.0) as c:
                    r = await c.get(f"{runpod_url.rstrip('/')}/v1/models", headers=_hdrs)
                    runpod_status = f"HTTP {r.status_code}" + (" ✅ healthy" if r.status_code == 200 else " ❌ DOWN")
            except Exception as e:
                runpod_status = f"❌ unreachable: {type(e).__name__}"
        return {
            "message": f"DRY RUN — {total_matched} candidates match (since {since_hours}h ago, excluding '{exclude_source}')",
            "candidates_to_process": min(total_matched, limit),
            "total_matched": total_matched,
            "source_breakdown": breakdown,
            "runpod_health": runpod_status,
            "dry_run": True,
        }

    # ── Pre-flight: RunPod health check ──
    if not force:
        runpod_url = os.environ.get("RUNPOD_VLLM_URL", "")
        if not runpod_url:
            raise HTTPException(400, "RUNPOD_VLLM_URL not configured and force=false — aborting")
        try:
            from services.llm_fallback_service import RUNPOD_API_KEY as _rk
            _hdrs = {"Authorization": f"Bearer {_rk}"} if _rk else {}
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(f"{runpod_url.rstrip('/')}/v1/models", headers=_hdrs)
                if r.status_code != 200:
                    raise HTTPException(
                        503,
                        f"RunPod /v1/models returned HTTP {r.status_code} — vLLM not ready. "
                        "Fix RunPod first or use force=true to proceed with fallbacks.",
                    )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(503, f"RunPod health probe failed ({type(e).__name__}). Use force=true to override.")

    # Fetch candidate list
    docs = await db.candidate_bank.find(
        query,
        {"id": 1, "name": 1, "raw_text_for_enrichment": 1, "raw_page_text": 1, "raw_profile_text": 1, "_id": 0},
    ).limit(limit).to_list(limit)

    # Initialise progress entry in DB (so GET /status can report it)
    job_id = str(uuid.uuid4())
    await db.bulk_enrich_jobs.insert_one({
        "id": job_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "total": len(docs),
        "succeeded": 0,
        "failed": 0,
        "skipped_no_text": 0,
        "by_source": {},
        "triggered_by": (user.get("email") if isinstance(user, dict) else None),
        "since_hours": since_hours,
        "concurrency": concurrency,
    })

    recruiter_phone = user.get("phone", "") if isinstance(user, dict) else ""
    recruiter_email = user.get("email", "") if isinstance(user, dict) else ""

    async def _run_job():
        """Background coroutine — does the heavy lifting, writes progress to DB."""
        from routes.extension import _apply_bg_enrichment
        from motor.motor_asyncio import AsyncIOMotorClient
        # Use a fresh motor client so we don't share with request-scope db
        _client = AsyncIOMotorClient(os.environ['MONGO_URL'])
        _jdb = _client[os.environ['DB_NAME']]

        stats = {"succeeded": 0, "failed": 0, "skipped_no_text": 0, "by_source": {}}
        sem = asyncio.Semaphore(concurrency)

        async def _worker(doc):
            async with sem:
                cid = doc["id"]
                name = doc.get("name") or "Unknown"
                raw_text = (
                    doc.get("raw_text_for_enrichment")
                    or doc.get("raw_page_text")
                    or doc.get("raw_profile_text")
                    or ""
                )
                if not raw_text or len(raw_text) < 200:
                    stats["skipped_no_text"] += 1
                else:
                    try:
                        result = await extract_full_profile_fallback(raw_text=raw_text, candidate_name=name)
                        if not result or result.get("error"):
                            stats["failed"] += 1
                        else:
                            src = result.get("source") or result.get("_extraction_source") or "unknown"
                            stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
                            # ⚠️  FIX: _apply_bg_enrichment is sync + spawns a MongoClient per call.
                            # Without to_thread it blocks the asyncio event loop → progress never flushes → UI stuck at 0%.
                            await asyncio.to_thread(
                                _apply_bg_enrichment, cid, name, result, raw_text, recruiter_phone, recruiter_email
                            )
                            stats["succeeded"] += 1
                    except Exception as e:
                        stats["failed"] += 1
                        logger.error(f"[Bulk-Re-Enrich] {name}: {e}")

                # Flush after EVERY candidate so the admin UI progress bar actually moves
                done = stats["succeeded"] + stats["failed"] + stats["skipped_no_text"]
                await _jdb.bulk_enrich_jobs.update_one(
                    {"id": job_id},
                    {"$set": {
                        **stats,
                        "processed": done,
                        "progress_pct": round(done * 100.0 / max(len(docs), 1), 1),
                        "last_update": datetime.now(timezone.utc).isoformat(),
                        "last_candidate": name,
                    }},
                )

        try:
            await asyncio.gather(*[_worker(d) for d in docs])
            await _jdb.bulk_enrich_jobs.update_one(
                {"id": job_id},
                {"$set": {
                    **stats,
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            logger.info(f"[Bulk-Re-Enrich] Job {job_id} completed: {stats}")
        except Exception as e:
            await _jdb.bulk_enrich_jobs.update_one(
                {"id": job_id},
                {"$set": {
                    **stats,
                    "status": "failed",
                    "error": str(e)[:500],
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            logger.error(f"[Bulk-Re-Enrich] Job {job_id} failed: {e}")
        finally:
            _client.close()

    background_tasks.add_task(_run_job)

    return {
        "message": f"Scheduled re-enrichment of {len(docs)} candidates (of {total_matched} matched). RunPod health OK.",
        "job_id": job_id,
        "scheduled": len(docs),
        "total_matched": total_matched,
        "remaining_after_this_batch": max(0, total_matched - len(docs)),
        "status_url": f"/api/candidate-bank/data-quality/bulk-re-enrich/status/{job_id}",
    }


@router.get("/data-quality/bulk-re-enrich/status/{job_id}")
async def bulk_re_enrich_status(
    job_id: str,
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Fetch the current progress of a bulk re-enrichment job."""
    job = await db.bulk_enrich_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    done = job.get("succeeded", 0) + job.get("failed", 0) + job.get("skipped_no_text", 0)
    total = job.get("total", 0) or 1
    job["progress_pct"] = round(done / total * 100, 1)
    job["done"] = done
    return job


@router.get("/data-quality/bulk-re-enrich/status")
async def bulk_re_enrich_status_latest(
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """List the 5 most recent bulk re-enrichment jobs.
    Side-effect: auto-aborts any `running` job with no progress for >10 minutes
    so a crashed worker never blocks the Start button indefinitely.
    """
    from datetime import datetime, timezone, timedelta
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    await db.bulk_enrich_jobs.update_many(
        {
            "status": "running",
            "$or": [
                {"last_update": {"$exists": False}},
                {"last_update": {"$lt": cutoff_iso}},
                {"last_update": None},
            ],
        },
        {"$set": {
            "status": "aborted",
            "error": "auto-aborted (no progress for >10m)",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    jobs = await db.bulk_enrich_jobs.find({}, {"_id": 0}).sort("started_at", -1).limit(5).to_list(5)
    for j in jobs:
        done = j.get("succeeded", 0) + j.get("failed", 0) + j.get("skipped_no_text", 0)
        total = j.get("total", 0) or 1
        j["progress_pct"] = round(done / total * 100, 1)
        j["done"] = done
    return {"jobs": jobs}


@router.post("/data-quality/bulk-re-enrich/abort-stale")
async def abort_stale_bulk_re_enrich_jobs(
    stale_minutes: int = Query(10, ge=1, le=1440),
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Mark any `running` job whose last_update is older than stale_minutes as aborted.
    Unblocks the Start button after a worker crash.
    """
    from datetime import datetime, timezone, timedelta
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
    # A job is stale if it is running AND (no last_update OR last_update < cutoff)
    query = {
        "status": "running",
        "$or": [
            {"last_update": {"$exists": False}},
            {"last_update": {"$lt": cutoff_iso}},
            {"last_update": None},
        ],
    }
    result = await db.bulk_enrich_jobs.update_many(
        query,
        {"$set": {
            "status": "aborted",
            "error": f"auto-aborted (no progress for >{stale_minutes}m)",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"aborted": result.modified_count, "stale_cutoff": cutoff_iso}


# ---------------------------------------------------------------------------
# Failed Capture Recovery (Data Quality section)
# ---------------------------------------------------------------------------

@router.get("/failed-captures")
async def get_failed_captures(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    show: str = Query("unrecovered", description="unrecovered, recovered, all"),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get failed Naukri extension captures for manual recovery."""
    query = {"status": "failed"}
    if show == "unrecovered":
        query["is_recovered"] = {"$ne": True}
    elif show == "recovered":
        query["is_recovered"] = True

    skip = (page - 1) * limit
    total = await db.naukri_capture_logs.count_documents(query)
    logs = await db.naukri_capture_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)

    unrecovered = await db.naukri_capture_logs.count_documents({"status": "failed", "is_recovered": {"$ne": True}})
    return {
        "logs": logs,
        "total": total,
        "unrecovered": unrecovered,
        "page": page,
        "pages": max(1, -(-total // limit)),
    }


@router.post("/failed-captures/{capture_id}/save-to-bank")
async def save_failed_capture_to_bank(
    capture_id: str,
    data: dict,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Fix a failed capture's data and save it to the candidate bank."""
    # Validate required fields
    name = (data.get("name") or "").strip()
    if not name or len(name) < 2:
        raise HTTPException(400, "Name is required (at least 2 characters)")

    email = (data.get("email") or "").strip() or None
    phone = (data.get("phone") or "").strip() or None
    if not email and not phone:
        raise HTTPException(400, "At least one of email or phone is required")

    # Check for duplicates in candidate_bank
    dup_query = []
    if email:
        dup_query.append({"email": {"$regex": f"^{email}$", "$options": "i"}})
    if phone:
        import re as re_mod
        digits = re_mod.sub(r'\D', '', phone)
        if len(digits) >= 10:
            dup_query.append({"phone_normalized": digits[-10:]})
    if dup_query:
        existing = await db.candidate_bank.find_one({"$or": dup_query}, {"id": 1, "name": 1, "email": 1})
        if existing:
            # Mark capture as recovered (already exists in bank)
            await db.naukri_capture_logs.update_one(
                {"id": capture_id},
                {"$set": {"is_recovered": True, "recovered_at": datetime.now(timezone.utc).isoformat(),
                           "recovered_by": current_user.get("id", ""), "recovery_method": "duplicate_found",
                           "linked_candidate_id": existing["id"]}}
            )
            return {"success": True, "message": f"Candidate already exists in bank: {existing.get('name')}", "candidate_id": existing["id"], "was_duplicate": True}

    now = datetime.now(timezone.utc).isoformat()
    candidate_id = str(uuid.uuid4())

    # Normalize phone
    phone_normalized = None
    if phone:
        import re as re_mod
        digits = re_mod.sub(r'\D', '', phone)
        phone_normalized = digits[-10:] if len(digits) >= 10 else digits

    doc = {
        "id": candidate_id,
        "name": name,
        "email": email,
        "phone": phone,
        "phone_normalized": phone_normalized,
        "headline": data.get("designation") or None,
        "current_employer": data.get("current_employer") or None,
        "designation": data.get("designation") or None,
        "location": data.get("location") or None,
        "skills": [s.strip() for s in (data.get("skills") or "").split(",") if s.strip()] if isinstance(data.get("skills"), str) else (data.get("skills") or []),
        "experience_years": float(data.get("experience_years") or 0),
        "industry": data.get("industry") or None,
        "source": "naukri_extension",
        "source_details": {
            "recovery_method": "manual_fix",
            "original_capture_id": capture_id,
            "profile_url": data.get("profile_url") or None,
            "recovered_by": current_user.get("id"),
            "recovered_at": now,
        },
        "summary": None,
        "experience": [],
        "education": [],
        "certifications": [],
        "resume_versions": [],
        "resume_fingerprints": [],
        "match_cache": [],
        "application_history": [],
        "profile_update_audit": [],
        "visibility": {},
        "created_by": current_user.get("id"),
        "created_at": now,
        "updated_at": now,
    }

    await db.candidate_bank.insert_one(doc)

    # Mark the capture log as recovered
    await db.naukri_capture_logs.update_one(
        {"id": capture_id},
        {"$set": {
            "is_recovered": True,
            "recovered_at": now,
            "recovered_by": current_user.get("id", ""),
            "recovery_method": "manual_save_to_bank",
            "linked_candidate_id": candidate_id,
        }}
    )

    # Log activity
    try:
        from services.activity_log_service import log_activity
        await log_activity(
            candidate_id=candidate_id,
            user_id=current_user.get("id", ""),
            user_name=current_user.get("name", current_user.get("email", "")),
            action="captured",
            details={"source": "failed_capture_recovery", "capture_id": capture_id},
        )
    except Exception:
        pass

    return {"success": True, "message": "Saved to candidate bank", "candidate_id": candidate_id, "was_duplicate": False}


@router.post("/failed-captures/bulk-dismiss")
async def bulk_dismiss_failed_captures(
    data: dict,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Bulk dismiss junk failed captures (mark as recovered/dismissed)."""
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "No capture IDs provided")

    now = datetime.now(timezone.utc).isoformat()
    result = await db.naukri_capture_logs.update_many(
        {"id": {"$in": ids}, "status": "failed"},
        {"$set": {
            "is_recovered": True,
            "recovered_at": now,
            "recovered_by": current_user.get("id", ""),
            "recovery_method": "bulk_dismissed",
        }}
    )
    return {"success": True, "dismissed": result.modified_count}


# ---------------------------------------------------------------------------
# Auto-Classification of Failed Captures
# ---------------------------------------------------------------------------

# Known junk patterns (UI elements, navigation text from Naukri)
_JUNK_NAMES = {
    "search candidates", "resdex", "filter by location", "application received",
    "showing 25 candidates", "showing 50 candidates", "page 1 of 10",
    "500 profiles found", "page 2 of 10", "page 3 of 10", "naukri",
    "home", "login", "dashboard", "settings", "profile", "logout",
    "back", "next", "previous", "close", "cancel", "save", "search",
    "filter", "sort", "apply", "clear", "reset", "loading", "error",
    "no results", "try again", "showing results", "results found",
}

import re as _re

def _classify_capture(capture: dict) -> dict:
    """Rule-based classification. Returns {label, confidence, reason}."""
    name = (capture.get("candidate_name") or "").strip()
    reason = (capture.get("failure_reason") or "").strip()
    email = (capture.get("candidate_email") or "").strip()
    phone = (capture.get("candidate_phone") or "").strip()
    url = (capture.get("profile_url") or "").strip()

    name_lower = name.lower()

    # Rule 1: Nav-text captures are always junk
    if "nav-text name:" in reason.lower():
        return {"label": "junk", "confidence": 0.98, "reason": "Navigation UI text captured instead of candidate name"}

    # Rule 2: Known junk names
    if name_lower in _JUNK_NAMES:
        return {"label": "junk", "confidence": 0.95, "reason": f"Known UI element: '{name}'"}

    # Rule 3: Name is a number or contains only numbers/symbols
    if _re.match(r'^[\d\s\.\,\#\-\(\)]+$', name):
        return {"label": "junk", "confidence": 0.95, "reason": "Name contains only numbers/symbols"}

    # Rule 4: Name contains common UI keywords
    ui_keywords = ["profiles found", "page ", "showing ", "filter by", "search ", "candidates",
                    "loading", "error", "no results", "results for"]
    if any(kw in name_lower for kw in ui_keywords):
        return {"label": "junk", "confidence": 0.90, "reason": "Name matches UI pattern"}

    # Rule 5: Name too short (single character or empty)
    if len(name) < 2:
        return {"label": "junk", "confidence": 0.95, "reason": "Name too short"}

    # Rule 6: Name is a single word and matches common UI terms
    single_word_junk = {"resdex", "naukri", "indeed", "linkedin", "glassdoor", "foundit",
                        "home", "back", "undefined", "null", "none", "n/a", "na", "test"}
    if name_lower in single_word_junk:
        return {"label": "junk", "confidence": 0.92, "reason": f"Single-word UI/platform term: '{name}'"}

    # Rule 7: Has a real Naukri profile URL + real-looking name = likely genuine
    has_real_url = "resdex.naukri.com" in url or "/v2/profile/" in url
    has_contact = bool(email) or bool(phone)
    name_parts = name.split()
    looks_like_name = len(name_parts) >= 2 and all(p[0].isupper() for p in name_parts if p)

    if has_real_url and looks_like_name:
        return {"label": "genuine", "confidence": 0.90, "reason": "Real profile URL + valid-looking name"}

    if has_real_url and has_contact:
        return {"label": "genuine", "confidence": 0.80, "reason": "Real profile URL + contact info"}

    # Rule 8: Name looks like a real name (2+ words, title case)
    if looks_like_name and len(name) > 4:
        return {"label": "genuine", "confidence": 0.75, "reason": "Name has proper name format"}

    # Ambiguous — needs review
    return {"label": "uncertain", "confidence": 0.50, "reason": "Could not determine — manual review needed"}


@router.post("/failed-captures/auto-classify")
async def auto_classify_failed_captures(
    data: dict = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Auto-classify unrecovered failed captures as junk or genuine.
    Optionally auto-dismiss junk captures if auto_dismiss=true."""
    if data is None:
        data = {}
    auto_dismiss = data.get("auto_dismiss", False)

    # Fetch all unrecovered captures
    captures = await db.naukri_capture_logs.find(
        {"status": "failed", "is_recovered": {"$ne": True}}, {"_id": 0}
    ).to_list(500)

    results = {"junk": [], "genuine": [], "uncertain": [], "total": len(captures)}

    for cap in captures:
        classification = _classify_capture(cap)
        entry = {
            "id": cap.get("id"),
            "name": cap.get("candidate_name", ""),
            "email": cap.get("candidate_email", ""),
            "profile_url": cap.get("profile_url", ""),
            "label": classification["label"],
            "confidence": classification["confidence"],
            "reason": classification["reason"],
        }
        results[classification["label"]].append(entry)

    results["junk_count"] = len(results["junk"])
    results["genuine_count"] = len(results["genuine"])
    results["uncertain_count"] = len(results["uncertain"])

    # Auto-dismiss junk if requested
    dismissed_count = 0
    if auto_dismiss and results["junk"]:
        junk_ids = [j["id"] for j in results["junk"]]
        now = datetime.now(timezone.utc).isoformat()
        result = await db.naukri_capture_logs.update_many(
            {"id": {"$in": junk_ids}, "status": "failed"},
            {"$set": {
                "is_recovered": True,
                "recovered_at": now,
                "recovered_by": current_user.get("id", ""),
                "recovery_method": "auto_classified_junk",
            }}
        )
        dismissed_count = result.modified_count

    results["auto_dismissed"] = dismissed_count
    return results


@router.get("/")
@router.get("")
async def list_candidates(
    page:      int   = Query(1, ge=1),
    limit:     int   = Query(20, ge=1, le=100),
    search:    Optional[str] = Query(None),
    boolean_search: Optional[str] = Query(None, description="Boolean search query: AND, OR, NOT, quotes, parentheses"),
    phone:     Optional[str] = Query(None),
    email:     Optional[str] = Query(None),
    location:  Optional[str] = Query(None),
    company:   Optional[str] = Query(None),
    skills:    Optional[str] = Query(None),
    notice_period: Optional[str] = Query(None),
    min_experience: Optional[int] = Query(None),
    max_experience: Optional[int] = Query(None),
    min_salary: Optional[int] = Query(None),
    max_salary: Optional[int] = Query(None),
    source:    Optional[str] = Query(None),
    has_resume: Optional[str] = Query(None),
    contact_hidden: Optional[str] = Query(None),
    captured_after:  Optional[str] = Query(None),
    captured_before: Optional[str] = Query(None),
    mandate_id: Optional[str] = Query(None, description="Filter by mandate/job ID (candidates captured under this mandate)"),
    ai_source: Optional[str] = Query(None, description="Filter by AI extraction source"),
    smart_tags: Optional[str] = Query(None, description="Filter by smart tags (comma-separated)"),
    designation: Optional[str] = Query(None, description="Filter by current designation"),
    industry: Optional[str] = Query(None, description="Filter by industry"),
    notice_period_max: Optional[int] = Query(None, description="Max notice period in days (e.g. 15, 30, 60, 90)"),
    education_level: Optional[str] = Query(None, description="UG, PG, or Doctorate"),
    gender: Optional[str] = Query(None, description="male, female, or all"),
    exclude_company: Optional[str] = Query(None, description="Exclude candidates from this company"),
    exclude_keywords: Optional[str] = Query(None, description="Exclude candidates matching these keywords"),
    has_phone: Optional[bool] = Query(None, description="Only candidates with phone number"),
    has_email: Optional[bool] = Query(None, description="Only candidates with email"),
    boolean_mode: Optional[bool] = Query(False, description="Enable AND/OR/NOT boolean keyword search"),
    cursor:    Optional[str] = Query(None, description="Cursor-based pagination"),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List candidates with advanced filters, boolean search, and cursor-based pagination.

    Supports two pagination modes:
    - **Offset** (default): use `page` + `limit` params. Simple but slow on deep pages.
    - **Cursor**: pass `cursor` (candidate id from previous response's `next_cursor`).
      O(1) performance regardless of page depth. When cursor is provided, `page` is ignored.
    """
    use_cursor = bool(cursor)
    skip  = 0 if use_cursor else (page - 1) * limit
    conditions = []

    # ── Cursor-based pagination filter ──
    if use_cursor:
        cursor_doc = await db.candidate_bank.find_one(
            {"id": cursor}, {"_id": 0, "created_at": 1}
        )
        if cursor_doc and cursor_doc.get("created_at"):
            # Fetch everything strictly before the cursor's created_at timestamp
            conditions.append({"created_at": {"$lt": cursor_doc["created_at"]}})
        else:
            return {"candidates": [], "total": 0, "page": 1, "limit": limit, "pages": 0, "next_cursor": None}

    # ── Boolean search (takes priority over simple search) ──
    if boolean_search:
        bool_filter = parse_boolean_query(boolean_search)
        if bool_filter:
            conditions.append(bool_filter)
    # ── Text search with synonym expansion ──
    elif search:
        import re
        from services.synonym_service import get_synonym_regex
        words = [w.strip() for w in search.split() if w.strip()]
        searchable_fields = [
            "name", "email", "phone", "key_skills", "skills",
            "current_designation", "designation", "headline",
            "current_company", "company", "location", "current_location",
        ]
        for word in words:
            # Expand word with synonyms for better recall
            pattern = get_synonym_regex(word)
            word_conditions = [
                {field: {"$regex": pattern, "$options": "i"}}
                for field in searchable_fields
            ]
            conditions.append({"$or": word_conditions})

    # ── Phone search ──
    if phone:
        import re
        clean = re.sub(r'[^0-9]', '', phone)
        if clean:
            conditions.append({"phone": {"$regex": clean, "$options": "i"}})

    # ── Email search ──
    if email:
        import re
        conditions.append({"email": {"$regex": re.escape(email), "$options": "i"}})

    # ── Location ──
    if location:
        import re
        conditions.append({"$or": [
            {"location":      {"$regex": re.escape(location), "$options": "i"}},
            {"current_location": {"$regex": re.escape(location), "$options": "i"}},
        ]})

    # ── Company ──
    if company:
        import re
        conditions.append({"$or": [
            {"current_company": {"$regex": re.escape(company), "$options": "i"}},
            {"company":         {"$regex": re.escape(company), "$options": "i"}},
        ]})

    # ── Skills (comma-separated) ──
    if skills:
        import re
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        skill_conditions = []
        for s in skill_list:
            pat = re.escape(s)
            skill_conditions.append({"$or": [
                {"skills":     {"$elemMatch": {"$regex": pat, "$options": "i"}}},
                {"key_skills": {"$regex": pat, "$options": "i"}},
            ]})
        if skill_conditions:
            conditions.append({"$and": skill_conditions})

    # ── Notice Period ──
    if notice_period:
        conditions.append({"notice_period": notice_period})

    # ── Experience Range ──
    if min_experience is not None or max_experience is not None:
        exp_filter = {}
        if min_experience is not None:
            exp_filter["$gte"] = min_experience
        if max_experience is not None:
            exp_filter["$lte"] = max_experience
        conditions.append({"experience_years": exp_filter})

    # ── Salary Range ──
    if min_salary is not None or max_salary is not None:
        sal_filter = {}
        if min_salary is not None:
            sal_filter["$gte"] = min_salary
        if max_salary is not None:
            sal_filter["$lte"] = max_salary
        conditions.append({"current_salary": sal_filter})

    # ── Source ──
    # Frontend sends short labels ("extension", "manual", "bulk") but the
    # DB stores full source tags like "naukri_extension", "naukri_excel_import",
    # "manual_upload", "csv_bulk". Use substring match so dropdown selections
    # actually return results (Phase 52 fix, 2026-05-06).
    if source:
        import re
        conditions.append({"source": {"$regex": re.escape(source), "$options": "i"}})

    # ── AI Extraction Source (admin only) ──
    if ai_source:
        conditions.append({"ai_enrichment_source": {"$regex": ai_source, "$options": "i"}})

    # ── Smart Tags Filter ──
    if smart_tags:
        tag_list = [t.strip() for t in smart_tags.split(",") if t.strip()]
        if tag_list:
            conditions.append({"smart_tags": {"$all": tag_list}})


    # ── Designation Filter ──
    if designation:
        conditions.append({"$or": [
            {"designation": {"$regex": designation, "$options": "i"}},
            {"headline": {"$regex": designation, "$options": "i"}},
            {"current_designation": {"$regex": designation, "$options": "i"}},
        ]})

    # ── Industry Filter ──
    if industry:
        conditions.append({"$or": [
            {"industry": {"$regex": industry, "$options": "i"}},
            {"current_industry": {"$regex": industry, "$options": "i"}},
        ]})

    # ── Notice Period Max (days) ──
    if notice_period_max is not None:
        if notice_period_max == 0:
            conditions.append({"$or": [
                {"notice_period_days": 0},
                {"notice_period": {"$regex": "immediate", "$options": "i"}},
            ]})
        else:
            conditions.append({"$or": [
                {"notice_period_days": {"$lte": notice_period_max}},
                {"notice_period": {"$regex": "immediate", "$options": "i"}},
            ]})

    # ── Education Level ──
    if education_level:
        if education_level.upper() == "UG":
            conditions.append({"education.degree": {"$regex": "b\\.?tech|b\\.?e\\.?|b\\.?sc|bca|b\\.?com|bba|bachelor|diploma", "$options": "i"}})
        elif education_level.upper() == "PG":
            conditions.append({"education.degree": {"$regex": "m\\.?tech|m\\.?e\\.?|mba|mca|m\\.?sc|m\\.?com|pgdm|master", "$options": "i"}})
        elif education_level.upper() == "DOCTORATE":
            conditions.append({"education.degree": {"$regex": "ph\\.?d|doctorate", "$options": "i"}})

    # ── Gender Filter ──
    if gender and gender.lower() != "all":
        conditions.append({"gender": {"$regex": f"^{gender}$", "$options": "i"}})

    # ── Exclude Company ──
    if exclude_company:
        conditions.append({"current_employer": {"$not": {"$regex": exclude_company, "$options": "i"}}})

    # ── Exclude Keywords ──
    if exclude_keywords:
        excl_list = [k.strip() for k in exclude_keywords.split(",") if k.strip()]
        for excl in excl_list:
            conditions.append({"$nor": [
                {"skills": {"$regex": excl, "$options": "i"}},
                {"designation": {"$regex": excl, "$options": "i"}},
                {"summary": {"$regex": excl, "$options": "i"}},
            ]})

    # ── Has Phone / Has Email ──
    if has_phone:
        conditions.append({"phone": {"$exists": True, "$nin": [None, "", "hidden"]}})
    if has_email:
        conditions.append({"email": {"$exists": True, "$nin": [None, ""]}})



    # ── Has Resume ──
    # FIX (Phase 52, 2026-05-06): "no" branch must treat MISSING fields as
    # equivalent to null — most candidate_bank docs don't have all three keys
    # at all (resume_path/resume_latex are added later when LaTeX is built),
    # so `$in: [None, ""]` would NOT match a missing key and the filter
    # silently returned 0 results.
    if has_resume == "yes":
        conditions.append({"$or": [
            {"resume_url":   {"$exists": True, "$nin": [None, ""]}},
            {"resume_path":  {"$exists": True, "$nin": [None, ""]}},
            {"resume_latex": {"$exists": True, "$nin": [None, ""]}},
        ]})
    elif has_resume == "no":
        def _empty(field):
            return {"$or": [
                {field: {"$exists": False}},
                {field: {"$in": [None, ""]}},
            ]}
        conditions.append({"$and": [
            _empty("resume_url"),
            _empty("resume_path"),
            _empty("resume_latex"),
        ]})

    # ── Contact Hidden (from Naukri — phone/email is null/missing/placeholder) ──
    # FIX (Phase 52): include missing keys + Naukri "hidden" placeholder as
    # equivalent to null. Without this, captures where Naukri masks the
    # contact info (most non-paid views) were incorrectly returned as
    # "visible".
    if contact_hidden == "yes":
        def _missing_or_blank(field):
            return {"$or": [
                {field: {"$exists": False}},
                {field: {"$in": [None, "", "hidden", "Not Available", "N/A"]}},
            ]}
        conditions.append({"$or": [
            _missing_or_blank("email"),
            _missing_or_blank("phone"),
        ]})
    elif contact_hidden == "no":
        conditions.append({
            "email": {"$exists": True, "$nin": [None, "", "hidden", "Not Available", "N/A"]},
            "phone": {"$exists": True, "$nin": [None, "", "hidden", "Not Available", "N/A"]},
        })

    # ── Capture Date Range ──
    # FIX (Phase 52, 2026-05-06): when user types a date-only value
    # (YYYY-MM-DD), the lex string-compare against ISO timestamps would
    # exclude same-day captures from `captured_before` (because
    # "2026-05-15T14:00..." > "2026-05-15"). Append the EOD suffix so the
    # bound is inclusive of the entire selected day.
    if captured_after:
        _after = captured_after if "T" in captured_after else f"{captured_after}T00:00:00"
        conditions.append({"$or": [
            {"created_at": {"$gte": _after}},
            {"scraped_at": {"$gte": _after}},
        ]})
    if captured_before:
        _before = captured_before if "T" in captured_before else f"{captured_before}T23:59:59.999999"
        conditions.append({"$or": [
            {"created_at": {"$lte": _before}},
            {"scraped_at": {"$lte": _before}},
        ]})

    # ── Mandate ID (candidates captured under a specific mandate) ──
    # FIX (Phase 52, 2026-05-06): the extension stores mandate links in the
    # `linked_mandates` array (see extension.py:2318), not as a scalar
    # `mandate_id`. This filter previously matched 0 results because the
    # field lookups used the wrong field names.
    if mandate_id:
        conditions.append({"$or": [
            {"linked_mandates": mandate_id},
            {"mandate_id": mandate_id},
            {"source_details.mandate_id": mandate_id},
        ]})

    query = {"$and": conditions} if conditions else {}

    total = await db.candidate_bank.count_documents(query)

    if use_cursor:
        # Cursor mode: no skip, just filter + limit (uses created_at index)
        docs = (
            await db.candidate_bank.find(query, {"_id": 0, "embedding": 0}, allow_disk_use=True)
            .limit(limit)
            .sort("created_at", -1)
            .to_list(limit)
        )
    else:
        # Offset mode: traditional skip/limit
        docs = (
            await db.candidate_bank.find(query, {"_id": 0, "embedding": 0}, allow_disk_use=True)
            .skip(skip)
            .limit(limit)
            .sort("created_at", -1)
            .to_list(limit)
        )

    # Compute next_cursor from last document
    next_cursor = docs[-1]["id"] if docs else None

    return {
        "candidates": docs,
        "total":      total,
        "page":       page,
        "limit":      limit,
        "pages":      (total + limit - 1) // limit,
        "next_cursor": next_cursor,
    }


# ---------------------------------------------------------------------------
# Duplicate Detection
# ---------------------------------------------------------------------------

@router.post("/match-from-index")
async def match_from_index(
    payload: dict,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Bulk match candidates from Naukri search index against the candidate bank.
    Matches using name + company + designation (no email/phone needed).
    Returns match status for each candidate so the extension can show badges.
    """
    import re as _re

    candidates_to_check = payload.get("candidates", [])
    if not candidates_to_check:
        raise HTTPException(status_code=400, detail="Provide a list of candidates to match")

    results = []

    for entry in candidates_to_check[:50]:  # Limit to 50 per request
        name = (entry.get("name") or "").strip()
        company = (entry.get("company") or "").strip()
        designation = (entry.get("designation") or "").strip()
        location = (entry.get("location") or "").strip()
        idx = entry.get("index", 0)  # position in search results

        if not name:
            results.append({"index": idx, "match": "none", "confidence": 0})
            continue

        # Build match queries in order of confidence
        name_parts = name.lower().split()
        name_regex = ".*".join([_re.escape(p) for p in name_parts])

        # Tier 1: Name + Company (high confidence)
        tier1_match = None
        if company:
            clean_company = _re.escape(company.split("(")[0].strip())  # Remove parenthetical
            tier1 = await db.candidate_bank.find_one(
                {"$and": [
                    {"name": {"$regex": name_regex, "$options": "i"}},
                    {"$or": [
                        {"current_company": {"$regex": clean_company, "$options": "i"}},
                        {"company": {"$regex": clean_company, "$options": "i"}},
                    ]},
                ]},
                {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
                 "current_company": 1, "current_designation": 1, "source": 1}
            )
            if tier1:
                tier1_match = tier1

        # Tier 2: Name + Designation + Location (medium confidence)
        tier2_match = None
        if not tier1_match and designation and location:
            clean_desig = _re.escape(designation.split("-")[0].strip())
            clean_loc = _re.escape(location.split(",")[0].strip())
            tier2 = await db.candidate_bank.find_one(
                {"$and": [
                    {"name": {"$regex": name_regex, "$options": "i"}},
                    {"$or": [
                        {"current_designation": {"$regex": clean_desig, "$options": "i"}},
                        {"designation": {"$regex": clean_desig, "$options": "i"}},
                        {"headline": {"$regex": clean_desig, "$options": "i"}},
                    ]},
                    {"$or": [
                        {"current_location": {"$regex": clean_loc, "$options": "i"}},
                        {"location": {"$regex": clean_loc, "$options": "i"}},
                    ]},
                ]},
                {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
                 "current_company": 1, "current_designation": 1, "source": 1}
            )
            if tier2:
                tier2_match = tier2

        # Tier 3: Name + Company keyword (lower confidence)
        tier3_match = None
        if not tier1_match and not tier2_match and company:
            # Try just first significant company word
            company_words = [w for w in company.split() if len(w) > 2 and w.lower() not in ("pvt", "ltd", "private", "limited", "inc", "llp", "india")]
            if company_words:
                tier3 = await db.candidate_bank.find_one(
                    {"$and": [
                        {"name": {"$regex": name_regex, "$options": "i"}},
                        {"$or": [
                            {"current_company": {"$regex": _re.escape(company_words[0]), "$options": "i"}},
                            {"company": {"$regex": _re.escape(company_words[0]), "$options": "i"}},
                        ]},
                    ]},
                    {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
                     "current_company": 1, "current_designation": 1, "source": 1}
                )
                if tier3:
                    tier3_match = tier3

        if tier1_match:
            results.append({
                "index": idx,
                "match": "high",
                "confidence": 95,
                "candidate_id": tier1_match.get("id"),
                "db_name": tier1_match.get("name"),
                "db_company": tier1_match.get("current_company"),
                "has_email": bool(tier1_match.get("email")),
                "has_phone": bool(tier1_match.get("phone")),
            })
        elif tier2_match:
            results.append({
                "index": idx,
                "match": "medium",
                "confidence": 70,
                "candidate_id": tier2_match.get("id"),
                "db_name": tier2_match.get("name"),
                "db_company": tier2_match.get("current_company"),
                "has_email": bool(tier2_match.get("email")),
                "has_phone": bool(tier2_match.get("phone")),
            })
        elif tier3_match:
            results.append({
                "index": idx,
                "match": "low",
                "confidence": 50,
                "candidate_id": tier3_match.get("id"),
                "db_name": tier3_match.get("name"),
                "db_company": tier3_match.get("current_company"),
                "has_email": bool(tier3_match.get("email")),
                "has_phone": bool(tier3_match.get("phone")),
            })
        else:
            results.append({"index": idx, "match": "none", "confidence": 0})

    matched = sum(1 for r in results if r["match"] != "none")
    return {
        "results": results,
        "total_checked": len(results),
        "total_matched": matched,
    }


@router.post("/check-duplicates")
async def check_duplicates(
    payload: dict,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Check for duplicate candidates by email and/or phone.
    Returns matching candidates if any.
    """
    import re as _re

    email = (payload.get("email") or "").strip().lower()
    phone = (payload.get("phone") or "").strip()
    name  = (payload.get("name") or "").strip()

    if not email and not phone and not name:
        raise HTTPException(status_code=400, detail="Provide email, phone, or name to check")

    conditions = []

    # Exact email match (case-insensitive)
    if email:
        conditions.append({"email": {"$regex": f"^{_re.escape(email)}$", "$options": "i"}})

    # Phone match (normalized, last 10 digits)
    if phone:
        clean_phone = _re.sub(r'[^0-9]', '', phone)
        if len(clean_phone) >= 10:
            last10 = clean_phone[-10:]
            conditions.append({"$or": [
                {"phone": {"$regex": last10}},
                {"phone_normalized": last10},
            ]})
        elif clean_phone:
            conditions.append({"phone": {"$regex": _re.escape(clean_phone)}})

    # Fuzzy name match (optional additional signal)
    if name and len(name) >= 3:
        conditions.append({"name": {"$regex": _re.escape(name), "$options": "i"}})

    if not conditions:
        return {"duplicates": [], "has_duplicates": False}

    # Search for each condition separately to get match type
    results = []
    seen_ids = set()

    for cond in conditions:
        docs = await db.candidate_bank.find(
            cond, {"_id": 0, "embedding": 0, "resume_latex": 0}
        ).limit(10).to_list(10)
        for doc in docs:
            cid = doc.get("id", "")
            if cid not in seen_ids:
                seen_ids.add(cid)
                # Determine match type
                match_reasons = []
                doc_email = (doc.get("email") or "").lower()
                doc_phone = _re.sub(r'[^0-9]', '', doc.get("phone") or "")
                if email and doc_email == email:
                    match_reasons.append("email")
                if phone and clean_phone and doc_phone.endswith(clean_phone[-10:]):
                    match_reasons.append("phone")
                if name and name.lower() in (doc.get("name") or "").lower():
                    match_reasons.append("name")
                doc["match_reasons"] = match_reasons or ["partial"]
                results.append(doc)

    return {
        "duplicates": results[:20],
        "has_duplicates": len(results) > 0,
        "total": len(results),
    }


@router.get("/find-all-duplicates")
async def find_all_duplicates(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Scan the candidate bank and return groups of duplicate candidates.
    Two-step approach to avoid MongoDB memory limits on shared tier:
    Step 1: Find duplicate keys (email/phone) with counts only
    Step 2: Fetch candidate details for those duplicate keys
    """
    # Step 1: Find duplicate emails (lightweight - no $push)
    email_keys_pipeline = [
        {"$match": {"email": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {
            "_id": {"$toLower": "$email"},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 50},
    ]
    email_keys = await db.candidate_bank.aggregate(email_keys_pipeline).to_list(50)

    # Step 2: Fetch candidates for duplicate emails
    email_dupes = []
    for ek in email_keys:
        dup_email = ek["_id"]
        candidates = await db.candidate_bank.find(
            {"email": {"$regex": f"^{dup_email}$", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "source": 1, "created_at": 1}
        ).to_list(20)
        email_dupes.append({
            "_id": dup_email,
            "count": ek["count"],
            "candidates": candidates,
        })

    # Step 1b: Find duplicate phones (lightweight)
    phone_keys_pipeline = [
        {"$match": {"phone_normalized": {"$exists": True, "$nin": [None, "", "0000000000"], "$regex": "^[0-9]{10}$"}}},
        {"$group": {
            "_id": "$phone_normalized",
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 50},
    ]
    phone_keys = await db.candidate_bank.aggregate(phone_keys_pipeline).to_list(50)

    # Step 2b: Fetch candidates for duplicate phones
    phone_dupes = []
    for pk in phone_keys:
        dup_phone = pk["_id"]
        candidates = await db.candidate_bank.find(
            {"phone_normalized": dup_phone},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "source": 1, "created_at": 1}
        ).to_list(20)
        phone_dupes.append({
            "_id": dup_phone,
            "count": pk["count"],
            "candidates": candidates,
        })

    return {
        "email_duplicates": email_dupes,
        "phone_duplicates": phone_dupes,
        "total_email_groups": len(email_dupes),
        "total_phone_groups": len(phone_dupes),
    }


@router.post("/merge-duplicates")
async def merge_duplicates(
    payload: dict,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Merge a group of duplicate candidates into one master record.

    SEC-05 (Feb 2026): every donor must match the master on at least
    2 of (name_similar, email_exact, phone_normalized_exact). This
    prevents bulk-merging two different people who happen to share a
    phone or email (e.g. spouse sharing a number).
    Donors that fail the gate are returned in `skipped` for manual review.
    """
    from services.extension_service import _names_are_similar
    from services.candidate_merge import normalize_phone

    candidate_ids = payload.get("candidate_ids", [])
    if len(candidate_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 candidate IDs to merge")

    docs = []
    for cid in candidate_ids:
        doc = await db.candidate_bank.find_one({"id": cid})
        if doc:
            docs.append(doc)

    if len(docs) < 2:
        raise HTTPException(status_code=404, detail="Could not find enough candidates to merge")

    def completeness_score(d):
        score = 0
        for k, v in d.items():
            if k.startswith("_") or k in ("id", "created_at", "updated_at"):
                continue
            if v and v != "" and v != [] and v != {}:
                score += 1
        return score

    docs.sort(key=lambda d: (
        d.get("updated_at") or d.get("created_at") or "",
        completeness_score(d),
    ), reverse=True)

    master = docs[0]
    master_id = master["id"]
    SKIP_FIELDS = {"_id", "id", "created_at"}

    def _match_score(a: dict, b: dict) -> int:
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

    actual_donors = []
    skipped = []
    for donor in docs[1:]:
        s = _match_score(master, donor)
        if s >= 2:
            actual_donors.append(donor)
        else:
            skipped.append({
                "id": donor["id"],
                "name": donor.get("name"),
                "match_score": s,
                "reason": "needs 2-of-3 match (name+email+phone); flagged for manual review",
            })

    if not actual_donors:
        return {
            "master_id": master_id,
            "merged_count": 0,
            "merged_ids": [],
            "skipped": skipped,
            "message": "No donors passed the 2-of-3 match gate — nothing merged.",
        }

    for donor in actual_donors:
        for key, value in donor.items():
            if key in SKIP_FIELDS:
                continue
            master_val = master.get(key)
            if not master_val and value:
                master[key] = value
            elif isinstance(master_val, list) and isinstance(value, list):
                combined = list(master_val)
                existing = set(str(x) for x in combined)
                for item in value:
                    if str(item) not in existing:
                        combined.append(item)
                        existing.add(str(item))
                master[key] = combined
            elif key in ("key_skills", "skills") and isinstance(master_val, str) and isinstance(value, str):
                existing_skills = set(s.strip().lower() for s in master_val.split(",") if s.strip())
                new_skills = [s.strip() for s in value.split(",") if s.strip() and s.strip().lower() not in existing_skills]
                if new_skills:
                    master[key] = master_val + ", " + ", ".join(new_skills)

    from datetime import datetime, timezone
    master["updated_at"] = datetime.now(timezone.utc).isoformat()
    master["merge_history"] = master.get("merge_history", [])
    master["merge_history"].append({
        "merged_ids": [d["id"] for d in actual_donors],
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "merged_by": current_user.get("email", "unknown"),
        "skipped": skipped or None,
    })

    update_doc = {k: v for k, v in master.items() if k != "_id"}
    await db.candidate_bank.replace_one({"id": master_id}, update_doc)

    duplicate_ids = [d["id"] for d in actual_donors]
    delete_result = await db.candidate_bank.delete_many({"id": {"$in": duplicate_ids}})

    await db.applications.update_many(
        {"candidate_id": {"$in": duplicate_ids}},
        {"$set": {"candidate_id": master_id}},
    )

    return {
        "master_id": master_id,
        "merged_count": delete_result.deleted_count,
        "merged_ids": duplicate_ids,
        "skipped": skipped,
        "message": f"Merged {len(actual_donors) + 1} candidates into {master.get('name', master_id)}"
                   + (f"; {len(skipped)} donor(s) skipped (low match score)" if skipped else ""),
    }



@router.get("/autocomplete")
async def autocomplete_suggestions(
    q: str = Query(..., min_length=2, description="Search prefix"),
    field: str = Query("all", description="Field to search: skills, designation, company, location, all"),
    limit: int = Query(10, le=20),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Predictive autocomplete suggestions based on existing candidate data."""
    from services.synonym_service import expand_query

    q_lower = q.lower().strip()
    regex_pattern = f"^{q_lower}"
    suggestions = []

    field_map = {
        "skills": {"field": "skills", "unwind": True},
        "designation": {"field": "designation", "unwind": False},
        "company": {"field": "current_employer", "unwind": False},
        "location": {"field": "location", "unwind": False},
        "smart_tags": {"field": "smart_tags", "unwind": True},
    }

    fields_to_search = field_map.keys() if field == "all" else [field] if field in field_map else ["skills"]

    for f_key in fields_to_search:
        f_config = field_map[f_key]
        f_name = f_config["field"]

        pipeline = []
        if f_config["unwind"]:
            pipeline.append({"$unwind": f"${f_name}"})

        pipeline.extend([
            {"$match": {f_name: {"$regex": regex_pattern, "$options": "i"}}},
            {"$group": {"_id": f"${f_name}", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$ne": None}}},
            {"$sort": {"count": -1}},
            {"$limit": limit},
        ])

        results = await db.candidate_bank.aggregate(pipeline).to_list(limit)
        for r in results:
            if r["_id"]:
                suggestions.append({
                    "text": r["_id"],
                    "count": r["count"],
                    "type": f_key,
                })

    # Deduplicate and sort by count
    seen = set()
    unique = []
    for s in sorted(suggestions, key=lambda x: x["count"], reverse=True):
        if s["text"].lower() not in seen:
            seen.add(s["text"].lower())
            unique.append(s)

    # Also expand with synonyms
    expanded = expand_query(q_lower)
    synonym_suggestions = [{"text": t, "count": 0, "type": "synonym"} for t in expanded if t.lower() != q_lower and t.lower() not in seen]

    return (unique + synonym_suggestions[:5])[:limit]



# ═══════════════════════════════════════
# CANDIDATE NOTES / COMMENTS
# ═══════════════════════════════════════

class NoteCreate(BaseModel):
    text: str

@router.get("/notes/{candidate_id}")
async def get_candidate_notes(
    candidate_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all notes/comments for a candidate, sorted newest first."""
    notes = await db.candidate_notes.find(
        {"candidate_id": candidate_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return notes


@router.post("/notes/{candidate_id}")
async def add_candidate_note(
    candidate_id: str,
    note: NoteCreate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Add a timestamped note/comment to a candidate profile."""
    if not note.text.strip():
        raise HTTPException(status_code=400, detail="Note text cannot be empty")

    # Verify candidate exists
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0, "id": 1, "name": 1})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    note_doc = {
        "id": str(uuid.uuid4()),
        "candidate_id": candidate_id,
        "text": note.text.strip(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", current_user.get("email", "Unknown")),
        "created_by_role": current_user.get("role", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.candidate_notes.insert_one(note_doc)
    note_doc.pop("_id", None)

    return note_doc


@router.delete("/notes/{candidate_id}/{note_id}")
async def delete_candidate_note(
    candidate_id: str,
    note_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a note. Only the author or admin can delete."""
    note = await db.candidate_notes.find_one({"id": note_id, "candidate_id": candidate_id})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if note.get("created_by") != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="You can only delete your own notes")

    await db.candidate_notes.delete_one({"id": note_id})
    return {"message": "Note deleted"}



@router.get("/{candidate_id}")
async def get_candidate(
    candidate_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get candidate by ID."""
    doc = await db.candidate_bank.find_one(
        {"id": candidate_id}, {"_id": 0, "embedding": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Log profile view activity (fire-and-forget)
    from services.activity_log_service import log_activity, ACTION_VIEWED
    await log_activity(
        candidate_id=candidate_id, action=ACTION_VIEWED,
        description="Profile viewed",
        performed_by=current_user.get("id"), performed_by_name=current_user.get("name"),
        performed_by_role=current_user.get("role"),
        candidate_name=doc.get("name"),
    )
    
    return doc


# ---------------------------------------------------------------------------
# Update candidate
# ---------------------------------------------------------------------------

@router.patch("/{candidate_id}")
async def update_candidate(
    candidate_id: str,
    updates: dict,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Partial update of a candidate record.
    Normalizes fields before writing to maintain schema invariant.
    """
    existing = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Merge then normalize to maintain dual-write invariant
    merged    = {**existing, **updates}
    normalized = normalize_candidate(merged)
    normalized["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$set": normalized},
    )

    # Invalidate caches
    cache.invalidate_search_cache()
    try:
        from services.cache import cache as _cache
        _cache.delete(f"emb_cand:{candidate_id}")
        _cache.delete(f"emb_text:{candidate_id}")
    except Exception:
        pass

    # Log profile edit activity
    from services.activity_log_service import log_activity, ACTION_PROFILE_EDITED
    changed_fields = list(updates.keys())[:10]
    await log_activity(
        candidate_id=candidate_id, action=ACTION_PROFILE_EDITED,
        description=f"Profile edited: {', '.join(changed_fields)}",
        performed_by=current_user.get("id"), performed_by_name=current_user.get("name"),
        performed_by_role=current_user.get("role"),
        candidate_name=existing.get("name"),
        details={"fields_changed": changed_fields},
    )

    return {"success": True, "candidate_id": candidate_id}



# ---------------------------------------------------------------------------
# Update mandatory fields (salary, notice period, location, experience)
# ---------------------------------------------------------------------------

@router.put("/{candidate_id}/salary-notice")
async def update_salary_notice(
    candidate_id: str,
    current_salary: Optional[int] = Query(None),
    notice_period: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    experience_years: Optional[int] = Query(None),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update mandatory candidate fields: salary, notice period, location, experience."""
    existing = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Candidate not found")

    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if current_salary is not None:
        updates["current_salary"] = current_salary
    if notice_period is not None:
        updates["notice_period"] = notice_period
    if location is not None:
        updates["location"] = location
    if experience_years is not None:
        updates["experience_years"] = experience_years

    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$set": updates},
    )

    cache.invalidate_search_cache()
    return {"success": True, "candidate_id": candidate_id}



# ---------------------------------------------------------------------------
# Delete candidate
# ---------------------------------------------------------------------------

@router.delete("/{candidate_id}")
async def delete_candidate(
    candidate_id: str,
    db=Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Delete a candidate record (Admin only)."""
    result = await db.candidate_bank.delete_one({"id": candidate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Candidate not found")

    cache.invalidate_search_cache()
    return {"success": True, "candidate_id": candidate_id}


# ---------------------------------------------------------------------------
# Re-parse a candidate's resume
# ---------------------------------------------------------------------------

@router.post("/{candidate_id}/reparse")
async def reparse_candidate(
    candidate_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Re-run AI parsing on an existing candidate's stored resume text."""
    doc = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Candidate not found")

    raw_text = doc.get("raw_resume_text") or doc.get("raw_profile_text")
    if not raw_text:
        raise HTTPException(
            status_code=422,
            detail="No raw resume text stored for this candidate.",
        )

    # Parse with AI
    parse_result = await parse_resume_with_ai(raw_text[:8000])
    if not parse_result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Re-parse failed: {parse_result.get('error')}",
        )

    new_data = parse_result["data"]
    new_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    new_data["reparsed_at"] = new_data["updated_at"]

    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$set": new_data},
    )

    cache.invalidate_search_cache()
    try:
        await process_candidate_embedding(candidate_id, new_data, db)
    except Exception as e:
        logger.warning(f"Embedding refresh failed for {candidate_id}: {e}")

    return {
        "success":      True,
        "candidate_id": candidate_id,
        "skills_count": len(get_skills(new_data)),
    }


# ---------------------------------------------------------------------------
# Candidate History / Audit Log endpoints
# ---------------------------------------------------------------------------

@router.get("/{candidate_id}/audit-log")
async def get_candidate_audit_log(candidate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Get audit log for a candidate (changes, updates, actions)."""
    logs = await db.audit_logs.find(
        {"entity_id": candidate_id, "entity_type": {"$in": ["candidate", "candidate_bank"]}},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    return logs


@router.get("/{candidate_id}/history")
async def get_candidate_history(candidate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Get activity history for a candidate."""
    # Combine audit logs and application activity
    logs = await db.audit_logs.find(
        {"entity_id": candidate_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    return logs


@router.get("/{candidate_id}/resume-history")
async def get_candidate_resume_history(candidate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Get resume upload/parse history for a candidate."""
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    history = []
    if candidate.get("created_at"):
        history.append({
            "action": "profile_created",
            "source": candidate.get("source", "unknown"),
            "timestamp": candidate.get("created_at"),
        })
    if candidate.get("reparsed_at"):
        history.append({
            "action": "resume_reparsed",
            "timestamp": candidate.get("reparsed_at"),
        })
    if candidate.get("resume_latex"):
        history.append({
            "action": "latex_resume_generated",
            "template": candidate.get("resume_template", "ats_clean"),
            "timestamp": candidate.get("updated_at"),
        })
    return history



# ---------------------------------------------------------------------------
# Download Resume (original uploaded CV)
# ---------------------------------------------------------------------------

@router.get("/{candidate_id}/download-resume")
async def download_resume(
    candidate_id: str,
    token: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """Download the original uploaded resume for a candidate.
    Supports ?token= query param for new-tab downloads."""
    import jwt as _jwt
    from config import JWT_SECRET_KEY, JWT_ALGORITHM
    from fastapi.responses import FileResponse, Response

    raw_token = token
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated. Pass ?token= for new-tab downloads.")

    try:
        payload = _jwt.decode(raw_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except (_jwt.ExpiredSignatureError, _jwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # ── Modern path: resume_versions[] populated by /admin/bulk-import/attach-cv ──
    # Resolve the active resume version → R2 presigned URL (or local file).
    active_id = candidate.get("active_resume_id")
    versions = candidate.get("resume_versions") or []
    active_version = None
    if active_id:
        active_version = next((v for v in versions if v.get("id") == active_id), None)
    if not active_version and versions:
        # Fallback: pick the last uploaded (most recent)
        active_version = versions[-1]

    if active_version:
        r2_meta = active_version.get("r2_metadata") or {}
        original_filename = active_version.get("original_filename") or r2_meta.get("filename") or "resume"

        # R2 stored → generate presigned URL and redirect
        if r2_meta.get("storage") == "r2" and r2_meta.get("r2_key"):
            from services.r2_storage import get_r2_signed_url
            from fastapi.responses import RedirectResponse
            signed = get_r2_signed_url(r2_meta["r2_key"], expires_in=600, download_filename=original_filename)
            if signed:
                return RedirectResponse(url=signed)
            raise HTTPException(status_code=502, detail="Failed to generate download URL from R2")

        # Local fallback → serve directly
        local_path = r2_meta.get("local_path")
        if local_path and os.path.exists(local_path):
            return FileResponse(local_path, filename=original_filename)

        raise HTTPException(status_code=404, detail="Resume file record exists but underlying storage is unreachable")

    # ── Legacy path: resume_path / resume_url fields ──
    resume_path = candidate.get("resume_path") or candidate.get("resume_url")
    if not resume_path:
        raise HTTPException(status_code=404, detail="No resume file available for this candidate")

    # If it's a local file path
    if os.path.exists(resume_path):
        return FileResponse(resume_path, filename=os.path.basename(resume_path))

    # If it's a URL (R2 or external), redirect
    if resume_path.startswith("http"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=resume_path)

    raise HTTPException(status_code=404, detail="Resume file not found on disk")



# ---------------------------------------------------------------------------
# ATS CV — Generate LaTeX resume using Resume Builder engine
# ---------------------------------------------------------------------------

@router.get("/{candidate_id}/ats-cv")
async def get_ats_cv(
    candidate_id: str,
    token: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """Generate or return a LaTeX resume for a candidate using the Resume Builder engine.
    Supports both Authorization header and ?token= query param for new-tab downloads."""
    from fastapi import Request
    from utils.auth import get_current_user_from_token

    # Auth: accept token from header or query param
    from starlette.requests import Request as _Req
    if not token:
        # Fall back to standard auth
        from utils.auth import get_current_user as _std_auth
        # This will be handled below via manual token extraction
        pass

    # Manual token resolution for new-tab downloads
    import jwt as _jwt
    from config import JWT_SECRET_KEY, JWT_ALGORITHM
    raw_token = token
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated. Pass ?token= for new-tab downloads.")

    try:
        payload = _jwt.decode(raw_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except _jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    from routes.resume import build_latex, _format_bank_profile_for_resume

    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Always regenerate fresh LaTeX to ensure it compiles cleanly
    profile = _format_bank_profile_for_resume(candidate)
    latex = build_latex(profile, "ats_clean")

    # Update stored copy
    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$set": {"resume_latex": latex, "resume_template": "ats_clean"}}
    )

    return _latex_download_response(latex, candidate.get("name", "Candidate"), profile=profile)


@router.post("/batch-generate-resumes")
async def batch_generate_resumes(
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Regenerate LaTeX resumes for ALL candidates in the bank (background). Admin only."""
    if user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin only")

    async def _run_batch():
        from routes.resume import build_latex, _format_bank_profile_for_resume
        from config import db as _db
        cursor = _db.candidate_bank.find({}, {"_id": 0})
        updated = errors = 0
        async for candidate in cursor:
            try:
                profile = _format_bank_profile_for_resume(candidate)
                latex = build_latex(profile, "ats_clean")
                await _db.candidate_bank.update_one(
                    {"id": candidate["id"]},
                    {"$set": {"resume_latex": latex, "resume_template": "ats_clean"}}
                )
                updated += 1
            except Exception as e:
                logger.warning(f"Batch resume gen failed for {candidate.get('id')}: {e}")
                errors += 1
        logger.info(f"[Batch Resume Gen] Done: {updated} updated, {errors} errors")

    import asyncio
    asyncio.create_task(_run_batch())
    return {"status": "started", "message": "Batch resume generation started in background for all candidates"}


def _latex_download_response(latex: str, name: str, profile: dict = None):
    """Generate a PDF resume and return as download.
    Uses pure-Python fpdf2 (no system deps), with pdflatex as optional bonus.
    Falls back to .tex if all else fails."""
    import re
    from fastapi.responses import Response

    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name.strip()) if name else "Candidate"

    # Method 1: Pure Python PDF generation (works everywhere)
    if profile:
        try:
            from services.pdf_generator import build_pdf_from_profile
            pdf_bytes = build_pdf_from_profile(profile)
            if pdf_bytes and len(pdf_bytes) > 100:
                return Response(
                    content=bytes(pdf_bytes),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{clean_name}_Resume_VHC.pdf"'},
                )
        except Exception as e:
            logger.warning(f"fpdf2 PDF generation failed for {name}: {e}")

    # Method 2: pdflatex compilation (if available on server)
    import shutil
    if shutil.which("pdflatex"):
        import tempfile
        import subprocess
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "resume.tex")
            with open(tex_path, "w") as f:
                f.write(latex)
            try:
                subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
                    cwd=tmpdir, capture_output=True, text=True, timeout=30,
                )
                pdf_path = os.path.join(tmpdir, "resume.pdf")
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as pf:
                        pdf_bytes = pf.read()
                    return Response(
                        content=pdf_bytes,
                        media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{clean_name}_Resume_VHC.pdf"'},
                    )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    # Fallback: return .tex
    return Response(
        content=latex,
        media_type="application/x-tex",
        headers={"Content-Disposition": f'attachment; filename="{clean_name}_Resume_VHC.tex"'},
    )



@router.post("/regenerate-smart-tags")
async def regenerate_smart_tags(
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Regenerate smart tags for ALL candidates in the bank. Admin only."""
    from services.smart_tags_service import generate_smart_tags

    cursor = db.candidate_bank.find({}, {"_id": 0}).batch_size(100)
    updated = 0
    async for doc in cursor:
        tags = generate_smart_tags(doc)
        await db.candidate_bank.update_one(
            {"id": doc["id"]},
            {"$set": {"smart_tags": tags}}
        )
        updated += 1

    return {"message": f"Regenerated smart tags for {updated} candidates", "updated": updated}


@router.get("/smart-tag-options")
async def get_smart_tag_options(
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Get all unique smart tags currently in use, for filter dropdowns."""
    pipeline = [
        {"$match": {"smart_tags": {"$exists": True, "$ne": []}}},
        {"$unwind": "$smart_tags"},
        {"$group": {"_id": "$smart_tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 50},
    ]
    results = await db.candidate_bank.aggregate(pipeline).to_list(50)
    return [{"tag": r["_id"], "count": r["count"]} for r in results]



