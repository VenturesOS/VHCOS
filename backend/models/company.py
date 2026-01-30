"""
Company-related Pydantic models.
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List


class HRContact(BaseModel):
    """HR / Point of Contact details for a company."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None


class CompanyBase(BaseModel):
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    hr_contacts: Optional[List[HRContact]] = None  # HR / POC details


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
    hr_contacts: Optional[List[HRContact]] = None  # HR / POC details
    status: str = "active"  # active, disabled
    created_at: str


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    assigned_employer_id: Optional[str] = None
    hr_contacts: Optional[List[HRContact]] = None  # HR / POC details
    status: Optional[str] = None
