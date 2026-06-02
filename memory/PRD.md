# VHC Talent OS — Product Requirements Document

**Last updated:** Feb 2026 (Phase 55.x)

## Original problem statement
Fix Chrome Extension background capture bug, stabilize EC2 infrastructure
from OOM crashes, solve RunPod LLM extraction truncations, and provide a
cost-optimization plan for AWS/RunPod infrastructure. Add advanced AI
sourcing, deep-link features, daily team digest, and Naukri / LinkedIn
profile capture quality improvements.

## Personas
- **Recruiter** — captures Naukri / LinkedIn profiles via Chrome extension, runs sourcing searches.
- **Manager / Admin** — reviews team performance digest, manages mandates.
- **Candidate (passive)** — captured + enriched. No direct UI.

## Tech stack
- Backend: FastAPI + MongoDB Atlas, hosted on AWS EC2 `t3.xlarge` (15 GB RAM, 4 vCPU).
- Service: systemd `vhc-backend` (port 8001, 3 workers, memory caps 5/6 GB, max-requests 1000).
- Frontend: React (CRA).
- Reverse proxy: Nginx (10 r/s rate-limit on `/api/extension/capture`).
- LLM: vLLM Qwen14B-AWQ on RunPod (port 8000).
- Embeddings + Reranking: BGE sidecar on RunPod (port 8001).
- Daily digest delivery: WhatsApp Cloud API.
- Cache: Redis local.

---

## What's implemented (rolling changelog)

### Phase 55 — Feb 2026 (this fork)
- **EC2 upgraded** `t3.medium` → `t3.xlarge` to eliminate OOM crashes.
- **Hardened `vhc-backend`** with memory caps + worker recycling. Killed rogue gunicorn shadow service.
- **Nginx rate-limit** added at `/api/extension/capture` (10 r/s).
- **`/api/health/live`** new lightweight probe.
- **Advanced / AI / Autocomplete search** keyword fallback fixes shipped (testing-agent verified).
- **BGE embeddings backfill** — 100% coverage (124 223 / 124 130 candidates).
- **RunPod pod migration** from `he7bjmeo47qa3o` → `31uikf6dsy0z8w` (both 8000 + 8001 exposed).
- **Auto-merge regression fix (Phase 55.1)** — relaxed `_names_are_similar` to allow:
  - first-name token match,
  - shared 3+-char token (handles reversed order),
  - SequenceMatcher ≥ 0.70 for typos.
  - Verified 10/10 unit cases pass including the "Deepak vs Renu" negative guard.
- **Cross-encoder reranker wired (Phase 55.2)** — `_cross_encoder_rerank` calls
  the RunPod sidecar `/rerank` (BAAI/bge-reranker-base) for top-N precision
  boost. Feature-flagged via `CROSS_ENCODER_ENABLED=true`. Falls back to the
  cheaper bi-encoder hybrid rerank on any failure.
- **Unified RunPod Docker image (Phase 55.2)** — `Dockerfile.unified` +
  `supervisord.conf` + `entrypoint.sh` so vLLM + BGE sidecar boot together
  on every pod start. Eliminates the daily-manual sidecar startup chore.
- **WhatsApp `team_daily_digest_v1` submission script (Phase 55.3)** —
  `backend/scripts/submit_whatsapp_template.py` supports `--submit`,
  `--list`, `--status`, `--delete` against Meta WABA API.

### Phase 54 — late Jan/Feb 2026
- WhatsApp Cloud API integration (`whatsapp_cloud_service.py`).
- BGE sidecar HTTP client + `/rerank` endpoint (`embed_client.py`).
- 2/3 match-gate auto-merge in extension capture (`candidate_merge.py`).
- Bulk backlog merge script (`merge_backlog_duplicates.py`).
- LLM extraction truncation fixes; Anthropic fallback for RunPod 524 timeouts.

---

## Pending / next priorities

### Immediate (P0/P1)
1. ~~**(P0)** Run `merge_backlog_duplicates.py --apply` on EC2~~ ✅ **DONE 2026-05-18** — 19 duplicate groups merged, Dedup tab is empty.
2. ~~**(P1)** Build Bill Generator MVP (PDF + Resend + Qwen LLM body + reminders)~~ ✅ **DONE 2026-05-21** — 11/11 backend tests + frontend smoke passing. See `docs/BILL_GENERATOR_RUNBOOK.md`.
3. ~~**(P1)** Auto-deploy script to stop the "I pulled but UI is stale" pain~~ ✅ **DONE 2026-02 (current session)** — `scripts/deploy.sh` + `scripts/post-merge.hook`. See `docs/DEPLOY_RUNBOOK.md`.
4. ~~**(P2)** Auto-draft Bill on candidate `hired`/`joined`~~ ✅ **DONE 2026-02 (current session)** — `services/bill_auto_draft.py`, idempotent via `line_items.application_id`. 20/20 unit tests passing.
5. ~~**(P2)** Reactivate user `hr8@vhc.in`~~ ✅ **DONE** (confirmed by user).
6. ~~**(P1)** Tally integration — one-way push VHC bills → Tally Sales Vouchers~~ ✅ **DONE 2026-02 (current session)** — `routes/tally_bridge.py` + `services/tally_xml.py` + Windows `tally_bridge/tally_bridge.py` agent. 24/24 e2e tests passing. See `docs/TALLY_BRIDGE_RUNBOOK.md`.
7. ⏸ **(P1, HELD)** Submit `team_daily_digest_v1` template to Meta — paused per user direction.
8. ⏸ **(P1, HELD)** Build & push unified RunPod image — paused per user direction.
9. ~~**(P0)** Chrome Extension v5.5.5 → v5.5.8 evolution — "Already in Database" badge clickable + matching accuracy~~ ✅ **DONE 2026-02-25/26 (current session)**
   - v5.5.5/6: badge → `<a>` anchor with `profile_url` from backend (`SITE_URL`-derived).
   - v5.5.7: backend returns `matched_candidate` (full DB fields) so client can cross-check before badging.
   - v5.5.8 (rebalanced): server score gate at 1.0 with no "strong signal required" hard rule (was too strict). Client switched from score-based to **conflict-based** post-validation (only rejects on employer mismatch or experience >3y apart). Naukri ID mismatch no longer disqualifies (Naukri rotates IDs every few hours per user feedback).
10. ~~**(P0)** Backend perf — deep-link badge → profile dialog was multi-second slow~~ ✅ **DONE 2026-02-26 (current session)**
    - Missing `candidate_bank.id_idx` index (UUID lookups were COLLSCANs on 126k docs) — added, single biggest win.
    - Added `audit_logs.entity_id + created_at` compound index.
    - `get_candidate` no longer awaits `log_activity` write (true fire-and-forget via `asyncio.create_task`).
    - Frontend: skip heavy list fetch when deep-link `?candidateId=` present; parallelized 4 detail calls; removed redundant `getById`.
    - Result: P99 dropped from ~2-5s → 115-547ms (5-10x improvement).
11. ~~**(P0)** `ChunkErrorBoundary` to recover from stale-bundle crashes~~ ✅ **DONE 2026-02-26 (current session)** — `components/ChunkErrorBoundary.jsx`. Catches `ChunkLoadError`, `SyntaxError: Unexpected token '<'`, `ReferenceError` from stale bundles; auto-reloads page once (30s guard). Eliminated the 162 `searchParams is not defined` errors flagged in the 2026-05-26 maintenance report.
12. ~~**(P0)** RunPod BGE sidecar restored + autonomy~~ ✅ **DONE 2026-02-26 (current session)** — Fixed `sidecar_keeper.sh` to invoke `python3 -m uvicorn embed_service:app --host 0.0.0.0 --port 8001` (the script has no `__main__` block, so old `python3 embed_service.py` exited immediately). Added cron `*/10 * * * *` to auto-monitor + restart. Pod proxy URL updated to `https://ccl2pccemzrjsw-8001.proxy.runpod.net`.
13. ~~**(P0)** Atlas password rotation reconciliation~~ ✅ **DONE 2026-02-26 (current session)** — `vhc_app_user` password had been rotated in Atlas but never propagated to `backend/.env`. Backend was running on cached connections; would have died on next pool reconnect. New password installed in `.env` via URL-encoded sed, ping verified, indexes created successfully.
14. ~~**(P0)** Gunicorn memory leak mitigation~~ ✅ **DONE 2026-02-27 (current session)** — Workers were bloating to 3.2GB+ within 1h41m, hitting cgroup MemoryHigh=5G and forcing 240K swap. Root cause traced to `_fire_and_forget` in `routes/extension.py` spawning unbounded `threading.Thread` per capture, each with own asyncio event loop + AsyncIOMotorClient + MongoClient — ~30-40MB glibc retention per capture. **Mitigation applied:** lowered `--max-requests` from 100 → 25 in `/etc/systemd/system/vhc-backend.service.d/override.conf`. After kill + restart: worker RSS 3.2GB→913MB, available RAM 1.7GB→5.2GB. `py-spy` installed for future flamegraph diagnosis.
15. ~~**(P1)** Extension auto-capture on Naukri preview UI~~ ✅ **RESOLVED 2026-02-27** — User confirmed auto-capture is working on current Naukri UI. Extension v5.5.9 (overlay-fix package in `/app/backend/static/extensions/`) is no longer needed; can be discarded or kept on the shelf.
16. ~~**(P0)** Memory leak Step 1 patch — gc.collect() + malloc_trim(0) in background~~ ✅ **DEPLOYED 2026-02-27 (current session)** — py-spy dump on PID 43584 (3.7 GB RSS / 4.4 GB VmData) revealed the leak lives in glibc secondary arenas. Added `gc.collect() + libc.malloc_trim(0)` to a new `_release_memory()` helper called from a `finally` block at the end of `_background_full_groq_enrich`. Result: leak rate reduced ~3x but worker 1007 still bloated to 3.2 GB over 3h29m — confirmed foreground request handler is the LARGER leak source.
17. 🟡 **(P0) Memory leak Step 2 patch — apply `_release_memory()` to foreground capture path** **DEPLOYED 2026-02-28 (current session, awaiting verification)** — Added FastAPI dependency `_force_memory_release_after_response()` with yield-cleanup that calls `_release_memory()` AFTER each `/api/extension/capture` response is flushed. Hooked into `capture_profile` via `_mem: None = Depends(...)`. Catches the ~250-300 MB/capture leak from inline regex parsing, Pydantic model construction, sanitization, LaTeX regen, and BSON serialization. Awaiting 2-3h soak test under normal traffic. Code: `routes/extension.py:998-1014, 1902-1905`.
18. ~~**(P0) Step 3 — Replace glibc malloc with jemalloc (LD_PRELOAD)**~~ ✅ **DEPLOYED 2026-02-28 (current session)** — py-spy dump on PID 6786 (2.6 GB RSS, 0 active threads, all idle) proved residual leak was glibc per-thread arena fragmentation, NOT Python code. Installed `libjemalloc2`, added `LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2` + `MALLOC_CONF=background_thread:true,...,dirty_decay_ms:5000,muzzy_decay_ms:5000` to `/etc/systemd/system/vhc-backend.service.d/override.conf`. Restarted backend. Immediate: workers baseline RSS dropped 33% (1.2GB → 800MB), available RAM jumped from 2.2GB → 6.0GB. jemalloc proactively decays unused memory back to kernel every 5s.
19. ~~**(P0) BGE Sidecar Resurrected — Moved to EC2 CPU**~~ ✅ **FIXED 2026-02-29 (current session)** — RunPod unified pod was dead (all URLs returning 404). Tried Vast.ai (UX too messy), then RunPod L4 with pytorch template (Jupyter/nginx blocking ports), then settled on simplest path: ran BGE sidecar directly on existing EC2 CPU. Installed `sentence-transformers==3.0.1`, `transformers==4.44.2`, `torch==2.2.2+cpu`, `numpy<2`, `scipy<1.14` in `/opt/bge-sidecar/venv/`. Created systemd service `bge-sidecar.service` listening on `127.0.0.1:8002` with MemoryMax=2.5G. Updated `BGE_SIDECAR_URL=http://127.0.0.1:8002` in backend `.env`. Both BAAI/bge-small-en-v1.5 (embed) and BAAI/bge-reranker-base (rerank) loaded. Zero RunPod cost, zero cold starts. Performance: CPU embed ~80ms (vs GPU ~30ms) — acceptable for current scale. Skipped Docker/RunPod permanent fix (deferred).
20. ~~**(P0) RunPod Qwen14B restored (A6000) + LLM log labels truthful**~~ ✅ **FIXED 2026-02-29** — New RunPod pod `8m5o6hyse40pbu` running vLLM with Qwen2.5-14B-Instruct-AWQ, max_model_len=32768. Updated `RUNPOD_VLLM_URL` in `.env`. Verified chain: RunPod Qwen is PRIMARY (Layer 1), Emergent Haiku is FALLBACK (Layer 2). Cleaned up misleading hardcoded `[BG-Haiku]` log labels in routes/extension.py — now shows `[BG-LLM] source=runpod_qwen14b` reflecting actual server. Memory soak confirmed 43/43 captures served by RunPod (100% primary hit rate).
21. ~~**(P1) Max-requests raised 25 → 500**~~ ✅ **DEPLOYED 2026-02-29** — After confirming workers stay flat at ~870MB through 325 captures (jemalloc + cleanup hooks holding), raised gunicorn `--max-requests` 20× to cut CPU recycle churn. Worker recycle frequency now ~1-2/hr instead of ~10/hr.
22. ~~**(P2) Custom Analytics Hub (Phase 56)**~~ ✅ **SHIPPED 2026-02-29** — Privacy-first first-party analytics. Backend: `routes/analytics_pageviews.py` with `POST /track` (anonymous + authed) + `GET /hub/dashboard` (admin). Frontend: `hooks/useAnalytics.js` auto-tracks route changes, `pages/admin/AnalyticsHubPage.jsx` shows KPIs + DAU chart + Top Pages + Top Recruiters + Activity Funnel + Top Referrers. IP hashing daily-salted SHA256, no cookies, no Google. 4 MongoDB indexes on `analytics_pageviews` collection.
23. ~~**(P3) trackEvent telemetry wired into 5 flows**~~ ✅ **SHIPPED 2026-02-29** — Custom events now fire on: `mandate_created` (employer + AM flows), `stage_changed` (drag+drop and quick-move), `search_performed`, `application_submitted`. Powers funnel analytics in the Hub.
24. ~~**(P3) k-Means + PCA candidate clustering MVP**~~ ✅ **SHIPPED 2026-02-29** — Pipeline at `scripts/cluster_candidates.py` reads BGE embeddings → PCA(32) → MiniBatchKMeans → writes `cluster_id` to embeddings + `candidate_clusters` collection (centroid + label + samples). Admin endpoints: `GET /api/clustering/clusters`, `GET /api/clustering/clusters/{id}/candidates`, `POST /api/clustering/run`, `GET /api/clustering/status`. Frontend `pages/admin/ClustersPage.jsx` with grid view + drill-down modal. Needs first run trigger to populate (manual or scheduler).
25. ~~**(P3) XGBoost LTR Reranker — properly scoped**~~ ✅ **SCOPING DOC DELIVERED 2026-02-29** at `/app/memory/XGBOOST_LTR_SCOPING.md`. Concluded 5-6 sessions needed (20-27 hours). Phase 1 prerequisite: build `search_sessions` telemetry collection FIRST (no model yet), let real recruiters generate ≥5k labeled triplets over 2-3 weeks. Then train, A/B test, ship. Also documented lighter-weight alternative: 3-5 hand-crafted features as post-rerank tie-breaker (~3-5% precision gain, 1-2 hours work).
26. ~~**(P1) "Already in Database" badge fast-path + LRU cache**~~ ✅ **SHIPPED 2026-03-01 (current session)** — `/api/extension/check-existing` was already optimized once (25 queries → 1) but still did a fuzzy `name_lower` prefix scan for every card. Two changes: (1) **Fast path:** cards with a stable Naukri Resdex `data-target-id` (scraped into `candidate.naukri_id`, NOT the rotating URL `pid` token) now resolve via ONE indexed `$in` lookup on `naukri_profile_id` / `naukri_id`; bypasses the fuzzy scan entirely. (2) **TTL cache:** the fuzzy fallback's per-first-token bucket is cached in-process for 5 min (bounded 256 keys), so popular first names (`akash`, `rahul`) skip Mongo after warm-up. Added `CandidateIn.naukri_id` schema field (was being silently dropped by Pydantic). Added `candidate_bank.naukri_profile_id` index in `services/lifecycle.py`. Curl-tested: warm cache call **5× faster** than cold (1.94s → 0.39s on preview env). Files: `routes/extension_check.py`, `services/lifecycle.py`. **Lever #4 (lean projection) intentionally skipped** — `_score_match` consumes both `skills` and `education` from the bulk fetch, so dropping them would degrade match quality.
27. ~~**(P1) Auto-merge regression — Phase 56.1 (spaced-letter names + double-match early-exit)**~~ ✅ **SHIPPED 2026-03-01 (current session)** — Dupe scan showed 13 pairs slipping past capture-time dedup. RCA found three causes: (a) Naukri occasionally renders names with whitespace between every letter (`"A J I T H"`); `_names_are_similar` tokenized to all-single-char then filtered to empty list → False → phone-match record was treated as "stale", incoming phone stripped, new dupe inserted. (b) Path-1 dedup gated every key match (email / phone) on `_names_are_similar`, so a weak name match nuked even strong 2-of-3 evidence (Yash vs Yash Vardhan with same email + phone). (c) Bulk-import dedup used strict case-sensitive lowercase email + `phone_normalized` only (missed legacy records with mixed-case email or unbackfilled phone_normalized). Fix: (1) `_names_are_similar` now retries with a de-spaced form when ≥50% of cleaned tokens are single-char; (2) new "DOUBLE-MATCH EARLY EXIT" in `extension.py` capture path — when email AND phone independently match the SAME record, merge unconditionally regardless of name variation; (3) `bulk_import.py` dedup now uses case-insensitive email regex + `$or` on `phone_normalized | phone` to catch un-backfilled legacy docs. 8/8 unit cases pass including all three observed dupe pairs. Files: `services/extension_service.py`, `routes/extension.py`, `routes/bulk_import.py`.
28. ~~**(P1) Badge recall fix — Phase 56.2 V2 dark-launched to admin**~~ ✅ **SHIPPED 2026-03-01 (current session)** — Real recall was ~1-2 of 15 known-in-DB candidates badged on a Naukri search page (10-15%). RCA: (a) V1 used `_strict_name_match` requiring BOTH first AND last token equal — rejected "Yash" ↔ "Yash Vardhan". (b) V1 score threshold of 1.0 needed strong signals (employer/ctc/skills) that search cards rarely expose. (c) Headline string ("ML Engineer at TCS - Pune") had untapped employer/designation/location info. Telemetry from EC2 confirmed only 22.8% of DB has `naukri_profile_id` (the fast-path coverage cap), while 99.7% have location, 88.7% designation, 88% employer. Fix: built `_loose_name_match_v2`, `_score_match_v2`, `_has_explicit_conflict_v2`, `_headline_contains` helpers + a `_BADGE_THRESHOLD_V2=0.85` threshold. Smart name matching: tight when both names are multi-token (require first+last OR fuzzy ≥0.80, prevents "Akash Sharma" ↔ "Akash Gundekar" false positive), loose when one side is single-token (catches "Yash" ↔ "Yash Vardhan"). Smarter headline parsing: `headline_designation` (+0.30) and `headline_location` (+0.15) signals. Location weight bumped 0.25→0.30. Explicit conflict rejection: card-employer vs DB-employer mismatch, or experience gap > 5y. ≥2 signal corroborator gate prevents name-alone badging. Dark-launched via `EXTENSION_CHECK_V2_USERS=admin@vhc.in` env var — V1 logic unchanged for everyone else. Unit tests: 8/8 name cases pass (including the false-positive guard); curl-tested end-to-end on preview env with realistic payloads. Files: `routes/extension_check.py`. Extension untouched — no v5.5.10 push, no update banner.
29. ~~**(P1) `name_lower` backfill — Phase 56.3a**~~ ✅ **SHIPPED 2026-06-02** — Diagnostic revealed 2,317 records (1.8% of 129,519) had no `name_lower` field. The badge endpoint's first-token bucket query is built on `name_lower` — so those records were invisible to the scan regardless of how good the scoring became. Wrote `/tmp/backfill_name_lower.py` (one-shot, Atlas-tier-friendly without `no_cursor_timeout`). Backfilled all 2,314 candidates with names; remaining 4 had `name=null`. Confirmed sample case (Godwin J Sobin, phone 9487957850) now indexed correctly. This was the silent root cause of "candidates obviously in DB but never badged."
30. ~~**(P1) Badge Audit framework — Phase 56.3b**~~ ✅ **SHIPPED 2026-06-02 (current session)** — User said the search session is "long gone" by the time we want to debug a missed match. Built a full verification bench so this is never a problem again. Backend: new `badge_audit` collection (TTL 30d), 4 endpoints under `/api/admin/badge-audit/` (list / get / label / stats overview), `/api/extension/audit/feedback` for v5.5.10+ extension to report which results it actually rendered as badges vs filtered out client-side. Every `/check-existing` call from a V2-audited user writes one doc capturing: card payload, backend decision (score, signals, matched DB record, conflict reason), V1/V2 path, took_ms, page URL. Audit ID returned in response so extension can later submit `/audit/feedback`. Frontend: `/admin/badge-audit` page with 5-tile rolling stats strip, recent-batches list with V2/unlabeled filters, per-card decision drilldown showing card payload ↔ best-match DB record ↔ matched signals ↔ conflict reasons, 4-label thumbs UI (correct / false_positive / false_negative / uncertain) with optional notes — labels accumulate as a benchmark dataset over time. Tested end-to-end on preview: insert → list → drilldown → label → stats all return 200. Files: `routes/badge_audit.py` (new), `routes/extension_check.py` (audit hook + audit_id in response), `services/lifecycle.py` (TTL index), `server.py` (router register), `pages/admin/BadgeAuditPage.jsx` (new), `App.js` (route).

### Near-term (P2)
9. Drop unused MongoDB indexes (audit after 7-day cluster uptime).
10. Flip `CROSS_ENCODER_ENABLED=true` in `.env` after smoke-testing reranker latency on prod traffic.
11. ⏸ **(P2, HELD)** Public deep-link page for rich WhatsApp daily digest — paused per user direction.
12. Marketing site deployment (staged for review in `/app/marketing_review/`, pending green-light).
13. **(P2)** Tally Phase 55.9 — Bulk client-ledger sync (push VHC companies → Tally ledgers automatically).
14. **(P2)** Tally Phase 55.10 — Pull payment receipts from Tally → auto `mark-paid` on VHC bills.
15. **(P2)** Admin UI: "Tally Bridge Health" page (pending count, last sync, recent errors).

### Future (P3)
11. Email Template Management UI.
12. XGBoost LTR re-ranker (currently using cross-encoder as the precision layer).
13. k-Means + PCA clustering for candidate discovery in the sourcing tab.

### Held / awaiting decision
- **Track 2 — Gunicorn memory leak root-cause fix** (held by user 2026-02-27, monitoring Track 1 mitigation first):
  - Replace `_fire_and_forget(threading.Thread)` in `routes/extension.py` with module-level `ThreadPoolExecutor(max_workers=4)`.
  - Cache `MongoClient` + `AsyncIOMotorClient` at module level (eliminate per-capture SSL/socket churn).
  - Add explicit `gc.collect()` at end of `_background_full_groq_enrich`.
  - Use single shared asyncio event loop per worker (background thread) instead of new loop per capture.
  - Expected outcome: per-capture leak drops from ~30-40MB → ~2-3MB; workers stay flat at ~900MB indefinitely; can raise `--max-requests` back to 500+.
  - Trigger: re-evaluate if worker RSS climbs >2GB despite `max-requests=25`, OR after user observes Track 1 for a few days.

---

## Known issues
- WhatsApp permanent access token was leaked in chat **twice** historically; user confirmed rotation each time. Treat new tokens as sensitive — never paste in chat.
- The old pod-id `he7bjmeo47qa3o` is removed from `.env` (May 2026 fork).

## Test credentials
See `/app/memory/test_credentials.md`.
