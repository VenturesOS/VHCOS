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
import logging
from datetime import datetime, timezone
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/candidate-bank", tags=["candidate-bank"])
candidates_router = router


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

async def get_db():
    from config import db
    return db


from utils.auth import get_current_user


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

    resume_text = extract_text_from_file(content, file.filename or "resume")
    if not resume_text or len(resume_text) < 50:
        raise HTTPException(
            status_code=422,
            detail="Could not extract readable text from the file.",
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

    candidate_data.update({
        "id":                  candidate_id,
        "created_by":          current_user["id"],
        "created_at":          now,
        "updated_at":          now,
        "source":              "cv_upload",
        "resume_fingerprints": [fingerprint],
    })

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

    await db.candidate_bank.update_one(
        upsert_filter,
        {
            "$set":        candidate_data,
            "$setOnInsert": {"created_at": now},
            "$addToSet":   {"resume_fingerprints": fingerprint},
        },
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

@router.get("/")
@router.get("")
async def list_candidates(
    page:      int   = Query(1, ge=1),
    limit:     int   = Query(20, ge=1, le=100),
    search:    Optional[str] = Query(None),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List candidates with optional text search."""
    skip  = (page - 1) * limit
    query = {}

    if search:
        import re
        pattern = re.escape(search)
        query["$or"] = [
            {"name":             {"$regex": pattern, "$options": "i"}},
            {"email":            {"$regex": pattern, "$options": "i"}},
            {"key_skills":       {"$regex": pattern, "$options": "i"}},
            {"skills":           {"$regex": pattern, "$options": "i"}},
            {"current_designation": {"$regex": pattern, "$options": "i"}},
            {"designation":      {"$regex": pattern, "$options": "i"}},
            {"headline":         {"$regex": pattern, "$options": "i"}},
        ]

    total = await db.candidate_bank.count_documents(query)
    docs  = (
        await db.candidate_bank.find(query, {"_id": 0, "embedding": 0})
        .skip(skip)
        .limit(limit)
        .sort("created_at", -1)
        .to_list(limit)
    )

    return {
        "candidates": docs,
        "total":      total,
        "page":       page,
        "limit":      limit,
        "pages":      (total + limit - 1) // limit,
    }


# ---------------------------------------------------------------------------
# Get a single candidate
# ---------------------------------------------------------------------------

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

    return {"success": True, "candidate_id": candidate_id}


# ---------------------------------------------------------------------------
# Delete candidate
# ---------------------------------------------------------------------------

@router.delete("/{candidate_id}")
async def delete_candidate(
    candidate_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a candidate record."""
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
