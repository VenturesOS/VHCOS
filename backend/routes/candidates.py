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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
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

    # Security: validate file content (magic bytes + threat scan)
    from services.security_service import validate_upload as _sec_validate
    sec_check = await _sec_validate(content, file.filename or "resume", current_user.get("email", "internal"))
    if not sec_check["valid"]:
        raise HTTPException(status_code=400, detail=sec_check["reason"])

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

    # Separate fields for $set vs $setOnInsert to avoid MongoDB path conflicts
    set_data = {k: v for k, v in candidate_data.items() if k not in ("created_at", "id", "resume_fingerprints")}
    set_data["updated_at"] = now

    await db.candidate_bank.update_one(
        upsert_filter,
        {
            "$set":         set_data,
            "$setOnInsert": {"created_at": now, "id": candidate_id},
            "$addToSet":    {"resume_fingerprints": fingerprint},
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


@router.get("/")
@router.get("")
async def list_candidates(
    page:      int   = Query(1, ge=1),
    limit:     int   = Query(20, ge=1, le=100),
    search:    Optional[str] = Query(None),
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
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List candidates with advanced filters."""
    skip  = (page - 1) * limit
    conditions = []

    # ── Text search (name, email, designation, headline) ──
    if search:
        import re
        pattern = re.escape(search)
        conditions.append({"$or": [
            {"name":             {"$regex": pattern, "$options": "i"}},
            {"email":            {"$regex": pattern, "$options": "i"}},
            {"phone":            {"$regex": pattern, "$options": "i"}},
            {"key_skills":       {"$regex": pattern, "$options": "i"}},
            {"skills":           {"$regex": pattern, "$options": "i"}},
            {"current_designation": {"$regex": pattern, "$options": "i"}},
            {"designation":      {"$regex": pattern, "$options": "i"}},
            {"headline":         {"$regex": pattern, "$options": "i"}},
        ]})

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
    if source:
        import re
        conditions.append({"$or": [
            {"source":            {"$regex": re.escape(source), "$options": "i"}},
            {"extension_version": {"$exists": source.lower() == "extension"}},
        ]})

    # ── Has Resume ──
    if has_resume == "yes":
        conditions.append({"$or": [
            {"resume_url":   {"$exists": True, "$nin": [None, ""]}},
            {"resume_path":  {"$exists": True, "$nin": [None, ""]}},
            {"resume_latex": {"$exists": True, "$nin": [None, ""]}},
        ]})
    elif has_resume == "no":
        conditions.append({
            "resume_url":   {"$in": [None, ""]},
            "resume_path":  {"$in": [None, ""]},
            "resume_latex": {"$in": [None, ""]},
        })

    # ── Contact Hidden (from Naukri — phone/email is null or placeholder) ──
    if contact_hidden == "yes":
        conditions.append({"$or": [
            {"email": {"$in": [None, ""]}},
            {"phone": {"$in": [None, ""]}},
        ]})
    elif contact_hidden == "no":
        conditions.append({
            "email": {"$exists": True, "$nin": [None, ""]},
            "phone": {"$exists": True, "$nin": [None, ""]},
        })

    # ── Capture Date Range ──
    if captured_after:
        conditions.append({"$or": [
            {"created_at": {"$gte": captured_after}},
            {"scraped_at": {"$gte": captured_after}},
        ]})
    if captured_before:
        conditions.append({"$or": [
            {"created_at": {"$lte": captured_before}},
            {"scraped_at": {"$lte": captured_before}},
        ]})

    query = {"$and": conditions} if conditions else {}

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
