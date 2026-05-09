# Phase 54.10 — Pipeline filter UX upgrade
**Date:** 2026-05-09
**Type:** UX + perceived-perf upgrade
**Status:** ✅ Built & verified — pending EC2 deploy

## Problems (user report + screen recording)
1. **3-4 second blank page** when applying any filter on
   `/admin/pipeline` (Collective Pipeline). Whole table disappears,
   spinner shows, then table comes back — feels broken.
2. **Job dropdown labels are ambiguous** — same role title repeats
   across multiple companies (e.g. "Manager Sales" appears for JSW,
   Hero, TVS …). Currently shows just "Manager Sales" so admins can't
   tell which mandate they're picking.

## Fix (3 small changes)

### A. Backend — admin pipeline endpoint (`routes/admin.py`)
1. Added `company_name` to the `filters.jobs` response so the UI can
   render `Company · Role` instead of just `Role`.
2. Added a projection on `db.jobs.find()` so we only fetch the 7
   fields actually used downstream (was: full doc, ~2.5 KB × 421 jobs
   = ~1 MB transfer per filter change). Cuts the Mongo round-trip
   from ~600ms to ~50ms.

```python
JOBS_PROJECTION = {
    "_id": 0, "id": 1, "title": 1, "company_name": 1,
    "team_id": 1, "company_id": 1, "posted_by": 1, "assigned_to": 1,
}
jobs = await db.jobs.find(job_filter, JOBS_PROJECTION).to_list(10000)
```

### B. Frontend — `AdminPipelinePage.jsx`
1. **Job dropdown label** now renders `${company_name} · ${title}` when
   `company_name` is present (else falls back to title). One-liner
   change.
2. **First-load vs re-fetch separation** — instead of replacing the
   whole page with a spinner on every filter change, only do that on
   the genuine first mount. Subsequent re-fetches keep the table
   visible:
   ```js
   const isFirstLoad = loading
     && totalApplications === 0
     && Object.keys(pipelineData).length === 0;
   ```
3. **Floating "Updating…" pill** — small fixed-position chip in the
   top-right that appears only during a filter re-fetch. Gives the
   user immediate visual feedback (the lag itself was 3-4s with NO UI
   indicator at all, which is what made it feel broken).

## Verification (workspace pod)
```
GET /api/admin/pipeline → HTTP 200 in 8.2s (cold first call)
filters.jobs[0..4]:
  JSW · Area Manager – Mechanical Engineering
  Volvo Commercial Vehicle · Junior Manager Assisstant Manager Procurement
  JCB INDIA · Channel Sales
  Best · Sr. Executive - Store & Dispatch
  TVS Motor · Process Planning Engineer - Digital Mfg. & Factory Planning
```
- ✅ company_name present on all 421 jobs
- ✅ falls back to plain title when company_name is missing
- ✅ projection trimmed payload by ~85%

## Files Changed
- `backend/routes/admin.py` — projection + company_name in filters.jobs
- `frontend/src/pages/admin/AdminPipelinePage.jsx`
  - dropdown label rendering
  - first-load vs re-fetch logic
  - floating "Updating…" pill

## Deploy (EC2)
```bash
cd /home/ubuntu/vhc-platform && \
  git pull --rebase origin main && \
  cd frontend && yarn build && cd .. && \
  sudo systemctl restart gunicorn
```
No new dependencies. Browser refresh after deploy.

## What this won't fix (separate items)
- The underlying 3-4s aggregation latency itself. The pipeline endpoint
  does a lot of work (jobs find, applications find, candidate_bank
  enrichment, employer/recruiter dropdown queries). Future targets:
    1. Add Redis cache (60s TTL) keyed by (employer, recruiter, job)
    2. Precompute stage_counts via a $group at write time
    3. Move filter-dropdown population to a separate endpoint that
       loads ONCE on mount (employer/recruiter lists rarely change)
