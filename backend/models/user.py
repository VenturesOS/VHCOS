"""
User-related Pydantic models.
"""
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional


class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: str = Field(..., pattern="^(admin|recruiter|employer|candidate)$")


class UserCreate(UserBase):
    password: str
    turnstile_token: Optional[str] = None
    notice_period: Optional[str] = None
    current_ctc: Optional[float] = None
    expected_ctc: Optional[float] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    name: str
    role: str
    company_id: Optional[str] = None
    phone: Optional[str] = None
    created_at: str
    is_active: bool = True
    requires_password_reset: bool = False
    is_account_manager: bool = False
    assigned_companies: Optional[list] = None
    # Team Lead — recruiter granted acting-employer access by their employer/admin
    is_team_lead: bool = False
    team_lead_employer_id: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None  # admin, employer, recruiter, candidate
    company_id: Optional[str] = None  # For assigning employer to recruiter
    is_account_manager: Optional[bool] = None
    assigned_companies: Optional[list] = None
    is_team_lead: Optional[bool] = None
    team_lead_employer_id: Optional[str] = None


class AdminUserCreate(BaseModel):
    """Admin-only user creation with role specification"""
    email: EmailStr
    password: str
    name: str
    role: str  # employer, recruiter, candidate
    phone: Optional[str] = None
    company_id: Optional[str] = None


class AdminPasswordReset(BaseModel):
    """Admin-initiated password reset for any user"""
    new_password: str


class PasswordReset(BaseModel):
    current_password: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: UserResponse
    requires_password_reset: bool = False
