import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// Vite migration — see docs/VITE_MIGRATION_RUNBOOK.md
// Coexists with craco during migration. Once prod deploys are on Vite,
// craco.config.js + @craco/craco + react-scripts can be removed.
export default defineConfig(({ mode }) => {
  // Load .env, .env.production, .env.development based on mode.
  // The empty prefix ('') means load ALL vars — we filter what to expose below.
  const env = loadEnv(mode, path.resolve(__dirname), '');

  return {
    plugins: [
      // Treat all .js files under src/ as JSX so we don't have to rename
      // ~200 files during the migration. Rename in a follow-up PR.
      react({
        include: /\.(js|jsx|ts|tsx)$/,
      }),
    ],
    resolve: {
      alias: { '@': path.resolve(__dirname, 'src') },
    },
    // Tell esbuild + Rollup's import-analysis pass to treat all .js files
    // under src/ as JSX. This lets us keep .js extensions during the
    // migration; rename to .jsx in a follow-up PR.
    esbuild: {
      loader: 'jsx',
      include: /src\/.*\.jsx?$/,
      exclude: [],
    },
    optimizeDeps: {
      esbuildOptions: {
        loader: { '.js': 'jsx' },
      },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      strictPort: true,
      proxy: {
        '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      },
      allowedHosts: ['.preview.emergentagent.com', 'localhost', '127.0.0.1'],
    },
    build: {
      outDir: 'build',
      sourcemap: false,
      chunkSizeWarningLimit: 1500,
    },
    // CRA env-var contract preserved: process.env.REACT_APP_* still works.
    envPrefix: ['REACT_APP_', 'VITE_'],
    define: {
      // CRA exposed process.env at runtime; Vite doesn't by default.
      // Re-expose only the REACT_APP_* subset the app actually reads.
      // Grep to keep this list current:
      //   grep -rho "process\.env\.REACT_APP_[A-Z_]*" src/ | sort -u
      'process.env.REACT_APP_BACKEND_URL': JSON.stringify(env.REACT_APP_BACKEND_URL || ''),
      'process.env.REACT_APP_TURNSTILE_SITE_KEY': JSON.stringify(env.REACT_APP_TURNSTILE_SITE_KEY || ''),
      'process.env.NODE_ENV': JSON.stringify(mode === 'production' ? 'production' : 'development'),
    },
  };
});


