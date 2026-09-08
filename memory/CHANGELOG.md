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