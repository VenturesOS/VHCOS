# VHC Talent OS — Product Requirements & Current State

Last updated: 2026-09-08. This concise document supersedes obsolete provider instructions in historical notes.

## Original problem statement
Fix Chrome Extension background capture failures, stabilize backend infrastructure and profile extraction, reduce operating cost, and support high-quality recruitment sourcing, profile deduplication, semantic matching, deep links, and team workflows.

Current user goal: remove the retired RunPod/Qwen integration and its strict-only gate, ensure new captures have reliable AI enrichment, and show Pending/Failed status instead of a missing badge.

## Explicit current user decisions
- Keep NVIDIA first and Emergent Haiku last; remove Qwen completely from active inference.
- NVIDIA GPT-OSS-120B is retired. User approved replacing it with another current NVIDIA endpoint and supplied their available model list.
- Final verified chain: **Nemotron Super 120B → Nemotron Ultra 550B → Mistral Nemotron → Emergent Claude Haiku 4.5**. Super leads because production data showed it processes more captures successfully than Ultra (Ultra hits HTTP 429 rate limits under load).
- **DO NOT retry or re-enrich previously missed profiles.** Earlier retry approval was expressly revoked. No missed-profile re-enrichment or backfill was executed in this session.
- MongoDB awarded the user USD 500 startup credit. Credit activation/balance/expiry have not been verified here. Keep Atlas M10 for now; no urgent Flex or RDS migration.
- No AWS DocumentDB, Azure Cosmos DB, or application-managed multi-Flex sharding.
- Database migrations, embedding backfills, and destructive retention changes require separate approval.

## Personas and core flows
- Recruiter: capture Naukri/LinkedIn profiles, search candidates, review matches, manage pipelines.
- Manager/admin: manage sourcing, review candidate enrichment and data quality, monitor operations and team performance.
- Employer/account manager: inspect candidate pipelines, hiring progress, and permitted candidate information.
- Captured candidate: source of profile data; no direct UI required for this flow.

## Architecture
- React/Vite frontend with Shadcn/Tailwind; retain existing design and role permissions.
- FastAPI backend with Motor/PyMongo and MongoDB Atlas. This preview connects to real candidate data: never assume it is a disposable test database.
- Runtime backend 8001, frontend 3000, supervised services. API routes begin `/api`.
- Frontend API base: `REACT_APP_BACKEND_URL`; MongoDB: `MONGO_URL` and unchanged `DB_NAME`.
- Existing production EC2 service is separate from this preview. User-confirmed service: **`vhc-backend.service`**, NOT `gunicorn.service` (gunicorn is the process). Production repo: `/home/ubuntu/vhc-platform`; Python 3.12.3; frontend output `frontend/build/`, existing webroot `/var/www/html/`. Earlier runbooks naming `gunicorn.service` are obsolete for this host.
- Existing token key: `vhc_token`. Credentials remain in `memory/test_credentials.md`; none changed this session.
- Active Talent Graph BGE-small sidecar remains 384-dimensional in `candidate_embeddings`. Do not mix those vectors with legacy 1024-dimensional BGE-M3 or planned NVIDIA embeddings.

## Current enrichment architecture (implemented and tested 2026-09-08)
1. `nvidia/nemotron-3-super-120b-a12b`, source `nvidia_nemotron_super_120b`, badge **NS**. **Primary** — user-observed to handle more real captures cleanly than Ultra.
2. `nvidia/nemotron-3-ultra-550b-a55b`, source `nvidia_nemotron_550b`, badge **N**. Fallback for the harder profiles Super struggles on.
3. `mistralai/mistral-nemotron` via NVIDIA NIM, source `nvidia_mistral_nemotron`, badge **MN**. 15 s wall-clock budget (via `MISTRAL_TIMEOUT`) because this endpoint is intermittent on the current NVIDIA account. Fast escape to Haiku when unhealthy.
4. `claude-haiku-4-5-20251001` through existing Emergent integrations, source `emergent_haiku_4_5`, badge **EC**.

Not usable on this NVIDIA key (listed in catalog but requests hang indefinitely — do not resurrect without account-side unblock): `deepseek-ai/deepseek-v4-pro-0813`, `deepseek-ai/deepseek-v4-flash-0731`, `google/gemma-4-31b-it`, `moonshotai/kimi-k3`.

Configuration: existing `NEMOTRON_API_KEY`, `NEMOTRON_BASE_URL`, `NEMOTRON_MODEL` (Ultra); `NVIDIA_FALLBACK_MODEL=nvidia/nemotron-3-super-120b-a12b`; `NVIDIA_MISTRAL_MODEL=mistralai/mistral-nemotron`; `EMERGENT_LLM_KEY`. Env variable **names** are unchanged — only the chain-order in `APPROVED_SOURCES` was flipped, so nothing to update in production `.env` beyond what was already added.

- Adapters: `backend/services/llm_providers.py`. Non-thinking Nemotron requests omit unsupported `response_format`; structured content is parsed and validated locally.
- Orchestration: `backend/services/llm_fallback_service.py`; shared facade `services/llm_service.py`.
- Existing salary/date/regex normalization moved intact to `services/profile_extraction_helpers.py`.
- Three attempts maximum for transient NVIDIA 502/503/504/network errors within a total 90-second budget per provider. Permanent failures/throttling proceed to the next provider; no strict-provider gate.
- CV extraction, industry classification, billing body generation, and talent summaries use the approved shared path rather than direct Qwen calls.
- RunPod sync daemon is no longer scheduled. Historical monitoring endpoints return an explicit retired status without network access. Legacy remote BGE-M3 transport is disabled; BGE-small is unchanged.
- `routes/extension.py` success persistence atomically saves enrichment status/source/time/hash/chain and clears stale errors. Conditional writes discard stale recapture results; failed attempts cannot replace an already-successful status.
- UI: `EnrichmentBadge.jsx` shows N/NS/MN/EC/Pending/Failed/Not enriched. Historical successful sources remain represented truthfully; old data is not rewritten.
- `useEnrichmentPolling.js` checks a bounded number of visible Pending rows, avoids overlapping requests, and cleans up on unmount. It does not initiate enrichment.
- Admin A/B now compares Ultra vs Super. Historical reports are not relabeled as the new models.
- `/admin/ai-monitoring` aliases existing `/admin/system-health`. Provider configuration display is not represented as proof of live availability.
- The former `scripts/retry_all_failed_enrichment.py` is deliberately **read-only** and accepts no execution mode. No recovery worker exists.

## Verification and limitations
- Reports: `test_reports/iteration_192.json` (initial findings), **`test_reports/iteration_193.json` (final pass)**.
- 29 targeted tests passed: 19 provider/chain/persistence cases plus 10 retry/full-profile post-processing cases.
- All three current providers were called live with synthetic input; forced fallback tests mocked only upstream failures while downstream calls were real.
- Full-profile persistence/post-processing and error scenarios used **MOCKED** fixtures; no existing candidate writes were performed for tests.
- UI passed read-only checks for badges, NS filter, alias, provider configuration, and pending polling using **MOCKED** response fixtures for state transitions.
- Main follow-up: 10 deterministic tests passed again; Python compilation passed; `/api/health` healthy with MongoDB/Redis OK and zero import failures. Optional Ruff is not installed.
- Production update completed by user on 2026-09-08: merge `7ef8e308`, fallback env setting, successful Vite build, **`vhc-backend` restart active**, and frontend copy. CSV security removal, housekeeping script and dependency lock preserved. Fresh production logs show successful `nvidia_nemotron_super_120b` extraction/persistence and normal live capture processing; Ultra HTTP429 falls through correctly. Main independently retrieved **`https://ventureshrd.com/api/health`**: healthy, MongoDB OK, Redis OK/local, import_failures=0. The previously supplied `app.ventureshrd.com` hostname has a certificate-name mismatch and is NOT the verified health-check hostname. Do not bypass TLS checks. Production badge display still awaits user observation; no repeat pull/build/restart or missed-profile backfill needed.
- NVIDIA transient overload remains possible; verified retries/fallback handle it. No promise of permanent upstream availability.

## Roles & access (as of 2026-09-17)
- **Recruiter**: Dashboard, Mandates, Pipeline, Advanced Search, Candidate Bank, Submission Tracker,
  Attendance, Leaves. Sees their target as a **percentage only**.
- **Employer / team lead**: Dashboard, Analytics, My Team (sets member revenue targets + already
  achieved), Joining List (fill CTC + revenue, Raise Invoice), Companies, Pipeline, Trackers, My Jobs,
  Candidate Bank, Advanced Search, Attendance, Team Attendance, Leaves, Team Insights (own team only),
  Reports, Salary Benchmark.
- **Accounts** (accounts@vhc.in): Bills & Invoices + the accounts portal.
- **Admin**: everything, plus Teams (team-level targets) and Performance Records (monthly/quarterly/
  annual archive).
- Revenue targets are one number per calendar year (Jan–Dec). Recruiter revenue Σ = team total,
  team Σ = company total.
- Pending from the user: further employer/recruiter access tweaks as they review.

## Billing module — current state (2026-09-17)
- Two sender entities: `VENTURE HRD CENTER` (07AAMPY9883D2ZT) and `Ventures HRD Pvt Ltd`
  (07AACCV6268J1ZW), both at Second Floor, D-12/79-80, Rohini Sector 8, New Delhi 110085.
- All historical bills/invoices/expenses/revenue were wiped on user instruction; numbering restarts at
  VHC/26-27/1. Bank accounts must be re-added by the user (invoice PDF prints the bank block from the
  default/only saved account).
- Invoices send from accounts@ventureshrd.com, reply-to + BCC accounts@vhc.in. Switch the FROM to
  accounts@vhc.in once that domain is verified in Resend.
- accounts@vhc.in (role `accounts`) can use Bills & Invoices at `/accounts/bills`.
- Pending from the user: further additions/removals to employer and recruiter access.

## Spec compliance status (2026-09-17) — both uploaded docs
All items from `fix.docx` and the Employee Performance Analytics specification are implemented and
verified live. See the 2026-09-17 entry in [CHANGELOG.md](CHANGELOG.md) for evidence per item.
- Analytics Hub is now public-website-only (internal portal routes excluded by route prefix).
- Joinings list lives on Employee Performance, derives DOJ from stage history, and follows the page's
  date/team/employee filters. Revenue stays blank until a team leader fills it in.
- "Candidates called" is tracked from three intents (extension badge click, profile open, explicit
  Mark Called) and surfaced on Badge Audit.
- Clusters has no dedicated page any more (backend service only).
- Invoice PDF always prints the company logo and the bank-transfer block (default/only saved account
  when a bill predates the feature).

Remaining backlog for this workstream: employee drill-down drawer, quarterly targets UI, composite score
weighting editor, Badge Audit "Already in Database" reuse report, Advanced Search redesign (deferred by
the spec), and unifying Daily Digest points (tracker_events) with the analytics points (stage_history).

## Documentation
- [CHANGELOG.md](CHANGELOG.md): current implementation and investigation facts.
- [ROADMAP.md](ROADMAP.md): prioritized remaining work and prohibited/deferred actions.
- [Historical archive](CHANGELOG_ARCHIVE_PRE_2026_09_08.md): exact prior 2,053-line PRD retained for older requirements and implementation history. Its RunPod/GPT routing instructions are obsolete.
- `ATLAS_FLEX_MIGRATION_RUNBOOK.md`: retained, migration paused.
- `PLATFORM_AUDIT_2026_08.md`, `badge_traceback_diagnostics.md`: earlier audit references.