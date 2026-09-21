/**
 * VHC Talent OS - Background Service Worker v4.0.0
 * 
 * Architecture:
 * - captureQueue: profiles extracted from DOM, waiting to be sent to AI + databank
 * - offlineQueue: profiles fully processed by AI, waiting for network to send to databank
 * 
 * Flow:
 *   content.js extracts raw profile data
 *     → queued into captureQueue (instant, non-blocking)
 *     → background worker drains captureQueue: AI extract → databank POST
 *     → on network failure: moves to offlineQueue
 *     → offlineQueue drains when back online
 */

const VERSION = '7.0.0';

// ═══ Background Tab Capture Tracking ═══
// Tracks which tabs we've already kicked a background-capture on so we
// don't double-trigger during Naukri's SPA navigation events.
const backgroundCaptureKickedTabs = new Set();
// Per-tab throttle so we respect Naukri's "View Contact" rate limit
let lastBackgroundCaptureAt = 0;
const BG_CAPTURE_MIN_GAP_MS = 600;
// Context-menu source tracking — if a tab was opened from our context menu,
// we'll always run the forced capture even on the first tab switch.
const contextMenuOpenedTabs = new Set();

// ═══ CV Iframe Data Storage (per tab) ═══
// Stores CV text relayed by content scripts running inside iframes (all_frames: true)
const cvIframeDataByTab = {};

const CONFIG = {
  MAX_CAPTURE_QUEUE_SIZE: 500,
  MAX_OFFLINE_QUEUE_SIZE: 500,
  DRAIN_CONCURRENCY: 4,
  DRAIN_INTERVAL_MS: 400,
  RETRY_MAX: 3,
  RETRY_BACKOFF_MS: 3000,
  SYNC_ALARM_MINUTES: 1,
  SESSION_PING_MINUTES: 10,    // ping /api/auth/me to keep token alive
  MAX_HISTORY_ITEMS: 200,      // max capture history records stored
  // ─── Async capture polling (v5.5.10) ───
  ASYNC_POLL_INTERVAL_MS: 3000,   // poll every 3 s
  ASYNC_POLL_MAX_ATTEMPTS: 60,    // give up after ~3 min (60 × 3 s)
};

// ═══════════════════════════════════════════════════════════════════════════════
//  ASYNC CAPTURE — v5.5.10
//
//  Posts the profile to /api/extension/capture/async (returns 202 + job_id
//  immediately), then polls /api/extension/capture/status/{job_id} until the
//  job finishes. This avoids the Chrome MV3 30 s service-worker timeout and
//  Cloudflare's 100 s edge timeout that the old sync /capture endpoint hit
//  on slow Atlas/RunPod calls.
//
//  Caller-side contract is IDENTICAL to the old sync call:
//    - Resolves with the same CaptureResponse shape ({success, action,
//      candidate_id, message}).
//    - Rejects on auth failure, network error, or job failure / timeout.
//    - On HTTP 401, returns the original Response so the caller can run its
//      token-refresh + requeue logic (preserves prior behaviour).
// ═══════════════════════════════════════════════════════════════════════════════
async function postCaptureAsync(auth, payload) {
  // v6.0.1: clean lone surrogates / styled Unicode before serialization
  payload = sanitizeDeep(payload);
  // 1. Submit
  const submit = await fetch(`${auth.apiUrl}/api/extension/capture/async`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${auth.token}`,
    },
    body: JSON.stringify(payload),
  });

  if (submit.status === 401) return { _httpResponse: submit };  // bubble up auth failure
  if (!submit.ok) {
    const txt = await submit.text();
    throw new Error(`capture/async HTTP ${submit.status}: ${txt.substring(0, 160)}`);
  }
  const { job_id } = await submit.json();
  if (!job_id) throw new Error('capture/async did not return a job_id');

  // 2. Poll until completed or failed
  for (let attempt = 1; attempt <= CONFIG.ASYNC_POLL_MAX_ATTEMPTS; attempt++) {
    await new Promise(r => setTimeout(r, CONFIG.ASYNC_POLL_INTERVAL_MS));

    const poll = await fetch(`${auth.apiUrl}/api/extension/capture/status/${job_id}`, {
      headers: { 'Authorization': `Bearer ${auth.token}` },
    });
    if (poll.status === 401) return { _httpResponse: poll };
    if (poll.status === 404) {
      // Job evicted (shouldn't happen mid-poll) — surface a clear error
      throw new Error(`capture/async job ${job_id} disappeared (404)`);
    }
    if (!poll.ok) {
      // Transient — keep polling
      console.warn(`[VHC BG v${VERSION}] capture/status HTTP ${poll.status}, retrying (attempt ${attempt})`);
      continue;
    }
    const job = await poll.json();
    if (job.status === 'completed') return { _result: job.result };
    if (job.status === 'failed')    throw new Error(`capture job ${job_id} failed: ${job.error || 'unknown error'}`);
    // pending / processing → continue polling
  }
  throw new Error(`capture/async job ${job_id} timed out after ${CONFIG.ASYNC_POLL_MAX_ATTEMPTS * CONFIG.ASYNC_POLL_INTERVAL_MS / 1000}s`);
}

// ─── State ────────────────────────────────────────────────────────────────────
let isDraining = false;          // prevent concurrent drain loops

// ─── Install ──────────────────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener((details) => {
  console.log(`[VHC BG v${VERSION}] Installed`);
  // Updates retain queues, capture history, preferences and usage statistics.
  if (details.reason === 'install') {
  chrome.storage.sync.set({
    enabled: true,
    showNotifications: true,
    autoCapture: true,
    bulkCapture: true,
    stats: {
      captured_today: 0, captured_week: 0,
      captured_total: 0, updated_total: 0,
      failed_total: 0,
      last_reset: new Date().toDateString()
    }
  });
  chrome.storage.local.set({ captureQueue: [], offlineQueue: [], deadLetterQueue: [], captureHistory: [] });
  }
  chrome.alarms.create('drainCaptureQueue', { periodInMinutes: CONFIG.SYNC_ALARM_MINUTES });
  chrome.alarms.create('syncOfflineQueue',  { periodInMinutes: CONFIG.SYNC_ALARM_MINUTES });
  chrome.alarms.create('sessionPing',       { periodInMinutes: CONFIG.SESSION_PING_MINUTES });

  registerContextMenus();
});

// ═══════════════════════════════════════════════════════════════════════════════
// CONTEXT MENU — "VHC: Capture this profile"
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Registers the right-click context menu items.
 * - Appears on Naukri links (e.g. search result rows) → captures via a new bg tab
 * - Appears on a loaded Naukri profile page → forces a capture of the current page
 */
function registerContextMenus() {
  try {
    chrome.contextMenus.removeAll(() => {
      chrome.contextMenus.create({
        id: 'vhc-capture-link',
        title: 'VHC: Capture this profile',
        contexts: ['link'],
        targetUrlPatterns: [
          'https://www.naukri.com/*',
          'https://*.naukri.com/*',
          'https://www.linkedin.com/in/*',
          'https://*.linkedin.com/in/*',
          'https://www.foundit.in/*',
          'https://*.foundit.in/*',
        ],
      });
      chrome.contextMenus.create({
        id: 'vhc-capture-page',
        title: 'VHC: Capture this profile',
        contexts: ['page'],
        documentUrlPatterns: [
          'https://www.naukri.com/*',
          'https://*.naukri.com/*',
          'https://www.linkedin.com/in/*',
          'https://*.linkedin.com/in/*',
          'https://www.foundit.in/*',
          'https://*.foundit.in/*',
        ],
      });
    });
  } catch (e) {
    console.warn(`[VHC BG v${VERSION}] Context menu register failed:`, e.message);
  }
}

// Re-register on startup (onInstalled doesn't fire on every browser launch)
chrome.runtime.onStartup.addListener(registerContextMenus);

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    if (info.menuItemId === 'vhc-capture-link' && info.linkUrl) {
      // Open the profile link in a background tab and mark it for forced capture
      const opened = await chrome.tabs.create({ url: info.linkUrl, active: false });
      if (opened?.id) {
        contextMenuOpenedTabs.add(opened.id);
        console.log(`[VHC BG v${VERSION}] Context-menu opened tab ${opened.id}: ${info.linkUrl}`);
      }
      return;
    }

    if (info.menuItemId === 'vhc-capture-page' && tab?.id) {
      // Force capture the currently-viewed profile tab
      console.log(`[VHC BG v${VERSION}] Context-menu capture current tab ${tab.id}`);
      await forceCaptureInTab(tab.id, { fromContextMenu: true });
    }
  } catch (e) {
    console.warn(`[VHC BG v${VERSION}] Context menu handler error:`, e.message);
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// BACKGROUND-TAB CAPTURE FORCING
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Detects candidate profile pages for Naukri, LinkedIn, and Foundit.
 */
function isProfileUrl(url) {
  if (!url) return false;
  try {
    const u = new URL(url);
    const host = u.hostname;
    const pathname = u.pathname;
    const search = u.search;
    
    // Naukri
    if (host.includes('naukri.com')) {
      if (pathname.includes('/v3/preview') && search.includes('tabKey=profile')) return true;
      if (/viewResume|view-resume|cvPreview/i.test(pathname)) return true;
      return false;
    }
    // LinkedIn
    if (host.includes('linkedin.com')) {
      return /^\/in\/[^/]+\/?$/.test(pathname);
    }
    // Foundit
    if (host.includes('foundit.in') || host.includes('foundit.sg') || host.includes('foundit.my') || host.includes('monster.com')) {
      return /\/(profile|resume|cv)\/[^/]+/.test(pathname);
    }
  } catch (_) {}
  return false;
}

/**
 * Normalizes candidate profile URLs to generate a stable, consistent dedup key.
 */
function normalizeProfileUrl(url) {
  if (!url) return '';
  try {
    const u = new URL(url);
    const host = u.hostname;
    
    if (host.includes('naukri.com')) {
      const candidateId = u.searchParams.get('candidateId') || u.searchParams.get('profileId') || u.searchParams.get('pid');
      if (candidateId) {
        return `naukri::id::${candidateId}`;
      }
      const sid = u.searchParams.get('sid');
      if (sid) {
        return `naukri::sid::${sid}`;
      }
      const pathMatch = u.pathname.match(/\/(?:resume|profile|cv|preview)\/([a-zA-Z0-9_-]+)/i);
      if (pathMatch) return `naukri::path::${pathMatch[1]}`;
      
      return `naukri::raw::${u.origin}${u.pathname}`;
    }
    
    if (host.includes('linkedin.com')) {
      const m = u.pathname.match(/^\/in\/([^/]+)/);
      if (m) return `linkedin::in::${m[1].toLowerCase()}`;
      return `linkedin::raw::${u.origin}${u.pathname}`;
    }
    
    if (host.includes('foundit.in') || host.includes('foundit.sg') || host.includes('foundit.my') || host.includes('monster.com')) {
      const m = u.pathname.match(/\/(profile|resume|cv)\/([^/]+)/);
      if (m) return `foundit::id::${m[2].toLowerCase()}`;
      return `foundit::raw::${u.origin}${u.pathname}`;
    }
    
    return u.href;
  } catch (_) {
    return url;
  }
}

// Identity badges trust a documented server decision, never a numeric score.
const IDENTITY_MATCHER_VERSION = 'identity-resolution-1';
const IDENTITY_BATCH_SIZE = 50;
const IDENTITY_DECISIONS = new Set([
  'confirmed_duplicate', 'probable_match', 'ambiguous', 'no_match_found',
  'insufficient_data', 'conflicting_records', 'unavailable',
]);

function unavailableIdentityResult(index, reason, serviceStatus = 'unavailable') {
  return {
    index, exists: false, decision: 'unavailable', service_status: serviceStatus,
    matcher_version: IDENTITY_MATCHER_VERSION, reason_codes: [reason],
    matched_signals: [], conflicts: [], missing_fields: [],
  };
}

// History remains an activity log. Rotating/reused source URLs cannot identify
// a candidate, even as an outage fallback.
function identityHistoryScope(auth) {
  if (!auth?.apiUrl || !auth?.userEmail) return null;
  return auth.apiUrl.replace(/\/+$/, '').toLowerCase() + '|' + auth.userEmail.trim().toLowerCase();
}

function checkLocalHistory(candidates) {
  return candidates.map((_, index) => unavailableIdentityResult(index, 'database_check_unavailable'));
}

function validateIdentityResponse(candidates, envelope) {
  if (!envelope || envelope.matcher_version !== IDENTITY_MATCHER_VERSION) {
    return candidates.map((_, index) => unavailableIdentityResult(index, 'unsupported_matcher_contract'));
  }
  if (envelope.service_status !== 'ready') {
    const disabled = envelope.service_status === 'disabled';
    return candidates.map((_, index) => unavailableIdentityResult(index,
      disabled ? 'matching_disabled' : 'database_check_unavailable', disabled ? 'disabled' : 'unavailable'));
  }
  const rows = Array.isArray(envelope.results) ? envelope.results : [];
  const byIndex = new Map();
  const duplicates = new Set();
  for (const row of rows) {
    if (!row || !Number.isInteger(row.index) || row.index < 0 || row.index >= candidates.length) continue;
    if (byIndex.has(row.index)) duplicates.add(row.index);
    byIndex.set(row.index, row);
  }
  return candidates.map((_, index) => {
    const row = byIndex.get(index);
    if (!row || duplicates.has(index)) return unavailableIdentityResult(index, 'incomplete_match_response');
    const confirmed = row.decision === 'confirmed_duplicate';
    const candidateId = row.candidate_id || row.top_match?.candidate_id;
    const hardConflict = Array.isArray(row.conflicts) && row.conflicts.some(code =>
      ['source_anchor_name_conflict', 'verified_id_conflict', 'confirmed_different'].includes(code));
    if (row.matcher_version !== IDENTITY_MATCHER_VERSION ||
        !IDENTITY_DECISIONS.has(row.decision) || row.exists !== confirmed ||
        row.score_kind !== 'evidence_points' ||
        !Number.isFinite(row.match_score) ||
        !Array.isArray(row.matched_signals) || !Array.isArray(row.conflicts) ||
        (confirmed && (!candidateId || hardConflict))) {
      return unavailableIdentityResult(index, 'invalid_match_response');
    }
    return {
      ...row, candidate_id: candidateId || null, provenance: 'backend',
      service_status: row.decision === 'unavailable' ? 'unavailable' : 'ready',
      audit_id: envelope.audit_id || null, audit_index: index,
    };
  });
}

async function checkExistingCandidates(candidates) {
  if (!Array.isArray(candidates) || candidates.length === 0) {
    return { results: [], matcher_version: IDENTITY_MATCHER_VERSION, service_status: 'ready' };
  }
  let auth = await getAuth();
  if (!auth) {
    return { results: candidates.map((_, i) => unavailableIdentityResult(i, 'authentication_required', 'disabled')),
      matcher_version: IDENTITY_MATCHER_VERSION, service_status: 'disabled' };
  }
  const results = new Array(candidates.length);
  let refreshPromise = null;
  let accessDenied = false;
  async function requestBatch(batch, requestAuth) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(`${requestAuth.apiUrl}/api/extension/check-existing`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${requestAuth.token}` },
        body: JSON.stringify({ candidates: batch }),
        signal: controller.signal,
      });
      // Keep the timeout active until the response body has finished arriving.
      return { status: response.status, ok: response.ok, data: response.ok ? await response.json() : null };
    } finally { clearTimeout(timeout); }
  }
  async function runBatch(offset) {
    const batch = candidates.slice(offset, offset + IDENTITY_BATCH_SIZE);
    let rows;
    let permissionPending = false;
    try {
      if (accessDenied) {
        rows = batch.map((_, i) => unavailableIdentityResult(i, 'access_denied', 'disabled'));
      } else {
        let response = await requestBatch(batch, auth);
        if (response.status === 401) {
          permissionPending = true;
          if (!refreshPromise) refreshPromise = refreshAccessToken(auth.apiUrl).then(async refreshed => {
            if (refreshed) auth = await getAuth();
            return refreshed && auth;
          });
          if (await refreshPromise) response = await requestBatch(batch, auth);
        }
        permissionPending = response.status === 401 || response.status === 403;
        if (response.status === 401 || response.status === 403) {
          accessDenied = true;
          rows = batch.map((_, i) => unavailableIdentityResult(i, 'access_denied', 'disabled'));
        } else if (!response.ok) {
          // An outage cannot recover identity from a rotating source URL.
          rows = response.status >= 500 || response.status === 429
            ? checkLocalHistory(batch)
            : batch.map((_, i) => unavailableIdentityResult(i, 'match_request_rejected'));
        } else {
          rows = validateIdentityResponse(batch, response.data);
          if (rows.some(row => row.service_status === 'disabled')) accessDenied = true;
        }
      }
    } catch (_) {
      if (permissionPending) {
        accessDenied = true;
        rows = batch.map((_, i) => unavailableIdentityResult(i, 'access_denied', 'disabled'));
      } else {
        rows = checkLocalHistory(batch);
      }
    }
    rows.forEach((row, i) => { results[offset + i] = { ...row, index: offset + i }; });
  }
  // Bounded parallelism keeps large result pages responsive without truncation.
  for (let offset = 0; offset < candidates.length; offset += IDENTITY_BATCH_SIZE * 3) {
    const offsets = [offset, offset + IDENTITY_BATCH_SIZE, offset + IDENTITY_BATCH_SIZE * 2]
      .filter(value => value < candidates.length);
    await Promise.all(offsets.map(runBatch));
  }
  // A permission failure invalidates the whole logical check, including an
  // earlier local reminder or successful batch from this request.
  if (accessDenied) {
    return { results: candidates.map((_, i) => unavailableIdentityResult(i, 'access_denied', 'disabled')),
      matcher_version: IDENTITY_MATCHER_VERSION, service_status: 'disabled' };
  }
  return {
    results, matcher_version: IDENTITY_MATCHER_VERSION,
    service_status: results.some(row => row.service_status === 'unavailable') ? 'unavailable'
      : results.every(row => row.service_status === 'disabled') ? 'disabled' : 'ready',
  };
}

/**
 * Smart polling loop to check if a tab is ready and fully rendered.
 */
async function waitForTabReady(tabId) {
  const MAX_POLLS = 15;
  const POLL_INTERVAL = 500;
  
  for (let poll = 0; poll < MAX_POLLS; poll++) {
    try {
      const [res] = await chrome.scripting.executeScript({
        target: { tabId, allFrames: false },
        func: () => {
          return {
            readyState: document.readyState,
            bodyTextLength: document.body ? (document.body.innerText || '').length : 0,
            hasContent: !!(
              document.querySelector('[class*="candidateCard"], [class*="candidate-card"], [class*="resumeCard"]') ||
              document.querySelector('[class*="experienc"], [class*="Experience"]') ||
              document.querySelector('[class*="skill"], [class*="Skill"]') ||
              document.querySelector('[class*="education"], [class*="Education"]') ||
              document.querySelector('[class*="viewContact"], [class*="view-contact"]')
            )
          };
        }
      });
      
      if (res && res.result) {
        const { readyState, bodyTextLength, hasContent } = res.result;
        console.log(`[VHC BG v${VERSION}] Poll tab ${tabId} readyState=${readyState}, textLen=${bodyTextLength}, hasContent=${hasContent}`);
        if (readyState === 'complete' && (bodyTextLength > 300 || hasContent)) {
          console.log(`[VHC BG v${VERSION}] Tab ${tabId} is ready after ${poll * POLL_INTERVAL}ms!`);
          return true;
        }
      }
    } catch (err) {
      if (err.message && (err.message.includes('No tab') || err.message.includes('cannot access') || err.message.includes('No frame'))) {
        console.warn(`[VHC BG v${VERSION}] Tab ${tabId} closed during readiness polling.`);
        return false;
      }
      console.warn(`[VHC BG v${VERSION}] Error polling tab ${tabId}:`, err.message);
    }
    await sleep(POLL_INTERVAL);
  }
  
  console.log(`[VHC BG v${VERSION}] Tab ${tabId} wait ready timed out, proceeding anyway.`);
  return false;
}


/**
 * Send a manualCapture message into the tab's content script.
 * Chrome does not throttle service-worker-originated messages, so this wakes
 * up the capture flow even in backgrounded/hidden tabs. If the content script
 * is not yet registered, we inject it via chrome.scripting as a fallback.
 */
async function forceCaptureInTab(tabId, opts = {}) {
  const now = Date.now();
  const gap = now - lastBackgroundCaptureAt;
  if (gap < BG_CAPTURE_MIN_GAP_MS) {
    const wait = BG_CAPTURE_MIN_GAP_MS - gap;
    await sleep(wait);
  }
  lastBackgroundCaptureAt = Date.now();

  const trySendMessage = () => new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(tabId, { action: 'manualCapture', _forced: true }, (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          resolve({ ok: true, resp });
        }
      });
    } catch (e) {
      resolve({ ok: false, error: e.message });
    }
  });

  // First attempt — content script should already be registered on Naukri pages
  let r = await trySendMessage();
  if (r.ok) {
    console.log(`[VHC BG v${VERSION}] Forced capture msg sent to tab ${tabId} (${opts.fromContextMenu ? 'ctxmenu' : 'bg-tab'})`);
    return true;
  }

  // Fallback: content script not ready yet → inject it, then retry
  console.warn(`[VHC BG v${VERSION}] sendMessage to tab ${tabId} failed (${r.error}) — injecting content.js`);
  try {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: false },
      files: ['content.js'],
    });
    // Small delay so init() has a chance to attach its onMessage listener
    await sleep(800);
    r = await trySendMessage();
    if (r.ok) {
      console.log(`[VHC BG v${VERSION}] Forced capture after inject on tab ${tabId}`);
      return true;
    }
    console.warn(`[VHC BG v${VERSION}] Forced capture still failed on tab ${tabId}: ${r.error}`);
  } catch (e) {
    console.warn(`[VHC BG v${VERSION}] Inject content.js failed on tab ${tabId}: ${e.message}`);
  }
  return false;
}

/**
 * Watch every tab-update: when a Naukri profile finishes loading in a tab
 * that is either (a) in the background (user opened via ctrl-click / middle-
 * click / right-click "Open in new tab"), or (b) opened via our context
 * menu, we forcibly trigger manual capture via the content script.
 *
 * We skip tabs that are already active+focused because content.js auto-
 * capture already covers those, and we only fire once per tab per URL.
 */
// Consolidated onUpdated Listener
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  try {
    // Section 1: Clean when tab navigates to a new page (loading)
    if (changeInfo.status === 'loading') {
      if (cvIframeDataByTab[tabId]) {
        delete cvIframeDataByTab[tabId];
        console.log(`[VHC BG v${VERSION}] Cleared CV iframe data for navigating tab ${tabId}`);
      }
      return;
    }

    if (changeInfo.status !== 'complete') return;

    // Section 2: Background / Context-menu capture forcing
    if (isProfileUrl(tab?.url)) {
      const wasContextMenu = contextMenuOpenedTabs.has(tabId);
      const isBackground = tab.active === false;

      if (wasContextMenu || isBackground) {
        // Dedup: don't fire the same tab twice for the same normalized URL
        const normUrl = normalizeProfileUrl(tab.url);
        const dedupKey = `${tabId}::${normUrl}`;
        if (!backgroundCaptureKickedTabs.has(dedupKey)) {
          backgroundCaptureKickedTabs.add(dedupKey);
          
          // Keep the set bounded
          if (backgroundCaptureKickedTabs.size > 500) {
            backgroundCaptureKickedTabs.clear();
          }

          console.log(`[VHC BG v${VERSION}] ${wasContextMenu ? 'ctxmenu' : 'bg-tab'} profile loaded in tab ${tabId} — forcing capture`);
          
          // Wait adaptively for tab ready instead of hardcoded delay
          await waitForTabReady(tabId);
          await forceCaptureInTab(tabId, { fromContextMenu: wasContextMenu });
          
          // One-shot — clear the context-menu flag after the capture attempt
          contextMenuOpenedTabs.delete(tabId);
        }
      }
    }

    // Section 3: Job binding from VHC dashboard tab
    const detectedJob = detectJobFromUrl(tab.url);
    if (detectedJob) {
      const auth = await getAuth();
      const details = await fetchJobDetails(detectedJob.job_id, auth);
      if (details) {
        await new Promise(r => chrome.storage.local.set({ vhc_active_job: details }, r));
        console.log(`[VHC BG v${VERSION}] Active job set: ${details.job_title} (${details.job_id})`);
        notifyPopup({ action: 'activeJobUpdated', job: details });
      }
    }
  } catch (err) {
    console.error(`[VHC BG v${VERSION}] Error in consolidated onUpdated listener:`, err.message);
  }
});

// Consolidated onRemoved Listener
chrome.tabs.onRemoved.addListener((tabId) => {
  try {
    contextMenuOpenedTabs.delete(tabId);
    
    // Purge any dedup keys belonging to this tab
    for (const k of backgroundCaptureKickedTabs) {
      if (k.startsWith(`${tabId}::`)) backgroundCaptureKickedTabs.delete(k);
    }
    
    // Clean up CV iframe data
    if (cvIframeDataByTab[tabId]) {
      delete cvIframeDataByTab[tabId];
      console.log(`[VHC BG v${VERSION}] Cleaned CV iframe data for closed tab ${tabId}`);
    }
  } catch (err) {
    console.error(`[VHC BG v${VERSION}] Error in consolidated onRemoved listener:`, err.message);
  }
});


// ─── Alarms ───────────────────────────────────────────────────────────────────
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'drainCaptureQueue') drainCaptureQueue();
  if (alarm.name === 'syncOfflineQueue')  processOfflineQueue();
  if (alarm.name === 'sessionPing')       pingSession();
});

// ─── Startup: ensure alarms are registered even after browser/extension restart ──
chrome.runtime.onStartup.addListener(() => {
  console.log(`[VHC BG v${VERSION}] Startup — ensuring alarms`);
  chrome.alarms.get('drainCaptureQueue', a => { if (!a) chrome.alarms.create('drainCaptureQueue', { periodInMinutes: CONFIG.SYNC_ALARM_MINUTES }); });
  chrome.alarms.get('syncOfflineQueue',  a => { if (!a) chrome.alarms.create('syncOfflineQueue',  { periodInMinutes: CONFIG.SYNC_ALARM_MINUTES }); });
  chrome.alarms.get('sessionPing',       a => { if (!a) chrome.alarms.create('sessionPing',       { periodInMinutes: CONFIG.SESSION_PING_MINUTES }); });
  // Ping immediately on startup so any stale token is refreshed
  setTimeout(pingSession, 2000);
});

// ─── Online event ─────────────────────────────────────────────────────────────
self.addEventListener('online', () => {
  console.log(`[VHC BG v${VERSION}] Back online — draining queues`);
  drainCaptureQueue();
  processOfflineQueue();
});


// ═══════════════════════════════════════════════════════════════════════════════
// JOB BINDING — detect active job from VHC dashboard tab
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Watch all tabs for VHC job pages.
 * When a recruiter opens a job in the VHC dashboard, we store it as the
 * "active job" so that subsequent captures are automatically shortlisted to it.
 *
 * VHC job page URL patterns:
 *   https://*.vhc.in/jobs/123                 → job_id = 123
 *   https://*.vhc.in/requisitions/456          → job_id = 456
 *   https://*.emergentagent.com/jobs/789       → job_id = 789
 *   https://*.ventureshrd.com/jobs/101         → job_id = 101
 *   or any VHC URL with ?job_id= or #job/
 */
function detectJobFromUrl(url) {
  if (!url) return null;
  try {
    const u = new URL(url);
    // Only watch VHC/Emergent domains
    const isVhcDomain = u.hostname.includes('vhc.in') ||
                        u.hostname.includes('emergentagent.com') ||
                        u.hostname.includes('emergent.host') ||
                        u.hostname.includes('ventureshrd.com');
    if (!isVhcDomain) return null;

    // Pattern 1: /jobs/123 or /requisitions/123
    const pathMatch = u.pathname.match(/\/(jobs|requisitions|job|req)\/(\d+)/i);
    if (pathMatch) return { job_id: pathMatch[2], source: 'path' };

    // Pattern 2: ?job_id=123 or ?req_id=123 or ?jobId=123
    const jobIdParam = u.searchParams.get('job_id') || u.searchParams.get('jobId') ||
                       u.searchParams.get('req_id') || u.searchParams.get('reqId');
    if (jobIdParam) return { job_id: jobIdParam, source: 'param' };

    // Pattern 3: hash fragment #job/123
    const hashMatch = u.hash.match(/#(?:job|req)\/(\d+)/i);
    if (hashMatch) return { job_id: hashMatch[1], source: 'hash' };

  } catch (_) {}
  return null;
}

async function fetchJobDetails(jobId, auth) {
  if (!auth || !jobId) return null;
  try {
    const res = await fetch(`${auth.apiUrl}/api/extension/job-info?job_id=${jobId}`, {
      headers: { 'Authorization': `Bearer ${auth.token}` }
    });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      job_id:    data.job_id || jobId,
      job_title: data.title || data.job_title || `Job #${jobId}`,
      job_code:  data.code  || data.job_code  || null,
    };
  } catch (_) {
    // Graceful fallback: store just the ID
    return { job_id: jobId, job_title: `Job #${jobId}`, job_code: null };
  }
}


// ─── Message Router ───────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {

  // ═══ REPORT WRONG-MATCH BADGE (Badge Phase A telemetry) ═══
  // Content.js calls this when a recruiter clicks the small "Wrong match?"
  // link beside a match suggestion. Acknowledge only after the API accepts it.
  if (request.action === 'reportWrongMatch') {
    (async () => {
      try {
        const auth = await getAuth();
        if (!auth?.token || !auth?.apiUrl) {
          sendResponse({ ok: false });
          return;
        }
        const response = await fetch(`${auth.apiUrl}/api/extension/audit/wrong-match`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${auth.token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            audit_id: request.audit_id || null,
            card_idx: request.card_idx ?? null,
            badge_candidate_id: request.badge_candidate_id,
            card_name: request.card_name || null,
            card_headline: request.card_headline || null,
            card_employer: request.card_employer || null,
            card_location: request.card_location || null,
            page_url: request.page_url || null,
            extension_version: VERSION,
            reason: request.reason || null,
          }),
        });
        sendResponse({ ok: response.ok });
      } catch (e) {
        console.warn(`[VHC BG v${VERSION}] reportWrongMatch failed:`, e.message);
        // Never bubble error to popup — flag stays silent per product spec.
        sendResponse({ ok: false });
      }
    })();
    return true;
  }

  // ═══ CANDIDATE CALLED (fix.docx — "how many candidates we called") ═══
  // Fired when a recruiter opens the DB record behind an "Already in
  // Database" badge. Silent telemetry — powers the "Candidates called"
  // box on the admin Badge Audit page.
  if (request.action === 'trackCandidateCalled') {
    (async () => {
      try {
        const auth = await getAuth();
        if (!auth?.token || !auth?.apiUrl) { sendResponse({ ok: false }); return; }
        await fetch(`${auth.apiUrl}/api/extension/candidate-called`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${auth.token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            candidate_id: request.candidate_id,
            source: request.source || 'badge_expand',
            candidate_name: request.candidate_name || null,
            naukri_id: request.naukri_id || null,
            page_url: request.page_url || null,
          }),
        });
        sendResponse({ ok: true });
      } catch (e) {
        console.warn(`[VHC BG v${VERSION}] trackCandidateCalled failed:`, e.message);
        sendResponse({ ok: false });
      }
    })();
    return true;
  }

  // ═══ CHECK EXISTING CANDIDATES (Local cache + API backend) ═══
  if (request.action === 'checkExisting') {
    checkExistingCandidates(request.candidates || [])
      .then(sendResponse)
      .catch(e => {
        console.error(`[VHC BG v${VERSION}] checkExisting error:`, e.message);
        sendResponse({ success: false, matcher_version: IDENTITY_MATCHER_VERSION, service_status: 'unavailable',
          results: (request.candidates || []).map((_, i) => unavailableIdentityResult(i, 'database_check_unavailable')) });
      });
    return true; // Keep message channel open for async response
  }

  // ═══ DEEP-LINK: Build candidate-bank URL from configured apiUrl ═══
  // Used by content.js to make the "Already in Database" badge an <a> with a
  // proper href (so middle-click / ctrl-click / right-click → open in new tab
  // all work natively). The frontend URL is derived from the api URL by
  // stripping the leading `api.` subdomain (e.g. api.ventureshrd.com →
  // ventureshrd.com). For non-standard hosts we just reuse the apiUrl host.
  if (request.action === 'getCandidateBankUrl') {
    buildCandidateBankUrl(request.candidate_id)
      .then((url) => sendResponse({ url }))
      .catch(() => sendResponse({ url: null }));
    return true;
  }

  // ═══ DEEP-LINK FALLBACK: Open candidate-bank profile in a new tab ═══
  // Used when content.js couldn't pre-resolve the URL (e.g. badge clicked
  // before getCandidateBankUrl resolved). Pure UX-fallback path.
  if (request.action === 'openCandidateProfile') {
    buildCandidateBankUrl(request.candidate_id)
      .then((url) => {
        if (url) chrome.tabs.create({ url });
        sendResponse({ success: !!url });
      })
      .catch(() => sendResponse({ success: false }));
    return true;
  }

  // ═══ CV IFRAME DATA RELAY (from content script running inside iframe) ═══
  if (request.action === 'broadcastCVExtraction') {
    // Parent page asks us to poke every frame's content script so late-
    // loading CV iframes re-extract and relay (tabs.sendMessage without a
    // frameId broadcasts to ALL frames in the tab).
    const tabId = sender.tab?.id;
    if (tabId) {
      try {
        chrome.tabs.sendMessage(tabId, { action: 'requestCVExtraction' }, () => {
          void chrome.runtime.lastError;
        });
      } catch (_) {}
    }
    sendResponse({ success: true });
    return false;
  }

  if (request.action === 'cvIframeData') {
    const tabId = sender.tab?.id;
    if (tabId && request.data) {
      // v6.2.1: progressive CV renders relay multiple times — keep the
      // BEST snapshot (longest text; contacts beat no-contacts).
      const prev = cvIframeDataByTab[tabId];
      const newLen = (request.data.text || '').length;
      const prevLen = prev ? (prev.text || '').length : 0;
      const newContacts = (request.data.phones?.length || 0) + (request.data.emails?.length || 0);
      const prevContacts = prev ? (prev.phones?.length || 0) + (prev.emails?.length || 0) : 0;
      if (!prev || newLen > prevLen || newContacts > prevContacts) {
        cvIframeDataByTab[tabId] = request.data;
        console.log(`[VHC BG v${VERSION}] CV iframe data stored for tab ${tabId}: ${newLen} chars (prev ${prevLen}), contacts ${newContacts}`);
      }
    }
    sendResponse({ success: true });
    return false;
  }

  // ═══ GET CV IFRAME DATA (requested by main page content script) ═══
  if (request.action === 'getCvIframeData') {
    const tabId = sender.tab?.id;
    const data = tabId ? cvIframeDataByTab[tabId] : null;
    console.log(`[VHC BG v${VERSION}] CV iframe data request for tab ${tabId}: ${data ? data.text.length + ' chars' : 'none'}`);
    sendResponse({ data: data || null });
    return false;
  }

  // ═══ FETCH IFRAME SRC (fallback: background fetches cross-origin iframe content) ═══
  if (request.action === 'fetchCvBinary') {
    // v6.3.0 — content-type-aware CV fetch. PDFs come back as base64 for
    // client-side pdf.js text extraction; HTML comes back stripped as
    // before; Office docs are flagged so the parent skips client parsing.
    (async () => {
      try {
        const url = request.url;
        if (!url) return sendResponse({ error: 'No URL' });
        const resp = await fetch(url, {
          credentials: 'include',
          headers: { 'Accept': 'application/pdf,text/html,*/*' },
        });
        if (!resp.ok) return sendResponse({ error: `HTTP ${resp.status}` });
        const ctype = (resp.headers.get('content-type') || '').toLowerCase();
        const isPdf = ctype.includes('application/pdf') || /\.pdf(\?|$)/i.test(url);
        if (isPdf) {
          const buf = await resp.arrayBuffer();
          if (buf.byteLength > 20 * 1024 * 1024) {
            return sendResponse({ error: 'PDF too large' });
          }
          // chunked base64 — avoids call-stack limits on big files
          const bytes = new Uint8Array(buf);
          let bin = '';
          const CHUNK = 0x8000;
          for (let i = 0; i < bytes.length; i += CHUNK) {
            bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
          }
          console.log(`[VHC BG v${VERSION}] CV PDF fetched: ${bytes.length} bytes (${url.substring(0, 80)})`);
          return sendResponse({ isPdf: true, base64: btoa(bin), bytes: bytes.length });
        }
        if (/msword|officedocument/.test(ctype)) {
          return sendResponse({ isDoc: true, contentType: ctype });
        }
        const html = await resp.text();
        const text = html
          .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
          .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
          .replace(/<[^>]+>/g, ' ')
          .replace(/&nbsp;/gi, ' ')
          .replace(/\s+/g, ' ')
          .trim();
        return sendResponse({ isPdf: false, text });
      } catch (e) {
        sendResponse({ error: e.message });
      }
    })();
    return true;
  }

  if (request.action === 'injectPdfJs') {
    // v6.3.0 — lazy-load pdf.js into the tab's isolated world only when a
    // PDF CV actually needs parsing (keeps every normal page load light).
    (async () => {
      try {
        const tabId = sender.tab?.id;
        if (!tabId) return sendResponse({ ok: false, error: 'no tab' });
        await chrome.scripting.executeScript({
          target: { tabId },
          files: ['vendor/pdf.min.js'],
        });
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: e.message });
      }
    })();
    return true;
  }

  if (request.action === 'fetchIframeSrc') {
    (async () => {
      try {
        const url = request.url;
        if (!url) return sendResponse({ text: '', error: 'No URL provided' });

        console.log(`[VHC BG v${VERSION}] Fetching iframe src: ${url.substring(0, 100)}`);
        const response = await fetch(url, {
          credentials: 'include',
          headers: { 'Accept': 'text/html,application/xhtml+xml,*/*' }
        });

        if (!response.ok) {
          return sendResponse({ text: '', error: `HTTP ${response.status}` });
        }

        const html = await response.text();
        // Strip HTML tags to get plain text content
        const text = html
          .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
          .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
          .replace(/<[^>]+>/g, ' ')
          .replace(/&nbsp;/gi, ' ')
          .replace(/&amp;/gi, '&')
          .replace(/&lt;/gi, '<')
          .replace(/&gt;/gi, '>')
          .replace(/&#\d+;/g, ' ')
          .replace(/\s+/g, ' ')
          .trim();

        console.log(`[VHC BG v${VERSION}] Iframe fetch result: ${text.length} chars from ${url.substring(0, 60)}`);
        sendResponse({ text: text.substring(0, 15000), url: url });
      } catch (e) {
        console.warn(`[VHC BG v${VERSION}] Iframe fetch error:`, e.message);
        sendResponse({ text: '', error: e.message });
      }
    })();
    return true; // Keep message channel open for async response
  }

  if (request.action === 'enqueueCapture') {
    enqueueCapture(request.data)
      .then(r => { sendResponse(r); drainCaptureQueue(); })
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // v6.0.1: BG-tab contact rescue — content script in a hidden tab asks us to
  // briefly activate it so Naukri renders the contact section. We remember the
  // user's current tab and restore it on 'visibilityAssistDone' (or after a
  // 15s safety timeout if the content script dies mid-assist).
  if (request.action === 'visibilityAssist') {
    (async () => {
      try {
        const capTabId = sender?.tab?.id;
        const capWinId = sender?.tab?.windowId;
        if (!capTabId) return sendResponse({ granted: false });
        const [prevActive] = await chrome.tabs.query({ active: true, windowId: capWinId });
        visibilityAssistState[capTabId] = {
          prevTabId: prevActive && prevActive.id !== capTabId ? prevActive.id : null,
          timer: setTimeout(() => restoreAfterAssist(capTabId), 15000),
        };
        await chrome.tabs.update(capTabId, { active: true });
        console.log(`[VHC BG v${VERSION}] Visibility assist granted for tab ${capTabId}`);
        sendResponse({ granted: true });
      } catch (e) {
        sendResponse({ granted: false, error: e.message });
      }
    })();
    return true;
  }

  if (request.action === 'visibilityAssistDone') {
    restoreAfterAssist(sender?.tab?.id);
    sendResponse({ ok: true });
    return false;
  }

  // NEW: Bulk enqueue — accepts array of raw profiles (from list/search page scrape)
  if (request.action === 'bulkEnqueue') {
    bulkEnqueue(request.data)
      .then(r => { sendResponse(r); drainCaptureQueue(); })
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  if (request.action === 'getHistory') {
    chrome.storage.local.get(['captureHistory'], (r) => {
      sendResponse({ history: (r.captureHistory || []).slice().reverse() }); // newest first
    });
    return true;
  }

  if (request.action === 'clearHistory') {
    serializeCaptureMutation(() => writeQueueStorage({ captureHistory: [] }))
      .then(() => sendResponse({ success: true }))
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  if (request.action === 'getQueueStatus') {
    getQueueStatus().then(sendResponse);
    return true;
  }

  if (request.action === 'clearDeadLetter') {
    serializeCaptureMutation(() => writeQueueStorage({ deadLetterQueue: [] }))
      .then(() => sendResponse({ success: true }))
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  if (request.action === 'retryDeadLetter') {
    retryDeadLetter().then(sendResponse).catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  if (request.action === 'getStats') {
    getStats().then(sendResponse);
    return true;
  }

  if (request.action === 'login') {
    handleLogin(request.data).then(sendResponse);
    return true;
  }

  if (request.action === 'logout') {
    handleLogout().then(sendResponse);
    return true;
  }

  if (request.action === 'checkAuth') {
    checkAuth().then(sendResponse);
    return true;
  }

  if (request.action === 'apiProxy') {
    handleApiProxy(request.data)
      .then(sendResponse)
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // Legacy: direct captureProfile (still supported for backward compat)
  if (request.action === 'captureProfile') {
    handleProfileCapture(request.data)
      .then(sendResponse)
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  if (request.action === 'setActiveJob') {
    chrome.storage.local.set({ vhc_active_job: request.data }, () => {
      sendResponse({ success: true });
      notifyPopup({ action: 'activeJobUpdated', job: request.data });
    });
    return true;
  }

  if (request.action === 'clearActiveJob') {
    chrome.storage.local.remove(['vhc_active_job'], () => {
      sendResponse({ success: true });
      notifyPopup({ action: 'activeJobUpdated', job: null });
    });
    return true;
  }

  if (request.action === 'getActiveJob') {
    chrome.storage.local.get(['vhc_active_job'], (r) => {
      sendResponse({ job: r.vhc_active_job || null });
    });
    return true;
  }

  // ── Fetch recruiter's assigned mandates for dropdown ──
  if (request.action === 'fetchMandates') {
    fetchMandates().then(sendResponse).catch(e => sendResponse({ mandates: [] }));
    return true;
  }

  // ── Evaluate candidate fit against a mandate ──
  if (request.action === 'evaluateFit') {
    evaluateFit(request.data)
      .then(sendResponse)
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // ── Hover-card preview: candidate snapshot + match vs active mandate ──
  // (v6.1.0) Used by hover-preview.js on "Already in Database" badges.
  if (request.action === 'getCandidatePreview') {
    getCandidatePreview(request.candidate_id)
      .then(sendResponse)
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  if (request.action === 'listLiveMandates') {
    listLiveMandates()
      .then(sendResponse)
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  if (request.action === 'addToMandate') {
    addCandidateToMandate(request.candidate_id, request.job_id)
      .then(sendResponse)
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }
});

// ═══ v6.3.1 — live mandates + add-to-mandate (hover-card dropdown) ═══
let _mandatesCache = { at: 0, data: null };

async function listLiveMandates() {
  if (_mandatesCache.data && Date.now() - _mandatesCache.at < 60000) {
    return { success: true, mandates: _mandatesCache.data, cached: true };
  }
  let auth = await getAuth();
  if (!auth) return { success: false, error: 'auth' };
  const url = `${auth.apiUrl}/api/jobs?status=active`;
  let r = await fetchPreview(url, auth);
  if (r.status === 401) {
    auth = await getAuth();
    if (!auth) return { success: false, error: 'auth' };
    r = await fetchPreview(url, auth);
  }
  if (!r.ok || !Array.isArray(r.json)) {
    return { success: false, error: r.error || `HTTP ${r.status}` };
  }
  const mandates = r.json.map(j => ({
    id: j.id,
    title: j.title || j.job_title || 'Untitled',
    location: j.location || '',
    company: j.company_name || j.public_company_alias || '',
  }));
  _mandatesCache = { at: Date.now(), data: mandates };
  console.log(`[VHC BG v${VERSION}] Live mandates: ${mandates.length}`);
  return { success: true, mandates };
}

async function addCandidateToMandate(candidateId, jobId) {
  if (!candidateId || !jobId) return { success: false, error: 'missing_ids' };
  let auth = await getAuth();
  if (!auth) return { success: false, error: 'auth' };
  const doPost = async (a) => {
    try {
      const resp = await fetch(`${a.apiUrl}/api/matching/shortlist`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${a.token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          candidate_id: candidateId,
          job_id: jobId,
          notes: 'Added via Naukri extension (hover card)',
        }),
      });
      let json = null;
      try { json = await resp.json(); } catch (_) {}
      return { status: resp.status, ok: resp.ok, json };
    } catch (e) {
      return { status: 0, ok: false, json: null, netError: e.message };
    }
  };
  let r = await doPost(auth);
  if (r.status === 401) {
    auth = await getAuth();
    if (!auth) return { success: false, error: 'auth' };
    r = await doPost(auth);
  }
  if (r.ok) {
    console.log(`[VHC BG v${VERSION}] Shortlisted ${candidateId} → job ${jobId}`);
    return { success: true };
  }
  const detail = (r.json && (r.json.detail || r.json.message)) || r.netError || `HTTP ${r.status}`;
  return { success: false, status: r.status, error: detail };
}

// ═══════════════════════════════════════════════════════════════════════════════
// QUEUE MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Add a raw profile (just-scraped, not yet AI-processed) to the captureQueue.
 * Returns immediately — processing happens asynchronously in drainCaptureQueue().
 */
function serializeCaptureMutation(work) {
  const pending = (serializeCaptureMutation._tail || Promise.resolve()).then(work, work);
  serializeCaptureMutation._tail = pending.then(() => undefined, () => undefined);
  return pending;
}

function readQueueStorage(keys) {
  return new Promise((resolve, reject) => chrome.storage.local.get(keys, result => {
    if (chrome.runtime.lastError) reject(new Error('Queue storage read failed'));
    else resolve(result);
  }));
}

function writeQueueStorage(values) {
  return new Promise((resolve, reject) => chrome.storage.local.set(values, () => {
    if (chrome.runtime.lastError) reject(new Error('Queue storage write failed'));
    else resolve();
  }));
}

async function freezeCapturePayload(item, payload) {
  if (!item?._queueId || !/^[A-Za-z0-9_-]{8,128}$/.test(item._queueId)) {
    throw new Error('Capture operation ID is missing or invalid');
  }
  return serializeCaptureMutation(async () => {
    const stored = await readQueueStorage(['captureQueue', 'offlineQueue']);
    const capture = stored.captureQueue || [];
    const offline = stored.offlineQueue || [];
    const queued = [...capture, ...offline].find(entry => entry._queueId === item._queueId);
    if (!queued) throw new Error('Capture operation is no longer queued');
    const existing = queued._capturePayload || item._capturePayload;
    if (existing && existing.capture_request_id !== item._queueId) {
      throw new Error('Frozen capture operation ID does not match');
    }
    const frozen = JSON.parse(JSON.stringify(existing || sanitizeDeep({ ...payload, capture_request_id: item._queueId })));
    if (!queued._capturePayload) {
      const retain = entry => entry._queueId === item._queueId ? { ...entry, _capturePayload: frozen } : entry;
      await writeQueueStorage({ captureQueue: capture.map(retain), offlineQueue: offline.map(retain) });
    }
    // Assign only after successful persistence: storage failure must stop POST.
    item._capturePayload = JSON.parse(JSON.stringify(frozen));
    return JSON.parse(JSON.stringify(frozen));
  });
}

function isSavedCaptureResult(result) {
  if (!result || result.success !== true) return false;
  if (typeof result.observation_id !== 'string' ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(result.observation_id)) return false;
  if (result.action === 'pending_review') return result.candidate_id === null;
  return result.action === 'exists' && typeof result.candidate_id === 'string' && !!result.candidate_id.trim();
}

async function enqueueCapture(profileData) {
  if (!profileData || typeof profileData !== 'object' || Array.isArray(profileData)) {
    return { success: false, error: 'Invalid profile payload' };
  }
  // An operation ID identifies a delivery/retry, never a candidate. A caller
  // retrying the same delivery may provide the returned queueId as _queueId.
  const suppliedId = profileData._queueId;
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (suppliedId !== undefined && (typeof suppliedId !== 'string' || !uuidPattern.test(suppliedId))) {
    return { success: false, error: 'Invalid operation ID: _queueId must be a UUID' };
  }
  const operationId = suppliedId ? suppliedId.toLowerCase() : crypto.randomUUID();
  const payload = { ...profileData, _queueId: operationId };

  const write = () => new Promise(resolve => {
    chrome.storage.sync.get(['vhc_active_mandate'], syncResult => {
      if (chrome.runtime.lastError) {
        resolve({ success: false, error: 'Storage read failed', queueId: operationId });
        return;
      }
      const activeMandateId = syncResult.vhc_active_mandate || null;
      chrome.storage.local.get(['captureQueue', 'offlineQueue', 'deadLetterQueue'], result => {
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: 'Storage read failed', queueId: operationId });
          return;
        }
        if (['captureQueue', 'offlineQueue', 'deadLetterQueue'].some(key => result[key] != null && !Array.isArray(result[key]))) {
          resolve({ success: false, error: 'Invalid capture queue data', queueId: operationId });
          return;
        }
        const queue = result.captureQueue || [];
        const allOperations = [...queue, ...(result.offlineQueue || []), ...(result.deadLetterQueue || [])];
        if (suppliedId && allOperations.some(item => item._queueId === operationId)) {
          resolve({ success: true, action: 'duplicate', queued: queue.length, queueId: operationId });
          return;
        }
        if (queue.length >= CONFIG.MAX_CAPTURE_QUEUE_SIZE) {
          resolve({ success: false, error: 'Queue full', queued: queue.length, queueId: operationId });
          return;
        }
        // A generated UUID collision is not permission to discard a profile.
        if (allOperations.some(item => item._queueId === operationId)) {
          resolve({ success: false, error: 'Operation ID collision; retry with a new operation', queued: queue.length });
          return;
        }
        const entry = {
          ...payload, _attempts: 0, _queued_at: new Date().toISOString(),
          _status: 'pending', _mandate_id: activeMandateId,
        };
        chrome.storage.local.set({ captureQueue: [...queue, entry] }, () => {
          if (chrome.runtime.lastError) {
            resolve({ success: false, error: 'Storage write failed', queueId: operationId });
            return;
          }
          resolve({ success: true, action: 'queued', queued: queue.length + 1, queueId: operationId });
        });
      });
    });
  });
  // Chrome storage has no atomic append. Serialize all enqueueCapture/bulkEnqueue
  // deliveries in this worker so simultaneous additions do not overwrite each other.
  return serializeCaptureMutation(write);
}

/**
 * Bulk enqueue distinct capture operations, preserving profiles with missing,
 * reused or rotating provider identifiers. Summary includes per-input queue IDs.
 */
async function bulkEnqueue(profiles) {
  if (!Array.isArray(profiles) || profiles.length === 0) {
    return { success: false, error: 'No profiles provided' };
  }
  let queued = 0, duplicates = 0, dropped = 0, total = 0;
  const results = [];
  for (let index = 0; index < profiles.length; index++) {
    const profile = profiles[index];
    const result = await enqueueCapture(profile && typeof profile === 'object' && !Array.isArray(profile)
      ? { ...profile, _bulk: true } : profile);
    results.push({ index, ...result });
    if (result.action === 'queued') queued++;
    else if (result.action === 'duplicate') duplicates++;
    else dropped++;
    if (Number.isInteger(result.queued)) total = result.queued;
  }
  notifyPopup({ action: 'queueUpdated' });
  const storageFailed = results.some(result => result.error?.startsWith('Storage'));
  return { success: !storageFailed, queued, duplicates, dropped, total, results,
    ...(storageFailed ? { error: 'One or more capture operations could not be saved' } : {}) };
}

/**
 * Main drain loop — pulls pending items from captureQueue, runs AI extraction,
 * then POSTs to databank. Runs up to DRAIN_CONCURRENCY profiles in parallel.
 */
async function drainCaptureQueue() {
  if (isDraining) return;
  if (!navigator.onLine) return;

  const auth = await getAuth();
  if (!auth) return;

  isDraining = true;
  console.log(`[VHC BG v${VERSION}] Starting drain cycle`);

  try {
    while (true) {
      // Pull a batch of pending items
      const batch = await pickPendingBatch(CONFIG.DRAIN_CONCURRENCY);
      if (batch.length === 0) break;

      console.log(`[VHC BG v${VERSION}] Processing batch of ${batch.length}`);

      // Mark them as processing (prevents double-pickup)
      await markStatus(batch.map(b => b._queueId), 'processing');

      // Process all in batch concurrently
      await Promise.allSettled(batch.map(item => processSingleCapture(item, auth)));

      // Small breath between batches
      await sleep(CONFIG.DRAIN_INTERVAL_MS);
    }
  } catch (err) {
    console.error(`[VHC BG v${VERSION}] Drain error:`, err);
  } finally {
    isDraining = false;
    // Notify popup to refresh queue counts
    notifyPopup({ action: 'queueUpdated' });
    console.log(`[VHC BG v${VERSION}] Drain cycle complete`);
  }
}

/**
 * Process one profile through the full pipeline:
 *   1. AI extraction  (apiProxy → /api/extension/ai-extract)
 *   2. Databank POST  (/api/extension/capture)
 */
async function processSingleCapture(item, auth) {
  const label = item.name || item.naukri_profile_id || item._queueId;
  console.log(`[VHC BG v${VERSION}] Processing: ${label} (attempt ${item._attempts + 1})`);

  try {
    let capturePayload;
    let finalName = item.name || 'Unknown';

    // ═══ 3-LAYER PATH: DOM fields available → skip AI-extract entirely ═══
    if (item._capturePayload) {
      // A retry resumes the exact submitted operation, without re-extracting
      // a potentially different person or generating a new AI interpretation.
      capturePayload = item._capturePayload;
      finalName = capturePayload.name;
    } else if (item.dom_fields && item.dom_fields._dom_scraped) {
      console.log(`[VHC BG v${VERSION}] 3-LAYER: Using DOM-scraped fields for ${label} (${item.dom_fields._dom_field_count} fields)`);

      const d = item.dom_fields;
      finalName = d.name || item.name || 'Unknown';

      capturePayload = {
        naukri_profile_id:       item.naukri_profile_id,
        naukri_profile_url:      item.naukri_profile_url || '',
        dom_scraped:             true,
        name:                    finalName,
        first_name:              finalName?.split(/[\s.]+/)[0] || null,
        last_name:               finalName?.split(/[\s.]+/).slice(-1)[0] || null,
        email:                   item.email || null,
        phone:                   item.phone || '',  // Likely empty — Naukri masks phone
        headline:                null,
        profile_summary:         d.profile_summary || null,
        current_company:         d.current_company || null,
        current_designation:     d.current_designation || null,
        total_experience_years:  d.total_experience_years || null,
        total_experience_months: d.total_experience_years ? Math.round(d.total_experience_years * 12) : null,
        total_experience_display:d.total_experience_years ? `${d.total_experience_years} years` : null,
        key_skills:              d.key_skills || [],
        work_experience:         d.work_experience || [],
        education:               d.education || [],
        career_preferences: {
          current_salary:    d.current_salary || null,
          expected_salary:   d.expected_salary || null,
          notice_period:     d.notice_period || null,
          notice_period_days:d.notice_period_days || null,
          current_location:  d.current_location || null,
          preferred_locations: d.preferred_locations || [],
        },
        scraped_at:            item._queued_at || new Date().toISOString(),
        raw_profile_text:      (item.raw_text || '').substring(0, 8000),
        page_text:             (item.raw_text || '').substring(0, 3000),
        extension_version:     VERSION,
        source_platform:       item.source_platform || 'naukri',
        active_job_id:         item.active_job_id || null,
        mandate_id:            item._mandate_id || null,
      };

    } else {
      // ═══ STANDARD PATH: AI extraction → capture ═══
      // ── Step 1: AI Extraction ──
      const aiResponse = await fetch(`${auth.apiUrl}/api/extension/ai-extract`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${auth.token}`
        },
        body: JSON.stringify(sanitizeDeep({
          raw_text:             (item.raw_text || '').substring(0, 15000),
          page_url:             item.naukri_profile_url || '',
          page_title:           item.page_title || '',
          naukri_profile_id:    item.naukri_profile_id,
          dom_extracted_name:   item.name || null,
          dom_extracted_email:  item.email || null,
          dom_extracted_phone:  item.phone || null,
          recruiter_email:      item.recruiter_email || null,
          recruiter_phone:      item.recruiter_phone || null,
        }))
      });

      if (aiResponse.status === 401) {
        const refreshed = await refreshAccessToken(auth.apiUrl);
        if (refreshed) {
          await requeueWithFailure(item, 'Token refreshed — will retry');
          return;
        }
        await requeueWithFailure(item, 'Session expired');
        return;
      }

      if (!aiResponse.ok) {
        const errText = await aiResponse.text();
        throw new Error(`AI extract HTTP ${aiResponse.status}: ${errText.substring(0, 100)}`);
      }

      const aiResult = await aiResponse.json();

      if (!aiResult.success || !aiResult.profile_data) {
        throw new Error(aiResult.error || 'AI returned no profile data');
      }

      const profileData = aiResult.profile_data;
      if (!profileData.name && !item.name) {
        throw new Error('No candidate name found');
      }

      // ── Step 2: Build final capture payload ──
      const rPhone = (item.phone || '').replace(/[\s.+\-()]/g, '').slice(-10);
      const rEmail = (item.recruiter_email || '').toLowerCase().trim();

      const aiFallbackEmail = profileData.email && profileData.email.toLowerCase().trim() !== rEmail
        ? profileData.email : null;
      const aiFallbackPhone = profileData.phone && profileData.phone.replace(/[\s.+\-()]/g, '').slice(-10) !== rPhone
        ? profileData.phone : null;

      const finalName_std = item.name || profileData.name;
      finalName = finalName_std;
      capturePayload = {
        naukri_profile_id:       item.naukri_profile_id,
        naukri_profile_url:      item.naukri_profile_url || '',
        name:                    finalName,
        first_name:              finalName?.split(/[\s.]+/)[0] || null,
        last_name:               finalName?.split(/[\s.]+/).slice(-1)[0] || null,
        email:                   item.email || aiFallbackEmail || null,
        phone:                   item.phone || aiFallbackPhone || null,
        headline:                profileData.headline || null,
        resume_headline:         profileData.headline || null,
        profile_summary:         profileData.profile_summary || null,
        current_company:         profileData.current_company || null,
        current_designation:     profileData.current_designation || null,
        current_industry:        profileData.current_industry || null,
        total_experience_years:  profileData.total_experience_years || null,
        total_experience_months: profileData.total_experience_years ? Math.round(profileData.total_experience_years * 12) : null,
        total_experience_display:profileData.total_experience_years ? `${profileData.total_experience_years} years` : null,
        work_experience:         profileData.work_experience || [],
        education:               profileData.education || [],
        key_skills:              profileData.key_skills || [],
        it_skills:               profileData.it_skills || [],
        certifications:          profileData.certifications || [],
        projects:                profileData.projects || [],
        languages:               profileData.languages || [],
        online_profiles:         profileData.online_profiles || [],
        linkedin_url:            (profileData.online_profiles || []).find(p => p.platform === 'LinkedIn')?.url || null,
        personal_details: {
          date_of_birth:   profileData.date_of_birth || null,
          gender:          profileData.gender || null,
          marital_status:  profileData.marital_status || null,
          nationality:     profileData.nationality || null,
          category:        profileData.category || null,
        },
        career_preferences: {
          current_salary:    profileData.current_salary || null,
          expected_salary:   profileData.expected_salary || null,
          notice_period:     profileData.notice_period || null,
          current_location:  profileData.location || null,
          preferred_locations: profileData.preferred_locations || [],
        },
        highest_qualification: (profileData.education || [])[0]?.degree || null,
        scraped_at:            item._queued_at || new Date().toISOString(),
        raw_profile_text:      (item.raw_text || '').substring(0, 8000),
        extension_version:     VERSION,
        source_platform:       item.source_platform || 'naukri',
        active_job_id:         item.active_job_id || null,
        mandate_id:            item._mandate_id || null,
      };
    }

    // ── Step 3: POST to databank (async + poll, v5.5.10) ──
    capturePayload = await freezeCapturePayload(item, capturePayload);
    const asyncResult = await postCaptureAsync(auth, capturePayload);

    if (asyncResult._httpResponse?.status === 401) {
      const refreshed = await refreshAccessToken(auth.apiUrl);
      if (refreshed) {
        await requeueWithFailure(item, 'Token refreshed — will retry');
        return;
      }
      await requeueWithFailure(item, 'Session expired during capture');
      return;
    }

    const captureResult = asyncResult._result;
    if (!isSavedCaptureResult(captureResult)) throw new Error('Capture response did not confirm a saved candidate or observation');

    // A review observation is saved successfully but is not a candidate record.
    const historyResult = await addToHistory({
      name:              finalName,
      queue_id:          item._queueId,
      history_scope:     identityHistoryScope(auth),
      naukri_profile_id: item.naukri_profile_id,
      naukri_profile_url: item.naukri_profile_url,
      action:            captureResult.action,
      candidate_id:      captureResult.candidate_id,
      observation_id:    captureResult.observation_id,
      message:           captureResult.message,
      email:             item.email || null,
      phone:             item.phone || null,
      _bulk:             item._bulk || false,
      // Context for the activity log only; never offline identity evidence.
      current_employer:  item.dom_fields?.current_company || capturePayload?.current_company || null,
      designation:       item.dom_fields?.current_designation || capturePayload?.current_designation || null,
      location:          item.dom_fields?.current_location || capturePayload?.career_preferences?.current_location || null,
      education:         Array.isArray(capturePayload?.education) ? (capturePayload.education[0]?.degree || capturePayload.education[0]?.institution || null) : null,
      experience_years:  item.dom_fields?.total_experience_years || capturePayload?.total_experience_years || null,
    });
    if (historyResult.added) await updateStats(captureResult.action);
    await removeFromCaptureQueue(item._queueId);

    const candidateId = captureResult.action === 'pending_review' ? null : captureResult.candidate_id;

    // Saving/replaying an observation authorizes no candidate side effects.
    // Even `exists` can be a late retry after manual review. Resume uploads,
    // shortlisting and fit evaluation require a separate explicit workflow.

    const actionLabels = { created: '✅ Added', updated: '🔄 Updated', exists: '✓ Already saved', pending_review: 'Saved for identity review' };
    console.log(`[VHC BG v${VERSION}] ${actionLabels[captureResult.action] || '✅'}: ${finalName}`);

    // Notify any open popup
    notifyPopup({
      action: 'captureComplete',
      name: finalName,
      result: captureResult.action,
      candidate_id: candidateId,
      observation_id: captureResult.observation_id || null,
      message: captureResult.message || null,
    });

  } catch (err) {
    console.error(`[VHC BG v${VERSION}] Failed: ${label} —`, err.message);

    const isNetworkError = err.name === 'TypeError' || err.message.includes('fetch') || err.message.includes('network');

    if (isNetworkError) {
      try {
        await moveToOfflineQueue(item);
      } catch (storageError) {
        await requeueWithFailure(item, storageError.message);
      }
    } else {
      await requeueWithFailure(item, err.message);
      // Log to history on final failure (dead-letter)
      const attempts = (item._attempts || 0) + 1;
      if (attempts >= CONFIG.RETRY_MAX) {
        await addToHistory({
          name:              item.name || label,
          naukri_profile_id: item.naukri_profile_id,
          naukri_profile_url: item.naukri_profile_url,
          action:            'failed',
          error:             err.message,
          email:             item.email || null,
          phone:             item.phone || null,
          _bulk:             item._bulk || false,
          // Multi-signal fields for offline composite matching (v5.5.6+)
          current_employer:  item.dom_fields?.current_company || null,
          designation:       item.dom_fields?.current_designation || null,
          location:          item.dom_fields?.current_location || null,
          education:         null,
          experience_years:  item.dom_fields?.total_experience_years || null,
        });
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CV FILE UPLOAD
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Fetch a CV/resume file from a job portal URL and upload it to the candidate record.
 * Called after a successful capture when item.cv_download_url is set.
 *
 * Flow:
 *   1. Fetch the file from the portal URL (using the user's auth cookies via fetch)
 *   2. Convert to base64
 *   3. POST to /api/extension/cv-upload with candidate_id + base64 content
 *
 * Failures here are non-fatal — logged as warnings, capture still counted as success.
 */
async function uploadCVFile(cvUrl, candidateId, auth) {
  console.log(`[VHC BG v${VERSION}] CV upload: fetching ${cvUrl.substring(0, 80)}...`);

  // Fetch the CV file from the source portal
  const fileResponse = await fetch(cvUrl, {
    credentials: 'include',   // send portal cookies to authenticate the download
    headers: { 'Accept': 'application/pdf,application/octet-stream,*/*' }
  });

  if (!fileResponse.ok) {
    throw new Error(`CV fetch HTTP ${fileResponse.status}`);
  }

  // Determine file type from Content-Type or URL extension
  const contentType = fileResponse.headers.get('content-type') || 'application/octet-stream';
  const urlLower = cvUrl.toLowerCase();
  const extension = urlLower.includes('.pdf') ? 'pdf' :
                    urlLower.includes('.doc') ? (urlLower.includes('.docx') ? 'docx' : 'doc') :
                    contentType.includes('pdf') ? 'pdf' : 'pdf'; // default to pdf

  // Convert to base64
  const arrayBuffer = await fileResponse.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const base64Data = btoa(binary);

  if (!base64Data || base64Data.length < 100) {
    throw new Error('CV file appears empty');
  }

  console.log(`[VHC BG v${VERSION}] CV upload: ${base64Data.length} base64 chars, type=${extension}`);

  // Upload to VHC API
  const uploadResponse = await fetch(`${auth.apiUrl}/api/extension/cv-upload`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${auth.token}`
    },
    body: JSON.stringify({
      candidate_id:  candidateId,
      file_data:     base64Data,
      file_type:     extension,
      source_url:    cvUrl,
    })
  });

  if (!uploadResponse.ok) {
    const errText = await uploadResponse.text();
    throw new Error(`CV upload HTTP ${uploadResponse.status}: ${errText.substring(0, 100)}`);
  }

  const uploadResult = await uploadResponse.json();
  console.log(`[VHC BG v${VERSION}] CV uploaded successfully for candidate ${candidateId}:`, uploadResult.filename || 'ok');
  return uploadResult;
}

// ═══════════════════════════════════════════════════════════════════════════════
// JOB SHORTLIST
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Shortlist a captured candidate against the recruiter's active job.
 * Called after successful capture when item.active_job_id is set.
 *
 * Non-fatal: if the shortlist call fails, capture still succeeds.
 * This allows captures to work even if the job no longer exists.
 */
async function shortlistCandidate(candidateId, jobId, auth) {
  console.log(`[VHC BG v${VERSION}] Shortlisting candidate ${candidateId} to job ${jobId}...`);

  const response = await fetch(`${auth.apiUrl}/api/extension/shortlist`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${auth.token}`
    },
    body: JSON.stringify({
      candidate_id: candidateId,
      job_id:       jobId,
    })
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Shortlist HTTP ${response.status}: ${errText.substring(0, 100)}`);
  }

  const result = await response.json();
  const action = result.action || 'shortlisted';
  console.log(`[VHC BG v${VERSION}] Shortlist ${action}: candidate ${candidateId} → job ${jobId}`);
  return result;
}

/**
 * Pick up to `count` pending items from captureQueue (status: pending, retry-due)
 */
async function pickPendingBatch(count) {
  return new Promise((resolve) => {
    chrome.storage.local.get(['captureQueue'], (result) => {
      const queue = result.captureQueue || [];
      const now = Date.now();
      const batch = queue
        .filter(item =>
          item._status === 'pending' ||
          (item._status === 'retry' && item._retry_after && now >= item._retry_after)
        )
        .slice(0, count);
      resolve(batch);
    });
  });
}

/**
 * Update status of queue items by queueId
 */
async function markStatus(queueIds, status, extra = {}) {
  return serializeCaptureMutation(async () => {
    const result = await readQueueStorage(['captureQueue']);
    const queue = (result.captureQueue || []).map(item =>
      queueIds.includes(item._queueId) ? { ...item, ...extra, _queueId: item._queueId, _status: status } : item);
    await writeQueueStorage({ captureQueue: queue });
  });
}

/** Remove only this operation, preserving concurrent appends and frozen bodies. */
async function removeFromCaptureQueue(queueId) {
  return serializeCaptureMutation(async () => {
    const result = await readQueueStorage(['captureQueue']);
    await writeQueueStorage({ captureQueue: (result.captureQueue || []).filter(item => item._queueId !== queueId) });
  });
}

async function requeueWithFailure(item, reason) {
  const attempts = (item._attempts || 0) + 1;
  if (attempts >= CONFIG.RETRY_MAX) {
    await serializeCaptureMutation(async () => {
      const result = await readQueueStorage(['captureQueue', 'deadLetterQueue']);
      const current = (result.captureQueue || []).find(entry => entry._queueId === item._queueId) || item;
      const failed = { ...current, _attempts: attempts, _fail_reason: reason, _failed_at: new Date().toISOString() };
      const dead = (result.deadLetterQueue || []).filter(entry => entry._queueId !== item._queueId);
      await writeQueueStorage({
        captureQueue: (result.captureQueue || []).filter(entry => entry._queueId !== item._queueId),
        deadLetterQueue: [...dead, failed].slice(-50),
      });
    });
    return;
  }
  await markStatus([item._queueId], 'retry', {
    _attempts: attempts, _last_error: reason,
    _retry_after: Date.now() + CONFIG.RETRY_BACKOFF_MS * attempts,
  });
}

/** Transfer one operation atomically; provider IDs never determine uniqueness. */
async function moveToOfflineQueue(item) {
  return serializeCaptureMutation(async () => {
    const result = await readQueueStorage(['captureQueue', 'offlineQueue']);
    const capture = result.captureQueue || [];
    const offline = result.offlineQueue || [];
    const current = capture.find(entry => entry._queueId === item._queueId) || item;
    if (!current._queueId) throw new Error('Offline operation ID missing');
    const existing = offline.find(entry => entry._queueId === current._queueId);
    if (!existing && offline.length >= CONFIG.MAX_OFFLINE_QUEUE_SIZE) throw new Error('Offline queue full');
    await writeQueueStorage({
      captureQueue: capture.filter(entry => entry._queueId !== current._queueId),
      offlineQueue: existing ? offline : [...offline, { ...current, _offline_queued_at: new Date().toISOString() }],
    });
  });
}

/**
 * Add to dead letter queue (failed after max retries — reviewable in popup)
 */
async function addToDeadLetter(item) {
  return serializeCaptureMutation(async () => {
    const result = await readQueueStorage(['deadLetterQueue']);
    const queue = (result.deadLetterQueue || []).filter(entry => entry._queueId !== item._queueId);
    await writeQueueStorage({ deadLetterQueue: [...queue, item] });
  });
}

/**
 * Re-enqueue dead letter items back into captureQueue for retry
 */
async function retryDeadLetter() {
  const outcome = await serializeCaptureMutation(async () => {
    const stored = await readQueueStorage(['captureQueue', 'offlineQueue', 'deadLetterQueue']);
    const capture = stored.captureQueue || [];
    const activeIds = new Set([...capture, ...(stored.offlineQueue || [])].map(item => item._queueId));
    const remaining = [];
    let requeued = 0;
    for (const item of stored.deadLetterQueue || []) {
      if (activeIds.has(item._queueId)) continue;
      if (capture.length >= CONFIG.MAX_CAPTURE_QUEUE_SIZE) { remaining.push(item); continue; }
      const operationId = item._queueId || crypto.randomUUID();
      capture.push({ ...item, _queueId: operationId, _attempts: 0, _status: 'pending', _fail_reason: null, _retry_after: null });
      activeIds.add(operationId);
      requeued++;
    }
    await writeQueueStorage({ captureQueue: capture, deadLetterQueue: remaining });
    return { success: true, requeued, remaining: remaining.length };
  });
  if (outcome.requeued) drainCaptureQueue();
  return outcome;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SESSION KEEP-ALIVE
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Ping /api/auth/me every SESSION_PING_MINUTES to keep the token alive
 * and verify it's still valid. If 401 → try to silently re-login using
 * stored credentials (if available). This prevents the extension from
 * ever logging out during a long capture session.
 */
async function pingSession() {
  const auth = await getAuth();
  if (!auth) return; // not logged in, nothing to keep alive

  try {
    const res = await fetch(`${auth.apiUrl}/api/auth/me`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${auth.token}` }
    });

    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      // If server returns a refreshed token, update it
      if (data.access_token) {
        await new Promise(r => chrome.storage.sync.set({ vhc_token: data.access_token }, r));
        console.log(`[VHC BG v${VERSION}] Session refreshed via ping`);
      } else {
        console.log(`[VHC BG v${VERSION}] Session still valid`);
      }
      // Fire-and-forget version check-in for admin telemetry
      extensionVersionCheckin(auth).catch(() => {});
      return;
    }

    if (res.status === 401) {
      console.warn(`[VHC BG v${VERSION}] Session expired — attempting token refresh`);
      const refreshed = await refreshAccessToken(auth.apiUrl);
      if (!refreshed) {
        console.warn(`[VHC BG v${VERSION}] Token refresh failed — attempting silent re-login`);
        await silentReLogin(auth.apiUrl);
      }
    }
  } catch (err) {
    // Network error during ping — don't logout, just wait for next ping
    console.warn(`[VHC BG v${VERSION}] Session ping failed (network?):`, err.message);
  }
}

// ── Version Check-In ──────────────────────────────────────────────────────────
// Reports this extension's version to the backend so admins can see who's on what.
// Also returns latest_version — if the extension is behind, we could show a banner.
// For CRX installs, Chrome auto-updates silently; this telemetry is informational only.
async function extensionVersionCheckin(auth) {
  try {
    const manifestInfo = chrome.runtime.getManifest();
    const updateType = manifestInfo.update_url ? 'crx_auto_update' : 'unpacked';
    await fetch(`${auth.apiUrl}/api/extension/checkin`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${auth.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ version: manifestInfo.version, install_type: updateType }),
    });
  } catch (_e) {
    // Silent — telemetry is best-effort
  }
}

/**
 * Try to refresh the access token using the stored refresh token.
 * Returns true if successful, false otherwise.
 */
async function refreshAccessToken(apiUrl) {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['vhc_refresh_token'], async (r) => {
      if (!r.vhc_refresh_token) {
        console.log(`[VHC BG v${VERSION}] No refresh token stored`);
        return resolve(false);
      }
      try {
        const res = await fetch(`${apiUrl}/api/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: r.vhc_refresh_token })
        });
        if (res.ok) {
          const data = await res.json();
          if (data.access_token) {
            await new Promise(r2 => chrome.storage.sync.set({
              vhc_token: data.access_token,
              vhc_refresh_token: data.refresh_token || r.vhc_refresh_token,
            }, r2));
            console.log(`[VHC BG v${VERSION}] Token refreshed successfully`);
            notifyPopup({ action: 'sessionRefreshed' });
            return resolve(true);
          }
        }
        console.warn(`[VHC BG v${VERSION}] Refresh token rejected (${res.status})`);
        resolve(false);
      } catch (err) {
        console.warn(`[VHC BG v${VERSION}] Refresh token request failed:`, err.message);
        resolve(false);
      }
    });
  });
}

/**
 * Try to silently re-login using stored email/password.
 * Only works if the user opted to "remember credentials".
 */
async function silentReLogin(apiUrl) {
  return new Promise((resolve) => {
    chrome.storage.local.get(['vhc_saved_email', 'vhc_saved_password'], async (r) => {
      if (!r.vhc_saved_email || !r.vhc_saved_password) {
        console.log(`[VHC BG v${VERSION}] No saved credentials for silent re-login`);
        return resolve(false);
      }
      try {
        const res = await fetch(`${apiUrl}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: r.vhc_saved_email, password: r.vhc_saved_password })
        });
        if (res.ok) {
          const data = await res.json();
          if (data.access_token) {
            await new Promise(r2 => chrome.storage.sync.set({
              vhc_token: data.access_token,
              vhc_refresh_token: data.refresh_token || null,
            }, r2));
            console.log(`[VHC BG v${VERSION}] Silent re-login successful`);
            notifyPopup({ action: 'sessionRefreshed' });
            return resolve(true);
          }
        }
      } catch (_) {}
      console.warn(`[VHC BG v${VERSION}] Silent re-login failed`);
      resolve(false);
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// CAPTURE HISTORY
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Append a completed capture result to the local history log.
 * action: 'pending_review' | 'exists' | 'failed' (legacy history may contain created/updated)
 */
async function addToHistory(entry) {
  return serializeCaptureMutation(async () => {
    const result = await readQueueStorage(['captureHistory']);
    const history = result.captureHistory || [];
    if (entry.queue_id && history.some(row => row.queue_id === entry.queue_id && row.action !== 'failed')) {
      return { added: false };
    }
    history.push({
      queue_id: entry.queue_id || null, name: entry.name || 'Unknown',
      history_scope: entry.history_scope || null,
      profileId: entry.naukri_profile_id || null, profileUrl: entry.naukri_profile_url || null,
      action: entry.action, error: entry.error || null,
      candidate_id: entry.action === 'pending_review' ? null : entry.candidate_id || null,
      observation_id: entry.observation_id || null, message: entry.message || null,
      email: entry.email || null, phone: entry.phone || null,
      timestamp: new Date().toISOString(), bulk: entry._bulk || false,
      current_employer: entry.current_employer || null, designation: entry.designation || null,
      location: entry.location || null, education: entry.education || null,
      experience_years: entry.experience_years ?? null,
    });
    await writeQueueStorage({ captureHistory: history.slice(-CONFIG.MAX_HISTORY_ITEMS) });
    return { added: true };
  });
}

/** Retry frozen operations without losing authentication failures or new appends. */
async function processOfflineQueue() {
  if (!navigator.onLine || processOfflineQueue._running) return;
  processOfflineQueue._running = true;
  try {
    let auth = await getAuth();
    if (!auth) return;
    const stored = await readQueueStorage(['offlineQueue']);
    for (const item of stored.offlineQueue || []) {
      try {
        if (!item._capturePayload) {
          // Old offline entries may contain only raw DOM text. Restore the
          // preparation path instead of posting a different body with the same key.
          await serializeCaptureMutation(async () => {
            const latest = await readQueueStorage(['captureQueue', 'offlineQueue']);
            const capture = latest.captureQueue || [];
            const offline = latest.offlineQueue || [];
            const current = offline.find(entry => entry._queueId === item._queueId);
            if (!current || capture.length >= CONFIG.MAX_CAPTURE_QUEUE_SIZE) return;
            const operationId = current._queueId || crypto.randomUUID();
            if (!capture.some(entry => entry._queueId === operationId)) {
              capture.push({ ...current, _queueId: operationId, _status: 'pending' });
            }
            await writeQueueStorage({
              captureQueue: capture,
              offlineQueue: offline.filter(entry => entry !== current),
            });
          });
          continue;
        }
        const payload = await freezeCapturePayload(item, item._capturePayload);
        let asyncResult = await postCaptureAsync(auth, payload);
        if (asyncResult._httpResponse?.status === 401) {
          const refreshed = await refreshAccessToken(auth.apiUrl);
          if (!refreshed) break;
          auth = await getAuth();
          if (!auth) break;
          asyncResult = await postCaptureAsync(auth, payload);
          if (asyncResult._httpResponse?.status === 401) break;
        }
        const result = asyncResult._result;
        if (!isSavedCaptureResult(result)) continue;
        const historyResult = await addToHistory({
          queue_id: item._queueId, name: payload.name || item.name,
          history_scope: identityHistoryScope(auth), action: result.action,
          candidate_id: result.candidate_id, observation_id: result.observation_id,
          message: result.message, _bulk: item._bulk,
          naukri_profile_id: item.naukri_profile_id, naukri_profile_url: item.naukri_profile_url,
          email: item.email, phone: item.phone,
        });
        if (historyResult.added) await updateStats(result.action);
        await serializeCaptureMutation(async () => {
          const latest = await readQueueStorage(['offlineQueue']);
          await writeQueueStorage({ offlineQueue: (latest.offlineQueue || []).filter(entry => entry._queueId !== item._queueId) });
        });
        console.log(`[VHC BG v${VERSION}] ${result.action === 'pending_review' ? 'Saved for identity review' : 'Offline capture saved'}: ${payload.name || item.name || 'Profile'}`);
        notifyPopup({
          action: 'captureComplete', name: payload.name || item.name, result: result.action,
          candidate_id: result.action === 'pending_review' ? null : result.candidate_id,
          observation_id: result.observation_id || null, message: result.message || null,
        });
      } catch (_) { /* Retain this operation and its exact frozen body for retry. */ }
    }
    notifyPopup({ action: 'queueUpdated' });
  } finally {
    processOfflineQueue._running = false;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// QUEUE STATUS
// ═══════════════════════════════════════════════════════════════════════════════

async function getQueueStatus() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['captureQueue', 'offlineQueue', 'deadLetterQueue'], (result) => {
      const cq = result.captureQueue || [];
      const oq = result.offlineQueue || [];
      const dq = result.deadLetterQueue || [];

      const byStatus = cq.reduce((acc, item) => {
        acc[item._status] = (acc[item._status] || 0) + 1;
        return acc;
      }, {});

      resolve({
        captureQueue: {
          total:      cq.length,
          pending:    byStatus.pending || 0,
          processing: byStatus.processing || 0,
          retry:      byStatus.retry || 0,
          items:      cq.map(i => ({
            queueId:   i._queueId,
            name:      i.name || 'Unknown',
            profileId: i.naukri_profile_id,
            status:    i._status,
            attempts:  i._attempts || 0,
            queued_at: i._queued_at,
            error:     i._last_error || null
          }))
        },
        offlineQueue: {
          total: oq.length,
          items: oq.map(i => ({ name: i.name, profileId: i.naukri_profile_id }))
        },
        deadLetterQueue: {
          total: dq.length,
          items: dq.map(i => ({
            name:       i.name || 'Unknown',
            profileId:  i.naukri_profile_id,
            reason:     i._fail_reason,
            failed_at:  i._failed_at
          }))
        }
      });
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── v6.0.1: Visibility-assist state (BG-tab contact rescue) ──
const visibilityAssistState = {};

async function restoreAfterAssist(tabId) {
  const st = visibilityAssistState[tabId];
  if (!st) return;
  delete visibilityAssistState[tabId];
  clearTimeout(st.timer);
  if (st.prevTabId != null) {
    try { await chrome.tabs.update(st.prevTabId, { active: true }); } catch (_) {}
  }
}

// ── v6.0.1: Outbound payload hygiene ──
// Lone UTF-16 surrogates (styled-font names like 𝐀𝐦𝐢𝐭 sliced mid-pair by
// substring()) crash the backend's UTF-8 encoder. Strip them and NFKC-fold
// decorative Unicode on every string before it leaves the extension.
function sanitizeDeep(v) {
  if (typeof v === 'string') {
    let s = v.replace(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])/g, '');
    s = s.replace(/(^|[^\uD800-\uDBFF])([\uDC00-\uDFFF])/g, '$1');
    try { s = s.normalize('NFKC'); } catch (_) {}
    return s;
  }
  if (Array.isArray(v)) return v.map(sanitizeDeep);
  if (v && typeof v === 'object') {
    const out = {};
    for (const k of Object.keys(v)) out[k] = sanitizeDeep(v[k]);
    return out;
  }
  return v;
}

function notifyPopup(data) {
  chrome.runtime.sendMessage({ ...data, from: 'background' }).catch(() => {
    // Popup not open — ignore
  });
}

async function handleApiProxy(data) {
  try {
    const auth = await getAuth();
    if (!auth) return { success: false, error: 'Not logged in' };

    const response = await fetch(`${auth.apiUrl}${data.path}`, {
      method: data.method || 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`
      },
      body: data.body ? JSON.stringify(data.body) : undefined
    });

    if (response.status === 401) {
      // Try refresh before giving up
      const refreshed = await refreshAccessToken(auth.apiUrl);
      if (refreshed) {
        const newAuth = await getAuth();
        const retryResponse = await fetch(`${newAuth.apiUrl}${data.path}`, {
          method: data.method || 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${newAuth.token}` },
          body: data.body ? JSON.stringify(data.body) : undefined
        });
        const retryResult = await retryResponse.json();
        return retryResult;
      }
      return { success: false, error: 'Session expired. Please login again.' };
    }

    const result = await response.json();
    return result;
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function handleProfileCapture(profileData) {
  // Legacy path — just enqueue it
  return enqueueCapture(profileData);
}

async function updateStats(action) {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['stats'], (result) => {
      const stats = result.stats || {
        captured_today: 0, captured_week: 0,
        captured_total: 0, updated_total: 0, failed_total: 0,
        last_reset: new Date().toDateString()
      };

      const today = new Date().toDateString();
      if (stats.last_reset !== today) {
        stats.captured_today = 0;
        stats.last_reset = today;
      }

      const thisWeekSunday = (() => {
        const d = new Date();
        d.setDate(d.getDate() - d.getDay());
        return d.toDateString();
      })();
      if ((stats.last_week_reset || '') !== thisWeekSunday) {
        stats.captured_week = 0;
        stats.last_week_reset = thisWeekSunday;
      }

      if (action === 'created')  { stats.captured_today++; stats.captured_week++; stats.captured_total++; }
      else if (action === 'pending_review') { stats.pending_review_total = (stats.pending_review_total || 0) + 1; }
      else if (action === 'updated') { stats.updated_total++; }
      else if (action === 'failed')  { stats.failed_total++; }

      chrome.storage.sync.set({ stats }, resolve);
    });
  });
}

async function getStats() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['stats'], (syncResult) => {
      const stats = syncResult.stats || {
        captured_today: 0, captured_week: 0, captured_total: 0, updated_total: 0, failed_total: 0
      };
      chrome.storage.local.get(['captureQueue', 'offlineQueue', 'deadLetterQueue'], (localResult) => {
        stats.queue_size         = (localResult.captureQueue || []).length;
        stats.offline_queue_size = (localResult.offlineQueue || []).length;
        stats.dead_letter_size   = (localResult.deadLetterQueue || []).length;
        resolve(stats);
      });
    });
  });
}

async function handleLogin(credentials) {
  try {
    const response = await fetch(`${credentials.apiUrl}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: credentials.email, password: credentials.password })
    });

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      return { success: false, error: 'Invalid Portal URL. Please check the URL and try again.' };
    }

    const data = await response.json();
    if (!response.ok) return { success: false, error: data.detail || 'Login failed' };

    await new Promise((resolve) => {
      chrome.storage.sync.set({
        vhc_token: data.access_token,
        vhc_refresh_token: data.refresh_token || null,
        vhc_api_url: credentials.apiUrl,
        vhc_user: {
          email: credentials.email,
          name: data.user?.name || credentials.email,
          role: data.user?.role || 'unknown',
          phone: data.user?.phone || null
        }
      }, resolve);
    });

    // Save credentials locally for silent re-login (keeps session alive)
    await new Promise((resolve) => {
      chrome.storage.local.set({
        vhc_saved_email: credentials.email,
        vhc_saved_password: credentials.password,
        vhc_saved_api_url: credentials.apiUrl,
      }, resolve);
    });

    // Start session ping immediately
    setTimeout(pingSession, 1000);

    return { success: true, user: data.user };
  } catch (error) {
    if (error.message.includes('JSON') || error.name === 'SyntaxError') {
      return { success: false, error: 'Invalid Portal URL. Please check the URL and try again.' };
    }
    if (error.name === 'TypeError' || error.message.includes('fetch')) {
      return { success: false, error: 'Cannot reach server. Please check the Portal URL.' };
    }
    return { success: false, error: error.message };
  }
}

async function handleLogout() {
  return new Promise((resolve) => {
    chrome.storage.sync.remove(['vhc_token', 'vhc_refresh_token', 'vhc_api_url', 'vhc_user'], () => {
      // Also clear saved credentials on explicit logout
      chrome.storage.local.remove(['vhc_saved_email', 'vhc_saved_password', 'vhc_saved_api_url'], () => {
        resolve({ success: true });
      });
    });
  });
}

async function checkAuth() {
  const auth = await getAuth();
  if (!auth) return { authenticated: false };
  return new Promise((resolve) => {
    chrome.storage.sync.get(['vhc_user'], (result) => {
      resolve({ authenticated: true, user: result.vhc_user });
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// HOVER PREVIEW (v6.1.0)
// Fetches a compact candidate snapshot + match % vs the active mandate for
// the badge hover card. 5-minute in-memory cache keyed on candidate+mandate
// so repeated hovers on a results page cost zero network calls.
// ═══════════════════════════════════════════════════════════════════════════
const previewCache = new Map(); // key -> { at, data }
const PREVIEW_TTL_MS = 5 * 60 * 1000;
const PREVIEW_CACHE_MAX = 150;

function getActiveMandateId() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['vhc_active_mandate'], (r) => {
      resolve(r.vhc_active_mandate || null);
    });
  });
}

async function getCandidatePreview(candidateId) {
  if (!candidateId) return { success: false, error: 'missing_candidate_id' };

  const mandateId = await getActiveMandateId();
  const key = `${candidateId}:${mandateId || 'none'}`;

  const hit = previewCache.get(key);
  if (hit && Date.now() - hit.at < PREVIEW_TTL_MS) {
    return { success: true, data: hit.data, cached: true };
  }

  let auth = await getAuth();
  if (!auth) return { success: false, error: 'auth' };
  const apiHost = (() => { try { return new URL(auth.apiUrl).host; } catch (_) { return auth.apiUrl; } })();

  const primaryUrl = `${auth.apiUrl}/api/extension/candidate-preview/${encodeURIComponent(candidateId)}` +
    (mandateId ? `?mandate_id=${encodeURIComponent(mandateId)}` : '');

  let result = await fetchPreview(primaryUrl, auth);

  // 401 → token may have rotated in another tab; re-read once and retry.
  if (result.status === 401) {
    auth = await getAuth();
    if (!auth) return { success: false, error: 'auth' };
    result = await fetchPreview(primaryUrl, auth);
    if (result.status === 401) return { success: false, error: 'auth' };
  }

  // 404 → the Phase-8 preview endpoint isn't deployed on this backend yet.
  // Fall back to the long-standing candidate detail endpoint so the card
  // still shows contact / salary / notice. Match % lights up automatically
  // once the backend ships — no extension update needed.
  if (result.status === 404) {
    console.warn(`[VHC BG v${VERSION}] Preview endpoint missing (404) — using /candidate-bank/{id} fallback`);
    const fbUrl = `${auth.apiUrl}/api/candidate-bank/${encodeURIComponent(candidateId)}`;
    const fb = await fetchPreview(fbUrl, auth);
    if (fb.status === 401) return { success: false, error: 'auth' };
    if (!fb.ok) {
      console.warn(`[VHC BG v${VERSION}] Fallback failed: HTTP ${fb.status} for ${fbUrl}`);
      return { success: false, error: fb.status ? `http_${fb.status}` : (fb.error || 'network'), api: apiHost };
    }
    const doc = (fb.json && (fb.json.candidate || fb.json)) || {};
    const pick = (...vals) => {
      for (const v of vals) if (v !== undefined && v !== null && v !== '') return v;
      return null;
    };
    const data = {
      success: true,
      candidate: {
        id: doc.id,
        name: doc.name,
        designation: pick(doc.current_designation, doc.designation, doc.headline),
        employer: pick(doc.current_employer, doc.current_company, doc.company),
        location: pick(doc.current_location, doc.location),
        phone: doc.phone != null ? doc.phone : null,
        email: doc.email != null ? doc.email : null,
        current_salary: doc.current_salary != null ? doc.current_salary : null,
        expected_salary: doc.expected_salary != null ? doc.expected_salary : null,
        notice_period: pick(
          doc.notice_period,
          doc.notice_period_days != null ? `${doc.notice_period_days} days` : null
        ),
        experience_years: pick(doc.total_experience_years, doc.experience_years),
        updated_at: pick(doc.updated_at, doc.created_at),
      },
      fit: null,
      fit_error: 'preview_endpoint_missing',
    };
    previewSet(key, data);
    return { success: true, data, fallback: true };
  }

  if (!result.ok) {
    console.warn(`[VHC BG v${VERSION}] Preview failed: HTTP ${result.status || 0} (${result.error || 'server'})`);
    return { success: false, error: result.status ? `http_${result.status}` : (result.error || 'network'), api: apiHost };
  }

  previewSet(key, result.json);
  console.log(`[VHC BG v${VERSION}] Preview served for ${candidateId} (mandate: ${mandateId || 'none'})`);
  return { success: true, data: result.json };
}

/** Single fetch wrapper so primary + fallback share error semantics. */
async function fetchPreview(url, auth) {
  try {
    const r = await fetch(url, { headers: { 'Authorization': `Bearer ${auth.token}` } });
    let json = null;
    if (r.ok) {
      try { json = await r.json(); }
      catch (_) { return { ok: false, status: r.status, error: 'bad_json' }; }
    }
    return { ok: r.ok, status: r.status, json };
  } catch (e) {
    return { ok: false, status: 0, error: 'network' };
  }
}

function previewSet(key, data) {
  if (previewCache.size >= PREVIEW_CACHE_MAX) {
    const oldest = previewCache.keys().next().value;
    if (oldest) previewCache.delete(oldest);
  }
  previewCache.set(key, { at: Date.now(), data });
}

async function getAuth() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['vhc_token', 'vhc_api_url', 'vhc_user'], (result) => {
      resolve(result.vhc_token && result.vhc_api_url
        ? { token: result.vhc_token, apiUrl: result.vhc_api_url, userEmail: result.vhc_user?.email || null }
        : null);
    });
  });
}

/**
 * Convert the user's configured backend apiUrl into the matching frontend web URL,
 * then return the deep-link to a specific candidate-bank profile.
 *
 * Production:   https://api.ventureshrd.com  → https://ventureshrd.com
 * Generic:      https://app.example.com      → https://app.example.com (unchanged)
 * Preview/dev:  https://*.emergentagent.com  → same host (frontend === api host)
 *
 * The generic `/candidate-bank` route on the frontend is role-aware: it
 * redirects logged-in admins / recruiters / employers to their respective
 * candidate-bank page, preserving the ?candidateId= query param.
 */
async function buildCandidateBankUrl(candidateId) {
  if (!candidateId) return null;
  const auth = await getAuth();
  if (!auth || !auth.apiUrl) return null;
  let frontendBase;
  try {
    const u = new URL(auth.apiUrl);
    // Strip a leading `api.` subdomain if present (prod convention)
    if (u.hostname.startsWith('api.')) {
      u.hostname = u.hostname.slice(4);
    }
    // Drop any trailing path
    u.pathname = '';
    u.search = '';
    u.hash = '';
    frontendBase = u.toString().replace(/\/$/, '');
  } catch {
    frontendBase = auth.apiUrl.replace(/\/$/, '');
  }
  return `${frontendBase}/candidate-bank?candidateId=${encodeURIComponent(candidateId)}`;
}


// ═══════════════════════════════════════════════════════════════════════════════
// MANDATE EVALUATION
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Fetch the recruiter's assigned mandates from the VHC backend.
 * Called from popup when building the mandate dropdown.
 */
async function fetchMandates() {
  const auth = await getAuth();
  if (!auth) return { mandates: [] };

  try {
    const response = await fetch(`${auth.apiUrl}/api/extension/mandates`, {
      headers: { 'Authorization': `Bearer ${auth.token}` },
    });
    if (!response.ok) return { mandates: [] };
    const mandates = await response.json();
    return { mandates };
  } catch (e) {
    console.warn(`[VHC BG v${VERSION}] Failed to fetch mandates:`, e.message);
    return { mandates: [] };
  }
}

/**
 * Evaluate a candidate profile against a selected mandate.
 * Called from popup or background after capture.
 */
async function evaluateFit(data) {
  const auth = await getAuth();
  if (!auth) return { success: false, error: 'Not authenticated' };

  try {
    const response = await fetch(`${auth.apiUrl}/api/extension/evaluate-fit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        candidate_profile: data.candidate_profile,
        job_id: data.job_id,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      return { success: false, error: `API error: ${response.status}` };
    }

    return await response.json();
  } catch (e) {
    console.warn(`[VHC BG v${VERSION}] Evaluate-fit error:`, e.message);
    return { success: false, error: e.message };
  }
}

/**
 * After a successful capture, check if a mandate is selected.
 * If so, call evaluate-fit and send the result to the active tab's content script.
 */
async function triggerEvaluation(capturedItem, candidateId, auth) {
  // Check if a mandate is selected
  const stored = await new Promise(r => chrome.storage.sync.get(['vhc_active_mandate'], r));
  const mandateId = stored.vhc_active_mandate;
  if (!mandateId) return; // No mandate selected — skip evaluation

  console.log(`[VHC BG v${VERSION}] Evaluating ${capturedItem.name} against mandate ${mandateId}`);

  const result = await evaluateFit({
    candidate_profile: capturedItem,
    job_id: mandateId,
  });

  if (!result || !result.success) {
    console.warn(`[VHC BG v${VERSION}] Evaluation failed:`, result?.error);
    return;
  }

  // Send evaluation result to the active tab's content script for display
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id) {
      chrome.tabs.sendMessage(tab.id, {
        action: 'showEvaluation',
        data: {
          candidateName: capturedItem.name,
          verdict: result.verdict,
          criteria: result.criteria,
          summary: result.summary,
          jobTitle: result.job_title,
        },
      });
    }
  } catch (e) {
    console.warn(`[VHC BG v${VERSION}] Could not send evaluation to tab:`, e.message);
  }
}
