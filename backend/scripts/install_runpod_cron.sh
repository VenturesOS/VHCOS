#!/bin/bash
# Phase 54.8 — Install RunPod auto start/stop schedule on EC2.
# Idempotent: re-running this safely refreshes cron + helpers.
#
# Usage (run once on EC2):
#     bash /home/ubuntu/vhc-platform/backend/scripts/install_runpod_cron.sh
#
# After install:
#     runpod-status        # show current pod state
#     runpod-start         # force-start now (bypass schedule)
#     runpod-stop          # force-stop now
#     tail -f /var/log/runpod-schedule.log
set -euo pipefail

REPO_ROOT="/home/ubuntu/vhc-platform"
VENV_PY="${REPO_ROOT}/backend/venv/bin/python3"
SCRIPT="${REPO_ROOT}/backend/scripts/runpod_schedule.py"
LOG_FILE="/var/log/runpod-schedule.log"

# ── Sanity checks ─────────────────────────────────────────────────────
if [[ ! -f "$SCRIPT" ]]; then
  echo "ERROR: $SCRIPT not found. Did you git pull?" >&2
  exit 1
fi
if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: venv python missing at $VENV_PY" >&2
  exit 1
fi
if ! grep -q '^RUNPOD_ACCOUNT_API_KEY=' "$REPO_ROOT/backend/.env"; then
  echo "ERROR: RUNPOD_ACCOUNT_API_KEY missing from backend/.env" >&2
  exit 1
fi
if ! grep -q '^RUNPOD_POD_ID=' "$REPO_ROOT/backend/.env"; then
  echo "ERROR: RUNPOD_POD_ID missing from backend/.env. Add the line:" >&2
  echo "       RUNPOD_POD_ID=v5451fppg9smt1" >&2
  exit 1
fi

# ── Make script executable ────────────────────────────────────────────
chmod +x "$SCRIPT"

# ── Log file (root-owned but world-writable so cron-as-ubuntu works) ──
sudo touch "$LOG_FILE"
sudo chown ubuntu:ubuntu "$LOG_FILE"
sudo chmod 644 "$LOG_FILE"

# ── Bash helpers in /usr/local/bin (always on PATH) ───────────────────
sudo tee /usr/local/bin/runpod-start  >/dev/null <<EOF
#!/bin/bash
exec ${VENV_PY} ${SCRIPT} start "\$@"
EOF
sudo tee /usr/local/bin/runpod-stop   >/dev/null <<EOF
#!/bin/bash
exec ${VENV_PY} ${SCRIPT} stop "\$@"
EOF
sudo tee /usr/local/bin/runpod-status >/dev/null <<EOF
#!/bin/bash
exec ${VENV_PY} ${SCRIPT} status "\$@"
EOF
sudo chmod +x /usr/local/bin/runpod-start /usr/local/bin/runpod-stop /usr/local/bin/runpod-status

# ── Cron entries (Mon–Sat, IST → UTC offset −5:30) ────────────────────
#   08:50 IST = 03:20 UTC  →  start
#   18:30 IST = 13:00 UTC  →  stop
TMP_CRON="$(mktemp)"
crontab -l 2>/dev/null | grep -v 'runpod_schedule.py' > "$TMP_CRON" || true
cat >> "$TMP_CRON" <<EOF
# === RunPod auto schedule (Phase 54.8) ===
# Start at 08:50 IST (Mon-Sat) — gives 10 min cold-start buffer before 09:00
20 3 * * 1-6 ${VENV_PY} ${SCRIPT} start  >> ${LOG_FILE} 2>&1
# Stop at 18:30 IST (Mon-Sat)
0 13 * * 1-6 ${VENV_PY} ${SCRIPT} stop   >> ${LOG_FILE} 2>&1
EOF
crontab "$TMP_CRON"
rm -f "$TMP_CRON"

echo "============================================================"
echo "✅  RunPod auto schedule installed"
echo "------------------------------------------------------------"
echo "  Start: 08:50 IST Mon–Sat"
echo "  Stop:  18:30 IST Mon–Sat"
echo ""
echo "Verify cron:    crontab -l | grep runpod"
echo "Verify helpers: which runpod-start runpod-stop runpod-status"
echo "Watch log:      tail -f ${LOG_FILE}"
echo "Manual run:     runpod-status"
echo "============================================================"
