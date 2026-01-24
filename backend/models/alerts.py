"""
Job Alerts & Notifications Pydantic models.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict


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
