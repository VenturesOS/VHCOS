# VHC Talent OS — Product Requirements & Current State

Last updated: 2026-09-08. This concise document supersedes obsolete provider instructions in historical notes.

## Original problem statement
Fix Chrome Extension background capture failures, stabilize backend infrastructure and profile extraction, reduce operating cost, and support high-quality recruitment sourcing, profile deduplication, semantic matching, deep links, and team workflows.

Current user goal: remove the retired RunPod/Qwen integration and its strict-only gate, ensure new captures have reliable AI enrichment, and show Pending/Failed status instead of a missing badge.

## Explicit current user decisions
- Keep NVIDIA first and Emergent Haiku last; remove Qwen completely from active inference.
- NVIDIA GPT-OSS-120B is retired. User approved replacing it with another current NVIDIA endpoint and supplied their available model list.
- Final verified chain: **Nemotron Ultra 550B → Nemotron Super 120B → Emergent Claude Haiku 4.5**.
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
1. `nvidia/nemotron-3-ultra-550b-a55b`, source `nvidia_nemotron_550b`, badge **N**.
2. `nvidia/nemotron-3-super-120b-a12b`, source `nvidia_nemotron_super_120b`, badge **NS**.
3. `claude-haiku-4-5-20251001` through existing Emergent integrations, source `emergent_haiku_4_5`, badge **EC**.

Configuration: existing `NEMOTRON_API_KEY`, `NEMOTRON_BASE_URL`, `NEMOTRON_MODEL`, `EMERGENT_LLM_KEY`; newly required `NVIDIA_FALLBACK_MODEL=nvidia/nemotron-3-super-120b-a12b` is configured in this preview. Existing deprecated env keys were preserved but are not read by active inference.

- Adapters: `backend/services/llm_providers.py`. Non-thinking Nemotron requests omit unsupported `response_format`; structured content is parsed and validated locally.
- Orchestration: `backend/services/llm_fallback_service.py`; shared facade `services/llm_service.py`.
- Existing salary/date/regex normalization moved intact to `services/profile_extraction_helpers.py`.
- Three attempts maximum for transient NVIDIA 502/503/504/network errors within a total 90-second budget per provider. Permanent failures/throttling proceed to the next provider; no strict-provider gate.
- CV extraction, industry classification, billing body generation, and talent summaries use the approved shared path rather than direct Qwen calls.
- RunPod sync daemon is no longer scheduled. Historical monitoring endpoints return an explicit retired status without network access. Legacy remote BGE-M3 transport is disabled; BGE-small is unchanged.
- `routes/extension.py` success persistence atomically saves enrichment status/source/time/hash/chain and clears stale errors. Conditional writes discard stale recapture results; failed attempts cannot replace an already-successful status.
- UI: `EnrichmentBadge.jsx` shows N/NS/EC/Pending/Failed/Not enriched. Historical successful sources remain represented truthfully; old data is not rewritten.
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
- Production update partially completed by user on 2026-09-08: merge `7ef8e308` committed; new fallback env configured; Vite build passed. CSV security removal, housekeeping script and dependency lock preserved. Restart failed because the suggested unit `gunicorn` does not exist, then user's `udo` typo prevented the attempted `vhc-backend` restart. Correct restart, built-frontend copy and production health verification are still pending. Do not repeat the pull/merge or backfill.
- NVIDIA transient overload remains possible; verified retries/fallback handle it. No promise of permanent upstream availability.

## Documentation
- [CHANGELOG.md](CHANGELOG.md): current implementation and investigation facts.
- [ROADMAP.md](ROADMAP.md): prioritized remaining work and prohibited/deferred actions.
- [Historical archive](CHANGELOG_ARCHIVE_PRE_2026_09_08.md): exact prior 2,053-line PRD retained for older requirements and implementation history. Its RunPod/GPT routing instructions are obsolete.
- `ATLAS_FLEX_MIGRATION_RUNBOOK.md`: retained, migration paused.
- `PLATFORM_AUDIT_2026_08.md`, `badge_traceback_diagnostics.md`: earlier audit references.