"""
Commercial Intelligence Pydantic models.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict


class CommercialCreate(BaseModel):
    """Commercial configuration for a company"""
    company_id: str
    commercial_name: str
    type: str = Field(..., pattern="^(percentage|fixed|level_based)$")
    # For percentage type
    fee_percentage: Optional[float] = None  # e.g., 8.33 for 8.33%
    # For fixed type
    fixed_amount: Optional[float] = None
    # For level_based type
    level_config: Optional[Dict[str, float]] = None  # {"junior": 8.0, "mid": 10.0, "senior": 12.0, "leadership": 15.0}
    # Salary range (optional, for scoped commercials)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    # Job level (optional, for level_based)
    job_level: Optional[str] = None
    # Validity
    effective_from: str
    effective_to: Optional[str] = None
    is_active: bool = True


class CommercialUpdate(BaseModel):
    commercial_name: Optional[str] = None
    type: Optional[str] = None
    fee_percentage: Optional[float] = None
    fixed_amount: Optional[float] = None
    level_config: Optional[Dict[str, float]] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_level: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    is_active: Optional[bool] = None


class CommercialResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    company_id: str
    company_name: Optional[str] = None
    commercial_name: str
    type: str
    fee_percentage: Optional[float] = None
    fixed_amount: Optional[float] = None
    level_config: Optional[Dict[str, float]] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_level: Optional[str] = None
    effective_from: str
    effective_to: Optional[str] = None
    is_active: bool = True
    created_at: str
    created_by: str
    updated_at: Optional[str] = None
    audit_log: List[dict] = []


class RevenueEntry(BaseModel):
    """Revenue calculation for an application"""
    application_id: str
    job_id: str
    candidate_id: str
    offered_salary: float
    commercial_id: str
    commercial_type: str
    fee_percentage: Optional[float] = None
    fixed_amount: Optional[float] = None
    calculated_revenue: float
    manual_override: Optional[float] = None
    final_revenue: float
    stage: str  # offered, joined
    is_closed: bool = False


class RevenueUpdate(BaseModel):
    offered_salary: Optional[float] = None
    manual_override: Optional[float] = None  # Admin only
