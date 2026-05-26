import React from 'react';

/**
 * Auto-reload error boundary for stale-bundle crashes.
 *
 * After a deploy, browsers that still have an old `index.html` cached will
 * try to lazy-load chunks with hashes that no longer exist on the server.
 * The server returns HTML 404 → browser tries to eval HTML as JS → either:
 *   • ChunkLoadError
 *   • Uncaught SyntaxError: Unexpected token '<'
 *   • Uncaught ReferenceError: <var> is not defined  (when an old runtime
 *     references a variable name from a since-renamed minified chunk)
 *
 * The fix is a soft reload of the page — that re-fetches `index.html`,
 * gets the new chunk hashes, and the user's app springs back to life.
 *
 * Guard: store a single retry flag in sessionStorage so we don't reload-loop
 * if the issue is something else (e.g. a real bug in our code).
 */
const STORAGE_KEY = 'vhc_chunk_reload_at';
const RETRY_WINDOW_MS = 30_000;  // don't auto-reload twice within 30s

function isChunkError(err) {
  if (!err) return false;
  const name = err.name || '';
  const msg = (err.message || '').toLowerCase();
  return (
    name === 'ChunkLoadError' ||
    msg.includes('loading chunk') ||
    msg.includes("unexpected token '<'") ||
    msg.includes('failed to fetch dynamically imported') ||
    msg.includes('importing a module script failed')
  );
}

function tryReload() {
  try {
    const last = parseInt(sessionStorage.getItem(STORAGE_KEY) || '0', 10);
    if (Date.now() - last < RETRY_WINDOW_MS) return false;
    sessionStorage.setItem(STORAGE_KEY, String(Date.now()));
    window.location.reload();
    return true;
  } catch {
    window.location.reload();
    return true;
  }
}

// Catch async chunk errors that happen outside React's render path
if (typeof window !== 'undefined') {
  window.addEventListener('error', (e) => {
    if (isChunkError(e?.error) || isChunkError(e)) tryReload();
  });
  window.addEventListener('unhandledrejection', (e) => {
    if (isChunkError(e?.reason)) tryReload();
  });
}

export class ChunkErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { reloading: false };
  }

  static getDerivedStateFromError(error) {
    if (isChunkError(error)) return { reloading: true };
    return null;
  }

  componentDidCatch(error) {
    if (isChunkError(error)) {
      tryReload();
    } else {
      // Re-throw so other error boundaries / Sentry can see it
      throw error;
    }
  }

  render() {
    if (this.state.reloading) {
      return (
        <div style={{ padding: 40, textAlign: 'center', fontFamily: 'system-ui, sans-serif', color: '#475569' }}>
          <div>Updating to the latest version…</div>
        </div>
      );
    }
    return this.props.children;
  }
}
