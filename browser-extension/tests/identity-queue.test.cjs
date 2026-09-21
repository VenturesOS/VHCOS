'use strict';

// Offline tests execute the actual queue entry points with asynchronous,
// copy-on-read/write Chrome storage. No server calls or live browser state.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'background.js'), 'utf8').replace(/\r\n/g, '\n');
const start = source.indexOf('function serializeCaptureMutation(work)');
const end = source.indexOf('/**\n * Main drain loop', start);
assert.ok(start >= 0 && end > start, 'production queue entry points exist');
const queueFunctions = source.slice(start, end);
const uuidV4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function harness({ queue = [], limit = 500, readFailures = 0, writeFailures = 0 } = {}) {
  const stored = { captureQueue: structuredClone(queue) };
  let generatedIds = 0;
  const notifications = [];
  const chrome = { runtime: {}, storage: { sync: {}, local: {} } };
  const deliver = (callback, data, error = null) => setImmediate(() => {
    chrome.runtime.lastError = error ? { message: error } : undefined;
    callback(data);
    chrome.runtime.lastError = undefined;
  });
  chrome.storage.sync.get = (_keys, callback) => deliver(callback, { vhc_active_mandate: 'mandate-1' });
  chrome.storage.local.get = (_keys, callback) => {
    const error = readFailures-- > 0 ? 'read failed' : null;
    deliver(callback, structuredClone(stored), error);
  };
  chrome.storage.local.set = (data, callback) => {
    const error = writeFailures-- > 0 ? 'write failed' : null;
    if (!error) Object.assign(stored, structuredClone(data));
    deliver(callback, undefined, error);
  };
  const context = vm.createContext({ chrome, CONFIG: { MAX_CAPTURE_QUEUE_SIZE: limit },
    sanitizeDeep: value => value,
    crypto: { randomUUID: () => { generatedIds++; return randomUUID(); } },
    notifyPopup: value => notifications.push(value),
  });
  vm.runInContext(queueFunctions + '\nglobalThis.api = { enqueueCapture, bulkEnqueue, freezeCapturePayload, isSavedCaptureResult };', context);
  return { api: context.api, stored, notifications, generated: () => generatedIds };
}

test('same, absent and rotating provider identifiers never deduplicate distinct captures', async () => {
  const state = harness();
  const profiles = [
    { name: 'Rahul Delhi', naukri_profile_id: 'reused', location: 'Delhi' },
    { name: 'Rahul Mumbai', naukri_profile_id: 'reused', location: 'Mumbai' },
    { name: 'Missing ID 1' }, { name: 'Missing ID 2', naukri_profile_id: null },
    { name: 'Rotating profile', naukri_profile_id: 'session-1' },
    { name: 'Rotating profile', naukri_profile_id: 'session-2' },
  ];
  const result = await state.api.bulkEnqueue(profiles);
  assert.equal(result.queued, 6);
  assert.equal(result.duplicates, 0);
  assert.equal(result.dropped, 0);
  assert.equal(state.stored.captureQueue.length, 6);
  assert.deepEqual(state.stored.captureQueue.map(item => item.name), profiles.map(item => item.name));
  assert.equal(new Set(state.stored.captureQueue.map(item => item._queueId)).size, 6);
  assert.equal(state.generated(), 6);
  assert.ok(state.stored.captureQueue.every(item => uuidV4.test(item._queueId)));
});

test('identical payloads without an explicit operation ID are distinct operations', async () => {
  const state = harness();
  const payload = { name: 'Same name', naukri_profile_id: 'same-id', naukri_profile_url: 'https://example.invalid/same' };
  const one = await state.api.enqueueCapture(payload);
  const two = await state.api.enqueueCapture(payload);
  assert.equal(one.action, 'queued');
  assert.equal(two.action, 'queued');
  assert.notEqual(one.queueId, two.queueId);
  assert.equal(state.stored.captureQueue.length, 2);
  assert.equal(payload._queueId, undefined, 'caller payload is not mutated');
});

test('only a deliberately reused UUID coalesces and preserves original retry state', async () => {
  const operationId = randomUUID();
  const original = { _queueId: operationId, name: 'Original capture', _attempts: 2, _status: 'retry',
    naukri_profile_id: 'old-session', _queued_at: '2026-09-09T00:00:00.000Z' };
  const state = harness({ queue: [original], limit: 1 });
  const result = await state.api.enqueueCapture({ name: 'Original capture', naukri_profile_id: 'new-session',
    _queueId: operationId.toUpperCase() });
  assert.equal(result.action, 'duplicate');
  assert.equal(result.queueId, operationId);
  assert.equal(state.generated(), 0);
  assert.deepEqual(state.stored.captureQueue, [original]);
});

test('bulk repeated operation IDs coalesce but distinct IDs with identical profiles remain separate', async () => {
  const state = harness();
  const operationA = randomUUID();
  const operationB = randomUUID();
  const result = await state.api.bulkEnqueue([
    { name: 'Same profile', _queueId: operationA },
    { name: 'Same profile', _queueId: operationA },
    { name: 'Same profile', _queueId: operationB },
  ]);
  assert.equal(result.queued, 2);
  assert.equal(result.duplicates, 1);
  assert.equal(result.dropped, 0);
  assert.equal(result.results[1].queueId, operationA);
  assert.equal(result.results[1].action, 'duplicate');
  assert.equal(result.results[2].queueId, operationB);
  assert.deepEqual(state.stored.captureQueue.map(item => item._queueId), [operationA, operationB]);
  assert.ok(state.stored.captureQueue.every(item => item._bulk && item._mandate_id === 'mandate-1'));
});

test('generated queue ID is persisted, returned and remains stable on delivery retry', async () => {
  const state = harness();
  const original = await state.api.enqueueCapture({ name: 'Missing provider ID' });
  assert.match(original.queueId, uuidV4);
  assert.equal(state.stored.captureQueue[0]._queueId, original.queueId);
  const retry = await state.api.enqueueCapture({ name: 'Missing provider ID', _queueId: original.queueId });
  assert.equal(retry.action, 'duplicate');
  assert.equal(retry.queueId, original.queueId);
  assert.equal(state.stored.captureQueue.length, 1);
});

test('simultaneous single and bulk deliveries cannot overwrite another enqueue', async () => {
  const state = harness();
  const results = await Promise.all([
    state.api.enqueueCapture({ name: 'single-1', naukri_profile_id: 'same' }),
    state.api.bulkEnqueue([{ name: 'bulk-1' }, { name: 'bulk-2', naukri_profile_id: 'same' }]),
    state.api.enqueueCapture({ name: 'single-2' }),
  ]);
  assert.ok(results.every(result => result.success));
  assert.equal(state.stored.captureQueue.length, 4);
  assert.deepEqual(state.stored.captureQueue.map(item => item.name).sort(), ['bulk-1', 'bulk-2', 'single-1', 'single-2']);
});

test('queue limits report drops without inferring duplicate identity', async () => {
  const state = harness({ limit: 2 });
  const result = await state.api.bulkEnqueue([
    { name: 'One', naukri_profile_id: null },
    { name: 'Two', naukri_profile_id: null },
    { name: 'Three', naukri_profile_id: null },
  ]);
  assert.equal(result.queued, 2);
  assert.equal(result.duplicates, 0);
  assert.equal(result.dropped, 1);
  assert.equal(result.total, 2);
  assert.equal(result.results[2].error, 'Queue full');
  assert.equal(state.stored.captureQueue.length, 2);
});

test('invalid payloads and provider-like values in operation-ID field are rejected explicitly', async () => {
  const state = harness();
  for (const value of [null, undefined, [], 'profile', { name: 'Person', _queueId: 'naukri-provider-id' }]) {
    const result = await state.api.enqueueCapture(value);
    assert.equal(result.success, false);
    assert.ok(result.error);
  }
  assert.equal(state.stored.captureQueue.length, 0);
  assert.equal(state.generated(), 0);
});

test('storage write failure returns a retryable operation ID and does not poison later writes', async () => {
  const state = harness({ writeFailures: 1 });
  const failed = await state.api.enqueueCapture({ name: 'Operation' });
  assert.equal(failed.success, false);
  assert.equal(failed.error, 'Storage write failed');
  assert.match(failed.queueId, uuidV4);
  assert.equal(state.stored.captureQueue.length, 0);
  const retry = await state.api.enqueueCapture({ name: 'Operation', _queueId: failed.queueId });
  assert.equal(retry.success, true);
  assert.equal(retry.queueId, failed.queueId);
  assert.equal(state.stored.captureQueue[0]._queueId, failed.queueId);
});

test('storage read failure does not replace existing queue contents', async () => {
  const original = { _queueId: randomUUID(), name: 'Already queued' };
  const state = harness({ queue: [original], readFailures: 1 });
  const failed = await state.api.enqueueCapture({ name: 'New capture' });
  assert.equal(failed.success, false);
  assert.equal(failed.error, 'Storage read failed');
  assert.deepEqual(state.stored.captureQueue, [original]);
});

test('prepared payload is persisted once and reused after restart or changed extraction', async () => {
  const item = { _queueId: randomUUID(), name: 'Original' };
  const state = harness({ queue: [item] });
  const frozen = await state.api.freezeCapturePayload(item, { name: 'Original', skills: ['Java'] });
  assert.equal(frozen.capture_request_id, item._queueId);
  frozen.skills.push('Changed by caller');
  const restartedItem = { _queueId: item._queueId };
  const retried = await state.api.freezeCapturePayload(restartedItem, { name: 'Changed extraction' });
  assert.equal(retried.name, 'Original');
  assert.deepEqual(Array.from(retried.skills), ['Java']);
  assert.equal(state.stored.captureQueue[0]._capturePayload.name, 'Original');
});

test('failed payload persistence prevents preparation acknowledgement', async () => {
  const item = { _queueId: randomUUID() };
  const state = harness({ queue: [item], writeFailures: 1 });
  await assert.rejects(state.api.freezeCapturePayload(item, { name: 'Profile' }), /write failed/);
  assert.equal(item._capturePayload, undefined);
  assert.equal(state.stored.captureQueue[0]._capturePayload, undefined);
});

test('concurrent preparation cannot replace the first frozen body', async () => {
  const id = randomUUID();
  const state = harness({ queue: [{ _queueId: id }] });
  const results = await Promise.all([
    state.api.freezeCapturePayload({ _queueId: id }, { name: 'First' }),
    state.api.freezeCapturePayload({ _queueId: id }, { name: 'Second' }),
  ]);
  assert.deepEqual(results.map(row => row.name), ['First', 'First']);
});

test('only saved observations or reviewed links acknowledge a capture', () => {
  const { api } = harness();
  const saved = { success: true, action: 'pending_review', candidate_id: null, observation_id: randomUUID() };
  assert.equal(api.isSavedCaptureResult(saved), true);
  assert.equal(api.isSavedCaptureResult({ ...saved, action: 'exists', candidate_id: 'person-1' }), true);
  for (const patch of [{ observation_id: null }, { candidate_id: 'unreviewed-person' },
    { success: false }, { action: 'created' }, { action: 'exists', candidate_id: '' }]) {
    assert.equal(api.isSavedCaptureResult({ ...saved, ...patch }), false);
  }
});

test('removed queue items and conflicting frozen operation IDs cannot be posted', async () => {
  const id = randomUUID();
  await assert.rejects(harness().api.freezeCapturePayload({ _queueId: id }, {}), /no longer queued/);
  const state = harness({ queue: [{ _queueId: id, _capturePayload: { capture_request_id: randomUUID() } }] });
  await assert.rejects(state.api.freezeCapturePayload({ _queueId: id }, {}), /does not match/);
});
