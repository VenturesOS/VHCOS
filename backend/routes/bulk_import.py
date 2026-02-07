"""
VHC Talent OS - Enhanced Bulk Import Routes
Admin-only tool for controlled production-grade candidate data seeding.

TWO IMPORT MODES:
1. EXCEL-ONLY: Upload Excel → Create profiles without CV → Attach CV later
2. CV/ZIP-ONLY: Upload ZIP of resumes (+ optional Excel) → Parse CVs → Create profiles

FEATURES:
- AI Industry Detection: If Industry column is empty, GPT detects from employer name
- Smart Deduplication: Higher salary/notice, merged job history, deduplicated skills
- Strict Governance: All imports are Admin-only until discovered via AI Screening
"""
import uuid
import logging
import zipfile
import tempfile
import os
import io
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import pandas as pd

# Import configuration
from config import db

# Import utilities
from utils import require_role

# Import services
from services.r2_storage import generate_r2_key, upload_to_r2
from services.matching_engine import parse_resume_with_ai, generate_resume_fingerprint

# Import Emergent LLM for industry detection
from emergentintegrations.llm.chat import LlmChat, UserMessage

# Import chunked upload service
from services.chunked_upload import chunked_upload_service, CHUNK_SIZE, MAX_FILE_SIZE

# Import job queue for background processing
from services.job_queue import job_queue, JobType

# Create router
bulk_import_router = APIRouter(prefix="/api/admin/bulk-import", tags=["Bulk Import"])

logger = logging.getLogger(__name__)


# ============== CHUNKED UPLOAD ENDPOINTS ==============

class ChunkInitRequest(BaseModel):
    """Request to initialize chunked upload"""
    filename: str
    total_size: int
    total_chunks: int


class ChunkInitResponse(BaseModel):
    """Response from chunk initialization"""
    upload_id: str
    chunk_size: int = CHUNK_SIZE
    max_file_size: int = MAX_FILE_SIZE


@bulk_import_router.post("/chunk/init", response_model=ChunkInitResponse)
async def init_chunked_upload(
    request: ChunkInitRequest,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Initialize a chunked file upload session.
    Returns upload_id to use for subsequent chunk uploads.
    
    Client should:
    1. Call this endpoint with filename, total_size, total_chunks
    2. Upload each chunk to /chunk/upload with the upload_id
    3. Call /chunk/complete to assemble the file
    4. Process the assembled file with /cv-zip-chunked
    """
    try:
        upload = chunked_upload_service.initiate_upload(
            filename=request.filename,
            total_size=request.total_size,
            total_chunks=request.total_chunks,
            created_by=current_user["id"]
        )
        
        logger.info(f"[CHUNK INIT] Upload {upload.upload_id} initiated for {request.filename}")
        
        return ChunkInitResponse(
            upload_id=upload.upload_id,
            chunk_size=CHUNK_SIZE,
            max_file_size=MAX_FILE_SIZE
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[CHUNK INIT] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize upload")


@bulk_import_router.post("/chunk/upload")
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Upload a single chunk of the file.
    
    Returns progress information including:
    - chunks_received: number of chunks uploaded so far
    - total_chunks: total expected chunks
    - progress: percentage complete
    """
    try:
        chunk_data = await chunk.read()
        
        result = await chunked_upload_service.upload_chunk(
            upload_id=upload_id,
            chunk_index=chunk_index,
            chunk_data=chunk_data
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[CHUNK UPLOAD] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload chunk")


@bulk_import_router.post("/chunk/complete")
async def complete_chunked_upload(
    upload_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Complete the chunked upload by assembling all chunks.
    Returns the path to the assembled file for processing.
    """
    try:
        result = await chunked_upload_service.complete_upload(upload_id)
        
        logger.info(f"[CHUNK COMPLETE] Upload {upload_id} assembled: {result['filename']}")
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[CHUNK COMPLETE] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete upload")


@bulk_import_router.get("/chunk/status/{upload_id}")
async def get_chunk_status(
    upload_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get the status of an in-progress chunked upload."""
    upload = chunked_upload_service.get_upload_status(upload_id)
    
    if not upload:
        raise HTTPException(status_code=404, detail="Upload session not found")
    
    return {
        "upload_id": upload.upload_id,
        "filename": upload.filename,
        "total_size": upload.total_size,
        "total_chunks": upload.total_chunks,
        "chunks_received": upload.chunks_received,
        "progress": round(upload.chunks_received / upload.total_chunks * 100, 1) if upload.total_chunks > 0 else 0,
        "status": upload.status,
        "created_at": upload.created_at
    }


@bulk_import_router.delete("/chunk/cancel/{upload_id}")
async def cancel_chunked_upload(
    upload_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Cancel and cleanup an in-progress chunked upload."""
    success = chunked_upload_service.cancel_upload(upload_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Upload session not found")
    
    return {"message": "Upload cancelled", "upload_id": upload_id}


# Get Emergent LLM Key
EMERGENT_KEY = os.environ.get('EMERGENT_LLM_KEY')


# ============== PYDANTIC MODELS ==============

class ExcelCandidate(BaseModel):
    """Candidate parsed from Excel for review"""
    row_index: int
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


# ============== HELPER FUNCTIONS ==============

def get_ai_chat_client(system_msg: str):
    """Get Emergent Chat client for GPT"""
    return LlmChat(
        api_key=EMERGENT_KEY,
        session_id=str(uuid.uuid4()),
        system_message=system_msg
    )


async def detect_industry_from_employer(employer_name: str) -> Optional[str]:
    """Use GPT to detect industry from employer/company name"""
    if not employer_name or not EMERGENT_KEY:
        return None
    
    try:
        chat = get_ai_chat_client(
            "You are an expert at identifying company industries. "
            "Given a company name, determine its primary industry sector. "
            "Return ONLY the industry name, nothing else. Keep it concise (1-3 words)."
        )
        
        prompt = f"""What industry does this company operate in? Company name: "{employer_name}"

Return ONLY the industry name (1-3 words), for example:
- Information Technology
- Automobile Manufacturing
- FMCG
- Banking & Finance
- Healthcare
- Consulting
- Retail
- Pharmaceutical
- Logistics
- Energy

Industry:"""
        
        response = await chat.send_message(UserMessage(text=prompt))
        
        if response:
            industry = response.strip().strip('"').strip("'")
            # Clean up any extra text
            if len(industry) > 50:  # Too long, likely contains explanation
                industry = industry.split('\n')[0].strip()
            logger.info(f"[AI INDUSTRY] Detected '{industry}' for employer '{employer_name}'")
            return industry
        return None
        
    except Exception as e:
        logger.error(f"[AI INDUSTRY] Error detecting industry for '{employer_name}': {e}")
        return None


def parse_experience_string(exp_str: str) -> int:
    """Parse experience string like '10Y 0 M' or '4Y 0 M' to years"""
    if not exp_str:
        return 0
    try:
        exp_str = str(exp_str).upper().strip()
        # Match patterns like "10Y 0 M", "4Y", "10 Years", etc.
        year_match = re.search(r'(\d+)\s*Y', exp_str)
        if year_match:
            return int(year_match.group(1))
        # Try just number
        num_match = re.search(r'(\d+)', exp_str)
        if num_match:
            return int(num_match.group(1))
        return 0
    except Exception:
        return 0


def parse_salary_string(salary_str: str) -> Optional[int]:
    """Parse salary string like '10.0 L' or '15.5 L' to INR"""
    if not salary_str:
        return None
    try:
        salary_str = str(salary_str).upper().strip()
        # Match patterns like "10.0 L", "15.5L", "10 Lakh", etc.
        match = re.search(r'(\d+\.?\d*)\s*L', salary_str)
        if match:
            lakhs = float(match.group(1))
            return int(lakhs * 100000)
        # Try just number (assume in lakhs)
        num_match = re.search(r'(\d+\.?\d*)', salary_str)
        if num_match:
            val = float(num_match.group(1))
            if val < 100:  # Likely in lakhs
                return int(val * 100000)
            return int(val)
        return None
    except Exception:
        return None


def normalize_phone(phone: str) -> Optional[str]:
    """Normalize phone number to last 10 digits"""
    if not phone:
        return None
    digits = "".join(filter(str.isdigit, str(phone)))
    return digits[-10:] if len(digits) >= 10 else digits if digits else None


def extract_text_from_file(file_content: bytes, filename: str) -> str:
    """Extract text from PDF, DOC, or DOCX files"""
    ext = Path(filename).suffix.lower()
    
    try:
        if ext == '.pdf':
            import fitz  # PyMuPDF
            doc = fitz.open(stream=file_content, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        
        elif ext == '.docx':
            from docx import Document
            doc = Document(io.BytesIO(file_content))
            return "\n".join([para.text for para in doc.paragraphs])
        
        elif ext == '.doc':
            try:
                text = file_content.decode('utf-8', errors='ignore')
                text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t')
                return text
            except Exception:
                return ""
        
        return ""
    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {e}")
        return ""


def merge_skills(existing: List[str], new: List[str]) -> List[str]:
    """Merge and deduplicate skills"""
    seen_lower = set()
    result = []
    for s in existing + new:
        if s and s.strip().lower() not in seen_lower:
            result.append(s.strip())
            seen_lower.add(s.strip().lower())
    return result


def merge_experience(existing: List[dict], new: List[dict]) -> List[dict]:
    """Merge job history and sort chronologically by latest date"""
    all_exp = existing + new
    # Sort by duration/date (descending - newest first)
    # Try to extract year from duration for sorting
    def get_sort_key(exp):
        duration = exp.get('duration', '') or ''
        # Try to find year numbers
        years = re.findall(r'20\d{2}', duration)
        if years:
            return max(int(y) for y in years)
        return 0
    
    return sorted(all_exp, key=get_sort_key, reverse=True)


# ============== EXCEL-ONLY MODE ENDPOINTS ==============

@bulk_import_router.post("/excel", response_model=ExcelParseResponse)
async def parse_excel_only(
    excel_file: UploadFile = File(..., description="Excel/CSV file with candidate data"),
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    MODE A: Excel-Only Import
    
    Parse Excel file and create candidate profiles WITHOUT CV.
    AI will detect industry from employer name if Industry column is empty.
    
    Required columns (marked with *):
    - Candidate Name*
    - Contact No.*
    - Email*
    - Work Exp*
    - Annual Salary*
    - Current Location*
    - Current Employer*
    - Designation*
    - U.G. Course*
    - Industry* (AI-detected if empty)
    - Age/Date of Birth*
    """
    batch_id = str(uuid.uuid4())
    candidates = []
    columns_found = []
    ai_industry_count = 0
    
    # Validate file type
    ext = Path(excel_file.filename).suffix.lower()
    if ext not in ['.xlsx', '.xls', '.csv']:
        raise HTTPException(status_code=400, detail="File must be .xlsx, .xls, or .csv")
    
    # Read Excel
    try:
        content = await excel_file.read()
        if ext == '.csv':
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
        
        # Normalize column names (remove * and whitespace)
        original_cols = list(df.columns)
        df.columns = [col.strip().rstrip('*').strip().rstrip('.').strip().lower().replace(' ', '_').replace('.', '_') for col in df.columns]
        columns_found = original_cols
        
        logger.info(f"[EXCEL PARSE] Columns: {list(df.columns)}")
        
    except Exception as e:
        logger.error(f"[EXCEL PARSE] Error reading file: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to read Excel file: {str(e)}")
    
    # Column mapping
    col_map = {
        'candidate_name': ['candidate_name', 'name', 'full_name', 'candidate'],
        'contact_no': ['contact_no', 'contact', 'phone', 'mobile', 'phone_number'],
        'email': ['email', 'email_id', 'e-mail', 'mail'],
        'work_exp': ['work_exp', 'experience', 'exp', 'work_experience', 'total_exp'],
        'annual_salary': ['annual_salary', 'salary', 'ctc', 'current_salary', 'current_ctc'],
        'current_location': ['current_location', 'location', 'city'],
        'current_employer': ['current_employer', 'employer', 'company', 'current_company'],
        'designation': ['designation', 'title', 'job_title', 'position', 'role'],
        'ug_course': ['ug_course', 'u_g_course', 'u_g__course', 'education', 'degree', 'qualification'],
        'industry': ['industry', 'sector', 'domain'],
        'age_dob': ['age/date_of_birth', 'age_date_of_birth', 'dob', 'date_of_birth', 'age', 'birth_date']
    }
    
    def find_column(df, key):
        for possible in col_map.get(key, [key]):
            if possible in df.columns:
                return possible
        return None
    
    # Process each row
    for idx, row in df.iterrows():
        try:
            candidate = ExcelCandidate(row_index=idx, candidate_name="Unknown")
            missing_mandatory = []
            
            # Extract each field
            def get_val(key):
                col = find_column(df, key)
                if col and pd.notna(row.get(col)):
                    return str(row[col]).strip()
                return None
            
            # Name
            name = get_val('candidate_name')
            if not name:
                missing_mandatory.append('Candidate Name')
                name = "Unknown"
            candidate.candidate_name = name
            
            # Contact
            contact = get_val('contact_no')
            if not contact:
                missing_mandatory.append('Contact No.')
            candidate.contact_no = contact
            candidate.phone_normalized = normalize_phone(contact)
            
            # Email
            email = get_val('email')
            if not email:
                missing_mandatory.append('Email')
            candidate.email = email
            
            # Work Experience
            work_exp = get_val('work_exp')
            if not work_exp:
                missing_mandatory.append('Work Exp')
            candidate.work_exp = work_exp
            candidate.experience_years = parse_experience_string(work_exp)
            
            # Salary
            salary = get_val('annual_salary')
            if not salary:
                missing_mandatory.append('Annual Salary')
            candidate.annual_salary = salary
            candidate.salary_inr = parse_salary_string(salary)
            
            # Location
            location = get_val('current_location')
            if not location:
                missing_mandatory.append('Current Location')
            candidate.current_location = location
            
            # Employer
            employer = get_val('current_employer')
            if not employer:
                missing_mandatory.append('Current Employer')
            candidate.current_employer = employer
            
            # Designation
            designation = get_val('designation')
            if not designation:
                missing_mandatory.append('Designation')
            candidate.designation = designation
            
            # Education
            ug_course = get_val('ug_course')
            if not ug_course:
                missing_mandatory.append('U.G. Course')
            candidate.ug_course = ug_course
            
            # Industry (AI-detect if empty)
            industry = get_val('industry')
            if industry:
                candidate.industry = industry
                candidate.industry_source = "excel"
            elif employer:
                # AI detect from employer
                detected = await detect_industry_from_employer(employer)
                if detected:
                    candidate.industry = detected
                    candidate.industry_source = "ai_detected"
                    ai_industry_count += 1
                else:
                    missing_mandatory.append('Industry')
            else:
                missing_mandatory.append('Industry')
            
            # Age/DOB
            age_dob = get_val('age_dob')
            if not age_dob:
                missing_mandatory.append('Age/Date of Birth')
            candidate.age_dob = age_dob
            
            # Set validation status
            candidate.missing_mandatory = missing_mandatory
            if missing_mandatory:
                candidate.warnings.append(f"Missing mandatory fields will be marked as 'Unknown': {', '.join(missing_mandatory)}")
            
            # Validation: at least email or phone required
            if not candidate.email and not candidate.phone_normalized:
                candidate.validation_errors.append("Either email or phone is required")
                candidate.is_valid = False
            
            candidates.append(candidate)
            
        except Exception as e:
            logger.error(f"[EXCEL PARSE] Error on row {idx}: {e}")
            candidates.append(ExcelCandidate(
                row_index=idx,
                candidate_name=f"Row {idx} Error",
                is_valid=False,
                validation_errors=[str(e)]
            ))
    
    valid_count = sum(1 for c in candidates if c.is_valid)
    
    # Store batch metadata
    now = datetime.now(timezone.utc).isoformat()
    batch_doc = {
        "id": batch_id,
        "mode": "excel",
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user["name"],
        "total_rows": len(candidates),
        "valid_rows": valid_count,
        "invalid_rows": len(candidates) - valid_count,
        "ai_industry_detected": ai_industry_count,
        "status": "pending_review",
        "candidates_preview": [c.dict() for c in candidates]
    }
    await db.bulk_import_batches.insert_one(batch_doc)
    
    return ExcelParseResponse(
        batch_id=batch_id,
        total_rows=len(candidates),
        valid_rows=valid_count,
        invalid_rows=len(candidates) - valid_count,
        candidates=candidates,
        columns_found=columns_found,
        ai_industry_detected=ai_industry_count
    )


# ============== CV/ZIP MODE ENDPOINTS ==============

@bulk_import_router.post("/cv-zip", response_model=CVZipParseResponse)
async def parse_cv_zip(
    zip_file: UploadFile = File(..., description="ZIP file containing CVs and optional Excel"),
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    MODE B: CV/ZIP-Only Import
    
    Parse ZIP file containing:
    - Resume files (PDF, DOC, DOCX)
    - Optional Excel files with additional metadata
    
    CVs are parsed using AI and profiles created with cv_attached=true.
    """
    batch_id = str(uuid.uuid4())
    candidates = []
    excel_files_found = 0
    excel_data_map = {}  # Map by email/phone for matching
    
    # Validate file type
    if not zip_file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")
    
    # Extract ZIP
    try:
        zip_content = await zip_file.read()
        resume_files = []  # List of (filename, content)
        excel_files = []  # List of (filename, content)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "upload.zip")
            with open(zip_path, 'wb') as f:
                f.write(zip_content)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.is_dir():
                        continue
                    
                    filename = os.path.basename(file_info.filename)
                    ext = Path(filename).suffix.lower()
                    
                    with zip_ref.open(file_info) as f:
                        content = f.read()
                    
                    if ext in ['.pdf', '.doc', '.docx']:
                        resume_files.append((filename, content))
                    elif ext in ['.xlsx', '.xls', '.csv']:
                        excel_files.append((filename, content))
                        excel_files_found += 1
        
        if not resume_files:
            raise HTTPException(status_code=400, detail="No resume files (PDF, DOC, DOCX) found in ZIP")
        
        logger.info(f"[CV ZIP] Found {len(resume_files)} resumes, {excel_files_found} Excel files")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CV ZIP] Error extracting ZIP: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to extract ZIP: {str(e)}")
    
    # Parse Excel files for additional metadata
    for excel_name, excel_content in excel_files:
        try:
            ext = Path(excel_name).suffix.lower()
            if ext == '.csv':
                df = pd.read_csv(io.BytesIO(excel_content))
            else:
                df = pd.read_excel(io.BytesIO(excel_content))
            
            df.columns = [col.strip().rstrip('*').strip().rstrip('.').strip().lower().replace(' ', '_').replace('.', '_') for col in df.columns]
            
            for _, row in df.iterrows():
                email = str(row.get('email', '')).strip().lower() if pd.notna(row.get('email')) else None
                phone = normalize_phone(str(row.get('contact_no', row.get('phone', '')))) if pd.notna(row.get('contact_no', row.get('phone'))) else None
                
                data = {
                    'name': str(row.get('candidate_name', row.get('name', ''))).strip() if pd.notna(row.get('candidate_name', row.get('name'))) else None,
                    'email': email,
                    'phone': phone,
                    'location': str(row.get('current_location', row.get('location', ''))).strip() if pd.notna(row.get('current_location', row.get('location'))) else None,
                    'salary': parse_salary_string(str(row.get('annual_salary', row.get('salary', '')))),
                    'employer': str(row.get('current_employer', '')).strip() if pd.notna(row.get('current_employer')) else None,
                    'designation': str(row.get('designation', '')).strip() if pd.notna(row.get('designation')) else None,
                }
                
                if email:
                    excel_data_map[email] = data
                if phone:
                    excel_data_map[phone] = data
                    
        except Exception as e:
            logger.warning(f"[CV ZIP] Error parsing Excel {excel_name}: {e}")
    
    # Process each resume
    now = datetime.now(timezone.utc).isoformat()
    
    for idx, (filename, content) in enumerate(resume_files):
        try:
            candidate = CVCandidate(row_index=idx, filename=filename)
            
            # Upload to R2
            file_id = str(uuid.uuid4())
            r2_key = generate_r2_key("bulk-import-cv", filename)
            
            ext = Path(filename).suffix.lower()
            content_type_map = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            }
            content_type = content_type_map.get(ext, 'application/octet-stream')
            
            r2_result = await upload_to_r2(content, r2_key, content_type)
            candidate.resume_file_id = file_id
            candidate.r2_metadata = r2_result
            
            # Extract text and parse with AI
            resume_text = extract_text_from_file(content, filename)
            
            if resume_text:
                # Generate fingerprint
                candidate.resume_fingerprint = generate_resume_fingerprint(resume_text)
                
                # Parse with AI
                if len(resume_text) > 100:
                    parsed = await parse_resume_with_ai(resume_text[:8000])
                    
                    if parsed.get('success') and parsed.get('data'):
                        data = parsed['data']
                        candidate.name = data.get('name')
                        candidate.email = data.get('email')
                        candidate.phone = data.get('phone')
                        candidate.location = data.get('location')
                        candidate.experience_years = data.get('experience_years', 0) or 0
                        candidate.skills = data.get('skills', [])
                        candidate.headline = data.get('headline')
                        candidate.summary = data.get('summary')
                        candidate.experience = data.get('experience', [])
                        candidate.education = data.get('education', [])
                    else:
                        candidate.warnings.append(f"AI parsing failed: {parsed.get('error', 'Unknown error')}")
            else:
                candidate.warnings.append("Could not extract text from file")
            
            # Try to match with Excel data
            if candidate.email and candidate.email.lower() in excel_data_map:
                candidate.excel_data = excel_data_map[candidate.email.lower()]
            elif candidate.phone:
                phone_norm = normalize_phone(candidate.phone)
                if phone_norm and phone_norm in excel_data_map:
                    candidate.excel_data = excel_data_map[phone_norm]
            
            # Validate
            if not candidate.name and not (candidate.excel_data and candidate.excel_data.get('name')):
                candidate.validation_errors.append("Could not extract name from CV")
            
            if not candidate.email and not candidate.phone:
                candidate.validation_errors.append("No email or phone found in CV")
                candidate.is_valid = False
            
            candidates.append(candidate)
            
        except Exception as e:
            logger.error(f"[CV ZIP] Error processing {filename}: {e}")
            candidates.append(CVCandidate(
                row_index=idx,
                filename=filename,
                is_valid=False,
                validation_errors=[str(e)]
            ))
    
    valid_count = sum(1 for c in candidates if c.is_valid)
    
    # Store batch metadata
    batch_doc = {
        "id": batch_id,
        "mode": "cv_zip",
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user["name"],
        "total_files": len(candidates),
        "valid_files": valid_count,
        "invalid_files": len(candidates) - valid_count,
        "excel_files_found": excel_files_found,
        "status": "pending_review",
        "candidates_preview": [c.dict() for c in candidates]
    }
    await db.bulk_import_batches.insert_one(batch_doc)
    
    return CVZipParseResponse(
        batch_id=batch_id,
        total_files=len(candidates),
        valid_files=valid_count,
        invalid_files=len(candidates) - valid_count,
        candidates=candidates,
        excel_files_found=excel_files_found
    )


# ============== SAVE ENDPOINT (Both Modes) ==============

@bulk_import_router.post("/save", response_model=BulkSaveResponse)
async def save_bulk_import(
    request: BulkSaveRequest,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Save reviewed candidates to Candidate Bank.
    
    SMART DEDUPLICATION:
    - Finds duplicates by email or phone
    - Salary/Notice: Uses HIGHER value
    - Job History: Merges and sorts by latest date
    - Location: Uses location from most recent job
    - Skills: Merges and deduplicates
    
    GOVERNANCE:
    - All records marked with bulk_import_restricted=true
    - Only Admin can view until discovered via AI Screening
    - Permanent visibility granted after "Add as Applicant"
    """
    batch_id = request.batch_id
    mode = request.mode
    candidates = request.candidates
    
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates to save")
    
    # Verify batch exists
    batch = await db.bulk_import_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")
    
    now = datetime.now(timezone.utc).isoformat()
    results = []
    successful = 0
    failed = 0
    duplicates_merged = 0
    
    for candidate_data in candidates:
        try:
            # Extract identifiers
            if mode == "excel":
                email = candidate_data.get('email')
                phone = candidate_data.get('phone_normalized') or normalize_phone(candidate_data.get('contact_no'))
                name = candidate_data.get('candidate_name', 'Unknown')
            else:  # cv_zip
                email = candidate_data.get('email')
                phone = normalize_phone(candidate_data.get('phone'))
                name = candidate_data.get('name') or (candidate_data.get('excel_data') or {}).get('name') or 'Unknown'
            
            # Check for existing candidate (deduplication)
            existing = None
            if email:
                existing = await db.candidate_bank.find_one({"email": email.lower()}, {"_id": 0})
            if not existing and phone:
                existing = await db.candidate_bank.find_one({"phone_normalized": phone}, {"_id": 0})
            
            if existing:
                # MERGE with existing record
                update_fields = {
                    "updated_at": now,
                    "last_updated_by": current_user["id"],
                }
                
                # Salary: Use higher value
                new_salary = candidate_data.get('salary_inr') or candidate_data.get('current_salary')
                if new_salary and (not existing.get('current_salary') or new_salary > existing.get('current_salary')):
                    update_fields["current_salary"] = new_salary
                
                # Skills: Merge
                existing_skills = existing.get('skills', [])
                new_skills = candidate_data.get('skills', [])
                if new_skills:
                    update_fields["skills"] = merge_skills(existing_skills, new_skills)
                
                # Experience: Merge
                existing_exp = existing.get('experience', [])
                new_exp = candidate_data.get('experience', [])
                if new_exp:
                    merged_exp = merge_experience(existing_exp, new_exp)
                    update_fields["experience"] = merged_exp
                    # Location from most recent job
                    if merged_exp and merged_exp[0].get('location'):
                        update_fields["location"] = merged_exp[0].get('location')
                
                # Add resume version if CV mode
                if mode == "cv_zip" and candidate_data.get('resume_file_id'):
                    resume_version = {
                        "id": candidate_data.get('resume_file_id'),
                        "fingerprint": candidate_data.get('resume_fingerprint'),
                        "uploaded_at": now,
                        "uploaded_by": current_user["id"],
                        "is_active": True,
                        "r2_metadata": candidate_data.get('r2_metadata'),
                        "original_filename": candidate_data.get('filename')
                    }
                    existing_versions = existing.get("resume_versions", [])
                    existing_versions.append(resume_version)
                    update_fields["resume_versions"] = existing_versions
                    update_fields["active_resume_id"] = candidate_data.get('resume_file_id')
                    update_fields["cv_attached"] = True
                
                # Update
                await db.candidate_bank.update_one(
                    {"id": existing["id"]},
                    {"$set": update_fields}
                )
                
                results.append({
                    "row_index": candidate_data.get('row_index'),
                    "name": name,
                    "email": email,
                    "status": "merged",
                    "candidate_id": existing["id"],
                    "message": "Merged with existing candidate"
                })
                successful += 1
                duplicates_merged += 1
                
            else:
                # CREATE new candidate
                candidate_id = str(uuid.uuid4())
                
                if mode == "excel":
                    candidate_doc = {
                        "id": candidate_id,
                        "email": email.lower() if email else None,
                        "name": name,
                        "phone": candidate_data.get('contact_no'),
                        "phone_normalized": phone,
                        "headline": candidate_data.get('designation'),
                        "summary": None,
                        "skills": [],
                        "experience_years": candidate_data.get('experience_years', 0),
                        "experience": [],
                        "education": [{"degree": candidate_data.get('ug_course')}] if candidate_data.get('ug_course') else [],
                        "location": candidate_data.get('current_location'),
                        "certifications": [],
                        "active_resume_id": None,
                        "resume_versions": [],
                        "resume_fingerprints": [],
                        "resume_url": None,
                        "current_salary": candidate_data.get('salary_inr'),
                        "notice_period": None,
                        # Bulk import specific fields
                        "source": "bulk_import",
                        "bulk_import_type": "excel",
                        "bulk_import_restricted": True,  # Admin only until discovered
                        "cv_attached": False,  # No CV yet for Excel imports
                        "industry": candidate_data.get('industry'),
                        "industry_source": candidate_data.get('industry_source'),
                        "current_employer": candidate_data.get('current_employer'),
                        "designation": candidate_data.get('designation'),
                        "ug_course": candidate_data.get('ug_course'),
                        "date_of_birth": candidate_data.get('age_dob'),
                        "import_batch_id": batch_id,
                        "discovered_by": [],
                        # Standard fields
                        "linked_user_id": None,
                        "visibility": {"admin_ids": [current_user["id"]], "employer_ids": [], "recruiter_ids": []},
                        "match_cache": [],
                        "created_at": now,
                        "updated_at": now,
                        "created_by": current_user["id"],
                        "last_updated_by": current_user["id"],
                        "uploaded_by_role": "admin",
                        "application_history": [],
                        "profile_update_audit": [{
                            "action": "bulk_import_created",
                            "mode": "excel",
                            "by_id": current_user["id"],
                            "by_name": current_user["name"],
                            "by_role": "admin",
                            "timestamp": now,
                            "batch_id": batch_id
                        }]
                    }
                else:  # cv_zip
                    excel_data = candidate_data.get('excel_data') or {}
                    
                    candidate_doc = {
                        "id": candidate_id,
                        "email": email.lower() if email else None,
                        "name": name,
                        "phone": candidate_data.get('phone'),
                        "phone_normalized": phone,
                        "headline": candidate_data.get('headline') or excel_data.get('designation'),
                        "summary": candidate_data.get('summary'),
                        "skills": candidate_data.get('skills', []),
                        "experience_years": candidate_data.get('experience_years', 0),
                        "experience": candidate_data.get('experience', []),
                        "education": candidate_data.get('education', []),
                        "location": candidate_data.get('location') or excel_data.get('location'),
                        "certifications": [],
                        "active_resume_id": candidate_data.get('resume_file_id'),
                        "resume_versions": [{
                            "id": candidate_data.get('resume_file_id'),
                            "fingerprint": candidate_data.get('resume_fingerprint'),
                            "uploaded_at": now,
                            "uploaded_by": current_user["id"],
                            "is_active": True,
                            "r2_metadata": candidate_data.get('r2_metadata'),
                            "original_filename": candidate_data.get('filename')
                        }] if candidate_data.get('resume_file_id') else [],
                        "resume_fingerprints": [candidate_data.get('resume_fingerprint')] if candidate_data.get('resume_fingerprint') else [],
                        "resume_url": None,
                        "current_salary": excel_data.get('salary'),
                        "notice_period": None,
                        # Bulk import specific fields
                        "source": "bulk_import",
                        "bulk_import_type": "cv_zip",
                        "bulk_import_restricted": True,  # Admin only until discovered
                        "cv_attached": True,  # Has CV
                        "industry": None,
                        "industry_source": None,
                        "current_employer": excel_data.get('employer'),
                        "designation": excel_data.get('designation'),
                        "ug_course": None,
                        "date_of_birth": None,
                        "import_batch_id": batch_id,
                        "discovered_by": [],
                        # Standard fields
                        "linked_user_id": None,
                        "visibility": {"admin_ids": [current_user["id"]], "employer_ids": [], "recruiter_ids": []},
                        "match_cache": [],
                        "created_at": now,
                        "updated_at": now,
                        "created_by": current_user["id"],
                        "last_updated_by": current_user["id"],
                        "uploaded_by_role": "admin",
                        "application_history": [],
                        "profile_update_audit": [{
                            "action": "bulk_import_created",
                            "mode": "cv_zip",
                            "by_id": current_user["id"],
                            "by_name": current_user["name"],
                            "by_role": "admin",
                            "timestamp": now,
                            "batch_id": batch_id
                        }]
                    }
                
                await db.candidate_bank.insert_one(candidate_doc)
                
                results.append({
                    "row_index": candidate_data.get('row_index'),
                    "name": name,
                    "email": email,
                    "status": "created",
                    "candidate_id": candidate_id,
                    "message": "New candidate created"
                })
                successful += 1
                
        except Exception as e:
            logger.error(f"[BULK SAVE] Error: {e}")
            results.append({
                "row_index": candidate_data.get('row_index'),
                "name": candidate_data.get('candidate_name') or candidate_data.get('name', 'Unknown'),
                "email": candidate_data.get('email'),
                "status": "failed",
                "candidate_id": None,
                "message": str(e)
            })
            failed += 1
    
    # Update batch status
    await db.bulk_import_batches.update_one(
        {"id": batch_id},
        {"$set": {
            "status": "completed",
            "completed_at": now,
            "results": {
                "successful": successful,
                "failed": failed,
                "duplicates_merged": duplicates_merged,
                "details": results
            }
        }}
    )
    
    return BulkSaveResponse(
        batch_id=batch_id,
        total_attempted=len(candidates),
        successful=successful,
        failed=failed,
        duplicates_merged=duplicates_merged,
        results=results
    )


# ============== ATTACH CV ENDPOINT ==============

@bulk_import_router.put("/attach-cv/{candidate_id}")
async def attach_cv_to_candidate(
    candidate_id: str,
    cv_file: UploadFile = File(..., description="CV file to attach (PDF, DOC, DOCX)"),
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Attach CV to a candidate that was imported via Excel (no CV initially).
    
    Only works for candidates with cv_attached=false.
    """
    # Find candidate
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Validate file type
    ext = Path(cv_file.filename).suffix.lower()
    if ext not in ['.pdf', '.doc', '.docx']:
        raise HTTPException(status_code=400, detail="CV must be PDF, DOC, or DOCX")
    
    # Upload to R2
    content = await cv_file.read()
    file_id = str(uuid.uuid4())
    r2_key = generate_r2_key("bulk-import-cv", cv_file.filename)
    
    content_type_map = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }
    content_type = content_type_map.get(ext, 'application/octet-stream')
    
    r2_result = await upload_to_r2(content, r2_key, content_type)
    
    # Generate fingerprint
    resume_text = extract_text_from_file(content, cv_file.filename)
    fingerprint = generate_resume_fingerprint(resume_text) if resume_text else None
    
    # Update candidate
    now = datetime.now(timezone.utc).isoformat()
    
    resume_version = {
        "id": file_id,
        "fingerprint": fingerprint,
        "uploaded_at": now,
        "uploaded_by": current_user["id"],
        "is_active": True,
        "r2_metadata": r2_result,
        "original_filename": cv_file.filename
    }
    
    existing_versions = candidate.get("resume_versions", [])
    existing_versions.append(resume_version)
    
    existing_fingerprints = candidate.get("resume_fingerprints", [])
    if fingerprint and fingerprint not in existing_fingerprints:
        existing_fingerprints.append(fingerprint)
    
    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$set": {
            "cv_attached": True,
            "active_resume_id": file_id,
            "resume_versions": existing_versions,
            "resume_fingerprints": existing_fingerprints,
            "updated_at": now,
            "last_updated_by": current_user["id"]
        }, "$push": {
            "profile_update_audit": {
                "action": "cv_attached",
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "by_role": "admin",
                "timestamp": now,
                "filename": cv_file.filename
            }
        }}
    )
    
    return {
        "success": True,
        "message": "CV attached successfully",
        "candidate_id": candidate_id,
        "resume_file_id": file_id
    }


# ============== UTILITY ENDPOINTS ==============

@bulk_import_router.get("/batches")
async def get_import_batches(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get list of all bulk import batches for audit"""
    batches = await db.bulk_import_batches.find(
        {},
        {"_id": 0, "candidates_preview": 0}
    ).sort("created_at", -1).to_list(100)
    
    return {"batches": batches}


@bulk_import_router.get("/batches/{batch_id}")
async def get_batch_details(
    batch_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get details of a specific import batch"""
    batch = await db.bulk_import_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    return batch


@bulk_import_router.get("/template")
async def download_template(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Download Excel template for bulk import (Excel-only mode)"""
    template_df = pd.DataFrame({
        'Candidate Name*': ['John Doe', 'Jane Smith'],
        'Contact No.*': ['9876543210', '9876543211'],
        'Email*': ['john.doe@example.com', 'jane.smith@example.com'],
        'Work Exp*': ['5Y 0 M', '3Y 6 M'],
        'Annual Salary*': ['12.0 L', '15.5 L'],
        'Current Location*': ['Bangalore', 'Mumbai'],
        'Current Employer*': ['Infosys Ltd', 'Tata Consultancy Services'],
        'Designation*': ['Senior Software Engineer', 'Business Analyst'],
        'U.G. Course*': ['B.Tech/B.E.', 'BBA'],
        'Industry*': ['Information Technology', ''],  # Empty = AI will detect
        'Age/Date of Birth*': ['28', '1995-05-15']
    })
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        template_df.to_excel(writer, index=False, sheet_name='Candidates')
    output.seek(0)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.document",
        headers={"Content-Disposition": "attachment; filename=bulk_import_template.xlsx"}
    )


@bulk_import_router.get("/restricted-candidates")
async def get_restricted_candidates(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get all bulk-imported candidates that are still restricted (admin-only)"""
    candidates = await db.candidate_bank.find(
        {"bulk_import_restricted": True},
        {"_id": 0}
    ).to_list(1000)
    
    return {
        "count": len(candidates),
        "candidates": candidates
    }


# ============== CHUNKED UPLOAD PROCESSING ENDPOINT ==============

@bulk_import_router.post("/cv-zip-chunked", response_model=CVZipParseResponse)
async def parse_cv_zip_from_chunked(
    upload_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Process a CV/ZIP file that was uploaded via chunked upload.
    
    This endpoint:
    1. Retrieves the completed upload by upload_id
    2. Processes the ZIP file (same as /cv-zip)
    3. Cleans up the temporary file after processing
    """
    # Get the completed upload
    upload = chunked_upload_service.get_upload_status(upload_id)
    
    if not upload:
        raise HTTPException(status_code=404, detail="Upload session not found")
    
    if upload.status != "completed":
        raise HTTPException(status_code=400, detail=f"Upload is not complete (status: {upload.status})")
    
    if not upload.file_path:
        raise HTTPException(status_code=400, detail="Upload file path not found")
    
    # Validate file type
    if not upload.filename.lower().endswith('.zip'):
        chunked_upload_service.cleanup_completed(upload_id)
        raise HTTPException(status_code=400, detail="File must be a .zip archive")
    
    batch_id = str(uuid.uuid4())
    candidates = []
    excel_files_found = 0
    excel_data_map = {}
    
    try:
        # Read the assembled file
        file_content = chunked_upload_service.get_file_content(upload_id)
        
        if not file_content:
            raise HTTPException(status_code=400, detail="Failed to read uploaded file")
        
        resume_files = []
        excel_files = []
        
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "upload.zip")
            with open(zip_path, 'wb') as f:
                f.write(file_content)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.is_dir():
                        continue
                    
                    filename = os.path.basename(file_info.filename)
                    ext = Path(filename).suffix.lower()
                    
                    with zip_ref.open(file_info) as f:
                        content = f.read()
                    
                    if ext in ['.pdf', '.doc', '.docx']:
                        resume_files.append((filename, content))
                    elif ext in ['.xlsx', '.xls', '.csv']:
                        excel_files.append((filename, content))
                        excel_files_found += 1
        
        if not resume_files:
            raise HTTPException(status_code=400, detail="No resume files (PDF, DOC, DOCX) found in ZIP")
        
        logger.info(f"[CV ZIP CHUNKED] Found {len(resume_files)} resumes, {excel_files_found} Excel files")
        
        # Parse Excel files for additional metadata
        for excel_name, excel_content in excel_files:
            try:
                ext = Path(excel_name).suffix.lower()
                if ext == '.csv':
                    df = pd.read_csv(io.BytesIO(excel_content))
                else:
                    df = pd.read_excel(io.BytesIO(excel_content))
                
                df.columns = [col.strip().rstrip('*').strip().rstrip('.').strip().lower().replace(' ', '_').replace('.', '_') for col in df.columns]
                
                for _, row in df.iterrows():
                    email = str(row.get('email', '')).strip().lower() if pd.notna(row.get('email')) else None
                    phone = normalize_phone(str(row.get('contact_no', row.get('phone', '')))) if pd.notna(row.get('contact_no', row.get('phone'))) else None
                    
                    data = {
                        'name': str(row.get('candidate_name', row.get('name', ''))).strip() if pd.notna(row.get('candidate_name', row.get('name'))) else None,
                        'email': email,
                        'phone': phone,
                        'location': str(row.get('current_location', row.get('location', ''))).strip() if pd.notna(row.get('current_location', row.get('location'))) else None,
                        'salary': parse_salary_string(str(row.get('annual_salary', row.get('salary', '')))),
                        'employer': str(row.get('current_employer', '')).strip() if pd.notna(row.get('current_employer')) else None,
                        'designation': str(row.get('designation', '')).strip() if pd.notna(row.get('designation')) else None,
                    }
                    
                    if email:
                        excel_data_map[email] = data
                    if phone:
                        excel_data_map[phone] = data
                        
            except Exception as e:
                logger.warning(f"[CV ZIP CHUNKED] Error parsing Excel {excel_name}: {e}")
        
        # Process each resume
        now = datetime.now(timezone.utc).isoformat()
        
        for idx, (filename, content) in enumerate(resume_files):
            try:
                candidate = CVCandidate(row_index=idx, filename=filename)
                
                # Upload to R2
                file_id = str(uuid.uuid4())
                r2_key = generate_r2_key("bulk-import-cv", filename)
                
                ext = Path(filename).suffix.lower()
                content_type_map = {
                    '.pdf': 'application/pdf',
                    '.doc': 'application/msword',
                    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                }
                content_type = content_type_map.get(ext, 'application/octet-stream')
                
                r2_result = await upload_to_r2(content, r2_key, content_type)
                candidate.resume_file_id = file_id
                candidate.r2_metadata = r2_result
                
                # Extract text and parse with AI
                resume_text = extract_text_from_file(content, filename)
                
                if resume_text:
                    # Generate fingerprint
                    candidate.resume_fingerprint = generate_resume_fingerprint(resume_text)
                    
                    # Parse with AI
                    if len(resume_text) > 100:
                        parsed = await parse_resume_with_ai(resume_text[:8000])
                        
                        if parsed.get('success') and parsed.get('data'):
                            data = parsed['data']
                            candidate.name = data.get('name')
                            candidate.email = data.get('email')
                            candidate.phone = data.get('phone')
                            candidate.location = data.get('location')
                            candidate.experience_years = data.get('experience_years', 0) or 0
                            candidate.skills = data.get('skills', [])
                            candidate.headline = data.get('headline')
                            candidate.summary = data.get('summary')
                            candidate.experience = data.get('experience', [])
                            candidate.education = data.get('education', [])
                        else:
                            candidate.warnings.append(f"AI parsing failed: {parsed.get('error', 'Unknown error')}")
                else:
                    candidate.warnings.append("Could not extract text from file")
                
                # Try to match with Excel data
                if candidate.email and candidate.email.lower() in excel_data_map:
                    candidate.excel_data = excel_data_map[candidate.email.lower()]
                elif candidate.phone:
                    phone_norm = normalize_phone(candidate.phone)
                    if phone_norm and phone_norm in excel_data_map:
                        candidate.excel_data = excel_data_map[phone_norm]
                
                # Validate
                if not candidate.name and not (candidate.excel_data and candidate.excel_data.get('name')):
                    candidate.validation_errors.append("Could not extract name from CV")
                
                if not candidate.email and not candidate.phone:
                    candidate.validation_errors.append("No email or phone found in CV")
                    candidate.is_valid = False
                
                candidates.append(candidate)
                
            except Exception as e:
                logger.error(f"[CV ZIP CHUNKED] Error processing {filename}: {e}")
                candidates.append(CVCandidate(
                    row_index=idx,
                    filename=filename,
                    is_valid=False,
                    validation_errors=[str(e)]
                ))
        
        valid_count = sum(1 for c in candidates if c.is_valid)
        
        # Store batch metadata
        batch_doc = {
            "id": batch_id,
            "mode": "cv_zip",
            "source": "chunked_upload",
            "upload_id": upload_id,
            "created_at": now,
            "created_by": current_user["id"],
            "created_by_name": current_user["name"],
            "total_files": len(candidates),
            "valid_files": valid_count,
            "invalid_files": len(candidates) - valid_count,
            "excel_files_found": excel_files_found,
            "status": "pending_review",
            "candidates_preview": [c.dict() for c in candidates]
        }
        await db.bulk_import_batches.insert_one(batch_doc)
        
        return CVZipParseResponse(
            batch_id=batch_id,
            total_files=len(candidates),
            valid_files=valid_count,
            invalid_files=len(candidates) - valid_count,
            candidates=candidates,
            excel_files_found=excel_files_found
        )
        
    finally:
        # Cleanup the chunked upload temporary file
        chunked_upload_service.cleanup_completed(upload_id)
