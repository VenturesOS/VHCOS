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
