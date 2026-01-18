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

class JobCreate(JobBase):
    pass

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
    posted_by: str
    status: str = "active"
    created_at: str
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
    status: Optional[str] = None

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
    location: Optional[str] = None
    headline: Optional[str] = None
    resume_url: Optional[str] = None
    status: str = "applied"
    stage: str = "applied"
    notes: List[dict] = []
    applied_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: str

class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    stage: Optional[str] = None
    rejection_reason: Optional[str] = None  # For tracking why rejected/not qualified

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
    created_at: str

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
    location: Optional[str] = None
    certifications: List[str] = []
    active_resume_id: Optional[str] = None
    resume_versions: List[dict] = []
    resume_fingerprints: List[str] = []
    source: str = "self"  # self, employer, recruiter, parsing
    linked_user_id: Optional[str] = None
    visibility: dict = {}  # employer_ids, recruiter_ids with access
    match_cache: List[dict] = []  # cached match results
    created_at: str
    updated_at: str
    created_by: Optional[str] = None
    last_updated_by: Optional[str] = None

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
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}

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
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    company_id = current_user.get("company_id", "default")
    company_name = None
    if company_id and company_id != "default":
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if company:
            company_name = company.get("name")
    
    job_doc = {
        "id": job_id,
        **job_data.model_dump(),
        "company_id": company_id,
        "company_name": company_name,
        "posted_by": current_user["id"],
        "status": "active",
        "applicant_count": 0,
        "created_at": now
    }
    
    await db.jobs.insert_one(job_doc)
    return JobResponse(**job_doc)

@api_router.get("/jobs", response_model=List[JobResponse])
async def get_jobs(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    
    if current_user["role"] == "employer":
        query["posted_by"] = current_user["id"]
    elif current_user["role"] == "candidate":
        query["status"] = "active"
    
    if status:
        query["status"] = status
    
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(1000)
    return [JobResponse(**j) for j in jobs]

@api_router.get("/jobs/browse", response_model=List[JobResponse])
async def browse_jobs(search: Optional[str] = None, location: Optional[str] = None, job_type: Optional[str] = None):
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
    
    app_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    app_doc = {
        "id": app_id,
        "job_id": app_data.job_id,
        "candidate_id": current_user["id"],
        "candidate_name": current_user["name"],
        "candidate_email": current_user["email"],
        "job_title": job.get("title"),
        "company_name": job.get("company_name"),
        "cover_letter": app_data.cover_letter,
        "status": "active",
        "stage": "applied",
        "notes": [],
        "created_at": now,
        "updated_at": now
    }
    
    await db.applications.insert_one(app_doc)
    
    # Increment applicant count
    await db.jobs.update_one({"id": app_data.job_id}, {"$inc": {"applicant_count": 1}})
    
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
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.applications.update_one({"id": app_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    return ApplicationResponse(**application)

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
            "notes": app.get("notes", [])
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
    
    # Enrich with company names
    for job in jobs:
        if job.get("company_id"):
            company = await db.companies.find_one({"id": job["company_id"]}, {"_id": 0, "name": 1})
            job["company_name"] = company.get("name", "VHC Client") if company else "VHC Client"
        else:
            job["company_name"] = "VHC Client"
    
    return jobs


@api_router.get("/public/jobs/{job_id}")
async def get_public_job_detail(job_id: str):
    """
    Get single job detail (PUBLIC - NO AUTH REQUIRED).
    """
    job = await db.jobs.find_one({"id": job_id, "status": "active"}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Add company name
    if job.get("company_id"):
        company = await db.companies.find_one({"id": job["company_id"]}, {"_id": 0, "name": 1})
        job["company_name"] = company.get("name", "VHC Client") if company else "VHC Client"
    else:
        job["company_name"] = "VHC Client"
    
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
