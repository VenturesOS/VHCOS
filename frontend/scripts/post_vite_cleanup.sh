#!/usr/bin/env bash
#
# Post-Vite Cleanup Script
# ========================
#
# Runs the three follow-up chores documented in the Vite runbook:
#   1. Rename `.js` files that contain JSX → `.jsx`
#   2. Flip `process.env.REACT_APP_*` → `import.meta.env.VITE_*`
#   3. Migrate jest → vitest scaffolding (config + `test` script swap)
#
# All three are DEFERRED until Vite is live in prod (Phase B of the runbook).
# Running them before Phase B is safe but pointless — the JSX-in-.js support
# already handles the mixed state.
#
# Usage:
#   bash scripts/post_vite_cleanup.sh --step rename    # Step 1
#   bash scripts/post_vite_cleanup.sh --step env       # Step 2
#   bash scripts/post_vite_cleanup.sh --step test      # Step 3
#   bash scripts/post_vite_cleanup.sh --step all       # 1 → 2 → 3
#
# Every step supports --dry-run to preview changes without applying.
#
set -euo pipefail

STEP=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --step) STEP="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$STEP" ]]; then
  echo "Usage: $0 --step {rename|env|test|all} [--dry-run]"
  exit 1
fi

# Resolve frontend dir relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/../../frontend" && pwd)"
cd "$FRONTEND_DIR"

echo "Frontend dir: $FRONTEND_DIR"
echo "Dry run:      $([[ $DRY_RUN -eq 1 ]] && echo yes || echo no)"
echo

# ---------------------------------------------------------------------------
# Step 1 — Rename JSX-bearing .js files to .jsx
# ---------------------------------------------------------------------------
step_rename() {
  echo "=== Step 1: Rename .js containing JSX → .jsx ==="
  # Find .js files (NOT .jsx) under src/ that contain a JSX tag: <UpperCase ...>
  # `find` gives us a strict .js extension filter that neither rg nor grep's
  # --include='*.js' handles reliably (both can match .jsx too).
  local files
  files=$(find src -type f -name '*.js' ! -name '*.jsx' -exec grep -lE '<[A-Z][A-Za-z0-9]*[[:space:]/>]' {} + 2>/dev/null || true)

  local count=0
  local skipped_index=0
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    # Skip src/index.js — Vite entry is src/index.jsx (already exists during the
    # parallel-install phase). Once craco is removed you can delete src/index.js.
    if [[ "$f" == *"/src/index.js" ]]; then
      skipped_index=1
      continue
    fi
    local new="${f%.js}.jsx"
    if [[ -e "$new" ]]; then
      echo "  SKIP  $f (target $new already exists)"
      continue
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "  DRY   git mv $f $new"
    else
      git mv "$f" "$new" 2>/dev/null || mv "$f" "$new"
      echo "  MOVE  $f → $new"
    fi
    count=$((count + 1))
  done <<< "$files"

  echo "Renamed: $count file(s)"
  [[ $skipped_index -eq 1 ]] && echo "(src/index.js kept — delete manually after craco removal)"
  echo
}

# ---------------------------------------------------------------------------
# Step 2 — Flip process.env.REACT_APP_* → import.meta.env.VITE_*
# ---------------------------------------------------------------------------
step_env() {
  echo "=== Step 2: process.env.REACT_APP_* → import.meta.env.VITE_* ==="
  # Vars actually referenced in src/ (grep to keep this list current):
  #   grep -rho "process\.env\.REACT_APP_[A-Z_]*" src/ | sort -u
  local vars=(
    "REACT_APP_BACKEND_URL"
    "REACT_APP_TURNSTILE_SITE_KEY"
  )
  for var in "${vars[@]}"; do
    local newvar="VITE_${var#REACT_APP_}"
    local pattern="process\\.env\\.${var}"
    local replacement="import.meta.env.${newvar}"
    local hit_files
    hit_files=$(grep -rl -E "$pattern" --include='*.js' --include='*.jsx' src/ 2>/dev/null || true)
    if [[ -z "$hit_files" ]]; then
      echo "  (no hits)  $var"
      continue
    fi
    local count
    count=$(echo "$hit_files" | wc -l | tr -d ' ')
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "  DRY   $var → $newvar   ($count file(s))"
      echo "$hit_files" | sed 's/^/            /'
    else
      # Portable sed -i (macOS + Linux). Use a temp suffix trick.
      while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        sed -i.bak -E "s|$pattern|$replacement|g" "$f" && rm -f "$f.bak"
      done <<< "$hit_files"
      echo "  DONE  $var → $newvar   ($count file(s))"
    fi
  done

  echo
  echo "Also rename in .env / .env.production / vite.config.js define block:"
  echo "  REACT_APP_BACKEND_URL       → VITE_BACKEND_URL"
  echo "  REACT_APP_TURNSTILE_SITE_KEY → VITE_TURNSTILE_SITE_KEY"
  echo "Then simplify vite.config.js — remove the define{} block entirely, since"
  echo "import.meta.env.VITE_* is exposed automatically by Vite."
  echo
}

# ---------------------------------------------------------------------------
# Step 3 — Scaffold vitest (jest → vitest)
# ---------------------------------------------------------------------------
step_test() {
  echo "=== Step 3: Scaffold vitest ==="
  echo "This step is manual because your test suite is minimal — likely just"
  echo "component snapshot tests. Do this by hand:"
  echo
  echo "  1. yarn add -D vitest @testing-library/jest-dom jsdom"
  echo "  2. Add to vite.config.js:"
  echo "       import { defineConfig } from 'vitest/config'"
  echo "       test: { globals: true, environment: 'jsdom', setupFiles: ['./src/setupTests.js'] }"
  echo "  3. In package.json: \"test\": \"vitest run\", \"test:watch\": \"vitest\""
  echo "  4. Convert any \`jest.fn()\` → \`vi.fn()\`, \`jest.mock()\` → \`vi.mock()\`"
  echo "  5. yarn remove jest @testing-library/jest jest-environment-jsdom  (if present)"
  echo
  echo "Once done, delete this section from post_vite_cleanup.sh."
  echo
}

case "$STEP" in
  rename) step_rename ;;
  env)    step_env ;;
  test)   step_test ;;
  all)    step_rename; step_env; step_test ;;
  *)      echo "Unknown step: $STEP"; exit 1 ;;
esac

echo "Done."
