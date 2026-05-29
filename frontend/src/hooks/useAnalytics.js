/**
 * useAnalytics — Phase 56 (Feb 2026)
 *
 * Hook that auto-tracks page views as the user navigates and exposes a
 * `track()` function for custom events.
 *
 * Privacy: We only send route, referrer, and (if logged in) the auth token —
 * the backend hashes the IP daily. No third-party scripts, no cookies, no
 * Google Analytics. Bog standard fetch(), failures are swallowed silently so
 * tracking never breaks the UX.
 */
import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

// Build (or reuse) a per-tab session id so we can group events into sessions.
function _sessionId() {
  try {
    let s = sessionStorage.getItem('vhc_sid');
    if (!s) {
      s = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      sessionStorage.setItem('vhc_sid', s);
    }
    return s;
  } catch {
    return 'no-storage';
  }
}

function _postEvent(payload) {
  try {
    const base = process.env.REACT_APP_BACKEND_URL || '';
    const url = `${base}/api/analytics/track`;
    const token = localStorage.getItem('access_token') || '';
    const body = JSON.stringify({
      session_id: _sessionId(),
      ...payload,
    });

    // sendBeacon when available — survives page unloads better than fetch().
    if (navigator.sendBeacon && !token) {
      const blob = new Blob([body], { type: 'application/json' });
      navigator.sendBeacon(url, blob);
      return;
    }

    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body,
      // do not block on response
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* swallow — analytics must never break UX */
  }
}

export function useAnalytics() {
  const location = useLocation();
  const lastRouteRef = useRef(null);

  useEffect(() => {
    // Skip dupes (StrictMode double-render, hash-only changes)
    const path = location.pathname + (location.search || '');
    if (lastRouteRef.current === path) return;
    lastRouteRef.current = path;

    _postEvent({
      event_type: 'pageview',
      route: path,
      referrer: typeof document !== 'undefined' ? document.referrer || '' : '',
    });
  }, [location.pathname, location.search]);
}

export function trackEvent(name, props = {}) {
  _postEvent({
    event_type: 'custom',
    route: typeof window !== 'undefined' ? window.location.pathname : '',
    props: { name, ...props },
  });
}
