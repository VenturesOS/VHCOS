"""
Job-related Pydantic models.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


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
    skills: Optional[List[str]] = []  # Required skills for the job
    experience_min: Optional[int] = None  # Minimum years of experience
    experience_max: Optional[int] = None  # Maximum years of experience


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
    # Career Page Publishing Control (Internal OS Enhancement)
    career_page_status: str = "not_posted"  # not_posted, live, removed
    career_page_history: List[dict] = []  # Audit trail for career page status changes
    team_id: Optional[str] = None
    approval_history: List[dict] = []  # Audit trail for state transitions
    created_at: str
    updated_at: Optional[str] = None
    applicant_count: int = 0
    # Shareable Job Link Feature
    job_public_id: Optional[str] = None  # Format: VHC/YYYY/NNNN
    shareable_link_enabled: bool = False  # Enable/disable public shareable link
    # Skills for job matching
    skills: List[str] = []
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    # Recruiter Assignment (Employer-led mandate allocation)
    assigned_recruiters: List[str] = []  # List of recruiter user IDs
    assignment_history: List[dict] = []  # Audit trail for recruiter assignments


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


class JobStateTransition(BaseModel):
    new_status: str = Field(..., pattern="^(draft|pending_approval|active|on_hold|closed|archived)$")
    reason: Optional[str] = None


class CareerPageStatusUpdate(BaseModel):
    """Model for updating career page visibility status"""
    new_status: str = Field(..., pattern="^(not_posted|live|removed)$")
    reason: Optional[str] = None


class JDParseRequest(BaseModel):
    """Request to parse a job description"""
    jd_text: Optional[str] = None


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
