"""
Batch Re-Import Script for Naukri Excel Data

Deletes all existing candidates with source="naukri_excel_import",
then re-imports from all .xlsx files in the specified directory
using the corrected column mapping.

Usage: python3 batch_reimport.py
"""

import os
import re
import sys
import uuid
import glob
import logging
import pandas as pd
from datetime import datetime, timezone
from pymongo import MongoClient
from typing import Optional, List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/batch_reimport.log')
    ]
)
logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb+srv://vhc_admin:DL4cbb4890@cluster0.vuhdiod.mongodb.net/?retryWrites=true&w=majority')
DB_NAME = os.environ.get('DB_NAME', 'vhc_talent_os')
EXCEL_DIR = '/tmp/reupload_zip/reupload zip/'
ADMIN_USER_ID = None  # Will be fetched from DB
ADMIN_USER_NAME = None

# ---------- Helper Functions (from bulk_import_service.py) ----------

def parse_experience_string(exp_str: str) -> int:
    if not exp_str:
        return 0
    try:
        exp_str = str(exp_str).upper().strip()
        year_match = re.search(r'(\d+)\s*YEAR', exp_str)
        if year_match:
            return int(year_match.group(1))
        year_match = re.search(r'(\d+)\s*Y', exp_str)
        if year_match:
            return int(year_match.group(1))
        num_match = re.search(r'(\d+)', exp_str)
        if num_match:
            return int(num_match.group(1))
        return 0
    except Exception:
        return 0


def parse_salary_string(salary_str: str) -> Optional[int]:
    if not salary_str:
        return None
    try:
        salary_str = str(salary_str).upper().strip()
        match = re.search(r'RS\.?\s*(\d+\.?\d*)\s*LAKH', salary_str)
        if match:
            return int(float(match.group(1)) * 100000)
        match = re.search(r'(\d+\.?\d*)\s*L', salary_str)
        if match:
            lakhs = float(match.group(1))
            return int(lakhs * 100000)
        num_match = re.search(r'(\d+\.?\d*)', salary_str)
        if num_match:
            val = float(num_match.group(1))
            if val < 100:
                return int(val * 100000)
            return int(val)
        return None
    except Exception:
        return None


def normalize_phone(phone: str) -> Optional[str]:
    if not phone:
        return None
    digits = "".join(filter(str.isdigit, str(phone)))
    return digits[-10:] if len(digits) >= 10 else digits if digits else None


# ---------- Column Mapping (from bulk_import.py) ----------

COL_MAP = {
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
    """Fuzzy column matcher: exact -> normalized -> contains"""
    synonyms = COL_MAP.get(key, [key])
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


def get_val(df, row, key):
    col = find_column(df, key)
    if col and pd.notna(row.get(col)):
        return str(row[col]).strip()
    return None


def build_candidate_doc(df, row, source_filename, batch_id, now):
    """Build a candidate document from a parsed Excel row."""
    name = get_val(df, row, 'candidate_name') or "Unknown"
    contact = get_val(df, row, 'contact_no')
    email = get_val(df, row, 'email')
    phone = normalize_phone(contact)

    # Must have email or phone
    if not email and not phone:
        return None, "No email or phone"

    work_exp = get_val(df, row, 'work_exp')
    salary = get_val(df, row, 'annual_salary')
    location = get_val(df, row, 'current_location')
    employer = get_val(df, row, 'current_employer')
    designation = get_val(df, row, 'designation')
    ug_course = get_val(df, row, 'ug_course')
    industry = get_val(df, row, 'industry')
    age_dob = get_val(df, row, 'age_dob')

    # Naukri-specific fields
    naukri_data = {}
    for nk in ('key_skills', 'notice_period', 'preferred_locations', 'resume_headline',
                'summary', 'department', 'role_category', 'gender', 'marital_status',
                'home_town', 'work_permit_usa', 'naukri_job_title', 'application_date',
                'candidate_source', 'candidate_profile',
                'ug_specialization', 'ug_university', 'ug_year',
                'pg_degree', 'pg_specialization', 'pg_university', 'pg_year',
                'doc_degree', 'doc_specialization', 'doc_university', 'doc_year'):
        val = get_val(df, row, nk)
        if val:
            naukri_data[nk] = val

    # Build skills
    skills = []
    raw_skills = naukri_data.get('key_skills', '')
    if raw_skills:
        skills = [s.strip() for s in str(raw_skills).split(',') if s.strip()]

    # Build education
    education = []
    if ug_course:
        edu = {"degree": ug_course, "level": "UG"}
        if naukri_data.get('ug_specialization'): edu["specialization"] = naukri_data['ug_specialization']
        if naukri_data.get('ug_university'): edu["institution"] = naukri_data['ug_university']
        if naukri_data.get('ug_year'): edu["year"] = str(naukri_data['ug_year'])
        education.append(edu)
    if naukri_data.get('pg_degree'):
        edu = {"degree": naukri_data['pg_degree'], "level": "PG"}
        if naukri_data.get('pg_specialization'): edu["specialization"] = naukri_data['pg_specialization']
        if naukri_data.get('pg_university'): edu["institution"] = naukri_data['pg_university']
        if naukri_data.get('pg_year'): edu["year"] = str(naukri_data['pg_year'])
        education.append(edu)
    if naukri_data.get('doc_degree'):
        edu = {"degree": naukri_data['doc_degree'], "level": "Doctorate"}
        if naukri_data.get('doc_specialization'): edu["specialization"] = naukri_data['doc_specialization']
        if naukri_data.get('doc_university'): edu["institution"] = naukri_data['doc_university']
        if naukri_data.get('doc_year'): edu["year"] = str(naukri_data['doc_year'])
        education.append(edu)

    candidate_id = str(uuid.uuid4())
    candidate_doc = {
        "id": candidate_id,
        "email": email.lower() if email else None,
        "name": name,
        "phone": contact,
        "phone_normalized": phone,
        "headline": naukri_data.get('resume_headline') or designation,
        "summary": naukri_data.get('summary'),
        "skills": skills,
        "experience_years": parse_experience_string(work_exp),
        "experience": [],
        "education": education,
        "location": location,
        "certifications": [],
        "active_resume_id": None,
        "resume_versions": [],
        "resume_fingerprints": [],
        "resume_url": None,
        "current_salary": parse_salary_string(salary),
        "notice_period": naukri_data.get('notice_period'),
        "preferred_locations": [l.strip() for l in str(naukri_data.get('preferred_locations', '')).split(',') if l.strip()] if naukri_data.get('preferred_locations') else [],
        "source": "naukri_excel_import",
        "source_file": source_filename,
        "bulk_import_type": "excel",
        "bulk_import_restricted": True,
        "cv_attached": False,
        "industry": industry,
        "industry_source": "excel" if industry else None,
        "current_employer": employer,
        "designation": designation,
        "department": naukri_data.get('department'),
        "role_category": naukri_data.get('role_category'),
        "ug_course": ug_course,
        "date_of_birth": age_dob,
        "gender": naukri_data.get('gender'),
        "marital_status": naukri_data.get('marital_status'),
        "home_town": naukri_data.get('home_town'),
        "naukri_profile_url": naukri_data.get('candidate_profile'),
        "naukri_job_title": naukri_data.get('naukri_job_title'),
        "application_date": naukri_data.get('application_date'),
        "naukri_data": naukri_data,
        "import_batch_id": batch_id,
        "discovered_by": [],
        "linked_user_id": None,
        "visibility": {"admin_ids": [ADMIN_USER_ID], "employer_ids": [], "recruiter_ids": []},
        "match_cache": [],
        "created_at": now,
        "updated_at": now,
        "created_by": ADMIN_USER_ID,
        "last_updated_by": ADMIN_USER_ID,
        "uploaded_by_role": "admin",
        "application_history": [],
        "profile_update_audit": [{
            "action": "bulk_import_created",
            "mode": "naukri_excel",
            "by_id": ADMIN_USER_ID,
            "by_name": ADMIN_USER_NAME,
            "by_role": "admin",
            "timestamp": now,
            "batch_id": batch_id,
            "naukri_job_title": naukri_data.get('naukri_job_title'),
        }]
    }

    return candidate_doc, None


def main():
    global ADMIN_USER_ID, ADMIN_USER_NAME

    logger.info("=" * 60)
    logger.info("BATCH RE-IMPORT: Starting Naukri Excel Re-Import")
    logger.info("=" * 60)

    # Connect to MongoDB
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    # Get admin user
    admin = db.users.find_one({"email": "admin@vhc.in"}, {"_id": 0, "id": 1, "name": 1})
    if not admin:
        logger.error("Admin user not found!")
        return
    ADMIN_USER_ID = admin["id"]
    ADMIN_USER_NAME = admin.get("name", "Admin")
    logger.info(f"Admin user: {ADMIN_USER_NAME} ({ADMIN_USER_ID})")

    # Step 1: Delete all existing naukri_excel_import candidates
    existing_count = db.candidate_bank.count_documents({"source": "naukri_excel_import"})
    logger.info(f"Step 1: Found {existing_count} existing naukri_excel_import candidates to delete")

    if existing_count > 0:
        result = db.candidate_bank.delete_many({"source": "naukri_excel_import"})
        logger.info(f"Step 1: Deleted {result.deleted_count} candidates")

    # Also delete old batch metadata
    old_batches = db.bulk_import_batches.delete_many({"mode": "excel"})
    logger.info(f"Step 1: Deleted {old_batches.deleted_count} old batch records")

    # Step 2: Find all Excel files
    excel_files = sorted(glob.glob(os.path.join(EXCEL_DIR, "*.xlsx")))
    logger.info(f"Step 2: Found {len(excel_files)} .xlsx files to process")

    if not excel_files:
        logger.error(f"No .xlsx files found in {EXCEL_DIR}")
        return

    # Step 3: Process each file
    now = datetime.now(timezone.utc).isoformat()
    batch_id = str(uuid.uuid4())
    
    total_rows = 0
    total_valid = 0
    total_inserted = 0
    total_skipped_no_contact = 0
    total_duplicates = 0
    total_errors = 0
    file_stats = []

    # Dedup tracking: email -> True, phone -> True
    seen_emails = set()
    seen_phones = set()

    # Also check existing non-naukri candidates for dedup
    logger.info("Step 3: Building dedup index from remaining candidates...")
    for doc in db.candidate_bank.find({}, {"_id": 0, "email": 1, "phone_normalized": 1}):
        if doc.get("email"):
            seen_emails.add(doc["email"].lower())
        if doc.get("phone_normalized"):
            seen_phones.add(doc["phone_normalized"])
    logger.info(f"  Existing dedup index: {len(seen_emails)} emails, {len(seen_phones)} phones")

    insert_buffer = []
    BATCH_SIZE = 500

    for file_idx, filepath in enumerate(excel_files):
        filename = os.path.basename(filepath)
        file_rows = 0
        file_valid = 0
        file_inserted = 0
        file_dupes = 0
        file_skip = 0

        try:
            df = pd.read_excel(filepath, engine='openpyxl')
            # Normalize column names
            df.columns = [col.strip().rstrip('*').strip().rstrip('.').strip().lower().replace(' ', '_').replace('.', '_') for col in df.columns]
            file_rows = len(df)
            total_rows += file_rows
        except Exception as e:
            logger.error(f"  [{file_idx+1}/{len(excel_files)}] Error reading {filename}: {e}")
            total_errors += 1
            file_stats.append({"file": filename, "rows": 0, "inserted": 0, "error": str(e)})
            continue

        for idx, row in df.iterrows():
            try:
                candidate_doc, err = build_candidate_doc(df, row, filename, batch_id, now)
                if err:
                    file_skip += 1
                    total_skipped_no_contact += 1
                    continue

                file_valid += 1

                # Dedup check
                email = candidate_doc.get("email")
                phone = candidate_doc.get("phone_normalized")

                is_dupe = False
                if email and email in seen_emails:
                    is_dupe = True
                if not is_dupe and phone and phone in seen_phones:
                    is_dupe = True

                if is_dupe:
                    file_dupes += 1
                    total_duplicates += 1
                    continue

                # Track for dedup
                if email:
                    seen_emails.add(email)
                if phone:
                    seen_phones.add(phone)

                insert_buffer.append(candidate_doc)
                file_inserted += 1
                total_inserted += 1

                # Flush buffer
                if len(insert_buffer) >= BATCH_SIZE:
                    db.candidate_bank.insert_many(insert_buffer, ordered=False)
                    insert_buffer = []

            except Exception:
                total_errors += 1

        total_valid += file_valid
        file_stats.append({
            "file": filename,
            "rows": file_rows,
            "valid": file_valid,
            "inserted": file_inserted,
            "duplicates": file_dupes,
            "skipped": file_skip
        })

        if (file_idx + 1) % 50 == 0:
            logger.info(f"  Progress: {file_idx+1}/{len(excel_files)} files | {total_inserted} inserted so far")

    # Flush remaining
    if insert_buffer:
        db.candidate_bank.insert_many(insert_buffer, ordered=False)
        insert_buffer = []

    # Step 4: Final report
    final_count = db.candidate_bank.count_documents({"source": "naukri_excel_import"})
    total_all = db.candidate_bank.count_documents({})

    logger.info("")
    logger.info("=" * 60)
    logger.info("BATCH RE-IMPORT: COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Files processed:        {len(excel_files)}")
    logger.info(f"  Total Excel rows:       {total_rows}")
    logger.info(f"  Valid candidates:        {total_valid}")
    logger.info(f"  Inserted (new):          {total_inserted}")
    logger.info(f"  Duplicates (skipped):    {total_duplicates}")
    logger.info(f"  Skipped (no contact):    {total_skipped_no_contact}")
    logger.info(f"  Errors:                  {total_errors}")
    logger.info(f"  ---")
    logger.info(f"  DB naukri_excel count:   {final_count}")
    logger.info(f"  DB total candidates:     {total_all}")
    logger.info(f"  Previously deleted:      {existing_count}")
    logger.info("=" * 60)

    # Verify designation field on a sample
    sample = db.candidate_bank.find_one(
        {"source": "naukri_excel_import", "designation": {"$ne": None}},
        {"_id": 0, "name": 1, "designation": 1, "naukri_job_title": 1, "source_file": 1}
    )
    if sample:
        logger.info(f"  Sample verification:")
        logger.info(f"    Name: {sample.get('name')}")
        logger.info(f"    Designation (should be actual role): {sample.get('designation')}")
        logger.info(f"    Naukri Job Title (applied for): {sample.get('naukri_job_title')}")
        logger.info(f"    Source file: {sample.get('source_file')}")

    client.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
