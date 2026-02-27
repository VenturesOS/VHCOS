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

const VERSION = '4.2.0';

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
};

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

// ─── Message Router ───────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {

  if (request.action === 'enqueueCapture') {
    enqueueCapture(request.data)
      .then(r => { sendResponse(r); drainCaptureQueue(); })
      .catch(e => sendResponse({ success: false, error: e.message }));
    return true;
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
        _status: 'pending'   // pending | processing | done | failed
      };

      queue.push(entry);
      chrome.storage.local.set({ captureQueue: queue }, () => {
        console.log(`[VHC BG v${VERSION}] Enqueued: ${profileData.name || profileData.naukri_profile_id} (queue: ${queue.length})`);
        resolve({ success: true, action: 'queued', queued: queue.length, queueId: entry._queueId });
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
          _bulk: true,   // tag as bulk capture for analytics
        };
        newItems.push(entry);
        existingIds.add(profileData.naukri_profile_id);
        queued++;
      }

      const merged = [...queue, ...newItems];
      chrome.storage.local.set({ captureQueue: merged }, () => {
        console.log(`[VHC BG v${VERSION}] Bulk enqueue: +${queued} queued, ${duplicates} dupes, ${dropped} dropped`);
        notifyPopup({ action: 'queueUpdated' });
        resolve({ success: true, queued, duplicates, dropped, total: merged.length });
      });
    });
  });
}

 — pulls pending items from captureQueue, runs AI extraction,
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
    // ── Step 1: AI Extraction ──
    const aiResponse = await fetch(`${auth.apiUrl}/api/extension/ai-extract`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`
      },
      body: JSON.stringify({
        raw_text:             (item.raw_text || '').substring(0, 15000),
        page_url:             item.naukri_profile_url || '',
        page_title:           item.page_title || '',
        naukri_profile_id:    item.naukri_profile_id,
        dom_extracted_name:   item.name || null,
        dom_extracted_email:  item.email || null,
        dom_extracted_phone:  item.phone || null,
        recruiter_email:      item.recruiter_email || null,
        recruiter_phone:      item.recruiter_phone || null,
      })
    });

    if (aiResponse.status === 401) {
      await handleLogout();
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

    const finalName = item.name || profileData.name;
    const capturePayload = {
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
    };

    // ── Step 3: POST to databank ──
    const captureResponse = await fetch(`${auth.apiUrl}/api/extension/capture`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`
      },
      body: JSON.stringify(capturePayload)
    });

    if (captureResponse.status === 401) {
      await handleLogout();
      await requeueWithFailure(item, 'Session expired during capture');
      return;
    }

    if (!captureResponse.ok) {
      const errText = await captureResponse.text();
      throw new Error(`Capture HTTP ${captureResponse.status}: ${errText.substring(0, 100)}`);
    }

    const captureResult = await captureResponse.json();

    // ── Step 4: Success — remove from queue, update stats, log history ──
    await removeFromCaptureQueue(item._queueId);
    await updateStats(captureResult.action);
    await addToHistory({
      name:              finalName,
      naukri_profile_id: item.naukri_profile_id,
      naukri_profile_url: item.naukri_profile_url,
      action:            captureResult.action,
      candidate_id:      captureResult.candidate_id,
      _bulk:             item._bulk || false,
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
          _bulk:             item._bulk || false,
        });
      }
    }
  }
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
      return;
    }

    if (res.status === 401) {
      console.warn(`[VHC BG v${VERSION}] Session expired — attempting silent re-login`);
      await silentReLogin(auth.apiUrl);
    }
  } catch (err) {
    // Network error during ping — don't logout, just wait for next ping
    console.warn(`[VHC BG v${VERSION}] Session ping failed (network?):`, err.message);
  }
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
            await new Promise(r2 => chrome.storage.sync.set({ vhc_token: data.access_token }, r2));
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
        timestamp:    new Date().toISOString(),
        bulk:         entry._bulk || false,
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
        const response = await fetch(`${auth.apiUrl}/api/extension/capture`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${auth.token}`
          },
          body: JSON.stringify(item)
        });

        if (response.ok) {
          const r = await response.json();
          await updateStats(r.action);
          console.log(`[VHC BG v${VERSION}] Offline sync OK: ${item.name}`);
          notifyPopup({ action: 'captureComplete', name: item.name, result: r.action });
        } else if (response.status !== 401) {
          newQueue.push(item); // Keep for later
        }
      } catch (_) {
        newQueue.push(item); // Network still down
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
      await handleLogout();
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
    chrome.storage.sync.remove(['vhc_token', 'vhc_api_url', 'vhc_user'], () => {
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
