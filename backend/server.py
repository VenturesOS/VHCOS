from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, status, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import hashlib
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import aiofiles
import fitz  # PyMuPDF for PDF text extraction

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'vhc-secret-key')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get('ACCESS_TOKEN_EXPIRE_MINUTES', 1440))

# Create upload directory
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Create the main app
app = FastAPI(title="VHC Talent OS API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

security = HTTPBearer()

# ============== MODELS ==============

class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: str = Field(..., pattern="^(admin|recruiter|employer|candidate)$")

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    name: str
    role: str
    company_id: Optional[str] = None
    phone: Optional[str] = None
    created_at: str
    is_active: bool = True
    requires_password_reset: bool = False

class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    company_id: Optional[str] = None  # For assigning employer to recruiter

class AdminUserCreate(BaseModel):
    """Admin-only user creation with role specification"""
    email: EmailStr
    password: str
    name: str
    role: str  # employer, recruiter, candidate
    phone: Optional[str] = None
    company_id: Optional[str] = None

class AdminPasswordReset(BaseModel):
    """Admin-initiated password reset for any user"""
    new_password: str

class PasswordReset(BaseModel):
    current_password: str
    new_password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    requires_password_reset: bool = False

class JobBase(BaseModel):
    title: str
    description: str
    requirements: Optional[str] = None
    location: str
    job_type: str = Field(..., pattern="^(full-time|part-time|contract|remote)$")
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    department: Optional[str] = None
    public_company_alias: Optional[str] = None  # Masked company name for candidates

class JobCreate(JobBase):
    company_id: Optional[str] = None  # Admin/Employer can specify company

class JobResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    description: str
    requirements: Optional[str] = None
    location: str
    job_type: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    department: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    public_company_alias: Optional[str] = None  # Masked name for candidates
    posted_by: str
    posted_by_role: Optional[str] = None
    status: str = "active"  # draft, pending_approval, active, on_hold, closed, archived
    team_id: Optional[str] = None
    approval_history: List[dict] = []  # Audit trail for state transitions
    created_at: str
    updated_at: Optional[str] = None
    applicant_count: int = 0

class JobUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    department: Optional[str] = None
    public_company_alias: Optional[str] = None
    status: Optional[str] = None

# Job State Transition Model
class JobStateTransition(BaseModel):
    new_status: str = Field(..., pattern="^(draft|pending_approval|active|on_hold|closed|archived)$")
    reason: Optional[str] = None

class CandidateProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    name: str
    email: str
    phone: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    skills: List[str] = []
    experience: List[dict] = []
    education: List[dict] = []
    resume_url: Optional[str] = None
    created_at: str
    updated_at: str

class CandidateProfileUpdate(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[List[str]] = None
    experience: Optional[List[dict]] = None
    education: Optional[List[dict]] = None
    phone: Optional[str] = None

class ApplicationBase(BaseModel):
    job_id: str
    cover_letter: Optional[str] = None

class ApplicationCreate(ApplicationBase):
    pass

class ApplicationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    job_id: str
    candidate_id: str
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_phone: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    cover_letter: Optional[str] = None
    current_salary: Optional[int] = None  # INR
    notice_period: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[int] = None
    experience_summary: Optional[str] = None  # Brief summary text
    location: Optional[str] = None
    headline: Optional[str] = None
    resume_url: Optional[str] = None
    status: str = "applied"
    stage: str = "applied"
    notes: List[dict] = []
    edit_history: List[dict] = []  # Audit trail
    last_edited_by: Optional[dict] = None  # {name, role, timestamp}
    manually_edited: bool = False  # Flag to prevent parsing overwrites
    applied_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: str

class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    stage: Optional[str] = None
    rejection_reason: Optional[str] = None  # For tracking why rejected/not qualified

class ApplicationDetailUpdate(BaseModel):
    """Model for controlled editing of applicant details by Admin/Employer/Recruiter"""
    current_salary: Optional[int] = None  # INR
    notice_period: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_summary: Optional[str] = None  # Brief summary of experience

class AuditLogEntry(BaseModel):
    """Audit log entry for tracking changes"""
    field: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    updated_by_id: str
    updated_by_name: str
    updated_by_role: str
    timestamp: str

class NoteCreate(BaseModel):
    content: str

class CompanyBase(BaseModel):
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None

class CompanyCreate(CompanyBase):
    pass

class CompanyResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    assigned_employer_id: Optional[str] = None  # Employer assigned to this company
    assigned_employer_name: Optional[str] = None
    status: str = "active"  # active, disabled
    created_at: str

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    assigned_employer_id: Optional[str] = None
    status: Optional[str] = None

# ============== TEAM & HIERARCHY MODELS ==============

class TeamCreate(BaseModel):
    name: str
    employer_id: str
    recruiter_ids: List[str] = []
    company_ids: List[str] = []

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    recruiter_ids: Optional[List[str]] = None
    company_ids: Optional[List[str]] = None
    status: Optional[str] = None

class TeamResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    employer_id: str
    employer_name: Optional[str] = None
    recruiter_ids: List[str] = []
    recruiter_names: List[str] = []
    company_ids: List[str] = []
    company_names: List[str] = []
    active_jobs_count: int = 0
    status: str = "active"  # active, disabled
    created_at: str
    updated_at: Optional[str] = None

# ============== REFERRAL MODELS ==============

class ReferralCreate(BaseModel):
    job_id: str
    candidate_name: str
    candidate_email: EmailStr
    candidate_phone: str
    resume_url: Optional[str] = None
    note: Optional[str] = None  # "Why this candidate?"

class ReferralResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    job_id: str
    job_title: Optional[str] = None
    referrer_id: str
    referrer_name: Optional[str] = None
    candidate_name: str
    candidate_email: str
    candidate_phone: str
    resume_url: Optional[str] = None
    note: Optional[str] = None
    status: str = "submitted"  # submitted, validated, linked, in_process, outcome_reached, closed
    linked_candidate_id: Optional[str] = None  # Links to candidate_bank if validated
    linked_application_id: Optional[str] = None  # Links to application if applied
    status_history: List[dict] = []  # Audit trail
    created_at: str
    updated_at: Optional[str] = None

class ReferralStatusUpdate(BaseModel):
    new_status: str = Field(..., pattern="^(submitted|validated|linked|in_process|outcome_reached|closed)$")
    reason: Optional[str] = None

class MessageBase(BaseModel):
    recipient_id: str
    subject: str
    content: str

class MessageCreate(MessageBase):
    pass

class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    sender_id: str
    sender_name: Optional[str] = None
    recipient_id: str
    recipient_name: Optional[str] = None
    subject: str
    content: str
    is_read: bool = False
    created_at: str

# ============== CANDIDATE DATA BANK MODELS ==============

class CandidateBankRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    name: str
    phone: Optional[str] = None
    phone_normalized: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    skills: List[str] = []
    experience_years: int = 0
    experience: List[dict] = []
    education: List[dict] = []
    location: Optional[str] = None  # MANDATORY for data completeness
    certifications: List[str] = []
    active_resume_id: Optional[str] = None
    resume_versions: List[dict] = []
    resume_fingerprints: List[str] = []
    resume_url: Optional[str] = None
    current_salary: Optional[int] = None  # MANDATORY - INR
    notice_period: Optional[str] = None  # MANDATORY
    source: str = "self"  # self, employer, recruiter, parsing, admin, referral
    linked_user_id: Optional[str] = None
    visibility: dict = {}  # employer_ids, recruiter_ids with access
    match_cache: List[dict] = []  # cached match results
    created_at: str
    updated_at: str
    created_by: Optional[str] = None
    last_updated_by: Optional[str] = None
    # Profile freshness metadata (system-managed)
    last_profile_updated_at: Optional[str] = None
    last_application_date: Optional[str] = None
    # Activity history for internal tracking
    application_history: List[dict] = []  # Internal only - not exposed to candidates
    profile_update_audit: List[dict] = []  # Audit log for salary, notice, location, experience changes

class CandidateBankUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[int] = None
    experience: Optional[List[dict]] = None
    education: Optional[List[dict]] = None
    location: Optional[str] = None
    certifications: Optional[List[str]] = None
    current_salary: Optional[int] = None  # INR
    notice_period: Optional[str] = None

class AuditLogEntry(BaseModel):
    id: str
    candidate_id: str
    field_changed: str
    old_value: Any
    new_value: Any
    updated_by_role: str
    updated_by_id: str
    updated_by_name: str
    timestamp: str
    source: str  # self_update, employer_update, recruiter_update, resume_parsing

class MatchRequest(BaseModel):
    job_id: Optional[str] = None
    jd_text: Optional[str] = None
    must_have_location: Optional[str] = None
    must_have_qualification: Optional[str] = None
    must_have_skills: Optional[List[str]] = None
    min_experience: Optional[int] = None
    max_experience: Optional[int] = None

class MatchResult(BaseModel):
    candidate_id: str
    candidate_name: str
    candidate_email: str
    score: int
    skill_match_score: Optional[int] = None
    experience_match_score: Optional[int] = None
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    strengths: List[str] = []
    gaps: List[str] = []
    explanation: str
    filtered_out: bool = False
    filter_reason: Optional[str] = None

class JobMatchForCandidate(BaseModel):
    job_id: str
    job_title: str
    company_name: Optional[str] = None
    location: str
    score: int
    explanation: str
    matched_skills: List[str] = []

# ============== JOB ALERT MODELS ==============

class JobAlertPreferences(BaseModel):
    """Candidate's job alert subscription preferences"""
    model_config = ConfigDict(extra="ignore")
    id: str
    candidate_id: str
    candidate_email: str
    is_active: bool = True
    email_enabled: bool = True
    skills: List[str] = []  # Skills to match against (from resume, editable)
    location_preference: Optional[str] = None
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    job_types: List[str] = []  # full-time, part-time, contract, remote
    frequency: str = "instant"  # instant, daily, weekly
    whatsapp_opt_in: bool = False
    whatsapp_number: Optional[str] = None
    whatsapp_opt_in_timestamp: Optional[str] = None
    notification_channels: List[str] = ["email"]  # email, whatsapp
    created_at: str
    updated_at: str

class JobAlertCreate(BaseModel):
    """Create or update job alert preferences"""
    skills: Optional[List[str]] = None
    location_preference: Optional[str] = None
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    job_types: Optional[List[str]] = None
    frequency: Optional[str] = "instant"
    email_enabled: Optional[bool] = True

class WhatsAppOptIn(BaseModel):
    """WhatsApp opt-in request"""
    whatsapp_number: str
    opt_in: bool = True

class NotificationLogEntry(BaseModel):
    """Log entry for sent notifications"""
    model_config = ConfigDict(extra="ignore")
    id: str
    type: str  # job_match, weekly_digest, alert_confirmation
    recipient_id: str
    recipient_email: str
    channel: str  # email, whatsapp
    job_id: Optional[str] = None
    status: str  # sent, failed, skipped
    details: Dict = {}
    created_at: str

# ============== COMMERCIAL INTELLIGENCE MODELS ==============

class CommercialCreate(BaseModel):
    """Commercial configuration for a company"""
    company_id: str
    commercial_name: str
    type: str = Field(..., pattern="^(percentage|fixed|level_based)$")
    # For percentage type
    fee_percentage: Optional[float] = None  # e.g., 8.33 for 8.33%
    # For fixed type
    fixed_amount: Optional[float] = None
    # For level_based type
    level_config: Optional[Dict[str, float]] = None  # {"junior": 8.0, "mid": 10.0, "senior": 12.0, "leadership": 15.0}
    # Salary range (optional, for scoped commercials)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    # Job level (optional, for level_based)
    job_level: Optional[str] = None
    # Validity
    effective_from: str
    effective_to: Optional[str] = None
    is_active: bool = True

class CommercialUpdate(BaseModel):
    commercial_name: Optional[str] = None
    type: Optional[str] = None
    fee_percentage: Optional[float] = None
    fixed_amount: Optional[float] = None
    level_config: Optional[Dict[str, float]] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_level: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    is_active: Optional[bool] = None

class CommercialResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    company_id: str
    company_name: Optional[str] = None
    commercial_name: str
    type: str
    fee_percentage: Optional[float] = None
    fixed_amount: Optional[float] = None
    level_config: Optional[Dict[str, float]] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_level: Optional[str] = None
    effective_from: str
    effective_to: Optional[str] = None
    is_active: bool = True
    created_at: str
    created_by: str
    updated_at: Optional[str] = None
    audit_log: List[dict] = []

class RevenueEntry(BaseModel):
    """Revenue calculation for an application"""
    application_id: str
    job_id: str
    candidate_id: str
    offered_salary: float
    commercial_id: str
    commercial_type: str
    fee_percentage: Optional[float] = None
    fixed_amount: Optional[float] = None
    calculated_revenue: float
    manual_override: Optional[float] = None
    final_revenue: float
    stage: str  # offered, joined
    is_closed: bool = False

class RevenueUpdate(BaseModel):
    offered_salary: Optional[float] = None
    manual_override: Optional[float] = None  # Admin only

class JDParseRequest(BaseModel):
    """Request to parse a job description"""
    jd_text: Optional[str] = None
    # File upload handled separately

class JDParseResponse(BaseModel):
    """Parsed job description fields"""
    title: Optional[str] = None
    skills: List[str] = []
    experience_years: Optional[int] = None
    location: Optional[str] = None
    job_level: Optional[str] = None  # junior, mid, senior, leadership
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    summary: Optional[str] = None
    responsibilities: List[str] = []
    requirements: List[str] = []
    raw_text: str = ""

class MandateAssignment(BaseModel):
    """Assign recruiters to a mandate/job"""
    job_id: str
    recruiter_ids: List[str]

# ============== DATA GOVERNANCE HELPERS ==============

def validate_mandatory_candidate_fields(data: dict, context: str = "candidate") -> List[str]:
    """
    Validate mandatory candidate fields for data completeness.
    Returns list of missing field errors.
    """
    errors = []
    
    # Current Salary - MANDATORY
    current_salary = data.get("current_salary")
    if current_salary is None or (isinstance(current_salary, (int, float)) and current_salary <= 0):
        errors.append(f"Current salary is mandatory and must be greater than 0")
    
    # Notice Period - MANDATORY
    notice_period = data.get("notice_period")
    if not notice_period or (isinstance(notice_period, str) and not notice_period.strip()):
        errors.append(f"Notice period is mandatory")
    
    # Location - MANDATORY
    location = data.get("location")
    if not location or (isinstance(location, str) and not location.strip()):
        errors.append(f"Location is mandatory")
    
    # Experience Years - MANDATORY (can be 0 for freshers)
    experience_years = data.get("experience_years")
    if experience_years is None:
        errors.append(f"Experience (years) is mandatory")
    
    return errors


def create_profile_audit_entry(
    field: str,
    old_value: Any,
    new_value: Any,
    user_id: str,
    user_name: str,
    user_role: str,
    source: str = "manual_update"
) -> dict:
    """
    Create an audit log entry for profile field changes.
    Tracks changes to: salary, notice_period, location, experience_years
    """
    return {
        "id": str(uuid.uuid4()),
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "changed_by_id": user_id,
        "changed_by_name": user_name,
        "changed_by_role": user_role,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def update_candidate_freshness(candidate_id: str, update_type: str = "profile"):
    """
    Update profile freshness metadata.
    update_type: 'profile' or 'application'
    """
    now = datetime.now(timezone.utc).isoformat()
    update_fields = {}
    
    if update_type == "profile":
        update_fields["last_profile_updated_at"] = now
    elif update_type == "application":
        update_fields["last_application_date"] = now
    
    update_fields["updated_at"] = now
    
    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$set": update_fields}
    )


async def add_application_to_history(candidate_id: str, application_data: dict):
    """
    Add an application entry to candidate's internal history.
    This is visible ONLY to Admin/Employer/Recruiter.
    """
    history_entry = {
        "application_id": application_data.get("id"),
        "job_id": application_data.get("job_id"),
        "job_title": application_data.get("job_title"),
        "company_name": application_data.get("company_name"),  # Real name for internal use
        "source": application_data.get("source", "self"),  # self, recruiter, employer, admin, referral
        "applied_at": application_data.get("created_at"),
        "current_stage": application_data.get("stage", "applied"),
        "final_outcome": None,  # Will be updated on closure
        "closure_date": None
    }
    
    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {
            "$push": {"application_history": history_entry},
            "$set": {"last_application_date": datetime.now(timezone.utc).isoformat()}
        }
    )


async def update_application_in_history(candidate_id: str, application_id: str, stage: str, outcome: str = None):
    """
    Update an application's stage/outcome in candidate's history.
    """
    update_data = {"application_history.$.current_stage": stage}
    
    if outcome:  # hired, rejected, dropped
        update_data["application_history.$.final_outcome"] = outcome
        update_data["application_history.$.closure_date"] = datetime.now(timezone.utc).isoformat()
    
    await db.candidate_bank.update_one(
        {"id": candidate_id, "application_history.application_id": application_id},
        {"$set": update_data}
    )


# ============== HELPERS ==============

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_role(allowed_roles: List[str]):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

# ============== AUTH ROUTES ==============

@api_router.post("/auth/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Validate password strength
    if len(user_data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "name": user_data.name,
        "role": user_data.role,
        "password": hash_password(user_data.password),
        "phone": None,
        "company_id": None,
        "is_active": True,
        "requires_password_reset": False,
        "created_at": now
    }
    
    await db.users.insert_one(user_doc)
    
    # Create candidate profile if role is candidate
    if user_data.role == "candidate":
        profile_doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": user_data.name,
            "email": user_data.email,
            "phone": None,
            "headline": None,
            "summary": None,
            "skills": [],
            "experience": [],
            "education": [],
            "resume_url": None,
            "created_at": now,
            "updated_at": now
        }
        await db.candidate_profiles.insert_one(profile_doc)
    
    access_token = create_access_token({"sub": user_id, "role": user_data.role})
    
    user_response = UserResponse(
        id=user_id,
        email=user_data.email,
        name=user_data.name,
        role=user_data.role,
        created_at=now,
        requires_password_reset=False
    )
    
    return TokenResponse(access_token=access_token, user=user_response, requires_password_reset=False)

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled")
    
    requires_reset = user.get("requires_password_reset", False)
    
    access_token = create_access_token({"sub": user["id"], "role": user["role"]})
    
    user_response = UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        role=user["role"],
        company_id=user.get("company_id"),
        phone=user.get("phone"),
        created_at=user["created_at"],
        requires_password_reset=requires_reset
    )
    
    return TokenResponse(access_token=access_token, user=user_response, requires_password_reset=requires_reset)

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)

@api_router.post("/auth/reset-password")
async def reset_password(reset_data: PasswordReset, current_user: dict = Depends(get_current_user)):
    """Reset password - validates current password and sets new one"""
    # Get user with password
    user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0})
    
    if not verify_password(reset_data.current_password, user["password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    if len(reset_data.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    
    if reset_data.current_password == reset_data.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")
    
    # Update password and clear reset flag
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {
            "password": hash_password(reset_data.new_password),
            "requires_password_reset": False
        }}
    )
    
    return {"message": "Password reset successfully"}

# ============== USER MANAGEMENT (ADMIN) ==============

@api_router.get("/users", response_model=List[UserResponse])
async def get_users(current_user: dict = Depends(require_role(["admin"]))):
    users = await db.users.find({}, {"_id": 0, "password": 0}).to_list(1000)
    return [UserResponse(**u) for u in users]

@api_router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, current_user: dict = Depends(require_role(["admin"]))):
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)

@api_router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, update_data: UserUpdate, current_user: dict = Depends(require_role(["admin"]))):
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = await db.users.update_one({"id": user_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    return UserResponse(**user)

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(require_role(["admin"]))):
    # Soft delete - set is_active to False instead of hard delete
    result = await db.users.update_one(
        {"id": user_id}, 
        {"$set": {"is_active": False, "deleted_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deactivated successfully"}

@api_router.post("/admin/users", response_model=UserResponse)
async def admin_create_user(user_data: AdminUserCreate, current_user: dict = Depends(require_role(["admin"]))):
    """Admin-only endpoint to create users with any role"""
    # Validate role
    allowed_roles = ["employer", "recruiter", "candidate"]
    if user_data.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(allowed_roles)}")
    
    # Check if email already exists
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "name": user_data.name,
        "role": user_data.role,
        "password": hash_password(user_data.password),
        "phone": user_data.phone,
        "company_id": user_data.company_id,
        "is_active": True,
        "requires_password_reset": False,
        "created_at": now,
        "created_by": current_user["id"]
    }
    
    await db.users.insert_one(user_doc)
    
    # Create candidate profile if role is candidate
    if user_data.role == "candidate":
        profile_doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": user_data.name,
            "email": user_data.email,
            "phone": user_data.phone,
            "headline": None,
            "summary": None,
            "skills": [],
            "experience": [],
            "education": [],
            "resume_url": None,
            "created_at": now,
            "updated_at": now
        }
        await db.candidates.insert_one(profile_doc)
    
    return UserResponse(**{k: v for k, v in user_doc.items() if k != "password" and k != "_id"})

@api_router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_user_password(user_id: str, reset_data: AdminPasswordReset, current_user: dict = Depends(require_role(["admin"]))):
    """Admin-only endpoint to reset any user's password"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Cannot reset admin passwords through this endpoint for security
    if user.get("role") == "admin" and user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Cannot reset another admin's password")
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password": hash_password(reset_data.new_password),
            "requires_password_reset": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Password reset successfully", "user_id": user_id}

@api_router.post("/admin/users/{user_id}/toggle-status")
async def admin_toggle_user_status(user_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """Admin-only endpoint to activate/deactivate a user"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Cannot deactivate own account
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    
    new_status = not user.get("is_active", True)
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": f"User {'activated' if new_status else 'deactivated'} successfully", "is_active": new_status}

@api_router.get("/admin/employers")
async def get_employers_list(current_user: dict = Depends(require_role(["admin"]))):
    """Get list of all employers for recruiter assignment"""
    employers = await db.users.find({"role": "employer"}, {"_id": 0, "password": 0}).to_list(1000)
    return employers

@api_router.post("/admin/assign-recruiter")
async def assign_recruiter_to_employer(
    recruiter_id: str,
    employer_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Assign a recruiter to an employer"""
    recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"})
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")
    
    employer = await db.users.find_one({"id": employer_id, "role": "employer"})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    
    # Update recruiter with employer assignment
    await db.users.update_one(
        {"id": recruiter_id},
        {"$set": {"assigned_employer_id": employer_id, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": "Recruiter assigned to employer successfully"}

# ============== ADMIN PIPELINE VIEW ==============

@api_router.get("/admin/pipeline")
async def get_admin_pipeline(
    employer_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    job_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Admin collective pipeline view across all employers and recruiters.
    Read-only aggregated view for management oversight.
    """
    # Build filter
    match_filter = {}
    
    if job_id:
        match_filter["job_id"] = job_id
    
    # Get all applications
    applications = await db.applications.find(match_filter, {"_id": 0}).to_list(10000)
    
    # Get job details for filtering and display
    job_ids = list(set(app["job_id"] for app in applications))
    jobs = await db.jobs.find({"id": {"$in": job_ids}}, {"_id": 0}).to_list(1000)
    jobs_map = {j["id"]: j for j in jobs}
    
    # Apply employer filter if specified
    if employer_id:
        employer_job_ids = [j["id"] for j in jobs if j.get("company_id") == employer_id or j.get("created_by") == employer_id]
        applications = [app for app in applications if app["job_id"] in employer_job_ids]
    
    # Apply recruiter filter if specified
    if recruiter_id:
        recruiter_job_ids = [j["id"] for j in jobs if j.get("created_by") == recruiter_id or j.get("assigned_recruiter") == recruiter_id]
        applications = [app for app in applications if app["job_id"] in recruiter_job_ids]
    
    # Define all pipeline stages
    all_stages = ["applied", "shortlisted", "interview", "offered", "hired", "rejected", "on_hold", "over_budget", "not_qualified"]
    
    # Group applications by stage
    pipeline_data = {stage: [] for stage in all_stages}
    
    for app in applications:
        stage = app.get("stage", "applied")
        if stage not in pipeline_data:
            stage = "applied"
        
        job = jobs_map.get(app["job_id"], {})
        
        pipeline_data[stage].append({
            "id": app["id"],
            "candidate_name": app.get("candidate_name", "Unknown"),
            "candidate_email": app.get("candidate_email"),
            "job_title": app.get("job_title") or job.get("title", "Unknown"),
            "job_id": app["job_id"],
            "company_name": job.get("company_name", ""),
            "match_score": app.get("match_score", 0),
            "applied_at": app.get("created_at"),
            "current_salary": app.get("current_salary"),
            "notice_period": app.get("notice_period"),
            "resume_url": app.get("resume_url")
        })
    
    # Calculate stage counts
    stage_counts = {stage: len(apps) for stage, apps in pipeline_data.items()}
    
    # Get filter options
    employers = await db.users.find({"role": "employer"}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    recruiters = await db.users.find({"role": "recruiter"}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    
    return {
        "pipeline": pipeline_data,
        "stage_counts": stage_counts,
        "total_applications": len(applications),
        "filters": {
            "employers": employers,
            "recruiters": recruiters,
            "jobs": [{"id": j["id"], "title": j.get("title", "Untitled")} for j in jobs]
        }
    }

# ============== CV DOWNLOAD ENDPOINT ==============

@api_router.get("/applications/{app_id}/resume")
async def download_application_resume(
    app_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Download candidate resume with proper naming: Firstname_Lastname_VHC.ext
    
    Permission checks:
    - Admin: Can access any resume
    - Employer/Recruiter: Only resumes for candidates who applied to their jobs
    """
    # Get application
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Permission check for non-admin
    if current_user["role"] != "admin":
        job = await db.jobs.find_one({"id": application["job_id"]}, {"_id": 0})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Check if user has access to this job
        has_access = (
            job.get("created_by") == current_user["id"] or
            job.get("company_id") == current_user.get("company_id") or
            job.get("assigned_recruiter") == current_user["id"]
        )
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied to this resume")
    
    # Get resume URL
    resume_url = application.get("resume_url")
    if not resume_url:
        # Try to get from candidate profile (check both candidates and candidate_bank)
        if application.get("candidate_id"):
            candidate = await db.candidates.find_one({"id": application["candidate_id"]}, {"_id": 0})
            if not candidate:
                candidate = await db.candidate_bank.find_one({"id": application["candidate_id"]}, {"_id": 0})
            if candidate:
                resume_url = candidate.get("resume_url")
    
    if not resume_url:
        raise HTTPException(status_code=404, detail="Resume not found for this application")
    
    # Extract filename from URL
    original_filename = resume_url.split("/")[-1]
    file_path = UPLOAD_DIR / original_filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    # Generate proper download filename: Firstname_Lastname_VHC.ext
    candidate_name = application.get("candidate_name", "Unknown_Candidate")
    name_parts = candidate_name.strip().split()
    
    if len(name_parts) >= 2:
        first_name = name_parts[0]
        last_name = name_parts[-1]
    elif len(name_parts) == 1:
        first_name = name_parts[0]
        last_name = "Unknown"
    else:
        first_name = "Unknown"
        last_name = "Candidate"
    
    # Clean names (remove special characters, replace spaces with underscore)
    import re
    first_name = re.sub(r'[^a-zA-Z0-9]', '', first_name)
    last_name = re.sub(r'[^a-zA-Z0-9]', '', last_name)
    
    # Get file extension
    file_ext = file_path.suffix
    
    # Create download filename
    download_filename = f"{first_name}_{last_name}_VHC{file_ext}"
    
    return FileResponse(
        file_path,
        filename=download_filename,
        media_type="application/octet-stream"
    )

@api_router.get("/candidates/{candidate_id}/resume")
async def download_candidate_resume(
    candidate_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Download resume directly from candidate bank.
    Same naming convention: Firstname_Lastname_VHC.ext
    """
    # Get candidate from candidate bank
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        # Try candidates collection
        candidate = await db.candidates.find_one({"id": candidate_id}, {"_id": 0})
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Get resume URL
    resume_url = candidate.get("resume_url")
    if not resume_url:
        raise HTTPException(status_code=404, detail="Resume not found for this candidate")
    
    # Extract filename from URL
    original_filename = resume_url.split("/")[-1]
    file_path = UPLOAD_DIR / original_filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    # Generate download filename
    candidate_name = candidate.get("name", "Unknown_Candidate")
    name_parts = candidate_name.strip().split()
    
    if len(name_parts) >= 2:
        first_name = name_parts[0]
        last_name = name_parts[-1]
    elif len(name_parts) == 1:
        first_name = name_parts[0]
        last_name = "Unknown"
    else:
        first_name = "Unknown"
        last_name = "Candidate"
    
    import re
    first_name = re.sub(r'[^a-zA-Z0-9]', '', first_name)
    last_name = re.sub(r'[^a-zA-Z0-9]', '', last_name)
    
    file_ext = file_path.suffix
    download_filename = f"{first_name}_{last_name}_VHC{file_ext}"
    
    return FileResponse(
        file_path,
        filename=download_filename,
        media_type="application/octet-stream"
    )

# ============== COMPANY ROUTES ==============

@api_router.post("/companies", response_model=CompanyResponse)
async def create_company(company_data: CompanyCreate, current_user: dict = Depends(require_role(["admin", "employer"]))):
    company_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    company_doc = {
        "id": company_id,
        **company_data.model_dump(),
        "created_by": current_user["id"],
        "created_at": now
    }
    
    await db.companies.insert_one(company_doc)
    
    # Link employer to company
    if current_user["role"] == "employer":
        await db.users.update_one({"id": current_user["id"]}, {"$set": {"company_id": company_id}})
    
    return CompanyResponse(**company_doc)

@api_router.get("/companies", response_model=List[CompanyResponse])
async def get_companies(current_user: dict = Depends(get_current_user)):
    companies = await db.companies.find({}, {"_id": 0}).to_list(1000)
    return [CompanyResponse(**c) for c in companies]

@api_router.get("/companies/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: str, current_user: dict = Depends(get_current_user)):
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyResponse(**company)

# ============== JOB ROUTES ==============

@api_router.post("/jobs", response_model=JobResponse)
async def create_job(job_data: JobCreate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    """
    Create a new job with approval workflow:
    - Admin/Employer: Job goes directly to 'active' status
    - Recruiter: Job goes to 'pending_approval' status, needs Employer/Admin approval
    """
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Determine company_id
    company_id = job_data.company_id or current_user.get("company_id", "default")
    company_name = None
    
    if company_id and company_id != "default":
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if company:
            company_name = company.get("name")
            # Verify employer is assigned to this company if not admin
            if current_user["role"] == "employer":
                if company.get("assigned_employer_id") and company.get("assigned_employer_id") != current_user["id"]:
                    raise HTTPException(status_code=403, detail="You are not assigned to this company")
    
    # Determine initial status based on role
    if current_user["role"] == "recruiter":
        initial_status = "pending_approval"
    else:
        initial_status = "active"
    
    # Validate public_company_alias for active jobs (mandatory for public visibility)
    if initial_status == "active" and not job_data.public_company_alias:
        # Default alias if not provided
        job_data_dict = job_data.model_dump()
        job_data_dict["public_company_alias"] = "Confidential Client"
    else:
        job_data_dict = job_data.model_dump()
    
    # Find team for this employer/recruiter
    team_id = None
    if current_user["role"] == "recruiter":
        # Find team where this recruiter is assigned
        team = await db.teams.find_one({"recruiter_ids": current_user["id"], "status": "active"}, {"_id": 0})
        if team:
            team_id = team["id"]
    elif current_user["role"] == "employer":
        # Find team for this employer
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        if team:
            team_id = team["id"]
    
    job_doc = {
        "id": job_id,
        **job_data_dict,
        "company_id": company_id,
        "company_name": company_name,
        "posted_by": current_user["id"],
        "posted_by_role": current_user["role"],
        "status": initial_status,
        "team_id": team_id,
        "applicant_count": 0,
        "approval_history": [{
            "status": initial_status,
            "changed_by": current_user["id"],
            "changed_by_name": current_user["name"],
            "changed_by_role": current_user["role"],
            "timestamp": now,
            "reason": "Job created"
        }],
        "created_at": now,
        "updated_at": now
    }
    
    await db.jobs.insert_one(job_doc)
    
    logging.info(f"Job {job_id} created by {current_user['name']} ({current_user['role']}) with status {initial_status}")
    
    return JobResponse(**job_doc)

@api_router.post("/jobs/{job_id}/transition", response_model=JobResponse)
async def transition_job_status(
    job_id: str, 
    transition: JobStateTransition, 
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Transition job status with audit logging.
    Valid transitions:
    - draft -> pending_approval, active (admin only)
    - pending_approval -> active, draft (rejected back to draft)
    - active -> on_hold, closed
    - on_hold -> active, closed
    - closed -> archived (admin only)
    - archived -> (no transitions, final state)
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    current_status = job.get("status", "active")
    new_status = transition.new_status
    
    # Define valid transitions
    valid_transitions = {
        "draft": ["pending_approval", "active"],
        "pending_approval": ["active", "draft", "on_hold"],
        "active": ["on_hold", "closed"],
        "on_hold": ["active", "closed"],
        "closed": ["archived"],
        "archived": []  # No transitions from archived
    }
    
    # Admin can do any transition except from archived
    if current_user["role"] != "admin":
        if new_status not in valid_transitions.get(current_status, []):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid transition from {current_status} to {new_status}"
            )
        # Employer can only approve their team's jobs
        if current_user["role"] == "employer":
            team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
            if team and job.get("team_id") != team["id"]:
                # Check if job was posted by a recruiter in their team
                if job.get("posted_by") not in team.get("recruiter_ids", []):
                    raise HTTPException(status_code=403, detail="You can only approve jobs from your team")
    else:
        # Admin can't transition from archived
        if current_status == "archived":
            raise HTTPException(status_code=400, detail="Cannot transition from archived state")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Create audit entry
    audit_entry = {
        "from_status": current_status,
        "to_status": new_status,
        "changed_by": current_user["id"],
        "changed_by_name": current_user["name"],
        "changed_by_role": current_user["role"],
        "timestamp": now,
        "reason": transition.reason or f"Status changed from {current_status} to {new_status}"
    }
    
    # Update job
    await db.jobs.update_one(
        {"id": job_id},
        {
            "$set": {"status": new_status, "updated_at": now},
            "$push": {"approval_history": audit_entry}
        }
    )
    
    logging.info(f"Job {job_id} transitioned from {current_status} to {new_status} by {current_user['name']}")
    
    updated_job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return JobResponse(**updated_job)

@api_router.get("/jobs/pending-approval", response_model=List[JobResponse])
async def get_pending_approval_jobs(current_user: dict = Depends(require_role(["admin", "employer"]))):
    """Get jobs pending approval (for Admin and Employers)"""
    query = {"status": "pending_approval"}
    
    if current_user["role"] == "employer":
        # Get jobs from recruiters in this employer's team
        team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
        if team:
            query["$or"] = [
                {"team_id": team["id"]},
                {"posted_by": {"$in": team.get("recruiter_ids", [])}}
            ]
        else:
            # No team, return empty
            return []
    
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(1000)
    return [JobResponse(**j) for j in jobs]

@api_router.get("/jobs", response_model=List[JobResponse])
async def get_jobs(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    
    if current_user["role"] == "employer":
        # Employer sees jobs from their team
        team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
        if team:
            query["$or"] = [
                {"posted_by": current_user["id"]},
                {"team_id": team["id"]}
            ]
        else:
            query["posted_by"] = current_user["id"]
    elif current_user["role"] == "recruiter":
        # Recruiter sees their assigned jobs and jobs they posted
        team = await db.teams.find_one({"recruiter_ids": current_user["id"]}, {"_id": 0})
        if team:
            query["$or"] = [
                {"posted_by": current_user["id"]},
                {"team_id": team["id"]}
            ]
        else:
            query["posted_by"] = current_user["id"]
    elif current_user["role"] == "candidate":
        query["status"] = "active"
    # Admin sees all jobs
    
    if status:
        query["status"] = status
    
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(1000)
    return [JobResponse(**j) for j in jobs]

@api_router.get("/jobs/browse", response_model=List[JobResponse])
async def browse_jobs(search: Optional[str] = None, location: Optional[str] = None, job_type: Optional[str] = None):
    """Public job browsing - only shows ACTIVE jobs with masked company names"""
    query = {"status": "active"}
    
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    if location:
        query["location"] = {"$regex": location, "$options": "i"}
    if job_type:
        query["job_type"] = job_type
    
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(100)
    return [JobResponse(**j) for j in jobs]

@api_router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job)

@api_router.put("/jobs/{job_id}", response_model=JobResponse)
async def update_job(job_id: str, update_data: JobUpdate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = await db.jobs.update_one({"id": job_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return JobResponse(**job)

@api_router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, current_user: dict = Depends(require_role(["admin", "employer"]))):
    result = await db.jobs.delete_one({"id": job_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": "Job deleted successfully"}

# ============== CANDIDATE PROFILE ROUTES ==============

@api_router.get("/profile", response_model=CandidateProfile)
async def get_profile(current_user: dict = Depends(require_role(["candidate"]))):
    profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return CandidateProfile(**profile)

@api_router.put("/profile", response_model=CandidateProfile)
async def update_profile(update_data: CandidateProfileUpdate, current_user: dict = Depends(require_role(["candidate"]))):
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.candidate_profiles.update_one(
        {"user_id": current_user["id"]},
        {"$set": update_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
    return CandidateProfile(**profile)

@api_router.post("/profile/resume")
async def upload_resume(file: UploadFile = File(...), current_user: dict = Depends(require_role(["candidate"]))):
    if not file.filename.lower().endswith(('.pdf', '.doc', '.docx')):
        raise HTTPException(status_code=400, detail="Only PDF and DOC files allowed")
    
    file_ext = Path(file.filename).suffix
    filename = f"{current_user['id']}_resume{file_ext}"
    file_path = UPLOAD_DIR / filename
    
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    resume_url = f"/api/uploads/{filename}"
    
    await db.candidate_profiles.update_one(
        {"user_id": current_user["id"]},
        {"$set": {"resume_url": resume_url, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": "Resume uploaded successfully", "resume_url": resume_url}

# ============== APPLICATION ROUTES ==============

@api_router.post("/applications", response_model=ApplicationResponse)
async def create_application(app_data: ApplicationCreate, current_user: dict = Depends(require_role(["candidate"]))):
    # Check if job exists
    job = await db.jobs.find_one({"id": app_data.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if already applied
    existing = await db.applications.find_one({
        "job_id": app_data.job_id,
        "candidate_id": current_user["id"]
    })
    if existing:
        raise HTTPException(status_code=400, detail="Already applied to this job")
    
    # Get candidate's data from candidate_bank if exists
    candidate_bank = await db.candidate_bank.find_one(
        {"$or": [{"linked_user_id": current_user["id"]}, {"email": current_user["email"]}]},
        {"_id": 0}
    )
    
    app_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Get company name
    company = await db.companies.find_one({"id": job.get("company_id")}, {"name": 1, "_id": 0})
    company_name = company.get("name") if company else job.get("company_name", "Unknown")
    
    app_doc = {
        "id": app_id,
        "job_id": app_data.job_id,
        "candidate_id": current_user["id"],
        "candidate_name": current_user["name"],
        "candidate_email": current_user["email"],
        "job_title": job.get("title"),
        "company_name": company_name,
        "cover_letter": app_data.cover_letter,
        "status": "active",
        "stage": "applied",
        "source": "self",
        "notes": [],
        "edit_history": [],
        "created_at": now,
        "updated_at": now
    }
    
    # Include candidate bank data if available
    if candidate_bank:
        app_doc["current_salary"] = candidate_bank.get("current_salary")
        app_doc["notice_period"] = candidate_bank.get("notice_period")
        app_doc["location"] = candidate_bank.get("location")
        app_doc["experience_years"] = candidate_bank.get("experience_years")
        app_doc["skills"] = candidate_bank.get("skills", [])
        app_doc["resume_url"] = candidate_bank.get("resume_url")
    
    await db.applications.insert_one(app_doc)
    
    # Increment applicant count
    await db.jobs.update_one({"id": app_data.job_id}, {"$inc": {"applicant_count": 1}})
    
    # Data Governance: Add to candidate's application history if they exist in candidate_bank
    if candidate_bank:
        await add_application_to_history(candidate_bank["id"], {
            "id": app_id,
            "job_id": app_data.job_id,
            "job_title": job.get("title"),
            "company_name": company_name,
            "source": "self",
            "created_at": now,
            "stage": "applied"
        })
    
    return ApplicationResponse(**app_doc)

@api_router.get("/applications", response_model=List[ApplicationResponse])
async def get_applications(job_id: Optional[str] = None, stage: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    
    if current_user["role"] == "candidate":
        query["candidate_id"] = current_user["id"]
    elif current_user["role"] == "employer":
        # Get employer's jobs
        jobs = await db.jobs.find({"posted_by": current_user["id"]}, {"id": 1, "_id": 0}).to_list(1000)
        job_ids = [j["id"] for j in jobs]
        query["job_id"] = {"$in": job_ids}
    
    if job_id:
        query["job_id"] = job_id
    if stage:
        query["stage"] = stage
    
    applications = await db.applications.find(query, {"_id": 0}).to_list(1000)
    return [ApplicationResponse(**a) for a in applications]

@api_router.get("/applications/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: str, current_user: dict = Depends(get_current_user)):
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationResponse(**application)

@api_router.put("/applications/{app_id}", response_model=ApplicationResponse)
async def update_application(app_id: str, update_data: ApplicationUpdate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    # Get current application for history tracking
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.applications.update_one({"id": app_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Data Governance: Update candidate history if stage changed
    if "stage" in update_dict and application.get("candidate_id"):
        new_stage = update_dict["stage"]
        outcome = None
        if new_stage in ["hired", "rejected", "dropped"]:
            outcome = new_stage
        await update_application_in_history(
            application["candidate_id"],
            app_id,
            new_stage,
            outcome
        )
    
    updated_application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    return ApplicationResponse(**updated_application)

@api_router.post("/applications/{app_id}/notes")
async def add_note(app_id: str, note_data: NoteCreate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    note = {
        "id": str(uuid.uuid4()),
        "content": note_data.content,
        "author_id": current_user["id"],
        "author_name": current_user["name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.applications.update_one(
        {"id": app_id},
        {"$push": {"notes": note}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    
    return {"message": "Note added successfully", "note": note}


@api_router.put("/applications/{app_id}/details")
async def update_application_details(
    app_id: str, 
    update_data: ApplicationDetailUpdate, 
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Controlled editing of applicant details (salary, notice period, skills, experience summary).
    
    Data Precedence: Candidate self-edit > Employer edit > Recruiter edit > Resume parsing
    - Manual edits override parsed data
    - Resume parsing will NEVER overwrite manual edits (manually_edited flag)
    
    All edits are logged with full audit trail.
    """
    # Get current application
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = {}
    audit_entries = []
    
    # Process each field that can be edited
    editable_fields = {
        "current_salary": update_data.current_salary,
        "notice_period": update_data.notice_period,
        "skills": update_data.skills,
        "experience_summary": update_data.experience_summary
    }
    
    for field, new_value in editable_fields.items():
        if new_value is not None:
            old_value = application.get(field)
            
            # Only log if value actually changed
            if old_value != new_value:
                update_dict[field] = new_value
                
                # Create audit entry
                audit_entry = {
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "updated_by_id": current_user["id"],
                    "updated_by_name": current_user["name"],
                    "updated_by_role": current_user["role"],
                    "timestamp": now
                }
                audit_entries.append(audit_entry)
    
    if not update_dict:
        return {"message": "No changes detected", "application_id": app_id}
    
    # Set metadata
    update_dict["updated_at"] = now
    update_dict["manually_edited"] = True  # Flag to prevent parsing overwrites
    update_dict["last_edited_by"] = {
        "name": current_user["name"],
        "role": current_user["role"],
        "user_id": current_user["id"],
        "timestamp": now
    }
    
    # Update application with audit trail
    result = await db.applications.update_one(
        {"id": app_id},
        {
            "$set": update_dict,
            "$push": {"edit_history": {"$each": audit_entries}}
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Also update candidate_bank if the candidate exists there
    if application.get("candidate_id"):
        candidate_update = {}
        audit_fields = []
        if "current_salary" in update_dict:
            candidate_update["current_salary"] = update_dict["current_salary"]
            audit_fields.append("current_salary")
        if "notice_period" in update_dict:
            candidate_update["notice_period"] = update_dict["notice_period"]
            audit_fields.append("notice_period")
        if "skills" in update_dict:
            candidate_update["skills"] = update_dict["skills"]
        if "experience_summary" in update_dict:
            candidate_update["summary"] = update_dict["experience_summary"]
        
        if candidate_update:
            candidate_update["updated_at"] = now
            candidate_update["manually_edited"] = True
            candidate_update["last_profile_updated_at"] = now  # Data Governance: freshness update
            candidate_update["last_updated_by"] = current_user["id"]
            await db.candidate_bank.update_one(
                {"id": application["candidate_id"]},
                {"$set": candidate_update}
            )
            
            # Data Governance: Add audit entries for mandatory field changes
            if audit_fields:
                candidate = await db.candidate_bank.find_one({"id": application["candidate_id"]}, {"_id": 0})
                if candidate:
                    for field in audit_fields:
                        old_entry = next((e for e in audit_entries if e["field"] == field), None)
                        if old_entry:
                            profile_audit = create_profile_audit_entry(
                                field, old_entry["old_value"], old_entry["new_value"],
                                current_user["id"], current_user["name"], current_user["role"],
                                "application_edit"
                            )
                            await db.candidate_bank.update_one(
                                {"id": application["candidate_id"]},
                                {"$push": {"profile_update_audit": profile_audit}}
                            )
    
    # Fetch updated application
    updated_application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    
    return {
        "message": "Application details updated successfully",
        "application_id": app_id,
        "changes": [
            {"field": e["field"], "old_value": e["old_value"], "new_value": e["new_value"]}
            for e in audit_entries
        ],
        "updated_by": {
            "name": current_user["name"],
            "role": current_user["role"]
        },
        "application": ApplicationResponse(**updated_application)
    }


@api_router.get("/applications/{app_id}/edit-history")
async def get_application_edit_history(
    app_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Get the full edit history (audit trail) for an application."""
    application = await db.applications.find_one({"id": app_id}, {"_id": 0, "edit_history": 1, "last_edited_by": 1})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    return {
        "application_id": app_id,
        "edit_history": application.get("edit_history", []),
        "last_edited_by": application.get("last_edited_by")
    }


# ============== JOB APPLICANTS (Per-Job Review Screen) ==============

class ApplicantReviewResponse(BaseModel):
    """Enhanced applicant data for review screen"""
    model_config = ConfigDict(extra="ignore")
    id: str
    job_id: str
    candidate_id: str
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_phone: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    experience_summary: Optional[str] = None  # Editable summary text
    skills: Optional[List[str]] = None
    experience_years: Optional[int] = None
    location: Optional[str] = None
    current_salary: Optional[int] = None  # INR
    notice_period: Optional[str] = None
    resume_url: Optional[str] = None
    cover_letter: Optional[str] = None
    stage: str = "applied"
    match_score: Optional[int] = None  # 0-100 percentage
    must_haves_met: Optional[List[Dict]] = None  # [{requirement: str, met: bool}]
    career_stability: Optional[Dict] = None  # {score: green/yellow/red, quick_changes: int}
    applied_at: Optional[str] = None
    updated_at: Optional[str] = None
    notes: List[Dict] = []
    edit_history: List[Dict] = []  # Audit trail
    last_edited_by: Optional[Dict] = None  # {name, role, timestamp}
    manually_edited: bool = False  # Flag indicating manual edits exist

@api_router.get("/jobs/{job_id}/applicants")
async def get_job_applicants(
    job_id: str, 
    stage: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Get all applicants for a specific job with enriched data for review.
    Returns candidate details, match scores, must-have indicators, salary, and notice period.
    """
    # Verify job exists and user has access
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # For employers, verify they own the job
    if current_user["role"] == "employer" and job.get("posted_by") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view applicants for this job")
    
    # Build query
    query = {"job_id": job_id}
    if stage:
        query["stage"] = stage
    
    # Get all applications for this job
    applications = await db.applications.find(query, {"_id": 0}).to_list(1000)
    
    # Parse job requirements for must-have matching
    job_requirements = []
    if job.get("requirements"):
        job_requirements = [r.strip().lower() for r in job.get("requirements", "").split(",") if r.strip()]
    
    enriched_applicants = []
    
    for app in applications:
        # Get additional candidate data from candidate_bank if available
        candidate_data = await db.candidate_bank.find_one(
            {"$or": [
                {"id": app.get("candidate_id")},
                {"email": app.get("candidate_email")}
            ]},
            {"_id": 0}
        )
        
        # Calculate match score based on skills overlap
        app_skills = app.get("skills") or (candidate_data.get("skills") if candidate_data else []) or []
        app_skills_lower = [s.lower() for s in app_skills]
        
        # Calculate must-haves met
        must_haves_met = []
        matched_requirements = 0
        for req in job_requirements:
            is_met = any(req in skill or skill in req for skill in app_skills_lower)
            must_haves_met.append({"requirement": req, "met": is_met})
            if is_met:
                matched_requirements += 1
        
        # Calculate match score (percentage of requirements met)
        match_score = int((matched_requirements / len(job_requirements) * 100)) if job_requirements else 0
        
        # Get career stability from candidate_bank or calculate
        career_stability = None
        if candidate_data and candidate_data.get("experience"):
            career_stability = calculate_career_stability(candidate_data.get("experience", []))
        
        # Build enriched response
        enriched = {
            "id": app.get("id"),
            "job_id": app.get("job_id"),
            "candidate_id": app.get("candidate_id"),
            "candidate_name": app.get("candidate_name") or (candidate_data.get("name") if candidate_data else None),
            "candidate_email": app.get("candidate_email") or (candidate_data.get("email") if candidate_data else None),
            "candidate_phone": app.get("candidate_phone") or (candidate_data.get("phone") if candidate_data else None),
            "headline": app.get("headline") or (candidate_data.get("headline") if candidate_data else None),
            "summary": candidate_data.get("summary") if candidate_data else None,
            "experience_summary": app.get("experience_summary") or (candidate_data.get("summary") if candidate_data else None),
            "skills": app_skills,
            "experience_years": app.get("experience_years") or (candidate_data.get("experience_years") if candidate_data else None),
            "location": app.get("location") or (candidate_data.get("location") if candidate_data else None),
            "current_salary": app.get("current_salary") or (candidate_data.get("current_salary") if candidate_data else None),
            "notice_period": app.get("notice_period") or (candidate_data.get("notice_period") if candidate_data else None),
            "resume_url": app.get("resume_url") or (candidate_data.get("resume_url") if candidate_data else None),
            "cover_letter": app.get("cover_letter"),
            "stage": app.get("stage", "applied"),
            "match_score": match_score,
            "must_haves_met": must_haves_met,
            "career_stability": career_stability,
            "applied_at": app.get("applied_at") or app.get("created_at"),
            "updated_at": app.get("updated_at"),
            "notes": app.get("notes", []),
            "edit_history": app.get("edit_history", []),
            "last_edited_by": app.get("last_edited_by"),
            "manually_edited": app.get("manually_edited", False)
        }
        
        enriched_applicants.append(enriched)
    
    # Sort by match score (highest first), then by applied date
    enriched_applicants.sort(key=lambda x: (-(x.get("match_score") or 0), x.get("applied_at") or ""))
    
    return {
        "job": {
            "id": job.get("id"),
            "title": job.get("title"),
            "location": job.get("location"),
            "job_type": job.get("job_type"),
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "requirements": job.get("requirements"),
            "applicant_count": len(applications)
        },
        "applicants": enriched_applicants,
        "stage_counts": {
            "applied": sum(1 for a in applications if a.get("stage") == "applied"),
            "shortlisted": sum(1 for a in applications if a.get("stage") == "shortlisted"),
            "interview": sum(1 for a in applications if a.get("stage") == "interview"),
            "offered": sum(1 for a in applications if a.get("stage") == "offered"),
            "hired": sum(1 for a in applications if a.get("stage") == "hired"),
            "rejected": sum(1 for a in applications if a.get("stage") == "rejected"),
            "on_hold": sum(1 for a in applications if a.get("stage") == "on_hold"),
            "over_budget": sum(1 for a in applications if a.get("stage") == "over_budget"),
            "not_qualified": sum(1 for a in applications if a.get("stage") == "not_qualified")
        }
    }


# ============== CANDIDATE MANAGEMENT (Admin/Recruiter) ==============

@api_router.get("/candidates", response_model=List[CandidateProfile])
async def get_candidates(current_user: dict = Depends(require_role(["admin", "recruiter", "employer"]))):
    profiles = await db.candidate_profiles.find({}, {"_id": 0}).to_list(1000)
    return [CandidateProfile(**p) for p in profiles]

@api_router.get("/candidates/{candidate_id}", response_model=CandidateProfile)
async def get_candidate(candidate_id: str, current_user: dict = Depends(require_role(["admin", "recruiter", "employer"]))):
    profile = await db.candidate_profiles.find_one({"user_id": candidate_id}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateProfile(**profile)

# ============== MESSAGE ROUTES ==============

@api_router.post("/messages", response_model=MessageResponse)
async def send_message(msg_data: MessageCreate, current_user: dict = Depends(get_current_user)):
    # Check recipient exists
    recipient = await db.users.find_one({"id": msg_data.recipient_id}, {"_id": 0})
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    msg_doc = {
        "id": msg_id,
        "sender_id": current_user["id"],
        "sender_name": current_user["name"],
        "recipient_id": msg_data.recipient_id,
        "recipient_name": recipient["name"],
        "subject": msg_data.subject,
        "content": msg_data.content,
        "is_read": False,
        "created_at": now
    }
    
    await db.messages.insert_one(msg_doc)
    return MessageResponse(**msg_doc)

@api_router.get("/messages", response_model=List[MessageResponse])
async def get_messages(sent: bool = False, current_user: dict = Depends(get_current_user)):
    if sent:
        query = {"sender_id": current_user["id"]}
    else:
        query = {"recipient_id": current_user["id"]}
    
    messages = await db.messages.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [MessageResponse(**m) for m in messages]

@api_router.put("/messages/{msg_id}/read")
async def mark_message_read(msg_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.messages.update_one(
        {"id": msg_id, "recipient_id": current_user["id"]},
        {"$set": {"is_read": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message": "Marked as read"}

# ============== DASHBOARD STATS ==============

@api_router.get("/stats/admin")
async def get_admin_stats(current_user: dict = Depends(require_role(["admin"]))):
    total_users = await db.users.count_documents({})
    total_jobs = await db.jobs.count_documents({})
    total_applications = await db.applications.count_documents({})
    total_companies = await db.companies.count_documents({})
    
    users_by_role = await db.users.aggregate([
        {"$group": {"_id": "$role", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    recent_applications = await db.applications.find({}, {"_id": 0}).sort("created_at", -1).to_list(5)
    
    return {
        "total_users": total_users,
        "total_jobs": total_jobs,
        "total_applications": total_applications,
        "total_companies": total_companies,
        "users_by_role": {item["_id"]: item["count"] for item in users_by_role},
        "recent_applications": recent_applications
    }

@api_router.get("/stats/recruiter")
async def get_recruiter_stats(current_user: dict = Depends(require_role(["recruiter"]))):
    total_jobs = await db.jobs.count_documents({})
    total_candidates = await db.candidate_profiles.count_documents({})
    
    pipeline_stats = await db.applications.aggregate([
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    return {
        "total_jobs": total_jobs,
        "total_candidates": total_candidates,
        "pipeline_stats": {item["_id"]: item["count"] for item in pipeline_stats}
    }

@api_router.get("/stats/employer")
async def get_employer_stats(current_user: dict = Depends(require_role(["employer"]))):
    my_jobs = await db.jobs.count_documents({"posted_by": current_user["id"]})
    
    jobs = await db.jobs.find({"posted_by": current_user["id"]}, {"id": 1, "_id": 0}).to_list(1000)
    job_ids = [j["id"] for j in jobs]
    
    total_applicants = await db.applications.count_documents({"job_id": {"$in": job_ids}})
    
    stage_stats = await db.applications.aggregate([
        {"$match": {"job_id": {"$in": job_ids}}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    return {
        "my_jobs": my_jobs,
        "total_applicants": total_applicants,
        "stage_stats": {item["_id"]: item["count"] for item in stage_stats}
    }

@api_router.get("/stats/candidate")
async def get_candidate_stats(current_user: dict = Depends(require_role(["candidate"]))):
    my_applications = await db.applications.count_documents({"candidate_id": current_user["id"]})
    active_jobs = await db.jobs.count_documents({"status": "active"})
    
    app_stages = await db.applications.aggregate([
        {"$match": {"candidate_id": current_user["id"]}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    unread_messages = await db.messages.count_documents({
        "recipient_id": current_user["id"],
        "is_read": False
    })
    
    return {
        "my_applications": my_applications,
        "active_jobs": active_jobs,
        "application_stages": {item["_id"]: item["count"] for item in app_stages},
        "unread_messages": unread_messages
    }

# ============== AI MATCHING ENGINE ==============

from services.matching_engine import (
    parse_resume_with_ai,
    parse_job_description_with_ai,
    calculate_candidate_job_match,
    apply_must_have_filters,
    generate_resume_fingerprint,
    find_similar_candidate
)

def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from PDF file"""
    try:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""

def normalize_phone(phone: str) -> str:
    """Normalize phone number for deduplication"""
    if not phone:
        return ""
    return "".join(filter(str.isdigit, phone))[-10:]

async def create_audit_log(
    candidate_id: str,
    field: str,
    old_val: Any,
    new_val: Any,
    user: dict,
    source: str
):
    """Create audit trail entry for candidate data changes"""
    log_entry = {
        "id": str(uuid.uuid4()),
        "candidate_id": candidate_id,
        "field_changed": field,
        "old_value": str(old_val) if old_val else None,
        "new_value": str(new_val) if new_val else None,
        "updated_by_role": user["role"],
        "updated_by_id": user["id"],
        "updated_by_name": user["name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source
    }
    await db.audit_logs.insert_one(log_entry)

# Data update priority: candidate > employer > recruiter > parsing
UPDATE_PRIORITY = {
    "candidate": 4,
    "employer": 3,
    "recruiter": 2,
    "admin": 5,
    "parsing": 1
}

async def should_update_field(
    candidate_id: str,
    field: str,
    new_source: str,
    db
) -> bool:
    """Check if update should proceed based on priority rules"""
    # Get last update source for this field
    last_log = await db.audit_logs.find_one(
        {"candidate_id": candidate_id, "field_changed": field},
        sort=[("timestamp", -1)]
    )
    
    if not last_log:
        return True
    
    last_source_role = last_log.get("updated_by_role", "parsing")
    last_priority = UPDATE_PRIORITY.get(last_source_role, 1)
    new_priority = UPDATE_PRIORITY.get(new_source, 1)
    
    return new_priority >= last_priority

@api_router.post("/ai/parse-resume")
async def ai_parse_resume(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Parse resume using AI and optionally add to candidate data bank"""
    if not file.filename.lower().endswith(('.pdf', '.doc', '.docx', '.txt')):
        raise HTTPException(status_code=400, detail="Only PDF, DOC, DOCX, TXT files allowed")
    
    # Save file temporarily
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    temp_path = UPLOAD_DIR / f"temp_{file_id}{file_ext}"
    
    async with aiofiles.open(temp_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Extract text
    if file_ext.lower() == '.pdf':
        resume_text = extract_text_from_pdf(temp_path)
    else:
        async with aiofiles.open(temp_path, 'r', errors='ignore') as f:
            resume_text = await f.read()
    
    if not resume_text.strip():
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Could not extract text from file")
    
    # Parse with AI
    result = await parse_resume_with_ai(resume_text)
    
    if not result["success"]:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=result.get("error", "Parsing failed"))
    
    # Generate fingerprint
    fingerprint = generate_resume_fingerprint(resume_text)
    result["data"]["resume_fingerprint"] = fingerprint
    
    temp_path.unlink(missing_ok=True)
    
    return {"success": True, "parsed_data": result["data"]}

@api_router.post("/ai/parse-jd")
async def ai_parse_job_description(
    jd_text: str = Form(None),
    file: UploadFile = File(None),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Parse job description using AI"""
    text_to_parse = jd_text
    
    if file:
        file_ext = Path(file.filename).suffix
        temp_path = UPLOAD_DIR / f"temp_jd_{uuid.uuid4()}{file_ext}"
        
        async with aiofiles.open(temp_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        if file_ext.lower() == '.pdf':
            text_to_parse = extract_text_from_pdf(temp_path)
        else:
            async with aiofiles.open(temp_path, 'r', errors='ignore') as f:
                text_to_parse = await f.read()
        
        temp_path.unlink(missing_ok=True)
    
    if not text_to_parse or not text_to_parse.strip():
        raise HTTPException(status_code=400, detail="No job description text provided")
    
    result = await parse_job_description_with_ai(text_to_parse)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Parsing failed"))
    
    return {"success": True, "parsed_data": result["data"]}

@api_router.post("/matching/find-candidates", response_model=List[MatchResult])
async def find_matching_candidates(
    match_req: MatchRequest,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Find candidates matching job requirements with AI scoring"""
    
    # Get job requirements
    job_data = None
    if match_req.job_id:
        job = await db.jobs.find_one({"id": match_req.job_id}, {"_id": 0})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        # Parse existing job description
        jd_result = await parse_job_description_with_ai(job.get("description", "") + " " + job.get("requirements", ""))
        if jd_result["success"]:
            job_data = jd_result["data"]
    elif match_req.jd_text:
        jd_result = await parse_job_description_with_ai(match_req.jd_text)
        if jd_result["success"]:
            job_data = jd_result["data"]
    
    if not job_data:
        raise HTTPException(status_code=400, detail="Could not parse job requirements")
    
    # Build must-have filters
    must_have = {}
    if match_req.must_have_location:
        must_have["location"] = match_req.must_have_location
    if match_req.must_have_qualification:
        must_have["required_qualification"] = match_req.must_have_qualification
    if match_req.must_have_skills:
        must_have["mandatory_skills"] = match_req.must_have_skills
    if match_req.min_experience is not None:
        must_have["min_experience"] = match_req.min_experience
    if match_req.max_experience is not None:
        must_have["max_experience"] = match_req.max_experience
    
    # Get candidates based on role visibility
    query = {}
    if current_user["role"] == "employer":
        query["$or"] = [
            {"visibility.employer_ids": current_user["id"]},
            {"source": "self"}  # Self-registered candidates visible to employers
        ]
    elif current_user["role"] == "recruiter":
        query["$or"] = [
            {"visibility.recruiter_ids": current_user["id"]},
            {"created_by": current_user["id"]},
            {"source": "self"}
        ]
    
    candidates = await db.candidate_bank.find(query, {"_id": 0}).to_list(500)
    
    results = []
    for candidate in candidates:
        match_result = await calculate_candidate_job_match(candidate, job_data, must_have if must_have else None)
        
        results.append(MatchResult(
            candidate_id=candidate["id"],
            candidate_name=candidate["name"],
            candidate_email=candidate["email"],
            score=match_result.get("score", 0),
            skill_match_score=match_result.get("skill_match_score"),
            experience_match_score=match_result.get("experience_match_score"),
            matched_skills=match_result.get("matched_skills", []),
            missing_skills=match_result.get("missing_skills", []),
            strengths=match_result.get("strengths", []),
            gaps=match_result.get("gaps", []),
            explanation=match_result.get("explanation", ""),
            filtered_out=match_result.get("filtered_out", False),
            filter_reason=match_result.get("filter_reason")
        ))
    
    # Sort by score descending, filtered_out last
    results.sort(key=lambda x: (not x.filtered_out, x.score), reverse=True)
    
    # Store match results for analytics
    if match_req.job_id:
        await db.match_results.insert_one({
            "id": str(uuid.uuid4()),
            "job_id": match_req.job_id,
            "searched_by": current_user["id"],
            "searched_by_role": current_user["role"],
            "total_candidates": len(candidates),
            "matched_count": len([r for r in results if r.score >= 50 and not r.filtered_out]),
            "filters_applied": must_have,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    return results

@api_router.get("/matching/jobs-for-candidate", response_model=List[JobMatchForCandidate])
async def get_matching_jobs_for_candidate(
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Get matching jobs for current candidate based on their profile"""
    
    # Get candidate from data bank
    candidate = await db.candidate_bank.find_one(
        {"linked_user_id": current_user["id"]},
        {"_id": 0}
    )
    
    if not candidate:
        # Fallback to candidate_profiles
        profile = await db.candidate_profiles.find_one(
            {"user_id": current_user["id"]},
            {"_id": 0}
        )
        if not profile:
            return []
        candidate = profile
    
    # Get active jobs
    jobs = await db.jobs.find({"status": "active"}, {"_id": 0}).to_list(100)
    
    results = []
    for job in jobs:
        # Parse job requirements
        jd_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"
        jd_result = await parse_job_description_with_ai(jd_text)
        
        if not jd_result["success"]:
            continue
        
        job_data = jd_result["data"]
        match_result = await calculate_candidate_job_match(candidate, job_data)
        
        if match_result.get("score", 0) >= 30:  # Only show relevant matches
            results.append(JobMatchForCandidate(
                job_id=job["id"],
                job_title=job["title"],
                company_name=job.get("company_name"),
                location=job.get("location", ""),
                score=match_result.get("score", 0),
                explanation=match_result.get("explanation", ""),
                matched_skills=match_result.get("matched_skills", [])
            ))
    
    # Sort by score
    results.sort(key=lambda x: x.score, reverse=True)
    
    return results[:20]  # Return top 20 matches

# ============== CANDIDATE DATA BANK ==============

@api_router.post("/candidate-bank/add")
async def add_to_candidate_bank(
    file: UploadFile = File(...),
    email: str = Form(None),
    name: str = Form(None),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Add candidate to data bank from resume upload with deduplication"""
    
    # Parse resume
    if not file.filename.lower().endswith(('.pdf', '.doc', '.docx', '.txt')):
        raise HTTPException(status_code=400, detail="Only PDF, DOC, DOCX, TXT files allowed")
    
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    file_path = UPLOAD_DIR / f"resume_{file_id}{file_ext}"
    
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Extract and parse
    if file_ext.lower() == '.pdf':
        resume_text = extract_text_from_pdf(file_path)
    else:
        async with aiofiles.open(file_path, 'r', errors='ignore') as f:
            resume_text = await f.read()
    
    fingerprint = generate_resume_fingerprint(resume_text)
    
    parse_result = await parse_resume_with_ai(resume_text)
    if not parse_result["success"]:
        raise HTTPException(status_code=500, detail="Failed to parse resume")
    
    parsed_data = parse_result["data"]
    candidate_email = email or parsed_data.get("email")
    candidate_name = name or parsed_data.get("name")
    
    if not candidate_email:
        raise HTTPException(status_code=400, detail="Could not determine candidate email")
    
    # Check for duplicates
    dup_check = await find_similar_candidate(
        db,
        email=candidate_email,
        phone=parsed_data.get("phone"),
        resume_fingerprint=fingerprint
    )
    
    now = datetime.now(timezone.utc).isoformat()
    resume_version = {
        "id": file_id,
        "filename": file.filename,
        "path": str(file_path),
        "fingerprint": fingerprint,
        "uploaded_at": now,
        "uploaded_by": current_user["id"],
        "is_active": True
    }
    
    if dup_check["found"]:
        # Update existing candidate
        existing = dup_check["candidate"]
        
        # Deactivate old resume, add new
        update_data = {
            "resume_versions": existing.get("resume_versions", []) + [resume_version],
            "active_resume_id": file_id,
            "updated_at": now,
            "last_updated_by": current_user["id"]
        }
        
        # Add fingerprint if new
        if fingerprint not in existing.get("resume_fingerprints", []):
            update_data["resume_fingerprints"] = existing.get("resume_fingerprints", []) + [fingerprint]
        
        # Update fields based on priority
        source = current_user["role"]
        for field in ["skills", "experience", "education", "experience_years", "location", "certifications"]:
            if parsed_data.get(field) and await should_update_field(existing["id"], field, source, db):
                old_val = existing.get(field)
                new_val = parsed_data[field]
                if old_val != new_val:
                    update_data[field] = new_val
                    await create_audit_log(existing["id"], field, old_val, new_val, current_user, f"{source}_update")
        
        # Add visibility
        vis_key = f"{current_user['role']}_ids"
        current_vis = existing.get("visibility", {}).get(vis_key, [])
        if current_user["id"] not in current_vis:
            update_data[f"visibility.{vis_key}"] = current_vis + [current_user["id"]]
        
        await db.candidate_bank.update_one(
            {"id": existing["id"]},
            {"$set": update_data}
        )
        
        return {
            "action": "updated",
            "candidate_id": existing["id"],
            "match_type": dup_check["match_type"],
            "message": f"Updated existing candidate (matched by {dup_check['match_type']})"
        }
    
    else:
        # Create new candidate
        candidate_id = str(uuid.uuid4())
        
        candidate_doc = {
            "id": candidate_id,
            "email": candidate_email.lower(),
            "name": candidate_name or "Unknown",
            "phone": parsed_data.get("phone"),
            "phone_normalized": normalize_phone(parsed_data.get("phone", "")),
            "headline": parsed_data.get("headline"),
            "summary": parsed_data.get("summary"),
            "skills": parsed_data.get("skills", []),
            "experience_years": parsed_data.get("experience_years", 0),
            "experience": parsed_data.get("experience", []),
            "education": parsed_data.get("education", []),
            "location": parsed_data.get("location"),
            "certifications": parsed_data.get("certifications", []),
            "active_resume_id": file_id,
            "resume_versions": [resume_version],
            "resume_fingerprints": [fingerprint],
            "source": current_user["role"],
            "linked_user_id": None,
            "visibility": {
                f"{current_user['role']}_ids": [current_user["id"]]
            },
            "match_cache": [],
            "created_at": now,
            "updated_at": now,
            "created_by": current_user["id"],
            "last_updated_by": current_user["id"]
        }
        
        await db.candidate_bank.insert_one(candidate_doc)
        
        return {
            "action": "created",
            "candidate_id": candidate_id,
            "message": "New candidate added to data bank"
        }

# ============== PHASE-2: BATCH CV UPLOAD ==============

class BatchUploadCandidate(BaseModel):
    """Single candidate data for batch save"""
    temp_id: str  # Temporary ID from parse response
    name: str
    email: str
    phone: Optional[str] = None
    skills: List[str] = []
    experience_summary: Optional[str] = None
    current_salary: int  # MANDATORY - INR
    notice_period: str  # MANDATORY
    location: str  # MANDATORY - Data Governance
    experience_years: int  # MANDATORY - Data Governance (can be 0 for freshers)
    file_id: str  # Reference to uploaded file
    fingerprint: str  # Resume fingerprint for dedup

class BatchSaveRequest(BaseModel):
    """Request body for batch save"""
    candidates: List[BatchUploadCandidate]

@api_router.post("/candidate-bank/batch-parse")
async def batch_parse_resumes(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Parse up to 10 CVs and return preview data. No save - just parsing.
    Returns parsed data for each file for user preview/edit before save.
    """
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed per batch")
    
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="No files uploaded")
    
    results = []
    
    for file in files:
        temp_id = str(uuid.uuid4())
        
        try:
            # Validate file type
            if not file.filename.lower().endswith(('.pdf', '.doc', '.docx')):
                results.append({
                    "temp_id": temp_id,
                    "filename": file.filename,
                    "success": False,
                    "error": "Only PDF, DOC, DOCX files allowed"
                })
                continue
            
            # Save file temporarily
            file_id = str(uuid.uuid4())
            file_ext = Path(file.filename).suffix
            file_path = UPLOAD_DIR / f"resume_{file_id}{file_ext}"
            
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            # Extract text
            if file_ext.lower() == '.pdf':
                resume_text = extract_text_from_pdf(file_path)
            else:
                async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                    resume_text = await f.read()
            
            # Generate fingerprint for dedup
            fingerprint = generate_resume_fingerprint(resume_text)
            
            # Parse with AI
            parse_result = await parse_resume_with_ai(resume_text[:8000])
            
            if not parse_result["success"]:
                results.append({
                    "temp_id": temp_id,
                    "filename": file.filename,
                    "success": False,
                    "error": "Failed to parse resume"
                })
                continue
            
            parsed_data = parse_result["data"]
            
            # Check for duplicates
            dup_check = await find_similar_candidate(
                db,
                email=parsed_data.get("email"),
                phone=parsed_data.get("phone"),
                resume_fingerprint=fingerprint
            )
            
            results.append({
                "temp_id": temp_id,
                "filename": file.filename,
                "file_id": file_id,
                "fingerprint": fingerprint,
                "success": True,
                "parsed_data": {
                    "name": parsed_data.get("name", "Unknown"),
                    "email": parsed_data.get("email", ""),
                    "phone": parsed_data.get("phone", ""),
                    "skills": parsed_data.get("skills", []),
                    "experience_summary": parsed_data.get("summary", ""),
                    "experience_years": parsed_data.get("experience_years", 0),
                    "location": parsed_data.get("location", ""),
                    "headline": parsed_data.get("headline", ""),
                    "experience": parsed_data.get("experience", []),
                    "education": parsed_data.get("education", [])
                },
                "duplicate_check": {
                    "is_duplicate": dup_check["found"],
                    "match_type": dup_check.get("match_type"),
                    "existing_candidate": {
                        "id": dup_check["candidate"]["id"],
                        "name": dup_check["candidate"].get("name"),
                        "email": dup_check["candidate"].get("email"),
                        "created_at": dup_check["candidate"].get("created_at"),
                        "current_salary": dup_check["candidate"].get("current_salary"),
                        "notice_period": dup_check["candidate"].get("notice_period")
                    } if dup_check["found"] else None
                }
            })
            
        except Exception as e:
            logger.error(f"Error parsing file {file.filename}: {str(e)}")
            results.append({
                "temp_id": temp_id,
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return {
        "total": len(files),
        "parsed": len([r for r in results if r.get("success")]),
        "failed": len([r for r in results if not r.get("success")]),
        "results": results
    }

@api_router.post("/candidate-bank/batch-save")
async def batch_save_candidates(
    request: BatchSaveRequest,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Save multiple candidates to data bank after user review/edit.
    ATOMIC: All succeed or all fail. Validates salary & notice period as mandatory.
    """
    candidates = request.candidates
    
    if len(candidates) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 candidates per batch")
    
    if len(candidates) == 0:
        raise HTTPException(status_code=400, detail="No candidates to save")
    
    # VALIDATION PHASE - Check all candidates first (Data Governance enforcement)
    validation_errors = []
    
    for idx, candidate in enumerate(candidates):
        errors = []
        
        if not candidate.email or not candidate.email.strip():
            errors.append("Email is required")
        if not candidate.name or not candidate.name.strip():
            errors.append("Name is required")
        # Data Governance: Mandatory fields enforcement
        if not candidate.current_salary or candidate.current_salary <= 0:
            errors.append("Current salary (INR) is mandatory and must be positive")
        if not candidate.notice_period or not candidate.notice_period.strip():
            errors.append("Notice period is mandatory")
        if not candidate.location or not candidate.location.strip():
            errors.append("Location is mandatory")
        if candidate.experience_years is None:
            errors.append("Experience (years) is mandatory")
        
        if errors:
            validation_errors.append({
                "temp_id": candidate.temp_id,
                "index": idx,
                "name": candidate.name,
                "errors": errors
            })
    
    # If any validation errors, FAIL ALL (atomic behavior)
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed. No candidates were saved.",
                "errors": validation_errors
            }
        )
    
    # SAVE PHASE - All validated, now save
    now = datetime.now(timezone.utc).isoformat()
    saved = []
    
    for candidate in candidates:
        try:
            # Check for duplicate again (in case of race condition)
            dup_check = await find_similar_candidate(
                db,
                email=candidate.email,
                phone=candidate.phone,
                resume_fingerprint=candidate.fingerprint
            )
            
            file_path = None
            for f in UPLOAD_DIR.iterdir():
                if candidate.file_id in f.name:
                    file_path = f
                    break
            
            resume_version = {
                "id": candidate.file_id,
                "fingerprint": candidate.fingerprint,
                "uploaded_at": now,
                "uploaded_by": current_user["id"],
                "is_active": True
            }
            
            if dup_check["found"]:
                # Update existing candidate
                existing = dup_check["candidate"]
                
                update_data = {
                    "resume_versions": existing.get("resume_versions", []) + [resume_version],
                    "active_resume_id": candidate.file_id,
                    "updated_at": now,
                    "last_updated_by": current_user["id"],
                    "current_salary": candidate.current_salary,
                    "notice_period": candidate.notice_period,
                    "resume_url": f"/api/uploads/resume_{candidate.file_id}{Path(file_path).suffix if file_path else '.pdf'}"
                }
                
                # Update fields with audit logging
                source = current_user["role"]
                
                if candidate.name and candidate.name != existing.get("name"):
                    if await should_update_field(existing["id"], "name", source, db):
                        await create_audit_log(existing["id"], "name", existing.get("name"), candidate.name, current_user, "batch_upload")
                        update_data["name"] = candidate.name
                
                if candidate.skills and candidate.skills != existing.get("skills"):
                    if await should_update_field(existing["id"], "skills", source, db):
                        await create_audit_log(existing["id"], "skills", existing.get("skills"), candidate.skills, current_user, "batch_upload")
                        update_data["skills"] = candidate.skills
                
                if candidate.experience_summary and candidate.experience_summary != existing.get("summary"):
                    if await should_update_field(existing["id"], "summary", source, db):
                        await create_audit_log(existing["id"], "summary", existing.get("summary"), candidate.experience_summary, current_user, "batch_upload")
                        update_data["summary"] = candidate.experience_summary
                
                # Add fingerprint if new
                if candidate.fingerprint not in existing.get("resume_fingerprints", []):
                    update_data["resume_fingerprints"] = existing.get("resume_fingerprints", []) + [candidate.fingerprint]
                
                await db.candidate_bank.update_one({"id": existing["id"]}, {"$set": update_data})
                
                saved.append({
                    "temp_id": candidate.temp_id,
                    "action": "updated",
                    "candidate_id": existing["id"],
                    "name": candidate.name
                })
            
            else:
                # Create new candidate
                candidate_id = str(uuid.uuid4())
                
                candidate_doc = {
                    "id": candidate_id,
                    "email": candidate.email.lower().strip(),
                    "name": candidate.name.strip(),
                    "phone": candidate.phone,
                    "phone_normalized": normalize_phone(candidate.phone or ""),
                    "headline": None,
                    "summary": candidate.experience_summary,
                    "skills": candidate.skills,
                    "experience_years": candidate.experience_years,  # Data Governance: mandatory
                    "experience": [],
                    "education": [],
                    "location": candidate.location,  # Data Governance: mandatory
                    "certifications": [],
                    "active_resume_id": candidate.file_id,
                    "resume_versions": [resume_version],
                    "resume_fingerprints": [candidate.fingerprint],
                    "resume_url": f"/api/uploads/resume_{candidate.file_id}{Path(file_path).suffix if file_path else '.pdf'}",
                    "current_salary": candidate.current_salary,
                    "notice_period": candidate.notice_period,
                    "source": current_user["role"],
                    "linked_user_id": None,
                    "visibility": {
                        f"{current_user['role']}_ids": [current_user["id"]]
                    },
                    "match_cache": [],
                    "created_at": now,
                    "updated_at": now,
                    "created_by": current_user["id"],
                    "last_updated_by": current_user["id"],
                    # Data Governance: Profile Freshness metadata
                    "last_profile_updated_at": now,
                    "last_application_date": None,
                    "application_history": [],
                    "profile_update_audit": []
                }
                
                await db.candidate_bank.insert_one(candidate_doc)
                
                saved.append({
                    "temp_id": candidate.temp_id,
                    "action": "created",
                    "candidate_id": candidate_id,
                    "name": candidate.name
                })
        
        except Exception as e:
            logger.error(f"Error saving candidate {candidate.temp_id}: {str(e)}")
            # Atomic failure - rollback and fail all
            raise HTTPException(
                status_code=500,
                detail={
                    "message": f"Failed to save candidate {candidate.name}. No candidates were saved.",
                    "error": str(e)
                }
            )
    
    return {
        "success": True,
        "message": f"Successfully saved {len(saved)} candidates",
        "saved": saved
    }

# ============== PHASE-2: MANUAL ADD AS APPLICANT ==============

class LinkCandidateRequest(BaseModel):
    """Request to link a candidate to a job as an applicant"""
    candidate_id: str
    job_id: str

@api_router.post("/applications/link-candidate")
async def link_candidate_to_job(
    request: LinkCandidateRequest,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Create an application record linking a Candidate Data Bank record to a job.
    Does NOT duplicate the candidate - just creates an application.
    Inherits salary & notice period from Candidate Data Bank.
    """
    # Validate candidate exists
    candidate = await db.candidate_bank.find_one({"id": request.candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found in data bank")
    
    # Validate job exists
    job = await db.jobs.find_one({"id": request.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check for duplicate application (candidate already applied to this job)
    existing_app = await db.applications.find_one({
        "candidate_id": request.candidate_id,
        "job_id": request.job_id
    })
    if existing_app:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Candidate has already been added to this job",
                "existing_application_id": existing_app.get("id"),
                "stage": existing_app.get("stage", "applied")
            }
        )
    
    # Validate mandatory fields from candidate (Data Governance)
    validation_errors = validate_mandatory_candidate_fields({
        "current_salary": candidate.get("current_salary"),
        "notice_period": candidate.get("notice_period"),
        "location": candidate.get("location"),
        "experience_years": candidate.get("experience_years")
    })
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Candidate is missing mandatory fields required for application",
                "errors": validation_errors,
                "candidate_id": request.candidate_id
            }
        )
    
    # Create application record
    now = datetime.now(timezone.utc).isoformat()
    app_id = str(uuid.uuid4())
    
    # Get company name for history
    company = await db.companies.find_one({"id": job.get("company_id")}, {"name": 1, "_id": 0})
    company_name = company.get("name") if company else job.get("company_name", "Unknown")
    
    application_doc = {
        "id": app_id,
        "job_id": request.job_id,
        "job_title": job.get("title"),
        "company_name": company_name,
        "candidate_id": request.candidate_id,
        "candidate_name": candidate.get("name"),
        "candidate_email": candidate.get("email"),
        "resume_url": candidate.get("resume_url"),
        "skills": candidate.get("skills", []),
        "experience_summary": candidate.get("summary"),
        "current_salary": candidate.get("current_salary"),
        "notice_period": candidate.get("notice_period"),
        "location": candidate.get("location"),  # Data Governance: mandatory field
        "experience_years": candidate.get("experience_years"),  # Data Governance: mandatory field
        "stage": "applied",
        "source": "manual_link",
        "match_score": 0,
        "manually_edited": False,
        "edit_history": [],
        "notes": [],
        "created_at": now,
        "updated_at": now,
        "created_by": current_user["id"],
        "created_by_role": current_user["role"]
    }
    
    await db.applications.insert_one(application_doc)
    
    # Data Governance: Add to candidate's application history
    await add_application_to_history(request.candidate_id, {
        "id": app_id,
        "job_id": request.job_id,
        "job_title": job.get("title"),
        "company_name": company_name,
        "source": "manual_link",
        "created_at": now,
        "stage": "applied"
    })
    
    return {
        "success": True,
        "message": f"Successfully added {candidate.get('name')} as applicant for {job.get('title')}",
        "application_id": app_id,
        "candidate_id": request.candidate_id,
        "job_id": request.job_id
    }

# ============== PHASE-2: UPDATE CANDIDATE SALARY/NOTICE ==============

@api_router.put("/candidate-bank/{candidate_id}/salary-notice")
async def update_candidate_mandatory_fields(
    candidate_id: str,
    current_salary: int = None,
    notice_period: str = None,
    location: str = None,
    experience_years: int = None,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Update candidate's mandatory fields in the Candidate Data Bank.
    Data Governance: salary, notice_period, location, experience_years
    Used to ensure mandatory fields are set before linking to jobs.
    All changes are audit-logged.
    """
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    now = datetime.now(timezone.utc).isoformat()
    update_data = {"updated_at": now}
    audit_entries = []
    
    # Track which fields are being updated
    fields_updated = []
    
    if current_salary is not None:
        if current_salary <= 0:
            raise HTTPException(status_code=400, detail="Salary must be positive")
        
        old_val = candidate.get("current_salary")
        if old_val != current_salary:
            audit_entries.append(create_profile_audit_entry(
                "current_salary", old_val, current_salary,
                current_user["id"], current_user["name"], current_user["role"],
                "manual_update"
            ))
            await create_audit_log(
                candidate_id, "current_salary", old_val, current_salary, 
                current_user, "manual_update"
            )
        update_data["current_salary"] = current_salary
        fields_updated.append("current_salary")
    
    if notice_period is not None:
        if not notice_period.strip():
            raise HTTPException(status_code=400, detail="Notice period cannot be empty")
        
        old_val = candidate.get("notice_period")
        if old_val != notice_period.strip():
            audit_entries.append(create_profile_audit_entry(
                "notice_period", old_val, notice_period.strip(),
                current_user["id"], current_user["name"], current_user["role"],
                "manual_update"
            ))
            await create_audit_log(
                candidate_id, "notice_period", old_val, notice_period.strip(),
                current_user, "manual_update"
            )
        update_data["notice_period"] = notice_period.strip()
        fields_updated.append("notice_period")
    
    if location is not None:
        if not location.strip():
            raise HTTPException(status_code=400, detail="Location cannot be empty")
        
        old_val = candidate.get("location")
        if old_val != location.strip():
            audit_entries.append(create_profile_audit_entry(
                "location", old_val, location.strip(),
                current_user["id"], current_user["name"], current_user["role"],
                "manual_update"
            ))
            await create_audit_log(
                candidate_id, "location", old_val, location.strip(),
                current_user, "manual_update"
            )
        update_data["location"] = location.strip()
        fields_updated.append("location")
    
    if experience_years is not None:
        if experience_years < 0:
            raise HTTPException(status_code=400, detail="Experience years cannot be negative")
        
        old_val = candidate.get("experience_years")
        if old_val != experience_years:
            audit_entries.append(create_profile_audit_entry(
                "experience_years", old_val, experience_years,
                current_user["id"], current_user["name"], current_user["role"],
                "manual_update"
            ))
            await create_audit_log(
                candidate_id, "experience_years", old_val, experience_years,
                current_user, "manual_update"
            )
        update_data["experience_years"] = experience_years
        fields_updated.append("experience_years")
    
    # Update freshness metadata
    update_data["last_profile_updated_at"] = now
    update_data["last_updated_by"] = current_user["id"]
    
    # Perform update with audit log appended
    update_ops = {"$set": update_data}
    if audit_entries:
        update_ops["$push"] = {"profile_update_audit": {"$each": audit_entries}}
    
    await db.candidate_bank.update_one({"id": candidate_id}, update_ops)
    
    return {
        "success": True,
        "message": "Candidate updated successfully",
        "candidate_id": candidate_id,
        "fields_updated": fields_updated
    }

@api_router.get("/candidate-bank", response_model=List[CandidateBankRecord])
async def get_candidate_bank(
    search: Optional[str] = None,
    skills: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get candidates from data bank based on role visibility"""
    
    query = {}
    
    # Role-based visibility
    if current_user["role"] == "admin":
        pass  # Full access
    elif current_user["role"] == "employer":
        query["$or"] = [
            {"visibility.employer_ids": current_user["id"]},
            {"source": "self"}
        ]
    elif current_user["role"] == "recruiter":
        query["$or"] = [
            {"visibility.recruiter_ids": current_user["id"]},
            {"created_by": current_user["id"]},
            {"source": "self"}
        ]
    elif current_user["role"] == "candidate":
        query["linked_user_id"] = current_user["id"]
    else:
        return []
    
    # Search filter
    if search:
        query["$and"] = query.get("$and", []) + [{
            "$or": [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"skills": {"$regex": search, "$options": "i"}}
            ]
        }]
    
    # Skills filter
    if skills:
        skill_list = [s.strip() for s in skills.split(",")]
        query["skills"] = {"$in": skill_list}
    
    candidates = await db.candidate_bank.find(query, {"_id": 0}).to_list(500)
    return [CandidateBankRecord(**c) for c in candidates]

@api_router.get("/candidate-bank/{candidate_id}")
async def get_candidate_bank_record(
    candidate_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get single candidate from data bank with visibility check"""
    
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Check visibility
    if current_user["role"] == "admin":
        pass
    elif current_user["role"] == "employer":
        if current_user["id"] not in candidate.get("visibility", {}).get("employer_ids", []) and candidate.get("source") != "self":
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user["role"] == "recruiter":
        vis = candidate.get("visibility", {})
        if (current_user["id"] not in vis.get("recruiter_ids", []) and 
            candidate.get("created_by") != current_user["id"] and
            candidate.get("source") != "self"):
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user["role"] == "candidate":
        if candidate.get("linked_user_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return candidate

@api_router.put("/candidate-bank/{candidate_id}")
async def update_candidate_bank_record(
    candidate_id: str,
    update_data: CandidateBankUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update candidate in data bank with priority rules and audit"""
    
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Determine source based on role and ownership
    if current_user["role"] == "candidate" and candidate.get("linked_user_id") == current_user["id"]:
        source = "candidate"
    else:
        source = current_user["role"]
    
    update_dict = {}
    for field, value in update_data.model_dump().items():
        if value is not None:
            if await should_update_field(candidate_id, field, source, db):
                old_val = candidate.get(field)
                if old_val != value:
                    update_dict[field] = value
                    await create_audit_log(candidate_id, field, old_val, value, current_user, f"{source}_update")
    
    if update_dict:
        update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_dict["last_updated_by"] = current_user["id"]
        
        await db.candidate_bank.update_one(
            {"id": candidate_id},
            {"$set": update_dict}
        )
    
    return {"message": "Candidate updated", "fields_updated": list(update_dict.keys())}

@api_router.get("/candidate-bank/{candidate_id}/audit-log")
async def get_candidate_audit_log(
    candidate_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Get audit trail for candidate"""
    
    logs = await db.audit_logs.find(
        {"candidate_id": candidate_id},
        {"_id": 0}
    ).sort("timestamp", -1).to_list(100)
    
    return logs


@api_router.get("/candidate-bank/{candidate_id}/history")
async def get_candidate_activity_history(
    candidate_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Data Governance: Get candidate's complete activity history.
    Internal-only endpoint for Admin, Employer, Recruiter.
    Shows all applications, stage changes, and outcomes across all jobs.
    """
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Get all applications for this candidate
    applications = await db.applications.find(
        {"candidate_id": candidate_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    # Enrich with job and company details
    enriched_applications = []
    for app in applications:
        job = await db.jobs.find_one({"id": app.get("job_id")}, {"title": 1, "company_id": 1, "location": 1, "_id": 0})
        company_name = "Unknown"
        if job and job.get("company_id"):
            company = await db.companies.find_one({"id": job.get("company_id")}, {"name": 1, "_id": 0})
            company_name = company.get("name") if company else app.get("company_name", "Unknown")
        
        enriched_applications.append({
            "application_id": app.get("id"),
            "job_id": app.get("job_id"),
            "job_title": job.get("title") if job else app.get("job_title", "Unknown"),
            "company_name": company_name,
            "job_location": job.get("location") if job else None,
            "stage": app.get("stage", "applied"),
            "source": app.get("source", "self"),
            "applied_at": app.get("created_at"),
            "last_updated": app.get("updated_at"),
            "current_salary_at_application": app.get("current_salary"),
            "notice_period_at_application": app.get("notice_period"),
            "has_notes": len(app.get("notes", [])) > 0,
            "edit_count": len(app.get("edit_history", []))
        })
    
    # Get stored application history from candidate record
    stored_history = candidate.get("application_history", [])
    
    # Profile freshness data
    freshness = {
        "last_profile_updated_at": candidate.get("last_profile_updated_at"),
        "last_application_date": candidate.get("last_application_date"),
        "profile_created_at": candidate.get("created_at"),
        "total_applications": len(applications)
    }
    
    # Profile audit trail for mandatory fields
    profile_audit = candidate.get("profile_update_audit", [])[-20:]  # Last 20 entries
    
    return {
        "candidate_id": candidate_id,
        "candidate_name": candidate.get("name"),
        "candidate_email": candidate.get("email"),
        "applications": enriched_applications,
        "stored_history": stored_history,
        "freshness": freshness,
        "profile_audit": profile_audit,
        "summary": {
            "total_applications": len(applications),
            "stages": {
                "applied": sum(1 for a in applications if a.get("stage") == "applied"),
                "shortlisted": sum(1 for a in applications if a.get("stage") == "shortlisted"),
                "interview": sum(1 for a in applications if a.get("stage") == "interview"),
                "offered": sum(1 for a in applications if a.get("stage") == "offered"),
                "hired": sum(1 for a in applications if a.get("stage") == "hired"),
                "rejected": sum(1 for a in applications if a.get("stage") == "rejected"),
            }
        }
    }


@api_router.get("/candidate-bank/{candidate_id}/resume-history")
async def get_candidate_resume_history(
    candidate_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get resume version history for candidate"""
    
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    return {
        "active_resume_id": candidate.get("active_resume_id"),
        "resume_versions": candidate.get("resume_versions", [])
    }

# ============== JOB ALERTS & NOTIFICATIONS ==============

from services.notification_service import (
    notify_candidate_of_job_match,
    process_job_notifications,
    trigger_job_notifications_background,
    send_alert_confirmation_email,
    get_candidate_notification_preferences
)
from services.whatsapp_service import validate_phone_number, is_whatsapp_enabled

@api_router.get("/alerts/preferences", response_model=JobAlertPreferences)
async def get_alert_preferences(current_user: dict = Depends(require_role(["candidate"]))):
    """Get candidate's job alert preferences"""
    prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    
    if not prefs:
        # Get candidate profile to populate default skills
        profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
        default_skills = profile.get("skills", []) if profile else []
        
        # Also check candidate_bank for skills
        if not default_skills:
            bank_record = await db.candidate_bank.find_one(
                {"$or": [{"linked_user_id": current_user["id"]}, {"email": current_user["email"]}]},
                {"_id": 0}
            )
            if bank_record:
                default_skills = bank_record.get("skills", [])
        
        # Create default preferences
        now = datetime.now(timezone.utc).isoformat()
        prefs = {
            "id": str(uuid.uuid4()),
            "candidate_id": current_user["id"],
            "candidate_email": current_user["email"],
            "is_active": False,  # Not active until explicitly enabled
            "email_enabled": True,
            "skills": default_skills[:10],  # Limit to 10 skills
            "location_preference": None,
            "experience_min": None,
            "experience_max": None,
            "job_types": [],
            "frequency": "instant",
            "whatsapp_opt_in": False,
            "whatsapp_number": None,
            "whatsapp_opt_in_timestamp": None,
            "notification_channels": ["email"],
            "created_at": now,
            "updated_at": now
        }
        await db.job_alerts.insert_one(prefs)
    
    return JobAlertPreferences(**prefs)


@api_router.post("/alerts/preferences", response_model=JobAlertPreferences)
async def create_or_update_alert_preferences(
    prefs_data: JobAlertCreate,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Create or update job alert preferences (opt-in to alerts)"""
    now = datetime.now(timezone.utc).isoformat()
    
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    
    update_dict = {k: v for k, v in prefs_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = now
    update_dict["is_active"] = True  # Activating alerts
    
    if existing:
        await db.job_alerts.update_one(
            {"candidate_id": current_user["id"]},
            {"$set": update_dict}
        )
        prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    else:
        # Get default skills from profile
        profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
        default_skills = profile.get("skills", []) if profile else []
        
        prefs = {
            "id": str(uuid.uuid4()),
            "candidate_id": current_user["id"],
            "candidate_email": current_user["email"],
            "is_active": True,
            "email_enabled": update_dict.get("email_enabled", True),
            "skills": update_dict.get("skills", default_skills[:10]),
            "location_preference": update_dict.get("location_preference"),
            "experience_min": update_dict.get("experience_min"),
            "experience_max": update_dict.get("experience_max"),
            "job_types": update_dict.get("job_types", []),
            "frequency": update_dict.get("frequency", "instant"),
            "whatsapp_opt_in": False,
            "whatsapp_number": None,
            "whatsapp_opt_in_timestamp": None,
            "notification_channels": ["email"],
            "created_at": now,
            "updated_at": now
        }
        await db.job_alerts.insert_one(prefs)
    
    # Send confirmation email
    asyncio.create_task(send_alert_confirmation_email(
        db=db,
        candidate_email=current_user["email"],
        candidate_name=current_user.get("name", "Candidate"),
        preferences=prefs
    ))
    
    return JobAlertPreferences(**prefs)


@api_router.put("/alerts/preferences", response_model=JobAlertPreferences)
async def update_alert_preferences(
    prefs_data: JobAlertCreate,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Update existing job alert preferences"""
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Alert preferences not found. Create them first.")
    
    update_dict = {k: v for k, v in prefs_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": update_dict}
    )
    
    prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    return JobAlertPreferences(**prefs)


@api_router.delete("/alerts/preferences")
async def delete_alert_preferences(current_user: dict = Depends(require_role(["candidate"]))):
    """Unsubscribe from all job alerts (soft delete - sets is_active to false)"""
    result = await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert preferences not found")
    
    return {"message": "Successfully unsubscribed from job alerts"}


@api_router.post("/alerts/pause")
async def pause_alerts(current_user: dict = Depends(require_role(["candidate"]))):
    """Temporarily pause job alerts"""
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Job alerts paused"}


@api_router.post("/alerts/resume")
async def resume_alerts(current_user: dict = Depends(require_role(["candidate"]))):
    """Resume paused job alerts"""
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {"is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Job alerts resumed"}


# ============== WHATSAPP OPT-IN/OUT ==============

@api_router.post("/alerts/whatsapp/opt-in", response_model=JobAlertPreferences)
async def whatsapp_opt_in(
    opt_in_data: WhatsAppOptIn,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """
    Opt-in to WhatsApp notifications.
    REQUIRES explicit consent and valid phone number.
    """
    if not is_whatsapp_enabled():
        raise HTTPException(
            status_code=400, 
            detail="WhatsApp notifications are not configured on this system"
        )
    
    # Validate phone number
    validated_phone = validate_phone_number(opt_in_data.whatsapp_number)
    if not validated_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format. Use E.164 format (e.g., +919876543210)")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Ensure alert preferences exist
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if not existing:
        # Create default preferences first
        prefs = {
            "id": str(uuid.uuid4()),
            "candidate_id": current_user["id"],
            "candidate_email": current_user["email"],
            "is_active": True,
            "email_enabled": True,
            "skills": [],
            "location_preference": None,
            "experience_min": None,
            "experience_max": None,
            "job_types": [],
            "frequency": "instant",
            "whatsapp_opt_in": True,
            "whatsapp_number": validated_phone,
            "whatsapp_opt_in_timestamp": now,
            "notification_channels": ["email", "whatsapp"],
            "created_at": now,
            "updated_at": now
        }
        await db.job_alerts.insert_one(prefs)
    else:
        # Update existing with WhatsApp opt-in
        update_data = {
            "whatsapp_opt_in": True,
            "whatsapp_number": validated_phone,
            "whatsapp_opt_in_timestamp": now,
            "notification_channels": list(set(existing.get("notification_channels", []) + ["whatsapp"])),
            "updated_at": now
        }
        await db.job_alerts.update_one(
            {"candidate_id": current_user["id"]},
            {"$set": update_data}
        )
    
    prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    return JobAlertPreferences(**prefs)


@api_router.post("/alerts/whatsapp/opt-out")
async def whatsapp_opt_out(current_user: dict = Depends(require_role(["candidate"]))):
    """
    Opt-out of WhatsApp notifications.
    Email notifications remain unaffected.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if existing:
        channels = existing.get("notification_channels", ["email"])
        if "whatsapp" in channels:
            channels.remove("whatsapp")
        
        await db.job_alerts.update_one(
            {"candidate_id": current_user["id"]},
            {"$set": {
                "whatsapp_opt_in": False,
                "notification_channels": channels,
                "updated_at": now
            }}
        )
    
    return {"message": "Successfully opted out of WhatsApp notifications"}


@api_router.put("/alerts/whatsapp/number")
async def update_whatsapp_number(
    opt_in_data: WhatsAppOptIn,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Update WhatsApp phone number (must already be opted in)"""
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if not existing or not existing.get("whatsapp_opt_in"):
        raise HTTPException(status_code=400, detail="Please opt-in to WhatsApp first")
    
    validated_phone = validate_phone_number(opt_in_data.whatsapp_number)
    if not validated_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {
            "whatsapp_number": validated_phone,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "WhatsApp number updated", "number": validated_phone}


# ============== NOTIFICATION HISTORY ==============

@api_router.get("/notifications/history")
async def get_notification_history(
    limit: int = 20,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Get notification history for current candidate"""
    notifications = await db.notification_logs.find(
        {"recipient_id": current_user["id"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return notifications


@api_router.get("/admin/notifications/stats")
async def get_notification_stats(current_user: dict = Depends(require_role(["admin"]))):
    """Get notification statistics (admin only)"""
    # Total notifications sent
    total_sent = await db.notification_logs.count_documents({"status": "sent"})
    total_failed = await db.notification_logs.count_documents({"status": "failed"})
    total_skipped = await db.notification_logs.count_documents({"status": "skipped"})
    
    # By channel
    email_sent = await db.notification_logs.count_documents({"channel": "email", "status": "sent"})
    whatsapp_sent = await db.notification_logs.count_documents({"channel": "whatsapp", "status": "sent"})
    
    # Active alert subscribers
    active_subscribers = await db.job_alerts.count_documents({"is_active": True})
    whatsapp_opted_in = await db.job_alerts.count_documents({"whatsapp_opt_in": True})
    
    return {
        "total_sent": total_sent,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "email_sent": email_sent,
        "whatsapp_sent": whatsapp_sent,
        "active_subscribers": active_subscribers,
        "whatsapp_opted_in": whatsapp_opted_in
    }


# ============== TRIGGER NOTIFICATIONS ON JOB EVENTS ==============

import asyncio

# Override job creation to trigger notifications
_original_create_job = None

@api_router.post("/jobs/with-notifications", response_model=JobResponse)
async def create_job_with_notifications(
    job_data: JobCreate,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Create a new job and trigger notifications to matching candidates.
    This is an alternative endpoint that includes notification triggering.
    """
    now = datetime.now(timezone.utc).isoformat()
    job_id = str(uuid.uuid4())
    
    # Get company_id for employers
    company_id = None
    if current_user["role"] == "employer":
        company_id = current_user.get("company_id")
    
    job_doc = {
        "id": job_id,
        **job_data.model_dump(),
        "company_id": company_id,
        "posted_by": current_user["id"],
        "status": "active",
        "applicant_count": 0,
        "created_at": now
    }
    
    await db.jobs.insert_one(job_doc)
    
    # Trigger notifications in background (non-blocking)
    asyncio.create_task(trigger_job_notifications_background(db, job_id))
    
    return JobResponse(**job_doc)


@api_router.post("/jobs/{job_id}/notify-candidates")
async def manually_trigger_notifications(
    job_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Manually trigger notifications for a job.
    Useful for re-notifying or notifying after job update.
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Trigger in background
    asyncio.create_task(trigger_job_notifications_background(db, job_id))
    
    return {"message": "Notification task started", "job_id": job_id}


# ============== PUBLIC API (NO AUTH REQUIRED) ==============

# Rate limiting storage (in-memory for Phase-1, use Redis in production)
rate_limit_store = {}

def check_rate_limit(identifier: str, limit: int = 10, window: int = 60) -> bool:
    """
    Simple rate limiter. Returns True if allowed, False if rate limited.
    identifier: IP or unique key
    limit: max requests per window
    window: time window in seconds
    """
    import time
    now = time.time()
    key = f"rate:{identifier}"
    
    if key not in rate_limit_store:
        rate_limit_store[key] = []
    
    # Clean old entries
    rate_limit_store[key] = [t for t in rate_limit_store[key] if now - t < window]
    
    if len(rate_limit_store[key]) >= limit:
        return False
    
    rate_limit_store[key].append(now)
    return True


class PublicApplicationCreate(BaseModel):
    """Public job application without login"""
    job_id: str
    email: EmailStr
    name: str
    phone: Optional[str] = None
    cover_letter: Optional[str] = None
    # Honeypot field - should be empty
    website: Optional[str] = None
    # Turnstile token for bot protection
    turnstile_token: Optional[str] = None


@api_router.get("/public/jobs")
async def get_public_jobs(
    search: Optional[str] = None,
    location: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 50
):
    """
    Get active job listings (PUBLIC - NO AUTH REQUIRED).
    For careers page on public website.
    
    CLIENT PRIVACY: Returns public_company_alias instead of real company name.
    Only ACTIVE jobs are visible to the public.
    """
    query = {"status": "active"}
    
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"department": {"$regex": search, "$options": "i"}}
        ]
    
    if location:
        query["location"] = {"$regex": location, "$options": "i"}
    
    if job_type:
        query["job_type"] = job_type
    
    jobs = await db.jobs.find(query, {"_id": 0}).limit(limit).to_list(limit)
    
    # CLIENT PRIVACY: Use public_company_alias for public listings
    for job in jobs:
        # Mask company name with public_company_alias (privacy protection)
        if job.get("public_company_alias"):
            job["company_name"] = job["public_company_alias"]
        else:
            job["company_name"] = "Confidential Client"
        # Remove internal company_id from public response
        job.pop("company_id", None)
    
    return jobs


@api_router.get("/public/jobs/{job_id}")
async def get_public_job_detail(job_id: str):
    """
    Get single job detail (PUBLIC - NO AUTH REQUIRED).
    
    CLIENT PRIVACY: Returns public_company_alias instead of real company name.
    """
    job = await db.jobs.find_one({"id": job_id, "status": "active"}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # CLIENT PRIVACY: Use public_company_alias for public view
    if job.get("public_company_alias"):
        job["company_name"] = job["public_company_alias"]
    else:
        job["company_name"] = "Confidential Client"
    # Remove internal company_id from public response
    job.pop("company_id", None)
    
    return job


from fastapi import Request

def calculate_career_stability(experience: List[Dict]) -> Dict:
    """
    Calculate career stability based on job tenure.
    Returns: {score: 'green'|'yellow'|'red', quick_changes: int, tooltip: str}
    
    Rules:
    - Green: 0-1 quick changes (≤1 year tenure)
    - Yellow: 2-3 quick changes
    - Red: More than 3 quick changes
    """
    import re
    
    if not experience:
        return {"score": "green", "quick_changes": 0, "tooltip": "No work history available"}
    
    quick_changes = 0
    
    for job in experience:
        duration = job.get("duration", "").lower()
        
        # Parse duration to check if ≤1 year
        is_quick = False
        if "month" in duration:
            # Extract months
            months_match = re.search(r'(\d+)\s*month', duration)
            if months_match:
                months = int(months_match.group(1))
                if months <= 12:
                    is_quick = True
        elif "year" in duration:
            years_match = re.search(r'(\d+)\s*year', duration)
            if years_match:
                years = int(years_match.group(1))
                if years < 1:
                    is_quick = True
        elif any(term in duration for term in ["present", "current", "ongoing"]):
            # Current job, don't count
            pass
        else:
            # Unknown format, assume not quick
            pass
        
        if is_quick:
            quick_changes += 1
    
    if quick_changes <= 1:
        return {
            "score": "green",
            "quick_changes": quick_changes,
            "tooltip": f"Stable career history ({quick_changes} short tenure)"
        }
    elif quick_changes <= 3:
        return {
            "score": "yellow",
            "quick_changes": quick_changes,
            "tooltip": f"Moderate job changes ({quick_changes} short tenures)"
        }
    else:
        return {
            "score": "red",
            "quick_changes": quick_changes,
            "tooltip": f"Frequent job changes ({quick_changes} short tenures)"
        }


@api_router.post("/public/parse-resume")
async def public_parse_resume(
    request: Request,
    resume: UploadFile = File(...),
    website: Optional[str] = Form(None),  # Honeypot
):
    """
    Parse resume and return extracted data for review (NO LOGIN REQUIRED).
    Step 1 of two-step apply flow.
    """
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    # Rate limit: 10 parses per minute per IP
    if not check_rate_limit(f"parse:{client_ip}", limit=10, window=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    
    # Honeypot check
    if website:
        logger.warning(f"[BOT] Honeypot triggered from {client_ip}")
        return {"success": True, "parsed_data": {}}
    
    # Save resume file temporarily
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f"temp_{timestamp}_{resume.filename}"
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / filename
    async with aiofiles.open(file_path, 'wb') as f:
        content = await resume.read()
        await f.write(content)
    
    # Extract resume text
    resume_text = ""
    try:
        if filename.lower().endswith('.pdf'):
            doc = fitz.open(str(file_path))
            for page in doc:
                resume_text += page.get_text()
            doc.close()
        elif filename.lower().endswith('.txt'):
            async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                resume_text = await f.read()
    except Exception as e:
        logger.error(f"[PARSE] Resume text extraction failed: {e}")
    
    # Parse resume with AI
    parsed_data = {}
    try:
        from services.matching_engine import parse_resume_with_ai
        result = await parse_resume_with_ai(resume_text[:8000])
        if result.get("success"):
            parsed_data = result.get("data", {})
    except Exception as e:
        logger.error(f"[PARSE] AI parsing failed: {e}")
    
    # Calculate career stability
    career_stability = calculate_career_stability(parsed_data.get("experience", []))
    
    return {
        "success": True,
        "parsed_data": {
            "name": parsed_data.get("name"),
            "email": parsed_data.get("email"),
            "phone": parsed_data.get("phone"),
            "headline": parsed_data.get("headline"),
            "summary": parsed_data.get("summary"),
            "skills": parsed_data.get("skills", []),
            "experience_years": parsed_data.get("experience_years", 0),
            "experience": parsed_data.get("experience", []),
            "education": parsed_data.get("education", []),
            "location": parsed_data.get("location"),
            "certifications": parsed_data.get("certifications", [])
        },
        "career_stability": career_stability,
        "resume_filename": filename,
        "resume_url": f"/api/uploads/{filename}"
    }


@api_router.post("/public/apply")
async def public_apply(
    request: Request,
    job_id: str = Form(...),
    email: str = Form(...),
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    cover_letter: Optional[str] = Form(None),
    current_salary: Optional[int] = Form(None),  # INR - from review step
    notice_period: Optional[str] = Form(None),  # e.g., "30 days", "2 weeks", "immediate"
    skills: Optional[str] = Form(None),  # Comma-separated, edited by candidate
    experience_years: Optional[int] = Form(None),  # Candidate-corrected value
    location: Optional[str] = Form(None),  # Candidate-corrected value
    headline: Optional[str] = Form(None),  # Candidate-corrected value
    resume: UploadFile = File(None),  # Optional if resume_filename provided from parse step
    resume_filename: Optional[str] = Form(None),  # From /public/parse-resume step
    website: Optional[str] = Form(None),  # Honeypot
    turnstile_token: Optional[str] = Form(None)
):
    """
    Public job application (NO LOGIN REQUIRED).
    Supports two-step apply flow:
    - Step 1: Candidate uploads resume via /public/parse-resume, gets parsed data
    - Step 2: Candidate reviews/edits data, adds salary & notice period, then submits here
    
    Can also accept direct resume upload for single-step apply.
    """
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    # Rate limit: 5 applications per minute per IP
    if not check_rate_limit(f"apply:{client_ip}", limit=5, window=60):
        raise HTTPException(status_code=429, detail="Too many applications. Please try again later.")
    
    # Honeypot check - if website field is filled, it's a bot
    if website:
        logger.warning(f"[BOT] Honeypot triggered from {client_ip}")
        # Return success to not tip off bots, but don't process
        return {"success": True, "message": "Application submitted successfully", "application_id": str(uuid.uuid4())}
    
    # Verify job exists
    job = await db.jobs.find_one({"id": job_id, "status": "active"}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or no longer active")
    
    # Validate email
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    
    # Handle resume - either from parse step or new upload
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(exist_ok=True)
    filename = None
    resume_text = ""
    parsed_data = {}
    
    if resume_filename:
        # Two-step flow: resume was already parsed, use the existing file
        file_path = upload_dir / resume_filename
        if not file_path.exists():
            raise HTTPException(status_code=400, detail="Resume file not found. Please re-upload your resume.")
        filename = resume_filename
        
        # Use candidate-provided data from review step (already corrected by candidate)
        parsed_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "headline": headline,
            "skills": [s.strip() for s in skills.split(",")] if skills else [],
            "experience_years": experience_years or 0,
            "location": location
        }
        
        # Extract resume text for storage
        try:
            if filename.lower().endswith('.pdf'):
                doc = fitz.open(str(file_path))
                for page in doc:
                    resume_text += page.get_text()
                doc.close()
            elif filename.lower().endswith('.txt'):
                async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                    resume_text = await f.read()
        except Exception as e:
            logger.error(f"[PUBLIC APPLY] Resume text extraction failed: {e}")
    elif resume:
        # Single-step flow: new resume upload, parse it now
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        safe_email = email.replace('@', '_at_').replace('.', '_')
        filename = f"public_{safe_email}_{timestamp}_{resume.filename}"
        
        file_path = upload_dir / filename
        async with aiofiles.open(file_path, 'wb') as f:
            content = await resume.read()
            await f.write(content)
        
        # Extract resume text
        try:
            if filename.lower().endswith('.pdf'):
                doc = fitz.open(str(file_path))
                for page in doc:
                    resume_text += page.get_text()
                doc.close()
            elif filename.lower().endswith('.txt'):
                async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                    resume_text = await f.read()
        except Exception as e:
            logger.error(f"[PUBLIC APPLY] Resume text extraction failed: {e}")
        
        # Parse resume with AI
        try:
            from services.matching_engine import parse_resume_with_ai
            result = await parse_resume_with_ai(resume_text[:8000])
            if result.get("success"):
                parsed_data = result.get("data", {})
        except Exception as e:
            logger.error(f"[PUBLIC APPLY] AI parsing failed: {e}")
    else:
        raise HTTPException(status_code=400, detail="Resume is required. Please upload a resume file.")
    
    # Check if candidate already exists in data bank
    existing_candidate = await db.candidate_bank.find_one({
        "$or": [
            {"email": email},
            {"phone": phone} if phone else {"email": email}
        ]
    }, {"_id": 0})
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Prepare skills list (from candidate-edited or parsed data)
    final_skills = parsed_data.get("skills", [])
    if skills and isinstance(skills, str):
        final_skills = [s.strip() for s in skills.split(",") if s.strip()]
    
    if existing_candidate:
        candidate_id = existing_candidate["id"]
        # Update with new data
        update_data = {
            "skills": final_skills or existing_candidate.get("skills", []),
            "experience_years": experience_years if experience_years is not None else existing_candidate.get("experience_years", 0),
            "current_salary": current_salary,
            "notice_period": notice_period,
            "updated_at": now
        }
        if location:
            update_data["location"] = location
        if headline:
            update_data["headline"] = headline
        if filename:
            update_data["resume_url"] = f"/api/uploads/{filename}"
        
        await db.candidate_bank.update_one(
            {"id": candidate_id},
            {"$set": update_data}
        )
    else:
        # Create new candidate in data bank
        candidate_id = str(uuid.uuid4())
        candidate_doc = {
            "id": candidate_id,
            "name": parsed_data.get("name") or name,
            "email": email,
            "phone": parsed_data.get("phone") or phone,
            "headline": headline or parsed_data.get("headline"),
            "summary": parsed_data.get("summary"),
            "skills": final_skills,
            "experience_years": experience_years if experience_years is not None else parsed_data.get("experience_years", 0),
            "experience": parsed_data.get("experience", []),
            "education": parsed_data.get("education", []),
            "location": location or parsed_data.get("location"),
            "current_salary": current_salary,  # INR
            "notice_period": notice_period,
            "source": "public_application",
            "source_job_id": job_id,
            "resume_url": f"/api/uploads/{filename}" if filename else None,
            "resume_text": resume_text[:5000],
            "is_active": True,
            "linked_user_id": None,  # Not linked to any user account
            "created_at": now,
            "updated_at": now
        }
        await db.candidate_bank.insert_one(candidate_doc)
    
    # Create application with salary and notice period
    application_id = str(uuid.uuid4())
    application_doc = {
        "id": application_id,
        "job_id": job_id,
        "candidate_id": candidate_id,
        "candidate_name": parsed_data.get("name") or name,
        "candidate_email": email,
        "candidate_phone": phone,
        "resume_url": f"/api/uploads/{filename}" if filename else None,
        "cover_letter": cover_letter,
        "current_salary": current_salary,  # INR
        "notice_period": notice_period,
        "skills": final_skills,
        "experience_years": experience_years if experience_years is not None else parsed_data.get("experience_years", 0),
        "location": location or parsed_data.get("location"),
        "headline": headline or parsed_data.get("headline"),
        "stage": "applied",
        "source": "public_website",
        "notes": [],
        "applied_at": now,
        "updated_at": now
    }
    await db.applications.insert_one(application_doc)
    
    # Update job applicant count
    await db.jobs.update_one({"id": job_id}, {"$inc": {"applicant_count": 1}})
    
    logger.info(f"[PUBLIC APPLY] New application from {email} for job {job_id}")
    
    return {
        "success": True,
        "message": "Application submitted successfully! We'll review your profile and get back to you.",
        "application_id": application_id,
        "candidate_id": candidate_id,
        "parsed_skills": parsed_data.get("skills", [])[:5]
    }


@api_router.post("/public/upload-resume")
async def public_upload_resume(
    request: Request,
    email: str = Form(...),
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    resume: UploadFile = File(...),
    website: Optional[str] = Form(None),  # Honeypot
):
    """
    Public resume upload to candidate data bank (NO LOGIN REQUIRED).
    For candidates who want to be in the talent pool without applying to specific job.
    """
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    # Rate limit: 3 uploads per hour per IP
    if not check_rate_limit(f"upload:{client_ip}", limit=3, window=3600):
        raise HTTPException(status_code=429, detail="Too many uploads. Please try again later.")
    
    # Honeypot check
    if website:
        logger.warning(f"[BOT] Honeypot triggered from {client_ip}")
        return {"success": True, "message": "Resume uploaded successfully"}
    
    # Save and process similar to apply
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    safe_email = email.replace('@', '_at_').replace('.', '_')
    filename = f"pool_{safe_email}_{timestamp}_{resume.filename}"
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / filename
    async with aiofiles.open(file_path, 'wb') as f:
        content = await resume.read()
        await f.write(content)
    
    # Extract and parse
    resume_text = ""
    try:
        if filename.lower().endswith('.pdf'):
            doc = fitz.open(str(file_path))
            for page in doc:
                resume_text += page.get_text()
            doc.close()
        elif filename.lower().endswith('.txt'):
            async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                resume_text = await f.read()
    except Exception as e:
        logger.error(f"Resume extraction failed: {e}")
    
    parsed_data = {}
    try:
        from services.matching_engine import parse_resume_with_ai
        result = await parse_resume_with_ai(resume_text[:8000])
        if result.get("success"):
            parsed_data = result.get("data", {})
    except Exception as e:
        logger.error(f"AI parsing failed: {e}")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Check existing
    existing = await db.candidate_bank.find_one({"email": email}, {"_id": 0})
    if existing:
        candidate_id = existing["id"]
        await db.candidate_bank.update_one(
            {"id": candidate_id},
            {"$set": {
                "name": parsed_data.get("name") or name,
                "skills": parsed_data.get("skills", existing.get("skills", [])),
                "experience_years": parsed_data.get("experience_years", existing.get("experience_years", 0)),
                "resume_url": f"/api/uploads/{filename}",
                "updated_at": now
            }}
        )
    else:
        candidate_id = str(uuid.uuid4())
        candidate_doc = {
            "id": candidate_id,
            "name": parsed_data.get("name") or name,
            "email": email,
            "phone": parsed_data.get("phone") or phone,
            "headline": parsed_data.get("headline"),
            "summary": parsed_data.get("summary"),
            "skills": parsed_data.get("skills", []),
            "experience_years": parsed_data.get("experience_years", 0),
            "experience": parsed_data.get("experience", []),
            "education": parsed_data.get("education", []),
            "location": parsed_data.get("location"),
            "source": "talent_pool_upload",
            "resume_url": f"/api/uploads/{filename}",
            "resume_text": resume_text[:5000],
            "is_active": True,
            "linked_user_id": None,
            "created_at": now,
            "updated_at": now
        }
        await db.candidate_bank.insert_one(candidate_doc)
    
    return {
        "success": True,
        "message": "Resume uploaded to our talent pool! We'll reach out when matching opportunities arise.",
        "candidate_id": candidate_id,
        "parsed_skills": parsed_data.get("skills", [])[:5]
    }


# ============== SETTINGS ==============

@api_router.get("/settings")
async def get_settings(current_user: dict = Depends(require_role(["admin"]))):
    settings = await db.settings.find_one({"type": "global"}, {"_id": 0})
    if not settings:
        settings = {
            "type": "global",
            "ai_parsing_enabled": True,
            "email_notifications": True,
            "max_applications_per_job": 100,
            "resume_size_limit_mb": 5
        }
        await db.settings.insert_one(settings)
    return settings

@api_router.put("/settings")
async def update_settings(settings_data: dict, current_user: dict = Depends(require_role(["admin"]))):
    await db.settings.update_one(
        {"type": "global"},
        {"$set": settings_data},
        upsert=True
    )
    return {"message": "Settings updated successfully"}

# ============== PHASE-A: TEAM MANAGEMENT ==============

@api_router.post("/teams", response_model=TeamResponse)
async def create_team(team_data: TeamCreate, current_user: dict = Depends(require_role(["admin"]))):
    """
    Create a new Team (Admin only).
    
    A Team links:
    - One Employer (team owner/manager)
    - Multiple Recruiters (team members)
    - Multiple Companies (client companies the team manages)
    """
    # Validate employer exists and has correct role
    employer = await db.users.find_one({"id": team_data.employer_id, "role": "employer"}, {"_id": 0})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    
    # Validate all recruiters exist and have correct role
    recruiter_names = []
    for recruiter_id in team_data.recruiter_ids:
        recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"}, {"_id": 0})
        if not recruiter:
            raise HTTPException(status_code=400, detail=f"Recruiter {recruiter_id} not found")
        recruiter_names.append(recruiter.get("name", "Unknown"))
    
    # Validate all companies exist
    company_names = []
    for company_id in team_data.company_ids:
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if not company:
            raise HTTPException(status_code=400, detail=f"Company {company_id} not found")
        company_names.append(company.get("name", "Unknown"))
    
    team_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    team_doc = {
        "id": team_id,
        "name": team_data.name,
        "employer_id": team_data.employer_id,
        "employer_name": employer.get("name"),
        "recruiter_ids": team_data.recruiter_ids,
        "recruiter_names": recruiter_names,
        "company_ids": team_data.company_ids,
        "company_names": company_names,
        "status": "active",
        "active_jobs_count": 0,
        "created_at": now,
        "updated_at": now,
        "created_by": current_user["id"],
        "audit_log": [{
            "action": "created",
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        }]
    }
    
    await db.teams.insert_one(team_doc)
    
    # Update recruiters with team assignment
    for recruiter_id in team_data.recruiter_ids:
        await db.users.update_one(
            {"id": recruiter_id},
            {"$set": {"team_id": team_id, "updated_at": now}}
        )
    
    # Update companies with employer assignment
    for company_id in team_data.company_ids:
        await db.companies.update_one(
            {"id": company_id},
            {"$set": {"assigned_employer_id": team_data.employer_id, "team_id": team_id, "updated_at": now}}
        )
    
    logging.info(f"Team '{team_data.name}' created by {current_user['name']}")
    
    return TeamResponse(**team_doc)


@api_router.get("/teams", response_model=List[TeamResponse])
async def get_teams(current_user: dict = Depends(require_role(["admin", "employer"]))):
    """
    Get all teams.
    - Admin: sees all teams
    - Employer: sees only their teams
    """
    query = {}
    if current_user["role"] == "employer":
        query["employer_id"] = current_user["id"]
    
    teams = await db.teams.find(query, {"_id": 0}).to_list(1000)
    
    # Enrich with active jobs count
    for team in teams:
        jobs_count = await db.jobs.count_documents({
            "team_id": team["id"],
            "status": {"$in": ["active", "pending_approval"]}
        })
        team["active_jobs_count"] = jobs_count
    
    return [TeamResponse(**t) for t in teams]


@api_router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str, current_user: dict = Depends(require_role(["admin", "employer"]))):
    """Get a specific team by ID."""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Employer can only view their own teams
    if current_user["role"] == "employer" and team["employer_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get active jobs count
    jobs_count = await db.jobs.count_documents({
        "team_id": team_id,
        "status": {"$in": ["active", "pending_approval"]}
    })
    team["active_jobs_count"] = jobs_count
    
    return TeamResponse(**team)


@api_router.put("/teams/{team_id}", response_model=TeamResponse)
async def update_team(team_id: str, update_data: TeamUpdate, current_user: dict = Depends(require_role(["admin"]))):
    """
    Update a team (Admin only).
    Can update name, recruiters, companies, and status.
    """
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = {"updated_at": now}
    audit_entries = []
    
    if update_data.name is not None:
        audit_entries.append({
            "action": "name_changed",
            "old_value": team.get("name"),
            "new_value": update_data.name,
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        })
        update_dict["name"] = update_data.name
    
    if update_data.status is not None:
        audit_entries.append({
            "action": "status_changed",
            "old_value": team.get("status"),
            "new_value": update_data.status,
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        })
        update_dict["status"] = update_data.status
    
    if update_data.recruiter_ids is not None:
        # Validate new recruiters
        recruiter_names = []
        for recruiter_id in update_data.recruiter_ids:
            recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"}, {"_id": 0})
            if not recruiter:
                raise HTTPException(status_code=400, detail=f"Recruiter {recruiter_id} not found")
            recruiter_names.append(recruiter.get("name", "Unknown"))
        
        # Remove old recruiters from team
        old_recruiter_ids = team.get("recruiter_ids", [])
        for old_id in old_recruiter_ids:
            if old_id not in update_data.recruiter_ids:
                await db.users.update_one(
                    {"id": old_id},
                    {"$unset": {"team_id": ""}}
                )
        
        # Add new recruiters to team
        for new_id in update_data.recruiter_ids:
            await db.users.update_one(
                {"id": new_id},
                {"$set": {"team_id": team_id, "updated_at": now}}
            )
        
        audit_entries.append({
            "action": "recruiters_changed",
            "old_value": old_recruiter_ids,
            "new_value": update_data.recruiter_ids,
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        })
        update_dict["recruiter_ids"] = update_data.recruiter_ids
        update_dict["recruiter_names"] = recruiter_names
    
    if update_data.company_ids is not None:
        # Validate new companies
        company_names = []
        for company_id in update_data.company_ids:
            company = await db.companies.find_one({"id": company_id}, {"_id": 0})
            if not company:
                raise HTTPException(status_code=400, detail=f"Company {company_id} not found")
            company_names.append(company.get("name", "Unknown"))
        
        # Update company assignments
        old_company_ids = team.get("company_ids", [])
        for old_id in old_company_ids:
            if old_id not in update_data.company_ids:
                await db.companies.update_one(
                    {"id": old_id},
                    {"$unset": {"assigned_employer_id": "", "team_id": ""}}
                )
        
        for new_id in update_data.company_ids:
            await db.companies.update_one(
                {"id": new_id},
                {"$set": {"assigned_employer_id": team["employer_id"], "team_id": team_id, "updated_at": now}}
            )
        
        audit_entries.append({
            "action": "companies_changed",
            "old_value": old_company_ids,
            "new_value": update_data.company_ids,
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        })
        update_dict["company_ids"] = update_data.company_ids
        update_dict["company_names"] = company_names
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$set": update_dict,
            "$push": {"audit_log": {"$each": audit_entries}}
        }
    )
    
    updated_team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    return TeamResponse(**updated_team)


@api_router.delete("/teams/{team_id}")
async def delete_team(team_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """
    Soft delete a team (Admin only).
    Sets status to 'disabled' instead of actual deletion.
    """
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$set": {"status": "disabled", "updated_at": now},
            "$push": {"audit_log": {
                "action": "disabled",
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "by_role": current_user["role"],
                "timestamp": now
            }}
        }
    )
    
    logging.info(f"Team {team_id} disabled by {current_user['name']}")
    
    return {"message": "Team disabled successfully"}


# ============== PHASE-A: REFERRAL MANAGEMENT ==============

@api_router.post("/referrals", response_model=ReferralResponse)
async def create_referral(referral_data: ReferralCreate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    """
    Create a new candidate referral.
    
    Referral Lifecycle:
    1. submitted - Initial submission
    2. validated - Referral details verified
    3. linked - Linked to candidate bank record
    4. in_process - Candidate is being processed for the job
    5. outcome_reached - Hiring decision made
    6. closed - Referral process complete
    """
    # Validate job exists and is active
    job = await db.jobs.find_one({"id": referral_data.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "active":
        raise HTTPException(status_code=400, detail="Can only refer candidates to active jobs")
    
    # Check for duplicate referral (same email + job)
    existing = await db.referrals.find_one({
        "job_id": referral_data.job_id,
        "candidate_email": referral_data.candidate_email.lower()
    })
    if existing:
        raise HTTPException(status_code=400, detail="This candidate has already been referred for this job")
    
    referral_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    referral_doc = {
        "id": referral_id,
        "job_id": referral_data.job_id,
        "job_title": job.get("title"),
        "referrer_id": current_user["id"],
        "referrer_name": current_user["name"],
        "candidate_name": referral_data.candidate_name,
        "candidate_email": referral_data.candidate_email.lower(),
        "candidate_phone": referral_data.candidate_phone,
        "resume_url": referral_data.resume_url,
        "note": referral_data.note,
        "status": "submitted",
        "linked_candidate_id": None,
        "linked_application_id": None,
        "status_history": [{
            "status": "submitted",
            "changed_by": current_user["id"],
            "changed_by_name": current_user["name"],
            "changed_by_role": current_user["role"],
            "timestamp": now,
            "reason": "Referral submitted"
        }],
        "created_at": now,
        "updated_at": now
    }
    
    await db.referrals.insert_one(referral_doc)
    
    logging.info(f"Referral {referral_id} created by {current_user['name']} for job {referral_data.job_id}")
    
    return ReferralResponse(**referral_doc)


@api_router.get("/referrals", response_model=List[ReferralResponse])
async def get_referrals(
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Get referrals based on user role.
    - Admin: sees all referrals
    - Employer: sees referrals for their team's jobs
    - Recruiter: sees their own referrals
    """
    query = {}
    
    if current_user["role"] == "recruiter":
        query["referrer_id"] = current_user["id"]
    elif current_user["role"] == "employer":
        # Get jobs from employer's team
        team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
        if team:
            team_jobs = await db.jobs.find({"team_id": team["id"]}, {"id": 1, "_id": 0}).to_list(1000)
            job_ids = [j["id"] for j in team_jobs]
            query["job_id"] = {"$in": job_ids}
        else:
            # No team, return empty
            return []
    
    if job_id:
        query["job_id"] = job_id
    if status:
        query["status"] = status
    
    referrals = await db.referrals.find(query, {"_id": 0}).to_list(1000)
    return [ReferralResponse(**r) for r in referrals]


@api_router.get("/referrals/{referral_id}", response_model=ReferralResponse)
async def get_referral(referral_id: str, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    """Get a specific referral by ID."""
    referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    
    # Access control for non-admin users
    if current_user["role"] == "recruiter":
        if referral["referrer_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user["role"] == "employer":
        # Check if job belongs to employer's team
        job = await db.jobs.find_one({"id": referral["job_id"]}, {"_id": 0})
        if job:
            team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
            if not team or job.get("team_id") != team["id"]:
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return ReferralResponse(**referral)


@api_router.post("/referrals/{referral_id}/transition", response_model=ReferralResponse)
async def transition_referral_status(
    referral_id: str,
    transition: ReferralStatusUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Transition referral status with audit logging.
    
    Valid transitions:
    - submitted -> validated, closed
    - validated -> linked, closed
    - linked -> in_process, closed
    - in_process -> outcome_reached, closed
    - outcome_reached -> closed
    - closed -> (no transitions, final state)
    """
    referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    
    current_status = referral.get("status", "submitted")
    new_status = transition.new_status
    
    # Define valid transitions
    valid_transitions = {
        "submitted": ["validated", "closed"],
        "validated": ["linked", "closed"],
        "linked": ["in_process", "closed"],
        "in_process": ["outcome_reached", "closed"],
        "outcome_reached": ["closed"],
        "closed": []  # Final state
    }
    
    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from {current_status} to {new_status}"
        )
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Create audit entry
    audit_entry = {
        "from_status": current_status,
        "to_status": new_status,
        "changed_by": current_user["id"],
        "changed_by_name": current_user["name"],
        "changed_by_role": current_user["role"],
        "timestamp": now,
        "reason": transition.reason or f"Status changed from {current_status} to {new_status}"
    }
    
    await db.referrals.update_one(
        {"id": referral_id},
        {
            "$set": {"status": new_status, "updated_at": now},
            "$push": {"status_history": audit_entry}
        }
    )
    
    logging.info(f"Referral {referral_id} transitioned from {current_status} to {new_status} by {current_user['name']}")
    
    updated_referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    return ReferralResponse(**updated_referral)


@api_router.post("/referrals/{referral_id}/link-candidate")
async def link_referral_to_candidate(
    referral_id: str,
    candidate_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Link a referral to an existing candidate bank record, or create a new candidate.
    
    If candidate_id is provided: links to existing candidate
    If not provided: creates new candidate from referral data
    """
    referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    
    if referral.get("status") not in ["submitted", "validated"]:
        raise HTTPException(status_code=400, detail="Can only link referrals in submitted or validated status")
    
    now = datetime.now(timezone.utc).isoformat()
    
    if candidate_id:
        # Link to existing candidate
        candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
    else:
        # Create new candidate from referral data
        candidate_id = str(uuid.uuid4())
        candidate_doc = {
            "id": candidate_id,
            "email": referral["candidate_email"],
            "name": referral["candidate_name"],
            "phone": referral.get("candidate_phone"),
            "phone_normalized": referral.get("candidate_phone"),
            "skills": [],
            "experience_years": 0,
            "experience": [],
            "education": [],
            "resume_url": referral.get("resume_url"),
            "source": "referral",
            "source_referral_id": referral_id,
            "visibility": {
                f"{current_user['role']}_ids": [current_user["id"]]
            },
            "created_at": now,
            "updated_at": now,
            "created_by": current_user["id"]
        }
        await db.candidate_bank.insert_one(candidate_doc)
    
    # Update referral with link
    await db.referrals.update_one(
        {"id": referral_id},
        {
            "$set": {
                "status": "linked",
                "linked_candidate_id": candidate_id,
                "updated_at": now
            },
            "$push": {"status_history": {
                "from_status": referral["status"],
                "to_status": "linked",
                "changed_by": current_user["id"],
                "changed_by_name": current_user["name"],
                "changed_by_role": current_user["role"],
                "timestamp": now,
                "reason": f"Linked to candidate {candidate_id}"
            }}
        }
    )
    
    return {
        "message": "Referral linked to candidate successfully",
        "referral_id": referral_id,
        "candidate_id": candidate_id
    }


# ============== PHASE-A: COMPANY-EMPLOYER ASSIGNMENT ==============

@api_router.put("/companies/{company_id}/assign-employer")
async def assign_employer_to_company(
    company_id: str,
    employer_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Assign an employer to manage a company (Admin only).
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    employer = await db.users.find_one({"id": employer_id, "role": "employer"}, {"_id": 0})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.companies.update_one(
        {"id": company_id},
        {"$set": {
            "assigned_employer_id": employer_id,
            "assigned_employer_name": employer.get("name"),
            "updated_at": now
        }}
    )
    
    return {
        "message": "Employer assigned to company successfully",
        "company_id": company_id,
        "employer_id": employer_id,
        "employer_name": employer.get("name")
    }


@api_router.put("/companies/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: str,
    update_data: CompanyUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Update company details.
    - Admin: can update any company
    - Employer: can only update companies assigned to them
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Access control for employers
    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You are not assigned to this company")
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.companies.update_one({"id": company_id}, {"$set": update_dict})
    
    updated_company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    return CompanyResponse(**updated_company)


# ============== PHASE-A: ADMIN HIERARCHY OVERVIEW ==============

@api_router.get("/admin/hierarchy")
async def get_admin_hierarchy(current_user: dict = Depends(require_role(["admin"]))):
    """
    Get complete hierarchy overview for Admin.
    Shows: Employers -> Teams -> Recruiters -> Companies
    """
    # Get all employers
    employers = await db.users.find({"role": "employer", "is_active": True}, {"_id": 0, "password": 0}).to_list(1000)
    
    hierarchy = []
    
    for employer in employers:
        employer_data = {
            "employer_id": employer["id"],
            "employer_name": employer["name"],
            "employer_email": employer["email"],
            "teams": []
        }
        
        # Get teams for this employer
        teams = await db.teams.find({"employer_id": employer["id"], "status": "active"}, {"_id": 0}).to_list(100)
        
        for team in teams:
            # Get active jobs count
            jobs_count = await db.jobs.count_documents({
                "team_id": team["id"],
                "status": {"$in": ["active", "pending_approval"]}
            })
            
            team_data = {
                "team_id": team["id"],
                "team_name": team["name"],
                "active_jobs_count": jobs_count,
                "recruiters": [],
                "companies": []
            }
            
            # Get recruiters in this team
            for recruiter_id in team.get("recruiter_ids", []):
                recruiter = await db.users.find_one({"id": recruiter_id}, {"_id": 0, "password": 0})
                if recruiter:
                    team_data["recruiters"].append({
                        "id": recruiter["id"],
                        "name": recruiter["name"],
                        "email": recruiter["email"]
                    })
            
            # Get companies in this team
            for company_id in team.get("company_ids", []):
                company = await db.companies.find_one({"id": company_id}, {"_id": 0})
                if company:
                    team_data["companies"].append({
                        "id": company["id"],
                        "name": company["name"],
                        "industry": company.get("industry")
                    })
            
            employer_data["teams"].append(team_data)
        
        hierarchy.append(employer_data)
    
    # Get unassigned recruiters
    unassigned_recruiters = await db.users.find(
        {"role": "recruiter", "is_active": True, "team_id": {"$exists": False}},
        {"_id": 0, "password": 0}
    ).to_list(1000)
    
    # Get unassigned companies
    unassigned_companies = await db.companies.find(
        {"assigned_employer_id": {"$exists": False}},
        {"_id": 0}
    ).to_list(1000)
    
    return {
        "hierarchy": hierarchy,
        "unassigned_recruiters": [{"id": r["id"], "name": r["name"], "email": r["email"]} for r in unassigned_recruiters],
        "unassigned_companies": [{"id": c["id"], "name": c["name"]} for c in unassigned_companies],
        "summary": {
            "total_employers": len(employers),
            "total_teams": sum(len(e["teams"]) for e in hierarchy),
            "total_unassigned_recruiters": len(unassigned_recruiters),
            "total_unassigned_companies": len(unassigned_companies)
        }
    }


# ============== COMMERCIAL INTELLIGENCE ENGINE ==============

@api_router.post("/commercials", response_model=CommercialResponse)
async def create_commercial(
    commercial_data: CommercialCreate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Create a commercial configuration for a company.
    - Admin: can create for any company
    - Employer: can only create for assigned companies
    """
    # Validate company exists
    company = await db.companies.find_one({"id": commercial_data.company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Employer can only manage assigned companies
    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You are not assigned to this company")
    
    # Validate commercial type fields
    if commercial_data.type == "percentage" and commercial_data.fee_percentage is None:
        raise HTTPException(status_code=400, detail="fee_percentage required for percentage type")
    if commercial_data.type == "fixed" and commercial_data.fixed_amount is None:
        raise HTTPException(status_code=400, detail="fixed_amount required for fixed type")
    if commercial_data.type == "level_based" and commercial_data.level_config is None:
        raise HTTPException(status_code=400, detail="level_config required for level_based type")
    
    commercial_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    commercial_doc = {
        "id": commercial_id,
        "company_id": commercial_data.company_id,
        "company_name": company.get("name"),
        "commercial_name": commercial_data.commercial_name,
        "type": commercial_data.type,
        "fee_percentage": commercial_data.fee_percentage,
        "fixed_amount": commercial_data.fixed_amount,
        "level_config": commercial_data.level_config,
        "salary_min": commercial_data.salary_min,
        "salary_max": commercial_data.salary_max,
        "job_level": commercial_data.job_level,
        "effective_from": commercial_data.effective_from,
        "effective_to": commercial_data.effective_to,
        "is_active": commercial_data.is_active,
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user["name"],
        "updated_at": now,
        "audit_log": [{
            "action": "created",
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        }]
    }
    
    await db.commercials.insert_one(commercial_doc)
    logging.info(f"Commercial '{commercial_data.commercial_name}' created for company {company.get('name')} by {current_user['name']}")
    
    return CommercialResponse(**commercial_doc)


@api_router.get("/commercials", response_model=List[CommercialResponse])
async def get_commercials(
    company_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get commercials.
    - Admin: sees all commercials
    - Employer: sees only commercials for assigned companies
    """
    query = {}
    
    if current_user["role"] == "employer":
        # Get companies assigned to this employer
        assigned_companies = await db.companies.find(
            {"assigned_employer_id": current_user["id"]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        company_ids = [c["id"] for c in assigned_companies]
        query["company_id"] = {"$in": company_ids}
    
    if company_id:
        query["company_id"] = company_id
    if is_active is not None:
        query["is_active"] = is_active
    
    commercials = await db.commercials.find(query, {"_id": 0}).to_list(1000)
    return [CommercialResponse(**c) for c in commercials]


@api_router.get("/commercials/{commercial_id}", response_model=CommercialResponse)
async def get_commercial(
    commercial_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Get a specific commercial by ID."""
    commercial = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    if not commercial:
        raise HTTPException(status_code=404, detail="Commercial not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        company = await db.companies.find_one({"id": commercial["company_id"]}, {"_id": 0})
        if not company or company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return CommercialResponse(**commercial)


@api_router.put("/commercials/{commercial_id}", response_model=CommercialResponse)
async def update_commercial(
    commercial_id: str,
    update_data: CommercialUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Update a commercial configuration."""
    commercial = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    if not commercial:
        raise HTTPException(status_code=404, detail="Commercial not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        company = await db.companies.find_one({"id": commercial["company_id"]}, {"_id": 0})
        if not company or company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_dict["updated_at"] = now
    
    # Create audit entry
    audit_entry = {
        "action": "updated",
        "changes": list(update_dict.keys()),
        "by_id": current_user["id"],
        "by_name": current_user["name"],
        "by_role": current_user["role"],
        "timestamp": now
    }
    
    await db.commercials.update_one(
        {"id": commercial_id},
        {
            "$set": update_dict,
            "$push": {"audit_log": audit_entry}
        }
    )
    
    updated = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    return CommercialResponse(**updated)


@api_router.delete("/commercials/{commercial_id}")
async def delete_commercial(
    commercial_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Soft delete (deactivate) a commercial. Admin only."""
    commercial = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    if not commercial:
        raise HTTPException(status_code=404, detail="Commercial not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.commercials.update_one(
        {"id": commercial_id},
        {
            "$set": {"is_active": False, "updated_at": now},
            "$push": {"audit_log": {
                "action": "deactivated",
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "by_role": current_user["role"],
                "timestamp": now
            }}
        }
    )
    
    return {"message": "Commercial deactivated successfully"}


# ============== REVENUE CALCULATION ENGINE ==============

def calculate_revenue(offered_salary: float, commercial: dict, job_level: Optional[str] = None) -> float:
    """Calculate revenue based on commercial type."""
    if commercial["type"] == "percentage":
        return offered_salary * (commercial["fee_percentage"] / 100)
    elif commercial["type"] == "fixed":
        return commercial["fixed_amount"]
    elif commercial["type"] == "level_based":
        level_config = commercial.get("level_config", {})
        level = job_level or "mid"  # Default to mid if not specified
        fee_pct = level_config.get(level, level_config.get("mid", 10.0))
        return offered_salary * (fee_pct / 100)
    return 0.0


async def get_applicable_commercial(company_id: str, salary: Optional[float] = None, job_level: Optional[str] = None) -> Optional[dict]:
    """Get the applicable commercial for a job/offer."""
    now = datetime.now(timezone.utc).isoformat()
    
    query = {
        "company_id": company_id,
        "is_active": True,
        "effective_from": {"$lte": now},
        "$or": [
            {"effective_to": None},
            {"effective_to": {"$gte": now}}
        ]
    }
    
    commercials = await db.commercials.find(query, {"_id": 0}).to_list(100)
    
    if not commercials:
        return None
    
    # If salary provided, try to find salary-range specific commercial
    if salary:
        for comm in commercials:
            if comm.get("salary_min") and comm.get("salary_max"):
                if comm["salary_min"] <= salary <= comm["salary_max"]:
                    return comm
    
    # If job level provided, try to find level-specific commercial
    if job_level:
        for comm in commercials:
            if comm.get("job_level") == job_level:
                return comm
            if comm["type"] == "level_based":
                return comm
    
    # Return first active commercial as default
    return commercials[0]


@api_router.post("/revenue/calculate")
async def calculate_application_revenue(
    application_id: str,
    offered_salary: float,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Calculate revenue for an application when offer is made.
    Creates/updates revenue entry in database.
    """
    application = await db.applications.find_one({"id": application_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Get job to find company
    job = await db.jobs.find_one({"id": application["job_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    company_id = job.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Job has no company assigned")
    
    # Employer access control
    if current_user["role"] == "employer":
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if not company or company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get applicable commercial
    commercial = await get_applicable_commercial(
        company_id,
        salary=offered_salary,
        job_level=job.get("job_level")
    )
    
    if not commercial:
        raise HTTPException(status_code=400, detail="No active commercial found for this company")
    
    # Calculate revenue
    calculated_revenue = calculate_revenue(
        offered_salary,
        commercial,
        job.get("job_level")
    )
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Check if revenue entry exists
    existing = await db.revenue.find_one({"application_id": application_id}, {"_id": 0})
    
    if existing:
        # Update existing
        await db.revenue.update_one(
            {"application_id": application_id},
            {
                "$set": {
                    "offered_salary": offered_salary,
                    "commercial_id": commercial["id"],
                    "commercial_type": commercial["type"],
                    "fee_percentage": commercial.get("fee_percentage"),
                    "fixed_amount": commercial.get("fixed_amount"),
                    "calculated_revenue": calculated_revenue,
                    "final_revenue": existing.get("manual_override") or calculated_revenue,
                    "stage": application.get("stage", "offered"),
                    "updated_at": now
                },
                "$push": {"audit_log": {
                    "action": "recalculated",
                    "offered_salary": offered_salary,
                    "calculated_revenue": calculated_revenue,
                    "by_id": current_user["id"],
                    "by_name": current_user["name"],
                    "timestamp": now
                }}
            }
        )
        revenue_id = existing["id"]
    else:
        # Create new
        revenue_id = str(uuid.uuid4())
        revenue_doc = {
            "id": revenue_id,
            "application_id": application_id,
            "job_id": application["job_id"],
            "job_title": job.get("title"),
            "candidate_id": application.get("candidate_id"),
            "candidate_name": application.get("candidate_name"),
            "company_id": company_id,
            "offered_salary": offered_salary,
            "commercial_id": commercial["id"],
            "commercial_name": commercial.get("commercial_name"),
            "commercial_type": commercial["type"],
            "fee_percentage": commercial.get("fee_percentage"),
            "fixed_amount": commercial.get("fixed_amount"),
            "calculated_revenue": calculated_revenue,
            "manual_override": None,
            "final_revenue": calculated_revenue,
            "stage": application.get("stage", "offered"),
            "is_closed": application.get("stage") == "hired",
            "created_at": now,
            "created_by": current_user["id"],
            "audit_log": [{
                "action": "created",
                "offered_salary": offered_salary,
                "calculated_revenue": calculated_revenue,
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "timestamp": now
            }]
        }
        await db.revenue.insert_one(revenue_doc)
    
    # Update application with offered salary
    await db.applications.update_one(
        {"id": application_id},
        {"$set": {"offered_salary": offered_salary, "updated_at": now}}
    )
    
    return {
        "revenue_id": revenue_id,
        "application_id": application_id,
        "offered_salary": offered_salary,
        "commercial_name": commercial.get("commercial_name"),
        "commercial_type": commercial["type"],
        "fee_percentage": commercial.get("fee_percentage"),
        "calculated_revenue": calculated_revenue,
        "final_revenue": calculated_revenue
    }


@api_router.put("/revenue/{revenue_id}/override")
async def override_revenue(
    revenue_id: str,
    manual_override: float,
    reason: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Admin-only: Manually override calculated revenue.
    """
    revenue = await db.revenue.find_one({"id": revenue_id}, {"_id": 0})
    if not revenue:
        raise HTTPException(status_code=404, detail="Revenue entry not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.revenue.update_one(
        {"id": revenue_id},
        {
            "$set": {
                "manual_override": manual_override,
                "final_revenue": manual_override,
                "updated_at": now
            },
            "$push": {"audit_log": {
                "action": "manual_override",
                "previous_revenue": revenue.get("final_revenue"),
                "new_revenue": manual_override,
                "reason": reason,
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "timestamp": now
            }}
        }
    )
    
    logging.info(f"Revenue {revenue_id} manually overridden to {manual_override} by {current_user['name']}: {reason}")
    
    return {"message": "Revenue overridden successfully", "final_revenue": manual_override}


@api_router.get("/revenue/pipeline")
async def get_revenue_pipeline(
    company_id: Optional[str] = None,
    employer_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get revenue pipeline data.
    - Admin: sees all
    - Employer: sees only assigned companies
    """
    query = {}
    
    if current_user["role"] == "employer":
        # Get companies assigned to this employer
        assigned_companies = await db.companies.find(
            {"assigned_employer_id": current_user["id"]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        company_ids = [c["id"] for c in assigned_companies]
        query["company_id"] = {"$in": company_ids}
    elif company_id:
        query["company_id"] = company_id
    
    if date_from:
        query["created_at"] = {"$gte": date_from}
    if date_to:
        if "created_at" in query:
            query["created_at"]["$lte"] = date_to
        else:
            query["created_at"] = {"$lte": date_to}
    
    revenues = await db.revenue.find(query, {"_id": 0}).to_list(10000)
    
    # Calculate pipeline stats
    pipeline_by_stage = {}
    closed_revenue = 0
    total_pipeline = 0
    
    for rev in revenues:
        stage = rev.get("stage", "offered")
        amount = rev.get("final_revenue", 0)
        
        if stage not in pipeline_by_stage:
            pipeline_by_stage[stage] = {"count": 0, "revenue": 0}
        
        pipeline_by_stage[stage]["count"] += 1
        pipeline_by_stage[stage]["revenue"] += amount
        
        if rev.get("is_closed"):
            closed_revenue += amount
        else:
            total_pipeline += amount
    
    return {
        "pipeline_by_stage": pipeline_by_stage,
        "total_pipeline_revenue": total_pipeline,
        "closed_revenue": closed_revenue,
        "total_entries": len(revenues),
        "entries": revenues[:100]  # Limit detail response
    }


# ============== ADMIN ANALYTICS DASHBOARD ==============

@api_router.get("/analytics/admin")
async def get_admin_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    employer_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    company_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Admin analytics dashboard - Power BI style.
    Full visibility into all business metrics.
    """
    # Build date query
    date_query = {}
    if date_from:
        date_query["$gte"] = date_from
    if date_to:
        date_query["$lte"] = date_to
    
    # Get all jobs with filters
    jobs_query = {"status": {"$in": ["active", "on_hold", "closed"]}}
    if company_id:
        jobs_query["company_id"] = company_id
    
    jobs = await db.jobs.find(jobs_query, {"_id": 0}).to_list(10000)
    active_jobs = [j for j in jobs if j.get("status") == "active"]
    
    # Get all applications
    apps_query = {}
    if date_query:
        apps_query["created_at"] = date_query
    
    applications = await db.applications.find(apps_query, {"_id": 0}).to_list(100000)
    
    # Get revenue data
    revenue_query = {}
    if date_query:
        revenue_query["created_at"] = date_query
    if company_id:
        revenue_query["company_id"] = company_id
    
    revenues = await db.revenue.find(revenue_query, {"_id": 0}).to_list(10000)
    
    # Calculate KPIs
    total_pipeline_revenue = sum(r.get("final_revenue", 0) for r in revenues if not r.get("is_closed"))
    closed_revenue = sum(r.get("final_revenue", 0) for r in revenues if r.get("is_closed"))
    
    # Stage distribution
    stage_counts = {}
    for app in applications:
        stage = app.get("stage", "applied")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    
    offered_count = stage_counts.get("offered", 0)
    hired_count = stage_counts.get("hired", 0)
    offer_to_join_ratio = (hired_count / offered_count * 100) if offered_count > 0 else 0
    
    # Calculate avg time to close
    hired_apps = [a for a in applications if a.get("stage") == "hired" and a.get("created_at")]
    if hired_apps:
        total_days = 0
        for app in hired_apps:
            try:
                created = datetime.fromisoformat(app["created_at"].replace("Z", "+00:00"))
                updated = datetime.fromisoformat(app.get("updated_at", app["created_at"]).replace("Z", "+00:00"))
                total_days += (updated - created).days
            except:
                pass
        avg_time_to_close = total_days / len(hired_apps) if hired_apps else 0
    else:
        avg_time_to_close = 0
    
    # Get counts
    active_employers = await db.users.count_documents({"role": "employer", "is_active": True})
    active_recruiters = await db.users.count_documents({"role": "recruiter", "is_active": True})
    
    # Revenue by company
    company_revenue = {}
    for rev in revenues:
        cid = rev.get("company_id")
        if cid:
            if cid not in company_revenue:
                company_revenue[cid] = {"name": "", "pipeline": 0, "closed": 0}
            company_revenue[cid]["pipeline"] += rev.get("final_revenue", 0) if not rev.get("is_closed") else 0
            company_revenue[cid]["closed"] += rev.get("final_revenue", 0) if rev.get("is_closed") else 0
    
    # Get company names
    for cid in company_revenue:
        company = await db.companies.find_one({"id": cid}, {"name": 1, "_id": 0})
        if company:
            company_revenue[cid]["name"] = company.get("name", "Unknown")
    
    # Recruiter performance
    recruiter_stats = {}
    for app in applications:
        # Get the recruiter who processed this application
        job = next((j for j in jobs if j["id"] == app.get("job_id")), None)
        if job:
            for rec_id in job.get("assigned_recruiter_ids", []):
                if rec_id not in recruiter_stats:
                    recruiter_stats[rec_id] = {"name": "", "applications": 0, "shortlisted": 0, "hired": 0, "revenue": 0}
                recruiter_stats[rec_id]["applications"] += 1
                if app.get("stage") in ["shortlisted", "interview", "offered", "hired"]:
                    recruiter_stats[rec_id]["shortlisted"] += 1
                if app.get("stage") == "hired":
                    recruiter_stats[rec_id]["hired"] += 1
    
    # Get recruiter names and add revenue
    for rec_id in recruiter_stats:
        user = await db.users.find_one({"id": rec_id}, {"name": 1, "_id": 0})
        if user:
            recruiter_stats[rec_id]["name"] = user.get("name", "Unknown")
        # Sum revenue for this recruiter's applications
        for rev in revenues:
            app = next((a for a in applications if a["id"] == rev.get("application_id")), None)
            if app:
                job = next((j for j in jobs if j["id"] == app.get("job_id")), None)
                if job and rec_id in job.get("assigned_recruiter_ids", []):
                    recruiter_stats[rec_id]["revenue"] += rev.get("final_revenue", 0)
    
    # Revenue funnel by stage
    revenue_funnel = {
        "offered": sum(r.get("final_revenue", 0) for r in revenues if r.get("stage") == "offered"),
        "hired": sum(r.get("final_revenue", 0) for r in revenues if r.get("stage") == "hired"),
    }
    
    return {
        "kpis": {
            "total_active_mandates": len(active_jobs),
            "total_pipeline_revenue": round(total_pipeline_revenue, 2),
            "closed_revenue": round(closed_revenue, 2),
            "avg_time_to_close_days": round(avg_time_to_close, 1),
            "offer_to_join_ratio": round(offer_to_join_ratio, 1),
            "active_employers": active_employers,
            "active_recruiters": active_recruiters,
        },
        "stage_distribution": stage_counts,
        "revenue_funnel": revenue_funnel,
        "company_revenue": list(company_revenue.values()),
        "recruiter_performance": list(recruiter_stats.values()),
    }


# ============== EMPLOYER ANALYTICS DASHBOARD ==============

@api_router.get("/analytics/employer")
async def get_employer_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Employer analytics dashboard.
    Scoped to assigned companies and teams only.
    """
    # Get companies assigned to this employer (or all for admin)
    if current_user["role"] == "employer":
        assigned_companies = await db.companies.find(
            {"assigned_employer_id": current_user["id"]},
            {"_id": 0}
        ).to_list(1000)
        company_ids = [c["id"] for c in assigned_companies]
    else:
        assigned_companies = await db.companies.find({}, {"_id": 0}).to_list(1000)
        company_ids = [c["id"] for c in assigned_companies]
    
    if not company_ids:
        return {
            "kpis": {
                "active_mandates": 0,
                "pipeline_revenue": 0,
                "closed_revenue": 0,
                "offers_pending": 0,
                "avg_fee_percentage": 0,
            },
            "team_performance": [],
            "company_revenue": [],
            "recruiter_contribution": [],
        }
    
    # Get jobs for these companies
    jobs = await db.jobs.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(10000)
    
    active_jobs = [j for j in jobs if j.get("status") == "active"]
    job_ids = [j["id"] for j in jobs]
    
    # Get applications for these jobs
    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0}
    ).to_list(100000)
    
    # Get revenue
    revenues = await db.revenue.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(10000)
    
    pipeline_revenue = sum(r.get("final_revenue", 0) for r in revenues if not r.get("is_closed"))
    closed_revenue = sum(r.get("final_revenue", 0) for r in revenues if r.get("is_closed"))
    
    # Offers pending
    offers_pending = len([a for a in applications if a.get("stage") == "offered"])
    
    # Average fee percentage
    commercials = await db.commercials.find(
        {"company_id": {"$in": company_ids}, "is_active": True},
        {"_id": 0}
    ).to_list(1000)
    
    pct_fees = [c.get("fee_percentage", 0) for c in commercials if c.get("fee_percentage")]
    avg_fee = sum(pct_fees) / len(pct_fees) if pct_fees else 0
    
    # Company-wise revenue
    company_revenue = []
    for company in assigned_companies:
        comp_revs = [r for r in revenues if r.get("company_id") == company["id"]]
        company_revenue.append({
            "company_id": company["id"],
            "company_name": company.get("name"),
            "pipeline": sum(r.get("final_revenue", 0) for r in comp_revs if not r.get("is_closed")),
            "closed": sum(r.get("final_revenue", 0) for r in comp_revs if r.get("is_closed")),
            "mandates": len([j for j in jobs if j.get("company_id") == company["id"]]),
        })
    
    # Get teams for this employer
    teams = await db.teams.find(
        {"employer_id": current_user["id"]} if current_user["role"] == "employer" else {},
        {"_id": 0}
    ).to_list(100)
    
    team_performance = []
    for team in teams:
        team_jobs = [j for j in jobs if j.get("team_id") == team["id"]]
        team_job_ids = [j["id"] for j in team_jobs]
        team_apps = [a for a in applications if a.get("job_id") in team_job_ids]
        team_revs = [r for r in revenues if r.get("job_id") in team_job_ids]
        
        team_performance.append({
            "team_id": team["id"],
            "team_name": team.get("name"),
            "mandates": len(team_jobs),
            "applications": len(team_apps),
            "hired": len([a for a in team_apps if a.get("stage") == "hired"]),
            "pipeline_revenue": sum(r.get("final_revenue", 0) for r in team_revs if not r.get("is_closed")),
            "closed_revenue": sum(r.get("final_revenue", 0) for r in team_revs if r.get("is_closed")),
        })
    
    # Recruiter contribution
    recruiter_contribution = []
    recruiter_ids = set()
    for job in jobs:
        for rec_id in job.get("assigned_recruiter_ids", []):
            recruiter_ids.add(rec_id)
    
    for rec_id in recruiter_ids:
        rec_jobs = [j for j in jobs if rec_id in j.get("assigned_recruiter_ids", [])]
        rec_job_ids = [j["id"] for j in rec_jobs]
        rec_apps = [a for a in applications if a.get("job_id") in rec_job_ids]
        rec_revs = [r for r in revenues if r.get("job_id") in rec_job_ids]
        
        recruiter = await db.users.find_one({"id": rec_id}, {"name": 1, "_id": 0})
        
        recruiter_contribution.append({
            "recruiter_id": rec_id,
            "recruiter_name": recruiter.get("name", "Unknown") if recruiter else "Unknown",
            "mandates": len(rec_jobs),
            "applications": len(rec_apps),
            "hired": len([a for a in rec_apps if a.get("stage") == "hired"]),
            "revenue": sum(r.get("final_revenue", 0) for r in rec_revs),
        })
    
    return {
        "kpis": {
            "active_mandates": len(active_jobs),
            "pipeline_revenue": round(pipeline_revenue, 2),
            "closed_revenue": round(closed_revenue, 2),
            "offers_pending": offers_pending,
            "avg_fee_percentage": round(avg_fee, 2),
        },
        "team_performance": team_performance,
        "company_revenue": company_revenue,
        "recruiter_contribution": recruiter_contribution,
    }


# ============== COMPANY PIPELINE VIEW ==============

@api_router.get("/companies/{company_id}/pipeline")
async def get_company_pipeline(
    company_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get company profile with pipeline view.
    Shows mandates, revenue breakdown, and detailed pipeline.
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all jobs for this company
    jobs = await db.jobs.find({"company_id": company_id}, {"_id": 0}).to_list(10000)
    
    total_mandates = len(jobs)
    active_mandates = len([j for j in jobs if j.get("status") == "active"])
    closed_mandates = len([j for j in jobs if j.get("status") == "closed"])
    
    # Get revenue
    revenues = await db.revenue.find({"company_id": company_id}, {"_id": 0}).to_list(10000)
    total_revenue = sum(r.get("final_revenue", 0) for r in revenues)
    
    # Get commercials
    commercials = await db.commercials.find(
        {"company_id": company_id, "is_active": True},
        {"_id": 0}
    ).to_list(100)
    
    pct_fees = [c.get("fee_percentage", 0) for c in commercials if c.get("fee_percentage")]
    avg_commercial_pct = sum(pct_fees) / len(pct_fees) if pct_fees else 0
    
    # Build pipeline table
    pipeline = []
    for job in jobs:
        job_revenues = [r for r in revenues if r.get("job_id") == job["id"]]
        expected_revenue = sum(r.get("final_revenue", 0) for r in job_revenues if not r.get("is_closed"))
        closed_revenue = sum(r.get("final_revenue", 0) for r in job_revenues if r.get("is_closed"))
        
        # Get recruiters for this job
        recruiters = []
        for rec_id in job.get("assigned_recruiter_ids", []):
            rec = await db.users.find_one({"id": rec_id}, {"name": 1, "_id": 0})
            if rec:
                recruiters.append(rec.get("name", "Unknown"))
        
        # Get application count by stage
        apps = await db.applications.find({"job_id": job["id"]}, {"stage": 1, "_id": 0}).to_list(10000)
        stage_counts = {}
        for app in apps:
            stage = app.get("stage", "applied")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        
        pipeline.append({
            "job_id": job["id"],
            "job_title": job.get("title"),
            "job_level": job.get("job_level"),
            "status": job.get("status"),
            "recruiters": recruiters,
            "stage_counts": stage_counts,
            "expected_revenue": round(expected_revenue, 2),
            "closed_revenue": round(closed_revenue, 2),
        })
    
    return {
        "company": {
            "id": company["id"],
            "name": company.get("name"),
            "industry": company.get("industry"),
        },
        "summary": {
            "total_mandates": total_mandates,
            "active_mandates": active_mandates,
            "closed_mandates": closed_mandates,
            "total_revenue": round(total_revenue, 2),
            "avg_commercial_percentage": round(avg_commercial_pct, 2),
        },
        "commercials": [CommercialResponse(**c).model_dump() for c in commercials],
        "pipeline": pipeline,
    }


# ============== JD PARSING ==============

@api_router.post("/jobs/parse-jd")
async def parse_job_description(
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Parse a job description (text or file) using AI.
    Returns structured job fields for form pre-fill.
    """
    raw_text = ""
    
    if jd_file:
        # Save and extract text from file
        file_ext = jd_file.filename.split(".")[-1].lower()
        if file_ext not in ["pdf", "doc", "docx", "txt"]:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use PDF, DOC, DOCX, or TXT")
        
        # Save file temporarily
        file_path = UPLOAD_DIR / f"jd_{uuid.uuid4()}.{file_ext}"
        async with aiofiles.open(file_path, "wb") as f:
            content = await jd_file.read()
            await f.write(content)
        
        # Extract text
        if file_ext == "pdf":
            doc = fitz.open(str(file_path))
            for page in doc:
                raw_text += page.get_text()
            doc.close()
        elif file_ext == "txt":
            async with aiofiles.open(file_path, "r") as f:
                raw_text = await f.read()
        else:
            # For DOC/DOCX, try to extract using python-docx
            try:
                from docx import Document
                doc = Document(str(file_path))
                raw_text = "\n".join([para.text for para in doc.paragraphs])
            except:
                raw_text = "Unable to parse DOC/DOCX file"
        
        # Clean up temp file
        file_path.unlink(missing_ok=True)
    
    elif jd_text:
        raw_text = jd_text
    else:
        raise HTTPException(status_code=400, detail="Provide either jd_text or jd_file")
    
    # Parse using AI (using GPT-5.2 via Emergent)
    try:
        from emergentintegrations.llm.chat import chat, UserMessage
        
        parse_prompt = f"""Parse the following job description and extract structured information.
Return a JSON object with these fields:
- title: Job title
- skills: Array of required skills
- experience_years: Estimated years of experience required (number)
- location: Job location
- job_level: One of "junior", "mid", "senior", "leadership" based on requirements
- salary_min: Minimum salary if mentioned (number, in INR)
- salary_max: Maximum salary if mentioned (number, in INR)
- summary: 2-3 sentence summary of the role
- responsibilities: Array of key responsibilities
- requirements: Array of key requirements

Job Description:
{raw_text[:4000]}

Return ONLY valid JSON, no markdown or explanation."""

        response = await chat(
            api_key=os.environ.get("EMERGENT_API_KEY"),
            model="gpt-5.2",
            messages=[UserMessage(content=parse_prompt)]
        )
        
        # Parse JSON response
        import json
        try:
            # Clean response (remove markdown if present)
            response_text = response.content.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            parsed = {}
        
        return {
            "title": parsed.get("title"),
            "skills": parsed.get("skills", []),
            "experience_years": parsed.get("experience_years"),
            "location": parsed.get("location"),
            "job_level": parsed.get("job_level"),
            "salary_min": parsed.get("salary_min"),
            "salary_max": parsed.get("salary_max"),
            "summary": parsed.get("summary"),
            "responsibilities": parsed.get("responsibilities", []),
            "requirements": parsed.get("requirements", []),
            "raw_text": raw_text[:2000],
        }
        
    except Exception as e:
        logging.error(f"JD parsing error: {e}")
        # Return basic extraction if AI fails
        return {
            "title": None,
            "skills": [],
            "experience_years": None,
            "location": None,
            "job_level": None,
            "salary_min": None,
            "salary_max": None,
            "summary": None,
            "responsibilities": [],
            "requirements": [],
            "raw_text": raw_text[:2000],
            "parse_error": str(e)
        }


# ============== MANDATE ASSIGNMENT ==============

@api_router.post("/jobs/{job_id}/assign-recruiters")
async def assign_recruiters_to_mandate(
    job_id: str,
    recruiter_ids: List[str],
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Assign recruiters to a job mandate.
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        if job.get("company_id"):
            company = await db.companies.find_one({"id": job["company_id"]}, {"_id": 0})
            if not company or company.get("assigned_employer_id") != current_user["id"]:
                raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate all recruiter IDs
    for rec_id in recruiter_ids:
        recruiter = await db.users.find_one({"id": rec_id, "role": "recruiter"}, {"_id": 0})
        if not recruiter:
            raise HTTPException(status_code=400, detail=f"Recruiter {rec_id} not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Get recruiter names
    recruiter_names = []
    for rec_id in recruiter_ids:
        rec = await db.users.find_one({"id": rec_id}, {"name": 1, "_id": 0})
        if rec:
            recruiter_names.append(rec.get("name", "Unknown"))
    
    await db.jobs.update_one(
        {"id": job_id},
        {
            "$set": {
                "assigned_recruiter_ids": recruiter_ids,
                "assigned_recruiter_names": recruiter_names,
                "updated_at": now
            },
            "$push": {"approval_history": {
                "action": "recruiters_assigned",
                "recruiter_ids": recruiter_ids,
                "recruiter_names": recruiter_names,
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "timestamp": now
            }}
        }
    )
    
    logging.info(f"Recruiters {recruiter_names} assigned to job {job_id} by {current_user['name']}")
    
    return {
        "message": "Recruiters assigned successfully",
        "job_id": job_id,
        "assigned_recruiter_ids": recruiter_ids,
        "assigned_recruiter_names": recruiter_names
    }


@api_router.get("/jobs/{job_id}/assignments")
async def get_job_assignments(
    job_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Get recruiter assignments for a job."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # For recruiter, check if they are assigned
    if current_user["role"] == "recruiter":
        if current_user["id"] not in job.get("assigned_recruiter_ids", []):
            raise HTTPException(status_code=403, detail="Not assigned to this job")
    
    return {
        "job_id": job_id,
        "job_title": job.get("title"),
        "team_id": job.get("team_id"),
        "assigned_recruiter_ids": job.get("assigned_recruiter_ids", []),
        "assigned_recruiter_names": job.get("assigned_recruiter_names", []),
    }


# ============== FILE SERVING ==============

from fastapi.responses import FileResponse

@api_router.get("/uploads/{filename}")
async def get_upload(filename: str):
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

# ============== SEED ADMIN ==============

@app.on_event("startup")
async def seed_admin():
    """
    Seeds admin user from environment variables on first run.
    Admin requires password reset on first login for security.
    Set ADMIN_EMAIL and ADMIN_PASSWORD in .env file.
    """
    admin_email = os.environ.get('ADMIN_EMAIL')
    admin_password = os.environ.get('ADMIN_PASSWORD')
    
    # Only seed if both credentials are provided in environment
    if not admin_email or not admin_password:
        logging.warning("ADMIN_EMAIL or ADMIN_PASSWORD not set - skipping admin seeding")
        return
    
    existing_admin = await db.users.find_one({"email": admin_email})
    if not existing_admin:
        admin_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        admin_doc = {
            "id": admin_id,
            "email": admin_email,
            "name": "System Admin",
            "role": "admin",
            "password": hash_password(admin_password),
            "phone": None,
            "company_id": None,
            "is_active": True,
            "requires_password_reset": True,  # Force password change on first login
            "created_at": now
        }
        
        await db.users.insert_one(admin_doc)
        logging.info(f"Admin user seeded (requires password reset): {admin_email}")
    
    # Cleanup: Remove any test users on startup
    test_result = await db.users.delete_many({"email": {"$regex": "@test\\.com$"}})
    if test_result.deleted_count > 0:
        logging.info(f"Cleaned up {test_result.deleted_count} test users")

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
