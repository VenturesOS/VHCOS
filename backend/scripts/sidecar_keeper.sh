#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# VHC Talent OS — RunPod BGE Sidecar Keeper
#
# Run from EC2. Checks if the BGE sidecar on the RunPod pod is up; if not,
# SSHes into the pod and (re)starts it in the background.
#
# Requirements (one-time setup):
#   1. RunPod pod must expose an SSH endpoint. From RunPod dashboard:
#        Connect → SSH → copy the connection string, looks like:
#        ssh root@ssh.runpod.io -p 12345 -i ~/.ssh/id_ed25519
#      Add the host/port/key to ~/.ssh/config on EC2 as host alias `runpod-bge`:
#        Host runpod-bge
#            HostName ssh.runpod.io
#            User root
#            Port 12345
#            IdentityFile /home/ubuntu/.ssh/runpod_id_ed25519
#            StrictHostKeyChecking accept-new
#   2. Sidecar code must already be in the pod at /workspace/embed_service.py
#      (matches the current manual paste). The keeper just (re)starts it.
#
# Idempotent: if the sidecar is already healthy this exits 0 without action.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/vhc-platform}"
BACKEND_DIR="$APP_DIR/backend"
LOG_DIR="${LOG_DIR:-/var/log/vhc}"
SSH_HOST_ALIAS="${SIDECAR_SSH_HOST:-runpod-bge}"

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/bge_sidecar_keeper.log"
exec >>"$LOG" 2>&1
echo "=== $(date -Is) keeper run ==="

# Load env
set -a
# shellcheck disable=SC1091
source "$BACKEND_DIR/.env"
set +a

SIDECAR_URL="${BGE_SIDECAR_URL:-}"
if [[ -z "$SIDECAR_URL" ]]; then
  echo "FATAL: BGE_SIDECAR_URL unset"
  exit 2
fi

# ── Health probe ──────────────────────────────────────────────────────────────
http_code=$(curl -s -o /tmp/keeper_health.json -w "%{http_code}" --max-time 5 "$SIDECAR_URL/health" || echo "000")
if [[ "$http_code" == "200" ]] && \
   grep -qE '"(ready|model_loaded)"\s*:\s*true' /tmp/keeper_health.json 2>/dev/null; then
  echo "OK: sidecar already healthy — $(cat /tmp/keeper_health.json)"
  exit 0
fi

echo "Sidecar UNHEALTHY (http=$http_code). Attempting remote restart via SSH alias '$SSH_HOST_ALIAS'..."

# ── Remote start ──────────────────────────────────────────────────────────────
# Kill any stale sidecar process first, then start fresh in nohup background.
# Note: embed_service.py has no `if __name__ == "__main__"` / uvicorn.run()
# at the bottom — it just defines the FastAPI app — so we MUST invoke uvicorn
# explicitly. setsid + nohup ensures the process stays alive after SSH closes.
REMOTE_CMD=$(cat <<'EOSH'
set -e
cd /workspace
pkill -f "uvicorn.*embed_service" 2>/dev/null || true
pkill -f embed_service.py 2>/dev/null || true
sleep 3
setsid nohup python3 -u -m uvicorn embed_service:app \
  --host 0.0.0.0 --port 8001 \
  >> /workspace/sidecar.log 2>&1 < /dev/null &
disown
echo "Started: PID $!"
EOSH
)

ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "$SSH_HOST_ALIAS" "$REMOTE_CMD" || {
  echo "FATAL: SSH to $SSH_HOST_ALIAS failed (RC=$?). Check ~/.ssh/config + key permissions."
  exit 4
}

# ── Re-probe (allow up to 60 s for model load) ────────────────────────────────
echo "Waiting for sidecar to warm up..."
for i in {1..12}; do
  sleep 5
  http_code=$(curl -s -o /tmp/keeper_health.json -w "%{http_code}" --max-time 5 "$SIDECAR_URL/health" || echo "000")
  if [[ "$http_code" == "200" ]] && \
     grep -qE '"(ready|model_loaded)"\s*:\s*true' /tmp/keeper_health.json 2>/dev/null; then
    echo "OK: sidecar warmed up in $((i*5))s — $(cat /tmp/keeper_health.json)"
    exit 0
  fi
done

echo "FATAL: sidecar did not warm up within 60s after restart attempt"
exit 5
