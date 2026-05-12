# Phase 54.17 — Combined Deployment: Local Redis + git pull + BGE Sidecar

**Date:** Feb 2026  
**Trigger:** Upstash free tier exhausted (500k commands / month). Cache
silently disabled, rate limiter falling back to in-memory, pipeline
cache cold on every request.

## What this deployment ships
1. **Local Redis** on the EC2 `t3a.large` instance (replaces Upstash)
2. **Workspace code already committed**: `pypdf` migration, pipeline
   pagination + denormalized stage counts, BGE sidecar client.
3. **BGE sidecar** running inside the RunPod A5000 pod (frees ~1 GB EC2 RAM)

## Code change shipped in this session
`backend/services/redis_client.py` now supports BOTH:
- `REDIS_URL` (e.g. `redis://localhost:6379`) → redis-py TCP client
- `UPSTASH_REDIS_REST_URL` + token → legacy Upstash REST (fallback)

`REDIS_URL` is tried **first**. If it succeeds, Upstash is ignored
completely — no surprise quota hits.

`requirements.txt` now pins `redis==5.3.1`.

---

## Step-by-step (run on EC2 unless noted)

### 1. SSH in
```bash
ssh -i ~/.ssh/your-key.pem ubuntu@<EC2-IP>
cd /home/ubuntu/vhc-platform
```

### 2. Pull latest code
```bash
git pull --rebase origin main
```
This brings down: redis_client refactor, pypdf migration, pipeline
pagination, BGE sidecar client.

### 3. Install local Redis + Python deps
```bash
sudo apt update
sudo apt install -y redis-server
sudo systemctl enable --now redis-server

# Verify Redis is up
redis-cli ping        # → PONG
```

```bash
cd /home/ubuntu/vhc-platform/backend
# Activate your venv first (adjust path if different)
source venv/bin/activate     # or: source /home/ubuntu/.venv/bin/activate

pip install 'redis==5.3.1' pypdf
pip uninstall -y PyPDF2       # optional cleanup
```

### 4. Update `/home/ubuntu/vhc-platform/backend/.env`
Add (or replace) at the top of the Redis section:

```ini
# --- Redis cache (local, Phase 54.17) ---
REDIS_URL=redis://localhost:6379/0
# Keep Upstash vars commented OR delete — they will be ignored when REDIS_URL is set.
# UPSTASH_REDIS_REST_URL=...
# UPSTASH_REDIS_REST_TOKEN=...
```

> The new code uses `REDIS_URL` first and only touches Upstash if
> `REDIS_URL` is empty. Leaving Upstash vars in place is safe but the
> quota-exhausted endpoint will never be called.

### 5. Tighten Redis (recommended, takes 1 min)
Default Ubuntu install only listens on `127.0.0.1` (good). Add a
maxmemory cap so it never starves Gunicorn/Mongo:

```bash
sudo tee -a /etc/redis/redis.conf > /dev/null <<'EOF'

# VHC tuning — added Phase 54.17
maxmemory 256mb
maxmemory-policy allkeys-lru
EOF

sudo systemctl restart redis-server
redis-cli ping        # → PONG
```

### 6. Restart Gunicorn
```bash
sudo systemctl restart gunicorn
sleep 4
```

### 7. Verify
```bash
# Local
curl -s http://localhost:8001/api/health | python3 -m json.tool
# Look for:
#   "redis": "ok",
#   "redis_backend": "local"
```

```bash
# Confirm pipeline pagination shipped
curl -s -X POST https://app.ventureshrd.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in","password":"VhcAdmin@2024"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])" > /tmp/tok

TOK=$(cat /tmp/tok)
curl -s -H "Authorization: Bearer $TOK" \
  "https://app.ventureshrd.com/api/admin/pipeline?limit=100" | python3 -c "import sys,json;d=json.load(sys.stdin);print('stages:', list(d.get('stage_counts',{}).keys())[:5]);print('first-stage rows:', len(next(iter(d.get('stages',{}).values()),[])))"
```

If `redis: ok` and `redis_backend: local`, cache is restored.

---

## Part 2 — BGE sidecar on RunPod

Follow `/app/memory/PHASE54_PART16_D1_BGE_SIDECAR_DEPLOY.md` start to
finish. TL;DR:

1. RunPod terminal → `mkdir -p /workspace/bge_sidecar && cd $_`
2. `curl` the two files from your GitHub `runpod-sidecar/` folder
3. `pip install fastapi==0.118.0 uvicorn==0.34.0 sentence-transformers==3.0.1`
4. `bash start_sidecar.sh` (background later via template)
5. Test from EC2:
   `curl https://t41o9p01whlrfe-8001.proxy.runpod.net/health`
6. Add to EC2 `/home/ubuntu/vhc-platform/backend/.env`:
   ```ini
   BGE_SIDECAR_URL=https://t41o9p01whlrfe-8001.proxy.runpod.net
   ```
7. `sudo systemctl restart gunicorn`

**Important — RunPod ID changed:** the proxy host is now
`t41o9p01whlrfe-8001.proxy.runpod.net` (not the older `31uikf6dsy0z8w`).

---

## Smoke test after everything is up

```bash
# Health
curl -s https://app.ventureshrd.com/api/health | python3 -m json.tool

# Captures still flowing?
curl -s -H "Authorization: Bearer $TOK" \
  https://app.ventureshrd.com/api/admin/daily-digest | python3 -m json.tool | head -40

# RAM should be ~1 GB lower than before sidecar (run on EC2):
free -h
```

---

## Rollback playbook

| Component  | Rollback                                                        |
|------------|-----------------------------------------------------------------|
| Local Redis | Remove `REDIS_URL` from `.env` → falls back to Upstash (when quota resets) or in-memory |
| pypdf      | `pip install PyPDF2==3.0.1` and revert matching_engine import   |
| Pagination | `git revert` the pagination commit; pipeline returns to full list |
| BGE sidecar| Delete `BGE_SIDECAR_URL` line in `.env`, restart gunicorn       |

Everything is feature-flagged via env vars — no schema migrations.
