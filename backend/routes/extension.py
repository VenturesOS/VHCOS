"""
Browser Extension API Routes - Extended Version
Handles complete Naukri profile capture with ALL fields
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
import logging

from utils.auth import get_current_user
from config import db

logger = logging.getLogger(__name__)

extension_router = APIRouter(prefix="/api/extension", tags=["Browser Extension"])


# ============== REQUEST/RESPONSE MODELS ==============

class WorkExperienceInput(BaseModel):
    company: Optional[str] = None
    company_url: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    duration: Optional[str] = None
    duration_months: Optional[int] = None
    is_current: bool = False
    job_type: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    responsibilities: List[str] = []
    achievements: List[str] = []
    reporting_to: Optional[str] = None
    team_size: Optional[int] = None
    annual_salary: Optional[int] = None
    industry: Optional[str] = None


class EducationInput(BaseModel):
    degree: Optional[str] = None
    degree_type: Optional[str] = None
    specialization: Optional[str] = None
    institution: Optional[str] = None
    university: Optional[str] = None
    board: Optional[str] = None
    location: Optional[str] = None
    from_year: Optional[str] = None
    to_year: Optional[str] = None
    year_of_passing: Optional[str] = None
    score: Optional[str] = None
    score_type: Optional[str] = None
    course_type: Optional[str] = None


class SkillInput(BaseModel):
    name: str
    version: Optional[str] = None
    last_used: Optional[str] = None
    experience_months: Optional[int] = None
    experience_years: Optional[float] = None
    proficiency: Optional[str] = None
    is_primary: bool = False


class CertificationInput(BaseModel):
    name: str
    issuing_authority: Optional[str] = None
    license_number: Optional[str] = None
    url: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    is_lifetime: bool = False
    description: Optional[str] = None


class ProjectInput(BaseModel):
    title: str
    client: Optional[str] = None
    status: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    team_size: Optional[int] = None
    skills_used: List[str] = []
    responsibilities: List[str] = []
    project_url: Optional[str] = None


class LanguageInput(BaseModel):
    language: str
    proficiency: Optional[str] = None
    read: bool = False
    write: bool = False
    speak: bool = False


class OnlineProfileInput(BaseModel):
    platform: str
    url: str
    username: Optional[str] = None


class PersonalDetailsInput(BaseModel):
    date_of_birth: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    nationality: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry: Optional[str] = None
    has_passport: bool = False
    permanent_address: Optional[str] = None
    permanent_city: Optional[str] = None
    permanent_state: Optional[str] = None
    permanent_country: Optional[str] = None
    permanent_pincode: Optional[str] = None
    current_address: Optional[str] = None
    current_city: Optional[str] = None
    current_state: Optional[str] = None
    current_country: Optional[str] = None
    current_pincode: Optional[str] = None
    category: Optional[str] = None
    differently_abled: bool = False
    disability_type: Optional[str] = None
    work_permit_usa: Optional[str] = None
    work_permit_other: Optional[str] = None


class CareerPreferencesInput(BaseModel):
    current_salary: Optional[int] = None
    current_salary_currency: str = "INR"
    current_salary_breakdown: Optional[Dict[str, int]] = None
    expected_salary: Optional[int] = None
    expected_salary_currency: str = "INR"
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    notice_period: Optional[str] = None
    notice_period_days: Optional[int] = None
    is_serving_notice: bool = False
    last_working_day: Optional[str] = None
    is_negotiable: bool = False
    current_location: Optional[str] = None
    preferred_locations: List[str] = []
    willing_to_relocate: bool = False
    relocation_preferences: List[str] = []
    preferred_job_type: List[str] = []
    preferred_employment_type: List[str] = []
    preferred_shift: List[str] = []
    work_from_home: bool = False
    remote_work_preference: Optional[str] = None
    preferred_industry: List[str] = []
    preferred_functional_area: List[str] = []
    preferred_role: List[str] = []
    preferred_role_category: List[str] = []
    preferred_company_type: List[str] = []
    preferred_company_size: Optional[str] = None
    companies_to_avoid: List[str] = []


class CompleteNaukriProfileInput(BaseModel):
    """Complete Naukri profile input - ALL fields"""
    
    # Naukri Identification
    naukri_profile_id: str
    naukri_profile_url: str
    naukri_resume_id: Optional[str] = None
    
    # Basic Info
    name: str
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    photo_url: Optional[str] = None
    
    # Contact
    email: Optional[str] = None
    alternate_email: Optional[str] = None
    phone: Optional[str] = None
    alternate_phone: Optional[str] = None
    
    # Professional Identity
    headline: Optional[str] = None
    resume_headline: Optional[str] = None
    profile_summary: Optional[str] = None
    
    # Current Employment
    current_company: Optional[str] = None
    current_designation: Optional[str] = None
    current_department: Optional[str] = None
    current_industry: Optional[str] = None
    current_role_category: Optional[str] = None
    employment_status: Optional[str] = None
    
    # Experience
    total_experience_years: Optional[float] = None
    total_experience_months: Optional[int] = None
    total_experience_display: Optional[str] = None
    work_experience: List[WorkExperienceInput] = []
    
    # Education
    highest_qualification: Optional[str] = None
    highest_degree: Optional[str] = None
    education: List[EducationInput] = []
    
    # Skills
    key_skills: List[str] = []
    key_skills_display: Optional[str] = None
    it_skills: List[SkillInput] = []
    soft_skills: List[str] = []
    tools: List[str] = []
    
    # Certifications
    certifications: List[CertificationInput] = []
    
    # Projects
    projects: List[ProjectInput] = []
    
    # Languages
    languages: List[LanguageInput] = []
    
    # Online Profiles
    online_profiles: List[OnlineProfileInput] = []
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    
    # Personal Details
    personal_details: Optional[PersonalDetailsInput] = None
    
    # Career Preferences
    career_preferences: Optional[CareerPreferencesInput] = None
    
    # Additional
    accomplishments: Optional[str] = None
    about_me: Optional[str] = None
    additional_info: Optional[str] = None
    
    # Resume
    has_resume: bool = False
    resume_title: Optional[str] = None
    resume_format: Optional[str] = None
    
    # Timestamps
    profile_created_on: Optional[str] = None
    profile_last_updated: Optional[str] = None
    last_active: Optional[str] = None
    
    # Activity
    response_rate: Optional[str] = None
    
    # Raw data for debugging
    raw_profile_text: Optional[str] = None
    raw_sections: Optional[Dict[str, str]] = None
    
    # Scrape metadata
    scraped_at: str


class CaptureResponse(BaseModel):
    success: bool
    action: str
    candidate_id: str
    message: str


# ============== ENDPOINTS ==============

@extension_router.post("/capture", response_model=CaptureResponse)
async def capture_profile(
    profile: CompleteNaukriProfileInput,
    current_user: dict = Depends(get_current_user)
):
    """
    Capture and save/update a COMPLETE Naukri profile.
    Stores ALL available data for 1:1 profile matching.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    # Check for existing profile by naukri_profile_id
    existing = await db.candidate_bank.find_one(
        {"naukri_profile_id": profile.naukri_profile_id},
        {"_id": 0}
    )
    
    # If not found, try email
    if not existing and profile.email:
        existing = await db.candidate_bank.find_one(
            {"email": profile.email.lower()},
            {"_id": 0}
        )
    
    # If not found, try phone
    if not existing and profile.phone:
        phone_normalized = normalize_phone(profile.phone)
        existing = await db.candidate_bank.find_one(
            {"phone_normalized": phone_normalized},
            {"_id": 0}
        )
    
    if existing:
        # Update existing record
        update_data = build_complete_update(profile, current_user, now)
        
        await db.candidate_bank.update_one(
            {"id": existing["id"]},
            {"$set": update_data}
        )
        
        logger.info(f"[Extension] Updated candidate: {profile.name} ({existing['id']})")
        
        return CaptureResponse(
            success=True,
            action="updated",
            candidate_id=existing["id"],
            message=f"Profile updated for {profile.name}"
        )
    
    else:
        # Create new candidate with ALL data
        candidate_id = str(uuid.uuid4())
        
        candidate_data = build_complete_candidate(profile, candidate_id, current_user, now)
        
        await db.candidate_bank.insert_one(candidate_data)
        
        logger.info(f"[Extension] Created new candidate: {profile.name} ({candidate_id})")
        
        return CaptureResponse(
            success=True,
            action="created",
            candidate_id=candidate_id,
            message=f"{profile.name} added to VHC Talent OS"
        )


@extension_router.get("/stats")
async def get_extension_stats(current_user: dict = Depends(get_current_user)):
    """Get statistics for extension-captured candidates"""
    
    total_captured = await db.candidate_bank.count_documents({
        "source": "naukri_extension"
    })
    
    user_captured = await db.candidate_bank.count_documents({
        "source": "naukri_extension",
        "source_details.captured_by": current_user["id"]
    })
    
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_captured = await db.candidate_bank.count_documents({
        "source": "naukri_extension",
        "created_at": {"$gte": today_start}
    })
    
    top_capturers = []
    if current_user.get("role") == "admin":
        pipeline = [
            {"$match": {"source": "naukri_extension"}},
            {"$group": {
                "_id": "$source_details.captured_by_name",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        cursor = db.candidate_bank.aggregate(pipeline)
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


# ============== HELPER FUNCTIONS ==============

def normalize_phone(phone: str) -> str:
    """Normalize phone number for comparison"""
    if not phone:
        return None
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('91') and len(digits) > 10:
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


def build_complete_candidate(profile: CompleteNaukriProfileInput, candidate_id: str, user: dict, now: str) -> dict:
    """Build complete candidate document with ALL Naukri data"""
    
    # Extract career preferences
    career_prefs = profile.career_preferences.model_dump() if profile.career_preferences else {}
    personal = profile.personal_details.model_dump() if profile.personal_details else {}
    
    return {
        "id": candidate_id,
        
        # === BASIC INFO ===
        "name": profile.name,
        "first_name": profile.first_name,
        "middle_name": profile.middle_name,
        "last_name": profile.last_name,
        "photo_url": profile.photo_url,
        
        # === CONTACT ===
        "email": profile.email.lower() if profile.email else f"naukri_{candidate_id[:8]}@placeholder.com",
        "alternate_email": profile.alternate_email,
        "phone": profile.phone,
        "phone_normalized": normalize_phone(profile.phone) if profile.phone else None,
        "alternate_phone": profile.alternate_phone,
        
        # === PROFESSIONAL IDENTITY ===
        "headline": profile.headline,
        "resume_headline": profile.resume_headline,
        "summary": profile.profile_summary,
        
        # === CURRENT EMPLOYMENT ===
        "current_employer": profile.current_company,
        "designation": profile.current_designation,
        "department": profile.current_department,
        "industry": profile.current_industry,
        "role_category": profile.current_role_category,
        "employment_status": profile.employment_status,
        
        # === EXPERIENCE ===
        "experience_years": profile.total_experience_years or 0,
        "experience_months": profile.total_experience_months,
        "experience_display": profile.total_experience_display,
        "experience": [exp.model_dump() for exp in profile.work_experience],
        
        # === EDUCATION ===
        "highest_qualification": profile.highest_qualification,
        "highest_degree": profile.highest_degree,
        "education": [edu.model_dump() for edu in profile.education],
        
        # === SKILLS ===
        "skills": profile.key_skills,
        "skills_display": profile.key_skills_display,
        "it_skills": [skill.model_dump() for skill in profile.it_skills],
        "soft_skills": profile.soft_skills,
        "tools": profile.tools,
        
        # === CERTIFICATIONS ===
        "certifications": [cert.name for cert in profile.certifications],
        "certifications_detailed": [cert.model_dump() for cert in profile.certifications],
        
        # === PROJECTS ===
        "projects": [proj.model_dump() for proj in profile.projects],
        
        # === LANGUAGES ===
        "languages": [lang.model_dump() for lang in profile.languages],
        
        # === ONLINE PROFILES ===
        "online_profiles": [op.model_dump() for op in profile.online_profiles],
        "linkedin_url": profile.linkedin_url,
        "github_url": profile.github_url,
        "portfolio_url": profile.portfolio_url,
        
        # === PERSONAL DETAILS ===
        "date_of_birth": personal.get("date_of_birth"),
        "age": personal.get("age"),
        "gender": personal.get("gender"),
        "marital_status": personal.get("marital_status"),
        "nationality": personal.get("nationality"),
        "has_passport": personal.get("has_passport", False),
        "passport_number": personal.get("passport_number"),
        "passport_expiry": personal.get("passport_expiry"),
        
        # Address
        "permanent_address": personal.get("permanent_address"),
        "permanent_city": personal.get("permanent_city"),
        "permanent_state": personal.get("permanent_state"),
        "permanent_country": personal.get("permanent_country"),
        "permanent_pincode": personal.get("permanent_pincode"),
        "current_address": personal.get("current_address"),
        "current_city": personal.get("current_city"),
        "current_state": personal.get("current_state"),
        "current_country": personal.get("current_country"),
        "current_pincode": personal.get("current_pincode"),
        
        # Category
        "category": personal.get("category"),
        "differently_abled": personal.get("differently_abled", False),
        "disability_type": personal.get("disability_type"),
        
        # Work Permit
        "work_permit_usa": personal.get("work_permit_usa"),
        "work_permit_other": personal.get("work_permit_other"),
        
        # === CAREER PREFERENCES ===
        "current_salary": career_prefs.get("current_salary"),
        "current_salary_currency": career_prefs.get("current_salary_currency", "INR"),
        "current_salary_breakdown": career_prefs.get("current_salary_breakdown"),
        "expected_salary": career_prefs.get("expected_salary"),
        "expected_salary_currency": career_prefs.get("expected_salary_currency", "INR"),
        "expected_salary_min": career_prefs.get("expected_salary_min"),
        "expected_salary_max": career_prefs.get("expected_salary_max"),
        
        "notice_period": career_prefs.get("notice_period"),
        "notice_period_days": career_prefs.get("notice_period_days"),
        "is_serving_notice": career_prefs.get("is_serving_notice", False),
        "last_working_day": career_prefs.get("last_working_day"),
        "notice_negotiable": career_prefs.get("is_negotiable", False),
        
        "location": career_prefs.get("current_location"),
        "preferred_locations": career_prefs.get("preferred_locations", []),
        "willing_to_relocate": career_prefs.get("willing_to_relocate", False),
        "relocation_preferences": career_prefs.get("relocation_preferences", []),
        
        "preferred_job_type": career_prefs.get("preferred_job_type", []),
        "preferred_employment_type": career_prefs.get("preferred_employment_type", []),
        "preferred_shift": career_prefs.get("preferred_shift", []),
        "work_from_home": career_prefs.get("work_from_home", False),
        "remote_work_preference": career_prefs.get("remote_work_preference"),
        
        "preferred_industry": career_prefs.get("preferred_industry", []),
        "preferred_functional_area": career_prefs.get("preferred_functional_area", []),
        "preferred_role": career_prefs.get("preferred_role", []),
        "preferred_role_category": career_prefs.get("preferred_role_category", []),
        
        "preferred_company_type": career_prefs.get("preferred_company_type", []),
        "preferred_company_size": career_prefs.get("preferred_company_size"),
        "companies_to_avoid": career_prefs.get("companies_to_avoid", []),
        
        # === ADDITIONAL ===
        "accomplishments": profile.accomplishments,
        "about_me": profile.about_me,
        "additional_info": profile.additional_info,
        
        # === RESUME ===
        "has_resume": profile.has_resume,
        "resume_title": profile.resume_title,
        "resume_format": profile.resume_format,
        
        # === NAUKRI METADATA ===
        "naukri_profile_id": profile.naukri_profile_id,
        "naukri_profile_url": profile.naukri_profile_url,
        "naukri_resume_id": profile.naukri_resume_id,
        "naukri_profile_created": profile.profile_created_on,
        "naukri_profile_updated": profile.profile_last_updated,
        "naukri_last_active": profile.last_active,
        "naukri_response_rate": profile.response_rate,
        
        # === RAW DATA (for debugging) ===
        "raw_profile_text": profile.raw_profile_text,
        "raw_sections": profile.raw_sections,
        
        # === SOURCE TRACKING ===
        "source": "naukri_extension",
        "source_details": {
            "captured_by": user["id"],
            "captured_by_name": user.get("name", user.get("email")),
            "captured_by_role": user.get("role"),
            "captured_at": profile.scraped_at,
            "extension_version": "2.0.0"
        },
        
        # === TIMESTAMPS ===
        "created_at": now,
        "updated_at": now,
        "created_by": user["id"],
        "last_updated_by": user["id"],
        
        # === EMPTY ARRAYS (for compatibility) ===
        "resume_versions": [],
        "resume_fingerprints": [],
        "match_cache": [],
        "application_history": [],
        "profile_update_audit": [],
        "notes": [],
        
        # === FLAGS ===
        "cv_attached": profile.has_resume,
        "manually_edited": False,
        "bulk_import_type": None,
        "bulk_import_restricted": False,
    }


def build_complete_update(profile: CompleteNaukriProfileInput, user: dict, now: str) -> dict:
    """Build update document with ALL changed fields"""
    
    career_prefs = profile.career_preferences.model_dump() if profile.career_preferences else {}
    personal = profile.personal_details.model_dump() if profile.personal_details else {}
    
    update = {
        "updated_at": now,
        "last_updated_by": user["id"],
        
        # Always update Naukri metadata
        "naukri_profile_id": profile.naukri_profile_id,
        "naukri_profile_url": profile.naukri_profile_url,
        "naukri_profile_updated": profile.profile_last_updated,
        "naukri_last_active": profile.last_active,
        
        # Track source — mark as naukri if captured via extension
        "source": "naukri_extension",
        "source_details": {
            "captured_by": user["id"],
            "captured_by_name": user.get("name", user.get("email")),
            "captured_by_role": user.get("role"),
            "captured_at": profile.scraped_at,
            "extension_version": "2.0.0"
        },
    }
    
    # Update ALL fields if they have values
    field_mapping = {
        "name": profile.name,
        "first_name": profile.first_name,
        "middle_name": profile.middle_name,
        "last_name": profile.last_name,
        "photo_url": profile.photo_url,
        "alternate_email": profile.alternate_email,
        "phone": profile.phone,
        "alternate_phone": profile.alternate_phone,
        "headline": profile.headline,
        "resume_headline": profile.resume_headline,
        "summary": profile.profile_summary,
        "current_employer": profile.current_company,
        "designation": profile.current_designation,
        "department": profile.current_department,
        "industry": profile.current_industry,
        "role_category": profile.current_role_category,
        "employment_status": profile.employment_status,
        "experience_years": profile.total_experience_years,
        "experience_months": profile.total_experience_months,
        "experience_display": profile.total_experience_display,
        "highest_qualification": profile.highest_qualification,
        "highest_degree": profile.highest_degree,
        "skills": profile.key_skills,
        "skills_display": profile.key_skills_display,
        "soft_skills": profile.soft_skills,
        "tools": profile.tools,
        "linkedin_url": profile.linkedin_url,
        "github_url": profile.github_url,
        "portfolio_url": profile.portfolio_url,
        "accomplishments": profile.accomplishments,
        "about_me": profile.about_me,
        "additional_info": profile.additional_info,
        "has_resume": profile.has_resume,
        "resume_title": profile.resume_title,
        "resume_format": profile.resume_format,
        "naukri_response_rate": profile.response_rate,
        "raw_profile_text": profile.raw_profile_text,
        "raw_sections": profile.raw_sections,
    }
    
    for key, value in field_mapping.items():
        if value is not None:
            update[key] = value
    
    # Update phone normalized
    if profile.phone:
        update["phone_normalized"] = normalize_phone(profile.phone)
    
    # Update arrays
    if profile.work_experience:
        update["experience"] = [exp.model_dump() for exp in profile.work_experience]
    if profile.education:
        update["education"] = [edu.model_dump() for edu in profile.education]
    if profile.it_skills:
        update["it_skills"] = [skill.model_dump() for skill in profile.it_skills]
    if profile.certifications:
        update["certifications"] = [cert.name for cert in profile.certifications]
        update["certifications_detailed"] = [cert.model_dump() for cert in profile.certifications]
    if profile.projects:
        update["projects"] = [proj.model_dump() for proj in profile.projects]
    if profile.languages:
        update["languages"] = [lang.model_dump() for lang in profile.languages]
    if profile.online_profiles:
        update["online_profiles"] = [op.model_dump() for op in profile.online_profiles]
    
    # Update personal details
    for key, value in personal.items():
        if value is not None:
            update[key] = value
    
    # Update career preferences
    career_keys = [
        "current_salary", "current_salary_currency", "current_salary_breakdown",
        "expected_salary", "expected_salary_currency", "expected_salary_min", "expected_salary_max",
        "notice_period", "notice_period_days", "is_serving_notice", "last_working_day",
        "preferred_locations", "willing_to_relocate", "relocation_preferences",
        "preferred_job_type", "preferred_employment_type", "preferred_shift",
        "work_from_home", "remote_work_preference",
        "preferred_industry", "preferred_functional_area", "preferred_role", "preferred_role_category",
        "preferred_company_type", "preferred_company_size", "companies_to_avoid"
    ]
    
    for key in career_keys:
        if key in career_prefs and career_prefs[key] is not None:
            update[key] = career_prefs[key]
    
    if "current_location" in career_prefs and career_prefs["current_location"]:
        update["location"] = career_prefs["current_location"]
    
    if "is_negotiable" in career_prefs:
        update["notice_negotiable"] = career_prefs["is_negotiable"]
    
    return update
