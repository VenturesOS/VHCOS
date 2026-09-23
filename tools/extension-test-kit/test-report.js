(() => {
  const get = id => document.getElementById(id);
  const number = value => Number.isFinite(value) && value >= 0 ? value : 0;
  function metrics(rows) {
    return rows.filter(row => row && ['matching', 'capture_submission'].includes(row.kind)).map(row => ({
      kind: row.kind, duration_ms: number(row.duration_ms), cards: number(row.cards),
      status: ['ready', 'disabled', 'unavailable', 'unknown', 'error', 'saved', 'not_saved'].includes(row.status) ? row.status : 'unknown',
      decisions: Object.fromEntries(['confirmed_duplicate', 'probable_match', 'ambiguous', 'insufficient_data',
        'no_match_found', 'unavailable', 'other'].map(key => [key, number(row.decisions?.[key])])),
    }));
  }
  function summary(rows, kind) {
    const selected = rows.filter(row => row.kind === kind);
    const timings = selected.map(row => row.duration_ms).sort((a, b) => a - b);
    const percentile = p => timings.length ? timings[Math.ceil(timings.length * p) - 1] : null;
    return { calls: selected.length, median_ms: percentile(.5), p95_ms: percentile(.95),
      errors: selected.filter(row => row.status === 'error').length,
      unavailable: selected.filter(row => ['disabled', 'unavailable', 'unknown', 'not_saved'].includes(row.status)).length };
  }
  async function report() {
    const stored = await chrome.storage.local.get(['vhc_test_metrics']);
    const rows = metrics(Array.isArray(stored.vhc_test_metrics) ? stored.vhc_test_metrics : []);
    const decisions = {};
    for (const row of rows.filter(row => row.kind === 'matching')) {
      for (const [key, value] of Object.entries(row.decisions)) decisions[key] = (decisions[key] || 0) + value;
    }
    const reviewed = Object.fromEntries(['correct', 'wrong', 'missed', 'uncertain'].map(key => [key,
      Math.min(100000, Math.floor(number(Number(get(key).value))))]));
    return { generated_at: new Date().toISOString(), build: globalThis.VHC_TEST_CONFIG,
      matching: summary(rows, 'matching'), capture_submission: summary(rows, 'capture_submission'),
      matching_outcomes: decisions, manually_reviewed: reviewed, samples: rows,
      note: 'Local observations and manual sample labels; not proof of production accuracy. No profile or authentication data included.' };
  }
  async function refresh() {
    const data = await report();
    const table = document.createElement('table');
    const header = table.insertRow();
    for (const title of ['Operation', 'Calls', 'Median', 'P95', 'Errors', 'Unavailable / disabled']) {
      const cell = document.createElement('th'); cell.textContent = title; header.appendChild(cell);
    }
    for (const [title, row] of [['Matching', data.matching], ['Capture submit + polling', data.capture_submission]]) {
      const tr = table.insertRow();
      for (const value of [title, row.calls, row.median_ms === null ? '—' : `${row.median_ms} ms`,
        row.p95_ms === null ? '—' : `${row.p95_ms} ms`, row.errors, row.unavailable]) tr.insertCell().textContent = value;
    }
    get('timing').replaceChildren(table);
    get('decisions').textContent = JSON.stringify(data.matching_outcomes, null, 2);
    get('build').textContent = `Source commit ${data.build.commit.slice(0, 12)} · ${chrome.runtime.getManifest().version_name}`;
    const auth = await chrome.storage.sync.get(['vhc_api_url']);
    get('connection').textContent = auth.vhc_api_url ? `Configured preview: ${new URL(auth.vhc_api_url).origin}` : 'Log into the test extension to configure your preview.';
  }
  get('refresh').addEventListener('click', () => refresh().catch(() => { get('status').textContent = 'Could not read the local report.'; }));
  get('health').addEventListener('click', async () => {
    get('health').disabled = true;
    try {
      const { vhc_api_url } = await chrome.storage.sync.get(['vhc_api_url']);
      if (!vhc_api_url || !vhcTestBackendAllowed(vhc_api_url)) throw new Error('preview_not_configured');
      const response = await fetch(vhc_api_url.replace(/\/$/, '') + '/api/health', { signal: AbortSignal.timeout(10000) });
      const data = await response.json();
      get('status').textContent = response.ok && data.status === 'healthy' && data.import_failures === 0
        ? 'Preview backend is healthy. Now test matching on a candidate search page.'
        : 'Backend responded, but health or route imports need checking in Emergent.';
    } catch (_) { get('status').textContent = 'Could not verify the preview. Check the URL, login and backend in Emergent.'; }
    finally { get('health').disabled = false; }
  });
  get('export').addEventListener('click', async () => {
    try {
      const data = await report();
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a'); link.href = url; link.download = 'VHC-extension-test-report.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (_) { get('status').textContent = 'Report download failed. Refresh and retry.'; }
  });
  refresh().catch(() => { get('status').textContent = 'Open this report through the installed test extension.'; });
})();
