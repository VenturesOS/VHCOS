# Backend Resilience Trio — Phase 56.6 (Jun 2026)

Three small, independent changes that make the platform survive Mongo
Atlas blips, RAM bloat, and stuck jobs without manual intervention.

Apply these on EC2 in the order below. Each is independent — you can
stop after any step and the platform is still better than before.

---

## 1. Mongo Atlas Retry Config (15 min, zero downtime)

**Why:** During the Atlas failover at 05:56-06:00 UTC on 2026-06-02, workers
hung 60-120s waiting for primary, then got `WORKER TIMEOUT`-killed by
gunicorn. With proper retry config, pymongo retries the failed op against
the new primary as soon as election completes — usually within 10-15s,
well below gunicorn's 120s timeout.

**Action on EC2:**

```bash
# 1. Backup .env
cp /home/ubuntu/vhc-platform/backend/.env /home/ubuntu/vhc-platform/backend/.env.bak.$(date +%s)

# 2. Inspect the current MONGO_URL (look for these query params)
grep '^MONGO_URL=' /home/ubuntu/vhc-platform/backend/.env
```

**Expected query string after the change:**

```
mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority&retryReads=true&serverSelectionTimeoutMS=10000&socketTimeoutMS=30000&connectTimeoutMS=10000&heartbeatFrequencyMS=10000
```

Key params:
- `retryWrites=true` — retry idempotent writes once on transient errors (defaults TRUE since pymongo 4.0, but explicit is safer)
- `retryReads=true` — same for reads (default TRUE)
- `serverSelectionTimeoutMS=10000` — **lowered from default 30s to 10s.** When primary is down, fail FAST so requests don't pile up.
- `socketTimeoutMS=30000` — cap individual op at 30s
- `heartbeatFrequencyMS=10000` — re-probe replica set every 10s (default) so new primary is detected quickly

**Edit the URL safely with sed:**

```bash
# Adjust the existing MONGO_URL query string (one-shot, idempotent)
sudo -u ubuntu python3 - <<'PYEOF'
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

env_path = Path("/home/ubuntu/vhc-platform/backend/.env")
lines = env_path.read_text().splitlines()
out = []
for ln in lines:
    if ln.startswith("MONGO_URL="):
        url = ln.split("=", 1)[1].strip().strip('"').strip("'")
        # pymongo's mongodb+srv:// → parse the bit after the '?'
        if "?" in url:
            base, qs = url.split("?", 1)
        else:
            base, qs = url, ""
        params = dict(parse_qsl(qs))
        params.update({
            "retryWrites": "true",
            "w": "majority",
            "retryReads": "true",
            "serverSelectionTimeoutMS": "10000",
            "socketTimeoutMS": "30000",
            "connectTimeoutMS": "10000",
            "heartbeatFrequencyMS": "10000",
        })
        new_url = f"{base}?{urlencode(params)}"
        out.append(f"MONGO_URL={new_url}")
        print(f"Updated MONGO_URL with resilience params ({len(params)} total)")
    else:
        out.append(ln)
env_path.write_text("\n".join(out) + "\n")
PYEOF

# Verify
grep '^MONGO_URL=' /home/ubuntu/vhc-platform/backend/.env | grep -oE 'retryWrites=[a-z]+|serverSelectionTimeoutMS=[0-9]+'

# Apply (no rebuild needed, just restart workers)
sudo systemctl restart vhc-backend

# Confirm clean boot
sleep 6 && sudo journalctl -u vhc-backend --since "30 sec ago" | tail -10
```

---

## 2. Stuck-Job Sweeper Cron (5 min, zero downtime)

**Why:** Even with retry config, edge cases still leave background jobs
stranded in `status: "processing"` (OOM kill, hard worker timeout, etc.).
This cron sweeps stale rows automatically every 10 minutes.

Code already in repo at `backend/scripts/sweep_stuck_jobs.py` (deploys
with the next git pull). Just needs a cron entry.

**Action on EC2:**

```bash
# 1. Confirm the script is there (after the next deploy)
ls -la /home/ubuntu/vhc-platform/backend/scripts/sweep_stuck_jobs.py

# 2. Test-run once (idempotent — safe even if nothing's stuck)
cd /home/ubuntu/vhc-platform/backend && \
  venv/bin/python scripts/sweep_stuck_jobs.py

# Expected output if nothing stuck: silence (script logs only on hits)
# Expected output if some stuck: "[<ts>] match_jobs: swept N stuck → failed"

# 3. Make the log file
sudo touch /var/log/sweep_stuck.log
sudo chown ubuntu:ubuntu /var/log/sweep_stuck.log

# 4. Add to crontab
crontab -e
```

Add this line (keep all existing crons intact):

```
*/10 * * * * cd /home/ubuntu/vhc-platform/backend && venv/bin/python scripts/sweep_stuck_jobs.py >> /var/log/sweep_stuck.log 2>&1
```

Save & exit. Verify:

```bash
crontab -l | grep sweep_stuck
# Then wait 10 min and check the log
sudo tail -n 20 /var/log/sweep_stuck.log
```

---

## 3. Scheduled HUP Every 6 Hours (5 min, zero downtime)

**Why:** Recurring issue all session — workers grow to 2-3 GB RSS over
hours and starve the 7.6GB box. Today we did manual HUPs twice. A
preemptive HUP every 6h keeps RAM headroom permanently healthy without
intervention. Gunicorn's HUP gracefully cycles workers — in-flight
requests finish, new requests go to fresh lean workers.

**Action on EC2:**

```bash
# 1. Find the gunicorn master PID dynamically each run — DO NOT
#    hard-code it (it changes on every full restart).
crontab -e
```

Add this line (preserve all existing crons):

```
0 */6 * * * /usr/bin/pkill -HUP -f "gunicorn server:app" || true
```

Save & exit. Verify:

```bash
crontab -l | grep gunicorn

# Optional: test it manually right now (gracefully recycles workers)
sudo /usr/bin/pkill -HUP -f "gunicorn server:app"
sleep 10
ps -eo pid,rss,etime,cmd --sort=-rss | grep gunicorn | grep -v grep | head -5
free -h
```

You should see new short-`etime` workers in the list and RAM availability
jump.

---

## Final state after all 3 changes

| Failure mode | Before | After |
|---|---|---|
| Atlas primary failover | 60-120s hang → workers killed | Auto-retry in ~10s, transparent |
| Worker RAM bloat | Manual HUP needed daily | Auto-recycled 4×/day |
| Stuck `processing` rows | Manual cleanup script needed | Auto-failed within 10min |

No code deploys needed for steps 1 & 3 — pure config. Step 2 ships with
the git push (the Python script). Total elapsed time: ~30 min including
verification.
