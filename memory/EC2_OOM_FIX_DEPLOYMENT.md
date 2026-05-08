# 🔴 CRITICAL OOM FIX — Deployment Guide (May 5, 2026)

## Root Cause (from your journalctl logs)

The OOM kill at 13:04:56 was caused by **3 compounding bugs**:

### Bug #1 — Embedding Task Leak (extension.py)
- `_embed_now()` was spawned via `asyncio.ensure_future()` inside a thread that closes its event loop when the parent finishes
- **Logs evidence**: dozens of `ERROR:asyncio:Task was destroyed but it is pending! task: <Task pending name='Task-XXXXX' coro=<_background_full_groq_enrich.<locals>._embed_now()>` from 12:35 onwards
- Each leaked task held an `AsyncIOMotorClient` (50-conn pool) → ran out of file descriptors + retained the BGE sentence-transformer tensor buffers in worker RAM

### Bug #2 — matching_engine.py still using strict `json.loads`
- The earlier fix added `json_repair` only to `llm_fallback_service.py`
- **Logs evidence**: `ERROR:services.matching_engine:[RESUME PARSE] JSON parse error: Expecting ',' delimiter` repeated every 30s for the same candidate (Kunal Jagdish Chavan), each retry consuming Anthropic credits and CPU

### Bug #3 — OpenAI embedding key invalid (401)
- **Logs evidence**: `ERROR:services.embeddings:Embedding generation failed: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-proj-...QrQA'`
- This key appears in `embeddings.py` and is called by `applications.py`, `candidates.py`, `job_queue.py`
- Each failed call burns CPU on retry + spams logs

---

## What Was Fixed in This Commit

### File 1: `backend/routes/extension.py`
- ✅ Added module-level `_EMBED_THREAD_SEMAPHORE` (BoundedSemaphore, default 2 slots) to cap concurrent embeds per worker
- ✅ Replaced `asyncio.ensure_future(_embed_now())` with `await`-style INLINE execution inside the existing async background flow
- ✅ Reduced motor client `maxPoolSize=5` per spawned client (was using global default of 50) and added `serverSelectionTimeoutMS=5000`
- ✅ Added 30s acquire timeout — if too many embeds queue up, capture skips embedding gracefully (logs "embed-queue full")

### File 2: `backend/services/matching_engine.py`
- ✅ `parse_resume_with_ai()` now tries `json.loads` first and falls back to `json_repair.repair_json()` if strict parsing fails

---

## Deployment on EC2 (Manual Steps)

```bash
# SSH into the EC2 box
ssh ubuntu@<your-ec2-ip>

# Pull the fix
cd /home/ubuntu/vhc-platform
git pull origin main

# Verify json_repair is installed in the venv (should already be, from previous incident)
source backend/venv/bin/activate
python -c "import json_repair; print('json_repair version:', json_repair.__version__)"
deactivate

# Restart gunicorn
sudo systemctl restart gunicorn

# Wait 5s and verify
sleep 5
sudo systemctl status gunicorn --no-pager | head -20

# Confirm health
curl -s https://ventureshrd.com/api/health/incident-analysis | python3 -m json.tool | head -30
```

---

## Verification Checklist (15 min after restart)

### 1. No more "Task destroyed" errors
```bash
sudo journalctl -u gunicorn --since "5 min ago" | grep -i "task was destroyed" | wc -l
# EXPECTED: 0 (was 50+ before fix)
```

### 2. No more matching_engine JSON storms
```bash
sudo journalctl -u gunicorn --since "5 min ago" | grep -i "RESUME PARSE.*JSON parse error" | wc -l
# EXPECTED: 0 (was repeated every 30s for same candidate)
```

### 3. Memory holding steady
```bash
free -m
ps -eo pid,ppid,rss,cmd --sort=-rss | grep gunicorn | head -5
# EXPECTED: each worker < 600 MB (was hitting 3 GB single-worker before OOM)
```

### 4. Capture flow still working
```bash
sudo journalctl -u gunicorn --since "5 min ago" | grep "BG-Haiku.*COMPLETE" | wc -l
# EXPECTED: > 0 (captures continuing to enrich)
```

---

## Optional — Fix the OpenAI 401 (Bug #3)

This is NOT critical for OOM (the BGE embedder in `talent_graph_service.py` is the active path), but it spams logs and burns CPU on retries.

Choose ONE:

### Option A — Replace the bad OpenAI key
```bash
# Edit /home/ubuntu/vhc-platform/backend/.env
OPENAI_API_KEY=sk-proj-<your-NEW-valid-key>

sudo systemctl restart gunicorn
```

### Option B — Disable the OpenAI embedding fallback entirely
Since `services/talent_graph_service.py` uses local BGE-small for embeddings (works fine), the `services/embeddings.py` (OpenAI text-embedding-3-small) only powers the legacy "find similar candidates" UI path. If you don't use it actively:

```bash
# Edit /home/ubuntu/vhc-platform/backend/.env — comment out or remove
# OPENAI_API_KEY=...
```

The service self-disables when `OPENAI_API_KEY` is unset (logs "embeddings disabled" once at boot, no per-call 401 spam).

---

## Memory Watchdog (Optional Hardening)

To prevent any future OOM from killing the whole service, edit
`/etc/systemd/system/gunicorn.service` and add under `[Service]`:

```ini
MemoryMax=3G
MemoryHigh=2.5G
TasksMax=200
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart gunicorn
```

This way, if memory ever spikes again, systemd will throttle/restart gunicorn cleanly instead of letting the kernel OOM-kill it.
