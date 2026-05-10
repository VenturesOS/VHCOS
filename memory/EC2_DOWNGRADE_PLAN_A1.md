# 🟢 EC2 Downgrade — Plan A1 Walkthrough

**Goal:** Downgrade `m7i-flex.large` → `t3.large` (still x86_64, 8 GB RAM, 2 vCPU).
**Why:** 60-day telemetry shows avg CPU = 2 % and peak < 25 %. CPU is vastly oversized; RAM stays the same so no venv rebuild.
**Risk:** Low — same architecture, same AMI, same disk. Only the host hardware tier changes.
**Expected savings:** ~₹2,000 / month (~$24).
**Downtime:** ~3–5 minutes (one stop + one start).

---

## ⏱ Pre-flight (do NOT skip)

Run these on the EC2 box **before** stopping the instance and save the output to a notepad:

```bash
# Confirm architecture is x86_64 (must NOT be aarch64)
uname -m            # expected: x86_64

# Confirm services are healthy right now (so we have a known-good baseline)
sudo systemctl is-active gunicorn      # expected: active
sudo systemctl is-active mongod        # expected: active (if running locally)
sudo systemctl is-active nginx         # expected: active
curl -s http://localhost:8001/api/health | head -5

# Note the current public IP (will change ONLY if you don't use Elastic IP)
curl -s http://checkip.amazonaws.com
```

> 📝 If `curl http://checkip.amazonaws.com` shows a public IP that is NOT your Elastic IP, please attach an Elastic IP first (or be ready to update DNS after restart).

---

## 🪜 Step-by-Step AWS Console Walkthrough

### Step 1 — Create a safety snapshot (5 min, optional but recommended)
1. AWS Console → **EC2** → **Volumes** (left sidebar).
2. Find the root volume attached to your instance (Volume ID will match the one in your instance's "Storage" tab).
3. Right-click → **Create snapshot** → Description: `pre-t3-large-downgrade-<today>` → **Create**.
4. Wait until snapshot status = `completed` (Snapshots tab).

> If anything goes wrong in Step 4, you can restore from this snapshot.

### Step 2 — Stop the instance
1. EC2 → **Instances** → select your instance.
2. **Instance state** → **Stop instance** → confirm.
3. Wait until **Instance state** = `Stopped` (~30–60 s).

> ⚠ "Stop", NOT "Terminate". Terminate deletes the instance permanently.

### Step 3 — Change instance type
1. With the (now stopped) instance still selected:
   **Actions** → **Instance settings** → **Change instance type**.
2. In the dropdown choose: **`t3.large`**
   - Family: t3
   - vCPU: 2, RAM: 8 GB
   - Architecture: x86_64 (matches current)
3. Click **Apply**.

### Step 4 — Start the instance
1. **Instance state** → **Start instance**.
2. Wait until **Instance state** = `Running` and **Status checks** = `2/2 checks passed` (~60–120 s).
3. Note the **Public IPv4** — if you're NOT using an Elastic IP, this will have changed; update your DNS / `~/.ssh/config`.

---

## ✅ Post-reboot Health Verification (do this immediately after Step 4)

SSH back in:

```bash
ssh ubuntu@<your-ec2-ip-or-domain>
```

Run the verification block (copy-paste as one command):

```bash
echo "=== Architecture (must still be x86_64) ===" && uname -m && \
echo "=== CPU / RAM ===" && nproc && free -h && \
echo "=== Gunicorn ===" && sudo systemctl is-active gunicorn && \
echo "=== Nginx ===" && sudo systemctl is-active nginx && \
echo "=== Mongod (skip if Atlas) ===" && (sudo systemctl is-active mongod || echo "not local") && \
echo "=== Backend health ===" && curl -s http://localhost:8001/api/health | head -5 && \
echo "=== Public health (through nginx + cloudflare) ===" && curl -sI https://ventureshrd.com/api/health | head -3 && \
echo "=== Memory of gunicorn workers ===" && ps -eo pid,rss,cmd --sort=-rss | grep gunicorn | grep -v grep | head -5 && \
echo "=== RunPod cron persistence ===" && (crontab -l | grep runpod_schedule || echo "MISSING - reinstall cron") && \
echo "=== Done ==="
```

### ✔ Acceptance criteria
| Check | Expected |
|---|---|
| `uname -m` | `x86_64` |
| `nproc` | `2` |
| `free -h` total | `~7.5–7.7 Gi` (8 GB minus kernel) |
| `gunicorn` | `active` |
| `nginx` | `active` |
| `/api/health` | `200 OK` JSON |
| `gunicorn` worker RSS | < 1.5 GB |
| `crontab -l` | shows `runpod_schedule` lines |

---

## 🚨 Rollback (only if something fails)

```text
EC2 Console → select instance → Stop → Actions → Change instance type → m7i-flex.large → Start
```

Cost of rollback: ₹0 (you already paid for the m7i-flex.large monthly).

If the disk itself is corrupted (extremely unlikely, this isn't a disk operation):
```text
EC2 → Snapshots → select pre-t3-large-downgrade-<date> → Create volume from snapshot
```

---

## 📊 What to monitor for 24 h after switch

Run once / hour for the first 4 hours:

```bash
# CPU % — should still be < 30 % even at peak
top -b -n 1 | head -5

# Memory — should stay < 6.5 GB used
free -h

# Gunicorn worker memory — should be < 1.5 GB each
ps -eo pid,rss,cmd --sort=-rss | grep gunicorn | grep -v grep | head -3

# 5xx errors in nginx (should be ~0)
sudo tail -200 /var/log/nginx/error.log | grep -i error | wc -l
```

If `free -h` ever shows `available < 1 GB` for >5 min → roll back immediately (memory pressure).

---

## 🎯 Sign-off

When all of the above passes for **24 hours straight**:
- ✅ Plan A1 complete.
- ✅ Old `m7i-flex.large` reservation is no longer billed (AWS bills per-hour on the *current* type).
- 🔜 Next: delete old RunPod A40 pod (Issue #2) and run the 7-day MongoDB index audit (Issue #3).
