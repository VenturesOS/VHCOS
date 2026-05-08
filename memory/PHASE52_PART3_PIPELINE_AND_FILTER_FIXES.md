# Phase 52 (Part 3) — Pipeline Cascade & Candidate Bank Filter Bug Fixes (2026-05-06)

## Bug 1: Admin Pipeline filters didn't cascade

### Symptom
1. Admin selects an Employer → Recruiter dropdown still shows ALL recruiters (50+)
2. Filter combinations were override-only — selecting `employer + recruiter` ignored one of them
3. Job dropdown didn't narrow when employer/recruiter narrowed

### Root cause (`backend/routes/admin.py:get_admin_pipeline`)
- Job filter used `if/elif/elif` cascade — only one filter could be active at a time
- Recruiter list was global (`db.users.find({"role": "recruiter"})`) regardless of selected employer

### Fix
- Job filter now COMBINES (AND) all provided clauses → real intersection
- Recruiter list narrows based on `employer_id` → only recruiters in that employer's teams
- Frontend now resets recruiter+job when employer changes (avoids stale invalid selections)

## Bug 2: Candidate Bank filters silently returned 0 results

Root causes (all in `backend/routes/candidates.py:search_candidates`):

### Bug 2a — Source filter
- Frontend dropdown sent `"extension"` but DB stores `"naukri_extension"`, `"naukri_excel_import"`
- Old regex `^extension$` matched **0 of 19,236 records**
- **Fix:** substring match `extension` → matches all 19,236

### Bug 2b — has_resume="no"
- Used `$in: [None, ""]` which doesn't match MISSING fields
- Most candidates lack `resume_path`/`resume_latex` keys entirely → filter returned 0
- **Fix:** explicit `$exists: false OR $in: [None, ""]` per-field, AND'd

### Bug 2c — contact_hidden="yes"
- Same missing-field issue + Naukri uses placeholder strings ("Not Available", "N/A")
- **Fix:** treat missing keys + placeholder strings as "hidden"

### Bug 2d — captured_before
- Lex string-compare: `"2026-05-15" < "2026-05-15T14:00:..."` → same-day captures excluded
- **Fix:** auto-append `T23:59:59.999999` when only a date is provided

### Bug 2e — mandate_id filter
- Looked at `mandate_id` (scalar) and `source_details.mandate_id` paths
- Actual field is `linked_mandates` (array, set in `extension.py:2318`)
- Old filter returned 0 even on mandates with 497 captured candidates
- **Fix:** added `linked_mandates: $eq` clause to the `$or`

## Verification (run in dev pod)

```python
# Source filter:
OLD (^extension$ exact)   → 0 candidates
NEW (extension substring) → 19236 candidates

# Mandate filter (Logistics Import/Export):
OLD (mandate_id only)     → 0 candidates
NEW (linked_mandates)     → 497 candidates
```

## Files Changed
- `backend/routes/admin.py` — pipeline filter combine logic, cascading recruiter dropdown
- `backend/routes/candidates.py` — 5 filter fixes (source/has_resume/contact_hidden/captured_before/mandate_id)
- `frontend/src/pages/admin/AdminPipelinePage.jsx` — cascade reset handlers

## Deployment on EC2

```bash
ssh ubuntu@<ec2>
cd /home/ubuntu/vhc-platform
git pull --rebase origin main
sudo systemctl restart gunicorn
sleep 5
cd frontend && yarn build       # for the cascade reset handlers
```

## Test Plan (UI)
1. Admin → Pipeline page
2. Select an Employer → Recruiter dropdown should show only that employer's team members
3. Select a Recruiter → Job dropdown should show only their assigned/posted jobs
4. Change Employer → Recruiter and Job auto-reset to "All"
5. Candidate Bank → set "Source = Naukri Extension" → should return your full extension capture pool (was 0)
6. Candidate Bank → set "Has Resume = No" → should return candidates without any resume artifact
7. Candidate Bank → set captured-before date to today → captures from today should appear (was missing)
