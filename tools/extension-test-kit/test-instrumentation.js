/* Test-only wrappers: the real resolver/queue implementations still run. */
(() => {
  let tail = Promise.resolve();
  function record(row) {
    tail = tail.then(async () => {
      const stored = await chrome.storage.local.get(['vhc_test_metrics']);
      const rows = Array.isArray(stored.vhc_test_metrics) ? stored.vhc_test_metrics : [];
      await chrome.storage.local.set({ vhc_test_metrics: [...rows, {
        ...row, at: new Date().toISOString(),
      }].slice(-300) });
    }).catch(() => {});
    return tail;
  }
  const originalCheck = checkExistingCandidates;
  checkExistingCandidates = async function(candidates) {
    const started = performance.now();
    try {
      const result = await originalCheck(candidates);
      const counts = {};
      for (const row of result.results || []) {
        const decision = ['confirmed_duplicate', 'probable_match', 'ambiguous', 'insufficient_data',
          'no_match_found', 'unavailable'].includes(row.decision) ? row.decision : 'other';
        counts[decision] = (counts[decision] || 0) + 1;
      }
      const status = ['ready', 'disabled', 'unavailable'].includes(result.service_status)
        ? result.service_status : 'unknown';
      await record({ kind: 'matching', duration_ms: Math.round(performance.now() - started),
        cards: Array.isArray(candidates) ? candidates.length : 0, status, decisions: counts });
      return result;
    } catch (error) {
      await record({ kind: 'matching', duration_ms: Math.round(performance.now() - started), status: 'error' });
      throw error;
    }
  };
  const originalCapture = postCaptureAsync;
  postCaptureAsync = async function(auth, payload) {
    const started = performance.now();
    try {
      const result = await originalCapture(auth, payload);
      const status = result?._result?.success === true ? 'saved' : 'not_saved';
      await record({ kind: 'capture_submission', duration_ms: Math.round(performance.now() - started), status });
      return result;
    } catch (error) {
      await record({ kind: 'capture_submission', duration_ms: Math.round(performance.now() - started), status: 'error' });
      throw error;
    }
  };
})();
