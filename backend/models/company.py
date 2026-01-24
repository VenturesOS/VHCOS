"""
Company-related Pydantic models.
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional


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
    assigned_employer_id: Optional[str] = None  # Employer assigned to this company
    assigned_employer_name: Optional[str] = None
    status: str = "active"  # active, disabled
    created_at: str


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    assigned_employer_id: Optional[str] = None
    status: Optional[str] = None
