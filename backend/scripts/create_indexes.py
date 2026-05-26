"""
MongoDB Index Creation Script for VHC Talent OS
Creates indexes to optimize search and query performance
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGO_URL = os.environ.get('MONGO_URL')
if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable is required.")
DB_NAME = os.environ.get('DB_NAME', 'vhc_talent_os')

async def create_indexes():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    print("Creating MongoDB indexes for performance optimization...")
    
    # ============ CANDIDATE_BANK INDEXES ============
    print("\n📊 Creating candidate_bank indexes...")
    
    # ─── PRIMARY: unique `id` (UUID) lookup index ───
    # Every `db.candidate_bank.find_one({"id": ...})` and `update_one({"id": ...})`
    # call across the codebase hits this. Without it Mongo does a COLLSCAN on
    # 100K+ docs per lookup — that's why the deep-link badge → profile dialog
    # was painfully slow. Single biggest performance fix on this collection.
    try:
        await db.candidate_bank.create_index("id", name="id_idx", unique=True)
        print("  ✅ id (UUID) unique index ← primary key lookups")
    except Exception as e:
        # Falls back to non-unique if duplicates exist (one-time data cleanup needed)
        print(f"  ⚠️ id unique index failed ({e}); creating non-unique fallback")
        await db.candidate_bank.create_index("id", name="id_idx")
        print("  ✅ id index (non-unique fallback)")

    # Text index for name search (supports partial/fuzzy matching)
    try:
        await db.candidate_bank.create_index([("name", "text"), ("email", "text"), ("skills", "text")], name="text_search_idx")
        print("  ✅ Text search index (name, email, skills)")
    except Exception as e:
        print(f"  ⚠️ Text index: {e}")
    
    # Email index (unique lookups)
    await db.candidate_bank.create_index("email", name="email_idx")
    print("  ✅ Email index")
    
    # Phone normalized index (duplicate detection)
    await db.candidate_bank.create_index("phone_normalized", name="phone_idx", sparse=True)
    print("  ✅ Phone normalized index")
    
    # Skills array index (AI matching)
    await db.candidate_bank.create_index("skills", name="skills_idx")
    print("  ✅ Skills array index")
    
    # Experience years index (filtering)
    await db.candidate_bank.create_index("experience_years", name="exp_years_idx")
    print("  ✅ Experience years index")
    
    # Location index (filtering)
    await db.candidate_bank.create_index("location", name="location_idx", sparse=True)
    print("  ✅ Location index")
    
    # Current salary index (filtering/sorting)
    await db.candidate_bank.create_index("current_salary", name="salary_idx", sparse=True)
    print("  ✅ Current salary index")
    
    # Bulk import restricted index (governance queries)
    await db.candidate_bank.create_index("bulk_import_restricted", name="bulk_restricted_idx", sparse=True)
    print("  ✅ Bulk import restricted index")
    
    # Compound index for common query patterns (AI matching)
    await db.candidate_bank.create_index([
        ("experience_years", 1),
        ("current_salary", 1),
        ("location", 1)
    ], name="matching_compound_idx")
    print("  ✅ Compound index (experience, salary, location)")
    
    # Created_at index (sorting by recent)
    await db.candidate_bank.create_index([("created_at", -1)], name="created_at_idx")
    print("  ✅ Created at index (descending)")

    # ============ AUDIT_LOGS INDEXES ============
    # The /candidate-bank/{id}/audit-log and /history endpoints query
    # `audit_logs.entity_id`. Without an index this scales as O(N) on the
    # audit collection (which grows by 1 row per profile view).
    print("\n📊 Creating audit_logs indexes...")
    try:
        await db.audit_logs.create_index([("entity_id", 1), ("created_at", -1)], name="entity_id_created_at_idx")
        print("  ✅ entity_id + created_at compound index")
    except Exception as e:
        print(f"  ⚠️ audit_logs index: {e}")
    
    # ============ JOBS INDEXES ============
    print("\n📊 Creating jobs indexes...")
    
    await db.jobs.create_index("status", name="status_idx")
    print("  ✅ Job status index")
    
    await db.jobs.create_index("company_id", name="company_idx")
    print("  ✅ Company ID index")
    
    try:
        await db.jobs.create_index([("title", "text"), ("description", "text")], name="job_text_idx")
        print("  ✅ Job text search index")
    except Exception as e:
        print(f"  ⚠️ Job text index: {e}")
    
    # ============ APPLICATIONS INDEXES ============
    print("\n📊 Creating applications indexes...")
    
    await db.applications.create_index("job_id", name="app_job_idx")
    print("  ✅ Application job_id index")
    
    await db.applications.create_index("candidate_id", name="app_candidate_idx")
    print("  ✅ Application candidate_id index")
    
    await db.applications.create_index("stage", name="app_stage_idx")
    print("  ✅ Application stage index")
    
    await db.applications.create_index([("job_id", 1), ("stage", 1)], name="app_job_stage_idx")
    print("  ✅ Compound index (job_id, stage)")
    
    # ============ USERS INDEXES ============
    print("\n📊 Creating users indexes...")
    
    try:
        await db.users.create_index("email", name="user_email_idx", unique=True)
        print("  ✅ User email index (unique)")
    except Exception as e:
        print(f"  ⚠️ User email index: {e}")
    
    await db.users.create_index("role", name="user_role_idx")
    print("  ✅ User role index")
    
    # ============ COMPANIES INDEXES ============
    print("\n📊 Creating companies indexes...")
    
    await db.companies.create_index("name", name="company_name_idx")
    print("  ✅ Company name index")
    
    await db.companies.create_index("employer_id", name="company_employer_idx")
    print("  ✅ Company employer_id index")
    
    print("\n✅ All indexes created successfully!")
    
    # ============ PARSE_TASKS INDEXES (Async CV Parsing) ============
    print("\n📊 Creating parse_tasks indexes...")
    
    await db.parse_tasks.create_index("id", name="task_id_idx", unique=True)
    print("  ✅ Task ID index (unique)")
    
    await db.parse_tasks.create_index("created_by", name="task_created_by_idx")
    print("  ✅ Task created_by index")
    
    await db.parse_tasks.create_index([("status", 1), ("created_at", -1)], name="task_status_created_idx")
    print("  ✅ Task status + created_at compound index")
    
    # ============ NOTIFICATIONS INDEXES ============
    print("\n📊 Creating notifications indexes...")
    
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)], name="notif_user_created_idx")
    print("  ✅ Notification user_id + created_at compound index")
    
    await db.notifications.create_index([("user_id", 1), ("read", 1)], name="notif_user_read_idx")
    print("  ✅ Notification user_id + read compound index")
    
    # ============ SYSTEM_ERRORS INDEXES ============
    print("\n📊 Creating system_errors indexes...")
    
    await db.system_errors.create_index([("source", 1), ("created_at", -1)], name="syserr_source_created_idx")
    print("  ✅ System errors source + created_at index")
    
    # ============ NAUKRI_CAPTURE_LOGS INDEXES ============
    print("\n📊 Creating naukri_capture_logs indexes...")
    
    await db.naukri_capture_logs.create_index([("timestamp", -1)], name="capture_timestamp_idx")
    print("  ✅ Capture logs timestamp index")
    
    print("\n✅ All additional indexes created!")
    
    # List all indexes
    print("\n📋 Current indexes on candidate_bank:")
    async for index in db.candidate_bank.list_indexes():
        print(f"   - {index['name']}: {index.get('key', {})}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(create_indexes())
