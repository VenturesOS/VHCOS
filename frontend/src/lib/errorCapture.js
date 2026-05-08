/**
 * Global error capture service.
 * Auto-captures: JS errors, unhandled promise rejections, API failures.
 * Sends them to POST /api/system-errors/frontend.
 */

const API_URL = '';

let errorQueue = [];
let flushTimer = null;

function getAuthHeader() {
  try {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch { return {}; }
}

function sendErrors() {
  if (errorQueue.length === 0) return;
  const batch = [...errorQueue];
  errorQueue = [];

  batch.forEach((err) => {
    fetch(`${API_URL}/api/system-errors/frontend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
      body: JSON.stringify(err),
    }).catch(() => {}); // Silent fail — don't create error loops
  });
}

function queueError(error) {
  errorQueue.push(error);
  if (!flushTimer) {
    flushTimer = setTimeout(() => {
      sendErrors();
      flushTimer = null;
    }, 2000); // Batch errors every 2s
  }
}

export function initErrorCapture() {
  // 1. Capture unhandled JS errors
  window.addEventListener('error', (event) => {
    queueError({
      error_message: event.message || 'Unknown error',
      stack_trace: event.error?.stack || `${event.filename}:${event.lineno}:${event.colno}`,
      component: 'window.onerror',
      page_url: window.location.href,
      browser_info: navigator.userAgent,
    });
  });

  // 2. Capture unhandled promise rejections
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    queueError({
      error_message: reason?.message || String(reason) || 'Unhandled promise rejection',
      stack_trace: reason?.stack || '',
      component: 'unhandledrejection',
      page_url: window.location.href,
      browser_info: navigator.userAgent,
    });
  });
}

/**
 * Call this from API interceptors when a request fails with 4xx/5xx.
 */
export function captureApiError(method, url, status, responseData) {
  // Only capture server errors, not client validation or auth issues
  if (status < 400) return;
  // Skip auth errors (401/403) and rate limits (429) — expected behavior, not bugs
  if (status === 401 || status === 403 || status === 429) return;
  // Skip 422 validation errors (client-side data issues, not system errors)
  if (status === 422) return;
  // Skip transient 502/503/504 — these are almost always gunicorn restart windows
  // or upstream cold-start latency, NOT real bugs. The frontend retries them on
  // the next poll cycle. Logging them just floods the maintenance report.
  if (status === 502 || status === 503 || status === 504) return;
  // Skip high-frequency polling endpoints — even when they fail with another 5xx,
  // they're noise for the bug-report board.
  const POLL_ENDPOINTS = [
    '/notifications/unread-count',
    '/admin/llm/live-banner',
    '/admin/llm/failure-stats',
    '/admin/runpod/health',
    '/extension/my-version-status',
    '/candidate-bank/data-quality/bulk-re-enrich/status',
  ];
  if (url && POLL_ENDPOINTS.some((p) => url.includes(p))) return;

  queueError({
    error_message: `API ${method} ${url} returned ${status}: ${responseData?.detail || JSON.stringify(responseData).slice(0, 200)}`,
    stack_trace: '',
    component: 'api_error',
    page_url: window.location.href,
    browser_info: navigator.userAgent,
    user_action: `${method} ${url}`,
  });
}
