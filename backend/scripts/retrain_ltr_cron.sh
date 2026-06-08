#!/bin/bash
# Weekly LTR retrain cron — Phase 56.8 (Jun 2026)
#
# Runs the training pipeline against the latest accumulated triplets in
# search_sessions. Idempotent: if not enough triplets accumulated since
# the last run, the script exits 1 without overwriting.
#
# Crontab entry (run Sunday 03:00 UTC, after the weekend's data settles):
#   0 3 * * 0 /app/backend/scripts/retrain_ltr_cron.sh >> /var/log/vhc/ltr-retrain.log 2>&1
#
# Env hooks
#   LTR_MIN_TRIPLETS — refuse to train below this (default 5000 = scoping target)
#   LTR_VENV         — path to the python venv (default /root/.venv)
#   LTR_BACKEND_DIR  — absolute path to backend (default /app/backend)
set -euo pipefail

LTR_VENV="${LTR_VENV:-/root/.venv}"
LTR_BACKEND_DIR="${LTR_BACKEND_DIR:-/app/backend}"
LTR_MIN_TRIPLETS="${LTR_MIN_TRIPLETS:-5000}"

echo "──────────────────────────────────────────────────"
echo "LTR retrain $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "  venv:     $LTR_VENV"
echo "  backend:  $LTR_BACKEND_DIR"
echo "  min:      $LTR_MIN_TRIPLETS triplets"
echo "──────────────────────────────────────────────────"

cd "$LTR_BACKEND_DIR"
"$LTR_VENV/bin/python" -m scripts.train_ltr_model --train --min-triplets "$LTR_MIN_TRIPLETS"
rc=$?

if [ $rc -eq 0 ]; then
    echo "RETRAIN: success — new model artifact saved to $LTR_BACKEND_DIR/data/ltr_models/"
    # Live model is loaded lazily on first /search request — nothing else to do.
    # Workers will pick up the new artifact when they next start cold; for hot
    # reload, restart the backend after verifying NDCG@10 in the meta sidecar.
elif [ $rc -eq 1 ]; then
    echo "RETRAIN: skipped — insufficient triplets (below $LTR_MIN_TRIPLETS). No-op."
elif [ $rc -eq 2 ]; then
    echo "RETRAIN: failed — xgboost not installed in $LTR_VENV. Fix:" >&2
    echo "   $LTR_VENV/bin/pip install xgboost" >&2
    exit 2
else
    echo "RETRAIN: failed with rc=$rc — investigate" >&2
    exit $rc
fi
