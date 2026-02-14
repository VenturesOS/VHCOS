"""
AI Matching Pydantic models.
"""
from pydantic import BaseModel
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
    semantic_score: Optional[float] = None  # Cosine similarity score (0-100)
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    strengths: List[str] = []
    gaps: List[str] = []
    explanation: str
    filtered_out: bool = False
    filter_reason: Optional[str] = None
    source: Optional[str] = None
    source_role: Optional[str] = None


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
