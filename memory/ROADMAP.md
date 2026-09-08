# VHCOS Prioritized Roadmap

Updated 2026-09-08. Consult PRD.md for authoritative current provider configuration.

## P0 — Verify user-facing outcome / remaining operational issues
- New-capture chain and badges: **implemented, 29 targeted tests passed**. Observe genuinely new captures after this code is adopted on the running production server. No production rollout or real capture mutation was performed from this preview.
- Production merge/env/build/restart/frontend copy completed by user. Correct unit is **`vhc-backend`**; canonical verified URL **`https://ventureshrd.com/api/health`** returns healthy (MongoDB/Redis OK, import failures zero). Fresh production captures successfully use Super when Ultra is throttled. Next: user observes N/NS/EC/Pending/Failed badges in normal use. No more restart/build or missed-profile retries. `app.ventureshrd.com` has an unmatched TLS certificate; do not use it as the health-check hostname or disable certificate verification.
- BGE-small sidecar timeouts: still unresolved and out of this session's implementation scope. Investigate load/concurrency, timeouts, circuit breaking and predictable semantic-search failure handling without changing vector dimensions.

## P1 — Controlled housekeeping
- Validate log timestamp types and existing indexes before proposing TTL changes. Intended retention from handoff:
  - `api_metrics`: 30 days
  - `activity_logs`: 90 days
  - `badge_audit`: 90 days (historical notes report a 30-day index already; inspect actual state first)
  - `extraction_traces`: 30 days
  - `naukri_capture_logs`: 60 days
- TTL can delete existing data: obtain explicit approval after previewing impact. No TTL writes performed here.
- Check Asha screening compatibility after historical removal of `GROQ_API_KEY`; do not silently change unrelated voice integration.
- Confirm MongoDB startup credit was activated on the correct organization, including eligible charges and expiry. USD 500 is user-reported; current balance not verified.
- Measure storage/index growth and actual monthly spend; retain M10 while credit is available if suitable.

## P2 — Evidence-led architecture / future work
- Master Plan Phase 0: storage/index profile, data quality, benchmark set.
- Decide BGE-small/BGE-M3/NVIDIA `nemotron-3-embed-1b` strategy before costly backfill. Do not mix dimensionalities.
- Consider PostgreSQL + pgvector/OpenSearch only if benchmarks justify a migration; not an immediate rewrite.
- Frontend Jest-to-Vitest migration and other historical backlog items remain; see archived PRD for detail.
- Enhancement: add a daily enrichment failure-rate alert and provider-specific error counts so silent outages are noticed early, without automatically retrying missed profiles.

## Paused / prohibited without new authorization
- **Missed-profile retries/backfill: explicitly cancelled by user. Do not run.** The old retry utility now only counts failed extension profiles.
- Atlas M10→Flex migration: paused after MongoDB credit news; retained runbook requires user-controlled window if reconsidered.
- RunPod/Qwen: permanently removed from active inference. Do not restore credentials, URLs, probes, strict gates or workers.
- GPT-OSS120B through NVIDIA: retired (HTTP410, provider EOL message). Historical badges may remain; no new calls.
- AWS DocumentDB, Azure Cosmos DB, and application-managed multi-Flex pseudo-sharding: rejected.