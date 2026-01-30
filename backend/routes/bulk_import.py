"""
VHC Talent OS - Bulk Import Routes
Admin-only tool for controlled production-grade candidate data seeding.

STRICT RULES:
- NO direct MongoDB writes
- Uses existing candidate-bank batch save logic
- All imports are traceable via import_batch_id
- Soft validation with detailed error reporting
"""
import uuid
import logging
import zipfile
import tempfile
import os
import io
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
import pandas as pd
import aiofiles

# Import configuration
from config import db, UPLOAD_DIR

# Import utilities
from utils import require_role

# Import services
from services.r2_storage import generate_r2_key, upload_to_r2
from services.matching_engine import parse_resume_with_ai, generate_resume_fingerprint

# Create router
bulk_import_router = APIRouter(prefix="/api/admin/bulk-import", tags=["Bulk Import"])

logger = logging.getLogger(__name__)


# ============== PYDANTIC MODELS ==============

class BulkImportCandidate(BaseModel):
    """Single candidate from bulk import - for review stage"""
    row_index: int
    # From Excel
    excel_name: str
    excel_email: Optional[str] = None
    excel_phone: Optional[str] = None
    excel_location: Optional[str] = None
    excel_experience_years: Optional[int] = None
    excel_skills: List[str] = []
    excel_current_salary: Optional[int] = None
    excel_notice_period: Optional[str] = None
    resume_filename: Optional[str] = None
    # From Resume Parsing
    parsed_name: Optional[str] = None
    parsed_email: Optional[str] = None
    parsed_phone: Optional[str] = None
    parsed_location: Optional[str] = None
    parsed_experience_years: Optional[int] = None
    parsed_skills: List[str] = []
    parsed_headline: Optional[str] = None
    parsed_summary: Optional[str] = None
    parsed_experience: List[dict] = []
    parsed_education: List[dict] = []
    # Merged/Final data (Excel takes priority)
    final_name: str
    final_email: Optional[str] = None
    final_phone: Optional[str] = None
    final_location: Optional[str] = None
    final_experience_years: int = 0
    final_skills: List[str] = []
    final_current_salary: Optional[int] = None
    final_notice_period: Optional[str] = None
    final_headline: Optional[str] = None
    final_summary: Optional[str] = None
    final_experience: List[dict] = []
    final_education: List[dict] = []
    # Metadata
    resume_file_id: Optional[str] = None
    resume_fingerprint: Optional[str] = None
    r2_metadata: Optional[dict] = None
    # Validation
    is_valid: bool = True
    validation_errors: List[str] = []
    warnings: List[str] = []


class BulkImportParseResponse(BaseModel):
    """Response from parsing bulk import files"""
    batch_id: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    candidates: List[BulkImportCandidate]
    global_errors: List[str] = []
    global_warnings: List[str] = []


class BulkImportSaveRequest(BaseModel):
    """Request to save reviewed candidates"""
    batch_id: str
    candidates: List[dict]  # Selected candidates with final data


class BulkImportSaveResponse(BaseModel):
    """Response from saving bulk import"""
    batch_id: str
    total_attempted: int
    successful: int
    failed: int
    results: List[dict]


# ============== HELPER FUNCTIONS ==============

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
            # For .doc files, try to extract as binary text
            # This is a fallback - .doc parsing is limited
            try:
                text = file_content.decode('utf-8', errors='ignore')
                # Filter out binary garbage
                text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t')
                return text
            except Exception:
                return ""
        
        return ""
    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {e}")
        return ""


def parse_excel_skills(skills_value) -> List[str]:
    """Parse skills from Excel cell (comma-separated string or list)"""
    if not skills_value:
        return []
    if isinstance(skills_value, list):
        return [s.strip() for s in skills_value if s and str(s).strip()]
    if isinstance(skills_value, str):
        return [s.strip() for s in skills_value.split(',') if s.strip()]
    return []


def merge_skills(excel_skills: List[str], parsed_skills: List[str]) -> List[str]:
    """Merge skills from Excel and parsed resume, deduplicated"""
    all_skills = set()
    for s in excel_skills:
        if s and s.strip():
            all_skills.add(s.strip().lower())
    for s in parsed_skills:
        if s and s.strip():
            all_skills.add(s.strip().lower())
    # Return with original casing from Excel first, then parsed
    result = []
    seen_lower = set()
    for s in excel_skills + parsed_skills:
        if s and s.strip().lower() not in seen_lower:
            result.append(s.strip())
            seen_lower.add(s.strip().lower())
    return result


def validate_candidate(candidate: BulkImportCandidate) -> BulkImportCandidate:
    """Validate candidate data and set validation status"""
    errors = []
    warnings = []
    
    # Required: At least email OR phone
    if not candidate.final_email and not candidate.final_phone:
        errors.append("Either email or phone is required")
    
    # Required: Name
    if not candidate.final_name or not candidate.final_name.strip():
        errors.append("Name is required")
    
    # Required: Resume
    if not candidate.resume_file_id:
        errors.append(f"Resume file not found for: {candidate.resume_filename}")
    
    # Warnings for missing optional but important fields
    if not candidate.final_location:
        warnings.append("Location is missing - will need to be added later")
    
    if not candidate.final_current_salary:
        warnings.append("Current salary is missing - will need to be added later")
    
    if not candidate.final_notice_period:
        warnings.append("Notice period is missing - will need to be added later")
    
    if candidate.final_experience_years == 0 and not candidate.final_experience:
        warnings.append("Experience years is 0 and no experience details found")
    
    candidate.validation_errors = errors
    candidate.warnings = warnings
    candidate.is_valid = len(errors) == 0
    
    return candidate


# ============== ENDPOINTS ==============

@bulk_import_router.post("/parse", response_model=BulkImportParseResponse)
async def parse_bulk_import(
    excel_file: UploadFile = File(..., description="Excel/CSV file with candidate metadata"),
    resume_zip: UploadFile = File(..., description="ZIP file containing resume files"),
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Parse bulk import files (Excel + ZIP of resumes).
    
    ADMIN ONLY. Does NOT save to database.
    Returns parsed data for review before confirmation.
    
    Excel Required Columns:
    - full_name
    - email OR phone (at least one)
    - resume_filename (must match a file in ZIP)
    
    Optional Columns:
    - current_location
    - experience_years
    - skills (comma-separated)
    - current_salary
    - notice_period
    """
    batch_id = str(uuid.uuid4())
    global_errors = []
    global_warnings = []
    candidates = []
    
    # Validate file types
    excel_ext = Path(excel_file.filename).suffix.lower()
    if excel_ext not in ['.xlsx', '.xls', '.csv']:
        raise HTTPException(status_code=400, detail="Excel file must be .xlsx, .xls, or .csv")
    
    if not resume_zip.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Resume file must be a .zip archive")
    
    # Read Excel file
    try:
        excel_content = await excel_file.read()
        if excel_ext == '.csv':
            df = pd.read_csv(io.BytesIO(excel_content))
        else:
            df = pd.read_excel(io.BytesIO(excel_content))
        
        # Normalize column names
        df.columns = [col.lower().strip().replace(' ', '_') for col in df.columns]
        
        # Check required columns
        required_cols = ['full_name', 'resume_filename']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required columns: {', '.join(missing_cols)}"
            )
        
        # Check for email or phone
        has_email = 'email' in df.columns
        has_phone = 'phone' in df.columns
        if not has_email and not has_phone:
            raise HTTPException(
                status_code=400,
                detail="Excel must have either 'email' or 'phone' column"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Excel parsing error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse Excel file: {str(e)}")
    
    # Extract ZIP file
    try:
        zip_content = await resume_zip.read()
        resume_files = {}  # filename -> content
        
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "resumes.zip")
            with open(zip_path, 'wb') as f:
                f.write(zip_content)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.is_dir():
                        continue
                    
                    filename = os.path.basename(file_info.filename)
                    ext = Path(filename).suffix.lower()
                    
                    if ext in ['.pdf', '.doc', '.docx']:
                        with zip_ref.open(file_info) as f:
                            resume_files[filename.lower()] = {
                                'content': f.read(),
                                'original_filename': filename
                            }
        
        if not resume_files:
            raise HTTPException(
                status_code=400,
                detail="No valid resume files (PDF, DOC, DOCX) found in ZIP"
            )
        
        global_warnings.append(f"Found {len(resume_files)} resume files in ZIP")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZIP extraction error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to extract ZIP file: {str(e)}")
    
    # Process each row
    now = datetime.now(timezone.utc).isoformat()
    
    for idx, row in df.iterrows():
        try:
            # Extract Excel data
            excel_name = str(row.get('full_name', '')).strip()
            excel_email = str(row.get('email', '')).strip() if pd.notna(row.get('email')) else None
            excel_phone = str(row.get('phone', '')).strip() if pd.notna(row.get('phone')) else None
            excel_location = str(row.get('current_location', '')).strip() if pd.notna(row.get('current_location')) else None
            excel_skills = parse_excel_skills(row.get('skills'))
            resume_filename = str(row.get('resume_filename', '')).strip()
            
            # Parse experience_years safely
            excel_exp = row.get('experience_years')
            excel_experience_years = None
            if pd.notna(excel_exp):
                try:
                    excel_experience_years = int(float(excel_exp))
                except (ValueError, TypeError):
                    pass
            
            # Parse salary safely
            excel_salary = row.get('current_salary')
            excel_current_salary = None
            if pd.notna(excel_salary):
                try:
                    excel_current_salary = int(float(excel_salary))
                except (ValueError, TypeError):
                    pass
            
            excel_notice_period = str(row.get('notice_period', '')).strip() if pd.notna(row.get('notice_period')) else None
            
            # Find matching resume file
            resume_filename_lower = resume_filename.lower()
            resume_data = resume_files.get(resume_filename_lower)
            
            candidate = BulkImportCandidate(
                row_index=idx,
                excel_name=excel_name,
                excel_email=excel_email,
                excel_phone=excel_phone,
                excel_location=excel_location,
                excel_experience_years=excel_experience_years,
                excel_skills=excel_skills,
                excel_current_salary=excel_current_salary,
                excel_notice_period=excel_notice_period,
                resume_filename=resume_filename,
                final_name=excel_name,
                final_email=excel_email,
                final_phone=excel_phone,
                final_location=excel_location,
                final_experience_years=excel_experience_years or 0,
                final_skills=excel_skills,
                final_current_salary=excel_current_salary,
                final_notice_period=excel_notice_period
            )
            
            if resume_data:
                # Upload resume to R2
                file_id = str(uuid.uuid4())
                original_filename = resume_data['original_filename']
                file_content = resume_data['content']
                
                # Generate R2 key
                r2_key = generate_r2_key("bulk-import", original_filename)
                
                # Determine content type
                ext = Path(original_filename).suffix.lower()
                content_type_map = {
                    '.pdf': 'application/pdf',
                    '.doc': 'application/msword',
                    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                }
                content_type = content_type_map.get(ext, 'application/octet-stream')
                
                # Upload to R2
                r2_result = await upload_to_r2(file_content, r2_key, content_type)
                
                candidate.resume_file_id = file_id
                candidate.r2_metadata = r2_result
                
                # Parse resume for enrichment
                resume_text = extract_text_from_file(file_content, original_filename)
                
                # Generate fingerprint from extracted text (not raw bytes)
                if resume_text:
                    fingerprint = generate_resume_fingerprint(resume_text)
                    candidate.resume_fingerprint = fingerprint
                else:
                    # Fallback: use hash of file content
                    import hashlib
                    candidate.resume_fingerprint = hashlib.sha256(file_content).hexdigest()[:32]
                
                if resume_text and len(resume_text) > 100:
                    try:
                        parsed = await parse_resume_with_ai(resume_text[:8000])
                        
                        candidate.parsed_name = parsed.get('name')
                        candidate.parsed_email = parsed.get('email')
                        candidate.parsed_phone = parsed.get('phone')
                        candidate.parsed_location = parsed.get('location')
                        candidate.parsed_experience_years = parsed.get('experience_years')
                        candidate.parsed_skills = parsed.get('skills', [])
                        candidate.parsed_headline = parsed.get('headline')
                        candidate.parsed_summary = parsed.get('summary')
                        candidate.parsed_experience = parsed.get('experience', [])
                        candidate.parsed_education = parsed.get('education', [])
                        
                        # MERGE LOGIC: Excel takes priority, parsed fills gaps
                        # Email/Phone: Excel ALWAYS overrides
                        # Skills: Merge (deduplicated)
                        # Missing Excel fields: Fill from parsed
                        
                        if not candidate.final_email and candidate.parsed_email:
                            candidate.final_email = candidate.parsed_email
                        
                        if not candidate.final_phone and candidate.parsed_phone:
                            candidate.final_phone = candidate.parsed_phone
                        
                        if not candidate.final_location and candidate.parsed_location:
                            candidate.final_location = candidate.parsed_location
                        
                        if candidate.final_experience_years == 0 and candidate.parsed_experience_years:
                            candidate.final_experience_years = candidate.parsed_experience_years
                        
                        # Merge skills
                        candidate.final_skills = merge_skills(
                            candidate.excel_skills, 
                            candidate.parsed_skills
                        )
                        
                        candidate.final_headline = candidate.parsed_headline
                        candidate.final_summary = candidate.parsed_summary
                        candidate.final_experience = candidate.parsed_experience
                        candidate.final_education = candidate.parsed_education
                        
                    except Exception as e:
                        logger.warning(f"Resume parsing failed for {resume_filename}: {e}")
                        candidate.warnings.append(f"Resume parsing failed: {str(e)}")
            
            # Validate candidate
            candidate = validate_candidate(candidate)
            candidates.append(candidate)
            
        except Exception as e:
            logger.error(f"Error processing row {idx}: {e}")
            # Create error candidate
            error_candidate = BulkImportCandidate(
                row_index=idx,
                excel_name=str(row.get('full_name', f'Row {idx}')),
                final_name=str(row.get('full_name', f'Row {idx}')),
                resume_filename=str(row.get('resume_filename', '')),
                is_valid=False,
                validation_errors=[f"Processing error: {str(e)}"]
            )
            candidates.append(error_candidate)
    
    valid_count = sum(1 for c in candidates if c.is_valid)
    invalid_count = len(candidates) - valid_count
    
    # Store batch metadata temporarily (for later save)
    batch_meta = {
        "id": batch_id,
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user["name"],
        "total_rows": len(candidates),
        "valid_rows": valid_count,
        "invalid_rows": invalid_count,
        "status": "pending_review",
        "candidates_preview": [c.dict() for c in candidates]
    }
    
    await db.bulk_import_batches.insert_one(batch_meta)
    
    return BulkImportParseResponse(
        batch_id=batch_id,
        total_rows=len(candidates),
        valid_rows=valid_count,
        invalid_rows=invalid_count,
        candidates=candidates,
        global_errors=global_errors,
        global_warnings=global_warnings
    )


@bulk_import_router.post("/save", response_model=BulkImportSaveResponse)
async def save_bulk_import(
    request: BulkImportSaveRequest,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Save reviewed candidates to Candidate Bank.
    
    ADMIN ONLY. Requires prior parsing and review.
    
    Each record is saved with:
    - source = "bulk_import"
    - import_batch_id = batch_id
    - uploaded_by_role = "admin"
    - resume_storage = storage type from R2
    
    Partial success: Successful records are saved even if some fail.
    """
    batch_id = request.batch_id
    candidates = request.candidates
    
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates to save")
    
    # Verify batch exists
    batch = await db.bulk_import_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found. Please re-parse files.")
    
    now = datetime.now(timezone.utc).isoformat()
    results = []
    successful = 0
    failed = 0
    
    for candidate_data in candidates:
        try:
            # Check for existing candidate (deduplication)
            email = candidate_data.get('final_email')
            phone = candidate_data.get('final_phone')
            fingerprint = candidate_data.get('resume_fingerprint')
            
            existing = None
            if email:
                existing = await db.candidate_bank.find_one({"email": email.lower()}, {"_id": 0})
            if not existing and phone:
                phone_normalized = "".join(filter(str.isdigit, phone))[-10:]
                if phone_normalized:
                    existing = await db.candidate_bank.find_one({"phone_normalized": phone_normalized}, {"_id": 0})
            
            # Build candidate document
            candidate_id = existing["id"] if existing else str(uuid.uuid4())
            
            # Build resume version
            resume_version = {
                "id": candidate_data.get('resume_file_id'),
                "fingerprint": fingerprint,
                "uploaded_at": now,
                "uploaded_by": current_user["id"],
                "is_active": True,
                "r2_metadata": candidate_data.get('r2_metadata'),
                "original_filename": candidate_data.get('resume_filename')
            }
            
            if existing:
                # Update existing candidate
                update_fields = {
                    "updated_at": now,
                    "last_updated_by": current_user["id"],
                    "active_resume_id": candidate_data.get('resume_file_id'),
                }
                
                # Add new resume version
                existing_versions = existing.get("resume_versions", [])
                existing_versions.append(resume_version)
                update_fields["resume_versions"] = existing_versions
                
                # Add fingerprint if not exists
                existing_fingerprints = existing.get("resume_fingerprints", [])
                if fingerprint and fingerprint not in existing_fingerprints:
                    existing_fingerprints.append(fingerprint)
                    update_fields["resume_fingerprints"] = existing_fingerprints
                
                # Update fields that are provided
                if candidate_data.get('final_skills'):
                    existing_skills = set(existing.get("skills", []))
                    new_skills = set(candidate_data.get('final_skills', []))
                    update_fields["skills"] = list(existing_skills.union(new_skills))
                
                if candidate_data.get('final_current_salary'):
                    update_fields["current_salary"] = candidate_data['final_current_salary']
                
                if candidate_data.get('final_notice_period'):
                    update_fields["notice_period"] = candidate_data['final_notice_period']
                
                if candidate_data.get('final_location'):
                    update_fields["location"] = candidate_data['final_location']
                
                if candidate_data.get('final_experience_years') is not None:
                    update_fields["experience_years"] = candidate_data['final_experience_years']
                
                if candidate_data.get('final_experience'):
                    update_fields["experience"] = candidate_data['final_experience']
                
                if candidate_data.get('final_education'):
                    update_fields["education"] = candidate_data['final_education']
                
                if candidate_data.get('final_headline'):
                    update_fields["headline"] = candidate_data['final_headline']
                
                if candidate_data.get('final_summary'):
                    update_fields["summary"] = candidate_data['final_summary']
                
                await db.candidate_bank.update_one(
                    {"id": existing["id"]},
                    {"$set": update_fields}
                )
                
                results.append({
                    "row_index": candidate_data.get('row_index'),
                    "name": candidate_data.get('final_name'),
                    "email": email,
                    "status": "updated",
                    "candidate_id": existing["id"],
                    "message": "Existing candidate updated"
                })
                successful += 1
                
            else:
                # Create new candidate
                candidate_doc = {
                    "id": candidate_id,
                    "email": email.lower() if email else None,
                    "name": candidate_data.get('final_name'),
                    "phone": phone,
                    "phone_normalized": "".join(filter(str.isdigit, phone or ""))[-10:] or None,
                    "headline": candidate_data.get('final_headline'),
                    "summary": candidate_data.get('final_summary'),
                    "skills": candidate_data.get('final_skills', []),
                    "experience_years": candidate_data.get('final_experience_years', 0),
                    "experience": candidate_data.get('final_experience', []),
                    "education": candidate_data.get('final_education', []),
                    "location": candidate_data.get('final_location'),
                    "certifications": [],
                    "active_resume_id": candidate_data.get('resume_file_id'),
                    "resume_versions": [resume_version],
                    "resume_fingerprints": [fingerprint] if fingerprint else [],
                    "resume_url": None,  # R2 storage used
                    "current_salary": candidate_data.get('final_current_salary'),
                    "notice_period": candidate_data.get('final_notice_period'),
                    "source": "bulk_import",
                    "import_batch_id": batch_id,
                    "linked_user_id": None,
                    "visibility": {
                        "admin_ids": [current_user["id"]],
                        "employer_ids": [],
                        "recruiter_ids": []
                    },
                    "match_cache": [],
                    "created_at": now,
                    "updated_at": now,
                    "created_by": current_user["id"],
                    "last_updated_by": current_user["id"],
                    "uploaded_by_role": "admin",
                    "application_history": [],
                    "profile_update_audit": [{
                        "action": "bulk_import_created",
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
                    "name": candidate_data.get('final_name'),
                    "email": email,
                    "status": "created",
                    "candidate_id": candidate_id,
                    "message": "New candidate created"
                })
                successful += 1
                
        except Exception as e:
            logger.error(f"Error saving candidate: {e}")
            results.append({
                "row_index": candidate_data.get('row_index'),
                "name": candidate_data.get('final_name', 'Unknown'),
                "email": candidate_data.get('final_email'),
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
                "details": results
            }
        }}
    )
    
    return BulkImportSaveResponse(
        batch_id=batch_id,
        total_attempted=len(candidates),
        successful=successful,
        failed=failed,
        results=results
    )


@bulk_import_router.get("/batches")
async def get_import_batches(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get list of all bulk import batches for audit"""
    batches = await db.bulk_import_batches.find(
        {},
        {"_id": 0, "candidates_preview": 0}  # Exclude large preview data
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
    """Download Excel template for bulk import"""
    # Create template DataFrame
    template_df = pd.DataFrame({
        'full_name': ['John Doe', 'Jane Smith'],
        'email': ['john.doe@example.com', 'jane.smith@example.com'],
        'phone': ['+919876543210', '+919876543211'],
        'current_location': ['Bangalore', 'Mumbai'],
        'experience_years': [5, 3],
        'skills': ['Python, JavaScript, React', 'Java, Spring Boot, AWS'],
        'current_salary': [1200000, 1500000],
        'notice_period': ['30 days', '60 days'],
        'resume_filename': ['john_doe_resume.pdf', 'jane_smith_resume.pdf']
    })
    
    # Create in-memory Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        template_df.to_excel(writer, index=False, sheet_name='Candidates')
    output.seek(0)
    
    from fastapi.responses import StreamingResponse
    
    return StreamingResponse(
        io.BytesIO(output.getvalue()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.document",
        headers={"Content-Disposition": "attachment; filename=bulk_import_template.xlsx"}
    )
