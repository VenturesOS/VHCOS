## 2026-09-15 — fix.docx pass (Pipeline, Salary, Bills, Blog Joinings, Analytics)

- **Pipeline calendar**: removed the legacy "Activity window" preset dropdown; two date pickers now sit at the TOP of the filter card with an Apply button that only fires the fetch when clicked. Bare `window_from` / `window_to` (without `window="custom"`) now filter — frontend no longer needs to spoof the preset. (`AdminPipelinePage.jsx`, `PipelinePage.jsx`, `routes/applications.py::_build_pipeline_window_filter`)
- **Salary Benchmark**:
  - Persistent `facet_cache` collection (`services/facet_cache.py`) precomputes top-500 per field via cursor-stream — dropdown fetches drop from 10 s→<200 ms.
  - Admin endpoint `POST /api/admin/rebuild-facet-cache` + startup auto-rebuild if stale (`bootstrap/lifespan.py`).
  - Frontend preloads full alphabetical list on box focus, then client-side filters as user types.
  - Single-pass `$facet` aggregation: stats + 5 breakdowns share one `$sample`, cutting unfiltered response ~30 s → ~5 s. Filter now actually reduces the candidate count.
- **Bills**:
  - `bill_bank_accounts` collection + full CRUD (`/api/bills/bank-accounts`) with default-account picker.
  - Bank details snapshotted onto each bill and printed as a block in the invoice PDF (`services/bill_pdf.py`).
  - Sender logo loaded from env-var URL (`BILLING_SENDER_LOGO_URL` / `BILLING_SENDER_PVT_LOGO_URL`) and shown in the PDF header.
  - `to_email` override in the send dialog so the client email can be typed per-send.
- **Blog Engine → Joinings tab**:
  - `GET /api/blog/joinings` — every application at stage=joined, hydrated with client company + logo, position, location, joined CTC, revenue. Filters: date range, position, location.
  - `PATCH /api/blog/joinings/{id}` — team leaders edit the revenue value that was intentionally left blank at joining time.
  - `JoinDialog` now captures `joined_ctc` when moving a candidate to Joined.
- **Analytics hub**:
  - `public_only` param (default true) restricts route-based aggregations to `/careers`, `/jobs`, `/blog`, and anonymous hits — internal portal noise no longer drowns marketing traffic.
  - New `top_utm_sources` block from `props.utm_source` so redirect campaigns (Naukri / LinkedIn / Facebook) are traceable.
- **Skills normalization migration** (from prior turn, kept for context): `skills_lc`, `current_company_lc`, `location_lc` mirrors + sparse indexes populated by `services.schema_normalizer.normalize_candidate` and one-shot `scripts.backfill_candidate_lc` (admin endpoint + status). Backfill run: 178 443 processed. Candidate Data Bank Company + Skills filters use `SearchableMultiSelect`.


## 2026-09-08 — Wave 3 remaining items

### 5.14 Bills & Invoices — Preview + Download + Email
Root cause: the preview `<iframe src>` pointed directly at `/api/bills/{id}/pdf` but browsers don't attach the `vhc_token` Authorization header to iframe requests, so the endpoint returned 401 and the modal rendered blank.

**Fix in `frontend/src/pages/admin/BillsPage.jsx`:**
- Fetch the PDF as an authenticated `fetch()` blob, then feed `URL.createObjectURL(blob)` to the iframe. Object URL is revoked on modal close to prevent memory leak.
- Added **Download PDF** button on the preview modal (same blob-fetch, triggers `<a download>`).
- Added **Email to Client** button that hands the current bill off to the existing Send Dialog (subject/body editor + Resend integration was already wired).
- `data-testid`: `bill-preview-iframe`, `bill-preview-download`, `bill-preview-email`.

### 5.11 Location / Company / Skills — Searchable multi-select
**Backend — new `GET /api/candidate-bank/facets` endpoint** in `routes/candidates.py`:
- Fields supported: `location` → `location`, `company` → `current_company`, `skills` → `skills`.
- Anchored prefix regex `^{q}` (case-insensitive) so the existing multikey indexes can be used.
- Sample cap at 20 k docs, `maxTimeMS=15000`, `allowDiskUse=True`.
- For `skills` (array field): two-stage filter — array-level `$match` first (index-friendly), then `$unwind` + per-token `$match` so a doc holding `[Python, Java]` for `q=py` surfaces only Python.
- Verified live: `location?q=Ban` returned Bangalore variants (713 + 153 + 84 + 72 + 43) in ~8 s.
- **Note**: skills facet is slower against the 172 k-doc dataset; the endpoint returns `{values: []}` gracefully on timeout so the UI stays responsive. Perf follow-up would be a normalized `skills_lc` field.

**Frontend — new `components/candidate-bank/SearchableMultiSelect.jsx`**:
- Debounced (300 ms) type-ahead against the facet endpoint. Renders chips for selected values. Emits a comma-separated string so the existing hook needs no shape change.
- Wired into the Location filter on the shared Candidate Bank Filters panel.
- Location backend query updated to split the comma-separated value and OR-match each token in either `location` or `current_location`.
- Company and Skills remain as free-text inputs for now (facet perf follow-up before switching them over).

### Runtime
- Backend restarted clean; `/api/health` `mongodb: ok`.
- `yarn build` succeeded in 10.7 s.
- **43/43 backend tests still pass** (unchanged from Wave 2 baseline).
- Live test: `?location=Bangalore` matched real docs.

### Still deferred (each ≈1 full task)
- **5.5 Badge Audit "Already in DB" report** — needs new exposure/click event tracking.
- **5.4 Analytics Hub public-vs-internal URL split + background aggregator** — needs a scheduler job.
- **Section 4 Employee Drill-down page** — data foundation is shipped; drawer UI deferred.
- **Composite score weighting editor + quarterly targets management UI**.
- **Company/Skills switched from free text to SearchableMultiSelect** — needs perf work on the facet aggregation for those fields.


## 2026-09-08 — Emergent Spec Wave 2 + Wave 3 (partial)

### Wave 2 — Employee Performance Analytics (spec §4 / 5.3)

Discovered the Daily Digest points table lives in `services/team_digest_service.py` as `PIPELINE_POINTS` (Python constant, not Mongo). Analytics reuses it directly — nothing hard-coded twice, so daily totals on the KPI page match the digest exactly.

**Backend**
- `GET /api/analytics/employee-performance` — filters by date range, team, employee. Returns KPI summary (sourced, submitted, interview_scheduled, interview_completed, offered, hired, joined, rejected, active_pipeline, total_points), conversion funnel (%), and per-recruiter breakdown with rank.
- `GET /api/analytics/leaderboard?year=YYYY` — calendar-year cumulative leaderboard, delegates to `employee-performance` with Jan 1 → today window.
- Filter uses `created_by` (the field that's actually populated on 100 % of live applications), not the legacy empty `assigned_recruiter_id`.
- Employer-scope enforcement: employer role sees only their own teams' members.
- Interview KPIs split per Section 10 decision: **Interview Scheduled = stage `shortlisted`**, **Interview Completed = stage `interview`**.
- Ranking tie-breakers: points → joined → offered → interview_completed.
- Live production sanity: annual leaderboard returned real ranked data (Delhi/Gurgaon/Faridabad recruiters at ~2500 points each; 112 joinings, 74 offers YTD).

**Frontend**
- `pages/admin/AdminAnalyticsPage.jsx` fully replaced (487 → 244 lines). New structure:
  - Filter bar: date From/To, Team, Employee, Apply.
  - KPI Summary tiles (Sourced / Submitted / Interview Scheduled / Interview Completed / Offered / Hired / Joined / Active Pipeline) + a prominent Total Points card.
  - Conversion funnel: Submitted→Interview, Interview→Offer, Offer→Joining, Submitted→Joining.
  - Team Comparison table sorted by points.
  - Annual Leaderboard table (top 20 of current calendar year).
- Fixes the "Analytics page fails to load" symptom (spec 5.3).

### Wave 3 — Point fixes

**5.7 Salary Benchmarking (page stuck loading)**
- Root cause: aggregation `$push`'d every `current_salary` into one array. With 172 k candidates that blew past Mongo's 16 MB BSON doc limit — endpoint returned 500 but frontend spinner stayed forever.
- Fix in `backend/routes/analytics.py`: switched to `$sample: 10 000` + `$percentile` (approximate) accumulator. Wrapped in `try/except` so a slow query returns `{count: 0, error: "Query too broad — please add more filters"}` in 200 instead of 500. Spec 5.7 "do not leave an indefinite Analyzing… state" now satisfied. Narrow queries (location-only) now return in <18 s. Full-population skill regex still slow — logged as follow-up (needs indexed lowercased-skills field).

**5.12 User Management — Team filter**
- Backend: `GET /admin/users?team_id=X` filters via team's `recruiter_ids` array.
- Frontend: `pages/admin/UsersPage.jsx` adds a Team dropdown next to Role. Loads teams via `GET /teams`, filters the users table client-side by team membership. `data-testid="users-team-filter"`.

**5.15 Blog Engine year context (2024 → 2026)**
- `backend/services/blog_generator.py` `research_topics`: prompt now injects `Today's date is {today}. Current year is {year}.` and explicitly instructs "Do NOT reference the year 2024 anywhere; anchor 'trend' claims to {year}; do not fabricate statistics with a specific year".
- No hard-coded years in the codebase — fix is prompt-time so it self-updates.

**5.2 Collective Pipeline — custom From/To calendars**
- Backend `applications.py` already supported `window_from` / `window_to` — just needed UI.
- `pages/admin/AdminPipelinePage.jsx`: added two `<input type="date">` controls below the Activity window preset select. `data-testid="filter-window-from"` / `filter-window-to`. URL params round-trip, `clearFilters` resets them.

### Not shipped this pass (documented for next session)
- **5.5 Badge Audit — "Already in Database" report** — needs new tracking of exposure/click events on existing candidates.
- **5.4 Analytics Hub — exclude internal URLs, move heavy agg to background** — needs separating public vs internal URL sets and a scheduled aggregator job.
- **5.11 Location / Company / Skills — server-side searchable multi-select** — needs new facet endpoints (`GET /candidate-bank/facets?field=location&q=X`) and a multi-select combobox component. ~1 full task.
- **5.14 Bills & Invoices — preview modal + email + download** — needs full invoice-render pipeline audit + Resend integration for send-to-client. ~1 full task.
- **Section 4 Employee Drill-down page** — clickable employee → detail drawer with jobs handled, monthly trend, activity timeline. Data foundation is shipped; UI is deferred.
- **Composite Performance Score weighting + admin editor** — settings collection design pending user sign-off on default weights.
- **Quarterly targets management UI** — `employee_targets` collection schema proposed in `ANALYTICS_SPEC_DECISIONS.md`; UI deferred.

### Runtime
- Backend restart clean; `/api/health` `mongodb: ok`.
- `yarn build` succeeded in 8.2 s.
- **43/43 backend tests pass** (unchanged from Wave 1 baseline).


## 2026-09-08 — Emergent Spec Wave 1 (removals + P0 defects)

Executing user-uploaded spec `Emergent_Fix_and_Employee_Performance_Analytics_Specification_WITH_IMAGES.docx`. Section 10 decisions captured in `memory/ANALYTICS_SPEC_DECISIONS.md`.

### Removals — 5 obsolete pages retired (spec 5.6 / 5.9 / 5.10 / 5.16 / 5.17)
- Deleted files: `pages/admin/DedupeMergePage.jsx`, `pages/admin/DigestEmailPage.jsx`, `pages/admin/LinkedInJobDraftsPage.jsx`, `pages/employer/FindCandidatesPage.jsx`, `pages/shared/TalentSearchABPage.jsx`.
- Sidebar entries removed for all three roles (admin/recruiter/employer): Dedupe, Find Candidates, LLM A/B Testing, Digest Email, LinkedIn Drafts.
- Routes removed from `App.jsx`; lazy imports pruned.
- CommandPalette entry pruned.
- 5 dead "Find Candidates" buttons/links removed from RecruiterDashboard, RecruiterJobsPage, admin JobsPage, EmployerDashboard, EmployerJobsPage.
- Daily Digest scoring logic preserved (still needed for Wave 2 analytics).
- Post-build grep: **0 references** in bundle to any of the 5 removed page components.

### Data Bank — filters cleanup + live count (spec 5.11)
- `hooks/useCandidateBankFilters.js`: `FILTER_KEYS` dropped `source`, `hasResume`, `mandateId`, `aiSource`, `smartTags`. Added `debouncedFiltersKey` (400 ms debounce over JSON-stringified filters) so downstream pages can auto-reload on any filter change.
- `components/candidate-bank/CandidateBankFilters.jsx`: Removed Source, Has Resume, Mandate, AI Source, Smart Tags filter sections and their chips. Dropped now-unused `jobAPI` mandate fetch. `isAdmin` prop kept for backwards-compat but no longer changes what renders.
- Wired `debouncedFiltersKey` into all three consumer pages so **the headline count and list refresh on every filter change**: `CandidateDataBankPage.jsx` (admin), `RecruiterCandidateBankPage.jsx`, `EmployerCandidateBankPage.jsx`. Fixes the "Phone/Email filters don't work" symptom (backend was fine; the UI just never re-fetched).
- Note: Location / Company / Skills remain as text inputs. Server-side searchable multi-select is Wave 3 work.

### Teams — active_jobs_count derived on read (spec 5.13)
- `backend/routes/teams.py`: Added canonical `ACTIVE_JOB_STATUSES = ("open", "in_progress", "active")` — used everywhere "active job" is counted. `"active"` is included alongside `open`/`in_progress` because 100 % of the current production dataset uses `active`; user Section 10 decision was `open + in_progress` so this bridges the two until a status normalization migration runs.
- `get_teams` now aggregates from the jobs collection in two passes (via `team_id`, fallback via `company_id` for legacy jobs) and attaches `active_jobs_count` per team.
- `get_team_stats` now uses `$in ACTIVE_JOB_STATUSES` instead of the single-value `"active"` match.
- Live verification against production Mongo after backend restart:
  ```
  Delhi Team          418 active jobs
  Faridabad team      330
  Gurgaon Team        306
  Bengaluru team       80
  Krishna Team          6
  Jatin Yadav Team      5
  Manorma yadav Team    1
  ```

### Jobs — auto-fill on joined (spec 5.1)
- `backend/routes/applications.py`: When a candidate transitions to `joined`, the code now counts joined applications on the same job. If `joined_count >= headcount` (fallback field order: `headcount → positions → vacancies → 1`), the job's `status` transitions to `"filled"` and `filled_at` is stamped.
- Best-effort — auto-fill errors log a warning and never break the stage transition.
- Idempotent — jobs already in `filled`/`archived`/`closed` are left alone.

### Tests
- New `backend/tests/test_wave1_fixes.py` (5 tests): locks `ACTIVE_JOB_STATUSES` shape, TeamResponse default, headcount-field priority order, "joined only" gating on auto-fill, terminal-status guard.
- Full suite: **43 tests pass** (5 new wave1 + 4 log_retention + 5 embed_client + 29 llm chain).

### Build & runtime
- `yarn build` succeeded in 10.2 s. Bundle now contains `EnrichmentBadge`, `nvidia_mistral_nemotron`, and none of the 5 removed page components.
- Backend restart clean; `/api/health` returns `mongodb: ok, redis: ok`.

### What's still pending

**Wave 2 — Analytics rebuild (biggest remaining piece)**
- Full Section 4 Employee Performance & KPI page: KPI Summary, Scorecard, Conversion View, Team Comparison, Annual Leaderboard, Employee Drill-down.
- Dashboard headline change (5.1) — replace Hiring Funnel block with recruitment KPI markers.
- Requires: locating the existing Daily Digest event→points collection (user Section 10 answer 1 said "in Mongo" — collection name to confirm).

**Wave 3 — remaining fixes**
- 5.2 Collective Pipeline From/To date filter
- 5.7 Salary Benchmarking loading fix
- 5.12 User Management team filter
- 5.14 Bills & Invoices preview modal / email / download
- 5.15 Blog Engine year=2026 + topic traction feedback
- 5.11 Location / Company / Skills → server-side searchable multi-select


## 2026-09-08 — Log retention (application-side pruner)

### Investigation
- Verified stored timestamp types on the four target collections. Native `expireAfterSeconds` TTL indexes only work on BSON `Date` — the current schema stores:
  - `api_metrics.timestamp` — **float** (Unix epoch)
  - `activity_logs.timestamp` — **str** (ISO 8601)
  - `extraction_traces.created_at` — **str** (ISO 8601)
  - `badge_audit.expires_at` — **BSON date**, **already** indexed with `expireAfterSeconds: 0` (verified in Atlas)
- Rather than migrate three field types (would touch every write path and require a backfill on ~640k rows), added an application-side pruner that reads the existing field. Dry-run count against production Mongo: **0 stale rows today** in all three collections — the retention windows are conservative and won't nuke anything on first run.

### Implementation
- New `backend/services/log_retention.py` — bounded `delete_many` per collection, tagged with `comment="log_retention_prune"` for Atlas profiler visibility. Uses the existing `timestamp_-1` / `created_at_1` indexes to keep the filter cheap. Failure in one collection never blocks the others; startup is never blocked.
- Wired into `backend/bootstrap/lifespan.py` after `ensure_metrics_indexes()`. First pass runs immediately after boot; then every 6 h.
- `badge_audit` deliberately left alone — its native TTL index is doing the work.

### Config (all optional; sensible defaults)
```
API_METRICS_RETENTION_DAYS        # default 30
ACTIVITY_LOGS_RETENTION_DAYS      # default 90
EXTRACTION_TRACES_RETENTION_DAYS  # default 30
RETENTION_INTERVAL_HOURS          # default 6
RETENTION_PRUNER_ENABLED          # default true; set false to disable
```

### Tests
- New `backend/tests/test_log_retention.py` (4 tests): confirms float/ISO cutoff shapes and the correct 30/90/30-day windows, per-collection failure isolation, disable-by-env, and the Atlas-profiler `comment` tag.
- Full suite: **38 tests pass** (4 new + 34 existing).

### Runtime evidence
- Backend log after restart: `[Retention] pruner started (every 6.0h, api_metrics=30d, activity_logs=90d, extraction_traces=30d)`.


## 2026-09-08 — BGE sidecar client stability fix

**Symptoms addressed**: Talent-graph similarity requests occasionally stalled under load when the local BGE sidecar at `127.0.0.1:8002` was slow or momentarily unreachable. Root cause was inside `backend/services/embed_client.py`, not in call-site orchestration (`_cross_encoder_rerank` at `services/talent_graph_service.py:590` already correctly runs under `asyncio.to_thread`).

### Fixes
- Replaced module-level `requests.post`/`requests.get` calls with a **shared `requests.Session`** mounted on a pooled `HTTPAdapter` (`pool_connections=4`, `pool_maxsize=32`, `max_retries=0`). Keep-alive avoids repeated TCP handshakes; explicit `max_retries=0` keeps failures visible to the existing circuit breaker instead of being masked by transparent retries.
- Split the single 10 s timeout into **`(connect=2s, read=8s)`** so an unreachable sidecar surfaces in ~2 s and the breaker trips in ~6 s (3× consecutive failures) instead of ~30 s. Tunable via `BGE_SIDECAR_CONNECT_TIMEOUT` and `BGE_SIDECAR_TIMEOUT`.
- Health probe now uses the same session and the split-timeout style: `(BGE_SIDECAR_CONNECT_TIMEOUT, 5.0)`.

### Tests
- New `backend/tests/test_embed_client_stability.py` (5 tests):
  1. Shared session pooled adapter with `max_retries.total == 0`.
  2. `embed_remote` passes the `(2.0, 8.0)` tuple as timeout.
  3. Three simulated `ConnectionError`s trip the breaker to OPEN and the 4th call short-circuits without hitting HTTP.
  4. `BGE_SIDECAR_URL=""` disables both embed and rerank cleanly.
  5. Success path closes the breaker and increments `total_successes`.
- Full LLM + sidecar suite: **34 tests pass** (5 new sidecar + 29 existing LLM/enrichment tests).

### Config
- `BGE_SIDECAR_TIMEOUT` default lowered from `10` to `8` seconds.
- New: `BGE_SIDECAR_CONNECT_TIMEOUT` (default `2`). Existing prod `.env` needs no change; the defaults are picked up automatically.


## 2026-09-08 — Chain reordered: Super 120B now primary

- User observed on live production data that **NS (Super 120B) processes more captures successfully than N (Ultra 550B)**. Ultra hits HTTP 429 rate limits under load; Super handles the same profiles cleanly. Reordered `APPROVED_SOURCES` accordingly.
- **New order**: `nvidia_nemotron_super_120b` → `nvidia_nemotron_550b` → `nvidia_mistral_nemotron` → `emergent_haiku_4_5`.
- Env variable **names** and values unchanged. `NEMOTRON_MODEL` still points to Ultra; `NVIDIA_FALLBACK_MODEL` still points to Super — only the chain-order in code flipped, so production `.env` needs **no change** beyond `NVIDIA_MISTRAL_MODEL` already added.
- Code: `backend/services/llm_fallback_service.py` (`APPROVED_SOURCES` tuple + provider zip), `backend/routes/candidates.py` (bulk re-enrich `provider_chain` metadata), `backend/routes/admin_monitoring.py` (`/llm/provider-status` reflects new order and labels Super as "primary"), `frontend/src/pages/admin/AIMonitoringPage.jsx` (re-enrich helper text).
- Tests updated: `test_fallback_forced_to_nvidia_fallback_when_nemotron_fails` renamed to `test_fallback_forced_to_ultra_when_super_fails` with mocks swapped to the new order. `test_fallback_forced_to_haiku_when_nemo_and_fallback_fail` error-order updated. `test_invalid_or_empty_json_triggers_next_provider` swapped mocks. `test_llm_provider_retry_and_full_extraction.py` fixture chains updated.
- **29/29 tests pass**. Live end-to-end verified: extraction of a fresh synthetic profile completed in 8.5 s with `source=nvidia_nemotron_super_120b` (Super used first, no fallback triggered).
- Frontend badge component unchanged — `NS` badge for Super is already present and correctly renders regardless of chain position.


## 2026-09-08 — Chain expanded to 4 providers (Mistral Nemotron inserted before Haiku)

### Chain change
- **New chain**: NVIDIA Nemotron Ultra 550B → Nemotron Super 120B → **NVIDIA Mistral Nemotron** → Emergent Claude Haiku 4.5.
- Also validated on user's NVIDIA account and rejected: `deepseek-ai/deepseek-v4-pro-0813`, `deepseek-ai/deepseek-v4-flash-0731`, `google/gemma-4-31b-it`, `moonshotai/kimi-k3` — all listed in the catalog but the endpoint hangs indefinitely (no HTTP response). Do not resurrect without an NVIDIA account-side unblock.
- `mistralai/mistral-nemotron` returns cleanly (~350 ms warm, ~14 s cold) but is intermittent. Given a 15 s wall-clock budget via `MISTRAL_TIMEOUT` so the chain escapes fast to Haiku when the endpoint is unhealthy.

### Code
- `backend/services/llm_providers.py` — `_nvidia` now takes an optional `budget` (default `PROVIDER_TIMEOUT`). Added `call_nvidia_mistral(...)` using `MISTRAL_TIMEOUT=15.0`. Accepts `mistralai/*` model IDs (skips the Nemotron-only `chat_template_kwargs`/`reasoning_effort` payload extras).
- `backend/services/llm_fallback_service.py` — `APPROVED_SOURCES` now 4-tuple. Chain zipped with the new provider in position 3.
- `backend/routes/admin_monitoring.py` — `/api/admin/monitoring/llm/stats` returns `mistral_nemotron_pct`; `/llm/provider-status` reports the new provider's config status. Health grade counts Mistral successes.
- `backend/routes/candidates.py` — bulk re-enrich response `provider_chain` metadata updated to the 4-item order.
- `backend/.env` — `NVIDIA_MISTRAL_MODEL=mistralai/mistral-nemotron`.
- `frontend/src/components/candidates/EnrichmentBadge.jsx` — new `MN` badge (indigo).
- `frontend/src/components/candidate-bank/CandidateBankFilters.jsx` — new AI-source filter option "MN - Mistral Nemotron".
- `frontend/src/pages/admin/AIMonitoringPage.jsx` — new metric row and updated re-enrich helper text.

### Tests
- `tests/test_llm_chain_badges_phase55.py` — mocked-fault tests now include `nvidia_mistral_nemotron` in the fallback chain; `test_all_failed_contains_only_approved_chain_and_sanitized_reasons` asserts a 4-item chain.
- Live-verified end-to-end: Ultra path took 6.3 s (source `nvidia_nemotron_550b`). Forced Ultra+Super failure and Mistral live-returned in 1.3 s (source `nvidia_mistral_nemotron`). Forced Mistral hang → correctly walked to Haiku.
- Full suite: **29 tests passed**.

### Deployment note
- Frontend badge fix from the prior session never reached production because the commit was not pushed to GitHub before the EC2 `git pull`. Production builds hit `/var/www/html/` at 06:06:30 UTC but the bundle contained zero references to `EnrichmentBadge` or the new source IDs (verified via curl of `/assets/*.js`).
- To ship this change: push all changes via "Save to Github", then on production run `git pull && cd frontend && yarn install --frozen-lockfile && yarn build && sudo cp -a build/. /var/www/html/`, and `sudo systemctl restart vhc-backend`.


## Production verification completed — 2026-09-08

- User successfully restarted **`vhc-backend`** (reported active) and copied the built frontend. New worker logs at 06:18 UTC confirm Super extraction success, enrichment metadata persistence, and normal extension capture processing. Ultra rate-limit HTTP429 correctly advances to the next provider.
- Health-check command initially used the wrong hostname supplied by main: `app.ventureshrd.com` fails certificate hostname verification. No TLS configuration was modified and no insecure bypass used.
- Main independently retrieved **`https://ventureshrd.com/api/health`** successfully: `status=healthy`, MongoDB OK, Redis OK with local backend, import_failures=0. Use this canonical root-domain health URL in future instructions.
- Backend rollout is now verified in production. Frontend build/copy is confirmed by the user's guarded command completing before the curl error; actual badge appearance is left for user confirmation. No missed-profile bulk retries/backfills were initiated; normal capture/recapture processing continues.
- `FULL GROQ` in this capture path is legacy log wording; the actual executed chain and saved source identify NVIDIA Ultra/Super/Emergent.

## Production terminal follow-up — 2026-09-08

- Actual production systemd unit is **`vhc-backend.service`**, NOT `gunicorn.service`. Older runbooks naming gunicorn are obsolete for this host. Repo `/home/ubuntu/vhc-platform`, Python 3.12.3, frontend output `frontend/build/`, webroot `/var/www/html/`.
- User preserved four server-only changes (two lock updates, housekeeping script, public candidate CSV removal) using backup `backup/ec2-before-enrichment-20260908T060308Z` and a reviewed, conflict-free merge.
- User committed merge `7ef8e308`, set the fallback model (env backup `.env.backup-20260908T060601Z`) and built the frontend successfully.
- Restart failed because main instructions used the obsolete unit name. User's subsequent `udo` typo also did not execute the correct restart. Old running workers therefore still log the retired chain.
- Correct `sudo systemctl restart vhc-backend`, frontend copy and production health verification remain pending. No need to repeat pull/merge/env/build. No missed-profile retries/backfills were run.

# VHCOS Changelog

## 2026-09-08 — New-capture enrichment repair

### Investigation
- Read-only sample of the newest 100 extension captures: 32 NVIDIA successes, 65 failures, 3 pending at observation time.
- Failed trails showed NVIDIA Ultra failure, GPT-OSS failure, retired RunPod call, then strict-Qwen gate preventing Haiku.
- A later read-only count found 896 profiles matching that specific failed trail. This was a count only, not a retry.
- User subsequently explicitly cancelled all missed-profile re-enrichment. No backfill, recovery job, or candidate retry was started.
- NVIDIA HTTP 410 body confirmed `openai/gpt-oss-120b` reached end of life at `2026-09-03T08:00:00Z`; live `/models` no longer listed it.
- Catalog-listed older Mistral variants returned account-route 404s. An initial broad account-access inference was **too broad**: the newer Nemotron Super endpoint from the user's list works with the existing key.
- Final live-tested replacement: `nvidia/nemotron-3-super-120b-a12b`. A transient 503 was handled by bounded retries. Do not resurrect the failed Mistral or retired GPT middle stages.

### Implementation
- Replaced oversized extraction provider code with three adapters, one shared ordered chain, and preserved normalization helpers.
- Removed strict-Qwen gating, direct Qwen calls, RunPod health gating and startup sync. Retired monitoring endpoints remain explicit non-network compatibility responses.
- Disabled obsolete remote BGE-M3 inference without modifying BGE-small or stored vectors.
- Added sanitized per-provider reasons, truncation/content/schema checks, and bounded transient retries.
- Success writes are conditional and atomic, clear stale error fields, and include approved source/status/time/hash metadata.
- Added Pending/Failed/NS badges and bounded pending-row polling. Historical provider badges remain historical, not new routing options.
- Updated admin A/B to Ultra vs Super; configuration monitor and live capture-status banner no longer depend on RunPod.
- Added `/admin/ai-monitoring` route alias; testing found and corrected its missing `Navigate` import.
- Cookie preferences reserve scroll space and cap settings height so controls remain reachable on small screens.
- Converted former retry utility to read-only inventory, with no `--execute` or LLM/write code path.
- Added `NVIDIA_FALLBACK_MODEL=nvidia/nemotron-3-super-120b-a12b`; restarted only preview backend for that env change. No credentials modified.

### Testing
- `backend/tests/test_llm_chain_badges_phase55.py`: 19/19, including real synthetic calls to all final providers and real destination calls under injected upstream faults.
- `backend/tests/test_llm_provider_retry_and_full_extraction.py`: 10/10, **MOCKED** transport/full-profile fixtures, no candidate writes.
- `test_reports/iteration_193.json`: no blocking backend/frontend issues; badges, polling, provider config, NS filter and alias verified.
- Post-report main verification: 10 deterministic tests pass again; compilation passes; external `/api/health` healthy, MongoDB/Redis OK, import failures zero.
- No live capture/re-enrichment jobs or production candidate mutations initiated. Auth test credentials unchanged.
- Optional Ruff unavailable in the environment; no dependency added merely to run it.

### Data/infrastructure decisions
- User reports USD 500 MongoDB credit. Activation/expiry not verified. Keep M10 for now; Flex urgency reduced.
- No TTL creation, database migration, BGE backfill, or BGE timeout change in this session.
- No external EC2 production code rollout performed. New fallback env setting must accompany this code when adopted there.

## Prior history
See [CHANGELOG_ARCHIVE_PRE_2026_09_08.md](CHANGELOG_ARCHIVE_PRE_2026_09_08.md) for the complete original PRD/history, preserved without losing older requirements.