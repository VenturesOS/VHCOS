"""
Team & hierarchy Pydantic models.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional


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
