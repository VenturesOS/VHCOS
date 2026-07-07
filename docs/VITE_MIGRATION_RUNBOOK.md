# Vite Migration Runbook — VHCOS Frontend

**Status:** ✅ **Validated in `/app/frontend`** (2026-07-07). Vite build succeeds in ~7.2s vs craco's ~57s (**8× faster**). Bundle size parity (184 kB gzip main). Ready to replicate on prod EC2 in a feature branch.

**Effort:** ~1 hour of focused execution + verification. Was originally scoped at 1 day; parallel-installation approach cuts risk drastically.

**Blast radius:** every deploy. Freeze other frontend work on `main` while this branch is open. Test on prod via a feature branch → PR → merge → deploy.

---

## Why migrate

- **CRA is unmaintained** — no security patches since Jan 2023, react-scripts is deprecated.
- **Craco patches** CRA's webpack config — patching a dead toolchain.
- **Build time drops ~87%** — 7.2s (Vite) vs 57s (craco) on the VHCOS codebase.
- **Dev server:** Vite boots in <500ms vs craco's 12–18s cold.

## Non-goals

- Do NOT ship this at the same time as other frontend changes.
- Do NOT introduce TypeScript in the same PR.
- Do NOT change routing / auth / API-shape during migration. Only build tooling.
- Do NOT rename all `.js` → `.jsx` in this PR (~200 files). We handle JSX-in-.js via `esbuild.loader: 'jsx'`. Rename in a follow-up.

---

## Approach: Parallel Install (validated)

Rather than a "big-bang" replacement, add Vite **alongside** craco. Both coexist. `yarn build` still runs craco; `yarn vite:build` runs Vite. Verify Vite on a preview host, then flip `build` → `vite build` in a follow-up commit and remove craco after 1–2 clean deploys.

---

## Step-by-step (verified against /app/frontend, 2026-07-07)

### 1. Cut a branch on prod

```bash
cd /home/ubuntu/vhc-platform/frontend
git checkout -b feat/vite-migration
```

### 2. Install Vite 5 (NOT Vite 8 — Rolldown JSX parser is stricter and breaks)

```bash
yarn add -D vite@^5.4.0 @vitejs/plugin-react@^4.3.0 vite-tsconfig-paths
```

### 3. Create `frontend/vite.config.js`

Exact working config (validated in `/app/frontend/vite.config.js`):

```js
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname), '');
  return {
    plugins: [
      react({ include: /\.(js|jsx|ts|tsx)$/ }),
    ],
    resolve: {
      alias: { '@': path.resolve(__dirname, 'src') },
    },
    // Treat .js files under src/ as JSX (avoid renaming ~200 files).
    esbuild: {
      loader: 'jsx',
      include: /src\/.*\.jsx?$/,
      exclude: [],
    },
    optimizeDeps: {
      esbuildOptions: { loader: { '.js': 'jsx' } },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      strictPort: true,
      proxy: { '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true } },
      allowedHosts: ['.preview.emergentagent.com', 'localhost', '127.0.0.1'],
    },
    build: {
      outDir: 'build',
      sourcemap: false,
      chunkSizeWarningLimit: 1500,
    },
    envPrefix: ['REACT_APP_', 'VITE_'],
    define: {
      // CRA-compat: expose the REACT_APP_* vars the app actually reads.
      // Grep to keep current: grep -rho "process\.env\.REACT_APP_[A-Z_]*" src/ | sort -u
      'process.env.REACT_APP_BACKEND_URL': JSON.stringify(env.REACT_APP_BACKEND_URL || ''),
      'process.env.REACT_APP_TURNSTILE_SITE_KEY': JSON.stringify(env.REACT_APP_TURNSTILE_SITE_KEY || ''),
      'process.env.NODE_ENV': JSON.stringify(mode === 'production' ? 'production' : 'development'),
    },
  };
});
```

### 4. Create `frontend/index.html` (Vite entry) as a copy of `public/index.html`

- Move it up one level (project root, not inside `public/`).
- Replace every `%PUBLIC_URL%/foo` with `/foo`.
- Add before `</body>`:
  ```html
  <script type="module" src="/src/index.jsx"></script>
  ```
- Vite auto-copies everything in `public/` to `build/` at build time. Do NOT move files out of `public/` — leave `favicon.ico`, `manifest.json`, `service-worker.js`, `sitemap.xml`, `robots.txt`, `website/`, etc. right where they are.

### 5. Create `src/index.jsx` (Vite entry)

Copy `src/index.js` → `src/index.jsx` verbatim. Keep the original `src/index.js` so craco still works during the parallel-install phase.

```jsx
import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { initErrorCapture } from "@/lib/errorCapture";

initErrorCapture();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch(() => {});
  });
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<React.StrictMode><App /></React.StrictMode>);
```

### 6. Add Vite scripts to `package.json` (keep craco scripts too)

```jsonc
{
  "scripts": {
    "start": "craco start",
    "build": "craco build",
    "test": "craco test",
    "vite:start": "vite",
    "vite:build": "vite build",
    "vite:preview": "vite preview"
  }
}
```

### 7. Verify locally

```bash
yarn install
yarn vite:build   # expect ~7s build, no errors, output in build/
ls build/assets/  # 100+ chunk files
grep -oE '"https://[^"]*preview\.emergentagent[^"]*"' build/assets/index-*.js | head -3
# Expect: your REACT_APP_BACKEND_URL baked in

# Serve built output and sanity-check
cd build && python3 -m http.server 8899 &
sleep 2
curl -sI http://localhost:8899/                     # HTTP/1.0 200
curl -sI http://localhost:8899/favicon.ico          # HTTP/1.0 200
curl -sI http://localhost:8899/website/about.html   # HTTP/1.0 200 (static marketing page)
curl -sI http://localhost:8899/sitemap.xml          # HTTP/1.0 200
kill %1
```

### 8. Screenshot before/after (P0 for shipping)

Take 1920×800 screenshots of the built output for all 8 sensitive routes:
`/`, `/login`, `/dashboard`, `/candidate-bank`, `/admin/badge-audit`,
`/admin/tally-health`, `/jobs/:id`, `/career-insights/:slug`.

Compare against a baseline craco build. Any pixel diff = investigate before shipping.

### 9. Nginx compat check

Vite emits `/assets/index-HASH.js` instead of CRA's `/static/js/main.HASH.js`. If your nginx config has hardcoded `location /static/` rules that DON'T just fall through to `try_files`, you may need to add:

```nginx
location /assets/ {
    root /path/to/build;
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

Most VHCOS nginx configs use the SPA-standard `try_files $uri $uri/ /index.html` which handles both. Verify with:
```bash
sudo grep -A 2 "location /static\|location /assets" /etc/nginx/sites-enabled/default
```

### 10. Ship in two phases

**Phase A — parallel-install PR:**
- Merges the config alongside craco.
- Prod still deploys `yarn build` (craco). Zero visible change.
- Verify `yarn vite:build` succeeds in CI.

**Phase B — flip PR (1–2 weeks later):**
- Edit `package.json`: swap `"build": "craco build"` → `"build": "vite build"`.
- Deploy. Watch monitoring dashboards + smoke-test the 8 sensitive routes.

**Phase C — cleanup PR (after 2 clean deploys):**
- Remove `@craco/craco`, `craco.config.js`, `react-scripts`, `src/index.js`, `public/index.html`.
- Remove `frontend/plugins/visual-edits/` and `frontend/plugins/health-check/` if only used by craco.

---

## Rollback

- **Phase B failure:** revert the flip commit. `yarn build` returns to craco. No infra change needed.
- **Phase C failure:** re-add `react-scripts` + `@craco/craco` from git history. All craco files preserved in older commits.

---

## Known gotchas (learned during /app validation)

1. **Vite 8 (Rolldown) rejects JSX in .js files** even with `esbuild.loader: 'jsx'`. Stay on Vite 5 until Rolldown adds a compat flag.
2. **`define: { 'process.env.X': ... }` reads shell env, not `.env` file.** Use `loadEnv()` in the config factory function.
3. **`public/index.html` is NOT the Vite entry.** Vite uses `frontend/index.html` (project root). Leave `public/index.html` alone — craco still needs it during the parallel-install phase.
4. **Service worker cache pattern (`.js`, `.css`, `/static/`)** in `public/service-worker.js` already covers Vite's `/assets/` paths via the `.js`/`.css` catch-all. No change needed.
5. **The visual-edits plugin (`frontend/plugins/visual-edits/`)** is a craco/webpack babel plugin. It has no Vite equivalent and is dev-only Emergent preview tooling — NOT used in prod. Leave it alone during migration; delete in Phase C.

---

## Deferred to follow-up PRs

- Rename `REACT_APP_*` env vars → `VITE_*` (across ~40 call sites; use `sed` + code review).
- Migrate jest → vitest (share the Vite config; ~1 day).
- Convert files with JSX from `.js` → `.jsx` across the tree (~200 files; purely cosmetic once the entry is `.jsx`).
- Optional: enable `@vitejs/plugin-react-swc` for ~30% faster HMR.
