"""
Public-facing Pydantic models.
Models for public job applications and resume submissions.
"""
from pydantic import BaseModel, EmailStr
from typing import Optional


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
