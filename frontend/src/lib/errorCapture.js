/**
 * Global error capture service.
 * Auto-captures: JS errors, unhandled promise rejections, API failures.
 * Sends them to POST /api/system-errors/frontend.
 */

const API_URL = process.env.REACT_APP_BACKEND_URL;

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
  // Only capture server errors and auth failures, not client validation
  if (status < 400) return;
  // Skip rate limit and auth errors (expected behavior)
  if (status === 401 || status === 429) return;

  queueError({
    error_message: `API ${method} ${url} returned ${status}: ${responseData?.detail || JSON.stringify(responseData).slice(0, 200)}`,
    stack_trace: '',
    component: 'api_error',
    page_url: window.location.href,
    browser_info: navigator.userAgent,
    user_action: `${method} ${url}`,
  });
}
