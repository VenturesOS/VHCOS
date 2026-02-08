"""
Browser Extension API Routes
Handles candidate profile capture from Naukri extension
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, timezone
import uuid
import logging

from utils.auth import get_current_user
from config import db

logger = logging.getLogger(__name__)

extension_router = APIRouter(prefix="/extension", tags=["Browser Extension"])


# ============== MODELS ==============

class WorkExperience(BaseModel):
    company: Optional[str] = None
    designation: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    duration: Optional[str] = None
    duration_months: Optional[int] = None
    description: Optional[str] = None
    location: Optional[str] = None
    is_current: Optional[bool] = False


class Education(BaseModel):
    degree: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[str] = None
    score: Optional[str] = None
    specialization: Optional[str] = None


class DetailedSkill(BaseModel):
    skill: Optional[str] = None
    version: Optional[str] = None
    experience_years: Optional[int] = None
    proficiency: Optional[str] = None


class Certification(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    year: Optional[str] = None


class Project(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    duration: Optional[str] = None


class Language(BaseModel):
    language: Optional[str] = None
    proficiency: Optional[str] = None


class NaukriProfileCapture(BaseModel):
    """Complete profile data captured from Naukri"""
    # Source identification
    naukri_profile_id: str
    naukri_profile_url: str
    naukri_last_updated: Optional[str] = None
    scraped_at: str
    
    # Basic info
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    
    # Professional info
    headline: Optional[str] = None
    summary: Optional[str] = None
    current_company: Optional[str] = None
    current_designation: Optional[str] = None
    
    # Compensation
    current_salary: Optional[int] = None
    expected_salary: Optional[int] = None
    notice_period: Optional[str] = None
    
    # Location
    location: Optional[str] = None
    preferred_locations: List[str] = []
    
    # Experience
    experience_years: int = 0
    experience: List[WorkExperience] = []
    
    # Education
    education: List[Education] = []
    
    # Skills
    skills: List[str] = []
    skills_detailed: List[DetailedSkill] = []
    
    # Additional
    certifications: List[Certification] = []
    projects: List[Project] = []
    languages: List[Language] = []
    
    # Personal details
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    
    # Preferences
    industry_preference: List[str] = []
    functional_area: Optional[str] = None
    
    # Resume
    resume_available: bool = False


class CaptureResponse(BaseModel):
    success: bool
    action: str  # 'created', 'updated', 'exists'
    candidate_id: str
    message: str


# ============== ENDPOINTS ==============

@extension_router.post("/capture", response_model=CaptureResponse)
async def capture_profile(
    profile: NaukriProfileCapture,
    current_user: dict = Depends(get_current_user)
):
    """
    Capture and save/update a candidate profile from Naukri extension.
    
    Logic:
    1. Check if profile exists by naukri_profile_id
    2. If exists, check if Naukri data is newer
    3. If newer, update; if same/older, skip
    4. If new, create candidate record
    """
    now = datetime.now(timezone.utc).isoformat()
    
    # Check by naukri_profile_id first (most reliable)
    existing = await db.candidate_bank.find_one(
        {"naukri_profile_id": profile.naukri_profile_id},
        {"_id": 0}
    )
    
    # If not found by naukri_id, try email
    if not existing and profile.email:
        existing = await db.candidate_bank.find_one(
            {"email": profile.email.lower()},
            {"_id": 0}
        )
    
    # If not found by email, try phone
    if not existing and profile.phone:
        phone_normalized = normalize_phone(profile.phone)
        existing = await db.candidate_bank.find_one(
            {"phone_normalized": phone_normalized},
            {"_id": 0}
        )
    
    if existing:
        # Check if we should update
        should_update = should_update_profile(existing, profile)
        
        if should_update:
            # Update existing record
            update_data = build_update_data(profile, current_user, now)
            
            await db.candidate_bank.update_one(
                {"id": existing["id"]},
                {"$set": update_data}
            )
            
            # Log the update
            await log_profile_update(db, existing["id"], profile, current_user, now)
            
            logger.info(f"[Extension] Updated candidate: {profile.name} ({existing['id']})")
            
            return CaptureResponse(
                success=True,
                action="updated",
                candidate_id=existing["id"],
                message=f"Profile updated for {profile.name}"
            )
        else:
            # Profile is already up-to-date
            logger.info(f"[Extension] Candidate exists and up-to-date: {profile.name}")
            
            return CaptureResponse(
                success=True,
                action="exists",
                candidate_id=existing["id"],
                message=f"{profile.name} already up-to-date"
            )
    
    else:
        # Create new candidate
        candidate_id = str(uuid.uuid4())
        
        candidate_data = {
            "id": candidate_id,
            "email": profile.email.lower() if profile.email else f"naukri_{candidate_id[:8]}@placeholder.com",
            "name": profile.name,
            "phone": profile.phone,
            "phone_normalized": normalize_phone(profile.phone) if profile.phone else None,
            "photo_url": profile.photo_url,
            
            # Professional
            "headline": profile.headline,
            "summary": profile.summary,
            "current_employer": profile.current_company,
            "designation": profile.current_designation,
            
            # Compensation
            "current_salary": profile.current_salary,
            "expected_salary": profile.expected_salary,
            "notice_period": profile.notice_period,
            
            # Location
            "location": profile.location,
            "preferred_locations": profile.preferred_locations,
            
            # Experience
            "experience_years": profile.experience_years,
            "experience": [exp.model_dump() for exp in profile.experience],
            
            # Education
            "education": [edu.model_dump() for edu in profile.education],
            
            # Skills
            "skills": profile.skills,
            "skills_detailed": [s.model_dump() for s in profile.skills_detailed],
            
            # Additional
            "certifications": [c.name for c in profile.certifications if c.name],
            "certifications_detailed": [c.model_dump() for c in profile.certifications],
            "projects": [p.model_dump() for p in profile.projects],
            "languages": [l.model_dump() for l in profile.languages],
            
            # Personal details
            "date_of_birth": profile.date_of_birth,
            "gender": profile.gender,
            "marital_status": profile.marital_status,
            
            # Preferences
            "industry_preference": profile.industry_preference,
            "industry": profile.industry_preference[0] if profile.industry_preference else None,
            "functional_area": profile.functional_area,
            
            # Naukri-specific
            "naukri_profile_id": profile.naukri_profile_id,
            "naukri_profile_url": profile.naukri_profile_url,
            "naukri_last_updated": profile.naukri_last_updated,
            
            # Source tracking
            "source": "naukri_extension",
            "source_details": {
                "captured_by": current_user["id"],
                "captured_by_name": current_user.get("name", current_user.get("email")),
                "captured_by_role": current_user.get("role"),
                "captured_at": profile.scraped_at,
                "extension_version": "1.0.0"
            },
            
            # Visibility - captured candidates visible to capturer's team
            "visibility": {
                "employer_ids": [],
                "recruiter_ids": [current_user["id"]] if current_user.get("role") == "recruiter" else []
            },
            
            # Metadata
            "created_at": now,
            "updated_at": now,
            "created_by": current_user["id"],
            "last_updated_by": current_user["id"],
            "last_profile_updated_at": profile.naukri_last_updated or now,
            
            # Bulk import fields (not applicable but keeping schema consistent)
            "bulk_import_type": None,
            "bulk_import_restricted": False,
            "cv_attached": profile.resume_available,
            
            # Initialize empty arrays
            "resume_versions": [],
            "resume_fingerprints": [],
            "match_cache": [],
            "application_history": [],
            "profile_update_audit": [],
            "discovered_by": [{
                "user_id": current_user["id"],
                "user_role": current_user.get("role"),
                "added_at": now
            }]
        }
        
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
    
    # Total captured by extension
    total_captured = await db.candidate_bank.count_documents({
        "source": "naukri_extension"
    })
    
    # Captured by current user
    user_captured = await db.candidate_bank.count_documents({
        "source": "naukri_extension",
        "source_details.captured_by": current_user["id"]
    })
    
    # Captured today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_captured = await db.candidate_bank.count_documents({
        "source": "naukri_extension",
        "created_at": {"$gte": today_start}
    })
    
    # Top capturers (for admin)
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


# ============== HELPER FUNCTIONS ==============

def normalize_phone(phone: str) -> str:
    """Normalize phone number for comparison"""
    if not phone:
        return None
    # Remove all non-digits
    digits = ''.join(filter(str.isdigit, phone))
    # Remove country code if present
    if digits.startswith('91') and len(digits) > 10:
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


def should_update_profile(existing: dict, new_profile: NaukriProfileCapture) -> bool:
    """
    Determine if we should update the existing profile.
    Update if:
    - Naukri profile has newer last_updated date
    - OR more fields are populated in new data
    - OR salary/notice period changed
    """
    # If we have naukri_last_updated, compare dates
    if new_profile.naukri_last_updated and existing.get("naukri_last_updated"):
        try:
            new_date = parse_date(new_profile.naukri_last_updated)
            old_date = parse_date(existing.get("naukri_last_updated"))
            if new_date > old_date:
                return True
        except:
            pass
    
    # Check if key fields changed
    if new_profile.current_salary and new_profile.current_salary != existing.get("current_salary"):
        return True
    
    if new_profile.notice_period and new_profile.notice_period != existing.get("notice_period"):
        return True
    
    if new_profile.current_company and new_profile.current_company != existing.get("current_employer"):
        return True
    
    if new_profile.current_designation and new_profile.current_designation != existing.get("designation"):
        return True
    
    # Check if new data has more skills
    if len(new_profile.skills) > len(existing.get("skills", [])):
        return True
    
    # Check if new data has more experience entries
    if len(new_profile.experience) > len(existing.get("experience", [])):
        return True
    
    return False


def parse_date(date_str: str):
    """Parse various date formats"""
    from dateutil import parser
    try:
        return parser.parse(date_str)
    except:
        return datetime.min


def build_update_data(profile: NaukriProfileCapture, current_user: dict, now: str) -> dict:
    """Build the update document for MongoDB"""
    update = {
        "updated_at": now,
        "last_updated_by": current_user["id"],
        "last_profile_updated_at": profile.naukri_last_updated or now,
        
        # Always update these if available
        "naukri_profile_url": profile.naukri_profile_url,
        "naukri_last_updated": profile.naukri_last_updated,
    }
    
    # Update fields only if new data is available
    if profile.phone:
        update["phone"] = profile.phone
        update["phone_normalized"] = normalize_phone(profile.phone)
    
    if profile.photo_url:
        update["photo_url"] = profile.photo_url
    
    if profile.headline:
        update["headline"] = profile.headline
    
    if profile.summary:
        update["summary"] = profile.summary
    
    if profile.current_company:
        update["current_employer"] = profile.current_company
    
    if profile.current_designation:
        update["designation"] = profile.current_designation
    
    if profile.current_salary:
        update["current_salary"] = profile.current_salary
    
    if profile.expected_salary:
        update["expected_salary"] = profile.expected_salary
    
    if profile.notice_period:
        update["notice_period"] = profile.notice_period
    
    if profile.location:
        update["location"] = profile.location
    
    if profile.preferred_locations:
        update["preferred_locations"] = profile.preferred_locations
    
    if profile.experience_years:
        update["experience_years"] = profile.experience_years
    
    if profile.experience:
        update["experience"] = [exp.model_dump() for exp in profile.experience]
    
    if profile.education:
        update["education"] = [edu.model_dump() for edu in profile.education]
    
    if profile.skills:
        update["skills"] = profile.skills
    
    if profile.skills_detailed:
        update["skills_detailed"] = [s.model_dump() for s in profile.skills_detailed]
    
    if profile.certifications:
        update["certifications"] = [c.name for c in profile.certifications if c.name]
        update["certifications_detailed"] = [c.model_dump() for c in profile.certifications]
    
    if profile.projects:
        update["projects"] = [p.model_dump() for p in profile.projects]
    
    if profile.languages:
        update["languages"] = [l.model_dump() for l in profile.languages]
    
    if profile.date_of_birth:
        update["date_of_birth"] = profile.date_of_birth
    
    if profile.gender:
        update["gender"] = profile.gender
    
    if profile.marital_status:
        update["marital_status"] = profile.marital_status
    
    if profile.industry_preference:
        update["industry_preference"] = profile.industry_preference
        update["industry"] = profile.industry_preference[0]
    
    if profile.functional_area:
        update["functional_area"] = profile.functional_area
    
    return update


async def log_profile_update(db, candidate_id: str, profile: NaukriProfileCapture, user: dict, timestamp: str):
    """Log the profile update in audit trail"""
    audit_entry = {
        "id": str(uuid.uuid4()),
        "candidate_id": candidate_id,
        "field_changed": "naukri_extension_update",
        "source": "naukri_extension",
        "updated_by_id": user["id"],
        "updated_by_name": user.get("name", user.get("email")),
        "updated_by_role": user.get("role"),
        "timestamp": timestamp,
        "details": {
            "naukri_profile_id": profile.naukri_profile_id,
            "scraped_at": profile.scraped_at
        }
    }
    
    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$push": {"profile_update_audit": audit_entry}}
    )
