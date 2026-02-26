#!/usr/bin/env python3
"""
DATABASE CONSOLIDATION — EXECUTION SCRIPT
==========================================
Merges production-only real data into Atlas (master DB).
Applies all user-confirmed decisions from the dry-run.

MUST be run with backup already taken.
"""
import json
import os
import sys
from pymongo import MongoClient
from datetime import datetime, timezone

MONGO_URL = os.environ.get('MONGO_URL') or os.environ.get('MONGODB_URI', '')
DB_NAME = 'vhc_talent_os'
PROD_SNAPSHOT_DIR = '/app/backup/production_snapshot_20260218'
REPORT_PATH = '/app/memory/MIGRATION_EXECUTION_LOG.md'

# UUID Conflict Resolution: Option A — Keep Production UUIDs
UUID_REMAP = {
    '842077a8-d9e7-4bca-b89e-dce044e630f6': 'eb962d6f-ad6f-454a-bd7b-edc68f8b4ff7',  # admin@vhc.in
    '09d5c0fa-4c11-4951-bcf8-bd223b0b62e2': 'cf36890a-b8fa-47e2-abf3-d4600f04c831',  # ajit@vhc.in
    '58dc5b71-adb6-4a04-9d19-1c3874907230': '839f5e28-f97e-4e0d-ae18-091e0636fa60',  # jatin@vhc.in
    '220bcc65-0f44-4550-b7ef-09bc4ccdb3d7': 'f412d7aa-c3f1-436f-aaea-91600905f486',  # siddharth@vhc.in
}
SIDDHARTH_PROD_UUID = 'f412d7aa-c3f1-436f-aaea-91600905f486'

CANONICAL_COMPANY_ID = '9c1553d8-4ead-4324-bf79-6a3a6c512d44'
DUPLICATE_COMPANY_ID = 'ba188401-91dc-446d-93c0-d9712b84c230'
CANONICAL_COMPANY_NAME = 'Panasonic India'

SKIP_USERS = {
    '096ec385-98a3-4001-9230-dfd79a68353f',
    'f501f248-57c4-4d38-ae9b-febcbe43c133',
    '0e82b2aa-9c30-4a06-ab62-6b4336fccf76',
}

# Jobs to explicitly skip (user decisions on edge cases)
SKIP_JOBS = {
    '5203cc0d-851f-4b79-a782-5929c7a39ee7',  # Test Recruiter Job Approval
    'afeea144-0b75-4dfd-8d39-88d0cf291745',  # AM/DM Warranty Specialist (refs TEST company)
}

TEST_PATTERNS = ['TEST_', 'Test Job', 'Career Page Test', 'Non-Live Job', 'Test Recruiter']

log_lines = []
ops_count = {
    'user_delete': 0, 'user_insert': 0, 'user_update': 0,
    'company_insert': 0, 'company_update': 0,
    'team_update': 0, 'job_insert': 0,
    'cb_insert': 0, 'app_insert': 0, 'app_delete': 0,
    'comm_insert': 0,
}

def log(msg, indent=0):
    line = '  ' * indent + msg
    log_lines.append(line)
    print(line)

def load_prod(name):
    with open(os.path.join(PROD_SNAPSHOT_DIR, f'{name}.json')) as f:
        return json.load(f)

def is_test(name):
    return any(p in (name or '') for p in TEST_PATTERNS)


def main():
    log("=" * 80)
    log("DATABASE CONSOLIDATION — LIVE EXECUTION")
    log(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    log("=" * 80)

    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]

    # Pre-merge snapshot
    log("\n--- PRE-MERGE DOCUMENT COUNTS ---")
    pre_counts = {}
    for col in ['users', 'companies', 'teams', 'jobs', 'applications', 'candidate_bank', 'commercials']:
        c = db[col].count_documents({})
        pre_counts[col] = c
        log(f"  {col}: {c}")

    # Load production data
    prod_users = load_prod('users')
    prod_companies = load_prod('companies')
    prod_jobs = load_prod('jobs')
    prod_apps = load_prod('applications')
    prod_commercials = load_prod('commercials')
    prod_candidates = load_prod('candidate_bank')

    # Build Atlas lookups
    atlas_users = {u['id']: u for u in db.users.find({}, {'_id': 0})}
    atlas_user_emails = {u['email']: u['id'] for u in atlas_users.values()}
    atlas_companies = {c['id']: c for c in db.companies.find({}, {'_id': 0})}
    atlas_job_ids = {j['id'] for j in db.jobs.find({}, {'_id': 0, 'id': 1})}
    atlas_app_ids = {a['id'] for a in db.applications.find({}, {'_id': 0, 'id': 1})}
    atlas_cb_ids = {c['id'] for c in db.candidate_bank.find({}, {'_id': 0, 'id': 1})}
    atlas_comm_ids = {c['id'] for c in db.commercials.find({}, {'_id': 0, 'id': 1})}

    prod_user_by_email = {u['email']: u for u in prod_users}
    prod_user_by_id = {u['id']: u for u in prod_users}

    # Track final valid IDs for application validation
    final_job_ids = atlas_job_ids.copy()
    final_cb_ids = atlas_cb_ids.copy()

    # =========================================================================
    # PHASE 1: USERS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 1: USERS")
    log("=" * 80)

    # 1a. UUID Conflict Resolution
    for atlas_uuid, prod_uuid in UUID_REMAP.items():
        atlas_user = atlas_users.get(atlas_uuid)
        if not atlas_user:
            log(f"  WARN: Atlas user {atlas_uuid} not found, skipping", 1)
            continue
        
        prod_user = prod_user_by_email.get(atlas_user['email'])
        if not prod_user:
            log(f"  WARN: Prod user for {atlas_user['email']} not found, skipping", 1)
            continue

        # Delete Atlas duplicate
        result = db.users.delete_one({'id': atlas_uuid})
        log(f"  DELETED Atlas user: {atlas_user['email']} ({atlas_uuid}) [matched: {result.deleted_count}]")
        ops_count['user_delete'] += result.deleted_count

        # Build new user doc from production (need full doc from prod API)
        new_user = dict(prod_user)
        # Remove any _id that might exist
        new_user.pop('_id', None)
        
        # Override siddharth's role to admin
        if prod_uuid == SIDDHARTH_PROD_UUID:
            new_user['role'] = 'admin'
            log(f"  Role override: siddharth@vhc.in -> admin")

        # We need the password hash from production. The API snapshot doesn't include it.
        # For these 4 users, we need to fetch the password from Atlas backup or set a known password.
        # Since both DBs use the same passwords (verified), we can copy the hash from Atlas backup.
        # Actually, the Atlas user we just deleted had a password. Let's use it since passwords are identical.
        if atlas_user.get('password'):
            new_user['password'] = atlas_user['password']
        
        db.users.insert_one(new_user)
        log(f"  INSERTED Prod user: {new_user['email']} ({prod_uuid}, role: {new_user.get('role')})")
        ops_count['user_insert'] += 1

    # 1b. Remap created_by across ALL Atlas users
    for doc in db.users.find({}, {'_id': 0, 'id': 1, 'created_by': 1}):
        cb = doc.get('created_by', '')
        if cb in UUID_REMAP:
            db.users.update_one({'id': doc['id']}, {'$set': {'created_by': UUID_REMAP[cb]}})
            log(f"  UPDATED user {doc['id']}: created_by -> {UUID_REMAP[cb]}")
            ops_count['user_update'] += 1

    # 1c. Insert production-only real users
    for u in prod_users:
        if u['id'] in SKIP_USERS:
            continue
        email = u['email']
        # Skip if email handled by UUID conflict or already exists
        if email in atlas_user_emails:
            continue
        # Skip if this is one of the conflicting users (already inserted above)
        already_handled = email in [atlas_users[a].get('email') for a in UUID_REMAP.keys() if a in atlas_users]
        if already_handled:
            continue
        # Check if already inserted by checking current DB
        if db.users.find_one({'email': email}):
            continue
        
        new_user = dict(u)
        new_user.pop('_id', None)
        # These users don't have passwords in the API snapshot
        # We need to set a temporary password or handle this
        # Since they were created with passwords on production, we'll need to handle password reset
        # For now, use a bcrypt hash of their known default password
        if not new_user.get('password'):
            import bcrypt
            new_user['password'] = bcrypt.hashpw('12345678'.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')
            log(f"  NOTE: Set default password for {email} (user should reset)")
        
        db.users.insert_one(new_user)
        log(f"  INSERTED prod-only user: {email} ({u['id']}, role: {u.get('role')})")
        ops_count['user_insert'] += 1

    # =========================================================================
    # PHASE 2: COMPANIES
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 2: COMPANIES")
    log("=" * 80)

    # 2a. Remap employer assignments on existing Atlas companies
    for cid, c in atlas_companies.items():
        emp = c.get('assigned_employer_id')
        if emp and emp in UUID_REMAP:
            db.companies.update_one({'id': cid}, {'$set': {'assigned_employer_id': UUID_REMAP[emp]}})
            log(f"  UPDATED company '{c['name']}': employer -> {UUID_REMAP[emp]}")
            ops_count['company_update'] += 1

    # 2b. Update companies that exist in both but prod has employer assignment Atlas doesn't
    for pc in prod_companies:
        if pc['id'] in atlas_companies:
            ac = atlas_companies[pc['id']]
            prod_emp = pc.get('assigned_employer_id')
            atlas_emp = ac.get('assigned_employer_id')
            if prod_emp and not atlas_emp:
                final_emp = UUID_REMAP.get(prod_emp, prod_emp)
                db.companies.update_one({'id': pc['id']}, {'$set': {'assigned_employer_id': final_emp}})
                log(f"  UPDATED company '{pc['name']}': employer set to {final_emp} (from prod)")
                ops_count['company_update'] += 1

    # 2c. Insert production-only real companies (skip TEST, skip duplicate)
    for pc in prod_companies:
        if pc['id'] in atlas_companies:
            continue
        if is_test(pc.get('name', '')):
            continue
        if pc['id'] == DUPLICATE_COMPANY_ID:
            continue
        
        new_comp = dict(pc)
        new_comp.pop('_id', None)
        emp = new_comp.get('assigned_employer_id')
        if emp:
            new_comp['assigned_employer_id'] = UUID_REMAP.get(emp, emp)
        
        db.companies.insert_one(new_comp)
        log(f"  INSERTED company: {pc['name']} ({pc['id']}, employer: {new_comp.get('assigned_employer_id')})")
        ops_count['company_insert'] += 1

    # 2d. Rename canonical company
    db.companies.update_one({'id': CANONICAL_COMPANY_ID}, {'$set': {'name': CANONICAL_COMPANY_NAME}})
    log(f"  RENAMED company {CANONICAL_COMPANY_ID} -> '{CANONICAL_COMPANY_NAME}'")
    ops_count['company_update'] += 1

    # =========================================================================
    # PHASE 3: TEAMS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 3: TEAMS")
    log("=" * 80)

    for t in db.teams.find({}, {'_id': 0}):
        emp = t.get('employer_id', '')
        if emp in UUID_REMAP:
            db.teams.update_one({'id': t['id']}, {'$set': {'employer_id': UUID_REMAP[emp]}})
            log(f"  UPDATED team '{t['name']}': employer_id -> {UUID_REMAP[emp]}")
            ops_count['team_update'] += 1

    # =========================================================================
    # PHASE 4: JOBS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 4: JOBS")
    log("=" * 80)

    for pj in prod_jobs:
        if pj['id'] in atlas_job_ids:
            continue
        if pj['id'] in SKIP_JOBS:
            log(f"  SKIP (user decision): {pj['title']} ({pj['id']})")
            continue
        if is_test(pj.get('title', '')):
            continue
        
        new_job = dict(pj)
        new_job.pop('_id', None)
        # Remap company_id if duplicate
        if new_job.get('company_id') == DUPLICATE_COMPANY_ID:
            new_job['company_id'] = CANONICAL_COMPANY_ID
        
        db.jobs.insert_one(new_job)
        final_job_ids.add(pj['id'])
        log(f"  INSERTED job: {pj['title']} ({pj['id']})")
        ops_count['job_insert'] += 1

    # =========================================================================
    # PHASE 5: CANDIDATE BANK
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 5: CANDIDATE BANK")
    log("=" * 80)

    inserted_cb = 0
    for pc in prod_candidates:
        if pc['id'] not in atlas_cb_ids:
            new_cand = dict(pc)
            new_cand.pop('_id', None)
            db.candidate_bank.insert_one(new_cand)
            final_cb_ids.add(pc['id'])
            inserted_cb += 1
    
    log(f"  INSERTED {inserted_cb} production-only candidates")
    ops_count['cb_insert'] = inserted_cb

    # =========================================================================
    # PHASE 6: APPLICATIONS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 6: APPLICATIONS")
    log("=" * 80)

    # 6a. Clean Atlas orphaned applications
    orphans_deleted = 0
    for a in db.applications.find({}, {'_id': 0}):
        job_ok = not a.get('job_id') or a['job_id'] in final_job_ids
        cand_ok = not a.get('candidate_id') or a['candidate_id'] in final_cb_ids
        if not job_ok or not cand_ok:
            db.applications.delete_one({'id': a['id']})
            orphans_deleted += 1
            log(f"  DELETED orphan app: {a['id']}")
    
    ops_count['app_delete'] = orphans_deleted
    log(f"  Total orphaned apps cleaned: {orphans_deleted}")

    # 6b. Insert production-only applications
    inserted_apps = 0
    skipped_apps = 0
    for pa in prod_apps:
        if pa['id'] in atlas_app_ids:
            continue
        
        job_id = pa.get('job_id', '')
        cand_id = pa.get('candidate_id', '')
        
        # Skip if job is explicitly skipped or test
        if job_id in SKIP_JOBS:
            skipped_apps += 1
            continue
        
        # Check final validity
        job_exists = job_id in final_job_ids
        cand_exists = cand_id in final_cb_ids
        
        if job_exists and cand_exists:
            new_app = dict(pa)
            new_app.pop('_id', None)
            db.applications.insert_one(new_app)
            inserted_apps += 1
        else:
            skipped_apps += 1
    
    ops_count['app_insert'] = inserted_apps
    log(f"  INSERTED {inserted_apps} production-only applications")
    log(f"  Skipped {skipped_apps} (orphan/test references)")

    # =========================================================================
    # PHASE 7: COMMERCIALS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 7: COMMERCIALS")
    log("=" * 80)

    for pc in prod_commercials:
        if pc['id'] not in atlas_comm_ids:
            new_comm = dict(pc)
            new_comm.pop('_id', None)
            # Remap company if duplicate
            if new_comm.get('company_id') == DUPLICATE_COMPANY_ID:
                new_comm['company_id'] = CANONICAL_COMPANY_ID
            db.commercials.insert_one(new_comm)
            log(f"  INSERTED commercial: {pc['id']} (company: {new_comm.get('company_id')})")
            ops_count['comm_insert'] += 1

    # =========================================================================
    # POST-MERGE VALIDATION
    # =========================================================================
    log("\n" + "=" * 80)
    log("POST-MERGE DOCUMENT COUNTS")
    log("=" * 80)

    post_counts = {}
    for col in ['users', 'companies', 'teams', 'jobs', 'applications', 'candidate_bank', 'commercials']:
        c = db[col].count_documents({})
        post_counts[col] = c
        delta = c - pre_counts[col]
        status = "OK" if delta >= 0 or col == 'applications' else "WARN"
        log(f"  {col:<20} {pre_counts[col]:<8} -> {c:<8} (delta: {'+' if delta >= 0 else ''}{delta}) [{status}]")

    # Operations summary
    log("\n--- Operations Executed ---")
    for k, v in ops_count.items():
        log(f"  {k}: {v}")

    client.close()

    # Write execution log
    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(log_lines))
    print(f"\nExecution log written to: {REPORT_PATH}")


if __name__ == '__main__':
    main()
