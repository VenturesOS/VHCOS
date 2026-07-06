# Vite Migration Runbook — VHCOS Frontend

**Status:** scoped, not shipped. This document is the step-by-step for
executing the CRA/craco → Vite migration in a single focused session.
Attempting it inside a shared agent session with 20 other tasks is how you
end up with a half-migrated repo you have to revert.

**Effort:** ~1 full day, 1 person, in a feature branch.
**Blast radius:** every dev, every build, every deploy. Freeze other frontend
work on `main` while this branch is open.

---

## Why migrate

- **CRA is unmaintained** — no security patches since Jan 2023, react-scripts
  is deprecated. `create-react-app` is officially discontinued.
- **Craco** patches CRA's webpack config, which means we're patching a dead
  toolchain. Every version bump of React/webpack is a coin flip.
- **Build time:** Vite dev-server starts in ~200ms; craco takes 12-18s cold.
  Prod bundle time drops ~40% (esbuild + native ESM).
- **Modern tooling** — `import.meta.env`, native ESM, first-class TypeScript
  path if you ever want it.

## Non-goals

- Do NOT ship this at the same time as other frontend changes.
- Do NOT introduce TypeScript in the same PR.
- Do NOT change routing / auth / API-shape during migration. Only build tooling.

---

## Pre-flight

1. Cut a branch: `git checkout -b feat/vite-migration`.
2. Confirm all frontend tests + `yarn build` pass on `main` first — baseline
   for "same as before".
3. Screenshot the following pages at 1920×800 (before/after visual diff):
   `/`, `/login`, `/dashboard`, `/candidate-bank`, `/admin/badge-audit`,
   `/admin/tally-health`, `/jobs/:id`, `/career-insights/:slug`.
4. Note down current `yarn build` output size (`build/static/js/main.*.js`
   gzip figure from `deploy.sh` logs). Compare after.

## Step-by-step

### 1. Install Vite + plugin

```bash
cd /app/frontend
yarn add -D vite @vitejs/plugin-react vite-tsconfig-paths
yarn add -D @vitejs/plugin-legacy       # only if you must support browsers older than the last 2 Chrome/Safari
```

### 2. Create `vite.config.js`

Drop this in `frontend/vite.config.js`:

```js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    strictPort: true,
    // Proxy /api → backend (dev only). Prod uses REACT_APP_BACKEND_URL.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
    },
    // Preview env quirk: allow the emergent domain.
    allowedHosts: ['.preview.emergentagent.com', 'localhost', '127.0.0.1'],
  },
  build: {
    outDir: 'build',              // deploy.sh rsyncs from build/, keep the name
    sourcemap: false,
    chunkSizeWarningLimit: 1500,  // suppress noise from the vendor chunk
  },
  // CRA env vars are prefixed REACT_APP_*. Keep that contract for a
  // clean migration — flip everything to VITE_* later in a separate PR.
  envPrefix: ['REACT_APP_', 'VITE_'],
});
```

### 3. Move `public/index.html` → `frontend/index.html`

Vite treats `index.html` as the entry. Move it up one level and change:

```html
<!-- OLD (CRA) -->
<div id="root"></div>
<!-- CRA injected the bundle here automatically -->

<!-- NEW (Vite) -->
<div id="root"></div>
<script type="module" src="/src/index.js"></script>
```

Replace every `%PUBLIC_URL%` with `/` and every `%REACT_APP_*%` template
placeholder with the runtime `process.env.REACT_APP_*` (Vite exposes the
same shape via `envPrefix` above).

Move all other files in `public/` (favicon, robots.txt, sitemap.xml,
`website/`, `og-default.png`) to a new top-level `public/` — Vite copies
that folder as-is to `build/`.

### 4. Rename `src/index.js` if needed

Vite requires the entry to be `.jsx` when it contains JSX. Rename
`src/index.js` → `src/index.jsx`. Same for any `.js` files that contain
JSX (grep: `grep -rln "return (" src/ | xargs grep -l "<[A-Z]"`).

### 5. Environment variables

CRA: `process.env.REACT_APP_BACKEND_URL`
Vite (with our envPrefix): SAME string works, no code change needed.
`import.meta.env.REACT_APP_BACKEND_URL` also works. Keep `process.env.*`
for zero-touch migration.

### 6. Update `package.json`

```jsonc
{
  "scripts": {
    "start": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "jest"                // unchanged for now; vitest is a future PR
  }
}
```

Remove `@craco/craco`, `craco.config.js`, `react-scripts` from devDeps
(but keep `react-scripts` around one more deploy in case you need to
roll back — `yarn remove` in the follow-up).

### 7. `deploy.sh` — one line change

The script currently does `yarn build`. That still works — Vite writes
to `build/` because we set `outDir: 'build'` in the config. No change
required. Verify after first CI run.

### 8. Nginx `/website/` compat

CRA's `public/website/` static bundle is served by CRA dev-server via
craco's `middlewares` config. Vite serves the `public/` folder natively,
so this Just Works after you move the files up (step 3).

Verify: `curl http://localhost:3000/website/careers.html` returns HTML,
not the SPA shell.

### 9. Verify

```bash
yarn install
yarn start                 # dev server, expect < 500 ms boot
# Visit every route in the pre-flight screenshot list. Diff pixels.
yarn build                 # expect esbuild + rollup, no craco warnings
ls -sh build/static/js/main.*  # bundle size should shrink
```

### 10. Ship

Merge feature branch. First deploy:

```bash
cd /home/ubuntu/vhc-platform && git pull origin main && bash scripts/deploy.sh
```

Watch the deploy logs for "Vite" not "craco". If any craco reference
appears, the migration is partial — revert immediately.

---

## Rollback

Two paths:

1. **Instant:** `git revert <merge-commit>` on `main` and redeploy. Because
   we did not change any runtime code (only build tooling), a revert is safe.
2. **Alternative:** re-add `@craco/craco` and `react-scripts` to `package.json`
   (they're still on npm), restore `craco.config.js` and the old
   `package.json` `scripts` block. `yarn install && yarn build` produces
   the CRA output again.

---

## Deferred to follow-up PRs

- Rename `REACT_APP_*` env vars → `VITE_*` (across ~40 call sites; use
  `sed` + code review).
- Migrate jest → vitest (share the Vite config; ~1 day).
- Convert files with JSX from `.js` → `.jsx` across the tree (~200 files;
  purely cosmetic once the entry is `.jsx`).
- Optional: enable `@vitejs/plugin-react-swc` for ~30% faster HMR.
