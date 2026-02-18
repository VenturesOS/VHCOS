"""
Company-related Pydantic models.
Includes embedded commercial model (merged from standalone commercials).
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict


class HRContact(BaseModel):
    """HR / Point of Contact details for a company."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None


class LevelRange(BaseModel):
    """Salary range with percentage for level-based commercials."""
    min_salary: float
    max_salary: float
    percentage: float


class CommercialModel(BaseModel):
    """Embedded commercial structure within a company."""
    type: str  # "percentage", "fixed", "level_based"
    percentage_value: Optional[float] = None      # for percentage type
    fixed_fee_amount: Optional[float] = None       # for fixed type
    level_config: Optional[List[LevelRange]] = None  # for level_based type
    legacy_level_mapping: Optional[Dict[str, float]] = None  # migrated named-key data


class CompanyBase(BaseModel):
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    hr_contacts: Optional[List[HRContact]] = None
    commercial: Optional[CommercialModel] = None


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
    assigned_employer_id: Optional[str] = None
    assigned_employer_name: Optional[str] = None
    hr_contacts: Optional[List[HRContact]] = None
    commercial: Optional[CommercialModel] = None
    status: str = "active"
    created_at: str


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    assigned_employer_id: Optional[str] = None
    hr_contacts: Optional[List[HRContact]] = None
    commercial: Optional[CommercialModel] = None
    status: Optional[str] = None
