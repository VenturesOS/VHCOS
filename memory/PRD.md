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
