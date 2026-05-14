# VHC Talent OS — Product Requirements (live)

## Original problem statement
Fix Chrome Extension background capture bug, stabilize EC2 infrastructure
from OOM crashes, solve RunPod LLM extraction truncations, and provide /
implement a cost optimization plan for AWS + RunPod. Add advanced AI
sourcing (XGBoost LTR Re-ranker, k-Means + PCA clustering) and deep-link
features. Provide daily team-performance digests (WhatsApp-shareable).

## Stack
- FastAPI + Motor (Async MongoDB) backend
- React (Vite) frontend
- AWS EC2 `t3a.large` (Gunicorn-managed, hot-reload disabled in prod)
- RunPod A5000 — Qwen14B vLLM (Pod ID `t41o9p01whlrfe`)
  - **BGE sidecar on port 8001** (`BAAI/bge-small-en-v1.5`, GPU)
- Emergent Haiku 4.5 LLM fallback
- Cache: Local Redis on EC2 (`REDIS_URL=redis://localhost:6379/0`)

## Personas
- Admin (`admin@vhc.in`)
- Recruiter / Sourcer
- Hiring Manager

## Core capabilities (live)
- Chrome Extension capture (Naukri / LinkedIn) → `candidate_bank`
  (`source: <vendor>_extension`)
- Sourcing pipeline w/ XGBoost LTR re-ranker, k-Means + PCA clustering
- AI extraction via RunPod Qwen14B → Emergent Haiku fallback
- BGE embeddings via RunPod GPU sidecar (Feb 2026, Phase 54.16/.17)
- Pipeline board (paginated, denormalized stage counts)
- Daily Team Performance Digest w/ WhatsApp share
- SEC-04 hardened auth: deactivated users instantly logged out across
  all devices (extension, browser, mobile)

## Recent changelog
- **2026-02-13 (Phase 54.21) — WhatsApp Cloud API integration shipped**
  - Backend: `services/whatsapp_cloud_service.py` + webhook receiver +
    fan-out from 18:00 IST cron + admin endpoints for status/test-send.
  - Frontend: green "Auto-Send" button on Daily Digest widget.
  - Meta credentials saved to EC2 `.env`. Awaiting template approval
    (`team_daily_digest_v1`, ~24-48h).
  - Full runbook: `/app/memory/PHASE54_PART21_WHATSAPP_CLOUD_API.md`.
- **2026-02-13 (EventBridge nightly off)** — Two schedules created in
  ap-south-1: stop 00:30 IST daily, start 06:30 IST Mon–Sat. Sunday is
  fully off. ~₹830/mo locked in.
- **2026-02-12 (Phase 54.19) — User Leaderboard KPI overhaul**
  - Activity Monitor's User Leaderboard now ranks by **blended composite**:
    `0.6 × activity_score_norm + 0.2 × capture_quality + 0.2 × mandate_efficiency`
    — same KPI engine as the WhatsApp Daily Digest.
  - Columns trimmed to digest-relevant: Score, Activity, Captures,
    Pipeline Pts, Quality %, Mandate Eff %, Last Active.
  - Profile Views moved to a small "👁 N views" engagement badge under
    the user name (not scored).
  - Period filter expanded: today / week / month / **quarter** / year /
    **all time** / custom — added as a dropdown right inside the
    leaderboard card header for visibility.
  - New service: `services/leaderboard_kpis.py` — bulk Mongo sweep for
    arbitrary date ranges (reuses digest helpers; safe for 100+ users).
- **2026-02-12 (Phase 54.17 + SEC-04)**
  - Local Redis live on EC2 (replaced Upstash quota-exhausted REST).
  - pypdf migration deployed.
  - Pipeline pagination + denormalized stage_counts deployed.
  - **SEC-04**: `get_current_user` now rejects `is_active=false`;
    soft-delete + toggle-status bump `token_version` + purge refresh
    tokens. One-time cleanup force-logged-out 12 deactivated users,
    purged 28 refresh tokens (closed Sarita data-leak).
  - **BGE sidecar shipped to RunPod GPU** — embeddings now served by
    A5000 (CUDA), `BGE_SIDECAR_URL` wired on EC2. End-to-end verified.
- **2026-02 (earlier)** — EC2 m7i-flex.large → t3.large → t3a.large.
  RunPod A40 → A5000 (+ A40 pod deleted). RunPod API key Read-only →
  R&W (cron auto start/stop works).
- **2026-02** — Daily Team Performance Digest backend + UI widget.
  Fixed naukri_extension source tracking; hide 0 % mandate efficiency;
  Team Ranking replaces "Low Team Output"; deactivated users excluded.

## Cost picture (₹, indicative, ap-south-1)

| Component        | Before (Jan 2026) | Now (Feb 12) | After t3.medium | Notes |
|------------------|-------------------|--------------|-----------------|-------|
| EC2              | ~₹6,500 (m7i-flex.large) | ~₹4,600 (t3a.large) | ~₹2,500 (t3.medium) | -62% |
| RunPod GPU       | ~₹23,700 (A40 24/7) | ~₹6,300 (A5000, cron 9h40m/day) | unchanged | -73% |
| Upstash Redis    | ₹830 (free tier hit, paid req'd) | ₹0 (local Redis) | ₹0 | -100% |
| **TOTAL**        | **~₹31,000** | **~₹10,900** | **~₹8,800** | **-72%** |

(Numbers are AWS/RunPod on-demand list prices; actual invoices vary.)

## Backlog
### P1
- [ ] **Phase 54.18 (TOMORROW LUNCH, Feb 13)** — combined maintenance:
  - Pre-flight: tail sidecar log to confirm clean overnight soak
  - Phase 1: `pip uninstall sentence-transformers` on EC2 → free ~800 MB
  - Phase 2: edit pod Container Start Command to launch sidecar +
    vLLM together (one-time, survives every restart forever)
  - Phase 3: AWS Console → EC2 t3a.large → t3.medium
  - Full plan + commands: `/app/memory/PHASE54_PART18_LUNCH_MAINTENANCE.md`
- [ ] EventBridge nightly EC2 off (12:30–6:30 AM IST) — after t3.medium.
- [ ] Drop unused Mongo indexes after 7-day cluster uptime.

### P2
- [x] Delete old A40 pod — DONE Feb 2026
- [x] BGE sidecar deploy — DONE Feb 12 2026

### P3
- [ ] Email Template Management
- [ ] WhatsApp Business API integration
- [ ] Offboarded-recruiter audit widget (surface captures from any
  user deactivated in last 30 days)

## Key endpoints
- `GET  /api/health` (returns `redis_backend: "local"`)
- `GET  /api/health/aws-readiness`
- `GET  /api/admin/pipeline?limit=100`
- `POST /api/admin/daily-digest/regenerate`
- `GET  /api/admin/daily-digest`

## Critical env vars
| Var                                | Purpose                          |
|------------------------------------|----------------------------------|
| `REDIS_URL`                        | Local Redis (Phase 54.17)        |
| `BGE_SIDECAR_URL`                  | RunPod BGE embed endpoint        |
| `MONGO_URL` / `DB_NAME`            | Mongo (protected)                |
| `EMERGENT_LLM_KEY`                 | Haiku fallback                   |

## Test credentials
See `/app/memory/test_credentials.md`.

## Reference deploy docs
- `/app/memory/PHASE54_PART17_LOCAL_REDIS_DEPLOY.md`
- `/app/memory/PHASE54_PART16_D1_BGE_SIDECAR_DEPLOY.md`
- `/app/memory/PHASE54_PART16_NIGHTLY_OFF_DEPLOY.md`
- `/app/memory/EC2_DOWNGRADE_PLAN_A1.md`
- `/app/backend/scripts/sec04_purge_deactivated_sessions.py` (one-time)


## Phase 55 — Search Quality Last Milestone (2026-02-14)

User complaint: Advanced Search, AI Search, and Autocomplete returned empty / inaccurate results. Root cause: backend filters were querying the wrong canonical fields while 87–99% of real candidate data lives in alias fields. Embedding coverage was <2% so semantic search missed almost everything.

### Batch A — Advanced Search filters (`/app/backend/routes/candidates.py`)
- **Company filter** now matches `current_employer` (87.4% coverage) in addition to `current_company` / `company`. Was returning 0; now returns thousands. *Verified: "TE Connectivity" → 28 candidates.*
- **Industry filter** matches `smart_tags` first (broad bucket aligned to the dropdown labels) with a loose-token fallback on the granular `industry` field. *Verified: "IT/Software" → 54,127 vs 10 before.*
- **Has Resume** filter now unions `cv_attached:true` and `has_resume:true` booleans alongside `resume_url/path/latex`. *Verified: 24,591 candidates vs ~0 before.*
- **Notice period** uses regex substring (case-insensitive) instead of exact equality. *Verified: "immediate" → 1,887 results.*
- **has_phone / has_email** reject `"hidden"`, `"Not Available"`, `"N/A"` placeholders.

### Batch B — AI Search quality (`services/ai_search.py`, `routes/ai_search.py`)
- Strip ```json markdown fences from LLM output (root cause of "AI could not parse the search prompt" errors).
- Drop hallucinated numeric constraints when the prompt has no digits — "experienced Java in Bangalore" no longer extracts `min_experience` from an adjective.
- `build_mongo_query` for industry now uses `smart_tags` first.
- Route sorts by `created_at` desc (fresh data first) and auto-relaxes (drops notice / CTC / stability) when strict query returns 0 — sets `relaxed:true` in response.

### Batch C — Suggestions + Semantic fallback
- `autocomplete_suggestions` now includes the **industry** field (new) and uses substring (not strict `^prefix`) match.
- `AutocompleteInput.jsx` adds `industry` to TYPE_COLORS.
- `find_candidates_by_text` (semantic search) **tops up** with a keyword + smart-tag fallback over `candidate_bank` when the vector pool is sparse (only ~1.4% of the 1.23 L bank has embeddings). Results are tagged `match_type: 'vector' | 'keyword'`.

### Verification
- Backend regression suite at `/app/backend/tests/test_search_fixes.py` → **15/15 PASS**.
- Frontend Playwright via testing agent: keywords AC, IT/Software filter, Company=Wipro (614 hits), Smart Re-rank (50/200 candidates @ AUC 0.7211) — all PASS.
- LTR sourcing bundle confirmed active (not graceful-fallback path).

### Files touched
- `backend/routes/candidates.py` (list_candidates filter section, autocomplete_suggestions)
- `backend/routes/ai_search.py` (sort + relax)
- `backend/services/ai_search.py` (json fence strip, sanitiser, industry smart_tag preference)
- `backend/services/talent_graph_service.py` (`_keyword_fallback_search`, vector match_type tag)
- `frontend/src/components/shared/AutocompleteInput.jsx`
- `frontend/src/pages/shared/AdvancedSearchPage.jsx` (unique result keys)

### Pending / Future
- (P0, blocked) WhatsApp `team_daily_digest_v1` Meta template approval + token rotation.
- (P1) Run BGE backfill on full candidate_bank (~5 hr GPU job) to push embedding coverage from 1.4% → 100% so semantic search is the primary path and fallback is rare.
- (P2) Wire cross-encoder reranker (deployed on sidecar) into match scoring.
- (P2) Drop unused Mongo indexes after 7-day uptime audit.
- (P3) Email template management; auto-persist BGE sidecar in unified vLLM Docker image.

