# Phase 54.16 — D1 BGE Sidecar Deployment

**Goal:** Move `BAAI/bge-small-en-v1.5` from EC2 RAM → RunPod GPU sidecar
running inside the existing Qwen vLLM pod. Frees ~1 GB EC2 RAM, enabling
the t3.medium downsize (~₹2,690/mo).

**Status:** Code shipped to workspace + EC2 (after next `git pull`).
Deploy the sidecar manually on RunPod, then flip `BGE_SIDECAR_URL` in
EC2 `.env` to switch traffic over.

## Files shipped
- `/app/runpod-sidecar/embed_service.py` — FastAPI app for the pod
- `/app/runpod-sidecar/start_sidecar.sh` — boot script
- `/app/backend/services/embed_client.py` — EC2 HTTP client
- `/app/backend/services/talent_graph_service.py` — `embed_text` /
  `embed_texts_batch` now try the sidecar FIRST, fall back to local
  sentence-transformers if it's unreachable or `BGE_SIDECAR_URL` is unset.

## Deploy steps (you do these on RunPod)

### 1. Open a terminal in your RunPod pod
RunPod dashboard → My Pods → click the running A5000 pod → **Connect →
Start Web Terminal** (or SSH if you have the key set up).

### 2. Create the sidecar directory + copy files
```bash
mkdir -p /workspace/bge_sidecar
cd /workspace/bge_sidecar

# Pull from your VHC GitHub repo (cleanest), OR scp from your laptop.
# Easiest: download both files raw from GitHub:
curl -fsSL https://raw.githubusercontent.com/VenturesOS/VHCOS/main/runpod-sidecar/embed_service.py -o embed_service.py
curl -fsSL https://raw.githubusercontent.com/VenturesOS/VHCOS/main/runpod-sidecar/start_sidecar.sh -o start_sidecar.sh
chmod +x start_sidecar.sh
```

### 3. Install deps (one-time, ~60 s)
```bash
pip install fastapi==0.118.0 uvicorn==0.34.0 sentence-transformers==3.0.1
```

> Note: the pod's existing vLLM venv already has torch + CUDA, so
> sentence-transformers reuses them. No GPU driver work needed.

### 4. Start the sidecar (foreground first, to watch logs)
```bash
bash start_sidecar.sh
```

Wait for: `[BGE-Sidecar] Ready in 2.3s`. The model warms during startup.

### 5. Verify from the pod itself
```bash
curl -s http://localhost:8001/health
# expect: {"ok":true,"model_loaded":true,"model_name":"BAAI/bge-small-en-v1.5","device":"cuda","dim":384}

curl -s -X POST http://localhost:8001/embed \
  -H "Content-Type: application/json" \
  -d '{"texts":["test query"]}'
# expect: {"embeddings":[[..384 floats..]],"dim":384,"device":"cuda",...}
```

### 6. Verify from outside (via RunPod proxy)
Your pod URL is already wired into EC2 as `https://31uikf6dsy0z8w-8000.proxy.runpod.net`
for vLLM. The sidecar uses port 8001 → URL becomes:
**`https://31uikf6dsy0z8w-8001.proxy.runpod.net`**

> RunPod exposes any port that has a process bound to `0.0.0.0` — no
> firewall changes needed.

From your laptop or EC2:
```bash
curl -s https://31uikf6dsy0z8w-8001.proxy.runpod.net/health
```

### 7. Persist the sidecar across pod restarts
RunPod pods don't run start scripts on resume by default. Easiest fix:
make the sidecar part of the pod's CMD/entrypoint via the template.

**Option A — Template edit (recommended):**
1. RunPod → My Pods → ⋯ → **Edit Template** (or "Save as template")
2. In **Container Start Command**, append:
   ```
   ; nohup bash /workspace/bge_sidecar/start_sidecar.sh > /var/log/bge.log 2>&1 &
   ```
   (semicolon then the start, backgrounded — keeps vLLM as the foreground proc)
3. Save template. Next time the pod resumes, both vLLM AND the sidecar start.

**Option B — Cron the pod itself:**
Add to the pod's crontab:
```cron
@reboot /workspace/bge_sidecar/start_sidecar.sh > /var/log/bge.log 2>&1 &
```

### 8. Wire EC2 to use the sidecar
On EC2:
```bash
cd /home/ubuntu/vhc-platform/backend
echo "" >> .env
echo "# Phase 54.16 — BGE embeddings sidecar (Qwen pod port 8001)" >> .env
echo "BGE_SIDECAR_URL=https://31uikf6dsy0z8w-8001.proxy.runpod.net" >> .env

# Restart so the env is picked up
sudo systemctl restart gunicorn
```

### 9. Verify EC2 is using the sidecar
```bash
# Should now show remote embeddings in talent graph activity:
sudo journalctl -u gunicorn --since "5 min ago" | grep -i "embed\|sidecar" | tail -10
```

Trigger any candidate capture or `/api/sourcing/search` call and watch
EC2 memory drop ~1 GB on the next gunicorn restart (the local model is
no longer loaded since `embed_remote()` returns early).

## Soak test (24 h)
Watch for:
- `[EmbedClient] sidecar call failed` warnings in gunicorn logs (>5/min
  means the sidecar is unstable — investigate).
- EC2 `free -h` shows `used` drop by ~1 GB compared to pre-deploy.
- RunPod pod GPU memory: should still be comfortably under 24 GB.

## Decommission step (after 24 h clean soak)
- Remove `sentence-transformers`, `torch`, `tokenizers` from
  `backend/requirements.txt`.
- Run `pip uninstall -y sentence-transformers torch tokenizers` on EC2.
- Comment out the `SentenceTransformer` import inside `_get_embed_model()`
  (the legacy fallback). Embeddings will be 100 % sidecar-dependent.
- Downsize EC2: t3a.large → **t3.medium** (4 GB RAM) — saves the
  ~₹2,690/mo this whole project was about.

## Rollback (any time)
Just remove the `BGE_SIDECAR_URL` line from EC2 `.env` and restart
gunicorn. The local `_get_embed_model()` fallback kicks in automatically.

## Cost note
Sidecar runs only when the RunPod pod is up (8:50 AM – 6:30 PM IST per
the cron schedule fixed earlier today). Outside those hours,
`embed_remote()` fails fast → local fallback runs. So nightly captures
still work, just slower (CPU vs GPU). For 8.5 PM – 8:50 AM IST when
your team isn't actively recruiting, that's acceptable.
