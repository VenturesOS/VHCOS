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
9. ~~**(P0)** Chrome Extension v5.5.5/v5.5.6 — "Already in Database" badge clickable, opens candidate profile in VHC~~ ✅ **DONE 2026-02-25 (current session)** — Badge rendered as `<a>` anchor with deep-link URL. v5.5.5: link derived client-side from `apiUrl`. **v5.5.6 (fix):** backend now returns `profile_url` directly in `check-existing` response, derived from `SITE_URL` env var — eliminates client-side guessing (broken for proxied API hosts like Cloudflare Workers). Frontend has new role-aware `/candidate-bank` redirect route (preserves `?candidateId=`). `?next=` param honoured by Login.jsx. CRX + ZIP built and served via `/api/extension/update.xml` (sha256 hashed).

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

---

## Known issues
- WhatsApp permanent access token was leaked in chat **twice** historically; user confirmed rotation each time. Treat new tokens as sensitive — never paste in chat.
- The old pod-id `he7bjmeo47qa3o` is removed from `.env` (May 2026 fork).

## Test credentials
See `/app/memory/test_credentials.md`.
