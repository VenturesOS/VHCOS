/**
 * VHC Talent OS - Popup Script v4.2.0
 * Queue-aware: shows live captureQueue, offlineQueue, deadLetterQueue
 * v4.1: Bulk capture from search/list pages
 * v4.2: Capture history cards + persistent session (never logs out)
 */

// Approx seconds per candidate in background (AI extract + POST)
const AVG_SECONDS_PER_CANDIDATE = 8;

document.addEventListener('DOMContentLoaded', async () => {

  // ── Auth check ────────────────────────────────────────────────────────────
  const authStatus = await chrome.runtime.sendMessage({ action: 'checkAuth' });
  if (authStatus.authenticated) {
    showDashboard(authStatus.user);
  } else {
    showLogin();
  }

  // ── Update-available banner ────────────────────────────────────────────────
  // Compares this build's manifest version against the backend's latest
  // (/api/extension/version, public). CRX installs: "Update now" triggers
  // chrome.runtime.requestUpdateCheck() so Chrome pulls update.xml
  // immediately instead of waiting for its ~5h cycle. Unpacked installs
  // can't self-update — banner explains how to get the new build.
  checkForExtensionUpdate().catch(() => {});

  // ── Detect page type & show/hide bulk button + active job banner ──────────
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.url) {
      const isSupported = tab.url.includes('naukri.com') || tab.url.includes('linkedin.com') ||
                          tab.url.includes('foundit.in') || tab.url.includes('foundit.sg') || tab.url.includes('monster.com');
      if (isSupported) {
        const pageInfo = await chrome.tabs.sendMessage(tab.id, { action: 'getPageInfo' }).catch(() => null);
        if (pageInfo?.isSearchPage && tab.url.includes('naukri.com')) {
          document.getElementById('bulkCaptureBtn').style.display = 'block';
          document.getElementById('bulkCaptureInfo').style.display = 'block';
          document.getElementById('bulkCaptureInfo').textContent = 'Queues all visible candidates on this search page';
          document.getElementById('manualCaptureBtn').style.display = 'none';
        }
      }
    }
    // Show active job banner if set
    const { vhc_active_job } = await chrome.storage.local.get(['vhc_active_job']);
    if (vhc_active_job?.job_title) {
      const jobBanner = document.getElementById('activeJobBanner');
      if (jobBanner) {
        jobBanner.textContent = `📎 Active job: ${vhc_active_job.job_title}${vhc_active_job.job_code ? ` (${vhc_active_job.job_code})` : ''}`;
        jobBanner.style.display = 'block';
      }
    }
  } catch (_) {}

  // ── Tab switching ─────────────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${tab}`).classList.add('active');
      if (tab === 'queue')   refreshQueueStatus();
      if (tab === 'history') refreshHistory();
    });
  });

  // ── Login handler ─────────────────────────────────────────────────────────
  document.getElementById('loginBtn').addEventListener('click', async () => {
    const apiUrl    = document.getElementById('apiUrl').value.trim().replace(/\/$/, '');
    const email     = document.getElementById('email').value.trim();
    const password  = document.getElementById('password').value;

    if (!apiUrl || !email || !password) { showLoginError('Please fill in all fields'); return; }

    const btn = document.getElementById('loginBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> Logging in...';

    try {
      const response = await chrome.runtime.sendMessage({ action: 'login', data: { apiUrl, email, password } });
      if (response.success) {
        showDashboard({ name: response.user?.name || email, role: response.user?.role || 'user' });
      } else {
        showLoginError(response.error || 'Login failed');
      }
    } catch (e) { showLoginError('Connection error. Please try again.'); }

    btn.disabled = false;
    btn.textContent = 'Login to Ventures HRD';
  });

  // ── Logout ────────────────────────────────────────────────────────────────
  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ action: 'logout' });
    showLogin();
  });

  // ── Manual capture ────────────────────────────────────────────────────────
  document.getElementById('manualCaptureBtn').addEventListener('click', async () => {
    const btn = document.getElementById('manualCaptureBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> Capturing...';
    hideCaptureStatus();
    setProgress(10, 'Scrolling page...');

    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      if (!tab) {
        showCaptureStatus('error', 'No active tab found');
        resetProgress();
        return;
      }
      if (!tab.url.includes('naukri.com') && !tab.url.includes('linkedin.com') && !tab.url.includes('foundit.in') && !tab.url.includes('foundit.sg') && !tab.url.includes('monster.com')) {
        showCaptureStatus('error', 'Open a Naukri, LinkedIn, or Foundit profile first.');
        resetProgress();
        return;
      }

      setProgress(20, 'Loading page content...');
      const t1 = setTimeout(() => setProgress(45, 'Extracting contacts...'),  2500);
      const t2 = setTimeout(() => setProgress(70, 'Building profile data...'), 5000);

      let response;
      try {
        response = await Promise.race([
          chrome.tabs.sendMessage(tab.id, { action: 'manualCapture' }),
          new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 30000))
        ]);
      } finally {
        clearTimeout(t1); clearTimeout(t2);
      }

      if (response?.success) {
        setProgress(100, 'Complete');

        if (response.action === 'queued') {
          showCaptureStatus('success', `✅ ${response.name || 'Profile'} queued for AI processing (${response.queued} in queue)`);
          // Switch to queue tab to show it
          setTimeout(() => {
            document.querySelectorAll('.tab-btn').forEach(b => {
              b.classList.toggle('active', b.dataset.tab === 'queue');
            });
            document.querySelectorAll('.tab-panel').forEach(p => {
              p.classList.toggle('active', p.id === 'tab-queue');
            });
            refreshQueueStatus();
          }, 1500);
        } else if (response.action === 'duplicate') {
          showCaptureStatus('info', `${response.name || 'Profile'} already in queue`);
        } else {
          showCaptureStatus('success', `${response.name || 'Profile'} captured!`);
        }
      } else if (response) {
        resetProgress();
        showCaptureStatus('error', response.error || 'Capture failed.');
      }
    } catch (error) {
      resetProgress();
      if (error.message === 'timeout') {
        setProgress(90, 'Still processing...');
        showCaptureStatus('info', 'Capture running on page. Check the Queue tab.');
        refreshQueueStatus();
      } else if (error.message?.includes('Receiving end') || error.message?.includes('Could not establish')) {
        showCaptureStatus('error', 'Content script not loaded. Refresh the Naukri page.');
      } else {
        showCaptureStatus('info', 'Capture triggered. Check the Queue tab for status.');
      }
    } finally {
      btn.disabled = false;
      btn.textContent = 'Capture This Profile';
    }
  });

  // ── Bulk capture handler ──────────────────────────────────────────────────
  document.getElementById('bulkCaptureBtn').addEventListener('click', async () => {
    const btn = document.getElementById('bulkCaptureBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> Scanning page...';
    hideCaptureStatus();

    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) { showCaptureStatus('error', 'No active tab found'); return; }
      if (!tab.url.includes('naukri.com')) {
        showCaptureStatus('error', 'Bulk capture is only available on Naukri search pages.'); return;
      }

      const response = await Promise.race([
        chrome.tabs.sendMessage(tab.id, { action: 'bulkCapture' }),
        new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 20000))
      ]);

      if (response?.success) {
        const eta = Math.ceil((response.queued * AVG_SECONDS_PER_CANDIDATE) / 60);
        showCaptureStatus('success',
          `⚡ ${response.queued} candidates queued${response.duplicates ? `, ${response.duplicates} skipped` : ''}.\n` +
          `Est. ~${eta} min to process all.`
        );
        // Auto-switch to queue tab
        setTimeout(() => {
          document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === 'queue'));
          document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-queue'));
          refreshQueueStatus();
        }, 1500);
      } else {
        showCaptureStatus('error', response?.error || 'Bulk capture failed.');
      }
    } catch (err) {
      if (err.message === 'timeout') {
        showCaptureStatus('info', 'Bulk scan running. Check Queue tab.');
        refreshQueueStatus();
      } else {
        showCaptureStatus('error', err.message || 'Unexpected error');
      }
    } finally {
      btn.disabled = false;
      btn.innerHTML = '⚡ Bulk Capture All on Page';
    }
  });

  // ── Queue actions ─────────────────────────────────────────────────────────
  document.getElementById('refreshQueueBtn').addEventListener('click', refreshQueueStatus);

  document.getElementById('retryDeadBtn').addEventListener('click', async () => {
    const btn = document.getElementById('retryDeadBtn');
    btn.disabled = true;
    const result = await chrome.runtime.sendMessage({ action: 'retryDeadLetter' });
    if (result.success) {
      showQueueToast(`↺ ${result.requeued} failed profile(s) re-queued for retry`);
    }
    btn.disabled = false;
    refreshQueueStatus();
  });

  document.getElementById('clearDeadBtn').addEventListener('click', async () => {
    if (!confirm('Clear all failed profiles? This cannot be undone.')) return;
    await chrome.runtime.sendMessage({ action: 'clearDeadLetter' });
    refreshQueueStatus();
  });

  // ── Clear history ─────────────────────────────────────────────────────────
  document.getElementById('clearHistoryBtn').addEventListener('click', async () => {
    if (!confirm('Clear all capture history?')) return;
    await chrome.runtime.sendMessage({ action: 'clearHistory' });
    refreshHistory();
  });

  // ── Settings ──────────────────────────────────────────────────────────────
  document.getElementById('settingEnabled').addEventListener('change', (e) => {
    chrome.storage.sync.set({ enabled: e.target.checked });
  });
  document.getElementById('settingNotifications').addEventListener('change', (e) => {
    chrome.storage.sync.set({ showNotifications: e.target.checked });
  });

  // ── Background messages (live queue updates) ──────────────────────────────
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.from !== 'background') return;

    if (msg.action === 'queueUpdated') {
      refreshQueueStatus();
      updateQueueBadge();
    }
    if (msg.action === 'captureComplete') {
      refreshQueueStatus();
      updateQueueBadge();
      // Refresh history if user is on that tab
      if (document.getElementById('tab-history').classList.contains('active')) {
        refreshHistory();
      }
      const label = { created: '✅ Added', updated: '🔄 Updated', exists: '✓ Observation linked', pending_review: 'Awaiting identity review:' };
      showQueueToast(`${label[msg.result] || 'Capture result:'} ${msg.name || 'Profile'}`);
    }
    if (msg.action === 'sessionRefreshed') {
      // Token was silently refreshed — show a subtle indicator
      showQueueToast('🔒 Session renewed');
    }
    if (msg.action === 'activeJobUpdated') {
      const jobBanner = document.getElementById('activeJobBanner');
      if (!jobBanner) return;
      if (msg.job?.job_title) {
        jobBanner.textContent = `📎 Active job: ${msg.job.job_title}${msg.job.job_code ? ` (${msg.job.job_code})` : ''}`;
        jobBanner.style.display = 'block';
      } else {
        jobBanner.style.display = 'none';
      }
    }
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // FUNCTIONS
  // ═══════════════════════════════════════════════════════════════════════════

  function showLogin() {
    document.getElementById('loginSection').style.display = 'flex';
    document.getElementById('dashboardSection').style.display = 'none';
    chrome.storage.sync.get(['vhc_api_url'], (r) => {
      if (r.vhc_api_url) document.getElementById('apiUrl').value = r.vhc_api_url;
    });
  }

  async function showDashboard(user) {
    document.getElementById('loginSection').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'block';
    document.getElementById('userName').textContent = user.name || 'User';
    document.getElementById('userRole').textContent = user.role || 'Member';

    chrome.storage.sync.get(['vhc_api_url'], (r) => {
      document.getElementById('apiUrlDisplay').textContent = r.vhc_api_url || '–';
    });
    chrome.storage.sync.get(['enabled', 'showNotifications'], (r) => {
      document.getElementById('settingEnabled').checked     = r.enabled !== false;
      document.getElementById('settingNotifications').checked = r.showNotifications !== false;
    });

    checkPageStatus();
    refreshQueueStatus();
    updateQueueBadge();
    refreshHistory(); // pre-load history in background
    loadMandates();   // load assigned mandates for dropdown

    // Auto-refresh queue every 3s while popup is open
    setInterval(() => {
      const queueTabActive = document.getElementById('tab-queue').classList.contains('active');
      if (queueTabActive) refreshQueueStatus();
      updateQueueBadge();
    }, 3000);
  }

  // ── Mandate selector ────────────────────────────────────────────────────
  async function loadMandates() {
    const dropdown = document.getElementById('mandateDropdown');
    const infoEl   = document.getElementById('mandateInfo');

    try {
      const result = await chrome.runtime.sendMessage({ action: 'fetchMandates' });
      if (!result || !result.mandates) return;

      const mandates = result.mandates;
      dropdown.innerHTML = '<option value="">No mandate selected (capture only)</option>';
      mandates.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.job_id;
        opt.textContent = `${m.title} — ${m.company || 'N/A'}${m.location ? ' (' + m.location + ')' : ''}`;
        opt.dataset.skills = (m.key_skills || []).join(', ');
        opt.dataset.exp = m.experience_required || (m.min_experience ? `${m.min_experience}-${m.max_experience} yrs` : '');
        opt.dataset.salary = m.salary_range || '';
        dropdown.appendChild(opt);
      });

      // Restore previously selected mandate
      chrome.storage.sync.get(['vhc_active_mandate'], (r) => {
        if (r.vhc_active_mandate) {
          dropdown.value = r.vhc_active_mandate;
          updateMandateInfo();
        }
      });
    } catch (e) {
      console.warn('[VHC Popup] Failed to load mandates:', e);
    }
  }

  function updateMandateInfo() {
    const dropdown = document.getElementById('mandateDropdown');
    const infoEl   = document.getElementById('mandateInfo');
    const selected = dropdown.options[dropdown.selectedIndex];

    if (!dropdown.value) {
      infoEl.style.display = 'none';
      chrome.storage.sync.set({ vhc_active_mandate: '' });
      return;
    }

    const skills = selected.dataset.skills || 'N/A';
    const exp    = selected.dataset.exp || 'N/A';
    const salary = selected.dataset.salary || 'N/A';
    infoEl.innerHTML = `Skills: <span>${skills}</span> | Exp: <span>${exp}</span> | Budget: <span>${salary}</span>`;
    infoEl.style.display = 'block';

    // Save selection
    chrome.storage.sync.set({ vhc_active_mandate: dropdown.value });
  }

  document.getElementById('mandateDropdown').addEventListener('change', updateMandateInfo);

  async function checkPageStatus() {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const captureBtn = document.getElementById('manualCaptureBtn');

      if (!tab?.url) { setPageStatus('gray', 'Unknown page'); return; }
      const url = tab.url;

      if (url.includes('naukri.com')) {
        const isProfile =
          (url.includes('/v3/preview') && url.includes('tabKey=profile')) ||
          /viewResume|view-resume|cvPreview/.test(url);
        if (isProfile) {
          setPageStatus('green', 'Naukri profile — ready to capture');
          captureBtn.disabled = false;
        } else {
          setPageStatus('yellow', 'Naukri page (navigate to a profile)');
          captureBtn.disabled = true;
        }
      } else if (url.includes('linkedin.com')) {
        const isProfile = /linkedin\.com\/in\/[^/?#]+\/?(\?.*)?$/.test(url);
        if (isProfile) {
          setPageStatus('green', 'LinkedIn profile — ready to capture');
          captureBtn.disabled = false;
        } else {
          setPageStatus('yellow', 'LinkedIn (navigate to a profile)');
          captureBtn.disabled = true;
        }
      } else if (url.includes('foundit.in') || url.includes('foundit.sg') || url.includes('monster.com')) {
        const isProfile = /\/(profile|resume|cv)\//.test(url);
        if (isProfile) {
          setPageStatus('green', 'Foundit profile — ready to capture');
          captureBtn.disabled = false;
        } else {
          setPageStatus('yellow', 'Foundit (navigate to a profile)');
          captureBtn.disabled = true;
        }
      } else {
        setPageStatus('gray', 'Open a Naukri, LinkedIn, or Foundit profile');
        captureBtn.disabled = true;
      }
    } catch (_) { setPageStatus('red', 'Error checking page'); }
  }

  function setPageStatus(color, text) {
    document.getElementById('statusDot').className = `status-dot ${color}`;
    document.getElementById('pageStatusText').textContent = text;
  }

  // ── Queue rendering ────────────────────────────────────────────────────────

  async function refreshQueueStatus() {
    const status = await chrome.runtime.sendMessage({ action: 'getQueueStatus' });
    if (!status) return;

    const { captureQueue, offlineQueue, deadLetterQueue } = status;

    // Update stat numbers
    document.getElementById('qsCaptureTotal').textContent = captureQueue.total;
    document.getElementById('qsOfflineTotal').textContent = offlineQueue.total;
    document.getElementById('qsDeadTotal').textContent    = deadLetterQueue.total;

    // Live dot
    const liveDot = document.getElementById('liveDot');
    liveDot.className = captureQueue.processing > 0 ? 'live-dot' : 'live-dot idle';

    // Render queue item list (captureQueue items + dead letter)
    const listEl = document.getElementById('queueList');
    const allItems = [
      ...captureQueue.items,
      ...deadLetterQueue.items.map(i => ({ ...i, status: 'failed' }))
    ];

    if (allItems.length === 0) {
      listEl.innerHTML = '<div class="queue-empty">Queue is empty</div>';
    } else {
      listEl.innerHTML = allItems.map(item => {
        const status = item.status || 'pending';
        const badge  = { pending: 'Pending', processing: 'Processing', retry: 'Retry', failed: 'Failed' }[status] || status;
        const errorHint = item.error ? ` — ${item.error.substring(0, 40)}` : (item.reason ? ` — ${item.reason.substring(0, 40)}` : '');
        return `
          <div class="queue-item" title="${item.name}${errorHint}">
            <span class="qi-dot ${status}"></span>
            <span class="qi-name">${item.name || item.profileId || 'Unknown'}</span>
            <span class="qi-badge ${status}">${badge}</span>
          </div>
        `;
      }).join('');
    }

    // ETA row
    const pendingCount = captureQueue.pending + captureQueue.retry + captureQueue.processing;
    const etaRow = document.getElementById('queueEtaRow');
    if (pendingCount > 0) {
      const etaSec = pendingCount * AVG_SECONDS_PER_CANDIDATE;
      const etaText = etaSec < 60 ? `~${etaSec}s` : `~${Math.ceil(etaSec / 60)} min`;
      document.getElementById('queueEta').textContent = `${etaText} (${pendingCount} remaining)`;
      etaRow.style.display = 'block';
    } else {
      etaRow.style.display = 'none';
    }

    // Show/hide dead letter actions
    document.getElementById('retryDeadBtn').style.display = deadLetterQueue.total > 0 ? 'inline-block' : 'none';
    document.getElementById('clearDeadBtn').style.display = deadLetterQueue.total > 0 ? 'inline-block' : 'none';

    // Offline queue note
    const offlineNote = document.getElementById('offlineQueueNote');
    if (offlineQueue.total > 0) {
      offlineNote.style.display = 'block';
      document.getElementById('offlineQueueCount').textContent = offlineQueue.total;
    } else {
      offlineNote.style.display = 'none';
    }
  }

  // ── Capture History rendering ──────────────────────────────────────────────

  /**
   * Determine the colour state for an E or M indicator circle.
   *
   * GREEN  — data was captured AND the record is new (action = created)
   * YELLOW — data is missing/hidden (null/empty)
   * RED    — data exists but record is duplicate/suspicious (action = exists|updated|failed)
   *          OR: Option C — red if EITHER condition (duplicate OR suspicious data)
   *
   * @param {string|null} value  - the captured email or phone string
   * @param {string}      action - created | updated | exists | failed
   * @returns {'green'|'yellow'|'red'}
   */
  function emState(value, action) {
    if (action === 'pending_review') return 'yellow';
    const hasValue = value && value.trim().length > 0;

    // Missing / hidden on Naukri → yellow
    if (!hasValue) return 'yellow';

    // Data captured AND brand new record → green
    if (action === 'created') return 'green';

    // Data exists but already in databank (updated/exists) OR failed → red
    // This catches: duplicate captures, recruiter number accidentally captured, etc.
    return 'red';
  }

  function emCircleHTML(letter, state, tooltip) {
    return `<div class="em-circle em-${state}" title="${escHtml(tooltip)}">${letter}</div>`;
  }

  async function refreshHistory() {
    const res = await chrome.runtime.sendMessage({ action: 'getHistory' });
    const history = res?.history || [];

    const listEl = document.getElementById('historyList');

    // Summary chips
    const counts = { created: 0, updated: 0, exists: 0, pending_review: 0, failed: 0 };
    history.forEach(h => { if (counts[h.action] !== undefined) counts[h.action]++; });
    document.getElementById('historySummary').innerHTML = `
      <span class="hist-chip chip-added">${counts.created} Added</span>
      <span class="hist-chip chip-updated">${counts.updated} Updated</span>
      <span class="hist-chip chip-exists">${counts.exists} Exists</span>
      <span class="hist-chip chip-updated">${counts.pending_review} Awaiting review</span>
      <span class="hist-chip chip-failed">${counts.failed} Failed</span>
    `;

    if (history.length === 0) {
      listEl.innerHTML = '<div class="queue-empty">No captures yet</div>';
      return;
    }

    const icons   = { created: '✓', updated: '↑', exists: '=', pending_review: '…', failed: '✕' };
    const labels  = { created: 'Added', updated: 'Updated', exists: 'Exists', pending_review: 'Awaiting review', failed: 'Failed' };

    listEl.innerHTML = history.map(item => {
      const action = item.action || 'exists';
      const icon   = icons[action]  || '?';
      const label  = labels[action] || action;
      const time   = item.timestamp ? formatTime(item.timestamp) : '';

      // ── E / M indicator logic ──
      const eState = emState(item.email, action);
      const mState = emState(item.phone, action);

      const eTooltip = action === 'pending_review' ? 'Identity review pending; no person assigned' : eState === 'green'  ? `Email: ${item.email}` :
                       eState === 'yellow' ? 'Email: hidden / not captured' :
                       `Email: ${item.email || 'unknown'} — duplicate/suspicious`;

      const mTooltip = action === 'pending_review' ? 'Identity review pending; no person assigned' : mState === 'green'  ? `Mobile: ${item.phone}` :
                       mState === 'yellow' ? 'Mobile: hidden / not captured' :
                       `Mobile: ${item.phone || 'unknown'} — duplicate/suspicious`;

      const indicators = `
        <div class="hist-indicators">
          ${emCircleHTML('E', eState, eTooltip)}
          ${emCircleHTML('M', mState, mTooltip)}
        </div>`;

      const meta = [
        item.bulk ? '⚡ Bulk' : '📄 Single',
        time,
        item.error ? `⚠ ${item.error.substring(0, 40)}` : ''
      ].filter(Boolean).join(' · ');

      const profileLink = item.profileUrl
        ? `<a href="${item.profileUrl}" target="_blank" style="color:#7CB342;text-decoration:none;font-size:10px;" title="Open profile">↗</a>`
        : '';

      return `
        <div class="hist-card hc-${action}">
          <div class="hist-icon">${icon}</div>
          <div class="hist-body">
            <div class="hist-name">${escHtml(item.name || 'Unknown')} ${profileLink}</div>
            <div class="hist-meta">${escHtml(meta)}</div>
          </div>
          ${indicators}
          <div class="hist-status">${label}</div>
        </div>
      `;
    }).join('');
  }

  function formatTime(iso) {
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now - d;
      const diffMin = Math.floor(diffMs / 60000);
      if (diffMin < 1)  return 'just now';
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHr = Math.floor(diffMin / 60);
      if (diffHr < 24)  return `${diffHr}h ago`;
      return d.toLocaleDateString();
    } catch (_) { return ''; }
  }

  function escHtml(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  async function updateQueueBadge() {
    const status = await chrome.runtime.sendMessage({ action: 'getQueueStatus' });
    if (!status) return;
    const total = status.captureQueue.total + status.deadLetterQueue.total;
    const badge = document.getElementById('queueBadge');
    if (total > 0) {
      badge.textContent = `(${total})`;
      badge.style.color = status.deadLetterQueue.total > 0 ? '#ef4444' : '#7CB342';
    } else {
      badge.textContent = '';
    }
  }

  // ── Toast for queue events ─────────────────────────────────────────────────
  function showQueueToast(msg) {
    let toast = document.getElementById('queueToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'queueToast';
      toast.style.cssText = `
        position:fixed;bottom:14px;left:50%;transform:translateX(-50%);
        background:#1e293b;color:white;padding:7px 14px;border-radius:20px;
        font-size:12px;font-weight:500;z-index:9999;white-space:nowrap;
        opacity:0;transition:opacity 0.25s;pointer-events:none;
      `;
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { toast.style.opacity = '0'; }, 3000);
  }

  // ── Progress bar ──────────────────────────────────────────────────────────
  function setProgress(pct, text) {
    const tp = document.getElementById('taskProgress');
    tp.classList.add('visible');
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressStepText').textContent = text;
    document.getElementById('progressPercent').textContent  = pct + '%';
    document.getElementById('progressTick').classList.toggle('show', pct >= 100);
  }
  function resetProgress() {
    document.getElementById('taskProgress').classList.remove('visible');
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('progressPercent').textContent = '0%';
    document.getElementById('progressTick').classList.remove('show');
  }

  function showLoginError(msg) {
    const el = document.getElementById('loginError');
    el.textContent = msg;
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; }, 5000);
  }

  function showCaptureStatus(type, msg) {
    const el = document.getElementById('captureStatus');
    el.textContent = msg;
    el.className = `capture-result visible ${type}`;
    if (type !== 'error') {
      setTimeout(() => {
        el.classList.remove('visible');
        if (type === 'success') setTimeout(() => resetProgress(), 500);
      }, 7000);
    }
  }
  function hideCaptureStatus() {
    document.getElementById('captureStatus').className = 'capture-result';
  }

  // ── Update-available banner (v6.0.0) ───────────────────────────────────────
  async function checkForExtensionUpdate() {
    const localVersion = chrome.runtime.getManifest().version;
    const { vhc_api_url } = await chrome.storage.sync.get(['vhc_api_url']);
    const apiUrl = (vhc_api_url || 'https://ventureshrd.com').replace(/\/$/, '');

    let latest;
    try {
      const res = await fetch(`${apiUrl}/api/extension/version`, { method: 'GET' });
      if (!res.ok) return;
      latest = (await res.json()).version;
    } catch (_) { return; }

    if (!latest || !isNewerVersion(latest, localVersion)) return;

    const banner = document.getElementById('updateBanner');
    const msg = document.getElementById('updateBannerMsg');
    const btn = document.getElementById('updateBannerBtn');
    const isCrxInstall = !!chrome.runtime.getManifest().update_url &&
                         !chrome.runtime.id.startsWith('temp');

    msg.textContent = `Version ${latest} is available (you're on v${localVersion}).`;
    banner.style.display = 'flex';

    btn.addEventListener('click', () => {
      if (isCrxInstall && chrome.runtime.requestUpdateCheck) {
        btn.disabled = true;
        btn.textContent = 'Checking…';
        chrome.runtime.requestUpdateCheck((status) => {
          if (status === 'update_available') {
            msg.textContent = `Downloading v${latest}… Chrome will install it automatically (the extension restarts itself).`;
            btn.style.display = 'none';
            // Reload applies a downloaded update immediately
            setTimeout(() => chrome.runtime.reload(), 4000);
          } else if (status === 'no_update') {
            msg.textContent = `Chrome hasn't published v${latest} to your browser yet — it auto-installs within a few hours. Nothing else to do.`;
            btn.style.display = 'none';
          } else { // throttled
            msg.textContent = 'Chrome is rate-limiting update checks — it will auto-update within a few hours.';
            btn.style.display = 'none';
          }
        });
      } else {
        // Unpacked dev install — cannot self-update
        msg.textContent = `You're on an unpacked dev build. Download v${latest} from the VHC admin panel and re-load it.`;
        btn.style.display = 'none';
      }
    });
  }

  // "6.0.0" vs "5.5.10" → true (numeric per-segment compare, not string)
  function isNewerVersion(remote, local) {
    const r = String(remote).split('.').map(Number);
    const l = String(local).split('.').map(Number);
    for (let i = 0; i < Math.max(r.length, l.length); i++) {
      const a = r[i] || 0, b = l[i] || 0;
      if (a > b) return true;
      if (a < b) return false;
    }
    return false;
  }

});
