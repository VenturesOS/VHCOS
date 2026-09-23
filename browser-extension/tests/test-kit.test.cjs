const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assets = path.join(__dirname, '../../tools/extension-test-kit');

function runtime(config = {}) {
  const calls = [];
  const context = vm.createContext({ URL, VHC_TEST_CONFIG: config,
    fetch: async (...args) => { calls.push(args); return { ok: true }; },
  });
  vm.runInContext(fs.readFileSync(path.join(assets, 'test-runtime.js'), 'utf8'), context);
  return { context, calls };
}

test('test package accepts preview/local origins and blocks production and deceptive hosts', () => {
  const { context } = runtime();
  for (const url of ['https://example.preview.emergentagent.com', 'https://example.emergent.host', 'http://localhost:8001']) {
    assert.equal(context.vhcTestBackendAllowed(url), true, url);
  }
  for (const url of ['https://api.ventureshrd.com', 'https://vhc.in',
    'https://talent-relay.siddharth-ab8.workers.dev', 'https://emergent.host.evil.test',
    'https://user:password@preview.emergent.host', 'http://preview.emergent.host', 'not-a-url']) {
    assert.equal(context.vhcTestBackendAllowed(url), false, url);
  }
});

test('test API requests cannot reach production or follow an unverified redirect', async () => {
  const { context, calls } = runtime();
  await assert.rejects(context.fetch('https://api.ventureshrd.com/api/auth/login'), /TEST BUILD/);
  await assert.rejects(context.fetch('https://other.test/api/extension/capture/async'), /TEST BUILD/);
  assert.equal(calls.length, 0);
  await context.fetch('https://test.preview.emergentagent.com/api/health', { redirect: 'follow' });
  assert.equal(calls[0][1].redirect, 'error');
});

test('an explicit custom preview origin is exact and never overrides known production', () => {
  const { context } = runtime({ backendOrigin: 'https://stage.example.test' });
  assert.equal(context.vhcTestBackendAllowed('https://stage.example.test/api/health'), true);
  assert.equal(context.vhcTestBackendAllowed('https://other.stage.example.test'), false);
  const prod = runtime({ backendOrigin: 'https://api.ventureshrd.com' });
  assert.equal(prod.context.vhcTestBackendAllowed('https://api.ventureshrd.com'), false);
});

function instrument({ check, capture } = {}) {
  const storage = {};
  let tick = 0;
  const context = vm.createContext({ Date, performance: { now: () => tick += 10 },
    chrome: { storage: { local: {
      get: async () => structuredClone(storage),
      set: async value => Object.assign(storage, structuredClone(value)),
    } } },
    checkExistingCandidates: check || (async () => ({ service_status: 'ready', results: [{ decision: 'ambiguous', name: 'Private Name' }] })),
    postCaptureAsync: capture || (async () => ({ _result: { success: true, observation_id: 'private-id' } })),
  });
  vm.runInContext(fs.readFileSync(path.join(assets, 'test-instrumentation.js'), 'utf8'), context);
  return { context, storage };
}

test('matching wrapper preserves result and records only counts and timing', async () => {
  const expected = { service_status: 'ready', results: [{ decision: 'probable_match', candidate_id: 'secret-id', name: 'Private Person' }] };
  const { context, storage } = instrument({ check: async () => expected });
  const result = await context.checkExistingCandidates([{ name: 'Private Person', email: 'secret@person.test' }]);
  assert.equal(result, expected);
  assert.equal(storage.vhc_test_metrics[0].cards, 1);
  assert.equal(storage.vhc_test_metrics[0].decisions.probable_match, 1);
  assert.equal(storage.vhc_test_metrics[0].duration_ms, 10);
  assert.doesNotMatch(JSON.stringify(storage), /Private|secret|person.test/);
});

test('capture errors propagate without recording profile, token or error text', async () => {
  const error = new Error('secret error with private profile');
  const { context, storage } = instrument({ capture: async () => { throw error; } });
  await assert.rejects(context.postCaptureAsync({ token: 'secret-token' }, { name: 'Private' }), value => value === error);
  assert.equal(storage.vhc_test_metrics[0].status, 'error');
  assert.doesNotMatch(JSON.stringify(storage), /secret|private|Private|token/);
});

test('concurrent operations retain all measurements within the bounded report', async () => {
  const { context, storage } = instrument();
  await Promise.all(Array.from({ length: 305 }, () => context.checkExistingCandidates([{}])));
  assert.equal(storage.vhc_test_metrics.length, 300);
  assert.ok(storage.vhc_test_metrics.every(row => row.kind === 'matching'));
});
