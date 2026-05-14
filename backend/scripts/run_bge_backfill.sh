#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# VHC Talent OS — BGE embedding backfill wrapper (EC2)
#
# Two modes:
#   --full         Full backfill — embed every candidate that doesn't yet have an
#                  embedding. Takes ~5–6 hrs for 1.23 L candidates at concurrency 16.
#   --incremental  Nightly top-up — only embeds new/changed candidates. <5 min
#                  in steady state. Default if no flag is passed.
#
# Pre-flight checks:
#   • Sidecar reachable on $BGE_SIDECAR_URL (read from backend/.env)
#   • MongoDB reachable
# Logs to /var/log/vhc/bge_backfill_<mode>_<date>.log
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/vhc-platform}"
BACKEND_DIR="$APP_DIR/backend"
VENV_DIR="${VENV_DIR:-$BACKEND_DIR/venv}"
LOG_DIR="${LOG_DIR:-/var/log/vhc}"

MODE="incremental"
if [[ "${1:-}" == "--full" ]]; then
  MODE="full"
elif [[ "${1:-}" == "--incremental" ]]; then
  MODE="incremental"
fi

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/bge_backfill_${MODE}_$(date +%Y%m%d_%H%M%S).log"

# Always append to a "latest" symlink so cron/systemd can tail one path
ln -sf "$LOG" "$LOG_DIR/bge_backfill_${MODE}.latest.log"

exec >>"$LOG" 2>&1
echo "=== $(date -Is) start [$MODE] ==="

cd "$BACKEND_DIR"

# Load env so we can read BGE_SIDECAR_URL
set -a
# shellcheck disable=SC1091
source .env
set +a

SIDECAR_URL="${BGE_SIDECAR_URL:-}"
if [[ -z "$SIDECAR_URL" ]]; then
  echo "FATAL: BGE_SIDECAR_URL not set in $BACKEND_DIR/.env — aborting"
  exit 2
fi

# ── Wait up to 90 s for the sidecar to respond ────────────────────────────────
echo "Probing sidecar at $SIDECAR_URL/health ..."
for i in {1..18}; do
  http_code=$(curl -s -o /tmp/sidecar_health.json -w "%{http_code}" --max-time 5 "$SIDECAR_URL/health" || echo "000")
  if [[ "$http_code" == "200" ]] && grep -q '"ready"\s*:\s*true' /tmp/sidecar_health.json 2>/dev/null; then
    echo "Sidecar OK ($http_code): $(cat /tmp/sidecar_health.json)"
    break
  fi
  echo "  attempt $i: http=$http_code, sleeping 5s..."
  sleep 5
done

if [[ "$http_code" != "200" ]]; then
  echo "FATAL: sidecar not healthy after 90s — aborting (check RunPod pod is awake + sidecar.sh started)"
  exit 3
fi

# ── Run the Python backfill ───────────────────────────────────────────────────
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

PYTHON_ARGS=(--concurrency 16 --fast-summary --skip-cold-days 0)
if [[ "$MODE" == "full" ]]; then
  PYTHON_ARGS+=(--all)
fi
# Incremental mode uses defaults (--only-missing implicit).

echo "Running: python3 scripts/backfill_talent_graph.py ${PYTHON_ARGS[*]}"
START=$(date +%s)
python3 scripts/backfill_talent_graph.py "${PYTHON_ARGS[@]}"
RC=$?
END=$(date +%s)
ELAPSED=$((END - START))

echo "=== $(date -Is) DONE [$MODE] in ${ELAPSED}s exit=$RC ==="
exit "$RC"
