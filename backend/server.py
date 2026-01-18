from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import aiofiles

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
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    cover_letter: Optional[str] = None
    status: str = "applied"
    stage: str = "applied"
    notes: List[dict] = []
    created_at: str
    updated_at: str

class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    stage: Optional[str] = None

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
        created_at=now
    )
    
    return TokenResponse(access_token=access_token, user=user_response)

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled")
    
    access_token = create_access_token({"sub": user["id"], "role": user["role"]})
    
    user_response = UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        role=user["role"],
        company_id=user.get("company_id"),
        phone=user.get("phone"),
        created_at=user["created_at"]
    )
    
    return TokenResponse(access_token=access_token, user=user_response)

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)

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
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@vhc.in')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'vhc@123')
    
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
            "created_at": now
        }
        
        await db.users.insert_one(admin_doc)
        logging.info(f"Admin user seeded: {admin_email}")

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
