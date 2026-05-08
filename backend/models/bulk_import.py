"""
Bulk Import Pydantic models.
Models for chunked upload, Excel/CV parsing, batch save operations.
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class ChunkInitRequest(BaseModel):
    """Request to initialize chunked upload"""
    filename: str
    total_size: int
    total_chunks: int


class ChunkInitResponse(BaseModel):
    """Response from chunk initialization"""
    upload_id: str
    chunk_size: int = 512 * 1024  # 512KB default
    max_file_size: int = 100 * 1024 * 1024  # 100MB default


class ExcelCandidate(BaseModel):
    """Candidate parsed from Excel for review"""
    row_index: int
    source_file: Optional[str] = None  # Original filename this candidate came from
    # Raw Excel data
    candidate_name: str
    contact_no: Optional[str] = None
    email: Optional[str] = None
    work_exp: Optional[str] = None
    annual_salary: Optional[str] = None
    current_location: Optional[str] = None
    current_employer: Optional[str] = None
    designation: Optional[str] = None
    ug_course: Optional[str] = None
    industry: Optional[str] = None
    industry_source: Optional[str] = None  # "excel" or "ai_detected"
    age_dob: Optional[str] = None
    # Parsed/normalized values
    experience_years: int = 0
    salary_inr: Optional[int] = None
    phone_normalized: Optional[str] = None
    # Validation
    is_valid: bool = True
    validation_errors: List[str] = []
    warnings: List[str] = []
    missing_mandatory: List[str] = []
    # Naukri-rich fields
    naukri_data: Optional[dict] = None


class CVCandidate(BaseModel):
    """Candidate parsed from CV/ZIP"""
    row_index: int
    filename: str
    # Parsed from CV
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    experience_years: int = 0
    skills: List[str] = []
    headline: Optional[str] = None
    summary: Optional[str] = None
    experience: List[dict] = []
    education: List[dict] = []
    # From Excel if provided
    excel_data: Optional[Dict] = None
    # R2 Storage
    resume_file_id: Optional[str] = None
    r2_metadata: Optional[dict] = None
    resume_fingerprint: Optional[str] = None
    # Validation
    is_valid: bool = True
    validation_errors: List[str] = []
    warnings: List[str] = []


class FileParseInfo(BaseModel):
    """Per-file parse summary"""
    filename: str
    rows: int
    valid: int
    columns_found: List[str] = []


class ExcelParseResponse(BaseModel):
    """Response from Excel-only parsing"""
    batch_id: str
    mode: str = "excel"
    total_rows: int
    valid_rows: int
    invalid_rows: int
    candidates: List[ExcelCandidate]
    columns_found: List[str]
    ai_industry_detected: int
    files_parsed: int = 1
    file_details: List[FileParseInfo] = []


class CVZipParseResponse(BaseModel):
    """Response from CV/ZIP parsing"""
    batch_id: str
    mode: str = "cv_zip"
    total_files: int
    valid_files: int
    invalid_files: int
    candidates: List[CVCandidate]
    excel_files_found: int


class BulkSaveRequest(BaseModel):
    """Request to save bulk import candidates"""
    batch_id: str
    mode: str  # "excel" or "cv_zip"
    candidates: List[dict]


class BulkSaveResponse(BaseModel):
    """Response from saving bulk import"""
    batch_id: str
    total_attempted: int
    successful: int
    failed: int
    duplicates_merged: int
    results: List[dict]


class AttachCVRequest(BaseModel):
    """Request to attach CV to existing candidate"""
    candidate_id: str


class AsyncCVParseRequest(BaseModel):
    """Request for async CV parsing from chunked upload"""
    upload_id: str
    excel_data: Optional[Dict[str, Dict[str, Any]]] = None  # Pre-parsed Excel data map


class AsyncCVParseResponse(BaseModel):
    """Response from async CV parse initiation"""
    job_id: str
    batch_id: str
    status_url: str
    message: str
