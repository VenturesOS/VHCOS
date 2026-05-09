# Phase 54.12 + 54.13 — Pipeline perf wins (3 in one PR)
**Date:** 2026-05-09
**Type:** Backend perf + cache control
**Status:** ✅ Built & verified — pending EC2 deploy

## Goals (user-prioritized backlog from Phase 54.11 finish)
1. Active cache invalidation on stage drag-drops so changes are
   instant instead of waiting up to 60 s.
2. Split filter dropdowns into a separate endpoint (loaded once on mount).
3. Trim heavy unused fields + enable wire-level gzip.
4. (deferred) per-stage pagination — bigger refactor with frontend
   work; will land as a separate phase.

## Implementation summary

### Active cache invalidation (54.11.b)
New helper `cache.invalidate_pipeline_cache()` clears both data and
filter caches by pattern. Called by every pipeline-affecting write:
- `PUT /applications/{id}` (stage moves, edits)
- `DELETE /applications/{id}` (remove from pipeline)
- `POST /applications/{id}/notes` (note adds)
- `PUT /applications/{id}/details` (revenue/salary edits)

Hooked via a small private helper `_bust_pipeline_cache()` in
`routes/applications.py` so future write endpoints just call one line.

### Split filter dropdowns endpoint (54.12)
New `GET /admin/pipeline/filters` returns ONLY `{employers, recruiters,
teams, jobs}`. Cached 5 min per `(employer_id)` tuple — these change
slowly. Frontend calls it ONCE on mount + when employer cascade changes.

The data endpoint now accepts `?include_filters=false` and skips the
filter computation entirely when set. Saves ~300 ms per filter click
(no more re-querying employers/recruiters/teams on every data fetch).

Cache key bumped `v1 → v2` so old keys don't get returned with the new
schema.

### Field trimming + gzip (54.13)
- Removed `industry`, `education`, `ug_course`, `headline` from per-app
  payload — none are rendered in the kanban view (verified by grepping
  the JSX). Fetch on demand from `/candidates/{id}` if any future
  detail dialog needs them.
- Added `GZipMiddleware(minimum_size=500)` to FastAPI. Auto-compresses
  any response > 500 bytes when the client sends `Accept-Encoding: gzip`
  (every browser does).

## Verified (workspace pod)

### Wire size
- BEFORE: `/admin/pipeline` = **2,487,728 B** (2.5 MB)
- AFTER (compressed): **266,611 B** (260 KB) — **9.3× smaller, 89% reduction**

### Latency
- Filters endpoint warm: ~1.7-3 s cold, **~ms warm hits** thereafter
- Pipeline data warm: 2.7 s (down from 3-4 s; floor is now Python
  serialization of 1,914 enriched application dicts)
- Stage drag-drop now visible **instantly** (was up to 60 s lag)

### Network impact (typical office connection 10–50 Mbps)
- Old: 2.5 MB ÷ 25 Mbps = **800 ms** of pure download time
- New: 260 KB ÷ 25 Mbps = **80 ms** of pure download time
- Real-world filter click feels ~700 ms faster on top of the cache hit
  win.

## Files Changed
### Backend
- `backend/services/cache.py` — `invalidate_pipeline_cache()` helper
- `backend/routes/applications.py` — `_bust_pipeline_cache()` calls
  in 4 write endpoints + helper definition
- `backend/routes/admin.py`
  - new `GET /admin/pipeline/filters` (cached 5 min)
  - `?include_filters=false` flag on existing endpoint
  - cache key bumped to v2
  - dropped 4 unused fields (industry/education/ug_course/headline)
- `backend/server.py` — `GZipMiddleware`

### Frontend
- `frontend/src/pages/admin/AdminPipelinePage.jsx`
  - new `loadFilters()` callback (separate from `loadPipeline()`)
  - data calls now include `include_filters: false`
- `frontend/src/lib/api.js` — `adminAPI.getPipelineFilters()`

## Deploy (EC2)
```bash
cd /home/ubuntu/vhc-platform && \
  git pull --rebase origin main && \
  cd frontend && yarn build && cd .. && \
  sudo systemctl restart gunicorn
```
No new Python deps (gzip middleware ships with Starlette/FastAPI).

## Future wins (separate phases)
- **Per-stage pagination** — return only top 50 per stage with a
  "load more" trigger. Would shrink payload by another ~80% for
  organizations with thousands of applications. Needs frontend kanban
  card lazy-load behaviour.
- **WebSocket push** — instead of cache invalidation + reload, push
  stage changes to all connected admins. Eliminates the reload entirely.
- **Materialized view** — precompute the entire pipeline doc on every
  app write (similar to React's getSnapshot). Feels like overkill for
  current scale but is the ultimate ceiling.
