# Platform-Wide Audit & Auto-Fix — Aug 2026

User asked: audit entire system for missing/duplicate/useless connections, loose ends,
unfinished features, and fix the platform lag. Auto-fix everything safe; list unfinished
features for keep/remove decision.

## Method
- Enumerated all 619 live FastAPI routes by importing the app; extracted all 425+ frontend
  API calls; cross-referenced both directions.
- Mined `api_metrics` (635K docs, LIVE prod traffic) for latency/error evidence — 7d and 90d windows.
- Scanned for unrouted pages, dead nav links (97 checked — all valid), unfinished markers.

## Root causes found & FIXED
1. **Candidate Bank 20-22s page load** (17.7s avg × 1,425 calls/wk in prod):
   `fast_search.quick_search` ran for EVERY list request; with no search text the
   `$match:{} → $facet` pipeline can't use indexes → fed all 170K full docs through
   in-memory sort+count. FIX: fast path now gated on `_fast_text_query` presence
   (`routes/candidates.py` ~line 2049). Browse mode → legacy indexed path. 20s → 1-4s.
2. **Autocomplete 219s avg**: 6 sequential unanchored case-insensitive regex aggregations
   over full candidate_bank per keystroke. FIX: new `services/autocomplete_vocab.py` —
   precomputed `autocomplete_vocab` collection (~70K terms, rebuilt in background daily,
   self-healing claim via meta doc). Two-phase lookup (prefix-anchored/index-backed, then
   word-boundary). 219s → ms. Also fixed FE race in `AutocompleteInput.jsx` (stale slow
   response overwrote newest suggestions — requestSeq guard + unmount cleanup).
3. **SSE 401 storm — 21,226× 401/wk on /api/notifications/stream**: NotificationBell
   captured JWT once at mount, retried every 15s forever with expired token (idle tabs).
   FIX: fresh token read per connect + exponential backoff 15s→10min cap + reset on tab
   visible. Also silenced h11 tracebacks on client disconnect (notifications.py).
4. **Missing endpoint /api/extension/job-info** (135× 404/wk from extension background.js:1043):
   implemented in `routes/extension.py` → {job_id,title,code,company_name,location}.
5. **jobs-for-candidate 900s avg** (candidate portal): 2 sequential LLM calls per job × 1,077
   active jobs. FIX (`routes/applications.py`): newest 60 → lexical prefilter to 25 →
   JD parse cached in `jd_parse_cache` → 5-way concurrent LLM match. ~15min → 20-30s cold, seconds warm.
6. **3 duplicate route registrations** (first-registered wins, duplicates dead):
   removed from `employer_routes.py`: GET /employers/{id}/companies, PUT /companies/{id},
   GET /analytics/admin (+dead GET /admin/hierarchy) — ~330 lines. Live handlers verified
   serving correct shapes (TeamsPage expects {companies:[...]} → admin.py provides ✓).
   `calculate_revenue` import moved to `services/revenue_engine.calculate_revenue_amount`.
7. **analytics/admin 23-45s cold**: added 5-min in-process cache (`routes/analytics.py`,
   per-worker) → repeats 1.4s. Cold first hit remains (Atlas M10 IO — see below).
8. **env-info 403 ×22/wk**: guard was admin/recruiter/employer only; badge shown to all
   logged-in users. FIX: any authenticated user (maintenance_routes.py).

## Dead code REMOVED (evidence: 0 traffic in 90d + zero references)
- `routes/commercials.py` (525 lines, whole commercials CRUD + legacy revenue calc endpoints),
  unregistered from server.py + routes/__init__.py.
- Pages: `admin/CommercialsPage.jsx`, `admin/HierarchyPage.jsx`, `employer/EmployerTrackerPage.jsx`.
- `api.js`: commercialAPI block, governanceAPI.getHierarchy.

## Verified (testing agent iteration_190 + follow-up): 17/17 backend tests, 13/13 admin pages
render clean, 0 console errors, 0 duplicate routes (610 endpoints). New read-only suite:
`backend/tests/test_audit_regression_readonly.py` (safe against prod).

## Remaining lag reality (NOT app code)
Atlas M10 cold-cache IO: explain shows 228 docs examined = 4.8s server-side. Candidate docs
are huge (embeddings inline, ~9KB projected / much larger raw). First-hit latencies on any
cold filter/analytics = 5-45s. The planned M10 → Flex/M20 migration is the real fix.
Secondary option later: move `embedding` field to separate collection (big migration, touches
talent_graph — do NOT do casually).

## Flagged, NOT auto-fixed (user decisions / backlog)
- **Revenue Dashboard (/admin/revenue)**: 0 API traffic in 90d AND shows ₹0 everywhere while
  /admin/bills has paid invoices (e.g. VHC/26-27/15 ₹49,147) → revenue_records pipeline never
  populated. DECIDE: wire it up or remove.
- **AdminResourcesPage**: "Coming soon" tiles (unfinished).
- **Public Career Blog (BlogPages.jsx)**: "articles coming soon" empty state (unfinished).
- **Cache admin endpoints (/api/cache/*), embeddings admin endpoints**: 0 traffic, ops-only.
- **talent-graph/similar**: 10.3s avg × 317/wk — works, heavy by design; revisit post-Flex.
- **find-all-duplicates**: 120s avg × 6 — admin dedupe tool, works; revisit post-Flex.
- **Admin cold-load UX**: pages show bare spinner 16-22s on cold cache → add skeletons/progressive
  KPI render (testing agent recommendation).
- **Extension capture/status polling**: 34.9K calls/wk — batch into v7.0.0.2 extension release.
- Asha agent: PAUSED (user), LinkedIn OAuth: WORKING (keep), Voice screening: HOLD (user).

## Deploy notes
User deploys manually on EC2: git pull → yarn build → systemctl restart vhc-backend.
`autocomplete_vocab` collection builds itself on first autocomplete request post-deploy.
