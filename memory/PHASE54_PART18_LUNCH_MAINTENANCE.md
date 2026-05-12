# Phase 54.18 — Tomorrow's Lunch Maintenance (Feb 13, 2026)

**Goal:** Lock in final cost savings + auto-persist BGE sidecar across
pod restarts. ~15 min wall-clock, one combined maintenance window.

## Pre-flight (run before starting — RunPod web terminal)

```
tail -30 /workspace/bge_sidecar/bge.log
curl -s http://localhost:8001/health
```

Expected: `{"ok":true,"model_loaded":true,...}` and no crashes in log.
If crashes shown, stop and investigate before proceeding.

---

## Phase 1 — Free EC2 RAM (remove local embeddings fallback)

On EC2 (`ssh ubuntu@<EC2-IP>`):

```
source /home/ubuntu/vhc-platform/backend/venv/bin/activate
pip uninstall -y sentence-transformers
sudo systemctl restart gunicorn
sleep 8
curl -s http://localhost:8001/api/health | python3 -m json.tool
free -h
```

Verify embeddings still work (sidecar is the only path now):

```
python -c "
import sys; sys.path.insert(0,'/home/ubuntu/vhc-platform/backend')
from services.embed_client import embed_remote
v = embed_remote(['test sales mumbai'])
print('OK' if v and v[0] and len(v[0])==384 else 'FAIL')
"
```

Expected: `OK`. RAM `used` should drop ~800 MB further.

---

## Phase 2 — Edit pod start command (one-time, persists forever)

RunPod console:
1. Pod `t41o9p01whlrfe` → click **⋮ (kebab) menu** → **Edit Pod**
2. Find "Container start command" — current value:
   ```
   --model Qwen/Qwen2.5-14B-Instruct-AWQ --port 8000 --max-model-len 32768 --disable-log-requests
   ```
3. Replace ENTIRELY with:
   ```
   bash -c "nohup uvicorn embed_service:app --host 0.0.0.0 --port 8001 --app-dir /workspace/bge_sidecar > /workspace/bge_sidecar/bge.log 2>&1 & exec python3 -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-14B-Instruct-AWQ --port 8000 --max-model-len 32768 --disable-log-requests"
   ```
4. Save (pod auto-resets, ~90 s)

Verify both services back up (from EC2):

```
curl -s https://t41o9p01whlrfe-8000.proxy.runpod.net/v1/models | head -c 200
curl -s https://t41o9p01whlrfe-8001.proxy.runpod.net/health
```

Both must return valid JSON.

---

## Phase 3 — EC2 downsize → t3.medium

AWS Console:
1. EC2 → select instance → **Stop**
2. Once stopped → Actions → Instance settings → Change instance type → **t3.medium**
3. **Start**
4. Wait ~60 s, then on EC2:

```
curl -s http://localhost:8001/api/health | python3 -m json.tool
free -h
```

Expected: `redis: ok`, `redis_backend: local`, ~2.5 GB free of 4 GB total.

Final smoke test:
- Login to admin dashboard (admin@vhc.in)
- Open pipeline → loads without errors
- Trigger a candidate capture from Chrome extension → succeeds
- Daily Digest widget renders

---

## Rollback playbook (won't be needed, but documented)

| Failure                  | Rollback                                         |
|--------------------------|--------------------------------------------------|
| Sidecar fails to boot    | Edit Pod → revert start cmd to vLLM-only line   |
| Embeddings broken on EC2 | `pip install sentence-transformers==5.4.1` + restart gunicorn |
| EC2 OOM on t3.medium     | AWS Console → Stop → instance type → t3a.large → Start |

---

## Cost picture after Phase 54.18

| Component        | Now (Feb 12) | Tomorrow (Feb 13) |
|------------------|-------------:|-------------------:|
| EC2              | ~₹4,600 (t3a.large) | ~₹2,500 (t3.medium) |
| RunPod GPU       | ~₹6,300 (A5000 9h40m/day) | unchanged |
| Upstash Redis    | ₹0 | ₹0 |
| **TOTAL**        | **~₹10,900** | **~₹8,800** |
| **Savings vs Jan ₹31k** | -65% (~₹20k/mo) | **-72% (~₹22k/mo)** |

---

## Files referenced

- `/app/backend/scripts/runpod_bge_keeper.py` — kept in repo as backup
  (cron-from-EC2 path) but NOT installed. Useful if Path 2 ever needs
  to be rolled back.
- `/app/runpod-sidecar/embed_service.py` — master copy of sidecar code.
- `/app/memory/PHASE54_PART17_LOCAL_REDIS_DEPLOY.md` — yesterday's deploy.
