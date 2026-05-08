"""
Extension-related Pydantic models.
Models for browser extension capture, CV upload, AI extraction, and mandate evaluation.
"""
from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict, Any


class CVUploadRequest(BaseModel):
    candidate_id: str
    file_data: str  # base64-encoded file content
    file_type: Optional[str] = "pdf"
    source_url: Optional[str] = None


class EvaluateFitRequest(BaseModel):
    candidate_profile: dict
    job_id: str


class WorkExperienceInput(BaseModel):
    company: Optional[str] = None
    company_url: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    duration: Optional[str] = None
    duration_months: Optional[int] = None
    is_current: bool = False
    job_type: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    responsibilities: List[str] = []
    achievements: List[str] = []
    reporting_to: Optional[str] = None
    team_size: Optional[int] = None
    annual_salary: Optional[int] = None
    industry: Optional[str] = None


class EducationInput(BaseModel):
    degree: Optional[str] = None
    degree_type: Optional[str] = None
    specialization: Optional[str] = None
    institution: Optional[str] = None
    university: Optional[str] = None
    board: Optional[str] = None
    location: Optional[str] = None
    from_year: Optional[str] = None
    to_year: Optional[str] = None
    year_of_passing: Optional[str] = None
    score: Optional[str] = None
    score_type: Optional[str] = None
    course_type: Optional[str] = None


class SkillInput(BaseModel):
    name: str
    version: Optional[str] = None
    last_used: Optional[str] = None
    experience_months: Optional[int] = None
    experience_years: Optional[float] = None
    proficiency: Optional[str] = None
    is_primary: bool = False


class CertificationInput(BaseModel):
    name: str
    issuing_authority: Optional[str] = None
    license_number: Optional[str] = None
    url: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    is_lifetime: bool = False
    description: Optional[str] = None


class ProjectInput(BaseModel):
    title: str
    client: Optional[str] = None
    status: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    team_size: Optional[int] = None
    skills_used: List[str] = []
    responsibilities: List[str] = []
    project_url: Optional[str] = None


class LanguageInput(BaseModel):
    language: str
    proficiency: Optional[str] = None
    read: bool = False
    write: bool = False
    speak: bool = False


class OnlineProfileInput(BaseModel):
    platform: str = ""
    url: Optional[str] = None
    username: Optional[str] = None


class PersonalDetailsInput(BaseModel):
    date_of_birth: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    nationality: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry: Optional[str] = None
    has_passport: bool = False
    permanent_address: Optional[str] = None
    permanent_city: Optional[str] = None
    permanent_state: Optional[str] = None
    permanent_country: Optional[str] = None
    permanent_pincode: Optional[str] = None
    current_address: Optional[str] = None
    current_city: Optional[str] = None
    current_state: Optional[str] = None
    current_country: Optional[str] = None
    current_pincode: Optional[str] = None
    category: Optional[str] = None
    differently_abled: bool = False
    disability_type: Optional[str] = None
    work_permit_usa: Optional[str] = None
    work_permit_other: Optional[str] = None


class CareerPreferencesInput(BaseModel):
    current_salary: Optional[float] = None
    current_salary_currency: str = "INR"
    current_salary_breakdown: Optional[Dict[str, float]] = None
    expected_salary: Optional[float] = None
    expected_salary_currency: str = "INR"
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    notice_period: Optional[str] = None
    notice_period_days: Optional[int] = None
    is_serving_notice: bool = False
    last_working_day: Optional[str] = None
    is_negotiable: bool = False
    current_location: Optional[str] = None
    preferred_locations: List[str] = []
    willing_to_relocate: bool = False
    relocation_preferences: List[str] = []
    preferred_job_type: List[str] = []
    preferred_employment_type: List[str] = []
    preferred_shift: List[str] = []
    work_from_home: bool = False
    remote_work_preference: Optional[str] = None
    preferred_industry: List[str] = []
    preferred_functional_area: List[str] = []
    preferred_role: List[str] = []
    preferred_role_category: List[str] = []
    preferred_company_type: List[str] = []
    preferred_company_size: Optional[str] = None
    companies_to_avoid: List[str] = []


class CompleteNaukriProfileInput(BaseModel):
    """Complete profile input from extension — supports Naukri, LinkedIn, Foundit"""

    # Source Identification
    naukri_profile_id: Optional[str] = None
    naukri_profile_url: Optional[str] = None
    naukri_resume_id: Optional[str] = None
    source_platform: Optional[str] = "naukri"  # naukri, naukri_mailer, linkedin, foundit
    contact_hidden: Optional[bool] = False  # True when Naukri hides candidate contacts (mailer pages)

    # Basic Info
    name: str
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    photo_url: Optional[str] = None

    # Contact
    email: Optional[str] = None
    alternate_email: Optional[str] = None
    phone: Optional[str] = None
    alternate_phone: Optional[str] = None

    # Professional Identity
    headline: Optional[str] = None
    resume_headline: Optional[str] = None
    profile_summary: Optional[str] = None

    # Current Employment
    current_company: Optional[str] = None
    current_designation: Optional[str] = None
    current_department: Optional[str] = None
    current_industry: Optional[str] = None
    current_role_category: Optional[str] = None
    employment_status: Optional[str] = None

    # Experience
    total_experience_years: Optional[float] = None
    total_experience_months: Optional[int] = None
    total_experience_display: Optional[str] = None
    work_experience: Any = []

    # Education
    highest_qualification: Optional[str] = None
    highest_degree: Optional[str] = None
    education: Any = []

    # Skills
    key_skills: Any = []
    key_skills_display: Optional[str] = None
    it_skills: Any = []
    soft_skills: Any = []
    tools: Any = []

    # Certifications
    certifications: Any = []

    # Projects
    projects: Any = []

    # Languages
    languages: Any = []

    # Online Profiles
    online_profiles: Any = []
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None

    # Personal Details
    personal_details: Optional[PersonalDetailsInput] = None

    # Career Preferences
    career_preferences: Optional[CareerPreferencesInput] = None

    # Additional
    accomplishments: Optional[str] = None
    about_me: Optional[str] = None
    additional_info: Optional[str] = None

    # Resume
    has_resume: bool = False
    resume_title: Optional[str] = None
    resume_format: Optional[str] = None

    @field_validator('work_experience', 'education', 'key_skills', 'it_skills',
                     'soft_skills', 'tools', 'certifications', 'projects',
                     'languages', 'online_profiles', mode='before')
    @classmethod
    def coerce_to_list(cls, v):
        """Safely coerce any input to a list to prevent 422 errors."""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Try to parse comma-separated string
            return [s.strip() for s in v.split(',') if s.strip()] if v.strip() else []
        if isinstance(v, dict):
            return [v]
        return []

    # Timestamps
    profile_created_on: Optional[str] = None
    profile_last_updated: Optional[str] = None
    last_active: Optional[str] = None

    # Activity
    response_rate: Optional[str] = None

    # Raw data for debugging
    raw_profile_text: Optional[str] = None
    raw_sections: Optional[Dict[str, str]] = None
    page_text: Optional[str] = None  # Naukri page summary text (structured: CTC, location, notice)

    # Scrape metadata
    scraped_at: str
    extension_version: Optional[str] = None

    # 3-Layer Capture: DOM scraping flag
    # When True, the extension has sent structured DOM-scraped fields (Layer 1)
    # Backend trusts these over regex/Claude extraction
    dom_scraped: bool = False

    # Mandate context (which mandate was active in the extension when capturing)
    mandate_id: Optional[str] = None

    # Recruiter identity (for filtering out recruiter's own contact info)
    recruiter_phone: Optional[str] = None
    recruiter_email: Optional[str] = None


class CaptureResponse(BaseModel):
    success: bool
    action: str
    candidate_id: str
    message: str


class AIExtractRequest(BaseModel):
    raw_text: str
    page_url: str
    page_title: Optional[str] = None
    naukri_profile_id: Optional[str] = None
    dom_extracted_name: Optional[str] = None
    dom_extracted_email: Optional[str] = None
    dom_extracted_phone: Optional[str] = None
    recruiter_email: Optional[str] = None
    recruiter_phone: Optional[str] = None


class AIExtractResponse(BaseModel):
    success: bool
    profile_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
