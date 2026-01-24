"""
Candidate profile Pydantic models.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional


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
