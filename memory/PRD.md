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
- Emergent Haiku 4.5 LLM fallback
- **Cache: Local Redis (Phase 54.17)** — replaced Upstash REST (quota
  exhausted). Old Upstash creds still in `.env` but ignored when
  `REDIS_URL` is set.

## Personas
- Admin (`admin@vhc.in`)
- Recruiter / Sourcer
- Hiring Manager

## Core capabilities (live)
- Chrome Extension capture (Naukri / LinkedIn) → `candidate_bank`
  (`source: <vendor>_extension`)
- Sourcing pipeline w/ XGBoost LTR re-ranker, k-Means + PCA clustering
- AI extraction via RunPod Qwen14B → Emergent Haiku fallback
- Pipeline board (paginated, denormalized stage counts — Phase 54.17)
- Daily Team Performance Digest (Activity Score, Capture Quality,
  Lifetime Mandate Efficiency, Team Ranking) w/ WhatsApp share
- Talent graph embeddings (BGE-small) — local fallback + RunPod sidecar
  (Phase 54.16)
- AWS readiness one-click health check (`/api/health/aws-readiness`)

## Recent changelog
- **2026-02 (Phase 54.17)** — Local Redis support, refactored
  `services/redis_client.py` to try `REDIS_URL` before Upstash. Pinned
  `redis==5.3.1`. Wrote combined deployment runbook
  (`/app/memory/PHASE54_PART17_LOCAL_REDIS_DEPLOY.md`).
- **2026-02 (Phase 54.16)** — BGE embeddings sidecar (workspace ready,
  pending RunPod deploy). PyPDF2 → pypdf. Pipeline pagination + stage
  counts denormalization.
- **2026-02** — Daily Team Performance Digest backend + UI widget.
  Fixed `naukri_extension` source tracking; hide 0 % mandate efficiency;
  Team Ranking replaces "Low Team Output"; deactivated users excluded.
- **2026-02** — EC2 downgrade `m7i-flex.large` → `t3.large` → `t3a.large`.
- **2026-02** — Fixed RunPod API key (Read-only → R&W) so cron start /
  stop actually works.
- **Earlier** — Chrome extension fix, MongoDB pool tuning, OOM fixes,
  XGBoost LTR, k-Means + PCA, deep-link sourcing.

## Backlog
### P0
- [ ] User: deploy Phase 54.17 (Local Redis + sidecar) per runbook.

### P1
- [ ] EventBridge nightly EC2 off (12:30–6:30 AM IST) — after BGE
  sidecar stable
- [ ] Drop unused MongoDB indexes once 7-day uptime is reached

### P2
- [ ] Downsize EC2 → `t3.medium` (after BGE sidecar frees ~1 GB)
- [x] ~~Delete old RunPod A40 pod~~ — DONE Feb 2026

### P3
- [ ] Email Template Management
- [ ] WhatsApp Business API integration

## Key endpoints
- `GET  /api/health` (now returns `redis_backend: "local" | "upstash"`)
- `GET  /api/health/aws-readiness`
- `GET  /api/admin/pipeline?limit=100` (paginated, stage_counts inline)
- `POST /api/admin/daily-digest/regenerate`
- `GET  /api/admin/daily-digest`

## Critical env vars
| Var                                | Purpose                          |
|------------------------------------|----------------------------------|
| `REDIS_URL`                        | Local Redis URL (Phase 54.17)    |
| `UPSTASH_REDIS_REST_URL/_TOKEN`    | Legacy (ignored if REDIS_URL set)|
| `BGE_SIDECAR_URL`                  | RunPod BGE embed endpoint        |
| `MONGO_URL` / `DB_NAME`            | Mongo (protected)                |
| `EMERGENT_LLM_KEY`                 | Haiku fallback                   |

## Test credentials
See `/app/memory/test_credentials.md`.

## Reference deploy docs
- `/app/memory/PHASE54_PART17_LOCAL_REDIS_DEPLOY.md` (combined Feb 2026)
- `/app/memory/PHASE54_PART16_D1_BGE_SIDECAR_DEPLOY.md`
- `/app/memory/PHASE54_PART16_NIGHTLY_OFF_DEPLOY.md`
- `/app/memory/EC2_DOWNGRADE_PLAN_A1.md`
