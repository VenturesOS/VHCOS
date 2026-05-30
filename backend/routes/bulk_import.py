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
import pandas as pd

# Import configuration
from config import db

# Import utilities
from utils import require_role

# Import services
from services.r2_storage import generate_r2_key, upload_to_r2
from services.matching_engine import parse_resume_with_ai, generate_resume_fingerprint

# Import Emergent LLM for industry detection (optional — falls back to direct OpenAI)
from services.matching_engine import _llm_chat

# Import chunked upload service
from services.chunked_upload import chunked_upload_service, CHUNK_SIZE, MAX_FILE_SIZE

# Import job queue for background processing
from services.job_queue import job_queue, JobType

# Import models
from models.bulk_import import (
    ChunkInitRequest, ChunkInitResponse,
    ExcelCandidate, CVCandidate,
    ExcelParseResponse, CVZipParseResponse, FileParseInfo,
    BulkSaveRequest, BulkSaveResponse,
    AttachCVRequest, AsyncCVParseRequest, AsyncCVParseResponse,
)

# Import service helpers
from services.bulk_import_service import (
    detect_industry_from_employer, parse_experience_string,
    parse_salary_string, normalize_phone,
    extract_text_from_file, merge_skills, merge_experience,
)

# Create router
bulk_import_router = APIRouter(prefix="/api/admin/bulk-import", tags=["Bulk Import"])

logger = logging.getLogger(__name__)


# ============== CHUNKED UPLOAD ENDPOINTS ==============


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


# ============== EXCEL-ONLY MODE ENDPOINTS ==============

@bulk_import_router.post("/excel", response_model=ExcelParseResponse)
async def parse_excel_only(
    excel_files: List[UploadFile] = File(..., description="One or more Excel/CSV files with candidate data (max 20)"),
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    MODE A: Excel-Only Import (Multi-file)
    
    Parse one or more Excel files and create candidate profiles WITHOUT CV.
    Supports up to 20 files at once. All candidates merged into a single preview.
    AI will detect industry from employer name if Industry column is empty.
    """
    if len(excel_files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files allowed per upload")
    
    batch_id = str(uuid.uuid4())
    all_candidates = []
    all_columns_found = []
    ai_industry_count = 0
    file_details = []
    global_row_idx = 0
    
    for file_num, excel_file in enumerate(excel_files):
        # Validate file type
        ext = Path(excel_file.filename).suffix.lower()
        if ext not in ['.xlsx', '.xls', '.csv']:
            logger.warning(f"[EXCEL PARSE] Skipping {excel_file.filename}: unsupported format")
            continue
        
        source_filename = excel_file.filename
        file_candidates = []
        
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
            
            # Merge columns (deduplicate)
            for col in original_cols:
                if col not in all_columns_found:
                    all_columns_found.append(col)
            
            logger.info(f"[EXCEL PARSE] File {file_num+1}/{len(excel_files)}: {source_filename} — {len(df)} rows, columns: {list(df.columns)}")
            
        except Exception as e:
            logger.error(f"[EXCEL PARSE] Error reading {source_filename}: {e}")
            file_details.append(FileParseInfo(filename=source_filename, rows=0, valid=0, columns_found=[]))
            continue
        
        # ── Column detection: maps each internal key to known column-name synonyms ──
        col_map = {
            'candidate_name': ['candidate_name', 'name', 'full_name', 'candidate', 'candidate name', 'applicant name'],
            'contact_no': ['contact_no', 'contact', 'phone', 'mobile', 'phone_number', 'phone number', 'contact number', 'mobile no', 'mobile number', 'contact no.'],
            'email': ['email', 'email_id', 'e-mail', 'mail', 'email id', 'email address', 'candidate email'],
            'work_exp': ['work_exp', 'experience', 'exp', 'work_experience', 'total_exp', 'total experience', 'total_experience', 'work experience', 'work exp.', 'yrs_of_exp', 'total exp'],
            'annual_salary': ['annual_salary', 'salary', 'ctc', 'current_salary', 'current_ctc', 'annual salary', 'current salary', 'annual ctc'],
            'current_location': ['current_location', 'location', 'city', 'current location', 'current city'],
            'current_employer': ['current_employer', 'employer', 'company', 'current_company', 'curr. company name', 'current company', 'company name', 'curr company name', 'organization'],
            'designation': ['curr. company designation', 'curr_company_designation', 'current designation', 'current_designation', 'designation', 'current position', 'current title'],
            'ug_course': ['ug_course', 'u_g_course', 'u_g__course', 'education', 'degree', 'qualification', 'under graduation degree', 'ug degree'],
            'industry': ['industry', 'sector', 'domain'],
            'age_dob': ['age/date_of_birth', 'age_date_of_birth', 'dob', 'date_of_birth', 'age', 'birth_date', 'date of birth'],
            'key_skills': ['key_skills', 'key skills', 'skills', 'skill set', 'skillset', 'technical skills'],
            'notice_period': ['notice_period', 'notice period', 'notice period/ availability to join', 'availability to join', 'notice'],
            'preferred_locations': ['preferred_locations', 'preferred locations', 'preferred location', 'preferred city'],
            'resume_headline': ['resume_headline', 'resume headline', 'headline', 'profile headline', 'profile title'],
            'summary': ['summary', 'profile summary', 'about', 'objective', 'career objective', 'professional summary'],
            'department': ['department', 'dept', 'function', 'functional area'],
            'role_category': ['role', 'functional role', 'role category', 'job role'],
            'gender': ['gender', 'sex'],
            'marital_status': ['marital_status', 'marital status'],
            'home_town': ['home_town', 'home town/city', 'home town', 'hometown'],
            'work_permit_usa': ['work_permit_usa', 'work permit for usa', 'work permit'],
            'naukri_job_title': ['job_title', 'job title', 'applied for', 'job applied'],
            'application_date': ['date_of_application', 'date of application', 'applied date', 'application date', 'apply date'],
            'candidate_source': ['source', 'candidate source', 'application source'],
            'candidate_profile': ['candidate_profile', 'candidate profile', 'naukri profile', 'profile url', 'naukri link'],
            'ug_specialization': ['ug_specialization', 'ug specialization', 'ug stream', 'ug branch'],
            'ug_university': ['ug_university', 'ug university/institute name', 'ug university', 'ug institute', 'ug college'],
            'ug_year': ['ug_year', 'ug graduation year', 'ug year', 'ug passing year'],
            'pg_degree': ['pg_degree', 'post graduation degree', 'pg degree', 'post graduation', 'pg course'],
            'pg_specialization': ['pg_specialization', 'pg specialization', 'pg stream', 'pg branch'],
            'pg_university': ['pg_university', 'pg university/institute name', 'pg university', 'pg institute', 'pg college'],
            'pg_year': ['pg_year', 'pg graduation year', 'pg year', 'pg passing year'],
            'doc_degree': ['doc_degree', 'doctorate degree', 'phd degree', 'doctorate'],
            'doc_specialization': ['doc_specialization', 'doctorate specialization', 'phd specialization'],
            'doc_university': ['doc_university', 'doctorate university/institute name', 'doctorate university', 'phd university'],
            'doc_year': ['doc_year', 'doctorate graduation year', 'doctorate year', 'phd year'],
        }
        
        def find_column(df, key):
            """Fuzzy column matcher: exact → normalized → contains"""
            synonyms = col_map.get(key, [key])
            df_cols_lower = {c.lower().strip(): c for c in df.columns}
            df_cols_norm = {c.lower().strip().replace(' ', '_').replace('.', '_'): c for c in df.columns}
            for possible in synonyms:
                if possible in df.columns:
                    return possible
                p_lower = possible.lower()
                p_norm = p_lower.replace(' ', '_').replace('.', '_')
                if p_lower in df_cols_lower:
                    return df_cols_lower[p_lower]
                if p_norm in df_cols_norm:
                    return df_cols_norm[p_norm]
            for possible in synonyms:
                p_norm = possible.lower().replace(' ', '_')
                for col_norm, col_orig in df_cols_norm.items():
                    if p_norm in col_norm or col_norm in p_norm:
                        return col_orig
            return None
        
        # Build column mapping summary
        detected_mapping = {}
        for key in col_map:
            col = find_column(df, key)
            if col:
                detected_mapping[key] = col

        for idx, row in df.iterrows():
            try:
                candidate = ExcelCandidate(row_index=global_row_idx, candidate_name="Unknown", source_file=source_filename)
                missing_mandatory = []
                
                def get_val(key):
                    col = find_column(df, key)
                    if col and pd.notna(row.get(col)):
                        return str(row[col]).strip()
                    return None
                
                name = get_val('candidate_name')
                if not name:
                    missing_mandatory.append('Candidate Name')
                    name = "Unknown"
                candidate.candidate_name = name
                
                contact = get_val('contact_no')
                if not contact:
                    missing_mandatory.append('Contact No.')
                candidate.contact_no = contact
                candidate.phone_normalized = normalize_phone(contact)
                
                email = get_val('email')
                if not email:
                    missing_mandatory.append('Email')
                candidate.email = email
                
                work_exp = get_val('work_exp')
                if not work_exp:
                    missing_mandatory.append('Work Exp')
                candidate.work_exp = work_exp
                candidate.experience_years = parse_experience_string(work_exp)
                
                salary = get_val('annual_salary')
                if not salary:
                    missing_mandatory.append('Annual Salary')
                candidate.annual_salary = salary
                candidate.salary_inr = parse_salary_string(salary)
                
                location = get_val('current_location')
                if not location:
                    missing_mandatory.append('Current Location')
                candidate.current_location = location
                
                employer = get_val('current_employer')
                if not employer:
                    missing_mandatory.append('Current Employer')
                candidate.current_employer = employer
                
                designation = get_val('designation')
                if not designation:
                    missing_mandatory.append('Designation')
                candidate.designation = designation
                
                ug_course = get_val('ug_course')
                if not ug_course:
                    missing_mandatory.append('U.G. Course')
                candidate.ug_course = ug_course
                
                industry = get_val('industry')
                if industry:
                    candidate.industry = industry
                    candidate.industry_source = "excel"
                elif employer:
                    detected = await detect_industry_from_employer(employer)
                    if detected:
                        candidate.industry = detected
                        candidate.industry_source = "ai_detected"
                        ai_industry_count += 1
                    else:
                        missing_mandatory.append('Industry')
                else:
                    missing_mandatory.append('Industry')
                
                age_dob = get_val('age_dob')
                if not age_dob:
                    missing_mandatory.append('Age/Date of Birth')
                candidate.age_dob = age_dob
                
                naukri_data = {}
                for nk in ('key_skills', 'notice_period', 'preferred_locations', 'resume_headline',
                            'summary', 'department', 'role_category', 'gender', 'marital_status',
                            'home_town', 'work_permit_usa', 'naukri_job_title', 'application_date',
                            'candidate_source', 'candidate_profile',
                            'ug_specialization', 'ug_university', 'ug_year',
                            'pg_degree', 'pg_specialization', 'pg_university', 'pg_year',
                            'doc_degree', 'doc_specialization', 'doc_university', 'doc_year'):
                    val = get_val(nk)
                    if val:
                        naukri_data[nk] = val
                candidate.naukri_data = naukri_data
                
                candidate.missing_mandatory = missing_mandatory
                if missing_mandatory:
                    candidate.warnings.append(f"Missing mandatory fields will be marked as 'Unknown': {', '.join(missing_mandatory)}")
                
                if not candidate.email and not candidate.phone_normalized:
                    candidate.validation_errors.append("Either email or phone is required")
                    candidate.is_valid = False
                
                file_candidates.append(candidate)
                global_row_idx += 1
                
            except Exception as e:
                logger.error(f"[EXCEL PARSE] Error on row {idx} in {source_filename}: {e}")
                file_candidates.append(ExcelCandidate(
                    row_index=global_row_idx,
                    candidate_name=f"Row {idx} Error",
                    source_file=source_filename,
                    is_valid=False,
                    validation_errors=[str(e)]
                ))
                global_row_idx += 1
        
        file_valid = sum(1 for c in file_candidates if c.is_valid)
        file_details.append(FileParseInfo(
            filename=source_filename,
            rows=len(file_candidates),
            valid=file_valid,
            columns_found=original_cols
        ))
        all_candidates.extend(file_candidates)
    
    if not all_candidates:
        raise HTTPException(status_code=400, detail="No valid Excel files found. Supported: .xlsx, .xls, .csv")
    
    valid_count = sum(1 for c in all_candidates if c.is_valid)
    
    # Store batch metadata
    now = datetime.now(timezone.utc).isoformat()
    batch_doc = {
        "id": batch_id,
        "mode": "excel",
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user["name"],
        "total_rows": len(all_candidates),
        "valid_rows": valid_count,
        "invalid_rows": len(all_candidates) - valid_count,
        "ai_industry_detected": ai_industry_count,
        "files_parsed": len(file_details),
        "file_details": [fd.dict() for fd in file_details],
        "status": "pending_review",
        "candidates_preview": [c.dict() for c in all_candidates]
    }
    await db.bulk_import_batches.insert_one(batch_doc)
    
    return ExcelParseResponse(
        batch_id=batch_id,
        total_rows=len(all_candidates),
        valid_rows=valid_count,
        invalid_rows=len(all_candidates) - valid_count,
        candidates=all_candidates,
        columns_found=all_columns_found,
        ai_industry_detected=ai_industry_count,
        files_parsed=len(file_details),
        file_details=file_details
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
                        # Security: validate each file inside ZIP
                        from services.security_service import scan_for_threats
                        _threats = scan_for_threats(content, filename)
                        if _threats:
                            logger.warning(f"[CV ZIP] Skipping malicious file: {filename} — {_threats}")
                            continue
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
            
            # Check for existing candidate (cross-source deduplication)
            existing = None
            # Case-insensitive email match — older records may have stored
            # email in mixed case, defeating the strict `.lower()` lookup.
            if email:
                import re as _re_em
                existing = await db.candidate_bank.find_one(
                    {"email": _re_em.compile(f"^{_re_em.escape(email)}$", _re_em.IGNORECASE)},
                    {"_id": 0},
                )
            if not existing and phone:
                # Match on phone_normalized OR raw phone — legacy records may
                # have phone populated but phone_normalized null/empty.
                existing = await db.candidate_bank.find_one(
                    {"$or": [
                        {"phone_normalized": phone},
                        {"phone": phone},
                    ]},
                    {"_id": 0},
                )
            # Fallback: Naukri profile URL match (only real URLs, skip "View profile" etc.)
            if not existing and mode == "excel":
                naukri_url = (candidate_data.get('naukri_data') or {}).get('candidate_profile')
                if naukri_url and naukri_url.startswith('http'):
                    existing = await db.candidate_bank.find_one({"naukri_profile_url": naukri_url}, {"_id": 0})
            
            if existing:
                # COMPREHENSIVE CROSS-SOURCE MERGE
                update_fields = {
                    "updated_at": now,
                    "last_updated_by": current_user["id"],
                }
                merge_details = []

                if mode == "excel":
                    nd = candidate_data.get('naukri_data') or {}
                    new_phone = candidate_data.get('contact_no')
                    new_phone_norm = normalize_phone(new_phone) if new_phone else None
                    new_email = email
                    new_location = candidate_data.get('current_location')
                    new_employer = candidate_data.get('current_employer')
                    new_designation = candidate_data.get('designation')
                    new_industry = candidate_data.get('industry')
                    new_headline = nd.get('resume_headline') or new_designation
                    new_summary = nd.get('summary')
                    new_notice = nd.get('notice_period')
                    new_salary = candidate_data.get('salary_inr')
                    new_skills = [s.strip() for s in str(nd.get('key_skills', '')).split(',') if s.strip()] if nd.get('key_skills') else []
                    new_dob = candidate_data.get('age_dob')
                    new_gender = nd.get('gender')
                    raw_naukri_url = nd.get('candidate_profile')
                    new_naukri_url = raw_naukri_url if raw_naukri_url and raw_naukri_url.startswith('http') else None
                    new_naukri_job_title = nd.get('naukri_job_title')
                    new_app_date = nd.get('application_date')
                    # Build education
                    new_education = []
                    if candidate_data.get('ug_course'):
                        edu = {"degree": candidate_data['ug_course'], "level": "UG"}
                        if nd.get('ug_specialization'): edu["specialization"] = nd['ug_specialization']
                        if nd.get('ug_university'): edu["institution"] = nd['ug_university']
                        if nd.get('ug_year'): edu["year"] = str(nd['ug_year'])
                        new_education.append(edu)
                    if nd.get('pg_degree'):
                        edu = {"degree": nd['pg_degree'], "level": "PG"}
                        if nd.get('pg_specialization'): edu["specialization"] = nd['pg_specialization']
                        if nd.get('pg_university'): edu["institution"] = nd['pg_university']
                        if nd.get('pg_year'): edu["year"] = str(nd['pg_year'])
                        new_education.append(edu)
                else:
                    new_phone = candidate_data.get('phone')
                    new_phone_norm = phone
                    new_email = email
                    new_location = candidate_data.get('location') or (candidate_data.get('excel_data') or {}).get('location')
                    new_employer = candidate_data.get('current_employer')
                    new_designation = candidate_data.get('designation')
                    new_industry = candidate_data.get('industry')
                    new_headline = candidate_data.get('headline')
                    new_summary = candidate_data.get('summary')
                    new_notice = None
                    new_salary = candidate_data.get('current_salary') or (candidate_data.get('excel_data') or {}).get('salary')
                    new_skills = candidate_data.get('skills', [])
                    new_education = candidate_data.get('education', [])
                    new_dob = None
                    new_gender = None
                    new_naukri_url = None
                    new_naukri_job_title = None
                    new_app_date = None
                    nd = {}

                # --- Fill-if-missing fields (never overwrite existing non-null) ---
                fill_fields = {
                    "phone": new_phone,
                    "phone_normalized": new_phone_norm,
                    "email": new_email.lower() if new_email else None,
                    "location": new_location,
                    "current_employer": new_employer,
                    "designation": new_designation,
                    "industry": new_industry,
                    "headline": new_headline,
                    "summary": new_summary,
                    "notice_period": new_notice,
                    "date_of_birth": new_dob,
                    "gender": new_gender,
                    "naukri_profile_url": new_naukri_url,
                    "naukri_job_title": new_naukri_job_title,
                    "application_date": new_app_date,
                }
                for field, new_val in fill_fields.items():
                    if new_val and not existing.get(field):
                        update_fields[field] = new_val
                        merge_details.append(field)

                # Salary: Use higher value
                if new_salary and (not existing.get('current_salary') or new_salary > existing.get('current_salary', 0)):
                    update_fields["current_salary"] = new_salary

                # Skills: Merge (union)
                existing_skills = existing.get('skills', [])
                if new_skills:
                    update_fields["skills"] = merge_skills(existing_skills, new_skills)

                # Experience: Merge
                existing_exp = existing.get('experience', [])
                new_exp = candidate_data.get('experience', [])
                if new_exp:
                    merged_exp = merge_experience(existing_exp, new_exp)
                    update_fields["experience"] = merged_exp
                    if merged_exp and merged_exp[0].get('location') and not existing.get('location'):
                        update_fields["location"] = merged_exp[0].get('location')

                # Education: Merge by level (don't duplicate UG/PG/Doc)
                existing_edu = existing.get('education', [])
                if new_education and existing_edu:
                    existing_levels = {e.get('level', '').upper() for e in existing_edu}
                    for new_edu in new_education:
                        if new_edu.get('level', '').upper() not in existing_levels:
                            existing_edu.append(new_edu)
                            merge_details.append(f"education_{new_edu.get('level')}")
                    update_fields["education"] = existing_edu
                elif new_education and not existing_edu:
                    update_fields["education"] = new_education
                    merge_details.append("education")

                # Naukri data: Deep merge (fill missing keys)
                if mode == "excel" and nd:
                    existing_nd = existing.get('naukri_data') or {}
                    for k, v in nd.items():
                        if v and not existing_nd.get(k):
                            existing_nd[k] = v
                    update_fields["naukri_data"] = existing_nd

                # Preferred locations: Merge
                new_pref = [l.strip() for l in str(nd.get('preferred_locations', '')).split(',') if l.strip()] if nd.get('preferred_locations') else []
                if new_pref:
                    existing_pref = set(existing.get('preferred_locations', []))
                    merged_pref = list(existing_pref | set(new_pref))
                    if len(merged_pref) > len(existing_pref):
                        update_fields["preferred_locations"] = merged_pref

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

                # Track source in audit trail
                source_label = "naukri_excel" if mode == "excel" else "cv_zip"
                audit_entry = {
                    "action": f"cross_source_merge_{source_label}",
                    "mode": source_label,
                    "by_id": current_user["id"],
                    "by_name": current_user["name"],
                    "by_role": current_user.get("role", "admin"),
                    "timestamp": now,
                    "batch_id": batch_id,
                    "fields_merged": merge_details,
                    "source_file": candidate_data.get('source_file') or candidate_data.get('filename'),
                }
                if new_naukri_job_title:
                    audit_entry["naukri_job_title"] = new_naukri_job_title

                # Update
                await db.candidate_bank.update_one(
                    {"id": existing["id"]},
                    {
                        "$set": update_fields,
                        "$push": {"profile_update_audit": audit_entry}
                    }
                )

                merge_msg = f"Merged {len(merge_details)} fields" if merge_details else "Enriched (skills/salary/experience)"
                results.append({
                    "row_index": candidate_data.get('row_index'),
                    "name": name,
                    "email": email,
                    "status": "merged",
                    "candidate_id": existing["id"],
                    "message": f"Cross-source merge: {merge_msg}",
                    "fields_merged": merge_details,
                })
                successful += 1
                duplicates_merged += 1
                
            else:
                # CREATE new candidate
                candidate_id = str(uuid.uuid4())
                
                if mode == "excel":
                    # Extract Naukri-rich data
                    nd = candidate_data.get('naukri_data') or {}
                    
                    # Build skills from key_skills
                    skills = []
                    raw_skills = nd.get('key_skills', '')
                    if raw_skills:
                        skills = [s.strip() for s in str(raw_skills).split(',') if s.strip()]
                    
                    # Build structured education array
                    education = []
                    if candidate_data.get('ug_course'):
                        edu = {"degree": candidate_data['ug_course'], "level": "UG"}
                        if nd.get('ug_specialization'): edu["specialization"] = nd['ug_specialization']
                        if nd.get('ug_university'): edu["institution"] = nd['ug_university']
                        if nd.get('ug_year'): edu["year"] = str(nd['ug_year'])
                        education.append(edu)
                    if nd.get('pg_degree'):
                        edu = {"degree": nd['pg_degree'], "level": "PG"}
                        if nd.get('pg_specialization'): edu["specialization"] = nd['pg_specialization']
                        if nd.get('pg_university'): edu["institution"] = nd['pg_university']
                        if nd.get('pg_year'): edu["year"] = str(nd['pg_year'])
                        education.append(edu)
                    if nd.get('doc_degree'):
                        edu = {"degree": nd['doc_degree'], "level": "Doctorate"}
                        if nd.get('doc_specialization'): edu["specialization"] = nd['doc_specialization']
                        if nd.get('doc_university'): edu["institution"] = nd['doc_university']
                        if nd.get('doc_year'): edu["year"] = str(nd['doc_year'])
                        education.append(edu)
                    
                    candidate_doc = {
                        "id": candidate_id,
                        "email": email.lower() if email else None,
                        "name": name,
                        "phone": candidate_data.get('contact_no'),
                        "phone_normalized": phone,
                        "headline": nd.get('resume_headline') or candidate_data.get('designation'),
                        "summary": nd.get('summary'),
                        "skills": skills,
                        "experience_years": candidate_data.get('experience_years', 0),
                        "experience": [],
                        "education": education,
                        "location": candidate_data.get('current_location'),
                        "certifications": [],
                        "active_resume_id": None,
                        "resume_versions": [],
                        "resume_fingerprints": [],
                        "resume_url": None,
                        "current_salary": candidate_data.get('salary_inr'),
                        "notice_period": nd.get('notice_period'),
                        "preferred_locations": [l.strip() for l in str(nd.get('preferred_locations', '')).split(',') if l.strip()] if nd.get('preferred_locations') else [],
                        # Source & metadata
                        "source": "naukri_excel_import",
                        "source_file": candidate_data.get('source_file'),
                        "bulk_import_type": "excel",
                        "bulk_import_restricted": True,
                        "cv_attached": False,
                        "industry": candidate_data.get('industry'),
                        "industry_source": candidate_data.get('industry_source'),
                        "current_employer": candidate_data.get('current_employer'),
                        "designation": candidate_data.get('designation'),
                        "department": nd.get('department'),
                        "role_category": nd.get('role_category'),
                        "ug_course": candidate_data.get('ug_course'),
                        "date_of_birth": candidate_data.get('age_dob'),
                        "gender": nd.get('gender'),
                        "marital_status": nd.get('marital_status'),
                        "home_town": nd.get('home_town'),
                        "naukri_profile_url": nd.get('candidate_profile') if nd.get('candidate_profile', '').startswith('http') else None,
                        "naukri_job_title": nd.get('naukri_job_title'),
                        "application_date": nd.get('application_date'),
                        "naukri_data": nd,  # Store full naukri data for reference
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
                            "mode": "naukri_excel",
                            "by_id": current_user["id"],
                            "by_name": current_user["name"],
                            "by_role": "admin",
                            "timestamp": now,
                            "batch_id": batch_id,
                            "naukri_job_title": nd.get('naukri_job_title'),
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
                
                # Auto-merge check before insert
                from services.candidate_merge import find_merge_candidate, merge_profiles, log_merge_audit
                _merge_target = await find_merge_candidate(name=name, email=email, phone=candidate_data.get('phone'))
                if _merge_target:
                    _merge_updates = merge_profiles(_merge_target, candidate_doc)
                    if _merge_updates:
                        await db.candidate_bank.update_one({"id": _merge_target["id"]}, {"$set": _merge_updates})
                        await log_merge_audit(_merge_target["id"], candidate_doc, _merge_updates, merged_by=current_user.get("email", "system"))
                        results.append({
                            "row_index": candidate_data.get('row_index'),
                            "name": name, "email": email,
                            "status": "merged",
                            "candidate_id": _merge_target["id"],
                            "message": f"Auto-merged with existing record '{_merge_target.get('name')}'"
                        })
                        successful += 1
                        continue

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
    current_user: dict = Depends(require_role(["admin", "recruiter", "employer"]))
):
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

    # Security: validate file content (magic bytes + threat scan)
    from services.security_service import validate_upload as _sec_validate
    sec_check = await _sec_validate(content, cv_file.filename, current_user.get("email", "internal"))
    if not sec_check["valid"]:
        raise HTTPException(status_code=400, detail=sec_check["reason"])
    file_id = str(uuid.uuid4())
    r2_key = generate_r2_key("bulk-import-cv", cv_file.filename)

    content_type_map = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }
    content_type = content_type_map.get(ext, 'application/octet-stream')

    try:
        r2_result = await upload_to_r2(content, r2_key, content_type)
    except Exception as e:
        logger.error(f"[attach-cv] R2 upload failed for {candidate_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {str(e)[:200]}")

    # Generate fingerprint — run blocking PDF parse off the event loop
    import asyncio as _aio
    try:
        loop = _aio.get_event_loop()
        resume_text = await loop.run_in_executor(
            None, extract_text_from_file, content, cv_file.filename
        )
    except Exception as e:
        logger.warning(f"[attach-cv] text extraction failed (non-fatal): {e}")
        resume_text = None
    fingerprint = generate_resume_fingerprint(resume_text) if resume_text else None

    # ── Parse CV with AI and smart-merge into candidate profile ──
    # "Smart-merge" = fill blank/missing fields only. Never overwrite what the
    # user has already edited. Also extend skills/education/experience arrays.
    parsed_updates: dict = {}
    if resume_text and len(resume_text.strip()) > 30:
        try:
            parse_result = await parse_resume_with_ai(resume_text[:8000])
            if parse_result.get("success"):
                parsed = parse_result["data"] or {}
                # Scalar fields — fill ONLY when candidate value is empty/null/0
                _scalar_map = [
                    "name", "email", "phone", "phone_normalized",
                    "headline", "summary", "location",
                    "current_employer", "current_company", "current_designation", "designation",
                    "current_industry", "industry", "current_department",
                    "experience_years", "total_experience_years",
                    "current_salary", "current_ctc", "expected_salary", "expected_ctc",
                    "notice_period", "notice_period_days",
                    "date_of_birth", "gender", "marital_status",
                    "profile_summary",
                ]
                for k in _scalar_map:
                    v = parsed.get(k)
                    if v in (None, "", 0, 0.0):
                        continue
                    if candidate.get(k) in (None, "", 0, 0.0):
                        parsed_updates[k] = v

                # Array fields — merge-dedupe (skills, preferred_locations, certifications, languages)
                for k in ("skills", "key_skills", "preferred_locations", "certifications", "languages"):
                    v = parsed.get(k)
                    if not isinstance(v, list) or not v:
                        continue
                    existing = candidate.get(k) or []
                    if not isinstance(existing, list):
                        existing = []
                    # Case-insensitive dedupe for strings, passthrough for dicts
                    seen = {s.lower() if isinstance(s, str) else id(s) for s in existing}
                    for item in v:
                        key = item.lower() if isinstance(item, str) else id(item)
                        if key not in seen:
                            existing.append(item)
                            seen.add(key)
                    parsed_updates[k] = existing

                # Array-of-objects — replace only if candidate has none (preserves
                # manually curated work_experience / education entries).
                for k in ("work_experience", "experience", "education"):
                    v = parsed.get(k)
                    if isinstance(v, list) and v and not candidate.get(k):
                        parsed_updates[k] = v
            else:
                logger.warning(f"[attach-cv] AI parse failed: {parse_result.get('error')}")
        except Exception as _p_err:
            logger.warning(f"[attach-cv] AI parse threw (non-fatal): {_p_err}")

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

    _set_payload = {
        "cv_attached": True,
        "active_resume_id": file_id,
        "resume_versions": existing_versions,
        "resume_fingerprints": existing_fingerprints,
        "updated_at": now,
        "last_updated_by": current_user["id"]
    }
    # Layer AI-parsed field backfill on top (only blanks were filled)
    _set_payload.update(parsed_updates)

    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$set": _set_payload,
        "$push": {
            "profile_update_audit": {
                "action": "cv_attached",
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "by_role": "admin",
                "timestamp": now,
                "filename": cv_file.filename,
                "fields_enriched": sorted(list(parsed_updates.keys())),
            }
        }}
    )

    return {
        "success": True,
        "candidate_id": candidate_id,
        "file_id": file_id,
        "filename": cv_file.filename,
        "cv_attached": True,
        "fields_enriched": sorted(list(parsed_updates.keys())),
        "enrichment_count": len(parsed_updates),
    }
    



# ============== ASYNC/BACKGROUND CV PARSING ==============


@bulk_import_router.post("/cv-zip-async", response_model=AsyncCVParseResponse)
async def parse_cv_zip_async(
    request: AsyncCVParseRequest,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Start background CV parsing job for large ZIP uploads.
    
    Use this instead of /cv-zip-chunked when:
    - ZIP contains 50+ resumes
    - You don't want to wait for synchronous processing
    - You need progress tracking
    
    Flow:
    1. Client uploads ZIP via /chunk/init, /chunk/upload, /chunk/complete
    2. Client calls this endpoint with upload_id
    3. Background job parses all CVs and creates candidates
    4. Client polls /background-jobs/{job_id} for status
    """
    # Validate upload exists and is complete
    upload = chunked_upload_service.get_upload_status(request.upload_id)
    
    if not upload:
        raise HTTPException(status_code=404, detail="Upload session not found")
    
    if upload.status != "completed":
        raise HTTPException(status_code=400, detail=f"Upload is not complete (status: {upload.status})")
    
    if not upload.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")
    
    # Create batch record
    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    batch_doc = {
        "id": batch_id,
        "mode": "cv_zip_async",
        "source": "background_job",
        "upload_id": request.upload_id,
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user["name"],
        "status": "processing",
        "excel_data_provided": bool(request.excel_data)
    }
    await db.bulk_import_batches.insert_one(batch_doc)
    
    # Create background job
    job = await job_queue.enqueue_job(
        job_type=JobType.BULK_IMPORT,
        input_data={
            "upload_id": request.upload_id,
            "batch_id": batch_id,
            "excel_data_map": request.excel_data or {}
        },
        created_by=current_user["id"]
    )
    
    logger.info(f"[CV ZIP ASYNC] Started background job {job.id} for batch {batch_id}")
    
    return AsyncCVParseResponse(
        job_id=job.id,
        batch_id=batch_id,
        status_url=f"/api/background-jobs/{job.id}",
        message=f"Background CV parsing started. Poll status at /api/background-jobs/{job.id}"
    )


@bulk_import_router.get("/batch/{batch_id}/status")
async def get_batch_status(
    batch_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get the status of a bulk import batch"""
    batch = await db.bulk_import_batches.find_one({"id": batch_id}, {"_id": 0})
    
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    # Get candidate count for this batch
    candidate_count = await db.candidate_bank.count_documents({"bulk_import_batch_id": batch_id})
    
    return {
        **batch,
        "candidates_created": candidate_count
    }


@bulk_import_router.get("/batch/{batch_id}/candidates")
async def get_batch_candidates(
    batch_id: str,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get candidates created from a specific batch"""
    batch = await db.bulk_import_batches.find_one({"id": batch_id}, {"_id": 0})
    
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    candidates = await db.candidate_bank.find(
        {"bulk_import_batch_id": batch_id},
        {"_id": 0, "embedding": 0}  # Exclude large fields
    ).skip(skip).limit(limit).to_list(limit)
    
    total = await db.candidate_bank.count_documents({"bulk_import_batch_id": batch_id})
    
    return {
        "batch_id": batch_id,
        "total": total,
        "skip": skip,
        "limit": limit,
        "candidates": candidates
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
                        from services.security_service import scan_for_threats
                        _threats = scan_for_threats(content, filename)
                        if _threats:
                            logger.warning(f"[CV ZIP CHUNKED] Skipping malicious file: {filename} — {_threats}")
                            continue
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



# ═══════════════════════════════════════
# BULK CV ATTACH QUEUE
# ═══════════════════════════════════════

@bulk_import_router.post("/bulk-attach-cv")
async def bulk_attach_cv(
    files: List[UploadFile] = File(..., description="Multiple CV files to match and attach"),
    current_user: dict = Depends(require_role(["admin", "recruiter"]))
):
    """
    Upload multiple CVs at once. Each CV is matched to existing candidates
    by name extracted from the file. Processes in batches to prevent server overload.
    
    Accepts up to 30 files per request. Returns match results for each file.
    """
    if len(files) > 30:
        raise HTTPException(status_code=400, detail="Maximum 30 files per batch. Split into multiple uploads.")

    results = []
    matched = 0
    failed = 0
    import asyncio as _aio
    import re
    sem = _aio.Semaphore(3)  # Process 3 files concurrently

    async def process_file(cv_file):
        nonlocal matched, failed
        async with sem:
            try:
                ext = Path(cv_file.filename).suffix.lower()
                if ext not in ['.pdf', '.doc', '.docx']:
                    return {"filename": cv_file.filename, "status": "skipped", "reason": "Invalid file type"}

                content = await cv_file.read()
                if len(content) > 10 * 1024 * 1024:  # 10MB limit
                    return {"filename": cv_file.filename, "status": "skipped", "reason": "File too large (>10MB)"}

                # Extract text to find candidate name
                resume_text = extract_text_from_file(content, cv_file.filename)
                if not resume_text or len(resume_text.strip()) < 20:
                    return {"filename": cv_file.filename, "status": "failed", "reason": "Could not extract text"}

                # Try to match by filename first (common pattern: "FirstName LastName.pdf")
                name_from_file = Path(cv_file.filename).stem.replace("_", " ").replace("-", " ").strip()

                # Search for candidate by name from filename
                candidate = None
                if name_from_file and len(name_from_file) > 2:
                    candidate = await db.candidate_bank.find_one(
                        {"name": {"$regex": f"^{name_from_file}$", "$options": "i"}},
                        {"_id": 0, "id": 1, "name": 1}
                    )

                # If no match by filename, try phone/email from text
                if not candidate:
                    import re
                    phone_match = re.search(r'\b(\d{10})\b', resume_text[:2000])
                    if phone_match:
                        candidate = await db.candidate_bank.find_one(
                            {"phone": {"$regex": phone_match.group(1)}},
                            {"_id": 0, "id": 1, "name": 1}
                        )

                if not candidate:
                    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', resume_text[:2000])
                    if email_match:
                        candidate = await db.candidate_bank.find_one(
                            {"email": {"$regex": f"^{email_match.group(0)}$", "$options": "i"}},
                            {"_id": 0, "id": 1, "name": 1}
                        )

                if not candidate:
                    failed += 1
                    return {"filename": cv_file.filename, "status": "no_match", "reason": f"No candidate found matching '{name_from_file}'"}

                # Upload to R2 and attach
                file_id = str(uuid.uuid4())
                r2_key = generate_r2_key("bulk-cv-attach", cv_file.filename)
                content_type_map = {'.pdf': 'application/pdf', '.doc': 'application/msword', '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
                r2_result = await upload_to_r2(content, r2_key, content_type_map.get(ext, 'application/octet-stream'))

                fingerprint = generate_resume_fingerprint(resume_text) if resume_text else None
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

                await db.candidate_bank.update_one(
                    {"id": candidate["id"]},
                    {
                        "$set": {
                            "cv_attached": True,
                            "active_resume_id": file_id,
                            "resume_url": r2_result.get("url", ""),
                            "updated_at": now,
                        },
                        "$push": {
                            "resume_versions": resume_version,
                            "profile_update_audit": {
                                "action": "bulk_cv_attached",
                                "by_id": current_user["id"],
                                "by_name": current_user.get("name", ""),
                                "timestamp": now,
                                "filename": cv_file.filename
                            }
                        }
                    }
                )
                if fingerprint:
                    await db.candidate_bank.update_one(
                        {"id": candidate["id"]},
                        {"$addToSet": {"resume_fingerprints": fingerprint}}
                    )

                matched += 1
                return {"filename": cv_file.filename, "status": "attached", "candidate_name": candidate.get("name"), "candidate_id": candidate["id"]}

            except Exception as e:
                failed += 1
                logger.error(f"[BulkCVAttach] Error processing {cv_file.filename}: {e}")
                return {"filename": cv_file.filename, "status": "error", "reason": str(e)[:200]}

    import asyncio as _asyncio
    tasks = [process_file(f) for f in files]
    results = await _asyncio.gather(*tasks)

    return {
        "total": len(files),
        "matched": matched,
        "failed": failed,
        "no_match": len(files) - matched - failed,
        "results": results,
    }
