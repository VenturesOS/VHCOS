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

const VERSION = '6.0.1';

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
chrome.runtime.onInstalled.addListener(() => {
  console.log(`[VHC BG v${VERSION}] Installed`);
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

/**
 * Computes a composite match score (0–100) between a search-card candidate
 * and a capture-history entry. Uses weighted signals so common names alone
 * can never trigger the badge — at least one corroborating signal is required.
 *
 * Score weights:
 *   Naukri ID   → 100 (definitive, short-circuits)
 *   Name        → 30
 *   Employer    → 25
 *   Designation → 15
 *   Location    → 10
 *   Education   → 10
 *   Experience  → 10
 *   -------------------
 *   Max         = 100
 */
function computeMatchScore(card, hist) {
  // ── Signal 0: Naukri ID match (100% definitive) ──
  const cardNaukriId = card.naukri_id || null;
  const histNaukriId = hist.profileId || hist.naukri_profile_id || null;
  if (cardNaukriId && histNaukriId) {
    if (cardNaukriId === histNaukriId) return 100;
    // Different IDs = definitely different people
    return 0;
  }

  let score = 0;

  // ── Signal 1: Name match (weight: 30) ──
  const cleanName = (n) => (n || '').toLowerCase()
    .replace(/\b(mr|ms|mrs|dr|shri|smt|prof)\.?\s+/gi, '')
    .replace(/[^a-z\s]/g, '').trim();

  const cardName = cleanName(card.name);
  const histName = cleanName(hist.name);

  if (cardName && histName) {
    if (cardName === histName) {
      score += 30;
    } else {
      // Jaccard similarity on name tokens (handles reordering, middle-name presence)
      const cardTokens = new Set(cardName.split(/\s+/).filter(t => t.length > 1));
      const histTokens = new Set(histName.split(/\s+/).filter(t => t.length > 1));
      const intersection = [...cardTokens].filter(t => histTokens.has(t));
      const union = new Set([...cardTokens, ...histTokens]);
      if (union.size > 0) {
        const jaccard = intersection.length / union.size;
        score += Math.round(jaccard * 30);
      }
    }
  }

  // ── Signal 2: Current Employer (weight: 25) ──
  if (card.current_employer && hist.current_employer) {
    const ce1 = (card.current_employer || '').toLowerCase()
      .replace(/\b(pvt|ltd|llp|inc|corp|limited|private|co|company)\b/g, '').trim();
    const ce2 = (hist.current_employer || '').toLowerCase()
      .replace(/\b(pvt|ltd|llp|inc|corp|limited|private|co|company)\b/g, '').trim();
    if (ce1 && ce2) {
      if (ce1 === ce2) score += 25;
      else if (ce1.includes(ce2) || ce2.includes(ce1)) score += 20;
    }
  }

  // ── Signal 3: Designation / Role (weight: 15) ──
  if (card.designation && hist.designation) {
    const d1 = (card.designation || '').toLowerCase().trim();
    const d2 = (hist.designation || '').toLowerCase().trim();
    if (d1 && d2) {
      if (d1 === d2) score += 15;
      else if (d1.includes(d2) || d2.includes(d1)) score += 10;
    }
  }

  // ── Signal 4: Location (weight: 10) ──
  if (card.location && hist.location) {
    const l1 = (card.location || '').toLowerCase().split(',')[0].trim();
    const l2 = (hist.location || '').toLowerCase().split(',')[0].trim();
    if (l1 && l2 && (l1 === l2 || l1.includes(l2) || l2.includes(l1))) {
      score += 10;
    }
  }

  // ── Signal 5: Education (weight: 10) ──
  if (card.education && hist.education) {
    const e1 = (card.education || '').toLowerCase();
    const e2 = (hist.education || '').toLowerCase();
    if (e1 && e2) {
      if (e1 === e2) score += 10;
      else if (e1.includes(e2) || e2.includes(e1)) score += 7;
    }
  }

  // ── Signal 6: Experience within 1 year (weight: 10) ──
  if (card.experience_years != null && hist.experience_years != null) {
    const diff = Math.abs(card.experience_years - hist.experience_years);
    if (diff <= 0.5) score += 10;
    else if (diff <= 1.5) score += 5;
  }

  return score;
}

/**
 * Match-score threshold: a candidate must score at least this to be badged.
 * 70 = name (30) + employer (25) + designation (15)  — safe minimum.
 */
const MATCH_THRESHOLD = 70;

/**
 * Checks a list of candidates against the local captureHistory using
 * multi-signal composite scoring. Replaces the old name-only fuzzy match.
 */
function checkLocalHistory(candidates, history) {
  const results = [];
  for (let i = 0; i < candidates.length; i++) {
    const cand = candidates[i];
    let bestMatch = null;
    let bestScore = 0;
    let matchType = 'none';

    // Normalize input URL if present
    const normUrl = cand.profileUrl ? normalizeProfileUrl(cand.profileUrl) : null;

    for (const hist of history) {
      if (hist.action === 'failed') continue;

      // 1. Match by normalized URL (definitive)
      if (normUrl && hist.profileUrl) {
        const histNormUrl = normalizeProfileUrl(hist.profileUrl);
        if (normUrl === histNormUrl) {
          bestMatch = hist;
          bestScore = 100;
          matchType = 'url';
          break;
        }
      }

      // 2. Multi-signal composite scoring
      const score = computeMatchScore(cand, hist);
      if (score > bestScore) {
        bestScore = score;
        bestMatch = hist;
        matchType = score === 100 ? 'naukri_id' : 'composite';
      }
    }

    // Only mark as existing if score meets threshold
    if (bestMatch && bestScore >= MATCH_THRESHOLD) {
      const confidence = bestScore >= 85 ? 'high'
                       : bestScore >= MATCH_THRESHOLD ? 'medium'
                       : 'low';
      results.push({
        index: i,
        exists: true,
        candidate_id: bestMatch.candidate_id,
        captured_at: bestMatch.timestamp,
        match_confidence: confidence,
        match_score: bestScore,
      });
    } else {
      results.push({ index: i, exists: false });
    }
  }
  return results;
}

/**
 * Merges local match results with backend check-existing API results.
 */
function mergeCheckResults(localResults, apiResults) {
  const merged = [];
  const apiMap = new Map();
  if (Array.isArray(apiResults)) {
    for (const r of apiResults) {
      if (r && typeof r.index === 'number') apiMap.set(r.index, r);
    }
  }
  
  for (let i = 0; i < localResults.length; i++) {
    const local = localResults[i];
    const api = apiMap.get(i) || null;
    
    if (api && api.exists) {
      merged.push({
        index: i,
        exists: true,
        candidate_id: api.candidate_id || local.candidate_id,
        captured_at: api.captured_at || local.captured_at,
        match_confidence: api.match_confidence || local.match_confidence || 'high'
      });
    } else if (local.exists) {
      merged.push(local);
    } else {
      merged.push({
        index: i,
        exists: false
      });
    }
  }
  return { results: merged };
}

/**
 * High-level orchestrator to check if candidates already exist in the database.
 * Calls local history matching and backend API, falling back gracefully to local on failures.
 */
async function checkExistingCandidates(candidates) {
  if (!candidates || candidates.length === 0) return { results: [] };
  const auth = await getAuth();
  
  // 1. Read local history
  const storage = await new Promise(resolve => {
    chrome.storage.local.get(['captureHistory'], (r) => resolve(r.captureHistory || []));
  });
  
  const localResults = checkLocalHistory(candidates, storage);
  
  // If not authenticated, return local results
  if (!auth) {
    console.log(`[VHC BG v${VERSION}] checkExisting: No auth. Returning local results.`);
    return { results: localResults };
  }
  
  try {
    console.log(`[VHC BG v${VERSION}] checkExisting: Sending batch of ${candidates.length} to API...`);
    
    const response = await fetch(`${auth.apiUrl}/api/extension/check-existing`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`
      },
      body: JSON.stringify({ candidates })
    });
    
    if (response.status === 401) {
      const refreshed = await refreshAccessToken(auth.apiUrl);
      if (refreshed) {
        const newAuth = await getAuth();
        const retryResponse = await fetch(`${newAuth.apiUrl}/api/extension/check-existing`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${newAuth.token}`
          },
          body: JSON.stringify({ candidates })
        });
        if (retryResponse.ok) {
          const apiData = await retryResponse.json();
          return { results: postValidateApiResults(candidates, apiData.results || [], storage) };
        }
      }
      console.warn(`[VHC BG v${VERSION}] checkExisting: API Auth failed, using local fallback.`);
      return { results: localResults };
    }
    
    if (!response.ok) {
      console.warn(`[VHC BG v${VERSION}] checkExisting: API returned HTTP ${response.status}, using local fallback.`);
      return { results: localResults };
    }
    
    const apiData = await response.json();
    // v5.5.10 — defensive debug: surface the API → client picture so we can
    // diagnose missing-badge bugs without diving into the Network tab.
    const apiHitCount = (apiData.results || []).filter(r => r && r.exists).length;
    console.log(`[VHC BG v${VERSION}] checkExisting: API returned ${apiHitCount} hits / ${candidates.length} candidates (audit_id=${apiData.audit_id || 'none'})`);
    // Show first 3 hits with their signals so we can see V2 working
    (apiData.results || []).filter(r => r && r.exists).slice(0, 3).forEach(r => {
      const c = candidates[r.index] || {};
      console.log(
        `[VHC BG v${VERSION}]   • API hit: idx=${r.index} card="${c.name}" → ` +
        `db="${(r.matched_candidate || {}).name || '?'}" ` +
        `score=${r.match_score} signals=${JSON.stringify(r.matched_signals)} conf=${r.match_confidence}`
      );
    });

    // Post-validate: the API may match by name alone, causing false positives
    // on common names (e.g. two different "Shubham Rawat"). We cross-check each
    // API match against local history using multi-signal composite scoring.
    const finalResults = postValidateApiResults(candidates, apiData.results || [], storage);
    const finalHitCount = finalResults.filter(r => r && r.exists).length;
    if (finalHitCount < apiHitCount) {
      console.warn(`[VHC BG v${VERSION}] checkExisting: post-validation dropped ${apiHitCount - finalHitCount} hits (API ${apiHitCount} → client ${finalHitCount})`);
    }
    return { results: finalResults };
  } catch (err) {
    console.warn(`[VHC BG v${VERSION}] checkExisting API call failed:`, err.message, "— falling back to local history.");
    return { results: localResults };
  }
}

/**
 * Post-validates API "exists" results against card data + local history.
 *
 * The API may match candidates by name alone, which produces false positives
 * for common Indian names (Rahul Sharma, Shubham Rawat, Amit Kumar etc.).
 * This function cross-checks each API match:
 *
 * 1. If API matched by URL/profile-ID → trust (definitive)
 * 2. If we find the matched candidate_id in local history with multi-signal
 *    fields → run computeMatchScore; reject if below threshold
 * 3. If local history has no multi-signal data, check for obvious conflicts
 *    between card fields and whatever the API returned
 * 4. If we can't validate at all → downgrade to 'medium' confidence
 */
function postValidateApiResults(candidates, apiResults, localHistory) {
  if (!Array.isArray(apiResults)) return [];

  // Helper: extract Naukri candidateId from a URL (same logic as content.js extractIdFromUrl)
  function extractNaukriId(url) {
    if (!url) return null;
    const m = url.match(/[?&](?:candidateId|profileId|pid)=([^&]+)/i);
    return m ? m[1] : null;
  }

  return apiResults.map(result => {
    // Non-matches pass through unchanged
    if (!result || !result.exists) return result;

    const card = candidates[result.index];
    if (!card) return result;

    // ── Trust definitive matches (URL or Naukri profile ID) ──
    const matchType = (result.matched_by || result.match_type || '').toLowerCase();
    if (matchType === 'url' || matchType === 'profile_id' || matchType === 'naukri_id') {
      return { ...result, match_confidence: 'high' };
    }

    // ── Also trust if the API returned a profile_url that matches the card URL ──
    if (result.profile_url && card.profileUrl) {
      const apiNormUrl  = normalizeProfileUrl(result.profile_url);
      const cardNormUrl = normalizeProfileUrl(card.profileUrl);
      if (apiNormUrl && cardNormUrl && apiNormUrl === cardNormUrl) {
        return { ...result, match_confidence: 'high' };
      }
    }

    // ── TRUST V2 BACKEND ──
    // The V2 scorer (Phase 56.4+) already does multi-signal composite scoring
    // server-side and only emits `matched_signals` when ≥2 strong signals
    // corroborate the name match. Running the OLD client-side computeMatchScore
    // on top of V2 was double-scoring and rejecting valid matches (it was
    // designed to filter false positives from the loose V1 backend).
    //
    // Signature of a V2 response: `matched_signals` is a populated array AND
    // the backend's `match_score` is a positive number. In that case the
    // backend has already done the verification — skip client post-validation.
    const isV2Response =
      Array.isArray(result.matched_signals) &&
      result.matched_signals.length > 0 &&
      typeof result.match_score === 'number';
    if (isV2Response) {
      // Map V2 confidence directly — server already chose high/medium/low.
      return result;
    }

    // ── PRIMARY (V1 fallback): Server-returned matched_candidate cross-check ──
    // The /api/extension/check-existing V1 endpoint matches loosely on name.
    // Run the composite scorer locally to drop the obvious false positives.
    if (result.matched_candidate) {
      const mc = result.matched_candidate;
      // Map server fields → the shape expected by computeMatchScore
      const histEntry = {
        name: mc.name,
        current_employer: mc.current_employer,
        designation: mc.designation,
        location: mc.location,
        experience_years: mc.experience_years,
        education: mc.education,
        profileId: mc.naukri_profile_id,
        naukri_profile_id: mc.naukri_profile_id,
      };

      // 1. Definitive Naukri ID match short-circuits in computeMatchScore (=100)
      // 2. Otherwise compute composite — same threshold as local-history path
      const score = computeMatchScore(card, histEntry);
      if (score < MATCH_THRESHOLD) {
        console.log(
          `[VHC BG v${VERSION}] Post-validation REJECTED (server cross-check): ` +
          `card="${card.name}" (${card.current_employer || '?'} / ${card.designation || '?'}) ` +
          `≠ db="${mc.name}" (${mc.current_employer || '?'} / ${mc.designation || '?'}) ` +
          `→ score ${score} < ${MATCH_THRESHOLD}`
        );
        return { index: result.index, exists: false };
      }
      // Confirmed via server — preserve any deep-link / metadata from the API
      return {
        ...result,
        match_confidence: score >= 85 ? 'high' : 'medium',
        match_score: score,
      };
    }

    // ── Try to find matched candidate in local history by candidate_id ──
    const resultCandId = result.candidate_id != null ? String(result.candidate_id) : null;
    let histEntry = null;

    if (resultCandId) {
      histEntry = localHistory.find(h =>
        h.candidate_id != null &&
        String(h.candidate_id) === resultCandId &&
        h.action !== 'failed'
      );
    }

    // Fallback: try matching by profileUrl in history
    if (!histEntry && result.profile_url) {
      const apiNorm = normalizeProfileUrl(result.profile_url);
      if (apiNorm) {
        histEntry = localHistory.find(h =>
          h.profileUrl &&
          normalizeProfileUrl(h.profileUrl) === apiNorm &&
          h.action !== 'failed'
        );
      }
    }

    if (histEntry) {
      // Check if history entry has multi-signal fields (captured after v5.5.6 changes)
      const hasMultiSignal = !!(histEntry.current_employer || histEntry.designation || histEntry.location);

      if (hasMultiSignal) {
        // Full multi-signal validation — reliable
        const score = computeMatchScore(card, histEntry);
        if (score < MATCH_THRESHOLD) {
          console.log(
            `[VHC BG v${VERSION}] Post-validation REJECTED: card="${card.name}" ` +
            `(${card.current_employer || '?'} / ${card.designation || '?'}) ` +
            `≠ history="${histEntry.name}" ` +
            `(${histEntry.current_employer || '?'} / ${histEntry.designation || '?'}) ` +
            `→ score ${score} < ${MATCH_THRESHOLD}`
          );
          return { index: result.index, exists: false };
        }
        return {
          ...result,
          match_confidence: score >= 85 ? 'high' : 'medium',
          match_score: score,
        };
      }

      // ── Old history entry (no multi-signal fields) ──
      // Compare Naukri profile IDs — these are definitive even without multi-signal data
      const cardNaukriId = card.naukri_id || extractNaukriId(card.profileUrl);
      const histNaukriId = histEntry.profileId || null;

      if (cardNaukriId && histNaukriId) {
        if (String(cardNaukriId) === String(histNaukriId)) {
          // Same Naukri ID → definitely same person
          console.log(
            `[VHC BG v${VERSION}] Post-validation CONFIRMED (Naukri ID match): ` +
            `card="${card.name}" id=${cardNaukriId}`
          );
          return { ...result, match_confidence: 'high' };
        } else {
          // Different Naukri IDs → definitely different people
          console.log(
            `[VHC BG v${VERSION}] Post-validation REJECTED (different Naukri IDs): ` +
            `card="${card.name}" cardId=${cardNaukriId} vs histId=${histNaukriId}`
          );
          return { index: result.index, exists: false };
        }
      }

      // Can't compare IDs — trust API for this old entry
      return { ...result, match_confidence: result.match_confidence || 'high' };
    }

    // ── No local history — check card fields vs API response for conflicts ──
    const apiEmployer  = (result.current_employer || result.company || '').toLowerCase().trim();
    const cardEmployer = (card.current_employer || '').toLowerCase().trim();

    if (apiEmployer && cardEmployer && apiEmployer.length > 2 && cardEmployer.length > 2) {
      const empClean = (s) => s.replace(/\b(pvt|ltd|llp|inc|corp|limited|private|co|company)\b/g, '').trim();
      const ae = empClean(apiEmployer);
      const ce = empClean(cardEmployer);
      if (ae && ce && !ae.includes(ce) && !ce.includes(ae)) {
        console.log(
          `[VHC BG v${VERSION}] Post-validation REJECTED (employer conflict): card="${card.name}" ` +
          `employer="${cardEmployer}" vs API="${apiEmployer}"`
        );
        return { index: result.index, exists: false };
      }
    }

    // No evidence of conflict — trust API with medium confidence
    return {
      ...result,
      match_confidence: 'medium',
    };
  });
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

  // ═══ CHECK EXISTING CANDIDATES (Local cache + API backend) ═══
  if (request.action === 'checkExisting') {
    checkExistingCandidates(request.candidates || [])
      .then(sendResponse)
      .catch(e => {
        console.error(`[VHC BG v${VERSION}] checkExisting error:`, e.message);
        sendResponse({ success: false, error: e.message, results: (request.candidates || []).map((_, i) => ({ index: i, exists: false })) });
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
  if (request.action === 'cvIframeData') {
    const tabId = sender.tab?.id;
    if (tabId && request.data) {
      cvIframeDataByTab[tabId] = request.data;
      console.log(`[VHC BG v${VERSION}] CV iframe data stored for tab ${tabId}: ${(request.data.text || '').length} chars`);
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
    chrome.storage.local.set({ captureHistory: [] }, () => sendResponse({ success: true }));
    return true;
  }

  if (request.action === 'getQueueStatus') {
    getQueueStatus().then(sendResponse);
    return true;
  }

  if (request.action === 'clearDeadLetter') {
    chrome.storage.local.set({ deadLetterQueue: [] }, () => sendResponse({ success: true }));
    return true;
  }

  if (request.action === 'retryDeadLetter') {
    retryDeadLetter().then(sendResponse);
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
});

// ═══════════════════════════════════════════════════════════════════════════════
// QUEUE MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Add a raw profile (just-scraped, not yet AI-processed) to the captureQueue.
 * Returns immediately — processing happens asynchronously in drainCaptureQueue().
 */
async function enqueueCapture(profileData) {
  return new Promise((resolve) => {
    // Read active mandate at queue time so the correct mandate is stamped
    chrome.storage.sync.get(['vhc_active_mandate'], (syncResult) => {
      const activeMandateId = syncResult.vhc_active_mandate || null;

      chrome.storage.local.get(['captureQueue'], (result) => {
        const queue = result.captureQueue || [];

        // Dedup by profile ID
        if (queue.some(item => item.naukri_profile_id === profileData.naukri_profile_id)) {
          console.log(`[VHC BG v${VERSION}] Skipping duplicate: ${profileData.naukri_profile_id}`);
          return resolve({ success: true, action: 'duplicate', queued: queue.length });
        }

        if (queue.length >= CONFIG.MAX_CAPTURE_QUEUE_SIZE) {
          console.warn(`[VHC BG v${VERSION}] Capture queue full (${queue.length})`);
          return resolve({ success: false, error: 'Queue full', queued: queue.length });
        }

        const entry = {
          ...profileData,
          _queueId: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          _attempts: 0,
          _queued_at: new Date().toISOString(),
          _status: 'pending',
          _mandate_id: activeMandateId,
        };

        queue.push(entry);
        chrome.storage.local.set({ captureQueue: queue }, () => {
          console.log(`[VHC BG v${VERSION}] Enqueued: ${profileData.name || profileData.naukri_profile_id} (queue: ${queue.length}, mandate: ${activeMandateId || 'none'})`);
          resolve({ success: true, action: 'queued', queued: queue.length, queueId: entry._queueId });
        });
      });
    });
  });
}

/**
 * Bulk enqueue an array of raw profiles from a search/list page.
 * Deduplicates, respects queue limits, returns summary.
 */
async function bulkEnqueue(profiles) {
  if (!Array.isArray(profiles) || profiles.length === 0) {
    return { success: false, error: 'No profiles provided' };
  }

  return new Promise((resolve) => {
    // Read active mandate at queue time
    chrome.storage.sync.get(['vhc_active_mandate'], (syncResult) => {
      const activeMandateId = syncResult.vhc_active_mandate || null;

      chrome.storage.local.get(['captureQueue'], (result) => {
        const queue = result.captureQueue || [];
        const existingIds = new Set(queue.map(i => i.naukri_profile_id));

        let queued = 0, duplicates = 0, dropped = 0;
        const newItems = [];

        for (const profileData of profiles) {
          if (!profileData.naukri_profile_id) { dropped++; continue; }
          if (existingIds.has(profileData.naukri_profile_id)) { duplicates++; continue; }
          if (queue.length + newItems.length >= CONFIG.MAX_CAPTURE_QUEUE_SIZE) { dropped++; continue; }

          const entry = {
            ...profileData,
            _queueId: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            _attempts: 0,
            _queued_at: new Date().toISOString(),
            _status: 'pending',
            _bulk: true,
            _mandate_id: activeMandateId,
          };
          newItems.push(entry);
          existingIds.add(profileData.naukri_profile_id);
          queued++;
        }

        const merged = [...queue, ...newItems];
        chrome.storage.local.set({ captureQueue: merged }, () => {
          console.log(`[VHC BG v${VERSION}] Bulk enqueue: +${queued} queued, ${duplicates} dupes, ${dropped} dropped (mandate: ${activeMandateId || 'none'})`);
          notifyPopup({ action: 'queueUpdated' });
          resolve({ success: true, queued, duplicates, dropped, total: merged.length });
        });
      });
    });
  });
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
    if (item.dom_fields && item.dom_fields._dom_scraped) {
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

    // ── Step 4: Success — remove from queue, update stats, log history ──
    await removeFromCaptureQueue(item._queueId);
    await updateStats(captureResult.action);
    await addToHistory({
      name:              finalName,
      naukri_profile_id: item.naukri_profile_id,
      naukri_profile_url: item.naukri_profile_url,
      action:            captureResult.action,
      candidate_id:      captureResult.candidate_id,
      email:             item.email || null,
      phone:             item.phone || null,
      _bulk:             item._bulk || false,
      // Multi-signal fields for offline composite matching (v5.5.6+)
      current_employer:  item.dom_fields?.current_company || capturePayload?.current_company || null,
      designation:       item.dom_fields?.current_designation || capturePayload?.current_designation || null,
      location:          item.dom_fields?.current_location || capturePayload?.career_preferences?.current_location || null,
      education:         Array.isArray(capturePayload?.education) ? (capturePayload.education[0]?.degree || capturePayload.education[0]?.institution || null) : null,
      experience_years:  item.dom_fields?.total_experience_years || capturePayload?.total_experience_years || null,
    });

    const candidateId = captureResult.candidate_id;

    // ── Step 5: CV file upload (if a download URL was found on the page) ──
    if (candidateId && item.cv_download_url) {
      uploadCVFile(item.cv_download_url, candidateId, auth).catch(err => {
        console.warn(`[VHC BG v${VERSION}] CV upload failed for ${finalName}:`, err.message);
      });
    }

    // ── Step 6: Job shortlist (if recruiter has an active job open) ──
    if (candidateId && item.active_job_id && captureResult.action !== 'exists') {
      shortlistCandidate(candidateId, item.active_job_id, auth).catch(err => {
        console.warn(`[VHC BG v${VERSION}] Shortlist failed for ${finalName}:`, err.message);
      });
    }

    // ── Step 7: Evaluate fit against active mandate (non-blocking) ──
    triggerEvaluation(item, candidateId, auth).catch(err => {
      console.warn(`[VHC BG v${VERSION}] Evaluate-fit skipped for ${finalName}:`, err.message);
    });

    const actionLabels = { created: '✅ Added', updated: '🔄 Updated', exists: '✓ Already saved' };
    console.log(`[VHC BG v${VERSION}] ${actionLabels[captureResult.action] || '✅'}: ${finalName}`);

    // Notify any open popup
    notifyPopup({
      action: 'captureComplete',
      name: finalName,
      result: captureResult.action,
      candidate_id: captureResult.candidate_id
    });

  } catch (err) {
    console.error(`[VHC BG v${VERSION}] Failed: ${label} —`, err.message);

    const isNetworkError = err.name === 'TypeError' || err.message.includes('fetch') || err.message.includes('network');

    if (isNetworkError) {
      await moveToOfflineQueue(item);
      await removeFromCaptureQueue(item._queueId);
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
  return new Promise((resolve) => {
    chrome.storage.local.get(['captureQueue'], (result) => {
      const queue = (result.captureQueue || []).map(item => {
        if (queueIds.includes(item._queueId)) {
          return { ...item, _status: status, ...extra };
        }
        return item;
      });
      chrome.storage.local.set({ captureQueue: queue }, resolve);
    });
  });
}

/**
 * Remove a processed item from captureQueue
 */
async function removeFromCaptureQueue(queueId) {
  return new Promise((resolve) => {
    chrome.storage.local.get(['captureQueue'], (result) => {
      const queue = (result.captureQueue || []).filter(i => i._queueId !== queueId);
      chrome.storage.local.set({ captureQueue: queue }, resolve);
    });
  });
}

/**
 * Increment retry counter; move to deadLetter if exceeded max retries
 */
async function requeueWithFailure(item, reason) {
  const attempts = (item._attempts || 0) + 1;

  if (attempts >= CONFIG.RETRY_MAX) {
    console.warn(`[VHC BG v${VERSION}] Dead-lettering after ${attempts} attempts: ${item.name || item._queueId}`);
    await removeFromCaptureQueue(item._queueId);
    await addToDeadLetter({ ...item, _attempts: attempts, _fail_reason: reason, _failed_at: new Date().toISOString() });
    return;
  }

  const backoffMs = CONFIG.RETRY_BACKOFF_MS * attempts;
  console.log(`[VHC BG v${VERSION}] Retry ${attempts}/${CONFIG.RETRY_MAX} in ${backoffMs}ms: ${item.name || item._queueId} (${reason})`);

  await markStatus([item._queueId], 'retry', {
    _attempts: attempts,
    _last_error: reason,
    _retry_after: Date.now() + backoffMs
  });
}

/**
 * Add fully-processed but network-failed profile to offline queue
 */
async function moveToOfflineQueue(item) {
  return new Promise((resolve) => {
    chrome.storage.local.get(['offlineQueue'], (result) => {
      const queue = result.offlineQueue || [];
      if (queue.some(i => i.naukri_profile_id === item.naukri_profile_id)) return resolve();
      if (queue.length >= CONFIG.MAX_OFFLINE_QUEUE_SIZE) return resolve();
      queue.push({ ...item, _offline_queued_at: new Date().toISOString() });
      chrome.storage.local.set({ offlineQueue: queue }, resolve);
    });
  });
}

/**
 * Add to dead letter queue (failed after max retries — reviewable in popup)
 */
async function addToDeadLetter(item) {
  return new Promise((resolve) => {
    chrome.storage.local.get(['deadLetterQueue'], (result) => {
      const queue = result.deadLetterQueue || [];
      queue.push(item);
      chrome.storage.local.set({ deadLetterQueue: queue.slice(-50) }, resolve); // keep last 50
    });
  });
}

/**
 * Re-enqueue dead letter items back into captureQueue for retry
 */
async function retryDeadLetter() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['deadLetterQueue'], (result) => {
      const dead = result.deadLetterQueue || [];
      if (dead.length === 0) return resolve({ success: true, requeued: 0 });

      const requeued = dead.map(item => ({
        ...item,
        _attempts: 0,
        _status: 'pending',
        _fail_reason: null,
        _retry_after: null
      }));

      // Re-add to captureQueue
      chrome.storage.local.get(['captureQueue'], (r2) => {
        const cq = r2.captureQueue || [];
        const merged = [...cq, ...requeued];
        chrome.storage.local.set({ captureQueue: merged, deadLetterQueue: [] }, () => {
          drainCaptureQueue();
          resolve({ success: true, requeued: requeued.length });
        });
      });
    });
  });
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
 * action: 'created' | 'updated' | 'exists' | 'failed'
 */
async function addToHistory(entry) {
  return new Promise((resolve) => {
    chrome.storage.local.get(['captureHistory'], (r) => {
      const history = r.captureHistory || [];
      history.push({
        name:         entry.name || 'Unknown',
        profileId:    entry.naukri_profile_id || null,
        profileUrl:   entry.naukri_profile_url || null,
        action:       entry.action,           // created | updated | exists | failed
        error:        entry.error || null,
        candidate_id: entry.candidate_id || null,
        email:        entry.email || null,    // captured email (null = hidden/missing)
        phone:        entry.phone || null,    // captured phone (null = hidden/missing)
        timestamp:    new Date().toISOString(),
        bulk:         entry._bulk || false,
        // Multi-signal fields for offline composite matching (v5.5.6+)
        current_employer:  entry.current_employer || null,
        designation:       entry.designation || null,
        location:          entry.location || null,
        education:         entry.education || null,
        experience_years:  entry.experience_years || null,
      });
      // Keep only the latest MAX_HISTORY_ITEMS
      const trimmed = history.slice(-CONFIG.MAX_HISTORY_ITEMS);
      chrome.storage.local.set({ captureHistory: trimmed }, resolve);
    });
  });
}

/**
 * Process offline queue (network-failed profiles) when back online
 */
async function processOfflineQueue() {
  if (!navigator.onLine) return;
  const auth = await getAuth();
  if (!auth) return;

  chrome.storage.local.get(['offlineQueue'], async (result) => {
    const queue = result.offlineQueue || [];
    if (queue.length === 0) return;

    console.log(`[VHC BG v${VERSION}] Syncing ${queue.length} offline profiles`);
    const newQueue = [];

    for (const item of queue) {
      try {
        // Map internal _mandate_id to the backend's expected field name
        const payload = { ...item, mandate_id: item._mandate_id || item.mandate_id || null };
        const asyncResult = await postCaptureAsync(auth, payload);

        if (asyncResult._httpResponse?.status === 401) {
          // Don't re-queue on auth failure — caller-level token refresh will retry
        } else if (asyncResult._result) {
          await updateStats(asyncResult._result.action);
          console.log(`[VHC BG v${VERSION}] Offline sync OK: ${item.name}`);
          notifyPopup({ action: 'captureComplete', name: item.name, result: asyncResult._result.action });
        } else {
          newQueue.push(item); // Unknown shape — keep for later
        }
      } catch (_) {
        newQueue.push(item); // Network still down or job failed
      }
      await sleep(300);
    }

    chrome.storage.local.set({ offlineQueue: newQueue }, () => {
      if (newQueue.length < queue.length) {
        notifyPopup({ action: 'queueUpdated' });
      }
    });
  });
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

async function getAuth() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['vhc_token', 'vhc_api_url'], (result) => {
      resolve(result.vhc_token && result.vhc_api_url
        ? { token: result.vhc_token, apiUrl: result.vhc_api_url }
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
