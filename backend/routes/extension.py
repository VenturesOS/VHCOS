"""
Browser Extension API Routes - Extended Version
Handles complete Naukri profile capture with ALL fields
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
import logging
import os
import json as json_module
import asyncio
import threading
import hashlib
import gc
import ctypes

import base64
import re as re_module
from pathlib import Path

from utils.auth import get_current_user, require_role
from config import db, UPLOAD_DIR, ROOT_DIR
from services.cache import cache
from services.r2_storage import upload_to_r2
from models.extension import (
    CVUploadRequest, EvaluateFitRequest,
    WorkExperienceInput, EducationInput, SkillInput, CertificationInput,
    ProjectInput, LanguageInput, OnlineProfileInput, PersonalDetailsInput,
    CareerPreferencesInput, CompleteNaukriProfileInput, CaptureResponse,
    AIExtractRequest, AIExtractResponse,
)
from services.extension_service import (
    normalize_phone, _names_are_similar,
    evaluate_skills as _evaluate_skills,
    evaluate_experience as _evaluate_experience,
    evaluate_salary as _evaluate_salary,
    evaluate_location as _evaluate_location,
    evaluate_notice as _evaluate_notice,
    evaluate_data_completeness as _evaluate_data_completeness,
    ai_comprehensive_evaluation as _ai_comprehensive_evaluation,
    log_capture as _log_capture,
    build_team_visibility, build_complete_candidate, build_complete_update,
)
from services.activity_log_service import log_activity, ACTION_CAPTURED, ACTION_UPDATED, ACTION_CV_UPLOADED

# NEW: Groq service for cost-effective extraction
from services.groq_service import extract_phone_and_work_experience_groq

# NEW: Local LLM service for admin testing
from services.local_llm_service import extract_full_profile_local

logger = logging.getLogger(__name__)

# Test user for local LLM (DISABLED - quality too low on CPU)
TEST_LOCAL_LLM_EMAIL = "DISABLED_admin@vhc.in"  # Set to invalid email to disable

# Feature flag: Use Groq for all enrichment (Claude completely removed)
USE_GROQ_ENRICHMENT = os.getenv('USE_GROQ_ENRICHMENT', 'true').lower() == 'true'

extension_router = APIRouter(prefix="/api/extension", tags=["Browser Extension"])


# ============== VERSION CHECK ==============

@extension_router.get("/version")
async def get_extension_version():
    """Return the latest extension version so installed copies can prompt updates."""
    manifest_path = ROOT_DIR.parent / "browser-extension" / "manifest.json"
    version = "5.1.1"
    if manifest_path.exists():
        with open(manifest_path) as f:
            version = json_module.load(f).get("version", version)
    return {
        "version": version,
        "download_url": "/api/download/naukri-extension",
        "update_available": True,
        "changelog": [
            "CV iframe cross-origin fix: 3-strategy extraction (direct, relay, fetch)",
            "Full work history, education, personal details now captured",
            "all_frames content script for Naukri subdomains",
            "Background service worker CV data relay",
        ],
    }


# ============== CV UPLOAD (base64) ==============


@extension_router.post("/cv-upload")
async def upload_cv_base64(
    request: CVUploadRequest,
    current_user: dict = Depends(get_current_user),
):
    """Accept a base64-encoded CV from the extension and store it."""
    try:
        file_bytes = base64.b64decode(request.file_data)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 file data")

    if len(file_bytes) < 100:
        raise HTTPException(status_code=400, detail="File too small")

    ext = request.file_type if request.file_type in ("pdf", "doc", "docx") else "pdf"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"ext_cv_{request.candidate_id}_{ts}.{ext}"

    content_type = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(ext, "application/octet-stream")

    r2_key = f"extension-cvs/{filename}"
    result = await upload_to_r2(file_bytes, r2_key, content_type)

    resume_url = f"/api/uploads/{filename}" if result.get("storage") == "local" else result.get("r2_key", "")

    await db.candidate_bank.update_one(
        {"id": request.candidate_id},
        {"$set": {
            "resume_url": resume_url,
            "resume_filename": filename,
            "r2_metadata": result,
            "resume_source": "extension_cv_upload",
            "resume_uploaded_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    return {"success": True, "filename": filename, "storage": result.get("storage", "local")}


# ============== MANDATE LIST FOR EXTENSION ==============

@extension_router.get("/mandates")
async def get_extension_mandates(current_user: dict = Depends(get_current_user)):
    """Return the recruiter's assigned mandates (jobs) for the extension dropdown."""
    user_id = current_user["id"]
    role = current_user.get("role", "")

    if role == "admin":
        query = {"status": "active"}
    elif role == "recruiter":
        query = {
            "status": "active",
            "$or": [
                {"posted_by": user_id},
                {"assigned_recruiters": user_id},
            ],
        }
    elif role == "employer":
        query = {"status": "active", "posted_by": user_id}
    else:
        return []

    jobs = await db.jobs.find(
        query,
        {"_id": 0, "id": 1, "title": 1, "company_name": 1, "location": 1,
         "job_type": 1, "experience_required": 1, "salary_range": 1,
         "description": 1, "requirements": 1, "key_skills": 1,
         "min_experience": 1, "max_experience": 1, "job_code": 1},
    ).to_list(200)

    return [
        {
            "job_id": j["id"],
            "title": j.get("title", "Untitled"),
            "company": j.get("company_name", ""),
            "location": j.get("location", ""),
            "job_code": j.get("job_code", ""),
            "experience_required": j.get("experience_required", ""),
            "min_experience": j.get("min_experience"),
            "max_experience": j.get("max_experience"),
            "salary_range": j.get("salary_range", ""),
            "key_skills": j.get("key_skills") or [],
            "description": (j.get("description") or "")[:2000],
            "requirements": (j.get("requirements") or "")[:2000],
        }
        for j in jobs
    ]



# ============== SOURCE MIGRATION ==============

@extension_router.post("/migrate-linkedin-sources")
async def migrate_linkedin_sources(
    current_user: dict = Depends(require_role("admin")),
):
    """One-time migration: Re-tag profiles with LinkedIn URLs from naukri_extension to linkedin_extension.
    Also tags profiles with foundit URLs appropriately.
    Admin only.
    """
    import re
    results = {"linkedin_updated": 0, "foundit_updated": 0, "already_correct": 0, "errors": []}

    # Find all naukri_extension profiles with LinkedIn URLs
    linkedin_pattern = re.compile(r"linkedin\.com", re.IGNORECASE)
    linkedin_cursor = db.candidate_bank.find(
        {
            "source": "naukri_extension",
            "$or": [
                {"naukri_profile_url": linkedin_pattern},
                {"source_url": linkedin_pattern},
                {"online_profiles": {"$elemMatch": {"url": linkedin_pattern}}},
            ]
        },
        {"_id": 0, "id": 1, "name": 1, "naukri_profile_url": 1}
    )

    async for doc in linkedin_cursor:
        try:
            await db.candidate_bank.update_one(
                {"id": doc["id"]},
                {"$set": {
                    "source": "linkedin_extension",
                    "source_platform": "linkedin",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            results["linkedin_updated"] += 1
            logger.info(f"[Migration] Re-tagged '{doc.get('name')}' ({doc['id'][:12]}) → linkedin_extension")
        except Exception as e:
            results["errors"].append({"id": doc["id"], "error": str(e)})

    # Find all naukri_extension profiles with Foundit URLs
    foundit_pattern = re.compile(r"foundit\.in|monster\.com", re.IGNORECASE)
    foundit_cursor = db.candidate_bank.find(
        {
            "source": "naukri_extension",
            "$or": [
                {"naukri_profile_url": foundit_pattern},
                {"source_url": foundit_pattern},
            ]
        },
        {"_id": 0, "id": 1, "name": 1}
    )

    async for doc in foundit_cursor:
        try:
            await db.candidate_bank.update_one(
                {"id": doc["id"]},
                {"$set": {
                    "source": "foundit_extension",
                    "source_platform": "foundit",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            results["foundit_updated"] += 1
        except Exception as e:
            results["errors"].append({"id": doc["id"], "error": str(e)})

    # Count already-correct profiles
    results["already_correct"] = await db.candidate_bank.count_documents({
        "source": {"$in": ["linkedin_extension", "foundit_extension"]}
    })

    return {
        "success": True,
        "results": results,
        "message": f"Migration complete. LinkedIn: {results['linkedin_updated']} updated, Foundit: {results['foundit_updated']} updated, Already correct: {results['already_correct']}"
    }

# ── Evaluation performed via services.extension_service ──


@extension_router.post("/evaluate-fit")
async def evaluate_candidate_fit(
    request: EvaluateFitRequest,
    current_user: dict = Depends(get_current_user),
):
    """Evaluate a captured candidate against a selected mandate.
    Returns color-coded criteria: green (match), yellow (partial/uncertain), red (mismatch).
    Uses rule-based checks where structured data exists, then AI for comprehensive analysis.
    """
    job = await db.jobs.find_one({"id": request.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidate = request.candidate_profile
    criteria = []

    # ── RULE-BASED EVALUATION (only when structured data exists) ──
    has_structured_job_data = bool(
        job.get("key_skills") or job.get("min_experience") or job.get("salary_range")
    )

    if has_structured_job_data:
        criteria.extend(_evaluate_skills(candidate, job))
        criteria.extend(_evaluate_experience(candidate, job))
        criteria.extend(_evaluate_salary(candidate, job))

    # Location check works even without structured data
    criteria.extend(_evaluate_location(candidate, job))
    criteria.extend(_evaluate_notice(candidate, job))

    # ── DATA COMPLETENESS CHECK ──
    criteria.extend(_evaluate_data_completeness(candidate))

    # ── AI COMPREHENSIVE EVALUATION ──
    # AI is the primary evaluator — it reads job description/requirements text
    try:
        ai_criteria = await _ai_comprehensive_evaluation(candidate, job, has_structured_job_data)
        criteria.extend(ai_criteria)
    except Exception as e:
        logger.warning(f"[Evaluate-Fit] AI analysis failed: {e}")
        criteria.append({"text": "AI analysis unavailable — evaluation may be incomplete", "color": "yellow", "category": "ai_analysis"})

    # Sort: red first (problems on top), then yellow, then green
    color_order = {"red": 0, "yellow": 1, "green": 2}
    criteria.sort(key=lambda c: color_order.get(c.get("color", "yellow"), 1))

    # Overall verdict — stricter logic
    greens = sum(1 for c in criteria if c["color"] == "green")
    yellows = sum(1 for c in criteria if c["color"] == "yellow")
    reds = sum(1 for c in criteria if c["color"] == "red")
    total = len(criteria)

    if total == 0:
        verdict = "unknown"
    elif reds >= 3:
        verdict = "weak_match"
    elif reds >= 1 and greens <= reds:
        verdict = "weak_match"
    elif reds == 0 and greens >= 3:
        verdict = "strong_match"
    elif greens > reds and greens > yellows:
        verdict = "strong_match"
    elif greens > reds:
        verdict = "potential_match"
    else:
        verdict = "potential_match"

    return {
        "success": True,
        "verdict": verdict,
        "criteria": criteria,
        "summary": {
            "green": greens,
            "yellow": yellows,
            "red": reds,
            "total": total,
        },
        "job_title": job.get("title", ""),
    }


# ============== AI EXTRACTION ==============

@extension_router.post("/ai-extract", response_model=AIExtractResponse)
async def ai_extract_profile(
    request: AIExtractRequest,
    current_user: dict = Depends(get_current_user)
):
    """Extract structured profile data from raw Naukri page text.
    Uses DOM-extracted fields + lightweight regex for instant response.
    Background enrichment (Claude) fills in remaining details after capture."""
    
    if not request.raw_text or len(request.raw_text) < 50:
        return AIExtractResponse(success=False, error="Insufficient text to extract profile")
    
    raw_text = request.raw_text
    profile = {}

    # ── Step 1: DOM-extracted fields (most reliable, from Chrome extension) ──
    if request.dom_extracted_name and request.dom_extracted_name.strip():
        profile["name"] = request.dom_extracted_name.strip()
    if request.dom_extracted_email and request.dom_extracted_email.strip():
        profile["email"] = request.dom_extracted_email.strip()
    if request.dom_extracted_phone and request.dom_extracted_phone.strip():
        profile["phone"] = request.dom_extracted_phone.strip()

    # ── Blocklist check: strip Naukri license numbers ──
    from routes.candidates import is_phone_blocked
    if profile.get("phone") and await is_phone_blocked(db, profile["phone"]):
        logger.warning(f"[Capture] Blocked phone {profile['phone']} (Naukri license number)")
        profile["phone"] = None

    # ── Step 2: Lightweight regex for key fields only ────────────────────────
    import re as _re

    # ── Experience Years — Priority-0 adjacency (structural signature) ──
    # Naukri top card ALWAYS places experience adjacent to currency:
    # "8y ₹14 Lacs", "22y  ₹60 Lacs". Role durations are NEVER followed by
    # currency — they're followed by company names. So adjacency is unambiguous.
    if not profile.get("total_experience_years"):
        for pat, kind in [
            (r'(?<![A-Za-z0-9])(\d{1,2})\s*[yY]\s{0,5}(?=[\u20B9]|\bRs\b|\bINR\b|\d+\s*(?:Lacs?|Lakhs?|LPA|Cr|Crore))', None),
            (r'(?<![A-Za-z0-9])(\d{1,2})\s*[yY]\s+(\d{1,2})\s*[mM]\s{0,5}(?=[\u20B9]|\bRs\b|\bINR\b|\d+\s*(?:Lacs?|Lakhs?|LPA))', 'ym'),
            (r'(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s{0,5}(?=[\u20B9]|\bRs\b|\bINR\b|\d+\s*(?:Lacs?|Lakhs?|LPA))', None),
        ]:
            m = _re.search(pat, raw_text[:2000], _re.IGNORECASE)
            if not m:
                continue
            if kind == 'ym':
                profile["total_experience_years"] = round(int(m.group(1)) + int(m.group(2)) / 100, 2)
                profile["_exp_source"] = "regex_adjacency_ym"
            else:
                profile["total_experience_years"] = float(m.group(1))
                profile["_exp_source"] = "regex_adjacency"
            break

    # ── Fallback — section-cut bounded regex (when adjacency misses) ──
    if not profile.get("total_experience_years"):
        section_cut = _re.search(
            r'\b(?:Professional\s*Experience|Work\s*Experience|Employment\s*History|Education|Academic|Key\s*Skills|IT\s*Skills)\b',
            raw_text, _re.IGNORECASE,
        )
        header_scan = raw_text[:section_cut.start()] if section_cut else raw_text[:1500]
        # Layer 1: compact "16y 3m" / "0y 8m" — most precise when present
        exp_m = _re.search(r'(?<![A-Za-z0-9])(\d{1,2})\s*[yY]\s+(\d{1,2})\s*[mM](?![A-Za-z0-9])', header_scan)
        if exp_m:
            years = int(exp_m.group(1))
            months = int(exp_m.group(2))
            profile["total_experience_years"] = round(years + months / 100, 2)
            profile["_exp_source"] = "regex_compact_ym"
        else:
            # Layer 2: whole-year "16y" — primary Naukri top-card format
            exp_m = _re.search(r'(?<![A-Za-z0-9])(\d{1,2})\s*[yY](?![A-Za-z0-9ears])', header_scan)
            if exp_m:
                profile["total_experience_years"] = float(exp_m.group(1))
                profile["_exp_source"] = "regex_y_only"
            else:
                # Layer 3: full-word "16 years" / "16+ years" / "16.5 yrs"
                exp_m = _re.search(
                    r'(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b', header_scan, _re.IGNORECASE
                )
                if exp_m:
                    v = float(exp_m.group(1))
                    if v >= 0:
                        profile["total_experience_years"] = v
                        profile["_exp_source"] = "regex_years_word"

    # Notice period — Naukri top-card patterns
    # Order matters: prefer explicit "Notice Period" label first, then top-card phrasings
    if not profile.get("notice_period"):
        notice_m = _re.search(r'Notice\s*Period\s*[:\-]\s*(.+?)(?:\n|$)', raw_text, _re.IGNORECASE)
        if notice_m:
            profile["notice_period"] = notice_m.group(1).strip()
        else:
            # Top-card phrases common in Naukri profile headers: "3 Months", "60 days",
            # "Immediate", "15 Days or less". Only scan the header region (first 2000 chars)
            # so we don't false-positive on phrases like "with 2 months of training".
            header = raw_text[:2000]
            notice_patterns = [
                (r'\bImmediate(?:ly)?\b', "Immediate"),
                (r'\b15\s*[Dd]ays?\s*or\s*less\b', "15 Days or less"),
                (r'\b(\d{1,3})\s*[Dd]ays?\b', None),      # "15 days", "60 days"
                (r'\b(\d{1,2})\s*[Mm]onths?\b', None),    # "3 Months", "2 months"
                (r'\b(\d{1,2})\s*[Mm]o\b', None),         # "3 Mo"
            ]
            for pat, fixed in notice_patterns:
                m = _re.search(pat, header)
                if m:
                    if fixed:
                        profile["notice_period"] = fixed
                    elif "day" in pat.lower():
                        profile["notice_period"] = f"{m.group(1)} Days"
                    else:
                        profile["notice_period"] = f"{m.group(1)} Months"
                    break

    # CTC — Naukri top-card patterns (CRITICAL, was missing before)
    # Naukri header shows "₹60 Lacs (expects: ₹80 Lacs)" for most candidates.
    # Always scan the header region to avoid false positives from work-history text.
    if not profile.get("current_salary") or not profile.get("expected_salary"):
        header = raw_text[:2000]

        def _to_rupees(val: str, unit: str) -> int:
            """Convert e.g. '60 Lacs' → 6000000, '1.2 Cr' → 12000000."""
            try:
                n = float(val.replace(",", ""))
            except ValueError:
                return 0
            unit_l = (unit or "").lower()
            if "cr" in unit_l:
                return int(round(n * 10_000_000))
            if "lac" in unit_l or "lakh" in unit_l or unit_l == "l":
                return int(round(n * 100_000))
            if "lpa" in unit_l:
                return int(round(n * 100_000))
            return int(round(n))  # raw rupees

        # Pattern 1 — the canonical Naukri top-card:
        # "₹60 Lacs (expects: ₹80 Lacs)" → capture both at once
        naukri_both = _re.search(
            r'₹?\s*(\d+(?:\.\d+)?)\s*(Lacs?|Lakhs?|LPA|Cr|Crore)'
            r'(?:\s*\(\s*expects?\s*:?\s*₹?\s*(\d+(?:\.\d+)?)\s*(Lacs?|Lakhs?|LPA|Cr|Crore)?\s*\))?',
            header, _re.IGNORECASE,
        )
        if naukri_both:
            cur_val, cur_unit, exp_val, exp_unit = naukri_both.groups()
            cur_rupees = _to_rupees(cur_val, cur_unit)
            if cur_rupees and not profile.get("current_salary"):
                profile["current_salary"] = cur_rupees
            if exp_val and not profile.get("expected_salary"):
                exp_rupees = _to_rupees(exp_val, exp_unit or cur_unit)
                if exp_rupees:
                    profile["expected_salary"] = exp_rupees

        # Pattern 2 — labeled fallback ("Current CTC: 6.5 Lacs", "Expected: 10 LPA")
        if not profile.get("current_salary"):
            m = _re.search(
                r'(?:Current\s*(?:CTC|Salary|Compensation)|Present\s*CTC)'
                r'\s*[:\-]?\s*₹?\s*(\d+(?:\.\d+)?)\s*(Lacs?|Lakhs?|LPA|Cr|Crore|L)?',
                header, _re.IGNORECASE,
            )
            if m:
                val, unit = m.groups()
                profile["current_salary"] = _to_rupees(val, unit or "Lacs")
        if not profile.get("expected_salary"):
            m = _re.search(
                r'(?:Expected\s*(?:CTC|Salary|Compensation)|Expectation)'
                r'\s*[:\-]?\s*₹?\s*(\d+(?:\.\d+)?)\s*(Lacs?|Lakhs?|LPA|Cr|Crore|L)?',
                header, _re.IGNORECASE,
            )
            if m:
                val, unit = m.groups()
                profile["expected_salary"] = _to_rupees(val, unit or "Lacs")

        # Sanity caps — reject absurd values (above ₹50 Cr are data errors)
        for fld in ("current_salary", "expected_salary"):
            v = profile.get(fld)
            if isinstance(v, (int, float)) and (v < 10000 or v > 500_000_000):
                profile[fld] = None

    # Location
    loc_m = _re.search(r'(?:Current\s*)?Location\s*[:\-]\s*(.+?)(?:\n|$)', raw_text, _re.IGNORECASE)
    if loc_m:
        profile["location"] = loc_m.group(1).strip()

    # Fill nulls for expected schema fields
    for field in ["name", "email", "phone", "current_company", "current_designation",
                  "current_department", "current_industry", "total_experience_years",
                  "headline", "profile_summary", "current_salary", "expected_salary",
                  "notice_period", "location", "preferred_locations", "date_of_birth",
                  "gender", "marital_status", "nationality", "category",
                  "key_skills", "it_skills", "work_experience", "education",
                  "certifications", "projects", "languages", "online_profiles"]:
        if field not in profile:
            profile[field] = None

    profile["naukri_profile_id"] = request.naukri_profile_id
    profile["naukri_profile_url"] = request.page_url

    has_name = bool(profile.get("name"))
    has_contact = bool(profile.get("email") or profile.get("phone"))

    # ── Always run full regex parser for top-card consistency ──
    # Even when DOM provides name/email/phone, the full parser's label-aware regex
    # catches experience/CTC/notice/location across Naukri's many layouts
    # (compact "19y ₹25 Lacs", labeled "Experience\n19 Years\nCurrent CTC\n₹25 Lacs").
    # DOM always wins for name/email/phone (most reliable). Parser fills the rest.
    try:
        from services.naukri_regex_parser import extract_full_profile_regex as _full_regex
        _parser = _full_regex(
            raw_text=raw_text,
            recruiter_phone=request.recruiter_phone,
            recruiter_email=current_user.get("email", ""),
        ) or {}

        # Mapping: parser field → profile field. Parser only fills when profile value is falsy.
        _fill_map = [
            ("current_employer", "current_company"),
            ("current_designation", "current_designation"),
            ("current_department", "current_department"),
            ("current_industry", "current_industry"),
            ("experience_years", "total_experience_years"),
            ("headline", "headline"),
            ("profile_summary", "profile_summary"),
            ("current_ctc", "current_salary"),
            ("expected_ctc", "expected_salary"),
            ("notice_period", "notice_period"),
            ("location", "location"),
            ("key_skills", "key_skills"),
            ("work_experience", "work_experience"),
            ("education", "education"),
            ("certifications", "certifications"),
            ("languages", "languages"),
            ("preferred_locations", "preferred_locations"),
            ("date_of_birth", "date_of_birth"),
            ("gender", "gender"),
            ("marital_status", "marital_status"),
        ]
        # Label-token blacklist — prevents labeled-layout leakage where e.g.
        # "Experience\n19 Years\nCurrent CTC\n..." causes the parser to pick up
        # the label token "Current CTC" as current_designation.
        _LABEL_TOKENS = {
            'experience', 'total experience', 'current ctc', 'expected ctc',
            'ctc', 'notice period', 'current location', 'location', 'current',
            '19 years', 'current salary', 'expected salary', 'highest qualification',
            'current employer', 'current company', 'current industry', 'current department',
            'summary', 'profile summary', 'skills', 'key skills', 'education',
        }
        for src, dst in _fill_map:
            v = _parser.get(src)
            if v in (None, "", [], {}):
                continue
            # Scalar string hygiene: reject if value matches a label token OR
            # looks like a numeric duration (e.g. "19 Years", "3 Months") which
            # would only be valid as experience/notice, not company/designation.
            if isinstance(v, str) and dst in ("current_company", "current_designation", "current_industry", "current_department", "headline"):
                v_norm = v.strip().lower()
                if v_norm in _LABEL_TOKENS:
                    continue
                if _re.match(r'^\d{1,2}\s*(?:years?|yrs?|months?|mos?)\s*$', v_norm, _re.IGNORECASE):
                    continue
                if _re.match(r'^[\u20B9]?\s*\d+(?:\.\d+)?\s*(?:Lacs?|Lakhs?|LPA|Cr|Crore)\b', v, _re.IGNORECASE):
                    continue
            if profile.get(dst) in (None, "", [], {}):
                profile[dst] = v

        # DOM fields ALWAYS win for name/email/phone (most reliable source)
        if not profile.get("name") and _parser.get("candidate_name"):
            profile["name"] = _parser["candidate_name"]
        if not profile.get("email") and _parser.get("candidate_email"):
            profile["email"] = _parser["candidate_email"]
        if not profile.get("phone") and _parser.get("candidate_phone"):
            profile["phone"] = _parser["candidate_phone"]

        # Refresh has_name/has_contact after parser backfill
        has_name = bool(profile.get("name"))
        has_contact = bool(profile.get("email") or profile.get("phone"))
    except Exception as _e:
        logger.warning(f"[AI Extract] Full parser merge failed ({_e}) — continuing with ad-hoc regex")

    if has_name and has_contact:
        logger.info(f"[AI Extract] DOM+FullParser instant response for {profile.get('name')} — Groq enrichment will follow on capture")
        # Fire-and-forget extraction trace for admin debug
        try:
            from routes.extraction_trace import record_trace_async
            import asyncio as _asyncio
            _asyncio.create_task(record_trace_async(
                db=db,
                endpoint="ai-extract",
                candidate_name=profile.get("name"),
                raw_text=raw_text,
                regex_output=_parser if "_parser" in dir() else None,
                llm_output=None,
                merged_output=profile,
                llm_source="regex_only",
                user_email=current_user.get("email"),
            ))
        except Exception:
            pass
        return AIExtractResponse(success=True, profile_data=profile)

    # ── Fallback: Groq for initial parse if DOM fields missing ─────────────
    logger.info(f"[AI Extract] DOM fields insufficient (name={has_name}, contact={has_contact}) — using Groq")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return AIExtractResponse(success=False, error="OpenAI API key not configured")
    
    # Truncate to ~6000 chars for faster LLM processing (profiles rarely exceed this)
    raw_text = request.raw_text[:6000]
    
    prompt = f"""You are a data extraction expert parsing a candidate profile page from a recruitment platform.

CRITICAL RULES:
1. The "name" field must be ONLY the person's actual name (e.g., "Rajiv Mathur"). 
   - NEVER include experience years, designations, page titles, or any other text in the name.
   - WRONG: "Puja Gupta Basu - 15 Year(s)", "Search candidates", "Vikrant Kumar Senior Manager"
   - CORRECT: "Puja Gupta Basu", "Vikrant Kumar"
2. For "email": Return null if no real email is found. 
   - IGNORE emails like support@naukri.com, placeholder@*, noreply@*, or any @naukri.com address.
   - Only return a personal/work email that belongs to the candidate.
3. For "phone": Return null if no real phone number is found. Only return numbers that belong to the candidate.
   - Look carefully in the CV text, contact sections, and personal details for phone numbers.
   - Indian mobile numbers start with 6-9 and have 10 digits.
4. IGNORE all navigation text (Jobs, Resdex, Reports, Search, Home, Prev, Next, Save for later, etc.)
5. IGNORE Naukri marketing text ("Decode India's largest talent pool", "AI matched similar profiles", etc.)
6. If the text contains "AI matched similar profiles" or "Similar profiles" section, ONLY extract the MAIN candidate's data that appears BEFORE that section.
7. The CV preview at the bottom may contain the candidate's real email and phone — prioritize those.

Return a JSON object with these fields (use null for missing data):

{{
  "name": "Full name only (no titles, no experience, no designations appended)",
  "email": "candidate's personal/work email or null",
  "phone": "candidate's phone with country code or null",
  "current_company": "current employer",
  "current_designation": "current job title",
  "current_department": "department if mentioned",
  "current_industry": "industry sector",
  "total_experience_years": number (e.g., 15.5),
  "headline": "resume headline text",
  "profile_summary": "full profile summary/about text — capture the ENTIRE summary, not just the first line",
  "current_salary": number in INR (35 Lacs = 3500000) or null,
  "expected_salary": number in INR or null,
  "notice_period": "e.g. 1 Month, 2 Months, Immediate",
  "location": "current city",
  "preferred_locations": ["city1", "city2"],
  "date_of_birth": "DOB or null",
  "gender": "Male/Female/Other or null",
  "marital_status": "status or null",
  "nationality": "nationality or null",
  "category": "General/OBC/SC/ST or null",
  "key_skills": ["skill1", "skill2", ...all mentioned skills],
  "it_skills": [{{"name": "skill", "version": "ver", "experience_years": num}}],
  "work_experience": [
    {{
      "company": "company name",
      "designation": "job title / role",
      "department": "department if mentioned",
      "industry": "industry if mentioned",
      "from_date": "start date",
      "to_date": "end date or null if current",
      "duration": "e.g. 3 years 2 months",
      "is_current": boolean,
      "location": "work location if mentioned",
      "description": "DETAILED description of the role — include ALL responsibilities, key tasks, projects handled, technologies used, team managed, and achievements. Capture the FULL synopsis for each role, not just a one-line summary. This is CRITICAL for recruitment evaluation.",
      "responsibilities": ["responsibility 1", "responsibility 2", ...],
      "achievements": ["achievement 1", "achievement 2", ...]
    }}
  ],
  "education": [{{"degree": "degree", "institution": "college/university", "year_of_passing": "year", "specialization": "field"}}],
  "certifications": [{{"name": "cert name", "issuing_authority": "issuer"}}],
  "projects": [{{"title": "project", "description": "detailed project description", "role": "role in project", "skills_used": ["skill1"]}}],
  "languages": [{{"language": "name", "proficiency": "level"}}],
  "online_profiles": [{{"platform": "LinkedIn/GitHub", "url": "url"}}]
}}

IMPORTANT EXTRACTION RULES:
- Convert "X Lacs" to number (35 Lacs = 3500000)
- Convert experience to decimal (15 years 6 months = 15.5)
- Extract ALL work experiences with FULL descriptions — every role, every company, every detail
- For each work experience, capture the COMPLETE role description/synopsis, not just the job title
- Include responsibilities and achievements as separate arrays when available
- Extract ALL education entries, ALL skills, ALL certifications
- Return ONLY valid JSON

Page text:
{raw_text}"""

    # Add DOM extraction hints if available
    hint_parts = []
    if request.dom_extracted_name:
        hint_parts.append(f"- The candidate's REAL name extracted from the page title is: {request.dom_extracted_name}. USE THIS as the name.")
    if request.dom_extracted_email:
        hint_parts.append(f"- The candidate's email extracted directly from the page DOM is: {request.dom_extracted_email}")
    if request.dom_extracted_phone:
        hint_parts.append(f"- The candidate's phone extracted directly from the page DOM is: {request.dom_extracted_phone}")
    
    # Add recruiter blocklist to prompt
    blocklist_parts = []
    if request.recruiter_email:
        blocklist_parts.append(f"- RECRUITER'S EMAIL (IGNORE THIS): {request.recruiter_email}")
    if request.recruiter_phone:
        blocklist_parts.append(f"- RECRUITER'S PHONE (IGNORE THIS): {request.recruiter_phone}")
    
    if blocklist_parts:
        prompt += f"""

RECRUITER IDENTITY (the person viewing this profile — NOT the candidate):
{chr(10).join(blocklist_parts)}
The above contact details belong to the RECRUITER who is logged in. They may appear on the page header/navigation. NEVER return these as the candidate's contact info."""
    
    if hint_parts:
        prompt += f"""

VERIFIED DATA FROM PAGE DOM (use these values, they are more reliable than anything in the text):
{chr(10).join(hint_parts)}
IMPORTANT: The page text may also contain the logged-in RECRUITER's email/phone. IGNORE any contact info that matches the recruiter's details listed above."""

    try:
        profile_data = None

        # ── HYBRID: Regex first for ALL users (zero cost), Groq fallback ──
        try:
            from services.naukri_regex_parser import extract_full_profile_regex
            ai = extract_full_profile_regex(
                raw_text=raw_text,
                recruiter_phone=request.recruiter_phone,
                recruiter_email=current_user.get("email", ""),
            )
            regex_quality = _score_extraction_quality(ai) if ai else 0.0
            if ai and regex_quality >= 0.5:
                profile_data = {
                    "name": ai.get("candidate_name"),
                    "email": ai.get("candidate_email"),
                    "phone": ai.get("candidate_phone"),
                    "current_company": ai.get("current_employer"),
                    "current_designation": ai.get("current_designation"),
                    "current_department": ai.get("current_department"),
                    "current_industry": ai.get("current_industry"),
                    "total_experience_years": ai.get("experience_years"),
                    "headline": ai.get("headline"),
                    "profile_summary": ai.get("profile_summary"),
                    "current_salary": ai.get("current_ctc"),
                    "expected_salary": ai.get("expected_ctc"),
                    "notice_period": ai.get("notice_period"),
                    "location": ai.get("location"),
                    "key_skills": ai.get("key_skills"),
                    "work_experience": ai.get("work_experience"),
                    "education": ai.get("education"),
                    "certifications": ai.get("certifications"),
                    "languages": ai.get("languages"),
                    "preferred_locations": ai.get("preferred_locations"),
                    "date_of_birth": ai.get("date_of_birth"),
                    "gender": ai.get("gender"),
                    "marital_status": ai.get("marital_status"),
                    "_extraction_source": "regex_hybrid",
                }
                logger.info(f"[AI Extract] Regex sufficient ({regex_quality:.0%}) for {profile_data.get('name')} — Groq SKIPPED")
            else:
                logger.info(f"[AI Extract] Regex quality low ({regex_quality:.0%}), using Groq")
        except Exception as regex_err:
            logger.warning(f"[AI Extract] Regex parser failed ({regex_err}), using Groq")

        if profile_data is None:
            # ── Groq Llama 3.3 70B fallback ──
            try:
                from services.groq_service import extract_full_profile_groq
                
                groq_result = await extract_full_profile_groq(
                    raw_text=raw_text,
                    candidate_name=None
                )
                
                if groq_result and not groq_result.get('error'):
                    profile_data = groq_result
                    profile_data["_extraction_source"] = "groq_llama_3_3_70b"
                    logger.info(f"[AI Extract] Groq extraction succeeded for: {profile_data.get('name')}")
                else:
                    logger.warning("[AI Extract] Groq returned error, falling back to DOM data")
                    profile_data = None
            except Exception as groq_err:
                logger.warning(f"[AI Extract] Groq failed ({groq_err}), falling back to DOM data")
                profile_data = None
        
        # Initialize profile_data if Groq failed
        if profile_data is None:
            profile_data = {}

        # Override with DOM-extracted values (most reliable sources)
        if request.dom_extracted_name and request.dom_extracted_name.strip():
            profile_data["name"] = request.dom_extracted_name.strip()
        if request.dom_extracted_email and request.dom_extracted_email.strip():
            profile_data["email"] = request.dom_extracted_email.strip()
        if request.dom_extracted_phone and request.dom_extracted_phone.strip():
            profile_data["phone"] = request.dom_extracted_phone.strip()
        # Blocklist check
        if profile_data.get("phone") and await is_phone_blocked(db, profile_data["phone"]):
            profile_data["phone"] = None
        profile_data["naukri_profile_id"] = request.naukri_profile_id
        profile_data["naukri_profile_url"] = request.page_url
        
        # ── Auto-repair loop: cross-validate experience against work-history ──
        # If extracted experience is missing OR much smaller than the work-history
        # date span, trust the date span. Catches cases where the LLM/regex grabbed
        # a per-role tenure (e.g. "1y" for Piaggio since Feb '25) instead of the
        # top-card total (8y).
        try:
            wexp = profile_data.get("work_experience") or []
            if wexp:
                import datetime as _dt
                def _parse_ym(s):
                    if not s or not isinstance(s, str):
                        return None
                    s = s.strip()
                    if _re.match(r'^(present|current|till\s*date|date)$', s, _re.IGNORECASE):
                        n = _dt.datetime.now()
                        return (n.year, n.month)
                    m = _re.search(r"([A-Za-z]{3,9})\s*['\u2019]?\s*(\d{2,4})", s)
                    if m:
                        mon_s = m.group(1)[:3].lower()
                        mmap = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
                        mon = mmap.get(mon_s)
                        yr = int(m.group(2))
                        if yr < 100:
                            yr += 2000 if yr < 50 else 1900
                        if mon and 1900 < yr < 2100:
                            return (yr, mon)
                    m = _re.match(r'^(\d{4})$', s)
                    if m:
                        return (int(m.group(1)), 1)
                    return None
                spans = []
                for e in wexp:
                    frm = _parse_ym(e.get("from_date"))
                    to = _parse_ym(e.get("to_date"))
                    if not to and e.get("is_current"):
                        n = _dt.datetime.now()
                        to = (n.year, n.month)
                    if frm and to:
                        spans.append((frm, to))
                if spans:
                    earliest = min(s[0] for s in spans)
                    latest = max(s[1] for s in spans)
                    total_mo = (latest[0] - earliest[0]) * 12 + (latest[1] - earliest[1])
                    if total_mo > 0 and total_mo < 50 * 12:
                        date_span = round(total_mo // 12 + (total_mo % 12) / 100, 2)
                        existing = profile_data.get("total_experience_years") or profile_data.get("experience_years")
                        # Overwrite when (a) missing, or (b) suspiciously low
                        # (less than half the date span and date span ≥ 2 years)
                        if existing is None or (date_span >= 2 and existing < date_span / 2):
                            profile_data["total_experience_years"] = date_span
                            profile_data["experience_years"] = date_span
                            profile_data["_exp_source"] = "date_span_fallback"
                            logger.info(f"[AI-Extract] Auto-repair: exp {existing}→{date_span} (from work_history span)")
        except Exception as repair_err:
            logger.warning(f"[AI-Extract] Auto-repair loop error: {repair_err}")

        # If no useful data at all, return error
        if not profile_data.get("name"):
            return AIExtractResponse(success=False, error="Could not extract profile data")

        logger.info(f"[AI Extract] Successfully extracted profile for: {profile_data.get('name')}")
        
        return AIExtractResponse(success=True, profile_data=profile_data)
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
        logger.error(f"[AI Extract] Error: {error_msg}")
        
        # Fallback: if LLM fails but we have DOM-extracted data, use that
        if request.dom_extracted_name and request.dom_extracted_name.strip():
            logger.info(f"[AI Extract] Using DOM fallback for: {request.dom_extracted_name}")
            fallback_data = {
                "name": request.dom_extracted_name.strip(),
                "email": (request.dom_extracted_email or "").strip() or None,
                "phone": (request.dom_extracted_phone or "").strip() or None,
                "naukri_profile_id": request.naukri_profile_id,
                "naukri_profile_url": request.page_url,
                "_ai_extraction_failed": True,
            }
            return AIExtractResponse(success=True, profile_data=fallback_data)
        
        return AIExtractResponse(success=False, error=error_msg)


# ============== ENDPOINTS ==============


def _fire_and_forget(coro):
    """Run an async coroutine in a separate thread so it never blocks the response."""
    def _run():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        except Exception as e:
            logger.error(f"[BG-Thread] Unhandled error: {e}")
        finally:
            loop.close()
    threading.Thread(target=_run, daemon=True).start()


# ── Memory pressure release helper (Phase 55.4, 2026-02-27) ──────────────
# Each background enrichment thread allocates ~100–150 MB of transient
# Python objects (Anthropic JSON responses, regex match buffers, BSON
# dicts, BGE embedding tensors, smart-tags numpy arrays). When the daemon
# thread exits, Python's cyclic GC doesn't run immediately and glibc keeps
# the memory in secondary arenas that MALLOC_TRIM_THRESHOLD_ cannot reach
# (those arenas are pinned alive by long-lived ThreadPoolExecutor workers).
# Calling gc.collect() + malloc_trim(0) explicitly at the end of each
# enrichment forces both Python and glibc to release the memory back to
# the kernel. Confirmed via py-spy dump (worker 43584, 3.7 GB RSS) on
# 2026-02-27 — VmData = 4.4 GB despite max-requests=25 worker recycling.
try:
    _LIBC = ctypes.CDLL("libc.so.6")
    _LIBC.malloc_trim.argtypes = [ctypes.c_int]
    _LIBC.malloc_trim.restype = ctypes.c_int
except Exception:
    _LIBC = None


def _release_memory():
    """Force Python GC + glibc arena release. Called after every background enrichment."""
    try:
        gc.collect()
        if _LIBC is not None:
            _LIBC.malloc_trim(0)
    except Exception:
        # Never let cleanup raise — would mask the real enrichment outcome.
        pass


async def _force_memory_release_after_response():
    """FastAPI dependency that triggers `_release_memory()` AFTER the
    response is fully sent. Applied to high-allocation endpoints like
    /api/extension/capture so the foreground hot path (regex parsing,
    Pydantic model construction, sanitization, LaTeX regen, BSON
    serialization — up to ~250-300 MB per call) returns its memory to
    the kernel instead of accumulating in glibc arenas.

    Confirmed necessary on 2026-02-28: Step 1 patch (background-only
    cleanup) reduced leak from 100 MB/min to 30 MB/min but worker 1007
    still bloated to 3.2 GB over 3h29m — proving the foreground request
    handler was the larger leak source.
    """
    try:
        yield
    finally:
        _release_memory()


# ── Concurrency cap for embedding generation (OOM protection) ──────────────
# Prevents > N simultaneous BGE encodes per gunicorn worker. The encode is
# CPU-bound and the model itself is ~250 MB resident; without this, a flood
# of captures (10–20/sec) accumulates pending asyncio tasks each holding a
# motor client + tensor buffers → OOM kill (root cause of May-05 13:04 crash).
# NOTE: must be threading-level (not asyncio) because _fire_and_forget spawns
# a fresh event loop per thread; an asyncio.Semaphore would fail across loops.
_EMBED_CONCURRENCY = int(os.environ.get("EMBED_CONCURRENCY", "2"))
_EMBED_THREAD_SEMAPHORE = threading.BoundedSemaphore(_EMBED_CONCURRENCY)


# ── Capture deduplication (Phase 52, 2026-05-06) ───────────────────────────
# Skip the expensive Qwen + embedding pipeline when:
#   1. The profile was successfully enriched within the last
#      DEDUP_FRESH_DAYS days, AND
#   2. The raw text we'd send to Qwen hashes to the same value as last time.
# This catches the common pattern where a recruiter (or two recruiters in
# the same team) re-captures the same Naukri profile within days.
# NOTE: dedup ONLY skips Qwen+embedding. Mandate tagging, visibility updates,
# and the candidate_bank UPSERT all still run — the candidate ALWAYS shows
# in "Add Candidate" tagged to the chosen job.
DEDUP_FRESH_DAYS = int(os.environ.get("CAPTURE_DEDUP_FRESH_DAYS", "7"))


def _should_skip_enrichment(existing_doc: Optional[dict], raw_text: str) -> tuple[bool, str]:
    """Decide whether to skip Qwen + embedding for this capture.

    Returns:
        (skip: bool, reason: str)
        reason is a short tag for logging — one of:
          - "no_existing"       → never enriched (always run)
          - "stale"             → last enrichment > DEDUP_FRESH_DAYS ago (run)
          - "text_changed"      → fresh but Naukri data changed (run)
          - "fresh_unchanged"   → SKIP (recent + identical text)
          - "no_raw_text"       → SKIP (nothing to enrich)
    """
    if not raw_text or not raw_text.strip():
        return True, "no_raw_text"

    if not existing_doc:
        return False, "no_existing"

    last_iso = existing_doc.get("ai_enriched_at")
    last_hash = existing_doc.get("raw_text_hash")
    enrichment_status = existing_doc.get("enrichment_status")

    # If the previous attempt failed, always retry — never skip on failed records.
    if enrichment_status not in ("enriched",):
        return False, "previous_not_enriched"

    if not last_iso or not last_hash:
        return False, "no_baseline"

    try:
        last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return False, "bad_timestamp"

    age_days = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400.0
    if age_days > DEDUP_FRESH_DAYS:
        return False, "stale"

    new_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    if new_hash != last_hash:
        return False, "text_changed"

    return True, "fresh_unchanged"


def _parse_naukri_page_text(page_text: str) -> dict:
    """
    Parse structured Naukri page summary text for reliable CTC, location, notice period.
    Naukri format: "17y  ₹ 78 Lacs  Oman  1 Month"
    Also: "Current: Procurement Head at Jindal Shadeed..."
    Also: "Highest degree: MBA/PGDM Jindal Global Business School"
    """
    data = {}
    if not page_text:
        return data

    # CTC: "₹ 78 Lacs" or "₹ 1.5 Cr"
    ctc_m = re_module.search(r'₹\s*([\d.]+)\s*(Lacs?|Lakhs?|LPA|Cr|Crore)', page_text, re_module.IGNORECASE)
    if ctc_m:
        val = float(ctc_m.group(1))
        unit = ctc_m.group(2).lower()
        ctc = int(val * 10_000_000) if 'cr' in unit else int(val * 100_000)
        if 50_000 <= ctc <= 50_000_000:  # ₹50K – ₹5 Cr sanity window
            data['current_ctc'] = ctc

    # Expected CTC: "(expects: ₹ 50.80 Lacs)" or "expects ₹ 1 Cr"
    exp_m = re_module.search(r'expects?[:\s]*₹?\s*([\d.]+)\s*(Lacs?|Lakhs?|LPA|Cr|Crore)', page_text, re_module.IGNORECASE)
    if exp_m:
        val = float(exp_m.group(1))
        unit = exp_m.group(2).lower()
        ectc = int(val * 10_000_000) if 'cr' in unit else int(val * 100_000)
        if 50_000 <= ectc <= 50_000_000:
            data['expected_ctc'] = ectc

    # Notice period: "1 Month" or "2 Months" or "30 Days" or "Immediate" or "Serving Notice"
    notice_m = re_module.search(r'(\d+)\s*(Months?|Days?|Weeks?)', page_text, re_module.IGNORECASE)
    if notice_m:
        val = int(notice_m.group(1))
        unit = notice_m.group(2).lower()
        if 'month' in unit:
            data['notice_period'] = f"{val} Month{'s' if val != 1 else ''}"
            data['notice_period_days'] = val * 30
        elif 'day' in unit:
            data['notice_period'] = f"{val} Day{'s' if val != 1 else ''}"
            data['notice_period_days'] = val
        elif 'week' in unit:
            data['notice_period'] = f"{val} Week{'s' if val != 1 else ''}"
            data['notice_period_days'] = val * 7
    elif re_module.search(r'Immediate', page_text, re_module.IGNORECASE):
        data['notice_period'] = "Immediate"
        data['notice_period_days'] = 0
    elif re_module.search(r'Serving\s*Notice', page_text, re_module.IGNORECASE):
        data['notice_period'] = "Serving Notice"
        data['notice_period_days'] = 0

    # Location: after CTC and before notice, or "📍 [Location]"
    # Naukri format typically: "17y  ₹ 78 Lacs  Oman  1 Month"
    loc_m = re_module.search(r'(?:Current\s*location|Location|📍)\s*[:\-]?\s*([A-Za-z][A-Za-z\s,]+?)(?:\s*[\n|•\-]|\s*$)', page_text, re_module.IGNORECASE)
    if loc_m:
        loc = loc_m.group(1).strip().rstrip(',')
        if loc and len(loc) > 1 and len(loc) < 50:
            data['location'] = loc

    # Current designation: "Current: [Title] at [Company]"
    cur_m = re_module.search(r'Current\s*:\s*(.+?)\s+(?:at|@)\s+(.+?)(?:\s+since|\s*$|\n)', page_text, re_module.IGNORECASE)
    if cur_m:
        data['current_designation'] = cur_m.group(1).strip()
        data['current_employer'] = cur_m.group(2).strip()

    # Highest degree: "Highest degree: MBA/PGDM Jindal Global Business School, O.P Jindal..."
    deg_m = re_module.search(r'Highest\s*degree\s*:\s*(.+?)(?:\n|$)', page_text, re_module.IGNORECASE)
    if deg_m:
        data['highest_degree'] = deg_m.group(1).strip()

    if data:
        logger.info(f"[PageText] Parsed: {data}")
    return data



def _validate_work_experience(work_exp_list: list) -> bool:
    """Validate that work experience entries look legitimate (not education/garbage data)."""
    if not work_exp_list or not isinstance(work_exp_list, list):
        return False
    
    # Check first work experience entry for obvious red flags
    first_exp = work_exp_list[0] if work_exp_list else {}
    company = str(first_exp.get('company', '')).lower()
    designation = str(first_exp.get('designation', '')).lower()
    
    # RED FLAGS: Education data masquerading as work experience
    education_keywords = ['university', 'college', 'school', 'institute', 'academy', 'gita university', 'iit ', 'nit ', 'iim ']
    grade_patterns = ['gpa:', 'cgpa:', 'percentage:', '%', 'grade:', 'marks:', 'score:']
    
    # Fail if company name contains education keywords
    if any(keyword in company for keyword in education_keywords):
        logger.warning(f"[Quality Check] FAILED: Company '{company}' looks like education, not employer")
        return False
    
    # Fail if designation looks like a grade/score
    if any(pattern in designation for pattern in grade_patterns):
        logger.warning(f"[Quality Check] FAILED: Designation '{designation}' looks like a grade, not job title")
        return False
    
    # Fail if designation is just a number or percentage
    designation_clean = designation.replace('.', '').replace('%', '').replace(':', '').replace('gpa', '').strip()
    if designation_clean.isdigit() or (len(designation_clean) < 3 and '%' in designation):
        logger.warning(f"[Quality Check] FAILED: Designation '{designation}' is just a number/grade")
        return False
    
    # Fail if company is empty or suspiciously short
    if not company or len(company) < 2:
        logger.warning("[Quality Check] FAILED: Company name too short or empty")
        return False
    
    # Fail if designation is empty or suspiciously short  
    if not designation or len(designation) < 3:
        logger.warning("[Quality Check] FAILED: Designation too short or empty")
        return False
    
    return True


async def _background_full_groq_enrich(
    candidate_id: str,
    candidate_name: str,
    raw_text: str,
    recruiter_phone: str,
    recruiter_email: str,
    user_role: str = "",
    user_email: str = "",
):
    """
    FULL GROQ ENRICHMENT BLUEPRINT (Unconditional, like old "Full Haiku" process).
    
    No complex conditions, no targeted extraction — just send EVERYTHING to Groq Llama 3.3 70B.
    Reliable, fast ($0.59/M input + $0.79/M output), and deterministic (temp=0).
    
    This replicates the proven "Full Claude Haiku" approach that worked flawlessly.
    
    NEW: If user_email == admin@vhc.in → Routes to local LLM (Gemma 4) for testing
    """
    from pymongo import MongoClient
    from datetime import datetime, timezone
    
    # Check if admin user for local LLM testing
    use_local_llm = (user_email == TEST_LOCAL_LLM_EMAIL)
    
    if use_local_llm:
        logger.warning(f"[BG-Local-LLM] 🧪 ADMIN TEST: Using local Gemma 4 for {candidate_name}")
    else:
        logger.info(f"[BG-LLM] ⚡ Starting extraction for {candidate_name} (chain: RunPod Qwen → Emergent Haiku)")
    
    try:
        # Chain: Layer 1 = RunPod Qwen 14B (primary, self-hosted), Layer 2 = Emergent Haiku 4.5 (fallback)
        from services.llm_fallback_service import extract_full_profile_fallback
        extraction_result = await extract_full_profile_fallback(raw_text=raw_text, candidate_name=candidate_name)
        source_label = extraction_result.get("source", extraction_result.get("_extraction_source", "unknown"))
        
        if extraction_result and not extraction_result.get('error'):
            if use_local_llm:
                logger.warning(f"[BG-Local-LLM] ✅ Local Gemma 4 extraction succeeded for {candidate_name}")
            else:
                logger.info(f"[BG-LLM] ✅ extraction succeeded for {candidate_name} (served by: {source_label})")
            
            # CRITICAL FIX: Pass recruiter phone/email to _apply_bg_enrichment
            _apply_bg_enrichment(
                candidate_id, 
                candidate_name, 
                extraction_result, 
                raw_text, 
                recruiter_phone, 
                recruiter_email
            )
            
            # Update enrichment status
            from config import mongodb_uri as _mongo_uri, db_name as _db_name
            sync_client = MongoClient(_mongo_uri, tlsAllowInvalidCertificates=True)
            sync_db = sync_client[_db_name]
            
            sync_db.candidate_bank.update_one(
                {"id": candidate_id},
                {"$set": {
                    "enrichment_status": "enriched",
                    "ai_enriched_at": datetime.now(timezone.utc).isoformat(),
                    "ai_enrichment_source": source_label,
                    # Phase 52 (capture-dedup): store a hash of the raw text
                    # we just enriched so future identical captures of the
                    # same profile can short-circuit Qwen + embedding work.
                    "raw_text_hash": hashlib.sha256(
                        (raw_text or "").encode("utf-8")
                    ).hexdigest(),
                }}
            )
            
            # Generate smart tags from enriched profile
            try:
                from services.smart_tags_service import generate_smart_tags
                enriched_doc = sync_db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
                if enriched_doc:
                    smart_tags = generate_smart_tags(enriched_doc)
                    sync_db.candidate_bank.update_one(
                        {"id": candidate_id},
                        {"$set": {"smart_tags": smart_tags}}
                    )
                    logger.info(f"[SmartTags] Generated {len(smart_tags)} tags for {candidate_name}: {smart_tags[:5]}")
            except Exception as tag_err:
                logger.error(f"[SmartTags] Failed for {candidate_name}: {tag_err}")

            # Talent Graph — generate AI summary + 384-d embedding.
            # FIXED (OOM/Task-leak): we are already inside an async function
            # running on its own event loop (spawned by _fire_and_forget).
            # Previously this used asyncio.ensure_future() which caused the
            # background event-loop to close BEFORE the embedding task
            # finished → "Task was destroyed but it is pending!" + leaked
            # AsyncIOMotorClient sockets → OOM Exception Storm (May-05 13:04).
            # Solution: await the embedding INLINE + bound concurrency with
            # a threading-level semaphore so we never run > _EMBED_CONCURRENCY
            # encodes simultaneously across this gunicorn worker (multiple
            # _fire_and_forget threads).
            _embed_acquired = _EMBED_THREAD_SEMAPHORE.acquire(timeout=30)
            if not _embed_acquired:
                logger.warning(
                    f"[TalentGraph] Skip {candidate_name}: embed-queue full "
                    f"(>{_EMBED_CONCURRENCY} concurrent)"
                )
            else:
                try:
                    from motor.motor_asyncio import AsyncIOMotorClient
                    from services.talent_graph_service import upsert_candidate_embedding

                    _client = AsyncIOMotorClient(
                        _mongo_uri,
                        tlsAllowInvalidCertificates=True,
                        maxPoolSize=5,
                        serverSelectionTimeoutMS=5000,
                    )
                    try:
                        _adb = _client[_db_name]
                        doc = await _adb.candidate_bank.find_one(
                            {"id": candidate_id}, {"_id": 0}
                        )
                        if doc:
                            res = await upsert_candidate_embedding(_adb, doc)
                            logger.info(
                                f"[TalentGraph] {candidate_name}: {res.get('status')} "
                                f"(reason={res.get('reason', '-')})"
                            )
                    finally:
                        _client.close()
                except Exception as graph_err:
                    logger.error(f"[TalentGraph] Failed for {candidate_name}: {graph_err}")
                finally:
                    _EMBED_THREAD_SEMAPHORE.release()

            sync_client.close()
            
            if use_local_llm:
                logger.warning(f"[BG-Local-LLM] 🎯 COMPLETE: '{candidate_name}' enriched via Local Gemma 4")
            else:
                logger.warning(f"[BG-LLM] 🎯 COMPLETE: '{candidate_name}' fully enriched (source={source_label})")
        else:
            if use_local_llm:
                logger.error(f"[BG-Local-LLM] ❌ Local LLM failed for {candidate_name}: {extraction_result.get('error')}")
            else:
                logger.warning(f"[BG-LLM] ❌ extraction failed for {candidate_name}: {extraction_result.get('error')} (source={source_label})")
            
            # Update status to failed
            from config import mongodb_uri as _mongo_uri, db_name as _db_name
            sync_client = MongoClient(_mongo_uri, tlsAllowInvalidCertificates=True)
            sync_db = sync_client[_db_name]
            
            sync_db.candidate_bank.update_one(
                {"id": candidate_id},
                {"$set": {
                    "enrichment_status": "failed",
                    "ai_enrichment_source": "all_failed",
                    "ai_enrichment_error": str(extraction_result.get('error', 'Unknown error') if extraction_result else 'LLM returned None')[:500],
                    "ai_fallback_chain": (extraction_result or {}).get('_fallback_chain', []),
                }}
            )
            sync_client.close()
            
    except Exception as e:
        logger.error(f"[BG-Full-Groq] ⚠️ Exception enriching {candidate_name}: {e}")
        import traceback
        traceback.print_exc()
        
        # Mark enrichment as failed
        try:
            from config import mongodb_uri as _mongo_uri, db_name as _db_name
            sync_client = MongoClient(_mongo_uri, tlsAllowInvalidCertificates=True)
            sync_db = sync_client[_db_name]
            
            sync_db.candidate_bank.update_one(
                {"id": candidate_id},
                {"$set": {
                    "enrichment_status": "failed",
                    "ai_enrichment_source": "exception",
                    "ai_enrichment_error": str(e)[:500],
                }}
            )
            sync_client.close()
        except Exception:
            pass

    finally:
        # Phase 55.4 (2026-02-27): Force Python GC + glibc arena release.
        # Without this each enrichment leaks ~100-150 MB into secondary
        # arenas that MALLOC_TRIM_THRESHOLD_ cannot reclaim. Confirmed via
        # py-spy + /proc/$pid/status (VmData=4.4 GB on a single worker).
        _release_memory()


def _score_extraction_quality(ai_result: dict) -> float:
    """Score regex extraction quality: 0.0 to 1.0 based on key hiring fields.
    NOW INCLUDES VALIDATION: Returns 0.0 if work experience contains obvious garbage."""
    if not ai_result:
        return 0.0
    
    # CRITICAL: Validate work experience quality FIRST
    work_exp = ai_result.get('work_experience') or ai_result.get('experience')
    if work_exp and isinstance(work_exp, list) and len(work_exp) > 0:
        if not _validate_work_experience(work_exp):
            logger.warning("[Quality Score] Work experience validation FAILED — forcing Groq enrichment")
            return 0.0  # Force Claude enrichment by returning zero quality
    
    # ALSO validate current employer/designation
    current_employer = str(ai_result.get('current_employer', '')).lower()
    current_designation = str(ai_result.get('current_designation', '')).lower()
    
    education_keywords = ['university', 'college', 'school', 'institute', 'academy']
    grade_patterns = ['gpa:', 'cgpa:', '%', 'grade:']
    
    if any(keyword in current_employer for keyword in education_keywords):
        logger.warning(f"[Quality Score] Current employer '{current_employer}' looks like education — forcing Groq")
        return 0.0
    
    if any(pattern in current_designation for pattern in grade_patterns):
        logger.warning(f"[Quality Score] Current designation '{current_designation}' looks like grade — forcing Groq")
        return 0.0
    
    key_fields = [
        ('candidate_name', lambda v: bool(v and len(str(v)) > 2)),
        ('current_employer', lambda v: bool(v and len(str(v)) > 2)),
        ('current_designation', lambda v: bool(v and len(str(v)) > 2)),
        ('experience_years', lambda v: v is not None),
        ('key_skills', lambda v: isinstance(v, list) and len(v) >= 2),
        ('work_experience', lambda v: isinstance(v, list) and len(v) >= 1),
        ('current_ctc', lambda v: v is not None and v > 0),
        ('notice_period', lambda v: bool(v)),
        ('location', lambda v: bool(v and len(str(v)) > 1)),
        ('education', lambda v: isinstance(v, list) and len(v) >= 1),
    ]
    filled = sum(1 for field_name, check in key_fields if check(ai_result.get(field_name)))
    return filled / len(key_fields)


def _is_already_enriched(doc: dict) -> bool:
    """Check if a candidate profile already has good enrichment data."""
    if not doc:
        return False
    has_skills = isinstance(doc.get("key_skills"), list) and len(doc.get("key_skills", [])) >= 2
    has_work = isinstance(doc.get("work_experience"), list) and len(doc.get("work_experience", [])) >= 1
    has_employer = bool(doc.get("current_employer"))
    # Consider enriched if at least 2 of 3 key signals present
    return sum([has_skills, has_work, has_employer]) >= 2


# DELETED: _background_hybrid_enrich - replaced with Groq-only enrichment


async def _background_regex_enrich(
    candidate_id: str, candidate_name: str,
    raw_text: str, recruiter_phone: str, recruiter_email: str,
):
    """Background task: Regex-based enrichment (zero LLM credits).
    Replicates _background_groq_enrich using naukri_regex_parser."""
    import re as _re
    from pymongo import MongoClient
    try:
        from services.naukri_regex_parser import extract_full_profile_regex
        ai = extract_full_profile_regex(
            raw_text=raw_text,
            recruiter_phone=recruiter_phone,
            recruiter_email=recruiter_email,
        )
        if not ai:
            logger.warning(f"[BG-Regex] Extraction returned nothing for {candidate_name}")
            return
        logger.info(f"[BG-Regex] Enrichment succeeded for {candidate_name}")

        from config import mongodb_uri as _mongo_uri, db_name as _db_name
        sync_client = MongoClient(_mongo_uri, tlsAllowInvalidCertificates=True)
        sync_db = sync_client[_db_name]

        doc = sync_db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
        if not doc:
            logger.warning(f"[BG-Regex] Candidate {candidate_id[:12]} not found, skipping")
            sync_client.close()
            return

        updates = {}

        # Phone
        if not doc.get("phone") and ai.get("candidate_phone"):
            phone_digits = ai["candidate_phone"]
            recruiter_norm = _re.sub(r'[\s\-\+\(\)]', '', str(recruiter_phone or ''))[-10:]
            if phone_digits[-10:] != recruiter_norm:
                updates["phone"] = phone_digits
                updates["phone_normalized"] = phone_digits[-10:]

        # Email
        if not doc.get("email") and ai.get("candidate_email"):
            ai_email = ai["candidate_email"].lower().strip()
            blocked = ['@naukri.com', '@vhc.in', 'noreply@', 'support@']
            if not any(p in ai_email for p in blocked) and ai_email != (recruiter_email or "").lower():
                updates["email"] = ai_email

        # CTC / Salary (with ₹20 Cr cap)
        _CTC_MAX = 50_000_000
        if not doc.get("current_salary") and ai.get("current_ctc") and int(ai["current_ctc"]) <= _CTC_MAX:
            updates["current_salary"] = int(ai["current_ctc"])
        if not doc.get("expected_salary") and ai.get("expected_ctc") and int(ai["expected_ctc"]) <= _CTC_MAX:
            updates["expected_salary"] = int(ai["expected_ctc"])

        # Notice period
        if not doc.get("notice_period") and ai.get("notice_period"):
            updates["notice_period"] = ai["notice_period"]
        if not doc.get("notice_period_days") and ai.get("notice_period_days"):
            updates["notice_period_days"] = int(ai["notice_period_days"])

        # Professional fields
        if not doc.get("current_employer") and ai.get("current_employer"):
            updates["current_employer"] = ai["current_employer"]
        if not doc.get("designation") and ai.get("current_designation"):
            updates["designation"] = ai["current_designation"]
        if not doc.get("department") and ai.get("current_department"):
            updates["department"] = ai["current_department"]
        if not doc.get("industry") and ai.get("current_industry"):
            updates["industry"] = ai["current_industry"]
        if not doc.get("location") and ai.get("location"):
            updates["location"] = ai["location"]
        if not doc.get("headline") and ai.get("headline"):
            updates["headline"] = ai["headline"]
        if not doc.get("summary") and ai.get("profile_summary"):
            updates["summary"] = ai["profile_summary"]
        if not doc.get("experience_years") and ai.get("experience_years"):
            try:
                _exp = float(ai["experience_years"])
                if _exp <= 50:
                    updates["experience_years"] = round(_exp, 2)  # Preserve decimal (2.05)
            except (ValueError, TypeError):
                logger.warning(f"[BG-Apply] Invalid experience_years value: {ai.get('experience_years')}")

        # Skills
        if not doc.get("skills") and ai.get("key_skills"):
            updates["skills"] = _clean_skills(ai["key_skills"])

        # Work Experience
        if not doc.get("experience") and ai.get("work_experience"):
            work_exp = ai["work_experience"]
            if isinstance(work_exp, list) and len(work_exp) > 0:
                updates["experience"] = work_exp

        # Education
        if not doc.get("education") and ai.get("education"):
            education = ai["education"]
            if isinstance(education, list) and len(education) > 0:
                updates["education"] = education

        # Highest Qualification
        if not doc.get("highest_qualification") and ai.get("highest_qualification"):
            updates["highest_qualification"] = ai["highest_qualification"]

        # Personal Details
        personal_updates = {}
        existing_personal = doc.get("personal_details") or {}
        if not existing_personal.get("date_of_birth") and ai.get("date_of_birth"):
            personal_updates["date_of_birth"] = ai["date_of_birth"]
        if not existing_personal.get("gender") and ai.get("gender"):
            personal_updates["gender"] = ai["gender"]
        if not existing_personal.get("marital_status") and ai.get("marital_status"):
            personal_updates["marital_status"] = ai["marital_status"]
        if personal_updates:
            merged_personal = {**existing_personal, **personal_updates}
            updates["personal_details"] = merged_personal

        # Synthesize experience if missing
        final_experience = updates.get("experience") or doc.get("experience") or []
        if not final_experience:
            employer = updates.get("current_employer") or doc.get("current_employer") or ai.get("current_employer")
            designation = updates.get("designation") or doc.get("designation") or ai.get("current_designation")
            if employer:
                updates["experience"] = [{
                    "company": employer, "designation": designation,
                    "is_current": True, "from_date": None, "to_date": "Present",
                    "duration": None, "location": updates.get("location") or doc.get("location"),
                    "description": None, "industry": updates.get("industry") or doc.get("industry"),
                }]

        if updates:
            updates["ai_enriched_at"] = datetime.now(timezone.utc).isoformat()
            updates["ai_enrichment_source"] = "regex_zero_cost"
            sync_db.candidate_bank.update_one({"id": candidate_id}, {"$set": updates})
            logger.warning(
                f"[BG-Regex] Enriched {candidate_name} ({candidate_id[:12]}): "
                f"{list(updates.keys())}"
            )
        else:
            logger.info(f"[BG-Regex] No new fields to enrich for {candidate_name}")

        sync_client.close()

    except Exception as e:
        logger.error(f"[BG-Regex] Error enriching {candidate_name}: {e}")



def _apply_bg_enrichment(candidate_id: str, candidate_name: str, ai: dict,
                          raw_text: str, recruiter_phone: str, recruiter_email: str):
    """Apply extracted data (from spaCy or Groq) to candidate record. Sync pymongo."""
    import re as _re
    from pymongo import MongoClient
    from config import mongodb_uri as _mongo_uri, db_name as _db_name

    try:
        sync_client = MongoClient(_mongo_uri, tlsAllowInvalidCertificates=True)
        sync_db = sync_client[_db_name]

        doc = sync_db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
        if not doc:
            logger.warning(f"[BG-Apply] Candidate {candidate_id[:12]} not found")
            sync_client.close()
            return

        # ── Regex safety-net backfill ──
        # Before applying LLM output, run the full Naukri regex parser on raw_text
        # and fill any null/missing structured fields. This guarantees top-card
        # consistency (experience, CTC, notice period, location) regardless of
        # which LLM handled the extraction or whether it returned nulls.
        try:
            from services.naukri_regex_parser import extract_full_profile_regex as _full_regex
            _rx = _full_regex(raw_text, recruiter_phone, recruiter_email) or {}
            for _k_rx, _k_ai in [
                ("experience_years", "experience_years"),
                ("current_ctc", "current_ctc"),
                ("expected_ctc", "expected_ctc"),
                ("notice_period", "notice_period"),
                ("notice_period_days", "notice_period_days"),
                ("location", "location"),
                ("current_employer", "current_employer"),
                ("current_designation", "current_designation"),
                ("key_skills", "key_skills"),
            ]:
                _rx_val = _rx.get(_k_rx)
                if _rx_val in (None, "", [], 0):
                    continue
                if ai.get(_k_ai) in (None, "", [], 0):
                    ai[_k_ai] = _rx_val
                    logger.info(f"[BG-Apply] Regex-backfill {_k_ai} <- {_rx_val!r} for {candidate_name}")
        except Exception as _rx_err:
            logger.warning(f"[BG-Apply] Regex backfill failed: {_rx_err}")

        updates = {}
        source = ai.get("_extraction_source", "unknown")

        # Skills
        if ai.get("key_skills"):
            updates["skills"] = _clean_skills(ai["key_skills"])

        # Work Experience - VALIDATE before saving
        if ai.get("work_experience") and isinstance(ai["work_experience"], list):
            if _validate_work_experience(ai["work_experience"]):
                updates["experience"] = ai["work_experience"]
            else:
                logger.warning(f"[BG-Apply] Work experience validation FAILED for {candidate_name} — skipping save")

        # Education - Clean "Not Available" values before saving
        if ai.get("education") and isinstance(ai["education"], list) and len(ai["education"]) > 0:
            # Clean education data - replace "Not Available" strings with None
            cleaned_education = []
            for edu in ai["education"]:
                if isinstance(edu, dict):
                    # Skip if ALL fields are "Not Available"
                    all_not_available = all(
                        v == "Not Available" or v is None 
                        for k, v in edu.items() 
                        if k in ['degree', 'institution', 'year_of_passing', 'score']
                    )
                    if all_not_available:
                        logger.warning("[BG-Apply] Skipping education entry with all 'Not Available' values")
                        continue
                    
                    # Replace "Not Available" with None for cleaner storage
                    cleaned_edu = {}
                    for key, value in edu.items():
                        if value == "Not Available":
                            cleaned_edu[key] = None
                        else:
                            cleaned_edu[key] = value
                    cleaned_education.append(cleaned_edu)
            
            if cleaned_education:
                updates["education"] = cleaned_education
                logger.info(f"[BG-Apply] Saving {len(cleaned_education)} education entries for {candidate_name}")
            else:
                logger.warning(f"[BG-Apply] No valid education data to save for {candidate_name}")

        # Profile summary
        if ai.get("profile_summary"):
            updates["summary"] = ai["profile_summary"]

        # Certifications
        if ai.get("certifications"):
            updates["certifications"] = ai["certifications"]

        # Languages
        if ai.get("languages"):
            updates["languages"] = ai["languages"]

        # Professional fields (only if present)
        for ai_key, db_key in [
            ("current_employer", "current_employer"),
            ("current_designation", "designation"),
            ("current_department", "department"),
            ("current_industry", "industry"),
            ("headline", "headline"),
        ]:
            if ai.get(ai_key):
                updates[db_key] = ai[ai_key]

        if ai.get("location") and "agnostic" not in str(ai["location"]).lower():
            updates["location"] = ai["location"]

        # CTC / Salary (only fill if DB record is missing, with ₹20 Cr cap)
        _CTC_MAX = 50_000_000
        if not doc.get("current_salary") and ai.get("current_ctc") and int(ai["current_ctc"]) <= _CTC_MAX:
            updates["current_salary"] = int(ai["current_ctc"])
        if not doc.get("expected_salary") and ai.get("expected_ctc") and int(ai["expected_ctc"]) <= _CTC_MAX:
            updates["expected_salary"] = int(ai["expected_ctc"])

        # Notice period
        if not doc.get("notice_period") and ai.get("notice_period"):
            updates["notice_period"] = ai["notice_period"]
        if not doc.get("notice_period_days") and ai.get("notice_period_days"):
            updates["notice_period_days"] = int(ai["notice_period_days"])

        # Experience years — fill if DB missing or 0 (guard against "0y" display bug)
        _exp_db = doc.get("experience_years") or doc.get("total_experience_years") or 0
        _exp_ai = ai.get("experience_years")
        try:
            _exp_ai_f = float(_exp_ai) if _exp_ai is not None else None
        except (TypeError, ValueError):
            _exp_ai_f = None
        if (_exp_db in (0, 0.0, None)) and _exp_ai_f and 0 < _exp_ai_f <= 50:
            updates["experience_years"] = _exp_ai_f
            updates["total_experience_years"] = _exp_ai_f

        if updates:
            updates["ai_enriched_at"] = datetime.now(timezone.utc).isoformat()
            updates["ai_enrichment_source"] = source
            if ai.get("_confidence"):
                updates["ai_confidence_score"] = ai["_confidence"]
            sync_db.candidate_bank.update_one({"id": candidate_id}, {"$set": updates})
            logger.info(f"[BG-Apply] Enriched {candidate_name} via {source}: {list(updates.keys())}")
        else:
            logger.info(f"[BG-Apply] No fields to update for {candidate_name}")

        # Admin debug trace (fire-and-forget, sync path)
        try:
            from routes.extraction_trace import record_trace_sync as _trace
            _trace(
                endpoint="bg-enrichment",
                candidate_name=candidate_name,
                raw_text=raw_text or "",
                regex_output=_rx if "_rx" in dir() else None,
                llm_output=ai,
                merged_output={**(doc or {}), **updates},
                llm_source=source,
                user_email=recruiter_email,
            )
        except Exception:
            pass

        sync_client.close()
    except Exception as e:
        logger.error(f"[BG-Apply] Error for {candidate_name}: {e}")



def _store_enrichment_cache(text_hash: str, enrichment_data: dict, source: str):
    """Store enrichment result in llm_enrichment_cache for future cache hits."""
    try:
        from pymongo import MongoClient
        from config import mongodb_uri as _mongo_uri, db_name as _db_name
        _c = MongoClient(_mongo_uri, tlsAllowInvalidCertificates=True)
        _d = _c[_db_name]
        # Strip internal keys before caching
        cache_data = {k: v for k, v in enrichment_data.items() if not k.startswith("_")}
        model_used = "groq" if USE_GROQ_ENRICHMENT else "claude"
        _d.llm_enrichment_cache.update_one(
            {"text_hash": text_hash},
            {"$set": {
                "text_hash": text_hash,
                "enrichment_data": cache_data,
                "source": source,
                "model": model_used,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        _c.close()
        logger.info(f"[BG-Cache] Stored enrichment cache (hash={text_hash[:12]}, source={source}, model={model_used})")
    except Exception as e:
        logger.warning(f"[BG-Cache] Failed to store cache: {e}")


async def _background_targeted_enrich(
    candidate_id: str, candidate_name: str,
    raw_text: str, recruiter_phone: str, recruiter_email: str,
    user_role: str = "", user_email: str = "",
):
    """
    COST-OPTIMIZED Background enrichment: Groq ONLY for phone + work experience.
    Regex extracts: company, designation, CTC, skills (zero cost).
    Target: 11M tokens/day → 3M tokens/day = $720/month savings.
    """
    import re as _re
    from pymongo import MongoClient
    from datetime import datetime, timezone
    
    logger.info(f"[BG-Targeted] Starting cost-optimized enrichment for {candidate_name}")
    
    try:
        # Step 1: Extract basic fields via REGEX (zero cost)
        from services.naukri_regex_parser import extract_full_profile_regex
        regex_data = extract_full_profile_regex(raw_text, recruiter_phone, recruiter_email)
        
        logger.info(f"[BG-Targeted] Regex extracted: company={regex_data.get('current_employer')}, "
                   f"designation={regex_data.get('current_designation')}, "
                   f"CTC={regex_data.get('current_ctc')}, "
                   f"skills={len(regex_data.get('skills', []))}")
        
        logger.info("[BG-Targeted] Using GROQ (Llama 3.3 70B for extraction...")
        llm_data = await extract_phone_and_work_experience_groq(raw_text, candidate_name)
        
        logger.info(f"[BG-Targeted] LLM extracted: phone={'found' if llm_data.get('phone') else 'not found'}, "
                   f"work_exp={len(llm_data.get('work_experience', []))} entries")
        
        # Step 3: MERGE results (regex for most fields + Groq for phone/work_exp)
        # CRITICAL: Validate employer/designation from regex before using
        education_keywords = ['university', 'college', 'school', 'institute', 'academy']
        grade_patterns = ['gpa:', 'cgpa:', '%', 'grade:']
        
        _employer = str(regex_data.get("current_employer", "")).lower()
        _designation = str(regex_data.get("current_designation", "")).lower()
        _employer_valid = not any(kw in _employer for kw in education_keywords) if _employer else False
        _designation_valid = not any(pat in _designation for pat in grade_patterns) if _designation else False
        
        merged = {
            # From regex (zero cost)
            "name": regex_data.get("name") or candidate_name,
            "email": regex_data.get("email"),
            "candidate_email": regex_data.get("email"),
            "candidate_phone": llm_data.get("phone"),  # From LLM (Groq)
            "current_employer": regex_data.get("current_employer") if _employer_valid else None,
            "current_designation": regex_data.get("current_designation") if _designation_valid else None,
            "current_ctc": regex_data.get("current_ctc"),
            "expected_ctc": regex_data.get("expected_ctc"),
            "notice_period": regex_data.get("notice_period"),
            "location": regex_data.get("location"),
            "experience_years": regex_data.get("experience_years"),
            "skills": regex_data.get("skills", []),
            "education": regex_data.get("education", []),
            "experience": llm_data.get("work_experience", []),  # From LLM (Groq)
            "_extraction_source": f"targeted_regex_plus_{'groq' if USE_GROQ_ENRICHMENT else 'claude'}",
            "_tokens_saved": "~8000 (vs full Groq)" if not USE_GROQ_ENRICHMENT else "~10500 (Groq ultra-fast)",
        }
        
        # Step 4: Apply enrichment to database
        _apply_bg_enrichment(candidate_id, candidate_name, merged, raw_text, recruiter_phone, recruiter_email)
        
        logger.info(f"[BG-Targeted] ✅ Enrichment complete for {candidate_name} | "
                   f"Token usage: ~3000 (vs ~11000 full Groq) = 65% savings")
        
    except Exception as e:
        logger.error(f"[BG-Targeted] Error for {candidate_name}: {e}")
        # Fallback to regex-only if targeted enrichment fails
        try:
            from services.naukri_regex_parser import extract_full_profile_regex
            regex_fallback = extract_full_profile_regex(raw_text, recruiter_phone, recruiter_email)
            regex_fallback["_extraction_source"] = "regex_only_after_targeted_failure"
            _apply_bg_enrichment(candidate_id, candidate_name, regex_fallback, raw_text, recruiter_phone, recruiter_email)
            logger.warning(f"[BG-Targeted] Fallback to regex-only for {candidate_name}")
        except Exception as fallback_err:
            logger.error(f"[BG-Targeted] Fallback also failed for {candidate_name}: {fallback_err}")


async def capture_raw_fallback(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Fallback capture endpoint that accepts raw JSON.
    Logs validation failures to naukri_capture_logs so they appear in Failed Captures.
    The extension should call /capture first, then /capture-raw on 422 errors.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        raw = await request.json()
    except Exception:
        return {"success": False, "message": "Invalid JSON"}

    name = raw.get("name", "Unknown")
    email = raw.get("email", "")
    phone = raw.get("phone", "")
    profile_url = raw.get("naukri_url", "") or raw.get("profile_url", "")

    # Try to parse with the model to get the real error
    try:
        CompleteNaukriProfileInput(**raw)
        # If parsing succeeded, forward to the real capture endpoint
        return await capture_profile(CompleteNaukriProfileInput(**raw), current_user)
    except Exception as validation_err:
        error_msg = str(validation_err)[:500]
        logger.warning(f"[CaptureRaw] Validation failed for {name}: {error_msg}")

        doc = {
            "id": str(uuid.uuid4()),
            "timestamp": now,
            "profile_id": raw.get("naukri_id", ""),
            "profile_url": profile_url,
            "candidate_name": name,
            "candidate_email": email,
            "candidate_phone": phone,
            "status": "failed",
            "action": "validation_error",
            "candidate_id": "",
            "failure_reason": f"Validation error: {error_msg}",
            "failed_step": "pydantic_validation",
            "data_missing_fields": [],
            "captured_to_bank": False,
            "is_recovered": False,
            "retry_count": 0,
            "capture_duration_ms": 0,
            "source": "naukri_extension",
            "captured_by": current_user.get("id", ""),
            "captured_by_name": current_user.get("name", ""),
            "raw_data": raw,
        }
        await db.naukri_capture_logs.insert_one(doc)
        return {"success": False, "action": "validation_error", "candidate_id": "", "message": f"Capture failed (logged): {error_msg[:200]}"}


@extension_router.post("/capture", response_model=CaptureResponse)
async def capture_profile(
    profile: CompleteNaukriProfileInput,
    current_user: dict = Depends(get_current_user),
    _mem: None = Depends(_force_memory_release_after_response),
):
    """
    Capture and save/update a COMPLETE Naukri profile.
    Stores ALL available data for 1:1 profile matching.
    """
    import re as re_module
    import time as _time
    capture_start = _time.time()
    now = datetime.now(timezone.utc).isoformat()
    
    # === DATA VALIDATION & CLEANING ===
    
    # Clean name: strip experience years, designations, noise
    if profile.name:
        # Remove patterns like " - 15 Year(s)", " - 3.5 Year(s)", " 15 Year(s)"
        profile.name = re_module.sub(r'\s*[-–]\s*\d+[\.\d]*\s*Year\(?s?\)?\s*$', '', profile.name, flags=re_module.IGNORECASE).strip()
        # Remove trailing designations that got appended
        profile.name = re_module.sub(r'\s*[-–]\s*(Senior|Junior|Lead|Manager|Director|Engineer|Developer|Architect|Consultant|Analyst).*$', '', profile.name, flags=re_module.IGNORECASE).strip()
    
    # Reject clearly fake/invalid names
    invalid_names = [
        'search candidates', 'decode india', 'profiles found', 'naukri.com',
        'similar profiles', 'save for later', 'download', 'login', 'sign up',
        'resdex', 'home', 'jobs', 'reports', 'my naukri', 'for employers',
        'search results', 'view contact', 'prev', 'next', 'page', 'back',
        'ai matched', 'recommended', 'shortlisted', 'saved', 'applied',
        'no results', 'loading', 'filter', 'sort by', 'relevance',
        'application received', 'mailer response', 'bulk email',
        'candidate database', 'talent pool', 'job posting',
    ]
    if profile.name and profile.name.lower().strip() in invalid_names:
        await _log_capture(profile, current_user, "failed", "rejected", "", f"Invalid name: '{profile.name}'", "validation", capture_start)
        return CaptureResponse(
            success=False, action="rejected", candidate_id="",
            message=f"Rejected: '{profile.name}' is not a valid candidate name"
        )
    
    # Also reject names that look like navigation text or Naukri system content
    if profile.name:
        name_lower = profile.name.lower().strip()
        # Reject if name contains obvious system/nav patterns
        nav_patterns = [
            r'^(search|filter|sort|page|next|prev|back|home|report|login)\b',
            r'\b(candidates found|profiles found|results|no result)',
            r'\b(naukri|resdex|foundit|monster)\b',
            r'^\d+\s*(candidates|profiles|results)',
            r'^(showing|displaying|filtered)\s+\d+',
            r'^(view all|see more|show more|load more)',
            r'^\(\d+\)\s',  # Browser tab titles like "(3) Feed", "(2) Messages"
            r'^(feed|messages|notifications|my network|linkedin|home)\s*$',  # LinkedIn page names
        ]
        for pattern in nav_patterns:
            if re_module.search(pattern, name_lower):
                await _log_capture(profile, current_user, "failed", "rejected", "", f"Nav-text name: '{profile.name}'", "validation", capture_start)
                return CaptureResponse(
                    success=False, action="rejected", candidate_id="",
                    message=f"Rejected: '{profile.name}' appears to be navigation text, not a candidate name"
                )
    
    # Reject names that are too short (< 2 chars) or too long (> 80 chars)
    if not profile.name or len(profile.name.strip()) < 2 or len(profile.name.strip()) > 80:
        await _log_capture(profile, current_user, "failed", "rejected", "", f"Name length invalid: '{profile.name}'", "validation", capture_start)
        return CaptureResponse(
            success=False, action="rejected", candidate_id="",
            message="Rejected: Invalid candidate name"
        )
    
    # Clean email: reject naukri/placeholder/support emails AND logged-in user's email
    if profile.email:
        email_lower = profile.email.lower().strip()
        # Reject known bad patterns AND company domain emails
        if any(pattern in email_lower for pattern in [
            '@naukri.com', '@placeholder', '@example.com', '@test.com',
            'noreply@', 'support@', 'info@naukri', 'donotreply@', '@vhc.in'
        ]):
            logger.warning(f"[Extension] Blocked system/company email: {profile.email} for {profile.name}")
            profile.email = None
        # Reject if it matches the logged-in user's email (recruiter's email, not candidate's)
        elif current_user.get("email") and email_lower == current_user["email"].lower().strip():
            logger.warning(f"[Extension] Stripped recruiter's own email ({profile.email}) from capture for {profile.name}")
            profile.email = None
    
    # Clean phone: reject recruiter's own phone number
    # Helper to normalize phone for comparison (strip spaces, dashes, country codes, take last 10 digits)
    def _normalize_phone_for_compare(p):
        return re_module.sub(r'[\s\-\+\(\)]', '', str(p or ''))[-10:]
    
    if profile.phone:
        recruiter_phone_from_user = current_user.get("phone", "")
        if recruiter_phone_from_user:
            # Compare normalized versions
            if _normalize_phone_for_compare(profile.phone) == _normalize_phone_for_compare(recruiter_phone_from_user):
                logger.warning(f"[Extension] Stripped recruiter's own phone ({profile.phone}) from capture for {profile.name}")
                profile.phone = None
        # Also check against recruiter_phone sent from extension
        if profile.phone and profile.recruiter_phone:
            if _normalize_phone_for_compare(profile.phone) == _normalize_phone_for_compare(profile.recruiter_phone):
                logger.warning(f"[Extension] Stripped recruiter phone (from extension creds) from capture for {profile.name}")
                profile.phone = None
    
    # Update first/last name from cleaned name
    if profile.name:
        name_parts = profile.name.strip().split()
        profile.first_name = name_parts[0] if name_parts else None
        profile.last_name = name_parts[-1] if len(name_parts) > 1 else None
    
    # ═══ SMART FULL EXTRACTION (Groq for gap-filling) ═══
    # Prepare raw text for background AI enrichment (runs AFTER response is sent)
    raw_for_ai = profile.raw_profile_text or ""
    if not raw_for_ai and hasattr(profile, 'raw_sections') and profile.raw_sections:
        raw_for_ai = "\n".join(f"{k}: {v}" for k, v in profile.raw_sections.items() if v)
    # Combine CV text with page_text for richer extraction
    ai_enrichment_combined = raw_for_ai if len(raw_for_ai) > 100 else ""
    if profile.page_text:
        ai_enrichment_combined += "\n\n=== NAUKRI PAGE TEXT ===\n" + profile.page_text
    if len(ai_enrichment_combined) < 100:
        ai_enrichment_combined = ""
    
    # FIX: If extension doesn't send raw text, build it from structured data
    if not ai_enrichment_combined and profile.name:
        logger.info(
            f"[Extension] No raw text from extension for '{profile.name}' — building from structured data"
        )
        parts = []
        if profile.name:
            parts.append(f"Name: {profile.name}")
        if profile.email:
            parts.append(f"Email: {profile.email}")
        if profile.phone:
            parts.append(f"Phone: {profile.phone}")
        if profile.headline:
            parts.append(f"Headline: {profile.headline}")
        if profile.profile_summary:
            parts.append(f"Summary: {profile.profile_summary}")
        if profile.current_company:
            parts.append(f"Current Company: {profile.current_company}")
        if profile.current_designation:
            parts.append(f"Current Designation: {profile.current_designation}")
        if profile.work_experience:
            parts.append("\nWork Experience:")
            for exp in profile.work_experience[:5]:
                if hasattr(exp, 'company') and hasattr(exp, 'designation'):
                    parts.append(f"- {exp.designation} at {exp.company}")
        if profile.key_skills:
            parts.append(f"\nSkills: {', '.join(profile.key_skills[:10])}")
        ai_enrichment_combined = "\n".join(parts)
        logger.info(
            f"[Extension] Built enrichment text: {len(ai_enrichment_combined)} chars from structured data"
        )
    
    ai_recruiter_phone = profile.recruiter_phone or current_user.get("phone")
    ai_recruiter_email = current_user.get("email")

    # ═══ FULL INLINE REGEX EXTRACTION (FREE, instant — fills ALL fields) ═══
    # Runs the battle-tested naukri_regex_parser (168 tests) to populate skills,
    # work experience, education, CTC, notice period, location, employer, etc.
    # This eliminates the need for background Claude enrichment in 80%+ of captures.
    _raw_text_for_regex = raw_for_ai or ""
    if profile.page_text:
        _raw_text_for_regex += "\n" + profile.page_text

    career_prefs = profile.career_preferences
    if not career_prefs:
        from models.extension import CareerPreferencesInput
        career_prefs = CareerPreferencesInput()
        profile.career_preferences = career_prefs

    _inline_regex_quality = 0.0  # Track quality for background enrichment decision

    # ── Step 1: Parse Naukri page_text for structured data (CTC, location, notice) ──
    # The page_text has reliable structured data like "₹ 78 Lacs  Oman  1 Month"
    _page_data = _parse_naukri_page_text(profile.page_text) if profile.page_text else {}

    if _raw_text_for_regex and len(_raw_text_for_regex) > 100:
        try:
            from services.naukri_regex_parser import extract_full_profile_regex
            _regex_result = extract_full_profile_regex(
                raw_text=_raw_text_for_regex,
                recruiter_phone=profile.recruiter_phone or current_user.get("phone", ""),
                recruiter_email=current_user.get("email", ""),
            )
            if _regex_result:
                _rx_quality = _score_extraction_quality(_regex_result)
                _inline_regex_quality = _rx_quality  # Persist for background enrichment decision

                # Fill CTC / Expected CTC / Notice Period / Location from regex
                if not career_prefs.current_salary and _regex_result.get("current_ctc"):
                    career_prefs.current_salary = int(_regex_result["current_ctc"])
                    logger.info(f"[Capture-Regex] CTC={career_prefs.current_salary} for {profile.name}")
                if not career_prefs.expected_salary and _regex_result.get("expected_ctc"):
                    career_prefs.expected_salary = int(_regex_result["expected_ctc"])
                if not career_prefs.notice_period and _regex_result.get("notice_period"):
                    career_prefs.notice_period = _regex_result["notice_period"]
                if not career_prefs.current_location and _regex_result.get("location"):
                    career_prefs.current_location = _regex_result["location"]

                # Fill employer, designation, department, industry from regex (if extension didn't capture them)
                # CRITICAL: Validate employer/designation before saving
                education_keywords = ['university', 'college', 'school', 'institute', 'academy']
                grade_patterns = ['gpa:', 'cgpa:', '%', 'grade:']
                
                _employer = _regex_result.get("current_employer", "").lower()
                _designation = _regex_result.get("current_designation", "").lower()
                _employer_valid = not any(kw in _employer for kw in education_keywords)
                _designation_valid = not any(pat in _designation for pat in grade_patterns)
                
                if not profile.current_company and _regex_result.get("current_employer") and _employer_valid:
                    profile.current_company = _regex_result["current_employer"]
                elif not _employer_valid and _regex_result.get("current_employer"):
                    logger.warning(f"[Capture-Regex] REJECTED current_employer '{_regex_result.get('current_employer')}' — contains education keyword")
                
                if not profile.current_designation and _regex_result.get("current_designation") and _designation_valid:
                    profile.current_designation = _regex_result["current_designation"]
                elif not _designation_valid and _regex_result.get("current_designation"):
                    logger.warning(f"[Capture-Regex] REJECTED current_designation '{_regex_result.get('current_designation')}' — contains grade pattern")
                
                if not profile.current_department and _regex_result.get("current_department"):
                    profile.current_department = _regex_result["current_department"]
                if not profile.current_industry and _regex_result.get("current_industry"):
                    profile.current_industry = _regex_result["current_industry"]

                # Fill skills from regex (if extension didn't capture them)
                if (not profile.key_skills or len(profile.key_skills) < 2) and _regex_result.get("key_skills"):
                    profile.key_skills = _regex_result["key_skills"]
                    logger.info(f"[Capture-Regex] Skills={len(profile.key_skills)} for {profile.name}")

                # Fill work experience from regex (if extension didn't capture them)
                if (not profile.work_experience or len(profile.work_experience) < 1) and _regex_result.get("work_experience"):
                    # CRITICAL: Validate work experience BEFORE saving to profile
                    if _validate_work_experience(_regex_result.get("work_experience")):
                        from models.extension import WorkExperienceInput
                        profile.work_experience = []
                        for we in _regex_result["work_experience"]:
                            if isinstance(we, dict):
                                profile.work_experience.append(WorkExperienceInput(
                                    company=we.get("company"),
                                    designation=we.get("designation"),
                                    from_date=we.get("from_date"),
                                    to_date=we.get("to_date"),
                                    duration=we.get("duration"),
                                    is_current=we.get("is_current", False),
                                    location=we.get("location"),
                                    description=we.get("description"),
                                ))
                        logger.info(f"[Capture-Regex] Work Experience={len(profile.work_experience)} for {profile.name}")
                    else:
                        logger.warning(f"[Capture-Regex] Work experience validation FAILED for {profile.name} — will trigger targeted enrichment")

                # Fill education from regex (if extension didn't capture them)
                if (not profile.education or len(profile.education) < 1) and _regex_result.get("education"):
                    from models.extension import EducationInput
                    profile.education = []
                    for ed in _regex_result["education"]:
                        if isinstance(ed, dict):
                            profile.education.append(EducationInput(
                                degree=ed.get("degree"),
                                specialization=ed.get("specialization"),
                                institution=ed.get("institution"),
                                year=ed.get("year"),
                            ))
                    logger.info(f"[Capture-Regex] Education={len(profile.education)} for {profile.name}")

                # Fill summary/headline from regex
                if not profile.profile_summary and _regex_result.get("profile_summary"):
                    profile.profile_summary = _regex_result["profile_summary"]
                if not profile.headline and _regex_result.get("headline"):
                    profile.headline = _regex_result["headline"]

                # Fill experience years from regex
                if not profile.total_experience_years and _regex_result.get("experience_years"):
                    profile.total_experience_years = _regex_result["experience_years"]

                # Phone fallback: Naukri DOM masks phone number.
                # Extract phone from CV/page text via regex when DOM didn't provide it.
                if not profile.phone and _regex_result.get("candidate_phone"):
                    profile.phone = _regex_result["candidate_phone"]
                    logger.info(f"[Capture-Regex] Phone={profile.phone} for {profile.name}")

                # Email fallback: grab from regex if DOM didn't provide it
                if not profile.email and _regex_result.get("candidate_email"):
                    _rx_email = _regex_result["candidate_email"].lower().strip()
                    _blocked_patterns = ['@naukri.com', '@vhc.in', 'noreply@', 'support@', '@placeholder', '@example.com']
                    if not any(p in _rx_email for p in _blocked_patterns):
                        profile.email = _rx_email
                        logger.info(f"[Capture-Regex] Email from regex: {profile.email} for {profile.name}")

                logger.warning(f"[Capture-Regex] ENRICHED inline: {profile.name} | quality={_rx_quality:.0%} | "
                              f"skills={len(profile.key_skills or [])} exp={len(profile.work_experience or [])} "
                              f"edu={len(profile.education or [])} ctc={career_prefs.current_salary}")
        except Exception as regex_err:
            logger.warning(f"[Capture-Regex] Failed for {profile.name}: {regex_err}")

    # ── Step 3: page_text overrides for CTC, location, notice ──
    # page_text has the most reliable structured data from Naukri
    # Override regex values when page_text provides better data
    if _page_data:
        if _page_data.get('current_ctc'):
            career_prefs.current_salary = _page_data['current_ctc']
            logger.info(f"[PageText] CTC override: {career_prefs.current_salary} for {profile.name}")
        if _page_data.get('expected_ctc'):
            career_prefs.expected_salary = _page_data['expected_ctc']
        if _page_data.get('notice_period'):
            career_prefs.notice_period = _page_data['notice_period']
            if _page_data.get('notice_period_days') is not None:
                career_prefs.notice_period_days = _page_data['notice_period_days']
        if _page_data.get('location'):
            career_prefs.current_location = _page_data['location']
        if _page_data.get('current_designation') and not profile.current_designation:
            profile.current_designation = _page_data['current_designation']
        if _page_data.get('current_employer') and not profile.current_company:
            profile.current_company = _page_data['current_employer']
    
    
    # ═══ SANITIZE: Reject garbage mislabeled as professional fields ═══
    if profile.current_company and _is_garbage_employer(profile.current_company):
        logger.warning(f"[Sanitize] Rejected garbage employer '{profile.current_company[:60]}' for {profile.name}")
        profile.current_company = None
    if profile.current_designation and _is_garbage_designation(profile.current_designation):
        logger.warning(f"[Sanitize] Rejected garbage designation '{profile.current_designation[:60]}' for {profile.name}")
        profile.current_designation = None

    # ═══ SANITIZE: Notice period sanity cap ═══
    # Max reasonable notice period is 365 days (1 year). Anything above is data entry error.
    if career_prefs.notice_period_days and career_prefs.notice_period_days > 365:
        logger.warning(f"[Sanitize] Absurd notice_period_days={career_prefs.notice_period_days} for {profile.name} — capping/rejecting")
        career_prefs.notice_period_days = None
        career_prefs.notice_period = None

    # ═══ SANITIZE: Experience years sanity cap ═══
    # Max realistic experience is 50 years. Catches header parsing bugs.
    if profile.total_experience_years is not None and profile.total_experience_years > 50:
        logger.warning(f"[Sanitize] Absurd experience_years={profile.total_experience_years} for {profile.name} — rejecting")
        profile.total_experience_years = None

    # ═══ SANITIZE: Profile summary quality check ═══
    # Reject raw page dumps stored as summary (contains keyword lists, section headers, etc.)
    if profile.profile_summary:
        _summ = profile.profile_summary.strip()
        _summ_lower = _summ.lower()
        _is_garbage_summary = (
            len(_summ) > 1000 or  # Real summaries are < 500 chars
            'key skills' in _summ_lower or
            'work experience' in _summ_lower[:100] or
            'view it skills' in _summ_lower or
            'may also know' in _summ_lower or
            'other personal details' in _summ_lower or
            'languages known' in _summ_lower or
            _summ_lower.count('•') > 10 or  # Bullet-heavy raw dumps
            _summ_lower.startswith('sap &') or  # Skills list as summary
            'till date' in _summ_lower[:200]  # Work experience fragment
        )
        if _is_garbage_summary:
            logger.warning(f"[Sanitize] Rejected garbage summary ({len(_summ)} chars) for {profile.name}")
            profile.profile_summary = None

    # ═══ DEDUP CHECKS ═══
    # Check for existing profile by naukri_profile_id (strongest match — same Naukri profile)
    # CRITICAL: Skip lookup when naukri_profile_id is None/empty to prevent overwriting unrelated records
    existing = None
    if profile.naukri_profile_id:
        existing = await db.candidate_bank.find_one(
            {"naukri_profile_id": profile.naukri_profile_id},
            {"_id": 0}
        )
        if existing:
            # SAFETY: If naukri_profile_id matched but names are completely different,
            # this is a different person (e.g. stale/shared session ID). Do NOT overwrite.
            if not _names_are_similar(profile.name, existing.get("name", "")):
                logger.warning(
                    f"[Extension] BLOCKED OVERWRITE: naukri_id match but names differ! "
                    f"Incoming='{profile.name}' vs Existing='{existing.get('name')}' ({existing.get('id','?')[:12]}). "
                    f"Treating as new profile."
                )
                existing = None
            else:
                logger.warning(f"[Extension] MATCH by naukri_id: '{profile.name}' -> existing '{existing.get('name')}' ({existing.get('id','?')[:12]})")
    else:
        logger.warning(f"[Extension] SKIP MATCH: naukri_profile_id is null/empty for '{profile.name}' -> will force insert if no name/email/phone match")
    
    # HIGH PRIORITY: Check by name + source (prevents duplicates from same person captured multiple times)
    if not existing and profile.name:
        import re
        name_regex = re.compile(f"^{re.escape(profile.name.strip())}$", re.IGNORECASE)
        source_pattern = f"{profile.source_platform or 'naukri'}_extension"
        existing = await db.candidate_bank.find_one(
            {"name": name_regex, "source": {"$in": [source_pattern, "naukri_extension"]}},
            {"_id": 0}
        )
        if existing:
            logger.warning(f"[Extension] Dedup: name+source match for '{profile.name}' -> updating {existing.get('id','?')[:12]}")

    # ═══ DOUBLE-MATCH EARLY EXIT (Phase 56.1, Feb 2026) ═══
    # If both email AND phone independently match the SAME existing record,
    # it's almost certainly the same person — merge unconditionally regardless
    # of name variation ("A J I T H" vs "Ajith Kumar", "Yash" vs "Yash Vardhan",
    # nickname changes, etc). This catches a class of duplicates the
    # name-gated lookups below would miss when `_names_are_similar` is
    # tripped by spacing / format quirks in the incoming name.
    if not existing and profile.email and profile.phone:
        import re as _re_dm
        phone_normalized_dm = normalize_phone(profile.phone)
        if phone_normalized_dm and len(phone_normalized_dm) >= 10:
            # Case-insensitive email match + phone_normalized match in a single query
            double_candidate = await db.candidate_bank.find_one(
                {
                    "email": _re_dm.compile(f"^{_re_dm.escape(profile.email)}$", _re_dm.IGNORECASE),
                    "phone_normalized": phone_normalized_dm,
                },
                {"_id": 0},
            )
            if double_candidate:
                existing = double_candidate
                logger.warning(
                    f"[Extension] Dedup: DOUBLE-MATCH (email+phone) for '{profile.name}' "
                    f"-> updating '{existing.get('name')}' ({existing.get('id','?')[:12]}). "
                    f"Bypassed name-similarity check."
                )

    # If not found, try email — but ONLY if the name is similar
    if not existing and profile.email:
        email_candidate = await db.candidate_bank.find_one(
            {"email": profile.email.lower()},
            {"_id": 0}
        )
        if email_candidate and _names_are_similar(profile.name, email_candidate.get("name", "")):
            existing = email_candidate
        elif email_candidate:
            logger.warning(
                f"[Extension] STALE EMAIL blocked: '{profile.email}' belongs to '{email_candidate.get('name')}' "
                f"not '{profile.name}'. Email cleared."
            )
            profile.email = None
    
    # If not found, try phone — but ONLY if the name is similar
    if not existing and profile.phone:
        phone_normalized = normalize_phone(profile.phone)
        phone_candidate = await db.candidate_bank.find_one(
            {"phone_normalized": phone_normalized},
            {"_id": 0}
        )
        if phone_candidate and _names_are_similar(profile.name, phone_candidate.get("name", "")):
            existing = phone_candidate
        elif phone_candidate:
            logger.warning(
                f"[Extension] STALE PHONE blocked: '{profile.phone}' belongs to '{phone_candidate.get('name')}' "
                f"not '{profile.name}'. Phone cleared."
            )
            profile.phone = None
    
    if existing:
        # Update existing record
        # ═══ CLEAN SKILLS before persisting (apply full garbage filter) ═══
        if profile.key_skills:
            profile.key_skills = _clean_skills(profile.key_skills)
        
        update_data = build_complete_update(profile, current_user, now)
        
        # Store dom_scraped flag for zero-LLM extension tracking
        if profile.dom_scraped:
            update_data["dom_scraped"] = True
        
        # Store combined raw text for future re-enrichment
        if ai_enrichment_combined:
            update_data["raw_text_for_enrichment"] = ai_enrichment_combined
        
        # Ensure visibility for the capturing user's team
        visibility_update = await build_team_visibility(current_user)
        if visibility_update:
            update_data.update(visibility_update)
        
        from utils.db_retry import retry_write
        await retry_write(db.candidate_bank.update_one,
            {"id": existing["id"]},
            {"$set": update_data}
        )

        # Multi-mandate linking: add new mandate without removing old ones
        if profile.mandate_id:
            await db.candidate_bank.update_one(
                {"id": existing["id"]},
                {"$addToSet": {"linked_mandates": profile.mandate_id}}
            )

            # Auto-create application (link candidate to mandate) if not already linked
            existing_app = await db.applications.find_one(
                {"candidate_id": existing["id"], "job_id": profile.mandate_id},
                {"_id": 0, "id": 1}
            )
            if not existing_app:
                import uuid as _uuid
                app_id = str(_uuid.uuid4())
                application = {
                    "id": app_id,
                    "job_id": profile.mandate_id,
                    "candidate_id": existing["id"],
                    "candidate_name": profile.name or existing.get("name", ""),
                    "candidate_email": profile.email or existing.get("email", ""),
                    "candidate_phone": profile.phone or existing.get("phone", ""),
                    "stage": "sourced",
                    "status": "active",
                    "source": "extension_capture",
                    "created_by": current_user["id"],
                    "created_at": now,
                    "updated_at": now,
                    "stage_history": [{
                        "stage": "sourced",
                        "moved_by": current_user["id"],
                        "moved_by_name": current_user.get("name", ""),
                        "timestamp": now,
                    }],
                }
                await db.applications.insert_one(application)
                logger.warning(f"[Extension] Auto-linked '{profile.name}' to mandate {profile.mandate_id[:12]} (new application {app_id[:12]})")
        
        # Invalidate search cache so new data appears immediately
        cache.invalidate_search_cache()

        # Auto-regenerate LaTeX resume on update
        try:
            from routes.resume import build_latex, _format_bank_profile_for_resume
            updated_doc = await db.candidate_bank.find_one({"id": existing["id"]}, {"_id": 0})
            if updated_doc:
                profile_data = _format_bank_profile_for_resume(updated_doc)
                latex = build_latex(profile_data, "ats_clean")
                await db.candidate_bank.update_one(
                    {"id": existing["id"]},
                    {"$set": {"resume_latex": latex, "resume_template": "ats_clean"}}
                )
                logger.info(f"[Extension] Re-generated LaTeX resume for {profile.name}")
        except Exception as latex_err:
            logger.warning(f"[Extension] LaTeX re-gen failed for {profile.name}: {latex_err}")

        # Safety log: count total profiles
        total = await db.candidate_bank.count_documents({"source": {"$regex": "_extension$"}})
        logger.warning(f"[Extension] UPDATE: '{profile.name}' -> existing record {existing['id'][:12]}. Total extension profiles: {total}")
        
        await _log_capture(profile, current_user, "success", "updated", existing["id"], None, None, capture_start)
        await log_activity(
            candidate_id=existing["id"], action=ACTION_UPDATED,
            description=f"Profile updated via {profile.source_platform or 'extension'} capture",
            performed_by=current_user.get("id"), performed_by_name=current_user.get("name"),
            performed_by_role=current_user.get("role"), candidate_name=profile.name,
            details={"source": profile.source_platform, "url": profile.naukri_profile_url},
        )
        # 🚀 FULL GROQ ENRICHMENT (Unconditional, like old "Full Haiku" blueprint)
        # Fire-and-forget background enrichment (non-blocking, separate thread)
        logger.warning(f"[Extension-UPDATE] Enrichment trigger: name={bool(profile.name)} ({profile.name}), ai_text_len={len(ai_enrichment_combined)}")
        if profile.name and ai_enrichment_combined:
            # Phase 52: skip Qwen + embedding when this exact profile was
            # enriched in the last DEDUP_FRESH_DAYS days with identical text.
            # The candidate is ALREADY tagged to the chosen mandate above.
            _skip, _reason = _should_skip_enrichment(existing, ai_enrichment_combined)
            if _skip:
                logger.warning(
                    f"[Dedup] SKIP_QWEN '{profile.name}' "
                    f"(reason={_reason}, candidate_id={existing['id'][:12]})"
                )
            else:
                logger.info(
                    f"[Extension-UPDATE] ⚡ Triggering FULL GROQ enrichment for "
                    f"'{profile.name}' (dedup_decision={_reason})"
                )
                _fire_and_forget(_background_full_groq_enrich(
                    existing["id"], profile.name,
                    ai_enrichment_combined, ai_recruiter_phone, ai_recruiter_email,
                    user_role=current_user.get("role", ""),
                    user_email=current_user.get("email", ""),
                ))
        return CaptureResponse(
            success=True,
            action="updated",
            candidate_id=existing["id"],
            message=f"Profile updated for {profile.name}"
        )
    
    else:
        # ═══ AUTO-MERGE CHECK (2/3 matching: name + email + phone) ═══
        # Before creating a new record, check if there's a mergeable existing profile
        # This catches cross-source duplicates (extension + Excel + manual + CV upload)
        from services.candidate_merge import find_merge_candidate, merge_profiles, log_merge_audit

        merge_target = await find_merge_candidate(
            name=profile.name,
            email=profile.email,
            phone=profile.phone,
            current_employer=getattr(profile, "current_employer", None) or getattr(profile, "current_company", None),
            designation=getattr(profile, "designation", None) or getattr(profile, "current_designation", None),
            location=getattr(profile, "location", None) or getattr(profile, "current_location", None),
            experience_years=getattr(profile, "experience_years", None),
        )

        if merge_target:
            # Build the incoming data to merge
            incoming_data = build_complete_candidate(profile, "temp", current_user, now)
            merge_updates = merge_profiles(merge_target, incoming_data)

            if merge_updates:
                from utils.db_retry import retry_write
                await retry_write(db.candidate_bank.update_one,
                    {"id": merge_target["id"]},
                    {"$set": merge_updates}
                )

                # Add team visibility
                visibility_update = await build_team_visibility(current_user)
                if visibility_update:
                    await db.candidate_bank.update_one(
                        {"id": merge_target["id"]},
                        {"$set": visibility_update}
                    )

                # Multi-mandate linking + application creation (with dedup check)
                if profile.mandate_id:
                    await db.candidate_bank.update_one(
                        {"id": merge_target["id"]},
                        {"$addToSet": {"linked_mandates": profile.mandate_id}}
                    )
                    # Create application record if not already linked
                    existing_app = await db.applications.find_one(
                        {"candidate_id": merge_target["id"], "job_id": profile.mandate_id},
                        {"_id": 0, "id": 1}
                    )
                    if not existing_app:
                        import uuid as _uuid
                        app_id = str(_uuid.uuid4())
                        application = {
                            "id": app_id,
                            "job_id": profile.mandate_id,
                            "candidate_id": merge_target["id"],
                            "candidate_name": profile.name or merge_target.get("name", ""),
                            "candidate_email": profile.email or merge_target.get("email", ""),
                            "candidate_phone": profile.phone or merge_target.get("phone", ""),
                            "stage": "sourced",
                            "status": "active",
                            "source": "extension_capture",
                            "created_by": current_user["id"],
                            "created_at": now,
                            "updated_at": now,
                            "stage_history": [{
                                "stage": "sourced",
                                "moved_by": current_user["id"],
                                "moved_by_name": current_user.get("name", ""),
                                "timestamp": now,
                            }],
                        }
                        await db.applications.insert_one(application)
                        logger.warning(f"[AutoMerge] Auto-linked '{profile.name}' to mandate {profile.mandate_id[:12]}")

                # Audit trail
                await log_merge_audit(
                    merge_target["id"], incoming_data, merge_updates,
                    merged_by=current_user.get("email", "system")
                )

                logger.warning(
                    f"[AutoMerge] MERGED '{profile.name}' into existing '{merge_target.get('name')}' "
                    f"(id={merge_target['id'][:12]}, fields_updated={len(merge_updates)})"
                )

                cache.invalidate_search_cache()
                await _log_capture(profile, current_user, "success", "auto_merged", merge_target["id"], None, None, capture_start)
                
                # 🚀 FULL GROQ ENRICHMENT for auto-merged profiles (with dedup)
                logger.warning(f"[Extension-Merge] Enrichment trigger: name={bool(profile.name)}, ai_text_len={len(ai_enrichment_combined)}")
                if ai_enrichment_combined and profile.name:
                    # Phase 52 dedup — same rules as the UPDATE path.
                    _skip, _reason = _should_skip_enrichment(merge_target, ai_enrichment_combined)
                    if _skip:
                        logger.warning(
                            f"[Dedup] SKIP_QWEN '{profile.name}' "
                            f"(reason={_reason}, candidate_id={merge_target['id'][:12]}, "
                            f"path=auto_merge)"
                        )
                    else:
                        logger.info(
                            f"[Extension-Merge] ⚡ Triggering FULL GROQ enrichment for "
                            f"'{profile.name}' (dedup_decision={_reason}, auto-merged)"
                        )
                        _fire_and_forget(_background_full_groq_enrich(
                            merge_target["id"], profile.name,
                            ai_enrichment_combined, ai_recruiter_phone, ai_recruiter_email,
                            user_role=current_user.get("role", ""),
                            user_email=current_user.get("email", ""),
                        ))
                
                return CaptureResponse(
                    success=True,
                    action="auto_merged",
                    candidate_id=merge_target["id"],
                    message=f"Profile auto-merged with existing record for {merge_target.get('name', profile.name)}"
                )

        # Create new candidate with ALL data
        candidate_id = str(uuid.uuid4())
        
        # ═══ CLEAN SKILLS before persisting (apply full garbage filter) ═══
        if profile.key_skills:
            profile.key_skills = _clean_skills(profile.key_skills)
        
        candidate_data = build_complete_candidate(profile, candidate_id, current_user, now)
        
        # Track enrichment lifecycle
        candidate_data["enrichment_status"] = "pending"
        
        # Store dom_scraped flag for zero-LLM extension tracking
        if profile.dom_scraped:
            candidate_data["dom_scraped"] = True
        
        # Store combined raw text for future re-enrichment
        if ai_enrichment_combined:
            candidate_data["raw_text_for_enrichment"] = ai_enrichment_combined
        
        # Add team visibility
        visibility_update = await build_team_visibility(current_user)
        if visibility_update:
            candidate_data.update(visibility_update)
        
        try:
            from utils.db_retry import retry_write
            await retry_write(db.candidate_bank.insert_one, candidate_data)
        except Exception as insert_err:
            logger.error(f"[Extension] Insert FAILED for {profile.name}: {insert_err}")
            await _log_capture(profile, current_user, "failed", "insert_failed", candidate_id, str(insert_err)[:300], "save_to_bank", capture_start)
            raise
        
        # Invalidate search cache so new profile appears immediately
        cache.invalidate_search_cache()

        # Auto-link new candidate to mandate (create application)
        if profile.mandate_id:
            import uuid as _uuid
            app_id = str(_uuid.uuid4())
            application = {
                "id": app_id,
                "job_id": profile.mandate_id,
                "candidate_id": candidate_id,
                "candidate_name": profile.name or "",
                "candidate_email": profile.email or "",
                "candidate_phone": profile.phone or "",
                "stage": "sourced",
                "status": "active",
                "source": "extension_capture",
                "created_by": current_user["id"],
                "created_at": now,
                "updated_at": now,
                "stage_history": [{
                    "stage": "sourced",
                    "moved_by": current_user["id"],
                    "moved_by_name": current_user.get("name", ""),
                    "timestamp": now,
                }],
            }
            await db.applications.insert_one(application)
            logger.warning(f"[Extension] Auto-linked new '{profile.name}' to mandate {profile.mandate_id[:12]}")

        # Auto-generate LaTeX resume using Resume Builder engine
        try:
            from routes.resume import build_latex, _format_bank_profile_for_resume
            profile_data = _format_bank_profile_for_resume(candidate_data)
            latex = build_latex(profile_data, "ats_clean")
            await db.candidate_bank.update_one(
                {"id": candidate_id},
                {"$set": {"resume_latex": latex, "resume_template": "ats_clean"}}
            )
            logger.info(f"[Extension] Auto-generated LaTeX resume for {profile.name}")
        except Exception as latex_err:
            logger.warning(f"[Extension] LaTeX auto-gen failed for {profile.name}: {latex_err}")

        # Safety log: count total profiles
        total = await db.candidate_bank.count_documents({"source": {"$regex": "_extension$"}})
        logger.warning(f"[Extension] INSERT: New profile '{profile.name}' ({candidate_id[:12]}). Total extension profiles: {total}")
        
        await _log_capture(profile, current_user, "success", "created", candidate_id, None, None, capture_start)
        await log_activity(
            candidate_id=candidate_id, action=ACTION_CAPTURED,
            description=f"Profile captured from {profile.source_platform or 'extension'}",
            performed_by=current_user.get("id"), performed_by_name=current_user.get("name"),
            performed_by_role=current_user.get("role"), candidate_name=profile.name,
            details={"source": profile.source_platform, "url": profile.naukri_profile_url},
        )
        # 🚀 FULL GROQ ENRICHMENT for new profiles (Unconditional, like "Full Haiku" blueprint)
        logger.warning(f"[Extension-CREATE] Enrichment trigger: name={bool(profile.name)} ({profile.name}), ai_text_len={len(ai_enrichment_combined)}")
        if profile.name and ai_enrichment_combined:
            logger.info(f"[Extension-CREATE] ⚡ Triggering FULL GROQ enrichment for NEW '{profile.name}'")
            _fire_and_forget(_background_full_groq_enrich(
                candidate_id, profile.name,
                ai_enrichment_combined, ai_recruiter_phone, ai_recruiter_email,
                user_role=current_user.get("role", ""),
                user_email=current_user.get("email", ""),
            ))
        return CaptureResponse(
            success=True,
            action="created",
            candidate_id=candidate_id,
            message=f"{profile.name} added to VHC Talent OS"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ASYNC CAPTURE  —  v5.5.10 (gated rollout)
#
# Problem the sync /capture endpoint hit:
#   • Chrome MV3 kills the service worker after ~30s of an awaited fetch.
#   • Cloudflare times out the request at 100s.
#   • Atlas primary failover sometimes adds 20-60s to a single capture.
#   • Net effect: orphaned "Processing" UI states and 502 errors.
#
# Fix:
#   • POST /capture/async returns 202 + job_id IMMEDIATELY.
#   • The same capture_profile() logic runs as a FastAPI BackgroundTask.
#   • The extension polls GET /capture/status/{job_id} every 3s.
#   • When status == completed, the extension reads the full CaptureResponse
#     from the job document and processes it exactly like the old sync flow.
#
# Gating:
#   • EXTENSION_ASYNC_USERS env var = comma-separated emails allowed to use it.
#   • The endpoint itself does NOT gate (the extension build is gated instead
#     — only admin@vhc.in is loading v5.5.10 unpacked while we test).
#   • Old extension versions (v5.5.8) keep using /capture and are unaffected.
# ═══════════════════════════════════════════════════════════════════════════════


async def _run_capture_job(job_id: str, profile: CompleteNaukriProfileInput, current_user: dict):
    """Background task: run the full capture_profile() flow and persist result."""
    def _now_iso():
        return datetime.now(timezone.utc).isoformat()
    try:
        await db.extension_capture_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "processing", "updated_at": _now_iso()}}
        )
        # Call the existing sync handler directly. _mem=None disables the
        # post-response GC hook (which is fine — gc + jemalloc clean up later).
        result = await capture_profile(profile, current_user, _mem=None)
        result_dict = result.model_dump() if hasattr(result, "model_dump") else result.dict()
        await db.extension_capture_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "completed",
                "completed_at": _now_iso(),
                "updated_at": _now_iso(),
                "result": result_dict,
            }}
        )
    except Exception as e:
        logger.exception(f"[capture-async] job_id={job_id} failed")
        await db.extension_capture_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "failed",
                "completed_at": _now_iso(),
                "updated_at": _now_iso(),
                "error": str(e)[:500],
            }}
        )


@extension_router.post("/capture/async", status_code=202)
async def capture_profile_async(
    profile: CompleteNaukriProfileInput,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Asynchronous capture: returns 202 + job_id immediately, processes in
    background. Extension polls GET /capture/status/{job_id} to retrieve result.

    Backward-compat: the existing POST /capture (sync) endpoint is untouched.
    """
    job_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.extension_capture_jobs.insert_one({
        "_id": job_id,
        "status": "pending",
        "user_id": current_user.get("id", ""),
        "user_email": current_user.get("email", ""),
        "candidate_name": (profile.name or "")[:200],
        "naukri_profile_id": profile.naukri_profile_id,
        "created_at": now_iso,
        "updated_at": now_iso,
    })
    background_tasks.add_task(_run_capture_job, job_id, profile, current_user)
    logger.info(f"[capture-async] queued job_id={job_id} for {profile.name} (user={current_user.get('email')})")
    return {"job_id": job_id, "status": "pending"}


@extension_router.get("/capture/status/{job_id}")
async def capture_status(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Poll endpoint — returns the current state of an async capture job."""
    job = await db.extension_capture_jobs.find_one(
        {"_id": job_id, "user_id": current_user.get("id", "")}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Capture job not found")
    # _id is the job_id (UUID string) — expose as job_id, drop _id for the client
    job["job_id"] = job.pop("_id")
    return job


@extension_router.get("/stats")
async def get_extension_stats(current_user: dict = Depends(get_current_user)):
    """Get statistics for extension-captured candidates"""
    
    total_captured = await db.candidate_bank.count_documents({
        "source": {"$regex": "_extension$"}
    })
    
    user_captured = await db.candidate_bank.count_documents({
        "source": {"$regex": "_extension$"},
        "source_details.captured_by": current_user["id"]
    })
    
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_captured = await db.candidate_bank.count_documents({
        "source": {"$regex": "_extension$"},
        "created_at": {"$gte": today_start}
    })
    
    top_capturers = []
    if current_user.get("role") == "admin":
        pipeline = [
            {"$match": {"source": {"$regex": "_extension$"}}},
            {"$group": {
                "_id": "$source_details.captured_by_name",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        # FIX: Add allowDiskUse to prevent "Exceeded memory limit" errors
        cursor = db.candidate_bank.aggregate(pipeline, allowDiskUse=True)
        top_capturers = await cursor.to_list(5)
    
    return {
        "total_captured": total_captured,
        "user_captured": user_captured,
        "today_captured": today_captured,
        "top_capturers": top_capturers
    }


@extension_router.get("/profile/{candidate_id}")
async def get_naukri_profile(
    candidate_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get complete Naukri profile for a candidate"""
    
    candidate = await db.candidate_bank.find_one(
        {"id": candidate_id},
        {"_id": 0}
    )
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    return candidate



from pydantic import BaseModel as _BaseModel


class CaptureErrorReport(_BaseModel):
    """Extension reports a client-side capture failure."""
    candidate_name: Optional[str] = None
    candidate_url: Optional[str] = None
    error_message: str
    error_type: Optional[str] = None  # e.g., "no_name", "http_422", "parse_error"
    raw_data: Optional[dict] = None
    source_platform: Optional[str] = "naukri"


@extension_router.post("/capture-error")
async def report_capture_error(
    report: CaptureErrorReport,
    current_user: dict = Depends(get_current_user),
):
    """Log a capture failure reported by the extension (client-side errors, HTTP errors, etc.)"""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "timestamp": now,
        "profile_id": "",
        "profile_url": report.candidate_url or "",
        "candidate_name": report.candidate_name or "Unknown",
        "candidate_email": "",
        "candidate_phone": "",
        "status": "failed",
        "action": "capture_error",
        "candidate_id": "",
        "failure_reason": report.error_message,
        "failed_step": report.error_type or "extension_error",
        "data_missing_fields": [],
        "captured_to_bank": False,
        "is_recovered": False,
        "retry_count": 0,
        "capture_duration_ms": 0,
        "source": "naukri_extension",
        "captured_by": current_user.get("id", ""),
        "captured_by_name": current_user.get("name", ""),
        "raw_data": report.raw_data,
    }
    try:
        await db.naukri_capture_logs.insert_one(doc)
        return {"success": True, "message": "Error logged"}
    except Exception as e:
        logger.error(f"[CaptureErrorLog] Failed to log: {e}")
        return {"success": False, "message": str(e)}



@extension_router.get("/batch-status")
async def get_batch_enrichment_status(current_user: dict = Depends(get_current_user)):
    """Admin-only: Get Batch API enrichment queue stats and recent batches."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    from services.batch_enrichment import get_batch_stats
    return get_batch_stats()


@extension_router.post("/batch-submit")
async def trigger_batch_submit(current_user: dict = Depends(get_current_user)):
    """Admin-only: Manually trigger batch submission of queued items."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    from services.batch_enrichment import submit_batch
    batch_id = submit_batch()
    if batch_id:
        return {"success": True, "batch_id": batch_id, "message": "Batch submitted"}
    return {"success": False, "message": "No items in queue or submission failed"}


@extension_router.post("/batch-poll")
async def trigger_batch_poll(current_user: dict = Depends(get_current_user)):
    """Admin-only: Manually trigger polling of pending batches."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    from services.batch_enrichment import poll_and_process_batches
    poll_and_process_batches()
    return {"success": True, "message": "Poll completed"}

# ── Profile building and team visibility are in services.extension_service ──


def _is_contact_info(value: str) -> bool:
    """Check if a value looks like contact info (email, phone, URL) rather than a professional field."""
    if not value or not isinstance(value, str):
        return False
    v = value.strip().lower()
    import re as _re
    # Email pattern
    if _re.search(r'@[a-zA-Z0-9.-]+\.[a-zA-Z]+', v):
        return True
    # Phone pattern (with or without prefix)
    if _re.match(r'^(?:mobile|phone|tel|contact|ph\.?)\s*[:\-]?\s*[\+\d]', v, _re.IGNORECASE):
        return True
    if _re.match(r'^[\+]?\d[\d\s\-]{8,}$', v):
        return True
    # "Email:" or "Mobile:" prefix
    if _re.match(r'^(?:email|e-mail|mobile|phone|tel)\s*[:\-]', v, _re.IGNORECASE):
        return True
    return False


def _is_garbage_employer(value: str) -> bool:
    """Check if an employer value is garbage (sentence, CV fragment, contact info, EDUCATION)."""
    if not value or not isinstance(value, str):
        return True
    v = value.strip()
    if _is_contact_info(v):
        return True
    vl = v.lower()
    
    # CRITICAL: Reject education institutions as employers
    education_keywords = ['university', 'college', 'school', 'institute', 'academy', 'iit ', 'nit ', 'iim ']
    if any(keyword in vl for keyword in education_keywords):
        logger.warning(f"[Garbage Check] Employer '{v[:50]}' contains education keyword — rejecting")
        return True
    
    # Too long for a company name (typically < 60 chars)
    if len(v) > 80:
        return True
    # Starts with first-person or sentence fragments
    if any(vl.startswith(p) for p in ['i am', 'i have', 'i was', 'i worked', 'i\'m', 'worked as',
                                       'working as', 'currently', 'responsible for', 'experienced in',
                                       'proficient', 'passionate', 'skilled in', 'hands-on']):
        return True
    # Contains date patterns (e.g. "from 20th August 2020 to 30th August 2021")
    import re as _re
    if _re.search(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b', vl):
        return True
    if _re.search(r'\bfrom\s+\d', vl):
        return True
    # Contains sentence connectors
    if any(w in vl for w in [' from ', ' to ', ' worked ', ' as an ', ' as a ', ' in "', " in '"]):
        return True
    return False


def _is_garbage_designation(value: str) -> bool:
    """Check if a designation value is a CV section header, garbage, or GRADE."""
    if not value or not isinstance(value, str):
        return True
    v = value.strip()
    if _is_contact_info(v):
        return True
    vl = v.lower()
    
    # CRITICAL: Reject grades/scores as designations
    grade_patterns = ['gpa:', 'cgpa:', 'percentage:', '%', 'grade:', 'marks:', 'score:']
    if any(pattern in vl for pattern in grade_patterns):
        logger.warning(f"[Garbage Check] Designation '{v[:50]}' contains grade pattern — rejecting")
        return True
    
    # Reject if designation is just a number or grade
    v_clean = v.replace('.', '').replace('%', '').replace(':', '').strip()
    if v_clean.isdigit():
        logger.warning(f"[Garbage Check] Designation '{v[:50]}' is just a number — rejecting")
        return True
    
    # Too long for a job title
    if len(v) > 80:
        return True
    # CV section headers commonly misidentified as designation
    section_headers = [
        'internship experience', 'work experience', 'experience', 'education',
        'objective', 'career objective', 'summary', 'profile summary',
        'personal details', 'other personal details', 'skills', 'key skills',
        'projects', 'certifications', 'achievements', 'references',
        'declaration', 'hobbies', 'interests', 'extra curricular',
    ]
    if vl in section_headers:
        return True
    # Starts with first-person
    if any(vl.startswith(p) for p in ['i am', 'i have', 'i was', 'i worked', 'worked as']):
        return True
    return False



def _clean_skills(skills: list) -> list:
    """Post-process skills array to remove garbage: dates, company names, phone numbers, emails, etc."""
    import re as _re
    if not skills or not isinstance(skills, list):
        return skills

    garbage_patterns = [
        _re.compile(r'^\d{4}\s*[-–]\s*(present|\d{4})', _re.IGNORECASE),  # Date ranges
        _re.compile(r'^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}', _re.IGNORECASE),  # Month Year
        _re.compile(r'^\+?\d[\d\s\-]{8,}$'),  # Phone numbers
        _re.compile(r'@[a-zA-Z0-9.-]+\.[a-zA-Z]+'),  # Email addresses
        _re.compile(r'^(ph\.|phone|email|tel)[:\s]', _re.IGNORECASE),  # Contact labels
        _re.compile(r'^professional\s+experience', _re.IGNORECASE),  # Section headers
        _re.compile(r'^(work\s+experience|education|certification|project)', _re.IGNORECASE),
        _re.compile(r'(pvt|ltd|private|limited|inc|corp|llp|llc)\.?\s*$', _re.IGNORECASE),  # Company suffixes
        _re.compile(r'^\d+\s*(year|month|day)\(?s?\)?', _re.IGNORECASE),  # Duration text
        _re.compile(r'^(present|current|till date)', _re.IGNORECASE),  # Date markers
        _re.compile(r'settings|manage\s+users|manage\s+quota|change\s+password|faqs|usage\s+guidelines', _re.IGNORECASE),  # Nav text
        _re.compile(r'product\s+settings|manage\s+teams', _re.IGNORECASE),  # Naukri nav
    ]

    cleaned = []
    seen_lower = set()
    for skill in skills:
        if not isinstance(skill, str):
            continue
        s = skill.strip().rstrip('|').strip()  # Remove trailing pipe chars from Naukri DOM
        if not s or len(s) < 2 or len(s) > 60:
            continue
        s_lower = s.lower()
        if s_lower in seen_lower:
            continue
        # Skip if matches garbage pattern
        if any(p.search(s) for p in garbage_patterns):
            continue
        # Skip items that look like sentences (too many words = likely a description)
        if len(s.split()) > 6:
            continue
        # Skip items that are just a person's name (all title case, 2-4 words)
        words = s.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
            # Could be a name or a company - skip if it ends with common name patterns
            if not any(tech_word in s_lower for tech_word in ['design', 'engineer', 'manage', 'develop', 'system', 'data', 'cloud', 'network', 'security', 'quality', 'sap', 'sigma', 'power', 'spring', 'red hat', 'machine', 'deep', 'oracle', 'azure', 'google', 'amazon', 'web', 'mobile', 'agile', 'scrum', 'devops', 'docker', 'kubernetes', 'react', 'angular', 'node', 'python', 'java', 'sql', 'tableau', 'salesforce', 'service', 'project', 'product', 'business', 'digital', 'cyber', 'block', 'chain', 'artificial', 'natural', 'process', 'automation', 'testing', 'analytics', 'market', 'supply', 'lean', 'kaizen']):
                # Check if it looks like a company or person name
                if any(c in s_lower for c in [' ltd', ' pvt', ' inc', ' corp', ' llp']):
                    continue
        seen_lower.add(s_lower)
        cleaned.append(s)
    return cleaned


@extension_router.post("/re-enrich/{candidate_id}")
async def re_enrich_candidate(
    candidate_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Re-run Claude AI extraction on an existing candidate using their stored raw_text.
    Useful when a candidate was previously enriched with low-quality spaCy/regex data."""
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    raw_text = candidate.get("raw_text_for_enrichment") or candidate.get("raw_page_text") or candidate.get("raw_profile_text") or ""
    # Also combine raw_sections if available
    raw_sections = candidate.get("raw_sections")
    if raw_sections and isinstance(raw_sections, dict) and len(raw_text) < 200:
        sections_text = "\n".join(f"{k}: {v}" for k, v in raw_sections.items() if v)
        if sections_text:
            raw_text = (raw_text + "\n" + sections_text).strip()
    if not raw_text or len(raw_text) < 100:
        raise HTTPException(status_code=400, detail="No raw text stored for this candidate — cannot re-enrich")

    candidate_name = candidate.get("name", "Unknown")

    try:
        # ── HYBRID: Regex first for ALL users, Groq fallback ──
        from services.naukri_regex_parser import extract_full_profile_regex
        ai = extract_full_profile_regex(
            raw_text=raw_text,
            recruiter_phone=current_user.get("phone", ""),
            recruiter_email=current_user.get("email", ""),
        )
        regex_quality = _score_extraction_quality(ai) if ai else 0.0
        _used_claude = False

        if ai and regex_quality >= 0.5:
            logger.info(f"[Re-Enrich] Regex sufficient ({regex_quality:.0%}) for {candidate_name} — Groq SKIPPED")
        else:
            logger.info(f"[Re-Enrich] Regex quality low ({regex_quality:.0%}) for {candidate_name} — calling Groq")
            from services.groq_service import extract_full_profile_groq
            ai = await extract_full_profile_groq(
                raw_text=raw_text,
                candidate_name=candidate_name
            )
            if not ai or ai.get("error"):
                raise HTTPException(status_code=500, detail=f"AI extraction failed: {ai.get('error', 'unknown')}")
            _used_claude = True

        # Build update dict from AI results
        updates = {}

        # Contact
        if ai.get("candidate_phone"):
            digits = ''.join(filter(str.isdigit, str(ai["candidate_phone"])))
            if len(digits) >= 10:
                updates["phone"] = digits[-10:]
                updates["phone_normalized"] = digits[-10:]
        if ai.get("candidate_email"):
            email = ai["candidate_email"].lower().strip()
            blocked = ['@naukri.com', '@vhc.in', 'noreply@', 'support@']
            if not any(p in email for p in blocked):
                updates["email"] = email

        # Professional fields
        if ai.get("current_employer"):
            updates["current_employer"] = ai["current_employer"]
        if ai.get("current_designation"):
            updates["designation"] = ai["current_designation"]
        if ai.get("current_department"):
            _dept = ai["current_department"].strip()
            if len(_dept) < 80:
                updates["department"] = _dept
        if ai.get("current_industry"):
            _ind = ai["current_industry"].strip()
            if len(_ind) < 80:
                updates["industry"] = _ind
        if ai.get("location"):
            updates["location"] = ai["location"]
        if ai.get("headline"):
            updates["headline"] = ai["headline"]
        if ai.get("profile_summary"):
            updates["summary"] = ai["profile_summary"]
        if ai.get("experience_years"):
            try:
                _exp = float(ai["experience_years"])
                if _exp <= 50:
                    updates["experience_years"] = round(_exp, 2)  # Preserve decimal (2.05)
            except (ValueError, TypeError):
                logger.warning(f"[BG] Invalid experience_years: {ai.get('experience_years')}")

        # CTC (with ₹20 Cr cap)
        _CTC_MAX = 50_000_000
        if ai.get("current_ctc") and int(ai["current_ctc"]) <= _CTC_MAX:
            updates["current_salary"] = int(ai["current_ctc"])
        if ai.get("expected_ctc") and int(ai["expected_ctc"]) <= _CTC_MAX:
            updates["expected_salary"] = int(ai["expected_ctc"])

        # Notice
        if ai.get("notice_period"):
            updates["notice_period"] = ai["notice_period"]
        if ai.get("notice_period_days"):
            updates["notice_period_days"] = int(ai["notice_period_days"])

        # Skills — clean
        if ai.get("key_skills"):
            updates["skills"] = _clean_skills(ai["key_skills"])

        # Work experience
        if ai.get("work_experience") and isinstance(ai["work_experience"], list):
            updates["experience"] = ai["work_experience"]

        # Education
        if ai.get("education") and isinstance(ai["education"], list):
            updates["education"] = ai["education"]

        # Certifications, languages
        if ai.get("certifications"):
            updates["certifications"] = ai["certifications"]
        if ai.get("languages"):
            updates["languages"] = ai["languages"]

        # Personal details
        personal = {}
        if ai.get("date_of_birth"):
            personal["date_of_birth"] = ai["date_of_birth"]
        if ai.get("gender"):
            personal["gender"] = ai["gender"]
        if ai.get("marital_status"):
            personal["marital_status"] = ai["marital_status"]
        if personal:
            existing_personal = candidate.get("personal_details") or {}
            updates["personal_details"] = {**existing_personal, **personal}

        if updates:
            updates["ai_enriched_at"] = datetime.now(timezone.utc).isoformat()
            updates["ai_enrichment_source"] = "anthropic_direct" if _used_claude else "regex_hybrid"
            await db.candidate_bank.update_one({"id": candidate_id}, {"$set": updates})

        return {
            "success": True,
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "fields_updated": list(updates.keys()),
            "source": updates.get("ai_enrichment_source", "unknown"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Re-Enrich] Error for {candidate_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

