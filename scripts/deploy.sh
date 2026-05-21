#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# VHC Talent OS — Auto-deploy script (Phase 55.7 / Feb 2026)
#
# What this does (in order):
#   1. git pull           — sync latest code from origin
#   2. pip install        — update Python deps if requirements.txt changed
#   3. yarn install       — update Node deps if package.json changed
#   4. yarn build         — build the React production bundle
#   5. rsync to Nginx     — sync build/ -> /var/www/html/
#   6. systemd restart    — restart vhc-backend.service
#   7. nginx reload       — reload Nginx with new static assets
#   8. healthcheck        — curl /api/health and bail out on non-200
#
# Designed to be:
#   • idempotent           (safe to run twice in a row)
#   • fast on no-op pulls  (skips yarn/pip when checksums unchanged)
#   • loud on failure      (set -e, traps with line numbers)
#   • production-safe      (refuses to run on dirty working tree)
#
# Usage:
#   ./deploy.sh                  # full deploy
#   ./deploy.sh --skip-pull      # skip git pull (use current working tree)
#   ./deploy.sh --frontend-only  # only rebuild + rsync frontend
#   ./deploy.sh --backend-only   # only pip install + restart backend
#
# Install as a Git post-merge hook (recommended):
#   ln -s ../../scripts/deploy.sh .git/hooks/post-merge
#   chmod +x scripts/deploy.sh
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Config (override via env if your prod layout differs) ────────────
REPO_DIR="${REPO_DIR:-/home/ubuntu/vhc-platform}"
FRONTEND_DIR="${FRONTEND_DIR:-$REPO_DIR/frontend}"
BACKEND_DIR="${BACKEND_DIR:-$REPO_DIR/backend}"
VENV_DIR="${VENV_DIR:-$BACKEND_DIR/venv}"
NGINX_WEB_ROOT="${NGINX_WEB_ROOT:-/var/www/html}"
BACKEND_SERVICE="${BACKEND_SERVICE:-vhc-backend}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1:8001/api/health}"
GIT_BRANCH="${GIT_BRANCH:-main}"

# ── Flags ────────────────────────────────────────────────────────────
SKIP_PULL=0
FRONTEND_ONLY=0
BACKEND_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --skip-pull)      SKIP_PULL=1 ;;
    --frontend-only)  FRONTEND_ONLY=1 ;;
    --backend-only)   BACKEND_ONLY=1 ;;
    -h|--help)
      sed -n '1,40p' "$0"; exit 0 ;;
    *)
      echo "[deploy] Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# ── Pretty logging ───────────────────────────────────────────────────
B="\033[1m"; G="\033[1;32m"; Y="\033[1;33m"; R="\033[1;31m"; X="\033[0m"
log()  { printf "${B}[deploy]${X} %s\n" "$*"; }
ok()   { printf "${G}[deploy] ✓ %s${X}\n" "$*"; }
warn() { printf "${Y}[deploy] ⚠ %s${X}\n" "$*"; }
err()  { printf "${R}[deploy] ✗ %s${X}\n" "$*" >&2; }

on_err() {
  local rc=$? line=${1:-?}
  err "FAILED at line $line (exit=$rc). The site is NOT fully updated."
  exit "$rc"
}
trap 'on_err $LINENO' ERR

# ── Pre-flight: layout sanity ────────────────────────────────────────
[[ -d "$REPO_DIR/.git"   ]] || { err "REPO_DIR ($REPO_DIR) is not a git checkout"; exit 1; }
[[ -d "$FRONTEND_DIR"    ]] || { err "FRONTEND_DIR not found: $FRONTEND_DIR"; exit 1; }
[[ -d "$BACKEND_DIR"     ]] || { err "BACKEND_DIR not found: $BACKEND_DIR"; exit 1; }
[[ -d "$NGINX_WEB_ROOT"  ]] || { err "NGINX_WEB_ROOT not found: $NGINX_WEB_ROOT"; exit 1; }

cd "$REPO_DIR"

# Refuse on a dirty tree (unless skip-pull, in which case the caller knows)
if [[ "$SKIP_PULL" -eq 0 ]]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    err "Working tree has uncommitted changes. Commit/stash first, or pass --skip-pull."
    git status --short
    exit 1
  fi
fi

# ── Stage 1: git pull ────────────────────────────────────────────────
PRE_HEAD="$(git rev-parse HEAD)"
if [[ "$SKIP_PULL" -eq 0 ]]; then
  log "git pull origin $GIT_BRANCH"
  git fetch --quiet origin "$GIT_BRANCH"
  git checkout --quiet "$GIT_BRANCH"
  git pull --ff-only --quiet origin "$GIT_BRANCH"
fi
POST_HEAD="$(git rev-parse HEAD)"

# What changed in this pull? (used to decide pip/yarn install)
if [[ "$PRE_HEAD" == "$POST_HEAD" ]]; then
  CHANGED_FILES=""
  log "No new commits — proceeding with rebuild only."
else
  CHANGED_FILES="$(git diff --name-only "$PRE_HEAD" "$POST_HEAD")"
  log "Pulled $(echo "$CHANGED_FILES" | wc -l) file(s) changed: $PRE_HEAD..$POST_HEAD"
fi

changed() { [[ -z "$CHANGED_FILES" ]] && return 1; grep -qE "^$1" <<<"$CHANGED_FILES"; }

# ── Stage 2: backend (pip + service restart) ─────────────────────────
if [[ "$FRONTEND_ONLY" -eq 0 ]]; then
  if [[ -d "$VENV_DIR" ]]; then
    if [[ -z "$CHANGED_FILES" ]] || changed 'backend/requirements\.txt'; then
      log "pip install -r backend/requirements.txt"
      # shellcheck source=/dev/null
      source "$VENV_DIR/bin/activate"
      pip install --quiet \
        --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ \
        -r "$BACKEND_DIR/requirements.txt"
      deactivate
      ok "Python deps up to date."
    else
      log "requirements.txt unchanged — skipping pip install."
    fi
  else
    warn "VENV_DIR not found ($VENV_DIR) — skipping pip install."
  fi

  log "systemctl restart $BACKEND_SERVICE"
  sudo systemctl restart "$BACKEND_SERVICE"
  # Give it a moment, then health-check
  sleep 3
  if curl -sf --max-time 8 "$HEALTHCHECK_URL" >/dev/null; then
    ok "Backend healthy ($HEALTHCHECK_URL)"
  else
    err "Backend healthcheck FAILED. Check: sudo journalctl -u $BACKEND_SERVICE -n 80"
    exit 1
  fi
fi

# ── Stage 3: frontend (yarn install + build + rsync + nginx reload) ──
if [[ "$BACKEND_ONLY" -eq 0 ]]; then
  cd "$FRONTEND_DIR"

  if [[ -z "$CHANGED_FILES" ]] || changed 'frontend/(package\.json|yarn\.lock)'; then
    log "yarn install --frozen-lockfile"
    yarn install --frozen-lockfile
    ok "Node deps up to date."
  else
    log "package.json/yarn.lock unchanged — skipping yarn install."
  fi

  log "yarn build (React production bundle)"
  CI=false yarn build

  log "rsync build/ -> $NGINX_WEB_ROOT"
  sudo rsync -a --delete "$FRONTEND_DIR/build/" "$NGINX_WEB_ROOT/"

  log "nginx -t && systemctl reload nginx"
  sudo nginx -t
  sudo systemctl reload nginx
  ok "Nginx reloaded with new static assets."
fi

# ── Done ─────────────────────────────────────────────────────────────
ok "Deploy complete. HEAD=$POST_HEAD"
log "Visit your domain to verify. If anything looks stale, force-refresh (Ctrl+Shift+R)."
