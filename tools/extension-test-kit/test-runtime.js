/* Included only in the test package; never loaded by the production manifest. */
(() => {
  const config = globalThis.VHC_TEST_CONFIG || {};
  const production = ['ventureshrd.com', 'vhc.in', 'talent-relay.siddharth-ab8.workers.dev'];
  const previews = ['emergentagent.com', 'emergent.host', 'emergent.sh'];
  const belongs = (host, domain) => host === domain || host.endsWith('.' + domain);
  function allowed(value) {
    try {
      const url = new URL(value);
      if (url.username || url.password || production.some(host => belongs(url.hostname, host))) return false;
      const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
      if (local) return ['http:', 'https:'].includes(url.protocol);
      return url.protocol === 'https:' && (previews.some(host => belongs(url.hostname, host)) ||
        Boolean(config.backendOrigin && url.origin === config.backendOrigin));
    } catch (_) { return false; }
  }
  globalThis.vhcTestBackendAllowed = allowed;
  const originalFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = (input, init = {}) => {
    const value = typeof input === 'string' || input instanceof URL ? String(input) : input.url;
    const url = new URL(value);
    // API calls use preview/local origins only. Third-party profile/CV reads
    // keep the original behavior. No credentials or response bodies are logged.
    if ((url.pathname.startsWith('/api/') || production.some(host => belongs(url.hostname, host))) && !allowed(url.href)) {
      return Promise.reject(new Error('TEST BUILD: use your Emergent preview backend URL, not the production portal.'));
    }
    return originalFetch(input, { ...init, redirect: 'error' });
  };
})();
