# Phase 54.8 — RunPod auto start/stop scheduler
**Date:** 2026-05-08
**Type:** Cost optimization (~63% reduction in pod billing hours)
**Status:** ✅ Built — pending one-time install on EC2

## Goal
Cut RunPod always-on billing by stopping the Qwen14B pod outside
office hours. Pod runs Mon–Sat 8:50 AM – 6:30 PM IST (9.5h × 6 days =
57 h/week instead of 168 h/week always-on).

## Cost impact
| Scenario | Monthly cost |
|---|---|
| Original A40 24/7 | $329 |
| A5000 24/7 (Phase 54.x baseline) | $200 |
| **A5000 office-hours only (Phase 54.8)** | **~$73** |

Total saved vs original: **~$256/mo (~₹21,400/mo)**.

## Architecture
- **EC2 host crontab** (not gunicorn APScheduler) — runs even if backend is
  down, easy to debug via `/var/log/runpod-schedule.log`.
- Single Python script `backend/scripts/runpod_schedule.py` calls
  RunPod REST API (`POST /v1/pods/{id}/start` and `/stop`).
- Stdlib + `requests` (already in venv). Reads creds from `backend/.env`:
    - `RUNPOD_ACCOUNT_API_KEY`
    - `RUNPOD_POD_ID` (NEW key — must be added to `.env`)
- 3 bash helpers in `/usr/local/bin/`:
    - `runpod-start` (manual override)
    - `runpod-stop` (manual override)
    - `runpod-status` (read pod state)

## Schedule
| Action | IST | UTC | Cron |
|---|---|---|---|
| Start | 08:50 Mon–Sat | 03:20 | `20 3 * * 1-6` |
| Stop  | 18:30 Mon–Sat | 13:00 | `0 13 * * 1-6` |

10-min start buffer accounts for vLLM cold-load (~2-3 min — fast since
the 9 GB Qwen weights persist on the volume disk between stops). Sunday
the pod stays off all day. Failure handling: log to file, no retry —
team will notice via Emergent Haiku fallback if pod never wakes up.

## Files
- `backend/scripts/runpod_schedule.py` (new) — start/stop/status CLI
- `backend/scripts/install_runpod_cron.sh` (new) — idempotent installer

## Install (one time on EC2)

### 1. Add the pod ID to backend/.env (if not already there)
```bash
echo "RUNPOD_POD_ID=v5451fppg9smt1" >> /home/ubuntu/vhc-platform/backend/.env
```

### 2. Pull + install
```bash
cd /home/ubuntu/vhc-platform && \
  git pull --rebase origin main && \
  bash backend/scripts/install_runpod_cron.sh
```

### 3. Verify
```bash
crontab -l | grep runpod                          # 2 lines, start + stop
which runpod-start runpod-stop runpod-status      # 3 paths
runpod-status                                     # JSON pod info
```

## Daily ops
- **Watch log:** `tail -f /var/log/runpod-schedule.log`
- **Force start now:** `runpod-start`
- **Force stop now:** `runpod-stop`
- **Check pod state:** `runpod-status`

## Disable schedule (revert to always-on)
```bash
crontab -l | grep -v 'runpod_schedule.py' | crontab -
runpod-start    # ensure pod is up
```

## Future enhancements
- Holiday list (skip start on Diwali, Christmas, etc.) via JSON
- Slack webhook on start/stop failure (currently just logs)
- Pre-warm health-check after start: hit `/v1/models` until 200 to
  confirm vLLM is actually serving
- Auto-update RUNPOD_POD_ID in .env via API when pod is rebuilt
