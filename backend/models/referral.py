"""
Referral Pydantic models.
"""
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional


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
