"""
Application-related Pydantic models.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any, Dict


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
    current_salary: Optional[float] = None  # INR
    expected_salary: Optional[int] = None  # INR - Expected CTC
    expected_ctc: Optional[float] = None
    offered_ctc: Optional[float] = None
    offer_date: Optional[str] = None
    join_date: Optional[str] = None
    forecast_revenue: Optional[float] = None
    forecast_slab: Optional[dict] = None
    forecast_percentage: Optional[float] = None
    notice_period: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[float] = None
    experience_summary: Optional[str] = None  # Brief summary text
    location: Optional[str] = None
    headline: Optional[str] = None
    current_employer: Optional[str] = None
    designation: Optional[str] = None
    industry: Optional[str] = None
    # FIX (Phase 52, 2026-05-07): the `education` field is populated from the
    # candidate_bank.education_details array (e.g. [{"degree":"BTech",...}]).
    # The previous `Optional[str]` declaration caused Pydantic
    # ValidationError 500s on /applications when the upstream value was the
    # native list. Accept either shape — the frontend already handles both.
    education: Optional[Any] = None
    resume_url: Optional[str] = None
    status: str = "applied"
    stage: str = "applied"
    source: Optional[str] = None
    notes: List[dict] = []
    edit_history: List[dict] = []  # Audit trail
    last_edited_by: Optional[dict] = None
    manually_edited: bool = False
    applied_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    stage: Optional[str] = None
    rejection_reason: Optional[str] = None  # For tracking why rejected/not qualified
    offered_ctc: Optional[float] = None
    offer_date: Optional[str] = None
    join_date: Optional[str] = None
    expected_ctc: Optional[float] = None


class ApplicationDetailUpdate(BaseModel):
    """Model for controlled editing of applicant details by Admin/Employer/Recruiter"""
    current_salary: Optional[float] = None  # INR
    expected_salary: Optional[int] = None  # INR - Expected CTC
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
    experience_summary: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[int] = None
    location: Optional[str] = None
    current_salary: Optional[float] = None
    notice_period: Optional[str] = None
    resume_url: Optional[str] = None
    cover_letter: Optional[str] = None
    stage: str = "applied"
    match_score: Optional[int] = None
    must_haves_met: Optional[List[Dict]] = None
    career_stability: Optional[Dict] = None
    applied_at: Optional[str] = None
    updated_at: Optional[str] = None
    notes: List[Dict] = []
    edit_history: List[Dict] = []
    last_edited_by: Optional[Dict] = None
    manually_edited: bool = False


class CandidateApprovalRequest(BaseModel):
    """Model for employer approving/rejecting shortlisted candidates."""
    action: str  # "approve" or "reject"
    reason: Optional[str] = None


class ShortlistRequest(BaseModel):
    candidate_id: str
    job_id: str
    notes: Optional[str] = None


class LinkCandidateRequest(BaseModel):
    candidate_id: str
    job_id: str
    expected_salary: Optional[float] = None
