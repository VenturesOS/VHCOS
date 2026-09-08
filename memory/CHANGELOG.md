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