"""
AI Matching Pydantic models.
"""
from pydantic import BaseModel, field_validator
from typing import List, Optional


class MatchRequest(BaseModel):
    job_id: Optional[str] = None
    jd_text: Optional[str] = None
    keyword: Optional[str] = None
    must_have_location: Optional[str] = None
    must_have_qualification: Optional[str] = None
    must_have_skills: Optional[List[str]] = None
    min_experience: Optional[int] = None
    max_experience: Optional[int] = None
    quick_match: Optional[bool] = None  # None = auto-decide, True = fast, False = full AI
    match_mode: Optional[str] = None  # "quick" | "full_ai" — overrides quick_match if set
    semantic_search: bool = True  # If True, use vector embeddings for semantic matching
    limit: int = 50  # Max candidates to return


class MatchResult(BaseModel):
    candidate_id: str
    candidate_name: str
    candidate_email: str
    score: int
    skill_match_score: Optional[int] = None
    experience_match_score: Optional[int] = None
    ctc_fit_score: Optional[int] = None
    location_fit_score: Optional[int] = None
    notice_fit_score: Optional[int] = None
    stability_score: Optional[int] = None
    tfidf_score: Optional[float] = None
    semantic_score: Optional[float] = None
    is_maybe: Optional[bool] = None
    data_completeness: Optional[float] = None
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    strengths: List[str] = []
    gaps: List[str] = []
    explanation: str
    filtered_out: bool = False
    filter_reason: Optional[str] = None
    source: Optional[str] = None
    source_role: Optional[str] = None
    # Full profile fields
    phone: Optional[str] = None
    designation: Optional[str] = None
    headline: Optional[str] = None
    current_employer: Optional[str] = None
    location: Optional[str] = None
    experience_years: Optional[float] = None
    current_salary: Optional[float] = None
    expected_salary: Optional[float] = None
    notice_period: Optional[str] = None
    industry: Optional[str] = None
    education: Optional[str] = None
    skills: List[str] = []

    @field_validator('education', mode='before')
    @classmethod
    def format_education(cls, v):
        """Convert education list to string for display."""
        if isinstance(v, list):
            parts = []
            for e in v:
                if isinstance(e, dict):
                    deg = e.get('degree', '')
                    inst = e.get('institution', '')
                    parts.append(f"{deg} - {inst}" if deg and inst else deg or inst)
                elif isinstance(e, str):
                    parts.append(e)
            return ', '.join(p for p in parts if p) or None
        return v


class MatchJobStatus(BaseModel):
    """Status of a background AI matching job."""
    job_id: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    progress: int = 0  # 0-100
    total_candidates: int = 0
    scored_candidates: int = 0
    results: Optional[List[MatchResult]] = None
    error: Optional[str] = None


class JobMatchForCandidate(BaseModel):
    job_id: str
    job_title: str
    company_name: Optional[str] = None
    location: str
    score: int
    explanation: str
    matched_skills: List[str] = []
