# Gunicorn `--max-requests` Restore Runbook

**Status:** Ready to deploy (P3, low-urgency)
**Date:** 2026-06-08
**Why:** Memory-leak root cause was fixed on 2026-06-03 (clustering moved to subprocess isolation, PRD item 34). Workers now stay flat at ~900 MB baseline through clustering runs. The conservative `--max-requests 500` cap that was set on 2026-02-29 (PRD item 21) was a safety net while the leak was unresolved — it's now over-defensive and just churns CPU recycling workers unnecessarily.

---

## Current AWS prod state

```
/etc/systemd/system/vhc-backend.service.d/override.conf

[Service]
ExecStart=
ExecStart=/usr/bin/gunicorn server:app \
  -w 3 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8001 \
  --max-requests 500 \
  --max-requests-jitter 30 \
  ... (other flags)
```

## Target state

Raise to `--max-requests 1500 --max-requests-jitter 100`.

Rationale:
- jemalloc handles arena defrag; per-worker RSS plateaus around 1.2 GB without recycling
- 1500 reqs ≈ 4–6 hours of normal traffic between recycles (vs ~30–60 min today)
- Jitter raised to 100 to stagger the recycle storm across 3 workers

## Apply (on AWS EC2 host)

```bash
sudo systemctl edit vhc-backend
# Inside the editor, change:
#   --max-requests 500
#   --max-requests-jitter 30
# To:
#   --max-requests 1500
#   --max-requests-jitter 100
# Save + exit.

sudo systemctl daemon-reload
sudo systemctl restart vhc-backend
sudo systemctl status vhc-backend --no-pager | head -20
```

## Verify (post-restart soak test)

```bash
# 1. Confirm new flags are active
ps -ef | grep gunicorn | grep -v grep

# 2. Watch worker memory over 2-3 hours under normal traffic
watch -n 60 'ps -eo pid,rss,cmd | grep gunicorn | grep -v grep | awk "{rss=\$2/1024; printf \"%s %.0f MB %s\\n\", \$1, rss, substr(\$0, index(\$0,\$3))}"'

# 3. Confirm /api/clustering/run still spawns isolated subprocess
# (sanity check that the resilience trio is still in place)
curl -X POST $API_URL/api/clustering/run -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{}'
# Expected log line in /var/log/vhc-backend/app.log:
#   [Clustering] Spawning isolated subprocess: python -m scripts.cluster_candidates ...
```

## Rollback (if RSS climbs >3 GB or worker timeouts return)

```bash
sudo systemctl edit vhc-backend
# Revert max-requests to 500, jitter to 30
sudo systemctl daemon-reload
sudo systemctl restart vhc-backend
```

Then file a follow-up: investigate which endpoint regressed (likely a new
fire-and-forget background task — same shape as the old `_fire_and_forget`
that caused the 2026-02-27 leak in `routes/extension.py`).

---

## Why not push higher (e.g. 5000)?

- Cumulative residual leak (~5–10 MB per 1000 requests) from misc Python
  caches still exists. Recycling once per ~6 hours keeps that bounded.
- `--max-requests 0` (disable recycle) is what production-grade gunicorn
  + uvicorn shops do **only after** they've eliminated all C-extension
  leaks at the wheel level (numpy, BSON encoding, etc.). We're not there.
- 1500 is the sweet spot per gunicorn ops guides (recycles every shift,
  jitter prevents stampedes).
