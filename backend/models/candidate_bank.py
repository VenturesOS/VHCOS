"""
Candidate Data Bank Pydantic models.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any


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


class CandidateBankAuditLogEntry(BaseModel):
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
    r2_metadata: Optional[dict] = None  # R2 storage info from parse response


class BatchSaveRequest(BaseModel):
    """Request body for batch save"""
    candidates: List[BatchUploadCandidate]

