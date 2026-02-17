#!/usr/bin/env python3
"""
DATABASE CONSOLIDATION DRY-RUN SIMULATION
==========================================
This script simulates the entire migration WITHOUT writing to any database.
It produces a detailed log of every operation that WOULD be performed.

Run: python3 /app/backend/migration_dry_run.py
"""
import json
import os
from pymongo import MongoClient
from datetime import datetime

# --- Configuration ---
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb+srv://vhc_admin:DL4cbb4890@cluster0.vuhdiod.mongodb.net/?retryWrites=true&w=majority')
DB_NAME = 'vhc_talent_os'
PROD_SNAPSHOT_DIR = '/app/backup/production_snapshot_20260218'
REPORT_PATH = '/app/memory/MIGRATION_DRY_RUN_RESULTS.md'

# UUID Conflict Resolution: Option A — Keep Production UUIDs
UUID_REMAP = {
    # Atlas UUID -> Production UUID (for the 4 conflicting users)
    '842077a8-d9e7-4bca-b89e-dce044e630f6': 'eb962d6f-ad6f-454a-bd7b-edc68f8b4ff7',  # admin@vhc.in
    '09d5c0fa-4c11-4951-bcf8-bd223b0b62e2': 'cf36890a-b8fa-47e2-abf3-d4600f04c831',  # ajit@vhc.in
    '58dc5b71-adb6-4a04-9d19-1c3874907230': '839f5e28-f97e-4e0d-ae18-091e0636fa60',  # jatin@vhc.in
    '220bcc65-0f44-4550-b7ef-09bc4ccdb3d7': 'f412d7aa-c3f1-436f-aaea-91600905f486',  # siddharth@vhc.in
}

# Siddharth role override: production UUID + admin role
SIDDHARTH_PROD_UUID = 'f412d7aa-c3f1-436f-aaea-91600905f486'

# Company dedup: Panosonic India (ba188401) + Panasonic (9c1553d8) -> canonical
CANONICAL_COMPANY_ID = '9c1553d8-4ead-4324-bf79-6a3a6c512d44'  # Keep Panasonic
DUPLICATE_COMPANY_ID = 'ba188401-91dc-446d-93c0-d9712b84c230'  # Remove Panosonic India
CANONICAL_COMPANY_NAME = 'Panasonic India'

# Test data patterns to skip
TEST_PATTERNS = ['TEST_', 'Test Job', 'Career Page Test', 'Non-Live Job']

# Production-only users to skip (inactive test accounts)
SKIP_USERS = {
    '096ec385-98a3-4001-9230-dfd79a68353f',  # employer@vhctalent.com
    'f501f248-57c4-4d38-ae9b-febcbe43c133',  # recruiter@vhctalent.com
    '0e82b2aa-9c30-4a06-ab62-6b4336fccf76',  # recruiter2@vhctalent.com
}

log_lines = []

def log(msg, indent=0):
    line = '  ' * indent + msg
    log_lines.append(line)
    print(line)

def load_prod_data(collection_name):
    path = os.path.join(PROD_SNAPSHOT_DIR, f'{collection_name}.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []

def is_test_data(name):
    return any(p in name for p in TEST_PATTERNS)


def main():
    log("=" * 80)
    log("DATABASE CONSOLIDATION — DRY-RUN SIMULATION")
    log(f"Timestamp: {datetime.utcnow().isoformat()}Z")
    log(f"Mode: READ-ONLY SIMULATION (no writes)")
    log("=" * 80)

    # Connect to Atlas (read-only)
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]

    # Load production snapshots
    prod_users = load_prod_data('users')
    prod_companies = load_prod_data('companies')
    prod_jobs = load_prod_data('jobs')
    prod_apps = load_prod_data('applications')
    prod_commercials = load_prod_data('commercials')
    prod_candidates = load_prod_data('candidate_bank')

    # Load Atlas data
    atlas_users = list(db.users.find({}, {'_id': 0}))
    atlas_companies = list(db.companies.find({}, {'_id': 0}))
    atlas_teams = list(db.teams.find({}, {'_id': 0}))
    atlas_jobs = list(db.jobs.find({}, {'_id': 0}))
    atlas_apps = list(db.applications.find({}, {'_id': 0}))
    atlas_commercials = list(db.commercials.find({}, {'_id': 0}))
    atlas_cb_ids = {c['id'] for c in db.candidate_bank.find({}, {'_id': 0, 'id': 1})}

    # Build lookup maps
    atlas_user_by_id = {u['id']: u for u in atlas_users}
    atlas_user_by_email = {u['email']: u for u in atlas_users}
    atlas_company_by_id = {c['id']: c for c in atlas_companies}
    atlas_job_ids = {j['id'] for j in atlas_jobs}
    atlas_app_ids = {a['id'] for a in atlas_apps}

    prod_user_by_id = {u['id']: u for u in prod_users}
    prod_user_by_email = {u['email']: u for u in prod_users}
    prod_company_by_id = {c['id']: c for c in prod_companies}
    prod_job_by_id = {j['id']: j for j in prod_jobs}
    prod_candidate_by_id = {c['id']: c for c in prod_candidates}

    # Counters
    ops = {
        'user_delete': [], 'user_insert': [], 'user_update': [],
        'company_insert': [], 'company_update': [], 'company_delete': [],
        'team_update': [],
        'job_insert': [],
        'app_insert': [], 'app_delete': [], 'app_remap': [],
        'cb_insert': [],
        'comm_insert': [],
        'orphan_cleanup': [],
    }

    # =========================================================================
    # PHASE 1: USERS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 1: USERS")
    log("=" * 80)

    # 1a. UUID Conflict resolution — delete Atlas dupes, insert prod versions
    log("\n--- 1a. UUID Conflict Resolution (Option A: Keep Production UUIDs) ---")
    for atlas_uuid, prod_uuid in UUID_REMAP.items():
        atlas_user = atlas_user_by_id.get(atlas_uuid)
        prod_user = prod_user_by_email.get(atlas_user['email']) if atlas_user else None
        if atlas_user and prod_user:
            log(f"DELETE Atlas user: {atlas_user['email']} (Atlas UUID: {atlas_uuid})", 1)
            ops['user_delete'].append(atlas_uuid)
            
            role = prod_user.get('role', 'employer')
            # Special case: siddharth role override
            if prod_uuid == SIDDHARTH_PROD_UUID:
                role = 'admin'
                log(f"INSERT Prod user: {prod_user['email']} (Prod UUID: {prod_uuid}, role overridden to: admin)", 1)
            else:
                log(f"INSERT Prod user: {prod_user['email']} (Prod UUID: {prod_uuid}, role: {role})", 1)
            ops['user_insert'].append({'id': prod_uuid, 'email': prod_user['email'], 'role': role})

    # 1b. Insert production-only real users (not in Atlas, not test)
    log("\n--- 1b. Production-Only Users ---")
    for u in prod_users:
        if u['id'] in SKIP_USERS:
            log(f"SKIP test user: {u['email']} (inactive)", 1)
            continue
        if u['email'] not in atlas_user_by_email and u['id'] not in [v for v in UUID_REMAP.values()]:
            # Check if this user's email isn't already being handled by UUID conflict
            already_handled = any(
                atlas_user_by_id.get(a_uuid, {}).get('email') == u['email'] 
                for a_uuid in UUID_REMAP.keys()
            )
            if not already_handled:
                log(f"INSERT prod-only user: {u['email']} ({u['id']}, role: {u['role']})", 1)
                ops['user_insert'].append({'id': u['id'], 'email': u['email'], 'role': u['role']})

    # 1c. Remap Atlas references from old UUIDs to new UUIDs
    log("\n--- 1c. Remap created_by References ---")
    for au in atlas_users:
        created_by = au.get('created_by', '')
        if created_by in UUID_REMAP:
            new_id = UUID_REMAP[created_by]
            log(f"UPDATE user {au['email']}: created_by {created_by} -> {new_id}", 1)
            ops['user_update'].append({'id': au['id'], 'field': 'created_by', 'old': created_by, 'new': new_id})

    # =========================================================================
    # PHASE 2: COMPANIES
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 2: COMPANIES")
    log("=" * 80)

    # 2a. Update employer assignments on companies in both DBs
    log("\n--- 2a. Update Employer Assignments (remap Atlas UUIDs to Prod UUIDs) ---")
    for c in atlas_companies:
        emp_id = c.get('assigned_employer_id')
        if emp_id and emp_id in UUID_REMAP:
            new_emp = UUID_REMAP[emp_id]
            log(f"UPDATE company '{c['name']}' ({c['id']}): employer {emp_id} -> {new_emp}", 1)
            ops['company_update'].append({'id': c['id'], 'field': 'assigned_employer_id', 'old': emp_id, 'new': new_emp})

    # 2b. Insert production-only REAL companies (skip TEST_)
    log("\n--- 2b. Production-Only Companies ---")
    for c in prod_companies:
        if c['id'] in atlas_company_by_id:
            # Company exists in both — check for employer update needed
            atlas_c = atlas_company_by_id[c['id']]
            prod_emp = c.get('assigned_employer_id')
            atlas_emp = atlas_c.get('assigned_employer_id')
            if prod_emp and not atlas_emp:
                # Production has employer assignment, Atlas doesn't — use prod value
                # But remap if it's a conflicting UUID
                final_emp = UUID_REMAP.get(prod_emp, prod_emp)
                log(f"UPDATE company '{c['name']}' ({c['id']}): set employer to {final_emp} (from prod)", 1)
                ops['company_update'].append({'id': c['id'], 'field': 'assigned_employer_id', 'old': None, 'new': final_emp})
            continue
        
        if is_test_data(c.get('name', '')):
            log(f"SKIP test company: {c['name']} ({c['id']})", 1)
            continue

        if c['id'] == DUPLICATE_COMPANY_ID:
            log(f"SKIP duplicate company: {c['name']} ({c['id']}) — will merge into '{CANONICAL_COMPANY_NAME}'", 1)
            continue

        # Remap employer ID if needed
        emp_id = c.get('assigned_employer_id')
        final_emp = UUID_REMAP.get(emp_id, emp_id) if emp_id else None
        log(f"INSERT prod-only company: {c['name']} ({c['id']}, employer: {final_emp})", 1)
        ops['company_insert'].append({'id': c['id'], 'name': c['name'], 'employer': final_emp})

    # 2c. Company dedup: Panasonic/Panosonic India
    log("\n--- 2c. Company Dedup: Panosonic India -> Panasonic India ---")
    log(f"RENAME company {CANONICAL_COMPANY_ID}: 'Panasonic' -> '{CANONICAL_COMPANY_NAME}'", 1)
    log(f"REPOINT all references from {DUPLICATE_COMPANY_ID} to {CANONICAL_COMPANY_ID}", 1)
    ops['company_update'].append({'id': CANONICAL_COMPANY_ID, 'field': 'name', 'old': 'Panasonic', 'new': CANONICAL_COMPANY_NAME})

    # Check production data for references to the duplicate company
    dup_refs = {'jobs': 0, 'apps': 0, 'commercials': 0}
    for j in prod_jobs:
        if j.get('company_id') == DUPLICATE_COMPANY_ID:
            dup_refs['jobs'] += 1
    for a in prod_apps:
        if a.get('company_id') == DUPLICATE_COMPANY_ID:
            dup_refs['apps'] += 1
    for c in prod_commercials:
        if c.get('company_id') == DUPLICATE_COMPANY_ID:
            dup_refs['commercials'] += 1
    log(f"References to duplicate company: jobs={dup_refs['jobs']}, apps={dup_refs['apps']}, commercials={dup_refs['commercials']}", 1)

    # =========================================================================
    # PHASE 3: TEAMS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 3: TEAMS")
    log("=" * 80)

    log("\n--- 3a. Remap Team Employer IDs ---")
    for t in atlas_teams:
        emp_id = t.get('employer_id', '')
        if emp_id in UUID_REMAP:
            new_emp = UUID_REMAP[emp_id]
            log(f"UPDATE team '{t['name']}' ({t['id']}): employer_id {emp_id} -> {new_emp}", 1)
            ops['team_update'].append({'id': t['id'], 'field': 'employer_id', 'old': emp_id, 'new': new_emp})
        
        # Check company_ids for any that need remapping
        cids = t.get('company_ids', [])
        for cid in cids:
            cid_str = str(cid)
            if cid_str == DUPLICATE_COMPANY_ID:
                log(f"UPDATE team '{t['name']}': company_id {DUPLICATE_COMPANY_ID} -> {CANONICAL_COMPANY_ID}", 1)

    # =========================================================================
    # PHASE 4: JOBS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 4: JOBS")
    log("=" * 80)

    log("\n--- 4a. Production-Only Jobs ---")
    for j in prod_jobs:
        if j['id'] in atlas_job_ids:
            continue
        title = j.get('title', '')
        if is_test_data(title):
            log(f"SKIP test job: {title} ({j['id']})", 1)
            continue
        # Remap company_id if it's the duplicate
        comp_id = j.get('company_id')
        if comp_id == DUPLICATE_COMPANY_ID:
            comp_id = CANONICAL_COMPANY_ID
            log(f"INSERT prod-only job (remapped company): {title} ({j['id']}, company: {comp_id})", 1)
        else:
            log(f"INSERT prod-only job: {title} ({j['id']}, company: {comp_id})", 1)
        ops['job_insert'].append({'id': j['id'], 'title': title, 'company_id': comp_id})

    # =========================================================================
    # PHASE 5: CANDIDATE BANK
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 5: CANDIDATE BANK")
    log("=" * 80)

    prod_only_candidates = []
    for c in prod_candidates:
        if c['id'] not in atlas_cb_ids:
            prod_only_candidates.append(c)

    # Check for email duplicates
    atlas_cb_emails = set()
    for c in db.candidate_bank.find({}, {'_id': 0, 'email': 1}):
        if c.get('email'):
            atlas_cb_emails.add(c['email'].lower().strip())

    email_dupes = 0
    for c in prod_only_candidates:
        email = (c.get('email', '') or '').lower().strip()
        if email and email in atlas_cb_emails:
            email_dupes += 1
            log(f"WARN: Prod-only candidate {c['id']} has duplicate email in Atlas: {email}", 1)
        else:
            ops['cb_insert'].append(c['id'])

    log(f"\nTotal prod-only candidates: {len(prod_only_candidates)}", 1)
    log(f"Email duplicates found: {email_dupes}", 1)
    log(f"Will INSERT: {len(ops['cb_insert'])} candidates", 1)

    # =========================================================================
    # PHASE 6: APPLICATIONS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 6: APPLICATIONS")
    log("=" * 80)

    # 6a. Clean Atlas orphaned applications
    log("\n--- 6a. Atlas Orphaned Application Cleanup ---")
    final_job_ids = atlas_job_ids.copy()
    for ji in ops['job_insert']:
        final_job_ids.add(ji['id'])
    
    final_cb_ids = atlas_cb_ids.copy()
    for ci in ops['cb_insert']:
        final_cb_ids.add(ci)

    for a in atlas_apps:
        job_ok = not a.get('job_id') or a['job_id'] in final_job_ids
        cand_ok = not a.get('candidate_id') or a['candidate_id'] in final_cb_ids
        if not job_ok or not cand_ok:
            reasons = []
            if not job_ok:
                reasons.append(f"job_id={a.get('job_id')} not found")
            if not cand_ok:
                reasons.append(f"candidate_id={a.get('candidate_id')} not found")
            log(f"DELETE orphaned app: {a['id']} ({', '.join(reasons)})", 1)
            ops['orphan_cleanup'].append({'id': a['id'], 'reasons': reasons})

    # 6b. Insert production-only applications
    log("\n--- 6b. Production-Only Applications ---")
    prod_only_apps = [a for a in prod_apps if a['id'] not in atlas_app_ids]
    
    skipped_apps = 0
    for a in prod_only_apps:
        job_id = a.get('job_id', '')
        cand_id = a.get('candidate_id', '')
        
        # Check if job is a test job
        prod_job = prod_job_by_id.get(job_id, {})
        if prod_job and is_test_data(prod_job.get('title', '')):
            skipped_apps += 1
            continue
        
        # Check if job and candidate exist in final merged state
        job_exists = job_id in final_job_ids
        cand_exists = cand_id in final_cb_ids
        
        if job_exists and cand_exists:
            ops['app_insert'].append(a['id'])
        elif not job_exists and not cand_exists:
            log(f"SKIP app {a['id']}: both job ({job_id}) and candidate ({cand_id}) missing", 2)
            skipped_apps += 1
        elif not job_exists:
            log(f"SKIP app {a['id']}: job ({job_id}) missing from final DB", 2)
            skipped_apps += 1
        elif not cand_exists:
            log(f"SKIP app {a['id']}: candidate ({cand_id}) missing from final DB", 2)
            skipped_apps += 1

    log(f"\nProd-only applications: {len(prod_only_apps)}", 1)
    log(f"Will INSERT: {len(ops['app_insert'])}", 1)
    log(f"Skipped (test/orphan): {skipped_apps}", 1)

    # =========================================================================
    # PHASE 7: COMMERCIALS
    # =========================================================================
    log("\n" + "=" * 80)
    log("PHASE 7: COMMERCIALS")
    log("=" * 80)

    atlas_comm_ids = {c['id'] for c in atlas_commercials}
    for c in prod_commercials:
        if c['id'] not in atlas_comm_ids:
            comp_id = c.get('company_id', '')
            if comp_id == DUPLICATE_COMPANY_ID:
                comp_id = CANONICAL_COMPANY_ID
            log(f"INSERT prod-only commercial: {c['id']} (company: {comp_id})", 1)
            ops['comm_insert'].append(c['id'])

    # =========================================================================
    # SUMMARY
    # =========================================================================
    log("\n" + "=" * 80)
    log("DRY-RUN SUMMARY")
    log("=" * 80)

    log("\n--- Operations Count ---")
    log(f"Users:       DELETE {len(ops['user_delete'])}, INSERT {len(ops['user_insert'])}, UPDATE {len(ops['user_update'])}")
    log(f"Companies:   INSERT {len(ops['company_insert'])}, UPDATE {len(ops['company_update'])}, DELETE {len(ops['company_delete'])}")
    log(f"Teams:       UPDATE {len(ops['team_update'])}")
    log(f"Jobs:        INSERT {len(ops['job_insert'])}")
    log(f"Candidates:  INSERT {len(ops['cb_insert'])}")
    log(f"Applications: INSERT {len(ops['app_insert'])}, DELETE (orphans) {len(ops['orphan_cleanup'])}")
    log(f"Commercials: INSERT {len(ops['comm_insert'])}")

    # Final expected counts
    final_users = len(atlas_users) - len(ops['user_delete']) + len(ops['user_insert'])
    final_companies = len(atlas_companies) + len(ops['company_insert'])
    final_teams = len(atlas_teams)
    final_jobs = len(atlas_jobs) + len(ops['job_insert'])
    final_apps = len(atlas_apps) - len(ops['orphan_cleanup']) + len(ops['app_insert'])
    final_cb = len(atlas_cb_ids) + len(ops['cb_insert'])
    final_comm = len(atlas_commercials) + len(ops['comm_insert'])

    log("\n--- Expected Final Document Counts ---")
    log(f"{'Collection':<20} {'Before':<10} {'After':<10} {'Change':<10}")
    log("-" * 50)
    log(f"{'users':<20} {len(atlas_users):<10} {final_users:<10} {'+' + str(final_users - len(atlas_users)) if final_users >= len(atlas_users) else str(final_users - len(atlas_users))}")
    log(f"{'companies':<20} {len(atlas_companies):<10} {final_companies:<10} +{final_companies - len(atlas_companies)}")
    log(f"{'teams':<20} {len(atlas_teams):<10} {final_teams:<10} 0 (updates only)")
    log(f"{'jobs':<20} {len(atlas_jobs):<10} {final_jobs:<10} +{final_jobs - len(atlas_jobs)}")
    log(f"{'applications':<20} {len(atlas_apps):<10} {final_apps:<10} {'+' + str(final_apps - len(atlas_apps)) if final_apps >= len(atlas_apps) else str(final_apps - len(atlas_apps))}")
    log(f"{'candidate_bank':<20} {len(atlas_cb_ids):<10} {final_cb:<10} +{final_cb - len(atlas_cb_ids)}")
    log(f"{'commercials':<20} {len(atlas_commercials):<10} {final_comm:<10} +{final_comm - len(atlas_commercials)}")

    log("\n--- Rollback Commands ---")
    log("mongorestore --uri='mongodb+srv://vhc_admin:DL4cbb4890@cluster0.vuhdiod.mongodb.net/vhc_talent_os' \\")
    log("  --drop --dir='/app/backup/atlas_pre_merge_20260218/vhc_talent_os'")
    log("Estimated rollback time: < 5 minutes")

    client.close()

    # Write report
    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(log_lines))
    print(f"\n\nFull report written to: {REPORT_PATH}")


if __name__ == '__main__':
    main()
