# Phase 54.13 — t3a.large swap + RunPod API key fix (D-day)

**Date:** 2026-05-11 (Mon)
**Type:** Cost optimization + security/automation fix
**Status:** ✅ Both done & verified live

## Context
After yesterday's m7i-flex.large → t3.large downgrade, two things were
pending:
1. Tighten EC2 cost further with a no-risk AMD swap.
2. Diagnose why the RunPod scheduler installed in Phase 54.8 was never
   firing (user had to manually start/stop the pod every day).

## Part A — RunPod API key fix

### Symptom
```
2026-05-09 13:00:05  POST /pods/.../stop  → HTTP 403  ❌
2026-05-11 03:20:04  POST /pods/.../start → HTTP 403  ❌
2026-05-11 04:31:36  GET  /pods/...       → HTTP 200  ✅
```

### Root cause
The `RUNPOD_ACCOUNT_API_KEY` rotated last week was created with the
default **Read-only** scope. GETs worked, but every POST (start/stop)
was rejected by the RunPod API with 403 — cron fired on time, but
silently failed.

### Fix
1. User created a new RunPod key named `vhc-scheduler-rw` with the
   **Read & Write** permission scope.
2. Replaced `RUNPOD_ACCOUNT_API_KEY` in `/home/ubuntu/vhc-platform/backend/.env`.
3. Cleaned up the OLD crontab entries that:
   - Pointed at the now-dead A40 pod ID `7tuntnx4unbbym`
   - Embedded the **leaked** plaintext key `rpa_0WAYP2RLT3...` in the crontab
4. Manual `runpod-stop` then `runpod-start` both returned HTTP 200.
5. Old keys revoked in RunPod console.

### Cosmetic fix in workspace
`backend/scripts/runpod_schedule.py` was double-logging every line under
cron (FileHandler wrote once, cron's `>> log` redirected stdout wrote
again). Switched FileHandler to TTY-only — cron writes via shell
redirect, interactive runs still get the audit trail. Will take effect
on next `git pull` on EC2.

## Part B — t3.large → t3a.large swap (AMD drop-in)

### Why
- Same x86_64 ISA → no venv rebuild
- Same 2 vCPU / 8 GB RAM
- **~10% cheaper:** $0.0896 → $0.0806 /hr in ap-south-1
- AMD EPYC 7571 indistinguishable from Intel Xeon for Python/Gunicorn

### Procedure
1. AWS Console → Stop instance (~30s)
2. Actions → Change instance type → `t3a.large` → Apply
3. Start instance (~90s, EIP reattaches automatically)
4. Verify via SSH

### Verification (post-boot)
| Check | Result |
|---|---|
| Instance type | `t3a.large` |
| CPU vendor | `AuthenticAMD` (EPYC 7571) |
| Gunicorn | active |
| Nginx | active |
| `/api/health` | healthy (mongodb:ok, redis:ok) |
| Memory used | 1.3 GB / 7.7 GB (excellent headroom) |
| Swap | 0 B |
| EIP | 3.108.98.192 (unchanged) |

### Saving
- Compute: $0.0896 → $0.0806 /hr
- Monthly: ~₹545 (~$6.50)

## Decisions taken this session

### Skipped Compute Savings Plan (for now)
AWS recommended a $0.054/hr × 1-yr Compute SP (saves ~$13/mo at current
usage). Decision: **don't buy yet** because the next planned moves
(EventBridge nightly off + BGE sidecar + t3.medium downsize) will cut
usage by 60–70%. Buying SP now risks over-commit. Revisit in 3 weeks
once final state usage is stable.

### Roadmap re-confirmed
| Step | Saves/mo | When |
|---|---|---|
| ~~A~~ Compute SP | ~₹1,090 | DEFERRED (3 weeks out) |
| **B** t3a swap | ₹545 | ✅ DONE today |
| **C** EventBridge nightly off | ~₹1,090 | TODO (next week, 1h) |
| **D1** BGE → RunPod sidecar | ~₹2,690 | TODO (next week, 1–2d code) |

## Cumulative cost savings (this week alone)

| Action | Saves/mo |
|---|---|
| RunPod A40 → A5000 (prior) | ₹10,500 |
| RunPod auto-schedule **fixed** today | ₹11,500 |
| EC2 m7i-flex.large → t3.large | ₹880 |
| **EC2 t3.large → t3a.large** | **₹545** |
| **TOTAL** | **~₹23,425/mo (~$280)** |

## Open items / next session
1. **Tomorrow ~9:30 AM IST:** verify auto-start cron fires successfully
   (`tail /var/log/runpod-schedule.log` should show a fresh `→ HTTP 200`
   line around 03:20 UTC).
2. **Within 7 days:** drop Tier-2 unused MongoDB indexes once cluster
   hits 7-day uptime (run `backend/scripts/audit_indexes.py`).
3. **Within 30 days:** delete old RunPod A40 pod permanently.
4. **Next week:** start D1 (BGE sidecar) — full architecture in
   `PHASE54_PART14_BGE_SIDECAR_PLAN.md`.
