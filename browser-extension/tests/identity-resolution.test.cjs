'use strict';

// Offline behavioral tests execute the production functions in a VM. No API,
// browser account, generated bundle, or duplicate matcher implementation needed.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const background = fs.readFileSync(path.join(__dirname, '..', 'background.js'), 'utf8').replace(/\r\n/g, '\n');
const content = fs.readFileSync(path.join(__dirname, '..', 'content.js'), 'utf8').replace(/\r\n/g, '\n');
const version = 'identity-resolution-1';
const auth = { token: 'offline-test', apiUrl: 'https://example.invalid', userEmail: 'tester@example.invalid' };
const candidate = { name: 'Rahul Sharma', location: 'Delhi', profile_url: 'https://resdex.naukri.com/preview?candidateId=abc' };
const history = [{ name: candidate.name, candidate_id: 'stored-1', profileUrl: candidate.profile_url,
  action: 'created', history_scope: 'https://example.invalid|tester@example.invalid' }];

function section(text, start, end) {
  const from = text.indexOf(start);
  const to = text.indexOf(end, from);
  assert.ok(from >= 0 && to > from, 'production function boundaries exist');
  return text.slice(from, to);
}
function row(index, decision = 'confirmed_duplicate', extra = {}) {
  return { index, exists: decision === 'confirmed_duplicate', decision, candidate_id: 'db-' + index,
    matcher_version: version, score_kind: 'evidence_points', match_score: 5,
    matched_signals: ['source_profile'], conflicts: [], ...extra };
}
function envelope(results, extra = {}) {
  return { matcher_version: version, service_status: 'ready', results, audit_id: 'audit-test', ...extra };
}
function response(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}
function backgroundHarness(overrides = {}) {
  const context = vm.createContext({
    URL, AbortController, setTimeout, clearTimeout, console,
    getAuth: async () => auth, refreshAccessToken: async () => false,
    chrome: { runtime: {}, storage: { local: { get: (_keys, callback) => callback({ captureHistory: history }) } } },
    fetch: async (_url, options) => response(envelope(JSON.parse(options.body).candidates.map((_, i) => row(i)))),
    ...overrides,
  });
  vm.runInContext(section(background, '// Identity badges trust', '/**\n * Smart polling loop') +
    '\nglobalThis.api = { checkExistingCandidates, validateIdentityResponse, checkLocalHistory };', context);
  return context;
}

test('201 candidates are chunked <=50, all results remap correctly, audit indices stay batch-local', async () => {
  const batches = [];
  let active = 0;
  let peak = 0;
  const harness = backgroundHarness({ fetch: async (_url, options) => {
    const batch = JSON.parse(options.body).candidates;
    batches.push(batch.length);
    peak = Math.max(peak, ++active);
    await Promise.resolve();
    active--;
    return response(envelope(batch.map((card, i) => row(i, 'confirmed_duplicate', { candidate_id: card.name })),
      { audit_id: 'batch-' + batch[0].name }));
  } });
  const cards = Array.from({ length: 201 }, (_, index) => ({ ...candidate, name: String(index) }));
  const actual = await harness.api.checkExistingCandidates(cards);
  assert.deepEqual(batches, [50, 50, 50, 50, 1]);
  assert.ok(peak <= 3);
  assert.equal(actual.results.length, cards.length);
  actual.results.forEach((result, index) => {
    assert.equal(result.index, index);
    assert.equal(result.candidate_id, String(index));
    assert.equal(result.audit_index, index % 50);
    assert.equal(result.audit_id, 'batch-' + (index - index % 50));
    assert.equal(result.exists, true);
  });
});

test('unversioned V1/V2 shaped responses cannot confirm a duplicate', async () => {
  const harness = backgroundHarness({ fetch: async () => response({ results: [row(0)] }) });
  const result = (await harness.api.checkExistingCandidates([candidate])).results[0];
  assert.equal(result.decision, 'unavailable');
  assert.equal(result.exists, false);
  assert.equal(result.provenance, undefined);
});

test('missing, duplicate, inconsistent, and unknown result rows become unavailable', () => {
  const harness = backgroundHarness();
  const values = [row(0), row(0), row(1, 'probable_match', { exists: true }), row(2, 'new_kind'),
    row(3, 'confirmed_duplicate', { conflicts: ['verified_id_conflict'] }), row(4, 'confirmed_duplicate', { match_score: NaN })];
  const result = harness.api.validateIdentityResponse(Array(6).fill(candidate), envelope(values));
  assert.equal(result.length, 6);
  assert.ok(result.every(value => value.decision === 'unavailable' && !value.exists));
});

test('authoritative no-match, ambiguity and insufficient evidence never inherit a local green match', async () => {
  const harness = backgroundHarness({ fetch: async () => response(envelope([
    row(0, 'no_match_found'), row(1, 'ambiguous'), row(2, 'insufficient_data'),
  ])) });
  const actual = await harness.api.checkExistingCandidates([candidate, candidate, candidate]);
  assert.deepEqual(Array.from(actual.results, result => result.decision),
    ['no_match_found', 'ambiguous', 'insufficient_data']);
  assert.ok(actual.results.every(result => !result.exists && result.provenance === 'backend'));
});

test('network failure cannot match from reused or rotated profile URLs in history', async () => {
  const harness = backgroundHarness({ fetch: async () => { throw new TypeError('offline'); } });
  const actual = await harness.api.checkExistingCandidates([candidate, { ...candidate, profile_url: 'https://resdex.naukri.com/preview?sid=abc' }]);
  assert.equal(actual.results[0].decision, 'unavailable');
  assert.equal(actual.results[0].provenance, undefined);
  assert.equal(actual.results[0].exists, false);
  assert.equal(actual.results[1].decision, 'unavailable');
  assert.equal(actual.service_status, 'unavailable');
  assert.equal(harness.api.checkLocalHistory([candidate], history, { ...auth, userEmail: 'other@example.invalid' })[0].decision, 'unavailable');
  assert.equal(harness.api.checkLocalHistory([candidate], [{ ...history[0], history_scope: null }], auth)[0].decision, 'unavailable');
});

test('disabled service and 403 forbid local fallback even when history matches', async () => {
  for (const fetch of [async () => response(envelope([], { service_status: 'disabled' })), async () => response({}, 403)]) {
    const actual = await backgroundHarness({ fetch }).api.checkExistingCandidates([candidate]);
    assert.equal(actual.service_status, 'disabled');
    assert.equal(actual.results[0].decision, 'unavailable');
    assert.equal(actual.results[0].provenance, undefined);
  }
});

test('a rejected auth refresh cannot fall through to local history', async () => {
  const actual = await backgroundHarness({ fetch: async () => response({}, 401),
    refreshAccessToken: async () => { throw new Error('refresh offline'); },
  }).api.checkExistingCandidates([candidate]);
  assert.equal(actual.service_status, 'disabled');
  assert.equal(actual.results[0].provenance, undefined);
});

test('simultaneous expired batches refresh once and preserve the new contract', async () => {
  let refreshes = 0;
  let refreshed = false;
  const harness = backgroundHarness({
    getAuth: async () => ({ ...auth, token: refreshed ? 'new-token' : 'old-token' }),
    refreshAccessToken: async () => { refreshes++; refreshed = true; return true; },
    fetch: async (_url, options) => options.headers.Authorization === 'Bearer old-token'
      ? response({}, 401)
      : response(envelope(JSON.parse(options.body).candidates.map((_, i) => row(i)))),
  });
  const actual = await harness.api.checkExistingCandidates(Array(101).fill(candidate));
  assert.equal(refreshes, 1);
  assert.ok(actual.results.every(result => result.decision === 'confirmed_duplicate'));
});

test('one denied batch invalidates every batch in the same logical check', async () => {
  const harness = backgroundHarness({ fetch: async (_url, options) => {
    const cards = JSON.parse(options.body).candidates;
    if (cards[0].name === 'denied') return response({}, 403);
    return response(envelope(cards.map((_, i) => row(i))));
  } });
  const cards = Array(51).fill(candidate);
  cards[50] = { ...candidate, name: 'denied' };
  const actual = await harness.api.checkExistingCandidates(cards);
  assert.ok(actual.results.every(result => !result.exists && result.service_status === 'disabled'));
});

function makeCard(info = null) {
  const classes = new Set();
  return { info, isConnected: true, textContent: 'lazy card', removedBadges: 0,
    getAttribute: () => '',
    querySelectorAll: () => [{ remove() { } }],
    classList: { add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value) },
  };
}
function contentHarness(cards, send) {
  let now = 0;
  let timerId = 0;
  const timers = new Map();
  const rendered = [];
  const sent = [];
  const context = vm.createContext({
    console, URL, isExtensionValid: () => true, findCardElements: () => cards,
    scrapeSearchCardInfo: card => card.info,
    Date: class extends Date { static now() { return now; } },
    setTimeout: (callback, delay) => { timers.set(++timerId, { callback, due: now + delay }); return timerId; },
    clearTimeout: id => timers.delete(id),
    markCardAsExisting: (card, info) => {
      rendered.push({ card, info });
      if (info.decision === 'confirmed_duplicate') card.classList.add('vhc-dimmed-card');
    },
    chrome: { storage: { onChanged: { addListener: callback => { context.storageChanged = callback; } } }, runtime: { sendMessage: (request, callback) => {
      sent.push(request);
      if (send) send(request, callback, context);
      else callback(envelope(request.candidates.map((_, i) => row(i))));
    } } },
  });
  vm.runInContext(section(content, '  const identityCardStates', '  /**\n   * Helper to find candidate card elements') +
    '\nglobalThis.api = { checkAndMarkExistingProfiles, getState: card => identityCardStates.get(card) };', context);
  return { context, api: context.api, timers, rendered, sent, advance: value => { now += value; } };
}

test('lazy cards retry after extraction arrives and duplicate scans do not repeat completed work', async () => {
  const card = makeCard();
  const harness = contentHarness([card]);
  await harness.api.checkAndMarkExistingProfiles();
  assert.equal(harness.api.getState(card).status, 'retry');
  assert.equal(harness.sent.length, 0);
  card.info = { name: 'Rahul Sharma', profileUrl: candidate.profile_url, source: 'naukri', source_id_kind: 'profile-url', experience_years: 0 };
  await harness.api.checkAndMarkExistingProfiles();
  await harness.api.checkAndMarkExistingProfiles();
  assert.equal(harness.sent.length, 1);
  assert.equal(harness.sent[0].candidates[0].experience_years, 0);
  assert.equal(harness.sent[0].candidates[0].profile_url, candidate.profile_url);
  assert.equal(harness.api.getState(card).status, 'done');
});

test('null and runtime-error replies retry with a finite budget', async () => {
  for (const runtimeError of [false, true]) {
    const card = makeCard({ name: 'Rahul', profileUrl: candidate.profile_url });
    const harness = contentHarness([card], (_request, callback, context) => {
      context.chrome.runtime.lastError = runtimeError ? { message: 'port closed' } : null;
      callback(null);
      context.chrome.runtime.lastError = null;
    });
    for (let attempt = 0; attempt < 8; attempt++) {
      harness.advance(20000);
      await harness.api.checkAndMarkExistingProfiles();
    }
    assert.equal(harness.sent.length, 5);
    assert.equal(harness.api.getState(card).status, 'exhausted');
    assert.ok(!card.classList.contains('vhc-dimmed-card'));
  }
});

test('a partial retrieval query failure is retried instead of being cached as final context', async () => {
  const card = makeCard({ name: 'Rahul Sharma', profileUrl: candidate.profile_url });
  let calls = 0;
  const harness = contentHarness([card], (_request, callback) => {
    calls++;
    callback(envelope([calls === 1
      ? row(0, 'ambiguous', { reason_codes: ['retrieval_incomplete', 'query_failed:name_company'], retrieval_complete: false })
      : row(0, 'no_match_found', { candidate_id: null, top_match: null, match_score: 0 })]));
  });
  await harness.api.checkAndMarkExistingProfiles();
  assert.equal(harness.api.getState(card).status, 'retry');
  harness.advance(20000);
  await harness.api.checkAndMarkExistingProfiles();
  assert.equal(calls, 2);
  assert.equal(harness.api.getState(card).status, 'done');
});

test('recycled cards invalidate an in-flight match and recheck their new identity', async () => {
  const callbacks = [];
  const card = makeCard({ name: 'Rahul', location: 'Delhi', profileUrl: candidate.profile_url });
  const harness = contentHarness([card], (_request, callback) => callbacks.push(callback));
  const first = harness.api.checkAndMarkExistingProfiles();
  await harness.api.checkAndMarkExistingProfiles();
  assert.equal(callbacks.length, 1, 'pending scans deduplicate');
  card.info = { ...card.info, location: 'Mumbai' };
  callbacks.shift()(envelope([row(0)]));
  await first;
  assert.equal(harness.rendered.length, 0, 'old response never badges the recycled person');
  const second = harness.api.checkAndMarkExistingProfiles();
  callbacks.shift()(envelope([row(0, 'ambiguous')]));
  await second;
  assert.equal(harness.sent.length, 2);
  assert.equal(harness.rendered[0].info.decision, 'ambiguous');
});

test('a failed recheck removes stale green badges; a disabled check does not retry', async () => {
  const card = makeCard({ name: 'Rahul', location: 'Delhi', profileUrl: candidate.profile_url });
  let count = 0;
  const harness = contentHarness([card], (_request, callback) => {
    if (++count === 1) callback(envelope([row(0)]));
    else callback(envelope([{ index: 0, exists: false, decision: 'unavailable', service_status: 'disabled' }]));
  });
  await harness.api.checkAndMarkExistingProfiles();
  assert.equal(card.classList.contains('vhc-dimmed-card'), true);
  card.info = { ...card.info, location: 'Mumbai' };
  await harness.api.checkAndMarkExistingProfiles();
  assert.equal(card.classList.contains('vhc-dimmed-card'), false);
  assert.equal(harness.api.getState(card).status, 'done');
});

test('actual scraper distinguishes data-target-id, profile URL parameters, and session IDs', () => {
  const context = vm.createContext({ URL, PLATFORM: 'naukri', cleanText: text => (text || '').trim() });
  vm.runInContext(section(content, '  function scrapeSearchCardInfo', '  function safeIdentityLink') +
    '\nglobalThis.scrape = scrapeSearchCardInfo;', context);
  function scrape(query, targetId = '') {
    return context.scrape({
      getAttribute: key => key === 'data-target-id' ? targetId : '',
      querySelector: selector => selector.startsWith('a.candidate-name, a.candidate-profile-summary')
        ? { href: 'https://resdex.naukri.com/preview?' + query }
        : selector.startsWith('a.candidate-name, [class*="candidateName"]') ? { innerText: 'Rahul Sharma' } : null,
      querySelectorAll: () => [],
    });
  }
  assert.equal(scrape('pid=session&sid=other').naukri_id, null);
  assert.equal(scrape('pid=session&sid=other').source_id_kind, 'unverified');
  assert.equal(scrape('candidateId=profile123').source_id_kind, 'unverified');
  assert.equal(scrape('candidateId=profile123').naukri_id, null);
  assert.equal(scrape('profileId=changed-after-hours').naukri_id, null);
  assert.equal(scrape('sid=session', 'real-profile-id').source_id_kind, 'data-target-id');
  assert.equal(scrape('sid=session', 'real-profile-id').naukri_id, 'real-profile-id');
});

test('capture-history changes recheck unchanged cards and account changes discard old requests', async () => {
  const card = makeCard({ name: 'Rahul', location: 'Delhi', profileUrl: candidate.profile_url });
  const harness = contentHarness([card]);
  await harness.api.checkAndMarkExistingProfiles();
  harness.context.storageChanged({ captureHistory: { newValue: history } }, 'local');
  assert.equal(card.classList.contains('vhc-dimmed-card'), false);
  assert.equal(harness.api.getState(card), undefined);
  await harness.api.checkAndMarkExistingProfiles();
  assert.equal(harness.sent.length, 2);
  harness.context.storageChanged({ vhc_user: { newValue: { email: 'new@example.invalid' } } }, 'sync');
  assert.equal(card.classList.contains('vhc-dimmed-card'), false);
  assert.equal(harness.api.getState(card), undefined);
});

test('ordinary token refresh does not invalidate completed cards', async () => {
  const card = makeCard({ name: 'Rahul', profileUrl: candidate.profile_url });
  const harness = contentHarness([card]);
  await harness.api.checkAndMarkExistingProfiles();
  harness.context.storageChanged({ vhc_token: { oldValue: 'expired', newValue: 'fresh' } }, 'sync');
  assert.equal(harness.api.getState(card).status, 'done');
  harness.context.storageChanged({ vhc_token: { oldValue: 'expired' } }, 'sync');
  assert.equal(harness.api.getState(card), undefined);
});

test('trusted backend source identity can retain soft conflicts caused by a move', () => {
  const harness = backgroundHarness();
  const actual = harness.api.validateIdentityResponse([candidate], envelope([
    row(0, 'confirmed_duplicate', { conflicts: ['location_differs'] }),
  ]));
  assert.equal(actual[0].exists, true);
  assert.equal(actual[0].decision, 'confirmed_duplicate');
});

test('extension updates retain history, queues and settings; first install initializes them', () => {
  const writes = [];
  let listener;
  const context = vm.createContext({ console: { log() {} }, VERSION: 'test',
    CONFIG: { SYNC_ALARM_MINUTES: 1, SESSION_PING_MINUTES: 10 }, registerContextMenus() {},
    chrome: { runtime: { onInstalled: { addListener: callback => { listener = callback; } } },
      storage: { sync: { set: data => writes.push(data) }, local: { set: data => writes.push(data) } },
      alarms: { create() {} },
    },
  });
  vm.runInContext(section(background, 'chrome.runtime.onInstalled.addListener(', '// ═══════════════════════════════════════════════════════════════════════════════'), context);
  listener({ reason: 'update' });
  assert.equal(writes.length, 0);
  listener({ reason: 'install' });
  assert.equal(writes.length, 2);
  assert.ok(Array.isArray(writes[1].captureHistory));
});

function domElement(tag) {
  const classes = new Set();
  const element = { tagName: tag, className: '', children: [], dataset: {}, listeners: {},
    classList: { add: value => classes.add(value), remove: value => classes.delete(value),
      contains: value => classes.has(value) || element.className.split(' ').includes(value) },
    getAttribute: key => element[key] || '',
    addEventListener: (type, callback) => { element.listeners[type] = callback; },
    insertBefore: (child, before) => {
      child.parentNode = element;
      const index = element.children.indexOf(before);
      if (index < 0) element.children.push(child);
      else element.children.splice(index, 0, child);
    },
    remove: () => { if (element.parentNode) element.parentNode.children = element.parentNode.children.filter(child => child !== element); },
  };
  Object.defineProperty(element, 'nextSibling', { get: () => element.parentNode?.children[element.parentNode.children.indexOf(element) + 1] || null });
  return element;
}

test('rendered badges reserve green, dimming and duplicate interception for confirmed matches', () => {
  const card = domElement('article');
  const name = domElement('a');
  name.href = candidate.profile_url;
  card.info = { name: candidate.name, profileUrl: candidate.profile_url };
  card.insertBefore(name, null);
  card.querySelector = () => name;
  card.querySelectorAll = selector => selector.startsWith('a[') ? [name]
    : card.children.filter(child => child !== name);
  let dialogs = 0;
  const context = vm.createContext({ URL, console, identityCardInfo: new WeakMap(), identityCardStates: new WeakMap(), identityLinkHandlers: new WeakMap(),
    document: { createElement: domElement }, window: {}, scheduleIdentityScan() {},
    scrapeSearchCardInfo: value => value.info,
    identityFingerprint: (_card, info) => JSON.stringify(info),
    showExistingConfirmDialog: () => { dialogs++; },
    chrome: { runtime: { sendMessage: (_request, callback) => callback?.({ url: 'https://example.invalid/candidate-bank' }) } },
  });
  vm.runInContext(section(content, '  function clearIdentityBadge', '  function invalidateIdentityCards') +
    section(content, '  function safeIdentityLink', '  /**\n   * Renders a premium') +
    '\nglobalThis.api = { markCardAsExisting, clearIdentityBadge, states: identityCardStates };', context);
  const decisions = [
    ['probable_match', 'Possible database match'], ['ambiguous', 'Multiple possible matches'],
    ['confirmed_duplicate', 'Already in database'],
  ];
  for (const [decision, label] of decisions) {
    context.api.clearIdentityBadge(card);
    context.api.states.set(card, { fingerprint: JSON.stringify(card.info) });
    context.api.markCardAsExisting(card, { ...card.info, ...row(0, decision), profile_url: 'https://example.invalid/candidate-bank',
      second_match: decision === 'ambiguous' ? { candidate_id: 'other' } : null });
    const badge = card.children.find(child => child.className === 'vhc-existing-badge');
    assert.equal(badge.innerText, label);
    assert.equal(badge.classList.contains('vhc-confidence-high'), decision === 'confirmed_duplicate');
    assert.equal(card.classList.contains('vhc-dimmed-card'), decision === 'confirmed_duplicate');
    if (decision === 'ambiguous') assert.ok(card.children.some(child => child.className === 'vhc-identity-alternative'));
  }
  name.listeners.click({ type: 'click', preventDefault() {}, stopPropagation() {} });
  assert.equal(dialogs, 1);
  context.api.clearIdentityBadge(card);
  name.listeners.click({ type: 'click', preventDefault: () => assert.fail('stale listener blocked navigation'), stopPropagation() {} });
  assert.equal(dialogs, 1);
  context.api.markCardAsExisting(card, { ...card.info, decision: 'unavailable' });
  const status = card.children.find(child => child.className === 'vhc-identity-status');
  assert.equal(status.innerText, 'Database check unavailable');
  assert.ok(!card.children.some(child => child.className === 'vhc-existing-badge'), 'unavailable status must not trigger missing-ID hover error');
});

test('observer responds to lazy text and recycled href updates without looping on badge text', () => {
  const scans = [];
  let notify;
  let observation;
  const context = vm.createContext({ console: { log() {} }, VERSION: 'test', cardObserver: null,
    Node: { ELEMENT_NODE: 1 }, document: { body: {} },
    scheduleIdentityScan: delay => scans.push(delay),
    MutationObserver: class { constructor(callback) { notify = callback; } observe(_body, options) { observation = options; } },
  });
  vm.runInContext(section(content, '  function observeNewCards()', '  function showToast') + '\nobserveNewCards();', context);
  assert.equal(scans.length, 1);
  const candidateElement = { nodeType: 1, closest: selector => selector.startsWith('.vhc-') ? null : {} };
  notify([{ target: { nodeType: 3, parentElement: candidateElement } }]);
  notify([{ target: candidateElement, attributeName: 'href' }]);
  assert.equal(scans.length, 3);
  notify([{ target: { nodeType: 1, closest: () => ({}) } }]);
  assert.equal(scans.length, 3);
  assert.equal(observation.characterData, true);
  assert.ok(observation.attributeFilter.includes('href'));
});

test('wrong-match feedback only acknowledges an accepted HTTP response', async () => {
  const handler = section(background, "  if (request.action === 'reportWrongMatch')", '  // ═══ CHECK EXISTING CANDIDATES');
  for (const status of [200, 403, 500]) {
    const context = vm.createContext({ console, VERSION: 'test', getAuth: async () => auth,
      fetch: async () => response({}, status),
    });
    vm.runInContext('globalThis.handle = function(request, sendResponse) {' + handler + '\n};', context);
    const result = await new Promise(resolve => context.handle({ action: 'reportWrongMatch', badge_candidate_id: 'db-1' }, resolve));
    assert.equal(result.ok, status === 200);
  }
});

// Synthetic card-scoped DOM fixtures exercise extraction grammar; these are not
// captures of a live Naukri page and do not certify current portal markup.
function contextScraper() {
  const context = vm.createContext({ URL, PLATFORM: 'naukri',
    cleanText: value => (value || '').replace(/\s+/g, ' ').trim(),
    document: { querySelector: () => assert.fail('scraper must not read another card or global page'),
      querySelectorAll: () => assert.fail('scraper must not read another card or global page') },
  });
  vm.runInContext(section(content, '  function scrapeSearchCardInfo', '  function safeIdentityLink') + '\nglobalThis.scrape = scrapeSearchCardInfo;', context);
  return options => {
    const { name = 'Rahul Sharma', current = '', text = '', education = '', profileUrl = candidate.profile_url,
      companyTitle = '', designationTitle = '', experienceText = '' } = options;
    const currentElement = { innerText: current, querySelector: selector => {
      const value = selector.includes('currently') ? designationTitle : companyTitle;
      return value ? { getAttribute: () => value } : null;
    } };
    return context.scrape({ innerText: text,
      getAttribute: () => '', querySelectorAll: () => [],
      querySelector: selector => {
        if (selector.startsWith('a.candidate-name, a.candidate-profile-summary')) return profileUrl ? { href: profileUrl } : null;
        if (selector.startsWith('a.candidate-name, [class*="candidateName"]')) return name ? { innerText: name } : null;
        if (selector.startsWith('#currentEmp')) return current || companyTitle || designationTitle ? currentElement : null;
        if (selector.startsWith('#education')) return education ? { innerText: education, getAttribute: () => '' } : null;
        if (selector.startsWith('[title="Experience"]')) return experienceText ? { innerText: experienceText } : null;
        return null;
      },
    });
  };
}

test('actual scraper keeps multiword current employers and separates following date lines', () => {
  const scrape = contextScraper();
  const result = scrape({ current: 'Senior Software Engineer at Tata Consultancy Services\nJanuary 2021 - Present' });
  assert.equal(result.current_employer, 'Tata Consultancy Services');
  assert.equal(result.designation, 'Senior Software Engineer');
  const structured = scrape({ current: 'Wrong role at Wrong company',
    companyTitle: 'Find candidates from Larsen & Toubro Limited',
    designationTitle: 'Find candidates who are currently Senior Engineer' });
  assert.equal(structured.current_employer, 'Larsen & Toubro Limited');
  assert.equal(structured.designation, 'Senior Engineer');
});

test('actual scraper captures explicitly labelled previous roles and never promotes them to current employment', () => {
  const result = contextScraper()({ current: 'Senior Engineer at Current Company Limited', text:
    'Rahul Sharma\nPrevious employment:\nEngineer at Tata Consultancy Services\n2017 - 2020\n' +
    'Previous: Consultant at Larsen & Toubro Limited\nPrevious: Engineer at Tata Consultancy Services\n' +
    'Current: Manager at Wrong Company\nDesigner at Unlabelled Company' });
  assert.equal(result.current_employer, 'Current Company Limited');
  assert.deepEqual(JSON.parse(JSON.stringify(result.experience)), [
    { title: 'Engineer', company: 'Tata Consultancy Services', relationship: 'previous' },
    { title: 'Consultant', company: 'Larsen & Toubro Limited', relationship: 'previous' },
  ]);
  const fieldBoundary = contextScraper()({ text: 'Previous:\nCurrent employment: Engineer at New Company' });
  assert.equal(fieldBoundary.experience.length, 0);
});

test('actual scraper structures only explicitly labelled education and retains unlabelled text as raw', () => {
  const scrape = contextScraper();
  const result = scrape({ education: 'Degree: B.Tech\nInstitution: Indian Institute of Technology Delhi\nGraduation year: 2020' });
  assert.deepEqual(JSON.parse(JSON.stringify(result.education_details)), [
    { degree: 'B.Tech', institution: 'Indian Institute of Technology Delhi', graduation_year: 2020 },
  ]);
  assert.ok(result.education.includes('Indian Institute of Technology Delhi'));
  const raw = 'B.Tech / B.E. Dr Babasaheb Ambedkar University 2023';
  const unlabelled = scrape({ education: raw });
  assert.equal(unlabelled.education, raw);
  assert.equal(unlabelled.education_details.length, 0, 'no guessed university or graduation year');
});

test('actual sparse-card scraping cannot acquire neighbouring candidate context', () => {
  const scrape = contextScraper();
  const other = scrape({ name: 'Priya Singh', current: 'Engineer at Other Company',
    text: 'Previous: Architect at Other Previous Company', education: 'Institution: Other University' });
  assert.equal(other.experience.length, 1);
  const sparse = scrape({ name: 'Rahul Sharma' });
  assert.equal(sparse.name, 'Rahul Sharma');
  assert.equal(sparse.current_employer, null);
  assert.equal(sparse.designation, null);
  assert.equal(sparse.education, null);
  assert.equal(sparse.experience.length, 0);
  assert.equal(sparse.education_details.length, 0);
  assert.equal(scrape({ profileUrl: null }), null);
});

test('observed context is bounded and transport excludes parser-only relationship metadata', async () => {
  const scrape = contextScraper();
  const info = scrape({
    text: Array.from({ length: 9 }, (_, i) => 'Previous: Engineer ' + i + ' at Prior Company ' + i).join('\n'),
    education: Array.from({ length: 6 }, (_, i) => 'Degree: Course ' + i + '\nInstitution: University ' + i + '\nGraduation: 2020').join('\n'),
  });
  assert.equal(info.experience.length, 5);
  assert.equal(info.education_details.length, 3);
  const harness = contentHarness([makeCard(info)]);
  await harness.api.checkAndMarkExistingProfiles();
  const sent = harness.sent[0].candidates[0];
  assert.equal(sent.experience.length, 5);
  assert.equal(sent.education_details.length, 3);
  assert.equal(sent.experience[0].company, 'Prior Company 0');
  assert.equal(sent.experience[0].relationship, undefined);
  assert.equal(sent.education_details[0].institution, 'University 0');
  assert.equal(sent.education_details[0].raw_text, undefined);
  const oversized = scrape({ current: 'Engineer at ' + 'A'.repeat(501),
    education: 'Degree: ' + 'B'.repeat(301), experienceText: '120y 2m' });
  assert.equal(oversized.current_employer, null);
  assert.equal(oversized.education_details.length, 0);
  assert.equal(oversized.experience_years, null);
});
