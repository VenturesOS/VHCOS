# Phase 54.14 — BGE Embedding Sidecar (D1)
**Date:** 2026-05-11
**Goal:** Move local BGE-small embedding model from EC2 → RunPod sidecar to free ~1GB EC2 RAM, enabling t3.medium downsize (~₹2,690/mo saving).

## Current architecture

```
[EC2 t3a.large]
├── gunicorn → fastapi
│   ├── services/talent_graph_service.py
│   │   └── _get_embed_model() → BAAI/bge-small-en-v1.5 (sentence-transformers)
│   │       ├── 80MB on disk
│   │       └── 800MB–1.2GB resident RAM (PyTorch tensors + tokenizer + scratch)
│   └── 4 callers:
│       ├── routes/extension.py:1242  (post-capture)
│       ├── routes/talent_graph.py    (manual upsert)
│       ├── routes/sourcing_search.py (semantic search)
│       └── scripts/backfill_talent_graph.py
```

Problem: model is pinned in RAM 24/7. Peak memory ≈ 3.5GB on t3a.large (8GB) which prevents t3.medium (4GB) downsize.

## Target architecture

```
[EC2 t3.medium]                          [RunPod RTX A5000]
gunicorn → fastapi                        vLLM (Qwen 14B :8000)
└── services/embed_client.py     ──HTTP──→ FastAPI sidecar (port 8001)
    └── POST /embed {"texts":[]}          └── BGE-small-en-v1.5
        └── Redis cache check first           ├── normalize=True
            (24h TTL on text→vector)          └── batched
```

Memory wins:
- EC2 frees ~1GB (sentence-transformers + torch unloaded)
- Peak RAM expected: ~2.5GB → fits in t3.medium (4GB) with headroom

## API contract — RunPod sidecar

### `POST /embed`
Request:
```json
{
  "texts": ["candidate 1 raw text", "candidate 2 raw text"],
  "normalize": true
}
```
Response (200):
```json
{
  "embeddings": [[0.012, -0.041, ...], [...]],
  "dim": 384,
  "model": "BAAI/bge-small-en-v1.5",
  "took_ms": 8
}
```
Errors:
- 503 if model not loaded yet (return retryable error to client)
- 500 + traceback in body for any internal failure

### `GET /health`
Returns `{"ok": true, "model_loaded": true}` after warmup.

## Files to create/modify

### NEW files
- `backend/services/embed_client.py` — HTTP client for the sidecar
- `runpod-sidecar/embed_service.py` — the FastAPI app deployed on RunPod
- `runpod-sidecar/Dockerfile` — base image + deps
- `runpod-sidecar/requirements.txt` — minimal (fastapi, uvicorn, sentence-transformers)
- `backend/scripts/backfill_pending_embeddings.py` — daily cron at 9AM IST to catch any deferred captures
- `backend/tests/test_embed_client.py` — unit + integration tests with mocked HTTP

### MODIFIED files
- `backend/services/talent_graph_service.py`:
  - Replace `_get_embed_model()`, `embed_text()`, `embed_texts_batch()` with calls to `embed_client`
  - Remove `from sentence_transformers import SentenceTransformer`
- `backend/routes/extension.py:1242`:
  - Wrap embedding call in try/except — on failure mark `embedding_pending=true`
- `backend/requirements.txt`:
  - **After deploy verified**: remove `sentence-transformers`, `torch`, `tokenizers` (saves ~3GB venv disk + RAM)

## Failure modes & retries

| Scenario | EC2 behavior |
|---|---|
| RunPod pod is OFF (cron stopped at 18:30 IST) | Cache hit serves common candidates; on miss → set `embedding_pending=true`, return None. Backfill cron at 09:05 IST sweeps these. |
| RunPod pod is initializing (just started) | `/health` returns `model_loaded:false`; client retries with exp. backoff (1s, 2s, 4s, max 3 tries) |
| Network blip mid-encode | Same 3-retry policy |
| Sidecar crashes mid-batch | RunPod restarts container; EC2 client gets connection refused → defer pattern as above |

## Deployment plan

### Step 1 — Build sidecar locally (today, workspace)
- Create `runpod-sidecar/` directory with FastAPI app
- Test locally via Docker

### Step 2 — Push to RunPod template (manual, user does this)
- User updates pod template to expose port 8001 and run sidecar at boot
- Test `/health` from EC2

### Step 3 — Wire up EC2 client (workspace)
- Add `embed_client.py`
- Add `RUNPOD_EMBED_URL` to .env

### Step 4 — Refactor talent_graph_service.py (workspace)
- Replace local model calls with client calls
- Keep `sentence-transformers` install for now (as emergency fallback)

### Step 5 — Soak test (24h)
- Watch logs for failed embeddings
- Validate cache hit rate
- Confirm memory drop on EC2 (`free -h` shows < 2.5GB used)

### Step 6 — Remove sentence-transformers from EC2 (after soak)
- Comment out import → pip uninstall → confirm app still boots
- Worker RSS should drop another 200–300MB

### Step 7 — Downsize EC2 t3a.large → t3.medium (4GB RAM)
- Stop → Change Type → t3.medium → Start
- Compute SP (when bought) auto-applies since it's the same family

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Embedding quality regression (different model version) | Low | Pin exact model name `BAAI/bge-small-en-v1.5` |
| Network latency adds visible UX delay | Low | Encode is async post-capture, no user blocks |
| RunPod sidecar OOMs the existing Qwen pod | Low | BGE-small + 384 batch = ~600MB peak, A5000 has 24GB |
| RunPod proxy bandwidth limits | Very low | 384 floats × 4 bytes = 1.5KB per vec, negligible |

## Estimated savings (final state)

| Step | Saving/mo |
|---|---|
| Move BGE → RunPod (no instance change) | $0 (just enables next step) |
| Remove sentence-transformers from venv | ~50MB disk |
| Downsize EC2 t3a.large → t3.medium | **$0.0806 → $0.0448 = ₹2,210/mo** |
| Plus Compute SP on t3.medium (later) | extra ~₹650/mo |
| **Total D1 saving** | **~₹2,860/mo** |

## Out of scope (future phases)
- Replacing BGE with a larger BGE-large or e5-mistral (quality bump, more RAM)
- Async queue (RabbitMQ / Redis Streams) for embedding requests — current sync HTTP is fine at 60-user scale
