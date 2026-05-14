# Phase 55 — BGE Embedding Backfill + Auto-Persistence Runbook

**Owner:** ATS Ops
**Last updated:** 2026-02-14
**Status:** Ready to deploy

## Why
Today only **1.4%** of the 1.23 L candidate bank has BGE embeddings, so semantic / AI search misses ~98% of the talent pool. Phase 55 Batch C added a keyword fallback that masks the gap in the UI, but pure vector search remains the better path. This runbook:

1. Embeds the **entire** bank in one ~5–6 hr GPU job on the RunPod BGE sidecar.
2. Installs a nightly systemd timer that keeps the index up-to-date going forward (`<5 min` per night).
3. Installs a watchdog that automatically (re)starts the BGE sidecar on the RunPod pod after every EC2 boot — eliminates the daily manual paste-1-liner chore.

After deployment, semantic search becomes the primary path; the keyword fallback only fires when the embedding genuinely fails (e.g., empty / non-English text).

---

## 0. Pre-flight (verify on EC2)

```bash
# RunPod BGE sidecar URL must already be in backend/.env
grep BGE_SIDECAR_URL /home/ubuntu/vhc-platform/backend/.env

# Pod must be awake. Probe it quickly:
SIDECAR=$(grep BGE_SIDECAR_URL /home/ubuntu/vhc-platform/backend/.env | cut -d= -f2)
curl -fsS "$SIDECAR/health" | jq
# Expected: {"ready": true, "device": "cuda", ...}
```

If sidecar isn't healthy, paste the **manual 1-liner** into the RunPod web terminal and re-probe. (The watchdog installed in §3 below will replace this manual step.)

---

## 1. One-shot full backfill — kick off NOW

Copy `run_bge_backfill.sh` from this repo onto EC2, then start it in a detached `tmux` session.

```bash
# (a) Copy the script (run from your laptop / dev box)
scp /app/backend/scripts/run_bge_backfill.sh \
    ubuntu@<EC2-IP>:/home/ubuntu/vhc-platform/backend/scripts/

# (b) SSH to EC2
ssh ubuntu@<EC2-IP>

# (c) Make it executable
chmod +x /home/ubuntu/vhc-platform/backend/scripts/run_bge_backfill.sh
sudo mkdir -p /var/log/vhc && sudo chown ubuntu:ubuntu /var/log/vhc

# (d) Launch in tmux (survives SSH disconnect)
tmux new -s bge-backfill -d \
  '/home/ubuntu/vhc-platform/backend/scripts/run_bge_backfill.sh --full'

# (e) Watch live progress (Ctrl-B then D to detach without killing)
tmux attach -t bge-backfill

# Or simply tail the log:
tail -f /var/log/vhc/bge_backfill_full.latest.log
```

### Monitoring checkpoints
- Every 50 candidates the script logs `Progress: X/Y @ N.N/s, ETA Nm`.
- Expected rate at concurrency 16 + `--fast-summary` on RTX A5000: **6–9 candidates / sec**.
- Total runtime for 1.21 L (1.23 L − the 1,713 already embedded): **~4–6 hrs**.
- Final line: `Backfill DONE: <embedded> embedded, <skipped> skipped, <failed> failed in <s>s`.

### Sanity check while it runs
In another SSH session:

```bash
# Count grows from 1,713 toward 1,23,143
mongosh "$MONGO_URL" --eval 'db.getSiblingDB("vhc_talent_os").candidate_embeddings.countDocuments({})'
```

---

## 2. Install the nightly incremental timer (idempotent top-up)

```bash
# (a) Copy the systemd unit files onto EC2
scp /app/backend/scripts/systemd/vhc-bge-backfill.{service,timer} \
    ubuntu@<EC2-IP>:/tmp/

# (b) SSH + install
ssh ubuntu@<EC2-IP> <<'EOSH'
sudo mv /tmp/vhc-bge-backfill.service /etc/systemd/system/
sudo mv /tmp/vhc-bge-backfill.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vhc-bge-backfill.timer
sudo systemctl list-timers | grep bge
EOSH
```

Expected output of `list-timers`:

```
NEXT                         LEFT     LAST PASSED   UNIT                       ACTIVATES
Sat 2026-02-15 16:30:00 UTC  21h ago  n/a  n/a      vhc-bge-backfill.timer     vhc-bge-backfill.service
```

The timer fires Mon–Sat at **16:30 UTC = 22:00 IST** (well before the EventBridge stop at 19:00 UTC / 00:30 IST). Each run takes <5 min in steady state because `--only-missing` is implicit.

### Manual fire-now (e.g. after a bulk import)

```bash
sudo systemctl start vhc-bge-backfill.service
sudo journalctl -u vhc-bge-backfill.service -f
```

---

## 3. Install the BGE sidecar watchdog (eliminates daily manual chore)

### 3.1 One-time SSH key setup (RunPod → EC2)

1. In the **RunPod dashboard** → click your pod → `Connect` → `SSH over exposed TCP`. Copy the connection string. It looks like:

   ```
   ssh root@123.45.67.89 -p 12345 -i ~/.ssh/id_ed25519
   ```

2. On **EC2** generate a dedicated key and add it to RunPod:

   ```bash
   ssh-keygen -t ed25519 -f /home/ubuntu/.ssh/runpod_id_ed25519 -N ''
   cat /home/ubuntu/.ssh/runpod_id_ed25519.pub
   ```

   Paste the public key into RunPod → `Settings → SSH Public Keys`. (Or, if your pod has its own `authorized_keys`, append it there.)

3. Add the host alias on EC2:

   ```bash
   cat >> /home/ubuntu/.ssh/config <<'EOCFG'

   Host runpod-bge
       HostName 123.45.67.89          # ← replace with your pod IP from step 1
       User root
       Port 12345                     # ← replace with your pod port from step 1
       IdentityFile /home/ubuntu/.ssh/runpod_id_ed25519
       StrictHostKeyChecking accept-new
       ServerAliveInterval 30
   EOCFG
   chmod 600 /home/ubuntu/.ssh/config /home/ubuntu/.ssh/runpod_id_ed25519
   ```

4. Verify:

   ```bash
   ssh runpod-bge 'ls /workspace/embed_service.py && nvidia-smi | head -5'
   ```

### 3.2 Install the watchdog units

```bash
# Copy
scp /app/backend/scripts/sidecar_keeper.sh \
    ubuntu@<EC2-IP>:/home/ubuntu/vhc-platform/backend/scripts/
scp /app/backend/scripts/systemd/vhc-bge-sidecar-keeper.{service,timer} \
    ubuntu@<EC2-IP>:/tmp/

# Install
ssh ubuntu@<EC2-IP> <<'EOSH'
chmod +x /home/ubuntu/vhc-platform/backend/scripts/sidecar_keeper.sh
sudo mv /tmp/vhc-bge-sidecar-keeper.service /etc/systemd/system/
sudo mv /tmp/vhc-bge-sidecar-keeper.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vhc-bge-sidecar-keeper.timer
sudo systemctl list-timers | grep sidecar-keeper
EOSH
```

The watchdog:
- Fires **2 min after every EC2 boot** (catches the 06:30 IST cold-start).
- Then every **30 min** while the box is awake — re-checks health, re-starts only if the sidecar died.
- Is **idempotent** — does nothing when the sidecar is already healthy.

### Verify the watchdog

```bash
# Force a run now
sudo systemctl start vhc-bge-sidecar-keeper.service
tail -f /var/log/vhc/bge_sidecar_keeper.log
```

Expected on the happy path:
```
=== 2026-02-14T19:00:00+05:30 keeper run ===
OK: sidecar already healthy — {"ready": true, "device": "cuda", "model": "BAAI/bge-small-en-v1.5"}
```

After this is enabled, the daily manual paste-1-liner step is **no longer required**.

---

## 4. Post-deploy verification

```bash
# (1) Embedding coverage should approach 100%
mongosh "$MONGO_URL" --eval '
  const db = db.getSiblingDB("vhc_talent_os");
  print("total candidates:",   db.candidate_bank.countDocuments({}));
  print("with embedding:",     db.candidate_embeddings.countDocuments({}));
'

# (2) Hit the AI search endpoint — `relaxed:false` and rich semantic hits
curl -s -X POST "$BACKEND_URL/api/talent-graph/search" \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"query":"product manager B2B SaaS Bangalore","limit":10,"min_score":0.5}' \
  | jq '.matches | map({n: .candidate_name, t: .match_type, s: .score})'
# Expected: match_type:"vector" for most rows, very few "keyword" fallbacks.

# (3) Check timers
sudo systemctl list-timers --all | grep vhc
```

---

## 5. Rollback / disable

```bash
# Disable the timers (keep the script for ad-hoc runs)
sudo systemctl disable --now vhc-bge-backfill.timer
sudo systemctl disable --now vhc-bge-sidecar-keeper.timer

# Or remove entirely
sudo rm /etc/systemd/system/vhc-bge-{backfill,sidecar-keeper}.{service,timer}
sudo systemctl daemon-reload
```

---

## 6. Files added

| Path on EC2 | Purpose |
|---|---|
| `/home/ubuntu/vhc-platform/backend/scripts/run_bge_backfill.sh`         | Wrapper invoked by service unit |
| `/home/ubuntu/vhc-platform/backend/scripts/sidecar_keeper.sh`           | SSH-based sidecar (re)starter |
| `/etc/systemd/system/vhc-bge-backfill.{service,timer}`                  | Nightly incremental top-up |
| `/etc/systemd/system/vhc-bge-sidecar-keeper.{service,timer}`            | Boot + 30-min watchdog |
| `/var/log/vhc/bge_backfill_*.log`                                       | Backfill output |
| `/var/log/vhc/bge_sidecar_keeper.log`                                   | Watchdog output |

In-repo source-of-truth: `/app/backend/scripts/{run_bge_backfill.sh,sidecar_keeper.sh,systemd/*}`.
