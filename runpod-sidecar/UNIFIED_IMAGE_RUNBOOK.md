# VHC Unified RunPod Image — Build & Deploy Runbook

**File set:** `Dockerfile.unified`, `supervisord.conf`, `entrypoint.sh`, `embed_service.py`
**Image target:** `ghcr.io/venturesos/vhc-runpod:unified`
**What changes for the user:** zero daily-manual sidecar startup chore. Both vLLM
and the BGE sidecar come up automatically whenever the RunPod pod boots.

---

## 1. Build the image

```bash
cd runpod-sidecar
docker build -f Dockerfile.unified -t ghcr.io/venturesos/vhc-runpod:unified .

# (Optional) push to GHCR — requires a GH PAT with `write:packages`
docker login ghcr.io -u <github-user>
docker push ghcr.io/venturesos/vhc-runpod:unified
```

> The image is ~12 GB (vLLM CUDA base 6.5 GB + Qwen weights are pulled at
> runtime, NOT baked in, to keep the image portable across pod GPU sizes).
> Build takes 8–10 min on a workstation; only the BGE pre-bake (~2 GB) adds
> measurable time over the stock vLLM image.

---

## 2. Deploy on RunPod

1. **Stop** the current pod (`31uikf6dsy0z8w`) so it releases the GPU.
2. **Edit Pod** → **Container Image** = `ghcr.io/venturesos/vhc-runpod:unified`
3. **Container Disk** = 50 GB+ (room for Qwen weights cache).
4. **Volume Mount** (recommended) — `/root/.cache/huggingface` to a persistent
   volume so Qwen weights survive pod restarts.
5. **Expose HTTP Ports** = `8000, 8001`
6. **Environment Variables** (override defaults if needed):
   - `VHC_VLLM_MODEL` (default `Qwen/Qwen2.5-14B-Instruct-AWQ`)
   - `VHC_VLLM_MAX_MODEL_LEN` (default `32768`)
7. **Save** → pod boots. Expect ~60–90 s before both `/v1/models` (8000) and
   `/health` (8001) return 200.

---

## 3. Verify (from EC2 or local)

```bash
POD_ID=31uikf6dsy0z8w   # or whatever the new pod id is
curl -sS https://${POD_ID}-8000.proxy.runpod.net/v1/models   | head -c 300
echo
curl -sS https://${POD_ID}-8001.proxy.runpod.net/health     | python3 -m json.tool
```

Both must return 200 with `model_loaded:true`.

---

## 4. Update `backend/.env` on EC2

If the pod id changed, update **both** URLs in a single sed pass:

```bash
NEW=<new-pod-id>
cp ~/vhc-platform/backend/.env ~/vhc-platform/backend/.env.bak.$(date +%s)
sed -i -E "s|//[a-z0-9]+-(8000|8001)\.proxy\.runpod\.net|//${NEW}-\1.proxy.runpod.net|g" \
    ~/vhc-platform/backend/.env
sed -i -E "s|^RUNPOD_POD_ID=.*|RUNPOD_POD_ID=${NEW}|" ~/vhc-platform/backend/.env
sudo systemctl restart vhc-backend
```

---

## 5. Logs (on the pod)

```bash
tail -f /var/log/vllm.out.log         # Qwen
tail -f /var/log/sidecar.out.log      # BGE
tail -f /var/log/supervisord.log      # supervisor
supervisorctl -c /etc/supervisor/conf.d/vhc.conf status
```

---

## 6. Rollback

If anything goes wrong, switch the pod image back to the old vLLM image
and run the legacy heredoc / dpaste recipe to start the sidecar manually.
The legacy `Dockerfile` (BGE-only) stays in this repo for that purpose.
