"""
Extended Naukri Profile Schema
Captures ALL available data from Naukri profiles for 1:1 matching
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime


class NaukriWorkExperience(BaseModel):
    """Complete work experience entry"""
    company: Optional[str] = None
    company_url: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None  # None = Present/Current
    duration: Optional[str] = None
    duration_months: Optional[int] = None
    is_current: bool = False
    job_type: Optional[str] = None  # Full-time, Part-time, Contract, etc.
    location: Optional[str] = None
    description: Optional[str] = None
    responsibilities: List[str] = []
    achievements: List[str] = []
    reporting_to: Optional[str] = None
    team_size: Optional[int] = None
    annual_salary: Optional[int] = None
    industry: Optional[str] = None


class NaukriEducation(BaseModel):
    """Complete education entry"""
    degree: Optional[str] = None
    degree_type: Optional[str] = None  # Full-time, Part-time, Distance
    specialization: Optional[str] = None
    institution: Optional[str] = None
    university: Optional[str] = None
    board: Optional[str] = None  # For 10th/12th
    location: Optional[str] = None
    from_year: Optional[str] = None
    to_year: Optional[str] = None
    year_of_passing: Optional[str] = None
    score: Optional[str] = None
    score_type: Optional[str] = None  # Percentage, CGPA, Grade
    course_type: Optional[str] = None


class NaukriSkill(BaseModel):
    """Detailed skill with proficiency"""
    name: str
    version: Optional[str] = None
    last_used: Optional[str] = None
    experience_months: Optional[int] = None
    experience_years: Optional[float] = None
    proficiency: Optional[str] = None  # Beginner, Intermediate, Expert
    is_primary: bool = False


class NaukriCertification(BaseModel):
    """Certification details"""
    name: str
    issuing_authority: Optional[str] = None
    license_number: Optional[str] = None
    url: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    is_lifetime: bool = False
    description: Optional[str] = None


class NaukriProject(BaseModel):
    """Project details"""
    title: str
    client: Optional[str] = None
    status: Optional[str] = None  # In Progress, Completed
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    team_size: Optional[int] = None
    skills_used: List[str] = []
    responsibilities: List[str] = []
    project_url: Optional[str] = None


class NaukriLanguage(BaseModel):
    """Language proficiency"""
    language: str
    proficiency: Optional[str] = None  # Beginner, Proficient, Expert
    read: bool = False
    write: bool = False
    speak: bool = False


class NaukriOnlineProfile(BaseModel):
    """Online presence/social profiles"""
    platform: str  # LinkedIn, GitHub, Portfolio, etc.
    url: str
    username: Optional[str] = None


class NaukriPatent(BaseModel):
    """Patent details"""
    title: str
    patent_office: Optional[str] = None
    patent_number: Optional[str] = None
    status: Optional[str] = None  # Filed, Published, Granted
    issue_date: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None


class NaukriPublication(BaseModel):
    """Publication details"""
    title: str
    publisher: Optional[str] = None
    publication_date: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None


class NaukriAward(BaseModel):
    """Award/Achievement"""
    title: str
    issuer: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None


class NaukriPersonalDetails(BaseModel):
    """All personal information"""
    date_of_birth: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    nationality: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry: Optional[str] = None
    has_passport: bool = False
    
    # Address
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
    
    # Category
    category: Optional[str] = None  # General, OBC, SC, ST, etc.
    differently_abled: bool = False
    disability_type: Optional[str] = None
    
    # Work Authorization
    work_permit_usa: Optional[str] = None  # H1, Green Card, etc.
    work_permit_other: Optional[str] = None


class NaukriCareerPreferences(BaseModel):
    """Career preferences and expectations"""
    # Salary
    current_salary: Optional[int] = None
    current_salary_currency: str = "INR"
    current_salary_breakdown: Optional[Dict[str, int]] = None  # Fixed, Variable, Bonus, etc.
    expected_salary: Optional[int] = None
    expected_salary_currency: str = "INR"
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    
    # Notice Period
    notice_period: Optional[str] = None
    notice_period_days: Optional[int] = None
    is_serving_notice: bool = False
    last_working_day: Optional[str] = None
    is_negotiable: bool = False
    
    # Location Preferences
    current_location: Optional[str] = None
    preferred_locations: List[str] = []
    willing_to_relocate: bool = False
    relocation_preferences: List[str] = []
    
    # Job Type Preferences
    preferred_job_type: List[str] = []  # Full-time, Part-time, Contract, Freelance
    preferred_employment_type: List[str] = []  # Permanent, Temporary
    preferred_shift: List[str] = []  # Day, Night, Flexible
    work_from_home: bool = False
    remote_work_preference: Optional[str] = None
    
    # Industry & Role
    preferred_industry: List[str] = []
    preferred_functional_area: List[str] = []
    preferred_role: List[str] = []
    preferred_role_category: List[str] = []
    
    # Company Preferences
    preferred_company_type: List[str] = []  # Startup, MNC, Product, Service
    preferred_company_size: Optional[str] = None
    companies_to_avoid: List[str] = []


class NaukriProfileMetadata(BaseModel):
    """Naukri profile metadata"""
    naukri_profile_id: str
    naukri_profile_url: str
    naukri_resume_id: Optional[str] = None
    
    # Timestamps
    profile_created_on: Optional[str] = None
    profile_last_updated: Optional[str] = None
    last_active: Optional[str] = None
    resume_updated_on: Optional[str] = None
    
    # Activity
    response_rate: Optional[str] = None
    profile_views: Optional[int] = None
    applications_sent: Optional[int] = None
    
    # Verification
    is_email_verified: bool = False
    is_phone_verified: bool = False
    is_profile_verified: bool = False
    verification_badges: List[str] = []
    
    # Premium
    is_premium: bool = False
    premium_type: Optional[str] = None
    
    # Scrape info
    scraped_at: str
    scraped_by_extension_version: str = "1.0.0"


class CompleteNaukriProfile(BaseModel):
    """
    Complete Naukri Profile - captures EVERYTHING available
    This should match the Naukri profile 1:1
    """
    
    # === BASIC INFORMATION ===
    name: str
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    
    # Profile Photo
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
    
    # === CURRENT EMPLOYMENT ===
    current_company: Optional[str] = None
    current_designation: Optional[str] = None
    current_department: Optional[str] = None
    current_industry: Optional[str] = None
    current_role_category: Optional[str] = None
    employment_status: Optional[str] = None  # Employed, Unemployed, Fresher
    
    # === EXPERIENCE ===
    total_experience_years: Optional[float] = None
    total_experience_months: Optional[int] = None
    total_experience_display: Optional[str] = None  # "15 years 3 months"
    work_experience: List[NaukriWorkExperience] = []
    
    # === EDUCATION ===
    highest_qualification: Optional[str] = None
    highest_degree: Optional[str] = None
    education: List[NaukriEducation] = []
    
    # === SKILLS ===
    key_skills: List[str] = []
    key_skills_display: Optional[str] = None  # Raw text as shown on Naukri
    it_skills: List[NaukriSkill] = []
    soft_skills: List[str] = []
    tools: List[str] = []
    
    # === CERTIFICATIONS ===
    certifications: List[NaukriCertification] = []
    
    # === PROJECTS ===
    projects: List[NaukriProject] = []
    
    # === LANGUAGES ===
    languages: List[NaukriLanguage] = []
    
    # === ONLINE PROFILES ===
    online_profiles: List[NaukriOnlineProfile] = []
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    
    # === PATENTS & PUBLICATIONS ===
    patents: List[NaukriPatent] = []
    publications: List[NaukriPublication] = []
    
    # === AWARDS ===
    awards: List[NaukriAward] = []
    
    # === PERSONAL DETAILS ===
    personal_details: Optional[NaukriPersonalDetails] = None
    
    # === CAREER PREFERENCES ===
    career_preferences: Optional[NaukriCareerPreferences] = None
    
    # === ACCOMPLISHMENTS ===
    accomplishments: Optional[str] = None
    
    # === ADDITIONAL INFO ===
    about_me: Optional[str] = None
    additional_info: Optional[str] = None
    
    # === RESUME ===
    has_resume: bool = False
    resume_title: Optional[str] = None
    resume_format: Optional[str] = None  # PDF, DOC, etc.
    
    # === AI-DETECTED FIELDS ===
    ai_detected_industry: Optional[str] = None
    ai_detected_role_category: Optional[str] = None
    ai_confidence_score: Optional[float] = None
    
    # === METADATA ===
    metadata: Optional[NaukriProfileMetadata] = None
    
    # === RAW DATA ===
    raw_profile_text: Optional[str] = None  # Store raw text for debugging
    raw_sections: Optional[Dict[str, str]] = None  # Store each section's raw content
