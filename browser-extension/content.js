/**
 * VHC Talent OS - Naukri Resdex Profile Scraper v5.2.0
 * 
 * Multi-Source Cross-Validation Pipeline:
 * 1. Wait for DOM to stabilize (title check) after SPA navigation
 * 2. Scroll page to load all content (including lazy-loaded CV preview)
 * 3. Extract name from page title (most reliable source)
 * 4. SNAPSHOT all emails/phones on page (= recruiter's baseline)
 * 5. Click "View Contact" → SNAPSHOT again → DIFF = candidate's contacts
 * 6. Scan CV iframe for email/phone/text (candidate's resume, guaranteed clean)
 * 7. Cross-validate: CV > Before/After Diff > DOM selectors > AI
 * 8. Send merged contacts + CV text + page text to AI for structured extraction
 * 9. Send final data to capture endpoint
 */

(function() {
  'use strict';

  // ===================== IFRAME CV RELAY (runs INSIDE iframes) =====================
  // If this script is running inside an iframe, extract CV text and relay to background.
  // This solves the cross-origin iframe problem on Naukri Resdex.
  if (window.self !== window.top) {
    // We're inside an iframe — check if we should extract CV content
    const _iframeUrl = window.location.href;
    const _isNaukriDomain = /naukri\.com/i.test(window.location.hostname);

    if (_isNaukriDomain) {
      const _extractAndRelay = () => {
        try {
          if (!chrome || !chrome.runtime || !chrome.runtime.id) return;
          let bodyText = document.body ? (document.body.innerText || document.body.textContent || '') : '';
          // v6.3.0: viewer-in-viewer — pull text from same-origin CHILD
          // frames as well (blob: children are same-origin with us here).
          try {
            document.querySelectorAll('iframe').forEach((child) => {
              try {
                const t = child.contentDocument?.body?.innerText || '';
                if (t && t.length > 30) bodyText += '\n' + t;
              } catch (_) {}
            });
          } catch (_) {}
          if (bodyText.length < 30) return; // Too short, probably not loaded yet

          // Extract emails from CV text
          const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
          const emails = (bodyText.match(emailRegex) || [])
            .map(e => e.toLowerCase().trim())
            .filter(e => !/@naukri\.com|@example\.|@test\.|noreply@|support@/i.test(e));

          // Extract phones from CV text (Indian mobile: starts with 6-9, 10 digits)
          const phoneMatches = bodyText.match(/(?:\+91[\s.-]?)?[6-9]\d[\s.-]?\d{4}[\s.-]?\d{4}/g) || [];
          const phones = phoneMatches
            .map(p => p.replace(/\D/g, '').slice(-10))
            .filter(p => p.length === 10 && /^[6-9]/.test(p));

          // Extract structured sections from CV text
          const lines = bodyText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
          const sectionHeaders = {
            objective: /^(career\s*objective|objective|summary|profile\s*summary|professional\s*summary|about\s*me)/i,
            experience: /^(work\s*experience|experience|employment|professional\s*experience|work\s*history)/i,
            education: /^(education|academic|qualification|educational\s*qualification)/i,
            skills: /^(skills|technical\s*skills|key\s*skills|core\s*competencies|competencies|it\s*skills)/i,
            certifications: /^(certifications?|certificates?|courses?|training)/i,
            projects: /^(projects?|key\s*projects?|notable\s*projects?)/i,
            languages: /^(languages?|language\s*known|languages\s*known)/i,
            personal: /^(personal\s*details|personal\s*information|personal\s*data|personal)/i,
            achievements: /^(achievements?|awards?|accomplishments?|honors?)/i,
          };
          let currentSection = 'header';
          const sections = { header: [] };
          for (const line of lines) {
            let matched = false;
            for (const [key, pattern] of Object.entries(sectionHeaders)) {
              if (pattern.test(line) && line.length < 60) {
                currentSection = key;
                if (!sections[currentSection]) sections[currentSection] = [];
                matched = true;
                break;
              }
            }
            if (!matched) {
              if (!sections[currentSection]) sections[currentSection] = [];
              sections[currentSection].push(line);
            }
          }

          // Extract LinkedIn URL
          const linkedinMatch = bodyText.match(/(?:https?:\/\/)?(?:www\.)?linkedin\.com\/in\/[a-zA-Z0-9_-]+/i);

          console.log(`[VHC IFRAME] Extracted ${bodyText.length} chars from CV iframe, emails: ${emails.length}, phones: ${phones.length}`);

          chrome.runtime.sendMessage({
            action: 'cvIframeData',
            data: {
              text: bodyText.substring(0, 15000),
              url: _iframeUrl,
              emails: emails,
              phones: phones,
              sections: sections,
              linkedin: linkedinMatch ? linkedinMatch[0] : null,
            }
          }, () => {
            if (chrome.runtime.lastError) {
              // Ignore — background may not be ready
            }
          });
        } catch (e) {
          console.warn('[VHC IFRAME] Error extracting CV data:', e.message);
        }
      };

      // v6.2.1 — PERSISTENT WATCHER. The old fire-and-forget retries
      // (load +1.5s +4s) missed every CV that finished loading later —
      // the exact slow-internet failure. Now a MutationObserver relays
      // (debounced) EVERY time the document grows, until the CV is
      // substantial and stable or the 90s watch window ends. Background
      // keeps the best snapshot, so late paint = late relay = captured.
      let _relayDebounce = null;
      const _extractDebounced = () => {
        if (_relayDebounce) clearTimeout(_relayDebounce);
        _relayDebounce = setTimeout(_extractAndRelay, 400);
      };

      const _tryExtract = () => {
        _extractAndRelay();
        setTimeout(_extractAndRelay, 1500);
        setTimeout(_extractAndRelay, 4000);
      };

      if (document.readyState === 'complete') {
        setTimeout(_tryExtract, 300);
      } else {
        window.addEventListener('load', () => setTimeout(_tryExtract, 300));
      }

      try {
        const _watchStart = Date.now();
        const _mo = new MutationObserver(() => {
          _extractDebounced();
          if (Date.now() - _watchStart > 90000) { try { _mo.disconnect(); } catch (_) {} }
        });
        const _attachMO = () => {
          try {
            _mo.observe(document.documentElement || document,
                        { subtree: true, childList: true, characterData: true });
          } catch (_) {}
        };
        if (document.documentElement) _attachMO();
        else window.addEventListener('DOMContentLoaded', _attachMO);
      } catch (e) {}

      // Explicit extraction requests: from background relay…
      try {
        chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
          if (request.action === 'requestCVExtraction') {
            _extractAndRelay();
            sendResponse({ success: true });
          }
          return false;
        });
      } catch (e) {}
      // …and from the parent page's postMessage nudge (previously had no
      // listener at all — the nudge was dead code).
      try {
        window.addEventListener('message', (ev) => {
          if (ev?.data?.action === 'vhc_extract_cv') _extractAndRelay();
        });
      } catch (e) {}
    }

    // Don't initialize the full capture script inside iframes
    return;
  }

  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  const VERSION = '6.3.1';
  const CONFIG = {
    CAPTURE_DELAY: 2000,
    SCROLL_DELAY: 150,
    TOAST_DURATION: 5000,
    BULK_SCROLL_DELAY: 600,     // wait per scroll step when loading list pages
    BULK_MAX_CANDIDATES: 100,   // cap per bulk sweep
  };

  // ===================== PLATFORM DETECTION =====================

  /**
   * Detect which job portal we're running on.
   * Returns: 'naukri' | 'linkedin' | 'foundit' | null
   */
  function detectPlatform() {
    const host = window.location.hostname;
    if (host.includes('naukri.com'))   return 'naukri';
    if (host.includes('linkedin.com')) return 'linkedin';
    if (host.includes('foundit.in') || host.includes('foundit.sg') || host.includes('foundit.my') || host.includes('monster.com')) return 'foundit';
    return null;
  }

  const PLATFORM = detectPlatform();
  console.log(`[VHC v${VERSION}] Platform: ${PLATFORM || 'unknown'} on ${window.location.hostname}`);

  let isCapturing = false;
  let lastCapturedUrl = null;
  let lastPageUrl = window.location.href;

  console.log(`[VHC v${VERSION}] Content script loaded on:`, window.location.href);

  // SPA navigation detection: reset state when URL changes and re-trigger capture on profile pages
  setInterval(() => {
    if (window.location.href !== lastPageUrl) {
      console.log(`[VHC v${VERSION}] URL changed: ${lastPageUrl} -> ${window.location.href}`);
      lastPageUrl = window.location.href;
      lastCapturedUrl = null; // Allow re-capture on new page

      // Disconnect infinite scroll observer from previous page
      if (cardObserver) {
        cardObserver.disconnect();
        cardObserver = null;
      }

      // Clean up any lingering UI from previous page capture
      const oldBar = document.getElementById('vhc-progress-bar');
      if (oldBar) oldBar.remove();
      const oldToast = document.getElementById('vhc-toast');
      if (oldToast) oldToast.remove();
      isCapturing = false; // Reset in case previous capture was mid-flight

      // Skip Naukri pages we explicitly do NOT want to operate on
      // (e.g. /v3/simcv — "Recruiters also viewed" / similar-CV suggestion view)
      if (PLATFORM === 'naukri' && isExcludedNaukriPage()) {
        console.log(`[VHC v${VERSION}] Excluded Naukri page (${window.location.pathname}) — extension will not run here`);
        return;
      }

      // Re-trigger auto-capture if navigated to a profile page
      if (isProfilePage() && !isCapturing) {
        getSettings().then(settings => {
          if (settings.enabled && settings.autoCapture) {
            console.log(`[VHC v${VERSION}] Navigated to profile page (${PLATFORM}), scheduling auto-capture`);
            setTimeout(() => autoCapture(), CONFIG.CAPTURE_DELAY);
          }
        });
      }

      // Show bulk button if navigated to a Naukri search/list page
      if (PLATFORM === 'naukri' && isSearchPage()) {
        getAuthToken().then(auth => {
          if (auth) {
            console.log(`[VHC v${VERSION}] Navigated to search page, showing bulk capture button`);
            setTimeout(() => addBulkCaptureButton(), 1500);
            
            // Also run checkAndMarkExistingProfiles on navigation to search results
            setTimeout(() => {
              checkAndMarkExistingProfiles();
              observeNewCards();
            }, 1000);
          }
        });
      }
    }
  }, 1000);

  // ===================== EXTENSION CONTEXT GUARD =====================
  function isExtensionValid() {
    try { return !!(chrome && chrome.runtime && chrome.runtime.id); } catch (e) { return false; }
  }
  function handleInvalidContext() {
    showToast('Extension updated. Refresh page (F5).', 'error');
  }

  // ===================== UTILITY =====================
  function cleanText(t) { return t ? t.replace(/\s+/g, ' ').trim() : null; }
  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  function escapeHTML(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ===================== FLOATING PROGRESS BAR (shown on page for both manual & auto capture) =====================
  
  function showProgressBar() {
    let bar = document.getElementById('vhc-progress-bar');
    if (bar) bar.remove();
    
    bar = document.createElement('div');
    bar.id = 'vhc-progress-bar';
    bar.innerHTML = `
      <style>
        #vhc-progress-bar {
          position: fixed; bottom: 20px; right: 20px; z-index: 999999;
          background: white; border-radius: 12px; padding: 14px 18px; width: 280px;
          box-shadow: 0 4px 20px rgba(0,0,0,0.15); font-family: -apple-system, BlinkMacSystemFont, sans-serif;
          animation: vhcSlideIn 0.3s ease;
        }
        @keyframes vhcSlideIn { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        #vhc-progress-bar .vhc-pb-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        #vhc-progress-bar .vhc-pb-title { font-size: 13px; font-weight: 600; color: #1e293b; }
        #vhc-progress-bar .vhc-pb-percent { font-size: 12px; font-weight: 600; color: #7CB342; }
        #vhc-progress-bar .vhc-pb-step { font-size: 11px; color: #64748b; margin-bottom: 6px; }
        #vhc-progress-bar .vhc-pb-track { width: 100%; height: 6px; background: #e8f5e9; border-radius: 100px; overflow: visible; position: relative; }
        #vhc-progress-bar .vhc-pb-fill { height: 100%; background: linear-gradient(90deg, #AED581, #7CB342, #558B2F); border-radius: 100px; transition: width 0.5s ease; width: 0%; position: relative; }
        #vhc-progress-bar .vhc-pb-tick { position: absolute; right: -10px; top: 50%; transform: translateY(-50%) scale(0); width: 20px; height: 20px; background: #43A047; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 6px rgba(67,160,71,0.4); transition: transform 0.3s ease; }
        #vhc-progress-bar .vhc-pb-tick.show { transform: translateY(-50%) scale(1); }
        #vhc-progress-bar .vhc-pb-tick svg { width: 12px; height: 12px; stroke: white; stroke-width: 3; fill: none; }
      </style>
      <div class="vhc-pb-header">
        <span class="vhc-pb-title">VHC Capture</span>
        <span class="vhc-pb-percent" id="vhcPbPercent">0%</span>
      </div>
      <div class="vhc-pb-step" id="vhcPbStep">Starting...</div>
      <div class="vhc-pb-track">
        <div class="vhc-pb-fill" id="vhcPbFill">
          <div class="vhc-pb-tick" id="vhcPbTick">
            <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(bar);
  }
  
  function updateProgress(percent, stepText) {
    const fill = document.getElementById('vhcPbFill');
    const step = document.getElementById('vhcPbStep');
    const pct = document.getElementById('vhcPbPercent');
    const tick = document.getElementById('vhcPbTick');
    if (!fill) return;
    fill.style.width = percent + '%';
    if (step) step.textContent = stepText;
    if (pct) pct.textContent = percent + '%';
    if (tick) {
      if (percent >= 100) tick.classList.add('show');
      else tick.classList.remove('show');
    }
  }
  
  function hideProgressBar(delay = 3000) {
    setTimeout(() => {
      const bar = document.getElementById('vhc-progress-bar');
      if (bar) { bar.style.opacity = '0'; bar.style.transition = 'opacity 0.3s'; setTimeout(() => bar.remove(), 300); }
    }, delay);
  }

  // ===================== DOM STABILITY CHECK =====================
  
  /**
   * Wait for the page DOM to stabilize after SPA navigation.
   * Uses MutationObserver to detect when DOM activity quiets down.
   * Falls back to a 300ms minimum wait. Much faster than fixed 1500-3500ms sleeps.
   */
  async function waitForDOMStability() {
    const title1 = document.title;
    console.log(`[VHC v${VERSION}] DOM stability check: title1="${title1}"`);

    await new Promise((resolve) => {
      let quietTimer = null;
      const QUIET_PERIOD = 300; // resolve if no DOM mutations for 300ms
      const MAX_WAIT = 2500;    // never wait more than 2.5s regardless
      const maxTimer = setTimeout(resolve, MAX_WAIT);

      const observer = new MutationObserver(() => {
        clearTimeout(quietTimer);
        quietTimer = setTimeout(() => {
          observer.disconnect();
          clearTimeout(maxTimer);
          resolve();
        }, QUIET_PERIOD);
      });

      observer.observe(document.body, { childList: true, subtree: true, attributes: false });

      // If DOM is already quiet, resolve after one quiet period
      quietTimer = setTimeout(() => {
        observer.disconnect();
        clearTimeout(maxTimer);
        resolve();
      }, QUIET_PERIOD);
    });

    const stableTitle = document.title;
    console.log(`[VHC v${VERSION}] DOM stable. Title: "${stableTitle}"`);
    return stableTitle;
  }

  // ===================== BACKGROUND TAB CANDIDATE PROFILE VALIDATION =====================
  
  /**
   * v5.4.1 FIX: Ensure candidate profile content is actually loaded before extracting.
   * 
   * Background tabs have throttled JS execution and lazy DOM rendering.
   * This function waits until we can VERIFY candidate-specific elements exist,
   * to avoid accidentally scraping the recruiter's header/nav info.
   *
   * Returns: { ready: boolean, candidateName: string|null, reason: string }
   */
  async function waitForCandidateProfile() {
    const isBackground = document.hidden;
    const MAX_WAIT_MS = isBackground ? 15000 : 8000; // Max wait for candidate profile to load (increased to 15s for bg tabs)
    const CHECK_INTERVAL_MS = 500;
    const requiredScore = isBackground ? 2 : 3; // Lower threshold to 2 for background tabs
    const startTime = Date.now();
    let lastLog = '';

    console.log(`[VHC v${VERSION}] Waiting for candidate profile to load... (${isBackground ? 'background tab' : 'foreground tab'}, max ${MAX_WAIT_MS}ms, threshold ${requiredScore}/4)`);

    while (Date.now() - startTime < MAX_WAIT_MS) {
      // Check 1: Page title should contain a candidate name (not just "Naukri Resdex")
      const title = document.title || '';
      const titleHasName = title.length > 15 && 
                           !title.toLowerCase().startsWith('naukri') &&
                           !title.toLowerCase().startsWith('recruiter') &&
                           !title.toLowerCase().includes('search results');

      // Check 2: Profile container exists with visible text content
      const candidateRoot = getCandidateRootSafe();
      const rootTextLen = candidateRoot ? (candidateRoot.innerText || '').length : 0;
      const hasSubstantialContent = rootTextLen > 500;

      // Check 3: Key profile elements exist (work experience, skills, education markers)
      const hasProfileMarkers = !!(
        document.querySelector('[class*="experienc"], [class*="Experience"]') ||
        document.querySelector('[class*="skill"], [class*="Skill"]') ||
        document.querySelector('[class*="education"], [class*="Education"]') ||
        document.querySelector('[class*="summary"], [class*="Summary"]') ||
        document.querySelector('[class*="profileSnap"], [class*="profile-snap"]') ||
        document.querySelector('[class*="tupleDetail"], [class*="tuple-detail"]')
      );

      // Check 4: "View Contact" button OR visible contact section exists
      const hasContactSection = !!(
        document.querySelector('[class*="viewContact"], [class*="view-contact"]') ||
        document.querySelector('button[class*="contact"]') ||
        document.querySelector('[class*="contactInfo"], [class*="contact-info"]') ||
        document.querySelector('i.naukri-icon-phone, i.naukri-icon-email')
      );

      const checkStatus = `title=${titleHasName}, content=${hasSubstantialContent}(${rootTextLen}), markers=${hasProfileMarkers}, contact=${hasContactSection}`;
      if (checkStatus !== lastLog) {
        console.log(`[VHC v${VERSION}] Profile checks: ${checkStatus}`);
        lastLog = checkStatus;
      }

      // Ready if at least requiredScore conditions are met
      const readyScore = [titleHasName, hasSubstantialContent, hasProfileMarkers, hasContactSection].filter(Boolean).length;
      
      if (readyScore >= requiredScore) {
        const candidateName = extractNameFromTitle();
        console.log(`[VHC v${VERSION}] ✅ Candidate profile READY: "${candidateName || 'Unknown'}" (score: ${readyScore}/${requiredScore})`);
        return { ready: true, candidateName, reason: `Score ${readyScore}/${requiredScore}` };
      }

      // Wait before next check
      await sleep(CHECK_INTERVAL_MS);
    }

    // Timeout — profile didn't load properly
    console.warn(`[VHC v${VERSION}] ⚠️ Candidate profile load TIMEOUT after ${MAX_WAIT_MS}ms`);
    return { ready: false, candidateName: null, reason: 'Timeout waiting for profile' };
  }

  /**
   * Safe version of getCandidateRoot that returns null if no valid container found.
   * Used during profile validation to avoid falling back to document.body.
   */
  function getCandidateRootSafe() {
    for (const sel of CANDIDATE_ROOT_SELECTORS) {
      const el = document.querySelector(sel);
      // Skip if element has very little content (likely not loaded yet)
      if (el && (el.innerText || '').length > 200) return el;
    }
    return null;
  }

  // ===================== RECRUITER BLOCKLIST =====================

  /**
   * Get the logged-in recruiter's email and phone from chrome.storage
   * so we can EXCLUDE them from candidate contact extraction.
   */
  async function getRecruiterCredentials() {
    if (!isExtensionValid()) return { email: null, phone: null };
    try {
      return await new Promise((resolve, reject) => {
        chrome.storage.sync.get(['vhc_user'], (result) => {
          if (chrome.runtime.lastError) return reject(chrome.runtime.lastError);
          const user = result.vhc_user || {};
          resolve({
            email: (user.email || '').toLowerCase().trim() || null,
            phone: (user.phone || '').replace(/[\s.-]/g, '') || null,
          });
        });
      });
    } catch (e) {
      console.warn(`[VHC v${VERSION}] Could not read recruiter credentials:`, e);
      return { email: null, phone: null };
    }
  }

  /**
   * Check if an email belongs to the recruiter (should be excluded).
   */
  function isRecruiterEmail(email, recruiterEmail) {
    if (!email || !recruiterEmail) return false;
    return email.toLowerCase().trim() === recruiterEmail.toLowerCase().trim();
  }

  /**
   * Check if a phone number belongs to the recruiter (should be excluded).
   */
  function isRecruiterPhone(phone, recruiterPhone) {
    if (!phone || !recruiterPhone) return false;
    // Normalize: strip +91, spaces, dashes — compare last 10 digits
    const clean = (p) => p.replace(/[\s.+\-()]/g, '').slice(-10);
    return clean(phone) === clean(recruiterPhone);
  }

  /**
   * v6.0.2 FIX (Sachin/ajit bug): Detect emails that belong to the Naukri-
   * logged-in account (page chrome / header / user dropdown). These emails
   * are session-scoped to the Naukri tab and are NOT covered by
   * `chrome.storage.sync.vhc_user.email` because:
   *   - chrome.storage stores the VHC platform login (e.g. sachin@vhc.in)
   *   - Naukri session login may be a different account (e.g. ajit@searchpartner.in)
   *     when teams share a Naukri seat.
   *
   * Without this filter, the BEFORE-snapshot fallback inside mergeContacts()
   * picked up the Naukri header email and saved it as the candidate's email
   * on the very first capture (only fixed itself on recapture because CV
   * iframe became cached).
   *
   * Returns a Set<string> of lowercase emails found in the page chrome.
   */
  function snapshotChromeEmails() {
    const chromeEmails = new Set();
    const addIfEmail = (raw) => {
      if (!raw) return;
      const s = String(raw).toLowerCase().trim();
      // Use a strict per-string match (not global) so we accept the whole string only
      if (/^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(s)) {
        if (!isNaukriSystemEmail(s)) chromeEmails.add(s);
      }
    };

    // 1) Naukri recruiter header / user-dropdown / utility-nav — explicit selectors
    const headerSelectors = [
      'header', '[class*="header"]', '[class*="Header"]',
      'nav', '[class*="nav"]', '[class*="Nav"]',
      '[class*="userInfo"]', '[class*="user-info"]', '[class*="UserInfo"]',
      '[class*="userDropdown"]', '[class*="user-dropdown"]', '[class*="UserDropdown"]',
      '[class*="userMenu"]', '[class*="user-menu"]', '[class*="UserMenu"]',
      '[class*="loggedInUser"]', '[class*="logged-in-user"]',
      '[class*="profileMenu"]', '[class*="profile-menu"]',
      '[class*="topBar"]', '[class*="top-bar"]', '[class*="TopBar"]',
      '[class*="utilityNav"]', '[class*="utility-nav"]',
      // Naukri-specific recruiter shell:
      '#root header', '#root nav', '.rdx-header', '.rdx-top-bar',
      '[class*="recruiterHeader"]', '[class*="recruiter-header"]',
    ];
    for (const sel of headerSelectors) {
      try {
        document.querySelectorAll(sel).forEach(el => {
          const txt = el.innerText || el.textContent || '';
          (txt.match(EMAIL_REGEX) || []).forEach(addIfEmail);
          // title attributes within header
          el.querySelectorAll('[title*="@"]').forEach(t => addIfEmail(t.getAttribute('title')));
          // data attributes occasionally hold the logged-in email
          ['data-email', 'data-user-email', 'data-username'].forEach(attr => {
            el.querySelectorAll(`[${attr}*="@"]`).forEach(d => addIfEmail(d.getAttribute(attr)));
          });
        });
      } catch (_) { /* selector engine may not support all forms */ }
    }

    // 2) Any email that appears in document.body.innerText but NOT inside the
    //    candidate root — that's by definition page chrome. This catches the
    //    case where Naukri renders the logged-in email in a non-standard
    //    container we haven't enumerated above.
    try {
      const candidateRoot = getCandidateRootSafe();
      const rootText = candidateRoot ? (candidateRoot.innerText || '').toLowerCase() : '';
      const bodyText = document.body ? (document.body.innerText || '') : '';
      const allEmails = (bodyText.match(EMAIL_REGEX) || []);
      for (const raw of allEmails) {
        const e = raw.toLowerCase().trim();
        if (!rootText || !rootText.includes(e)) addIfEmail(e);
      }
    } catch (_) { /* DOM may be partially loaded */ }

    return chromeEmails;
  }

  // ===================== TEXT CAPTURE =====================

  /**
   * Multi-strategy text extraction for Naukri Resdex profiles.
   *
   * Strategy A: Try known Resdex content container selectors
   * Strategy B: Clone body, aggressively strip all non-profile elements
   * Strategy C: Post-process text to remove known nav/menu line patterns
   */
  function getRawPageText() {
    // --- Strategy A: Try Resdex-specific content containers ---
    const containerSelectors = [
      '[class*="profileContainer"]',
      '[class*="profile-container"]',
      '[class*="candidateDetail"]',
      '[class*="candidate-detail"]',
      '[class*="profileDetail"]',
      '[class*="profile-detail"]',
      '[class*="resumeDetail"]',
      '[class*="resume-detail"]',
      '[class*="preview-container"]',
      '[class*="previewContainer"]',
      '[class*="mainContent"]',
      '[class*="main-content"]',
      '[class*="content-area"]',
      '[class*="rightSection"]',
      '[class*="right-section"]',
      '[class*="detailSection"]',
      'main',
      '[role="main"]',
      '#root > div > div:last-child',
    ];

    let bestContainerText = '';
    let bestSelector = '';
    for (const sel of containerSelectors) {
      try {
        const el = document.querySelector(sel);
        if (el) {
          const t = el.innerText || '';
          if (t.length > bestContainerText.length) {
            bestContainerText = t;
            bestSelector = sel;
          }
        }
      } catch (_) {}
    }

    if (bestContainerText.length > 300) {
      console.log(`[VHC v${VERSION}] Strategy A: ${bestContainerText.length} chars from "${bestSelector}"`);
      return postProcessText(bestContainerText);
    }

    // --- Strategy B: Clone body and aggressively strip noise ---
    const clone = document.body.cloneNode(true);

    const noiseSelectors = [
      'nav', 'header', 'footer', 'aside', 'script', 'style', 'noscript', 'iframe', 'svg',
      '[class*="naukri-header"]', '[class*="naukri-footer"]',
      '[class*="topnav"]', '[class*="topNav"]', '[class*="top-nav"]',
      '[class*="leftNav"]', '[class*="leftSec"]', '[class*="left-nav"]', '[class*="left-panel"]',
      '[class*="navbar"]', '[class*="navBar"]',
      '[class*="headerContainer"]', '[class*="header-container"]',
      '[class*="menuContainer"]', '[class*="menu-container"]',
      '[class*="sideMenu"]', '[class*="side-menu"]',
      '[class*="globalNav"]', '[class*="global-nav"]',
      '[class*="similar-profile"]', '[class*="similarProfile"]', '[class*="similar_profile"]',
      '[class*="related-profile"]', '[class*="relatedProfile"]',
      '[id*="similar"]', '[id*="related"]',
      '[class*="chatbot"]', '[class*="cookie"]', '[class*="banner-ad"]', '[class*="ad-container"]',
      '[class*="intercom"]', '[class*="helpWidget"]',
      '[class*="saveForLater"]', '[class*="save-for-later"]',
      '[class*="folderList"]', '[class*="folder-list"]',
      '[class*="searchBar"]', '[class*="search-bar"]', '[class*="searchContainer"]',
      '[class*="filterPanel"]', '[class*="filter-panel"]',
    ];

    noiseSelectors.forEach(sel => {
      try { clone.querySelectorAll(sel).forEach(el => el.remove()); } catch (_) {}
    });

    let text = clone.innerText || '';
    console.log(`[VHC v${VERSION}] Strategy B: ${text.length} chars after aggressive DOM strip`);

    if (text.length < 200) {
      text = document.body.innerText || '';
      console.log(`[VHC v${VERSION}] Fallback to raw body: ${text.length} chars`);
    }

    return postProcessText(text);
  }

  /**
   * Light text post-processing: only remove known navigation/noise LINES.
   * Does NOT try to detect "profile start" — keeps all content intact
   * so the AI can see the full profile including the candidate's name.
   */
  function postProcessText(text) {
    if (!text || text.length < 50) return text;

    const lines = text.split('\n');

    const noisePatterns = [
      /^(Jobs & Responses|Resdex|Reports|Recent|Search)$/i,
      /^(Home|Dashboard|Inbox|Notifications|Settings|Help|Logout)$/i,
      /^(Profiles saved for later|No profiles saved|Now you can save)$/i,
      /^(Save for later|Add to folder|Send NVite|Forward|Report profile)$/i,
      /^(Sort by|Customize|Filters|Clear all|Apply)$/i,
      /^(Prev|Next|Print|Back to search)$/i,
      /^(Decode India|Download the app|naukri\.com|recruiter\.naukri)$/i,
      /^(AI matched similar profiles?)$/i,
      /^\d+\s*profiles?\s*found$/i,
      /^(Call candidate|WhatsApp)$/i,
    ];

    const cleanLines = lines.filter(line => {
      const trimmed = line.trim();
      if (!trimmed) return false;
      if (trimmed.length < 50 && noisePatterns.some(p => p.test(trimmed))) return false;
      return true;
    });

    const result = cleanLines.join('\n');
    console.log(`[VHC v${VERSION}] Post-processed: ${text.length} -> ${result.length} chars (removed ${lines.length - cleanLines.length} noise lines)`);
    return result.trim();
  }

  // ===================== DOM DIRECT EXTRACTION =====================

  /**
   * Extract candidate NAME from document.title.
   * Resdex page titles typically follow: "Candidate Name - Naukri Resdex" or similar.
   * This is the MOST reliable source for the candidate's name.
   */
  function extractNameFromTitle() {
    // v6.0.1: strip the browser-tab unread-count badge ("(4) Deepika Agarwal")
    // that Naukri prepends to document.title — it broke every title-based
    // name extraction in background tabs.
    const title = (document.title || '').replace(/^\s*\(\d+\)\s*/, '');
    console.log(`[VHC v${VERSION}] Page title: "${title}"`);

    if (!title || title.length < 3) return null;

    const separators = [' | ', ' - ', ' – ', ' — '];
    for (const sep of separators) {
      if (title.includes(sep)) {
        const parts = title.split(sep);
        for (const part of parts) {
          const cleaned = part.trim();
          if (/naukri|resdex|preview|search|recruiter/i.test(cleaned)) continue;
          if (cleaned.length >= 3 && cleaned.length <= 60 && /^[A-Za-z]/.test(cleaned) && !/\d/.test(cleaned)) {
            console.log(`[VHC v${VERSION}] DOM name (from title): "${cleaned}"`);
            return cleaned;
          }
        }
      }
    }

    const trimmedTitle = title.trim();
    if (trimmedTitle.length >= 3 && trimmedTitle.length <= 60 && /^[A-Za-z]/.test(trimmedTitle) && !/\d/.test(trimmedTitle) && !/naukri|resdex|preview|search/i.test(trimmedTitle)) {
      console.log(`[VHC v${VERSION}] DOM name (whole title): "${trimmedTitle}"`);
      return trimmedTitle;
    }

    console.log(`[VHC v${VERSION}] Could not extract name from title`);
    return null;
  }

  /**
   * Auto-click "View Contact" / "View Phone" buttons to reveal hidden numbers.
   * Waits for the number to appear, then returns the revealed contact info.
   */
  /**
   * Click the "View Contact" button, then detect the NEWLY revealed phone number
   * using a BEFORE/AFTER diff on the candidate root container.
   *
   * v4.5 key insight: snapshot phones in the candidate root BEFORE clicking,
   * then diff AFTER — only phones that NEWLY appeared are the candidate's.
   * The recruiter's phone (in the sidebar/nav) was already present before,
   * so it is always excluded from the diff — regardless of recruiterCreds.phone.
   */
  /**
   * v6.2.0 — resolve with newly-appeared phones in the candidate root.
   * MutationObserver (never throttled in hidden tabs) + absolute
   * wall-clock deadline + coarse interval backstop.
   */
  function waitForNewPhones(phonesBefore, timeoutMs) {
    return new Promise((resolve) => {
      const startedAt = Date.now();
      let settled = false;
      let observer = null;
      let backstop = null;
      const finish = (phones, via) => {
        if (settled) return;
        settled = true;
        try { if (observer) observer.disconnect(); } catch (_) {}
        if (backstop) clearInterval(backstop);
        if (phones.length > 0) {
          console.log(`[VHC v${VERSION}] ✅ New phone via ${via} after ${Date.now() - startedAt}ms: [${phones.join(', ')}]`);
        } else {
          console.log(`[VHC v${VERSION}] Timeout (${Date.now() - startedAt}ms) — no new phone appeared after click`);
        }
        resolve(phones);
      };
      const check = (via) => {
        if (settled) return;
        const fresh = diffPhoneSets(phonesBefore, snapshotPhonesInRoot());
        if (fresh.length > 0) return finish(fresh, via);
        if (Date.now() - startedAt >= timeoutMs) return finish([], via);
      };
      try {
        observer = new MutationObserver(() => check('mutation'));
        observer.observe(getCandidateRoot(), {
          subtree: true, childList: true, characterData: true,
          attributes: true, attributeFilter: ['class', 'style'],
        });
      } catch (_) {}
      backstop = setInterval(() => check('poll'), 900);
      check('immediate');
    });
  }

  /**
   * v6.2.0 — wait for a contact button / section to MOUNT (hidden tabs:
   * lazy-mounted UI may appear late even with the visibility shim).
   */
  function waitForContactUI(timeoutMs) {
    const present = () => !!(
      document.querySelector('[class*="viewContact"], [class*="view-contact"], [class*="ViewContact"]') ||
      document.querySelector('button[class*="contact" i]') ||
      document.querySelector('[class*="contactInfo"], [class*="contact-info"]') ||
      document.querySelector('i.naukri-icon-phone, i.naukri-icon-email')
    );
    return new Promise((resolve) => {
      if (present()) return resolve(true);
      const startedAt = Date.now();
      let settled = false;
      let observer = null;
      let backstop = null;
      const finish = (ok) => {
        if (settled) return;
        settled = true;
        try { if (observer) observer.disconnect(); } catch (_) {}
        if (backstop) clearInterval(backstop);
        resolve(ok);
      };
      const check = () => {
        if (settled) return;
        if (present()) return finish(true);
        if (Date.now() - startedAt >= timeoutMs) return finish(false);
      };
      try {
        observer = new MutationObserver(check);
        observer.observe(document.body || document.documentElement,
                         { subtree: true, childList: true });
      } catch (_) {}
      backstop = setInterval(check, 900);
    });
  }

  async function clickViewContactButton() {
    // ── BEFORE snapshot: record all phones currently in candidate root ──
    const phonesBeforeClick = snapshotPhonesInRoot();
    console.log(`[VHC v${VERSION}] BEFORE click phones in root: [${[...phonesBeforeClick].join(', ')}]`);

    const buttonTexts = [
      'View Contact', 'View contact', 'view contact',
      'View Phone', 'View phone', 'view phone',
      'View Number', 'View number',
      'Show Contact', 'Show Phone', 'Show Number',
      'Reveal Contact', 'Reveal Phone',
      'View mobile', 'View Mobile',
    ];

    let clicked = false;

    // Strategy 1: Exact button text match (scoped inside candidate root)
    const root = getCandidateRoot();
    for (const text of buttonTexts) {
      const buttons = root.querySelectorAll('button, a, span[role="button"], div[role="button"]');
      for (const btn of buttons) {
        const btnText = (btn.innerText || btn.textContent || '').trim();
        if (btnText === text) {
          try {
            btn.click();
            clicked = true;
            console.log(`[VHC v${VERSION}] Clicked "${btnText}" button`);
            break;
          } catch (_) {}
        }
      }
      if (clicked) break;
    }

    // Strategy 2: Class/attribute selectors (scoped to root)
    if (!clicked) {
      const selectors = [
        '[class*="viewContact"]', '[class*="view-contact"]', '[class*="ViewContact"]',
        '[class*="viewPhone"]', '[class*="view-phone"]', '[class*="ViewPhone"]',
        '[class*="revealContact"]', '[class*="reveal-contact"]',
        '[class*="showPhone"]', '[class*="show-phone"]',
        '[data-action*="contact"]', '[data-action*="phone"]',
      ];
      for (const sel of selectors) {
        try {
          const el = root.querySelector(sel);
          if (el) {
            el.click();
            clicked = true;
            console.log(`[VHC v${VERSION}] Clicked via selector: ${sel}`);
            break;
          }
        } catch (_) {}
      }
    }

    if (clicked) {
      // v6.2.0: MutationObserver-driven wait. Chrome clamps timers in
      // hidden tabs to ~1s ticks, but MutationObserver callbacks fire
      // UNTHROTTLED the instant the reveal lands in the DOM — so this
      // detects the number immediately in foreground AND background.
      // A 900ms interval remains as a backstop, and the deadline is
      // absolute wall-clock so throttling can't stretch it.
      const revealedPhones = await waitForNewPhones(phonesBeforeClick,
        document.hidden ? 9000 : 4500);
      return { clicked: true, revealedPhones };
    } else {
      // No button found — number may already be visible
      // The BEFORE snapshot IS the candidate's number (no recruiter number expected in root)
      console.log(`[VHC v${VERSION}] No "View Contact" button — checking root for existing phones`);
      return { clicked: false, revealedPhones: [...phonesBeforeClick] };
    }
  }

  function extractNaukriProfileId() {
    const urlParams = new URLSearchParams(window.location.search);
    // 1. uresid is the unique resume/profile ID per candidate (most reliable)
    const uresid = urlParams.get('uresid');
    if (uresid) return `naukri_${uresid}`;
    // 2. storageKey often has format "sid-tupleIndex" making it unique per profile
    const storageKey = urlParams.get('storageKey');
    if (storageKey) return `naukri_sk_${storageKey}`;
    // 3. Classic Naukri URL params
    const pid = urlParams.get('profile_id') || urlParams.get('profileId') || urlParams.get('id');
    if (pid) return `naukri_${pid}`;
    // 4. uniqId is another candidate-specific param in v3 URLs
    const uniqId = urlParams.get('uniqId');
    if (uniqId) return `naukri_uq_${uniqId}`;
    // 5. sid is a search SESSION id — combine with the full path for better uniqueness
    //    Do NOT use Date.now() here — it would create duplicate records on re-capture
    const sid = urlParams.get('sid');
    if (sid) {
      // Use pathname + sid as a stable fingerprint (same candidate = same URL)
      const pathHash = window.location.pathname.replace(/\//g, '_').replace(/^_/, '');
      return `naukri_sid_${sid}_${pathHash}`;
    }
    // Last resort: hash of the full URL (stable, no timestamp)
    const urlHash = btoa(window.location.href.substring(0, 100)).replace(/[^a-zA-Z0-9]/g, '').substring(0, 20);
    return `naukri_url_${urlHash}`;
  }

  // ===================== MULTI-SOURCE CONTACT EXTRACTION =====================

  const EMAIL_REGEX = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;

  /**
   * PHONE EXTRACTION v4.4 — Targeted, not whole-page.
   *
   * Root causes fixed:
   *  1. PHONE_CHUNK_REGEX was too greedy → matched profile IDs, salary ranges etc.
   *  2. Whole body.innerText scan included recruiter's nav-bar number
   *  3. recruiterCreds.phone often null (API doesn't return it) → filter bypassed
   *
   * New strategy:
   *  - scanContactSection():  read ONLY the Naukri contact info div, not full page
   *  - clickAndWaitForPhone(): click View Contact, then poll the contact section
   *    for a real number to appear — avoids whole-page before/after diff entirely
   *  - extractPhonesFromText(): stricter regex, only matches clean 10-digit groups
   *  - Recruiter phone blocklist: built from BOTH stored phone AND email-derived
   *    heuristics so it works even when API doesn't return the phone field
   */

  /** Strip non-digits, take last 10 */
  function cleanPhone(p) {
    return (p || '').replace(/\D/g, '').slice(-10);
  }

  /** True if cleaned string is a valid Indian mobile (starts 6-9, exactly 10 digits) */
  function isValidIndianMobile(c) {
    return c.length === 10 && /^[6-9]\d{9}$/.test(c);
  }

  /**
   * Extract valid Indian mobile numbers from a SHORT, targeted text snippet.
   * Covers all common separator patterns seen on Naukri.
   * Do NOT use this on full body.innerText (guard enforced via length check).
   */
  function extractPhonesFromText(text) {
    const found = new Set();
    if (!text) return found;

    // For longer text (contact section can be 200-500 chars), we allow up to 1000
    const t = text.substring(0, 1000);

    // Pattern: strip all non-digits between the digit groups, validate result
    // We match: optional +91/00 91 prefix, then groups of digits+separators
    // totalling 10 digits, starting with 6-9
    const SEP = '[\\s\\-\\.]?'; // single optional separator
    const MSEP = '[\\s\\-\\.]*'; // zero or more separators

    const patterns = [
      // Plain 10 digits (no separators)
      /(?:(?:\+|00)91\s*)?([6-9]\d{9})/g,
      // +91 prefix with separator then 10 digits
      /(?:\+91|0091)[\s\-\.]([6-9]\d{9})/g,
      // 5+5 split: 98765 43210
      /([6-9]\d{4})[\s\-\.](\d{5})/g,
      // 4+6 split: 9876-543210
      /([6-9]\d{3})[\s\-\.](\d{6})/g,
      // 4+3+3 split: 9876-543-210
      /([6-9]\d{3})[\s\-\.](\d{3})[\s\-\.](\d{3})/g,
      // 3+3+4 split: 987-654-3210
      /([6-9]\d{2})[\s\-\.](\d{3})[\s\-\.](\d{4})/g,
      // 4+2+4 split: 9876 54 3210 (common on Naukri Resdex)
      /([6-9]\d{3})[\s\-\.](\d{2})[\s\-\.](\d{4})/g,
      // 4+4+2 split: 9876 5432 10
      /([6-9]\d{3})[\s\-\.](\d{4})[\s\-\.](\d{2})/g,
      // 5+3+2 split
      /([6-9]\d{4})[\s\-\.](\d{3})[\s\-\.](\d{2})/g,
      // 5+2+3 split
      /([6-9]\d{4})[\s\-\.](\d{2})[\s\-\.](\d{3})/g,
      // 2+4+4 split: 98-7654-3210
      /([6-9]\d)[\s\-\.](\d{4})[\s\-\.](\d{4})/g,
      // Dot-separated: 9876.543.210
      /([6-9]\d{3})\.(\d{3})\.(\d{3})/g,
      /([6-9]\d{4})\.(\d{3})\.(\d{2})/g,
    ];

    for (const re of patterns) {
      let m;
      re.lastIndex = 0;
      while ((m = re.exec(t)) !== null) {
        // Collect all capture groups and join digits
        const digits = m.slice(1).join('').replace(/\D/g, '');
        const c = digits.slice(-10);
        if (isValidIndianMobile(c)) found.add(c);
        // Also try full match in case groups aren't captured cleanly
        const fullClean = cleanPhone(m[0]);
        if (isValidIndianMobile(fullClean)) found.add(fullClean);
      }
    }

    return found;
  }

  /**
   * Naukri contact section selectors — ordered by reliability.
   * We read from THESE elements only, not full body text.
   */
  // ─────────────────────────────────────────────────────────────────────────
  // PHONE EXTRACTION v4.5 — Diff-based on contact section, scoped to candidate
  // ─────────────────────────────────────────────────────────────────────────
  //
  // THE DEFINITIVE APPROACH:
  //
  // Problem with every previous approach:
  //   - Whole-page before/after diff: picks up recruiter nav number
  //   - Contact section scan: class*=contactInfo matches recruiter sidebar too
  //   - Recruiter phone filter: only works if API returns phone (often null)
  //
  // Solution (v4.5):
  //   1. Find the candidate profile ROOT container (not whole page)
  //   2. SNAPSHOT all digit-strings in that container BEFORE click
  //   3. Click "View Contact"
  //   4. SNAPSHOT again AFTER
  //   5. DIFF → only NEW digit-strings that appeared = candidate phone
  //
  // This is safe because:
  //   - The recruiter phone was ALREADY in the container before the click
  //   - After click, only the candidate number is NEW
  //   - We never need to know the recruiter phone at all
  //   - Works even when recruiterCreds.phone is null
  //
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Candidate profile root container selectors — ordered by specificity.
   * These wrap ONLY the candidate's profile, not the recruiter header/nav.
   */
  const CANDIDATE_ROOT_SELECTORS = [
    '#rdxRoot .pages',
    '#rdxRoot [class*="tupleDetail"]',
    '#rdxRoot [class*="candidateDetail"]',
    '#rdxRoot [class*="profilePage"]',
    '#rdxRoot [class*="resumeDetail"]',
    '#rdxRoot [class*="cvDetail"]',
    '#rdxRoot',
    // Absolute fallback: main content area
    'main',
    '[role="main"]',
  ];

  /** Get the tightest candidate profile container available */
  function getCandidateRoot() {
    for (const sel of CANDIDATE_ROOT_SELECTORS) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return document.body; // last resort
  }

  /**
   * Snapshot all valid Indian mobile numbers visible inside the candidate root.
   * Reads text of ALL descendant elements but only from inside the candidate container.
   * Returns a Set<string> of 10-digit numbers.
   */
  function snapshotPhonesInRoot() {
    const root = getCandidateRoot();
    const text = root.innerText || root.textContent || '';
    return extractPhonesFromText(text.substring(0, 8000));
  }

  /**
   * DIFF two phone Sets — returns numbers that appeared in `after` but not `before`.
   */
  function diffPhoneSets(before, after) {
    return [...after].filter(p => !before.has(p));
  }

    function isNaukriSystemEmail(e) {
    const lower = (e || '').toLowerCase();
    return lower.includes('@naukri.com') || lower.includes('support@') ||
           lower.includes('noreply@') || lower.includes('@example.') ||
           lower.includes('info@naukri') || lower.includes('recruiter@naukri') ||
           lower.endsWith('@vhc.in');
  }

  /**
   * v4.4: Snapshot EMAILS only from page body text.
   * Phone extraction is done via scanContactSectionForPhones() — reads ONLY
   * the Naukri contact info div, not full body text. This prevents recruiter
   * nav-bar numbers, profile IDs, and salary ranges from leaking in.
   */
  function snapshotPageEmails() {
    const text = document.body.innerText || '';
    const emails = new Set();
    (text.match(EMAIL_REGEX) || []).forEach(e => {
      const lower = e.toLowerCase().trim();
      if (!isNaukriSystemEmail(lower)) emails.add(lower);
    });
    document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
      const e = a.getAttribute('href').replace('mailto:', '').split('?')[0].trim().toLowerCase();
      if (e && !isNaukriSystemEmail(e)) emails.add(e);
    });
    return emails;
  }

  // Compatibility shim — phones always empty, email diff still works
  function snapshotPageContacts() {
    return { emails: snapshotPageEmails(), phones: new Set() };
  }

  /**
   * Diff two email snapshots. Returns NEW emails that appeared after View Contact.
   */
  function diffContacts(before, after) {
    const newEmails = [...after.emails].filter(e => !before.emails.has(e));
    return { emails: newEmails, phones: [] }; // phone diff retired in v4.4
  }

  /**
   * Scan the CV preview iframe for email, phone, and FULL structured content.
   * The CV only contains candidate data — no recruiter contamination.
   * Deep scan extracts: email, phone, skills, education, experience sections.
   *
   * v5.1.1: Three strategies:
   *   1. Direct DOM access (same-origin iframes)
   *   2. Background relay (cross-origin iframes via all_frames: true)
   *   3. Background fetch of iframe src URL (ultimate fallback)
   */
  /**
   * v6.2.1 — how long we're willing to wait for the CV to load, scaled
   * by the real network. Slow connections get up to 30s; fast ones exit
   * the moment data arrives (the loop below returns early).
   */
  function cvWaitBudget() {
    let base = document.hidden ? 15000 : 10000;
    try {
      const conn = navigator.connection;
      if (conn && (conn.saveData ||
                   /(^|-)2g$|^3g$/.test(conn.effectiveType || '') ||
                   (typeof conn.downlink === 'number' && conn.downlink > 0 && conn.downlink < 1.5))) {
        console.log(`[VHC v${VERSION}] Slow network detected (${conn.effectiveType}, ${conn.downlink}Mbps) — doubling CV wait budget`);
        base *= 2;
      }
    } catch (_) {}
    return Math.min(base, 30000);
  }

  /**
   * v6.2.1 — EVENT-DRIVEN CV ACQUISITION. Fixes the slow-internet race
   * where the pipeline completed before the CV iframe (which carries the
   * contact info) had loaded. Strategy: quick scan first; if the result
   * is thin, keep nudging every frame to re-extract and keep re-scanning
   * until the CV is substantial / has contacts, or the budget ends.
   * Returns the BEST result seen. Fast connections are unaffected — the
   * first scan already satisfies the exit condition.
   */
  async function acquireCVData(candidateName, budgetMs) {
    const startedAt = Date.now();
    const goodEnough = (d) => !!d && (
      !!d.phone ||
      (!!d.email && (d.text || '').length >= 300) ||
      (d.text || '').length >= 1200
    );
    const better = (a, b) => {  // is a better than b?
      const ac = (a.phone ? 2 : 0) + (a.email ? 1 : 0);
      const bc = (b.phone ? 2 : 0) + (b.email ? 1 : 0);
      if (ac !== bc) return ac > bc;
      return (a.text || '').length > (b.text || '').length;
    };

    let best = await scanCVIframe(candidateName);
    if (goodEnough(best)) return best;

    console.log(`[VHC v${VERSION}] CV thin after first scan (${(best.text || '').length} chars) — waiting up to ${budgetMs}ms for it to load`);
    let lastNudge = 0;
    while (Date.now() - startedAt < budgetMs) {
      const elapsed = Date.now() - startedAt;
      updateProgress(50, `Waiting for CV to load… ${Math.round(elapsed / 1000)}s`);

      if (Date.now() - lastNudge >= 3000) {
        lastNudge = Date.now();
        // background relays to every frame's content script…
        try {
          chrome.runtime.sendMessage({ action: 'broadcastCVExtraction' }, () => {
            void chrome.runtime.lastError;
          });
        } catch (_) {}
        // …and the direct postMessage path (now has a listener) as belt+braces
        try {
          document.querySelectorAll('iframe').forEach((f) => {
            try { f.contentWindow?.postMessage({ action: 'vhc_extract_cv' }, '*'); } catch (_) {}
          });
        } catch (_) {}
      }

      await sleep(1200);
      const again = await scanCVIframe(candidateName);
      if (better(again, best)) {
        best = again;
        console.log(`[VHC v${VERSION}] CV improved: ${(best.text || '').length} chars, phone=${best.phone || 'none'}, email=${best.email || 'none'}`);
      }
      if (goodEnough(best)) break;
    }
    console.log(`[VHC v${VERSION}] CV acquisition done in ${Date.now() - startedAt}ms: ${(best.text || '').length} chars, phone=${best.phone || 'none'}`);
    return best;
  }

  // ── v6.3.0 PDF CV support ──────────────────────────────────────────
  const _pdfTextCache = {};   // url → extracted text (per page load)

  function findCvPdfSource() {
    // explicit pdf embeds first
    const embedish = document.querySelector(
      'iframe[src*=".pdf"], embed[src*=".pdf"], object[data*=".pdf"], embed[type="application/pdf"], object[type="application/pdf"]');
    if (embedish) {
      const u = embedish.src || embedish.getAttribute('data') || null;
      if (u && u.startsWith('http')) return u;
    }
    // the download-CV link (authoritative source of the actual file)
    const dl = extractNaukriCVUrl();
    if (dl) return dl;
    // any preview-ish iframe — background will sniff the content-type
    const f = document.querySelector(
      'iframe#cv-iframe, iframe[name="cv-iframe"], iframe[src*="cv"], iframe[src*="resume"], iframe[src*="preview"], iframe[src*="filepreview"]');
    if (f && f.src && f.src.startsWith('http')) return f.src;
    return null;
  }

  async function ensurePdfJs() {
    if (window.pdfjsLib) return true;
    const ok = await new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ action: 'injectPdfJs' }, (r) => {
          if (chrome.runtime.lastError) return resolve(false);
          resolve(!!(r && r.ok));
        });
      } catch (_) { resolve(false); }
    });
    if (!ok) return false;
    // pdf.js registers synchronously on injection; tiny settle for safety
    await sleep(150);
    return !!window.pdfjsLib;
  }

  async function extractPdfTextFromBase64(b64) {
    if (!(await ensurePdfJs())) return '';
    try {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      // No workerSrc configured → pdf.js falls back to its main-thread
      // "fake worker" automatically. Fine for 1–5 page CVs.
      const doc = await window.pdfjsLib.getDocument({
        data: bytes, isEvalSupported: false, disableFontFace: true, useSystemFonts: true,
      }).promise;
      const pages = Math.min(doc.numPages, 8);
      let out = '';
      for (let p = 1; p <= pages; p++) {
        const page = await doc.getPage(p);
        const tc = await page.getTextContent();
        let last = null;
        for (const item of tc.items) {
          if (last && item.transform && last.transform &&
              Math.abs(item.transform[5] - last.transform[5]) > 2) out += '\n';
          else if (out && !out.endsWith('\n')) out += ' ';
          out += item.str;
          last = item;
        }
        out += '\n';
      }
      try { doc.destroy(); } catch (_) {}
      return out.trim();
    } catch (e) {
      console.warn(`[VHC v${VERSION}] PDF parse failed: ${e.message}`);
      return '';
    }
  }

  async function tryPdfCvStrategy() {
    const url = findCvPdfSource();
    if (!url) return null;
    if (_pdfTextCache[url] !== undefined) return _pdfTextCache[url] || null;
    const resp = await new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ action: 'fetchCvBinary', url }, (r) => {
          if (chrome.runtime.lastError) return resolve(null);
          resolve(r);
        });
      } catch (_) { resolve(null); }
    });
    if (!resp) return null;
    if (resp.isPdf && resp.base64) {
      console.log(`[VHC v${VERSION}] Strategy 4: PDF CV detected (${resp.bytes} bytes) — extracting text via pdf.js`);
      const text = await extractPdfTextFromBase64(resp.base64);
      _pdfTextCache[url] = text || '';
      if (text && text.length > 50) {
        console.log(`[VHC v${VERSION}] Strategy 4 SUCCESS: pdf.js extracted ${text.length} chars`);
        return text;
      }
      return null;
    }
    if (resp.isDoc) {
      console.log(`[VHC v${VERSION}] Strategy 4: CV is Word (${resp.contentType}) — leaving to page/iframe strategies`);
      _pdfTextCache[url] = '';
      return null;
    }
    if (resp.text && resp.text.length > 200) {
      _pdfTextCache[url] = resp.text;
      console.log(`[VHC v${VERSION}] Strategy 4: HTML CV via background fetch, ${resp.text.length} chars`);
      return resp.text;
    }
    return null;
  }

  async function scanCVIframe(candidateName) {
    const result = { email: null, phone: null, text: '', isValid: false, sections: {} };

    // ═══ STRATEGY 1: Direct DOM access (original approach, works for same-origin) ═══
    try {
      const iframeEl = document.querySelector('iframe#cv-iframe') ||
                       document.querySelector('iframe[name="cv-iframe"]') ||
                       document.querySelector('#cv-iframe iframe') ||
                       document.querySelector('.iframe-cv-iframe iframe') ||
                       document.querySelector('iframe[src*="cv/view"]') ||
                       document.querySelector('iframe[src*="resume"]') ||
                       document.querySelector('iframe[src*="preview"]');

      if (iframeEl) {
        let iframeDoc;
        try {
          iframeDoc = iframeEl.contentDocument || iframeEl.contentWindow?.document;
        } catch (e) {
          console.warn(`[VHC v${VERSION}] Strategy 1: Cannot access CV iframe (cross-origin): ${e.message}`);
        }

        if (iframeDoc && iframeDoc.body) {
          const cvText = iframeDoc.body.innerText || iframeDoc.body.textContent || '';
          if (cvText.length > 50) {
            result.text = cvText.substring(0, 15000);
            result.isValid = true;
            console.log(`[VHC v${VERSION}] Strategy 1 SUCCESS: Direct DOM access, ${cvText.length} chars`);
          }
        }
      } else {
        console.log(`[VHC v${VERSION}] Strategy 1: No CV iframe element found in DOM`);
      }
    } catch (err) {
      console.warn(`[VHC v${VERSION}] Strategy 1 error:`, err.message);
    }

    // ═══ STRATEGY 2: Get CV data from background (relayed by iframe content script via all_frames) ═══
    if (!result.isValid || result.text.length < 50) {
      try {
        // First, try to trigger extraction from any iframe content scripts
        try {
          const allFrames = document.querySelectorAll('iframe');
          for (const frame of allFrames) {
            try {
              frame.contentWindow?.postMessage({ action: 'vhc_extract_cv' }, '*');
            } catch (e) { /* cross-origin, expected */ }
          }
        } catch (e) {}

        // Wait a moment for iframe scripts to relay data, then ask background.
        // Background tabs suffer from severe throttling, so we need a retry loop with longer wait intervals.
        const isBackground = document.hidden;
        const maxAttempts = isBackground ? 3 : 1;
        const initialDelay = isBackground ? 1500 : 800;
        const retryDelay = 1500;
        
        await new Promise(r => setTimeout(r, initialDelay));

        let bgData = null;
        for (let attempt = 0; attempt < maxAttempts; attempt++) {
          if (attempt > 0) {
            console.log(`[VHC v${VERSION}] Strategy 2: Retrying CV iframe data retrieval, attempt ${attempt + 1}/${maxAttempts}...`);
            await new Promise(r => setTimeout(r, retryDelay));
          }

          bgData = await new Promise((resolve) => {
            if (!chrome?.runtime?.id) return resolve(null);
            chrome.runtime.sendMessage({ action: 'getCvIframeData' }, (response) => {
              if (chrome.runtime.lastError) return resolve(null);
              resolve(response);
            });
          });

          if (bgData?.data?.text && bgData.data.text.length > 50) {
            break; // Found it!
          }
        }

        if (bgData?.data?.text && bgData.data.text.length > 50) {
          result.text = bgData.data.text.substring(0, 15000);
          result.isValid = true;

          // Use pre-extracted emails/phones from iframe script
          if (bgData.data.emails?.length > 0) {
            for (const e of bgData.data.emails) {
              if (!isNaukriSystemEmail(e)) {
                result.email = e;
                break;
              }
            }
          }
          if (bgData.data.phones?.length > 0) {
            result.phone = bgData.data.phones[0];
          }
          if (bgData.data.sections) {
            result.sections = bgData.data.sections;
          }
          if (bgData.data.linkedin) {
            result.sections.linkedin = bgData.data.linkedin;
          }

          console.log(`[VHC v${VERSION}] Strategy 2 SUCCESS: Background relay, ${result.text.length} chars, email=${result.email || 'none'}, phone=${result.phone || 'none'}`);
        } else {
          console.log(`[VHC v${VERSION}] Strategy 2: No CV data from background relay`);
        }
      } catch (err) {
        console.warn(`[VHC v${VERSION}] Strategy 2 error:`, err.message);
      }
    }

    // ═══ STRATEGY 3: Fetch iframe src via background service worker (ultimate fallback) ═══
    if (!result.isValid || result.text.length < 50) {
      try {
        // Find any iframe that looks like a CV
        const iframes = document.querySelectorAll('iframe');
        let cvIframeSrc = null;

        for (const iframe of iframes) {
          const src = iframe.src || iframe.getAttribute('data-src') || '';
          if (src && (
            /cv|resume|preview|document|attachment|viewer/i.test(src) ||
            /naukri\.com/i.test(src) // Any naukri iframe is worth trying
          )) {
            cvIframeSrc = src;
            console.log(`[VHC v${VERSION}] Strategy 3: Found iframe src: ${src.substring(0, 100)}`);
            break;
          }
        }

        // Also check for iframes without explicit CV-related src (Naukri sometimes uses generic paths)
        if (!cvIframeSrc) {
          for (const iframe of iframes) {
            const src = iframe.src || '';
            if (src && src.startsWith('http') && !src.includes('google') && !src.includes('facebook') && !src.includes('ad')) {
              cvIframeSrc = src;
              console.log(`[VHC v${VERSION}] Strategy 3: Trying generic iframe src: ${src.substring(0, 100)}`);
              break;
            }
          }
        }

        if (cvIframeSrc && chrome?.runtime?.id) {
          const fetchResult = await new Promise((resolve) => {
            chrome.runtime.sendMessage({ action: 'fetchIframeSrc', url: cvIframeSrc }, (response) => {
              if (chrome.runtime.lastError) return resolve(null);
              resolve(response);
            });
          });

          if (fetchResult?.text && fetchResult.text.length > 50) {
            result.text = fetchResult.text.substring(0, 15000);
            result.isValid = true;
            console.log(`[VHC v${VERSION}] Strategy 3 SUCCESS: Background fetch, ${result.text.length} chars`);
          } else {
            console.log(`[VHC v${VERSION}] Strategy 3: Fetch returned insufficient text`);
          }
        } else {
          console.log(`[VHC v${VERSION}] Strategy 3: No suitable iframe src found`);
        }
      } catch (err) {
        console.warn(`[VHC v${VERSION}] Strategy 3 error:`, err.message);
      }
    }

    // ═══ STRATEGY 4 (v6.3.0): PDF CV → pdf.js text extraction ═══
    if (!result.isValid || result.text.length < 50) {
      try {
        const pdfText = await tryPdfCvStrategy();
        if (pdfText && pdfText.length > 50) {
          result.text = pdfText.substring(0, 15000);
          result.isValid = true;
        }
      } catch (err) {
        console.warn(`[VHC v${VERSION}] Strategy 4 error:`, err.message);
      }
    }

    // ═══ POST-PROCESSING: Extract contacts and sections from CV text ═══
    if (result.isValid && result.text.length > 50) {
      const cvText = result.text;

      // Sanity check: does CV contain the candidate's name?
      if (candidateName) {
        const nameParts = candidateName.split(/\s+/).filter(w => w.length > 2);
        const nameFound = nameParts.some(part =>
          cvText.toLowerCase().includes(part.toLowerCase())
        );
        if (!nameFound) {
          console.warn(`[VHC v${VERSION}] CV does NOT contain candidate name "${candidateName}". May be a bad upload.`);
          // Still use text but mark contacts as unreliable
          result.isValid = true; // Keep text for AI extraction
        } else {
          console.log(`[VHC v${VERSION}] CV sanity check PASSED: contains name "${candidateName}"`);
        }
      }

      // Extract emails from CV text (if not already found by strategy 2)
      if (!result.email) {
        const cvEmails = cvText.match(EMAIL_REGEX) || [];
        for (const e of cvEmails) {
          const lower = e.toLowerCase().trim();
          if (!isNaukriSystemEmail(lower)) {
            result.email = lower;
            console.log(`[VHC v${VERSION}] CV email: ${lower}`);
            break;
          }
        }
      }

      // Extract phones from CV text (if not already found by strategy 2)
      if (!result.phone) {
        const cvPhoneSet = extractPhonesFromText(cvText);
        const cvPhonesArray = [...cvPhoneSet];
        if (cvPhonesArray.length > 0) {
          result.phone = cvPhonesArray[0];
          console.log(`[VHC v${VERSION}] CV phone: ${result.phone} (found ${cvPhonesArray.length} total)`);
        }
      }

      // Parse sections if not already done by strategy 2
      if (!result.sections || Object.keys(result.sections).length <= 1) {
        const lines = cvText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
        const sectionHeaders = {
          objective: /^(career\s*objective|objective|summary|profile\s*summary|professional\s*summary|about\s*me)/i,
          experience: /^(work\s*experience|experience|employment|professional\s*experience|work\s*history)/i,
          education: /^(education|academic|qualification|educational\s*qualification)/i,
          skills: /^(skills|technical\s*skills|key\s*skills|core\s*competencies|competencies|it\s*skills)/i,
          certifications: /^(certifications?|certificates?|courses?|training)/i,
          projects: /^(projects?|key\s*projects?|notable\s*projects?)/i,
          languages: /^(languages?|language\s*known|languages\s*known)/i,
          personal: /^(personal\s*details|personal\s*information|personal\s*data|personal)/i,
          achievements: /^(achievements?|awards?|accomplishments?|honors?)/i,
        };
        let currentSection = 'header';
        const sections = { header: [] };
        for (const line of lines) {
          let matched = false;
          for (const [key, pattern] of Object.entries(sectionHeaders)) {
            if (pattern.test(line) && line.length < 60) {
              currentSection = key;
              if (!sections[currentSection]) sections[currentSection] = [];
              matched = true;
              break;
            }
          }
          if (!matched) {
            if (!sections[currentSection]) sections[currentSection] = [];
            sections[currentSection].push(line);
          }
        }
        result.sections = sections;
      }

      // Extract LinkedIn URL from CV text
      if (!result.sections.linkedin) {
        const linkedinMatch = cvText.match(/(?:https?:\/\/)?(?:www\.)?linkedin\.com\/in\/[a-zA-Z0-9_-]+/i);
        if (linkedinMatch) {
          result.sections.linkedin = linkedinMatch[0];
          console.log(`[VHC v${VERSION}] CV LinkedIn: ${linkedinMatch[0]}`);
        }
      }

      // Log summary
      const foundSections = Object.keys(result.sections).filter(k =>
        Array.isArray(result.sections[k]) ? result.sections[k].length > 0 : result.sections[k]
      );
      console.log(`[VHC v${VERSION}] CV scan complete: ${result.text.length} chars, sections=[${foundSections.join(', ')}], email=${result.email || 'none'}, phone=${result.phone || 'none'}`);
    }

    return result;
  }

  /**
   * Extract contacts using Naukri's DOM selectors as a fallback.
   * FIX v4.3: now extracts PHONE as well as email.
   */
  function extractFromDOMSelectors(recruiterCreds = {}) {
    const contacts = { email: null, phone: null };
    const rEmail = recruiterCreds.email || null;
    const rPhone = cleanPhone(recruiterCreds.phone || '');

    function isRecruiterOrSystem(e) {
      if (!e) return true;
      if (isNaukriSystemEmail(e)) return true;
      if (rEmail && e.toLowerCase().trim() === rEmail.toLowerCase().trim()) return true;
      return false;
    }

    function isRecruiterPhone(p) {
      if (!p) return false;
      return rPhone && cleanPhone(p) === rPhone;
    }

    // ── EMAIL via naukri icon ──
    const emailIcon = document.querySelector('#rdxRoot i.naukri-icon-email') ||
                      document.querySelector('i.naukri-icon-email') ||
                      document.querySelector('i[title="Email"]');
    if (emailIcon) {
      const parent = emailIcon.closest('[title]') || emailIcon.parentElement;
      if (parent) {
        const titleVal = (parent.getAttribute('title') || '').trim().toLowerCase();
        if (titleVal.includes('@') && !isRecruiterOrSystem(titleVal)) {
          contacts.email = titleVal;
          console.log(`[VHC v${VERSION}] DOM selector email: ${contacts.email}`);
        }
        if (!contacts.email) {
          const span = parent.querySelector('span.hlite-inherit') || parent.querySelector('span');
          if (span) {
            const spanText = (span.textContent || '').trim().toLowerCase();
            if (spanText.includes('@') && !isRecruiterOrSystem(spanText)) {
              contacts.email = spanText;
              console.log(`[VHC v${VERSION}] DOM selector email (span): ${contacts.email}`);
            }
          }
        }
      }
    }

    // ── EMAIL via title attribute containing @ ──
    if (!contacts.email) {
      const profileRoot = document.querySelector('#rdxRoot .pages') || document.querySelector('#rdxRoot');
      if (profileRoot) {
        const titledEls = profileRoot.querySelectorAll('[title*="@"]');
        for (const el of titledEls) {
          const t = el.getAttribute('title').trim().toLowerCase();
          if (/^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(t) && !isRecruiterOrSystem(t)) {
            contacts.email = t;
            console.log(`[VHC v${VERSION}] DOM selector email (rdxRoot title): ${contacts.email}`);
            break;
          }
        }
      }
    }

    // ── FIX v4.3: PHONE via naukri phone icon ──
    const phoneIconSelectors = [
      '#rdxRoot i.naukri-icon-phone',
      'i.naukri-icon-phone',
      '#rdxRoot i.naukri-icon-mobile',
      'i.naukri-icon-mobile',
      'i[title="Mobile"]',
      'i[title="Phone"]',
      '[class*="phoneIcon"]',
      '[class*="phone-icon"]',
    ];
    for (const sel of phoneIconSelectors) {
      const icon = document.querySelector(sel);
      if (!icon) continue;
      const parent = icon.closest('[title]') || icon.parentElement;
      if (parent) {
        const titleVal = parent.getAttribute('title') || '';
        const cleaned = cleanPhone(titleVal);
        if (isValidIndianMobile(cleaned) && !isRecruiterPhone(cleaned)) {
          contacts.phone = cleaned;
          console.log(`[VHC v${VERSION}] DOM selector phone (icon title): ${cleaned}`);
          break;
        }
        // Also check text content of parent
        const txt = (parent.textContent || '').trim();
        const phonesInParent = extractPhonesFromText(txt);
        for (const p of phonesInParent) {
          if (!isRecruiterPhone(p)) {
            contacts.phone = p;
            console.log(`[VHC v${VERSION}] DOM selector phone (icon text): ${p}`);
            break;
          }
        }
        if (contacts.phone) break;
      }
    }

    // ── FIX v4.3: PHONE via tel: links ──
    if (!contacts.phone) {
      document.querySelectorAll('a[href^="tel:"]').forEach(a => {
        if (contacts.phone) return;
        const c = cleanPhone(a.getAttribute('href').replace('tel:', ''));
        if (isValidIndianMobile(c) && !isRecruiterPhone(c)) {
          contacts.phone = c;
          console.log(`[VHC v${VERSION}] DOM selector phone (tel: link): ${c}`);
        }
      });
    }

    // ── FIX v4.3: PHONE via data-phone / data-mobile attributes ──
    if (!contacts.phone) {
      const dataPhoneEl = document.querySelector('[data-phone],[data-mobile],[data-contact-number]');
      if (dataPhoneEl) {
        const raw = dataPhoneEl.getAttribute('data-phone') ||
                    dataPhoneEl.getAttribute('data-mobile') ||
                    dataPhoneEl.getAttribute('data-contact-number') || '';
        const c = cleanPhone(raw);
        if (isValidIndianMobile(c) && !isRecruiterPhone(c)) {
          contacts.phone = c;
          console.log(`[VHC v${VERSION}] DOM selector phone (data attr): ${c}`);
        }
      }
    }

    // ── FIX v4.3: PHONE via known Naukri contact section selectors ──
    if (!contacts.phone) {
      const contactSectionSelectors = [
        '[class*="contactInfo"] [class*="phone"]',
        '[class*="contact-info"] [class*="phone"]',
        '[class*="candidateContact"] [class*="phone"]',
        '[class*="phoneNumber"]',
        '[class*="phone-number"]',
        '[class*="mobileNumber"]',
        '[class*="mobile-number"]',
        '.rdx-phone', '.rdx-mobile',
        '[class*="contactPhone"]',
      ];
      for (const sel of contactSectionSelectors) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const txt = (el.textContent || el.getAttribute('title') || '').trim();
        const phones = extractPhonesFromText(txt);
        for (const p of phones) {
          if (!isRecruiterPhone(p)) {
            contacts.phone = p;
            console.log(`[VHC v${VERSION}] DOM selector phone (contact section ${sel}): ${p}`);
            break;
          }
        }
        if (contacts.phone) break;
      }
    }

    return contacts;
  }

  /**
   * MERGE contacts from all sources.
   * v5.4.1 trust hierarchy:
   *   EMAIL: CV iframe > Email diff (after View Contact) > BEFORE snapshot > DOM
   *   PHONE: CV iframe > Revealed phones (from contact section) > DOM selectors
   *
   * Phone NEVER falls back to BEFORE snapshot — that contains recruiter's number.
   * Phone sources are now guaranteed to come from the contact section only.
   * 
   * v5.4.1 FIX: Added final safety check to ensure we NEVER return recruiter contacts.
   */
  function mergeContacts(cvData, diffData, domData, recruiterCreds, beforeSnapshot) {
    const rEmail = (recruiterCreds.email || '').toLowerCase().trim();
    const rPhone = cleanPhone(recruiterCreds.phone || '');
    // v6.0.2 FIX: page-chrome / Naukri-session-login email blocklist
    const chromeBlock = recruiterCreds.chromeEmails instanceof Set
      ? recruiterCreds.chromeEmails
      : new Set();

    function isRecruiterEmail(e) {
      if (!e) return false;
      const lower = e.toLowerCase().trim();
      if (rEmail && lower === rEmail) return true;
      if (chromeBlock.has(lower)) return true;  // Naukri-session login leak guard
      return false;
    }

    function isRecruiterPhone(p) {
      if (!p || !rPhone) return false;
      return cleanPhone(p) === rPhone;
    }

    function isBadEmail(e) {
      return !e || isNaukriSystemEmail(e) || isRecruiterEmail(e);
    }

    // ── EMAIL: CV > Diff > BEFORE snapshot > DOM ──
    let finalEmail = null;
    let emailSource = 'none';

    if (cvData.isValid && cvData.email && !isBadEmail(cvData.email)) {
      finalEmail = cvData.email;
      emailSource = 'CV iframe';
    } else if (diffData.emails.length > 0) {
      for (const e of diffData.emails) {
        if (!isBadEmail(e)) { finalEmail = e; emailSource = 'After View Contact'; break; }
      }
    }
    if (!finalEmail && beforeSnapshot?.emails) {
      // v6.0.2 FIX: BEFORE-snapshot fallback ONLY trusts emails that also
      // appear inside the candidate profile root. Emails that exist on the
      // page but NOT in the candidate root are page chrome (Naukri header /
      // recruiter dropdown) and must never become the candidate's email.
      let rootTextLower = '';
      try {
        const root = getCandidateRootSafe();
        rootTextLower = root ? (root.innerText || '').toLowerCase() : '';
      } catch (_) {}
      for (const e of beforeSnapshot.emails) {
        if (isBadEmail(e)) continue;
        if (rootTextLower && !rootTextLower.includes(e.toLowerCase())) {
          console.warn(`[VHC v${VERSION}] 🚫 BEFORE-snapshot email "${e}" not in candidate root — treating as page chrome`);
          continue;
        }
        finalEmail = e;
        emailSource = 'Already-visible';
        break;
      }
    }
    if (!finalEmail && domData.email && !isBadEmail(domData.email)) {
      finalEmail = domData.email;
      emailSource = 'DOM selectors';
    }

    // ── PHONE: CV > Revealed (contact section) > DOM ──
    // NEVER uses BEFORE snapshot — too risky (contains recruiter's number).
    // diffData.phones now contains only phones from scanContactSectionForPhones()
    // which reads the contact div only — so recruiter nav number never appears here.
    let finalPhone = null;
    let phoneSource = 'none';

    if (cvData.isValid && cvData.phone && !isRecruiterPhone(cvData.phone)) {
      finalPhone = cvData.phone;
      phoneSource = 'CV iframe';
    } else if (diffData.phones.length > 0) {
      for (const p of diffData.phones) {
        if (!isRecruiterPhone(p)) { finalPhone = p; phoneSource = 'View Contact reveal'; break; }
      }
    }
    if (!finalPhone && domData.phone && !isRecruiterPhone(domData.phone)) {
      finalPhone = domData.phone;
      phoneSource = 'DOM selectors';
    }

    // v5.4.1 FIX: FINAL SAFETY CHECK — never return recruiter's contact info
    // This catches edge cases where filtering above might have missed
    if (finalEmail && isRecruiterEmail(finalEmail)) {
      console.error(`[VHC v${VERSION}] 🚨 SAFETY: Blocked recruiter email leak: ${finalEmail}`);
      finalEmail = null;
      emailSource = 'blocked-recruiter';
    }
    if (finalPhone && isRecruiterPhone(finalPhone)) {
      console.error(`[VHC v${VERSION}] 🚨 SAFETY: Blocked recruiter phone leak: ${finalPhone}`);
      finalPhone = null;
      phoneSource = 'blocked-recruiter';
    }

    console.log(`[VHC v${VERSION}] MERGE email: ${finalEmail || 'NONE'} [source: ${emailSource}]`);
    console.log(`[VHC v${VERSION}] MERGE phone: ${finalPhone || 'NONE'} [source: ${phoneSource}]`);
    return { email: finalEmail, phone: finalPhone };
  }

  // ===================== JOB BINDING =====================

  /**
   * Read the active job the recruiter has selected from chrome.storage.
   * Set by background.js when a VHC job page is detected.
   * Returns: { job_id, job_title, job_code } or null
   */
  async function getActiveJob() {
    if (!isExtensionValid()) return null;
    try {
      return await new Promise((resolve, reject) => {
        chrome.storage.local.get(['vhc_active_job'], (result) => {
          if (chrome.runtime.lastError) return reject(chrome.runtime.lastError);
          resolve(result.vhc_active_job || null);
        });
      });
    } catch (e) {
      console.warn(`[VHC v${VERSION}] Could not read active job:`, e);
      return null;
    }
  }

  // ===================== LINKEDIN EXTRACTION =====================

  /**
   * Extract a platform-unique profile ID for LinkedIn.
   * Uses the vanity URL slug as the identifier.
   */
  function extractLinkedInProfileId() {
    const match = window.location.pathname.match(/\/in\/([^/?#]+)/);
    if (match) return `linkedin_${match[1]}`;
    return `linkedin_url_${btoa(window.location.href.substring(0, 80)).replace(/[^a-zA-Z0-9]/g, '').substring(0, 20)}`;
  }

  /**
   * Extract full profile text from a LinkedIn profile page.
   * LinkedIn's DOM is heavily class-obfuscated so we rely on semantic sections
   * and aria-labels rather than brittle class names.
   * The AI will do the heavy lifting of parsing the raw text.
   */
  function extractLinkedInPageText() {
    let parts = [];

    // Name + headline (top card)
    const nameEl = document.querySelector('h1') ||
                   document.querySelector('[data-generated-suggestion-target]');
    if (nameEl) parts.push(`Name: ${cleanText(nameEl.innerText)}`);

    const headlineEl = document.querySelector('.text-body-medium.break-words') ||
                       document.querySelector('[data-field="headline"]');
    if (headlineEl) parts.push(`Headline: ${cleanText(headlineEl.innerText)}`);

    // Location
    const locationEl = document.querySelector('.text-body-small.inline.t-black--light.break-words');
    if (locationEl) parts.push(`Location: ${cleanText(locationEl.innerText)}`);

    // About / Summary section
    const aboutSection = document.querySelector('section[data-section="summary"]') ||
                         document.getElementById('about') ||
                         [...document.querySelectorAll('section')].find(s => s.querySelector('div[id*="about"]'));
    if (aboutSection) {
      const aboutText = cleanText(aboutSection.innerText);
      if (aboutText) parts.push(`\n=== About ===\n${aboutText}`);
    }

    // Experience section
    const expSection = document.getElementById('experience') ||
                       [...document.querySelectorAll('section')].find(s => s.querySelector('div[id*="experience"]'));
    if (expSection) {
      const expText = cleanText(expSection.innerText);
      if (expText) parts.push(`\n=== Experience ===\n${expText}`);
    }

    // Education section
    const eduSection = document.getElementById('education') ||
                       [...document.querySelectorAll('section')].find(s => s.querySelector('div[id*="education"]'));
    if (eduSection) {
      const eduText = cleanText(eduSection.innerText);
      if (eduText) parts.push(`\n=== Education ===\n${eduText}`);
    }

    // Skills section
    const skillsSection = document.getElementById('skills') ||
                          [...document.querySelectorAll('section')].find(s => s.querySelector('div[id*="skills"]'));
    if (skillsSection) {
      const skillsText = cleanText(skillsSection.innerText);
      if (skillsText) parts.push(`\n=== Skills ===\n${skillsText}`);
    }

    // Certifications
    const certsSection = document.getElementById('certifications') ||
                         document.getElementById('licenses_and_certifications');
    if (certsSection) {
      parts.push(`\n=== Certifications ===\n${cleanText(certsSection.innerText)}`);
    }

    // Contact info (only visible if user has clicked "Contact info" modal)
    const contactModal = document.querySelector('[aria-label="Contact info"], .ci-vanity-url, .pv-contact-info');
    if (contactModal) {
      parts.push(`\n=== Contact ===\n${cleanText(contactModal.innerText)}`);
    }

    // Fallback: if we got very little, grab the main content div
    const combined = parts.join('\n');
    if (combined.length < 300) {
      const main = document.querySelector('main') || document.querySelector('[role="main"]');
      if (main) return (cleanText(main.innerText) || '').substring(0, 15000);
    }

    return combined.substring(0, 15000);
  }

  /**
   * Try to find candidate's email/phone from LinkedIn contact info modal.
   * The modal is opened via "Contact info" link — we look for it if already open.
   */
  function extractLinkedInContacts() {
    const modal = document.querySelector('[data-view-name="profile-contact-info"]') ||
                  document.querySelector('.artdeco-modal__content') ||
                  document.querySelector('.pv-contact-info');
    if (!modal) return { email: null, phone: null };

    const text = modal.innerText || '';
    const emailMatch = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
    const email = emailMatch ? emailMatch[0].toLowerCase() : null;

    const phoneSet = extractPhonesFromText(text);
    const phone = phoneSet.size > 0 ? [...phoneSet][0] : null;

    return { email, phone };
  }

  /**
   * Extract name from LinkedIn page title (most reliable).
   * Typical format: "Firstname Lastname | LinkedIn" or "Firstname Lastname - LinkedIn"
   */
  function extractLinkedInName() {
    const title = document.title || '';
    const separators = [' | ', ' - ', ' – '];
    for (const sep of separators) {
      if (title.includes(sep)) {
        const name = title.split(sep)[0].trim();
        if (name.length >= 3 && name.length <= 60 && !/linkedin/i.test(name)) return name;
      }
    }
    // Try h1 directly
    const h1 = document.querySelector('h1');
    if (h1) return cleanText(h1.innerText) || null;
    return null;
  }

  /**
   * Full capture flow for LinkedIn profile pages.
   * Simpler than Naukri — no "View Contact" click needed, just text extraction + AI.
   */
  async function performLinkedInCapture() {
    const auth = await getAuthToken();
    if (!auth) return { success: false, error: 'Not logged in. Login via extension popup.' };

    showProgressBar();
    updateProgress(10, 'Waiting for LinkedIn profile to load...');
    await waitForDOMStability();

    updateProgress(25, 'Extracting LinkedIn profile...');
    const name = extractLinkedInName();
    const profileId = extractLinkedInProfileId();
    const rawText = extractLinkedInPageText();
    const contacts = extractLinkedInContacts();
    const activeJob = await getActiveJob();
    const recruiterCreds = await getRecruiterCredentials();

    if (rawText.length < 100) {
      hideProgressBar(2000);
      return { success: false, error: 'Profile not fully loaded. Try scrolling down first.' };
    }

    updateProgress(70, 'Adding to queue...');

    const payload = {
      naukri_profile_id:  profileId,      // reusing field name — means "source_profile_id"
      naukri_profile_url: window.location.href,
      page_title:         document.title,
      name:               name || null,
      email:              contacts.email || null,
      phone:              contacts.phone || null,
      raw_text:           rawText,
      recruiter_email:    recruiterCreds.email || null,
      recruiter_phone:    recruiterCreds.phone || null,
      scraped_at:         new Date().toISOString(),
      extension_version:  VERSION,
      source_platform:    'linkedin',
      active_job_id:      activeJob?.job_id || null,
      active_job_title:   activeJob?.job_title || null,
    };

    try {
      const result = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: 'enqueueCapture', data: payload }, response => {
          if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
          else resolve(response);
        });
      });

      if (result.action === 'duplicate') {
        updateProgress(100, `${name || 'Profile'} already in queue`);
        hideProgressBar(3000);
        return { success: true, action: 'duplicate', name };
      }

      updateProgress(100, `${name || 'Profile'} queued (#${result.queued} in queue)`);
      if (activeJob?.job_title) {
        setTimeout(() => showToast(`📎 Will auto-shortlist to: ${activeJob.job_title}`, 'info'), 1500);
      }
      hideProgressBar(3500);
      return { success: true, action: 'queued', name, queued: result.queued };
    } catch (e) {
      hideProgressBar(2000);
      return { success: false, error: e.message };
    }
  }

  // ===================== FOUNDIT EXTRACTION =====================

  /**
   * Extract platform-unique ID for Foundit profiles.
   * Foundit URLs: /profile/12345?... or /resume/uid=XYZ
   */
  function extractFounditProfileId() {
    const pathname = window.location.pathname;
    // /profile/123456 pattern
    const pathMatch = pathname.match(/\/(profile|resume|cv)\/([^/?#]+)/);
    if (pathMatch) return `foundit_${pathMatch[2]}`;
    // uid= param
    const uidMatch = window.location.search.match(/uid=([^&]+)/);
    if (uidMatch) return `foundit_uid_${uidMatch[1]}`;
    return `foundit_url_${btoa(window.location.href.substring(0, 80)).replace(/[^a-zA-Z0-9]/g, '').substring(0, 20)}`;
  }

  /**
   * Extract full profile text from Foundit (formerly Monster India) profile pages.
   * Foundit uses class names like .profile-name, .snapshot-details, .experience-section etc.
   */
  function extractFounditPageText() {
    let parts = [];

    // Name
    const nameEl = document.querySelector('.profile-name, [class*="profileName"], h1.name, h1');
    if (nameEl) parts.push(`Name: ${cleanText(nameEl.innerText)}`);

    // Headline / current role
    const headlineEl = document.querySelector('[class*="currentDesignation"], [class*="current-designation"], .profile-designation');
    if (headlineEl) parts.push(`Headline: ${cleanText(headlineEl.innerText)}`);

    // Location
    const locEl = document.querySelector('[class*="currentLocation"], [class*="location"], .profile-location');
    if (locEl) parts.push(`Location: ${cleanText(locEl.innerText)}`);

    // Email and phone (visible in profile)
    const emailEl = document.querySelector('[class*="email"], a[href^="mailto:"]');
    if (emailEl) parts.push(`Email: ${cleanText(emailEl.getAttribute('href')?.replace('mailto:', '') || emailEl.innerText)}`);

    const phoneEl = document.querySelector('[class*="phone"], [class*="mobile"], a[href^="tel:"]');
    if (phoneEl) parts.push(`Phone: ${cleanText(phoneEl.getAttribute('href')?.replace('tel:', '') || phoneEl.innerText)}`);

    // Snapshot / summary section
    const snapshotEl = document.querySelector('[class*="snapshotDetails"], [class*="snapshot-details"], [class*="profileSummary"], [class*="profile-summary"]');
    if (snapshotEl) parts.push(`\n=== Profile Summary ===\n${cleanText(snapshotEl.innerText)}`);

    // Experience
    const expEl = document.querySelector('[class*="experienceSection"], [class*="experience-section"], #experience');
    if (expEl) parts.push(`\n=== Experience ===\n${cleanText(expEl.innerText)}`);

    // Education
    const eduEl = document.querySelector('[class*="educationSection"], [class*="education-section"], #education');
    if (eduEl) parts.push(`\n=== Education ===\n${cleanText(eduEl.innerText)}`);

    // Skills
    const skillsEl = document.querySelector('[class*="skillsSection"], [class*="skills-section"], [class*="itSkills"], #skills');
    if (skillsEl) parts.push(`\n=== Skills ===\n${cleanText(skillsEl.innerText)}`);

    // Fallback to main content
    const combined = parts.join('\n');
    if (combined.length < 300) {
      const main = document.querySelector('main, [class*="candidateDetail"], [class*="profile-container"]');
      if (main) return (cleanText(main.innerText) || '').substring(0, 15000);
      return (document.body.innerText || '').substring(0, 15000);
    }

    return combined.substring(0, 15000);
  }

  /**
   * Try to find a CV download link on a Foundit profile page.
   * Returns the URL string if found, null otherwise.
   * Background worker will download and upload it.
   */
  function extractFounditCVUrl() {
    // Check for a direct CV download link
    const cvLinkSelectors = [
      'a[href*="download"][href*="resume"]',
      'a[href*="download"][href*="cv"]',
      'a[href*=".pdf"]',
      '[class*="downloadCV"] a',
      '[class*="download-cv"] a',
      'a[data-file-type="resume"]',
    ];
    for (const sel of cvLinkSelectors) {
      const el = document.querySelector(sel);
      if (el?.href) return el.href;
    }
    return null;
  }

  /**
   * Full capture flow for Foundit profile pages.
   */
  async function performFounditCapture() {
    const auth = await getAuthToken();
    if (!auth) return { success: false, error: 'Not logged in. Login via extension popup.' };

    showProgressBar();
    updateProgress(10, 'Waiting for Foundit profile to load...');
    await waitForDOMStability();
    await scrollToLoadContent();

    updateProgress(30, 'Extracting Foundit profile...');
    const profileId = extractFounditProfileId();
    const rawText = extractFounditPageText();
    const cvUrl = extractFounditCVUrl();
    const activeJob = await getActiveJob();
    const recruiterCreds = await getRecruiterCredentials();

    // Name from title: "CandidateName - Recruiter Profile | Foundit"
    const titleName = (() => {
      const t = document.title || '';
      const sep = t.includes(' - ') ? ' - ' : t.includes(' | ') ? ' | ' : null;
      if (sep) {
        const part = t.split(sep)[0].trim();
        if (part.length >= 3 && part.length <= 60 && !/foundit|monster/i.test(part)) return part;
      }
      return null;
    })();

    // Extract email/phone from page text
    const emailMatches = rawText.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g) || [];
    const email = emailMatches.find(e => !isNaukriSystemEmail(e)) || null;
    const phoneSet = extractPhonesFromText(rawText.substring(0, 2000));
    const phone = phoneSet.size > 0 ? [...phoneSet][0] : null;

    if (rawText.length < 100) {
      hideProgressBar(2000);
      return { success: false, error: 'Profile not fully loaded. Try scrolling down first.' };
    }

    updateProgress(70, 'Adding to queue...');

    const payload = {
      naukri_profile_id:  profileId,
      naukri_profile_url: window.location.href,
      page_title:         document.title,
      name:               titleName || null,
      email:              email || null,
      phone:              phone || null,
      raw_text:           rawText,
      cv_download_url:    cvUrl || null,    // background will fetch & upload
      recruiter_email:    recruiterCreds.email || null,
      recruiter_phone:    recruiterCreds.phone || null,
      scraped_at:         new Date().toISOString(),
      extension_version:  VERSION,
      source_platform:    'foundit',
      active_job_id:      activeJob?.job_id || null,
      active_job_title:   activeJob?.job_title || null,
    };

    try {
      const result = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: 'enqueueCapture', data: payload }, response => {
          if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
          else resolve(response);
        });
      });

      if (result.action === 'duplicate') {
        updateProgress(100, `${titleName || 'Profile'} already in queue`);
        hideProgressBar(3000);
        return { success: true, action: 'duplicate', name: titleName };
      }

      updateProgress(100, `${titleName || 'Profile'} queued (#${result.queued} in queue)`);
      if (activeJob?.job_title) {
        setTimeout(() => showToast(`📎 Will auto-shortlist to: ${activeJob.job_title}`, 'info'), 1500);
      }
      hideProgressBar(3500);
      return { success: true, action: 'queued', name: titleName, queued: result.queued };
    } catch (e) {
      hideProgressBar(2000);
      return { success: false, error: e.message };
    }
  }

  // ===================== NAUKRI CV URL EXTRACTION =====================

  /**
   * Look for a CV download/attachment URL on Naukri profile pages.
   * Returns URL string if found, null otherwise.
   * The background worker will download this and upload to the candidate record.
   */
  function extractNaukriCVUrl() {
    // CV download button / link selectors on Naukri Resdex
    const cvSelectors = [
      'a[href*="downloadResume"]',
      'a[href*="download-resume"]',
      'a[href*="downloadCV"]',
      'a[href*="cvDownload"]',
      'a[href*="resume/download"]',
      '[class*="downloadResume"] a',
      '[class*="download-resume"] a',
      '[class*="cvDownload"] a',
      'button[class*="downloadResume"]',
      'a[data-ga-track*="download"]',
    ];
    for (const sel of cvSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        const href = el.href || el.getAttribute('data-url') || null;
        if (href && href.startsWith('http')) return href;
      }
    }
    return null;
  }

  // ===================== CAPTURE FLOW =====================

  // ===================== EXCLUDED NAUKRI PAGES =====================
  // Naukri's `/v3/simcv` ("Recruiters also viewed" / similar-CV) overlay
  // mounts the focal candidate's top card *plus* a list of 195+ suggested
  // profiles. Running auto-capture or bulk-capture here causes the extension
  // to grab the wrong person (it scrapes the focal top card while the
  // recruiter is actually browsing the suggestion cards below). Skip it.
  function isExcludedNaukriPage() {
    if (PLATFORM !== 'naukri') return false;
    const pathname = window.location.pathname;
    if (pathname.includes('/v3/simcv')) return true;
    return false;
  }

  // ===================== SEARCH/LIST PAGE DETECTION =====================

  function isSearchPage() {
    const pathname = window.location.pathname;
    const search   = window.location.search;

    if (PLATFORM === 'naukri') {
      if (isExcludedNaukriPage()) return false;
      if (pathname.includes('/v3/search') || pathname.includes('/resdex')) return true;
      if (search.includes('searchId') || search.includes('srcPage')) return true;
      if (document.querySelector('[class*="candidateCard"], [class*="candidate-card"], [class*="resumeCard"]')) return true;
      return false;
    }

    if (PLATFORM === 'linkedin') {
      // Recruiter search: linkedin.com/recruiter/... or /talent/... search pages
      return pathname.includes('/recruiter/') || pathname.includes('/talent/') || pathname.includes('/search/results/');
    }

    if (PLATFORM === 'foundit') {
      return pathname.includes('/search') || pathname.includes('/candidate-search') || search.includes('query');
    }

    return false;
  }

  // ===================== BULK CAPTURE FROM SEARCH/LIST PAGE =====================

  /**
   * Scrape all candidate cards visible on a Naukri search results page.
   * Extracts shallow profile data (name, id, url, headline, location, experience)
   * — these are pre-queued immediately; background worker does full AI extraction.
   */
  async function bulkCapture() {
    if (!isExtensionValid()) return { success: false, error: 'Extension context invalid. Refresh.' };

    showToast('🔍 Scanning candidate list...', 'info');

    // Scroll to load all lazy-rendered cards
    await scrollToLoadList();

    const candidates = scrapeSearchListCandidates();

    if (candidates.length === 0) {
      showToast('No candidates found on this page. Open a Naukri search results page.', 'error');
      return { success: false, error: 'No candidates found on page' };
    }

    showToast(`📋 Found ${candidates.length} candidates — queuing...`, 'info');

    const recruiterCreds = await getRecruiterCredentials();

    const profiles = candidates.map(c => ({
      naukri_profile_id:  c.profileId,
      naukri_profile_url: c.profileUrl,
      page_title:         c.name,
      name:               c.name,
      email:              null,
      phone:              null,
      raw_text:           buildShallowText(c),
      recruiter_email:    recruiterCreds.email || null,
      recruiter_phone:    recruiterCreds.phone || null,
      scraped_at:         new Date().toISOString(),
      extension_version:  VERSION,
      _source:            'bulk_list',
      // Extra fields to help AI when it processes this
      _hint_headline:     c.headline || null,
      _hint_experience:   c.experience || null,
      _hint_location:     c.location || null,
      _hint_company:      c.company || null,
    }));

    try {
      const result = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: 'bulkEnqueue', data: profiles }, response => {
          if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
          else resolve(response);
        });
      });

      if (result.success) {
        const msg = `✅ ${result.queued} queued, ${result.duplicates} dupes skipped${result.dropped ? `, ${result.dropped} dropped (queue full)` : ''}`;
        showToast(msg, 'success');
        return { success: true, ...result };
      } else {
        showToast(`Bulk queue failed: ${result.error}`, 'error');
        return result;
      }
    } catch (err) {
      showToast(`Bulk capture error: ${err.message}`, 'error');
      return { success: false, error: err.message };
    }
  }

  /**
   * Scroll list page to trigger all lazy-loaded candidate cards
   */
  async function scrollToLoadList() {
    const total = document.documentElement.scrollHeight;
    const step  = Math.max(600, Math.floor(window.innerHeight * 0.8));
    for (let y = 0; y < total; y += step) {
      window.scrollTo({ top: y, behavior: 'instant' });
      await sleep(CONFIG.BULK_SCROLL_DELAY);
    }
    window.scrollTo({ top: 0, behavior: 'instant' });
    await sleep(300);
  }

  /**
   * Scrape candidate summary cards from Naukri search results DOM.
   * Handles both classic and SPA-rendered Resdex layouts.
   */
  function scrapeSearchListCandidates() {
    const candidates = [];

    // Try multiple card selectors for different Naukri layouts
    const cardSelectors = [
      '[class*="candidateCard"]',
      '[class*="candidate-card"]',
      '[class*="resumeCard"]',
      '[class*="srp-tuple"]',
      '[class*="srpTuple"]',
      '[data-target-id]',     // older Resdex
      '.tupleCard',
    ];

    let cards = [];
    for (const sel of cardSelectors) {
      cards = Array.from(document.querySelectorAll(sel));
      if (cards.length > 0) break;
    }

    if (cards.length === 0) return [];

    for (const card of cards.slice(0, CONFIG.BULK_MAX_CANDIDATES)) {
      try {
        // ── Profile URL & ID ──
        const linkEl = card.querySelector('a[href*="profile"], a[href*="resume"], a[href*="preview"], a[href*="resdex"]');
        const profileUrl = linkEl ? linkEl.href : null;
        if (!profileUrl) continue;

        const profileId = extractIdFromUrl(profileUrl) || `bulk_${Date.now()}_${Math.random().toString(36).slice(2,6)}`;

        // ── Name ──
        const nameEl = card.querySelector(
          '[class*="name"], [class*="candidateName"], h2, h3, [class*="title"]:first-of-type'
        );
        const name = cleanText(nameEl?.innerText) || 'Unknown';

        // ── Headline / Designation ──
        const headlineEl = card.querySelector('[class*="headline"], [class*="designation"], [class*="currentTitle"]');
        const headline = cleanText(headlineEl?.innerText) || null;

        // ── Experience ──
        const expEl = card.querySelector('[class*="experience"], [class*="exp"], [class*="workex"]');
        const experience = cleanText(expEl?.innerText) || null;

        // ── Location ──
        const locEl = card.querySelector('[class*="location"], [class*="loc"], [class*="city"]');
        const location = cleanText(locEl?.innerText) || null;

        // ── Current Company ──
        const compEl = card.querySelector('[class*="company"], [class*="employer"], [class*="currentCompany"]');
        const company = cleanText(compEl?.innerText) || null;

        candidates.push({ profileId, profileUrl, name, headline, experience, location, company });
      } catch (_) {
        // skip broken card
      }
    }

    return candidates;
  }

  /**
   * Build a shallow text blob so background AI has some context even for list-sourced profiles
   */
  function buildShallowText(c) {
    return [
      c.name      ? `Name: ${c.name}` : '',
      c.headline  ? `Current Role: ${c.headline}` : '',
      c.company   ? `Current Company: ${c.company}` : '',
      c.experience ? `Experience: ${c.experience}` : '',
      c.location  ? `Location: ${c.location}` : '',
      c.profileUrl ? `Profile URL: ${c.profileUrl}` : '',
    ].filter(Boolean).join('\n');
  }

  /**
   * Extract a Naukri profile ID from a URL string
   */
  function extractIdFromUrl(url) {
    if (!url) return null;
    // /v3/preview?..&candidateId=XXX
    const cidMatch = url.match(/[?&](?:candidateId|profileId|pid)=([^&]+)/i);
    if (cidMatch) return cidMatch[1];
    // /resdex/resume/XXX or path segment
    const pathMatch = url.match(/\/(?:resume|profile|cv|preview)\/([a-zA-Z0-9_-]+)/i);
    if (pathMatch) return pathMatch[1];
    // Naukri search-results format: /resdex/profile/<hash> or
    // .../profile/<hash>?…
    const resdexMatch = url.match(/\/resdex\/[^/]*\/([a-zA-Z0-9_-]{12,})/i);
    if (resdexMatch) return resdexMatch[1];
    // Naukri's hashed naukri_<hex> token in any path segment
    const naukriHash = url.match(/(naukri_[a-f0-9]{20,})/i);
    if (naukriHash) return naukriHash[1];
    // sid param
    const sidMatch = url.match(/[?&]sid=([^&]+)/i);
    if (sidMatch) return sidMatch[1];
    return null;
  }

  function isProfilePage() {
    const pathname = window.location.pathname;
    const search = window.location.search;

    if (PLATFORM === 'naukri') {
      if (isExcludedNaukriPage()) return false;
      if (pathname.includes('/v3/preview') && search.includes('tabKey=profile')) return true;
      if (/viewResume|view-resume|cvPreview/i.test(pathname)) return true;
      return false;
    }

    if (PLATFORM === 'linkedin') {
      // linkedin.com/in/username — profile pages only, not /in/ directory or /jobs/ etc
      return /^\/in\/[^/]+\/?$/.test(pathname);
    }

    if (PLATFORM === 'foundit') {
      // foundit.in/profile/xxxxxxx or /resume/xxxxxxx
      return /\/(profile|resume|cv)\/[^/]+/.test(pathname);
    }

    return false;
  }

  async function scrollToLoadContent() {
    const isBackground = document.hidden;
    console.log(`[VHC v${VERSION}] Smart scroll: trigger lazy-load (${isBackground ? 'background tab: bypass physical scrolling' : 'foreground tab: run instant jumps'})`);

    const MAX_SCROLL_TIME = 5000; // hard cap: never scroll for more than 5s total
    const startTime = Date.now();

    // v6.2.2: native lazy-loading (loading="lazy") is IntersectionObserver-
    // based inside the browser — dead in hidden tabs. Flipping the
    // attribute to eager forces the load IMMEDIATELY, viewport be damned.
    try {
      let eagered = 0;
      document.querySelectorAll('iframe[loading="lazy"]').forEach((f) => {
        f.setAttribute('loading', 'eager'); eagered++;
      });
      if (eagered) console.log(`[VHC v${VERSION}] Forced ${eagered} lazy iframe(s) to eager-load`);
    } catch (_) {}

    if (false) { // v6.2.2: background tabs now use the REAL scroll path below.
      // (Old belief: "window.scrollTo is throttled or ignored in background
      // tabs" — wrong. Programmatic scrolling works in hidden tabs; it is
      // RENDERING that stops. The old quietness-wait never scrolled, so
      // scroll-gated lazy content — the CV iframe — never began loading.)
      // In background tabs, window.scrollTo is throttled or ignored by browser layout engines.
      // Simply wait for DOM quietness using a MutationObserver.
      await new Promise((resolve) => {
        let quietTimer = null;
        const QUIET_PERIOD = 600; // slightly longer quiet period for background tab hydration
        const maxTimer = setTimeout(() => {
          observer.disconnect();
          clearTimeout(quietTimer);
          resolve();
        }, MAX_SCROLL_TIME);

        const observer = new MutationObserver(() => {
          clearTimeout(quietTimer);
          quietTimer = setTimeout(() => {
            observer.disconnect();
            clearTimeout(maxTimer);
            resolve();
          }, QUIET_PERIOD);
        });

        observer.observe(document.body, { childList: true, subtree: true });

        quietTimer = setTimeout(() => {
          observer.disconnect();
          clearTimeout(maxTimer);
          resolve();
        }, QUIET_PERIOD);
      });
      
      console.log(`[VHC v${VERSION}] Background DOM quietness wait complete in ${Date.now() - startTime}ms`);
      return;
    }

    // Strategy 1: Jump to bottom instantly — triggers all lazy-load observers at once
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
    try { window.dispatchEvent(new Event('scroll')); } catch (_) {}
    await sleep(400);

    // Strategy 2: Wait for content to settle using MutationObserver (instead of fixed sleeps)
    await new Promise((resolve) => {
      let quietTimer = null;
      const QUIET_PERIOD = 400; // content settled if no new DOM nodes for 400ms
      const remaining = MAX_SCROLL_TIME - (Date.now() - startTime);
      const maxTimer = setTimeout(() => {
        observer.disconnect();
        clearTimeout(quietTimer);
        resolve();
      }, Math.max(remaining, 500));

      const observer = new MutationObserver(() => {
        clearTimeout(quietTimer);
        quietTimer = setTimeout(() => {
          observer.disconnect();
          clearTimeout(maxTimer);
          resolve();
        }, QUIET_PERIOD);
      });

      observer.observe(document.body, { childList: true, subtree: true });

      quietTimer = setTimeout(() => {
        observer.disconnect();
        clearTimeout(maxTimer);
        resolve();
      }, QUIET_PERIOD);
    });

    // Strategy 3: If page grew significantly, do one more targeted scroll
    const heightAfter = document.documentElement.scrollHeight;
    const textLen = (document.body.innerText || '').length;
    console.log(`[VHC v${VERSION}] After instant-scroll: height=${heightAfter}px, text=${textLen}chars`);

    // Strategy 4: Scroll through in 3 large jumps to hit any remaining lazy sections
    // (much faster than 600ms-per-step smooth scroll)
    const thirds = [0.33, 0.66, 1.0];
    for (const fraction of thirds) {
      window.scrollTo({ top: heightAfter * fraction, behavior: 'instant' });
      try { window.dispatchEvent(new Event('scroll')); } catch (_) {}
      await sleep(CONFIG.SCROLL_DELAY); // now 150ms each = 450ms total for 3 jumps
    }

    // v6.2.2: park the viewport ON the CV iframe — keeps its load
    // prioritized and satisfies any residual position-based gating.
    try {
      const cvEl = document.querySelector('iframe#cv-iframe, iframe[name="cv-iframe"], #cv-iframe iframe, .iframe-cv-iframe iframe, iframe[src*="cv"], iframe[src*="resume"], iframe[src*="preview"]');
      if (cvEl) cvEl.scrollIntoView({ block: 'center', behavior: 'instant' });
    } catch (_) {}
    if (!document.hidden) {
      // Foreground: restore the view for the human after a short beat.
      await sleep(300);
      window.scrollTo({ top: 0, behavior: 'instant' });
      await sleep(200);
    }

    const elapsed = Date.now() - startTime;
    console.log(`[VHC v${VERSION}] Scroll complete in ${elapsed}ms. text: ${(document.body.innerText || '').length} chars`);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 3-LAYER DOM STRUCTURED EXTRACTION (Layer 1)
  // Scrapes structured profile fields directly from Naukri Resdex DOM elements.
  // These fields are more reliable than regex/AI because they come from
  // rendered HTML, not unstructured CV text.
  // Phone is typically MASKED on Naukri — must fall back to Layer 2/3.
  // ═══════════════════════════════════════════════════════════════════════════
  // ── Value parsers for labeled Naukri layout (used by extractDOMProfileFields) ──
  function _parseExpVal(s) {
    // "19 Years" / "5 Years 3 Months" / "8 Yrs"
    const m = (s || '').match(/(\d{1,2})\s*(?:Years?|Yrs?)(?:\s+(\d{1,2})\s*(?:Months?|Mos?))?/i);
    if (!m) return null;
    const y = parseInt(m[1], 10);
    const mo = m[2] ? parseInt(m[2], 10) : 0;
    return mo ? parseFloat((y + mo / 100).toFixed(2)) : y;
  }
  function _parseCtcVal(s) {
    // "₹ 25 Lacs" / "25 LPA" / "1.5 Cr"
    const m = (s || '').match(/₹?\s*(\d+(?:\.\d+)?)\s*(Lacs?|Lakhs?|LPA|Lac|Cr|Crore|L)\b/i);
    if (!m) return null;
    const v = parseFloat(m[1]);
    const unit = m[2].toLowerCase();
    const rupees = (unit === 'cr' || unit === 'crore') ? v * 10000000 : v * 100000;
    if (rupees < 50000 || rupees > 200000000) return null;  // sanity window
    return Math.round(rupees);
  }
  function _parseNoticeVal(s) {
    // Returns {label, days}
    const t = (s || '').trim();
    if (/^immediat/i.test(t))       return { label: 'Immediate',        days: 0 };
    if (/15\s*days?\s*or\s*less/i.test(t)) return { label: '15 Days or less', days: 15 };
    if (/^serving/i.test(t))        return { label: 'Serving Notice',   days: 0 };
    const m = t.match(/(\d{1,3})\s*(Days?|Months?|Weeks?)/i);
    if (!m) return null;
    const n = parseInt(m[1], 10);
    const u = m[2].toLowerCase();
    if (u.startsWith('day') && n <= 180)  return { label: `${n} Days`,  days: n };
    if (u.startsWith('month') && n <= 12) return { label: `${n} Month${n !== 1 ? 's' : ''}`, days: n * 30 };
    if (u.startsWith('week') && n <= 52)  return { label: `${n} Week${n !== 1 ? 's' : ''}`,  days: n * 7 };
    return null;
  }
  function _parseLocVal(s) {
    const t = (s || '').trim().replace(/^,|,$/g, '');
    if (t.length < 2 || t.length > 80) return null;
    if (/\d{4,}|@|http/.test(t)) return null;
    return t;
  }

  function extractDOMProfileFields(domName) {
    // ── SCOPE GUARDS v5.3.1 ──
    // Fix for the "Ramakant bug": when the current candidate's top card has
    // NO CTC / experience / notice-period, the earlier document-wide
    // querySelectorAll scans latched onto values from the right-side
    // "AI matched similar profiles" / "Recommended profiles" sidebar.
    // These helpers keep every title-attribute / label scan strictly
    // inside the CURRENT candidate's container.
    function _isInRecommendedSection(el) {
      let cur = el;
      while (cur && cur !== document.body) {
        try {
          const cls = (cur.className && typeof cur.className === 'string')
            ? cur.className.toLowerCase() : '';
          const id  = (cur.id || '').toLowerCase();
          if (/similar|related|recommend|suggest|matching[-_ ]?profile|ai[-_ ]?match|other[-_ ]?profile|matchingcand|matching-cand|aiprofile|more[-_ ]?profile/i.test(cls)
              || /similar|related|recommend|suggest|matching/i.test(id)) {
            return true;
          }
        } catch (_) {}
        cur = cur.parentElement;
      }
      return false;
    }
    function _getTopCardEl() {
      const tryList = [
        '#rdxRoot [class*="topHeader"]',   '#rdxRoot [class*="top-header"]',
        '#rdxRoot [class*="topBar"]',      '#rdxRoot [class*="top-bar"]',
        '#rdxRoot [class*="profileHeader"]','#rdxRoot [class*="profile-header"]',
        '#rdxRoot [class*="candidateHeader"]','#rdxRoot [class*="headerDetail"]',
        '#rdxRoot [class*="profileTop"]',  '#rdxRoot [class*="profile-top"]',
      ];
      for (const sel of tryList) {
        const el = document.querySelector(sel);
        if (el && !_isInRecommendedSection(el)) return el;
      }
      return null;
    }
    const _topCard = _getTopCardEl();
    const _candRoot = (typeof getCandidateRoot === 'function') ? getCandidateRoot() : document.body;
    // Tight scope for top-card-only fields (CTC, exp, notice).
    // Broad scope for sections that may live below the top card but still
    // inside the main candidate container (labeled layout, summary bar).
    const _tightScope = _topCard || _candRoot;
    const _broadScope = _candRoot;
    console.log(`[VHC v${VERSION}] DOM scope: topCard=${_topCard ? 'yes' : 'no'}, using tight=${_tightScope === _topCard ? 'topCard' : 'candidateRoot'}`);

    const fields = {
      name: domName || null,
      current_company: null,
      current_designation: null,
      current_salary: null,
      expected_salary: null,
      notice_period: null,
      notice_period_days: null,
      current_location: null,
      total_experience_years: null,
      key_skills: [],
      education: [],
      work_experience: [],
      profile_summary: null,
      preferred_locations: [],
    };

    try {
      // ── 1. NAUKRI RESDEX SPECIFIC: Company + Designation ──
      // Strategy: Use ellipsis title attributes which contain "Designation at Company since Date"
      
      // Method 1: Extract from ellipsis title (most reliable)
      // v5.3.1: scoped to candidate root with recommended-section guard.
      const ellipsisSpans = _broadScope.querySelectorAll('span.ellipsis[title]');
      for (const span of ellipsisSpans) {
        if (_isInRecommendedSection(span)) continue;
        const title = span.getAttribute('title') || '';
        // Match: "Associate Manager at Adani Infra India Limited since Apr '24"
        const atMatch = title.match(/^(.+?)\s+at\s+(.+?)(?:\s+since\s+|$)/i);
        if (atMatch) {
          const designation = atMatch[1].trim();
          const company = atMatch[2].trim();
          if (!fields.current_designation && designation.length > 2 && designation.length < 100 && !designation.match(/^\d/)) {
            fields.current_designation = designation;
          }
          if (!fields.current_company && company.length > 2 && company.length < 100 && !company.match(/^\d/)) {
            fields.current_company = company;
          }
          if (fields.current_designation && fields.current_company) break;
        }
      }

      // Method 2: hlite-inherit spans (top bar data)
      // v5.3.1: scoped + recommended-section guard.
      if (!fields.current_company || !fields.current_designation) {
        const hliteSpansAll = _tightScope.querySelectorAll('span.hlite-inherit');
        const hliteSpans = [...hliteSpansAll].filter(s => !_isInRecommendedSection(s));
        if (hliteSpans.length >= 2) {
          // Naukri Resdex top bar order: [Company, Designation, Experience, CTC, ...]
          const company = cleanText(hliteSpans[0].textContent);
          const designation = cleanText(hliteSpans[1].textContent);
          
          if (!fields.current_company && company && company.length > 2 && company.length < 100 && !company.match(/^\d/) && !company.match(/lac|month|year/i)) {
            fields.current_company = company;
          }
          if (!fields.current_designation && designation && designation.length > 2 && designation.length < 100 && !designation.match(/^\d/) && !designation.match(/lac|month|year/i)) {
            fields.current_designation = designation;
          }
        }
      }

      // ── 2. NAUKRI RESDEX: Extract CTC, Experience, Notice Period from title attributes ──
      // Naukri uses: <span title="₹ 12 Lacs (expects: ₹ 18 Lacs)">
      //              <span title="17y">17y</span>
      //              <span>3 Months</span>
      
      // CTC from title attributes
      // v5.3.1: scoped to top card + _isInRecommendedSection guard.
      // Previously document-wide → leaked from "AI matched similar profiles".
      const ctcSpans = _tightScope.querySelectorAll('span[title*="Lac"], span[title*="₹"]');
      for (const span of ctcSpans) {
        if (_isInRecommendedSection(span)) continue;
        const title = span.getAttribute('title') || '';
        // Match: "₹ 12 Lacs (expects: ₹ 18 Lacs)"
        const currentMatch = title.match(/₹\s*(\d+(?:\.\d+)?)\s*Lac/i);
        const expectsMatch = title.match(/expects:\s*₹\s*(\d+(?:\.\d+)?)\s*Lac/i);

        if (currentMatch && !fields.current_salary) {
          const v = parseFloat(currentMatch[1]) * 100000;
          // Sanity window: ₹50K – ₹5 Cr annual
          if (v >= 50000 && v <= 50000000) fields.current_salary = v;
        }
        if (expectsMatch && !fields.expected_salary) {
          const v = parseFloat(expectsMatch[1]) * 100000;
          if (v >= 50000 && v <= 50000000) fields.expected_salary = v;
        }
        if (fields.current_salary && fields.expected_salary) break;
      }

      // Experience from title attributes: <span title="10y 1m">10y 1m</span> or <span title="17y">17y</span>
      // v5.3.1: scoped + recommended-section guard.
      if (!fields.total_experience_years) {
        const expSpans = _tightScope.querySelectorAll('span[title]');
        for (const span of expSpans) {
          if (_isInRecommendedSection(span)) continue;
          const title = (span.getAttribute('title') || '').trim();
          // Try compound "10y 1m" first (Naukri top-card standard)
          let expMatch = title.match(/^(\d{1,2})\s*y\s+(\d{1,2})\s*m$/i);
          if (expMatch) {
            const yrs = parseInt(expMatch[1]);
            const mos = parseInt(expMatch[2]);
            // Use /100 formula to stay consistent with backend (years + months/100)
            fields.total_experience_years = parseFloat((yrs + mos / 100).toFixed(2));
            break;
          }
          // Fallback: "17y" alone
          expMatch = title.match(/^(\d{1,2})\s*y$/i);
          if (expMatch) {
            fields.total_experience_years = parseInt(expMatch[1]);
            break;
          }
        }
      }

      // Notice Period - Naukri shows directly: <span>3 Months</span> or <span>7 Months</span>
      // v5.3.1: scoped to top card to prevent leak from sidebar cards.
      if (!fields.notice_period) {
        // Look for spans near notice period icon
        const noticeIcon = _tightScope.querySelector('i[title="Notice period"]') ||
                           (!_isInRecommendedSection(document.querySelector('i[title="Notice period"]') || document.body)
                             ? document.querySelector('i[title="Notice period"]') : null);
        if (noticeIcon && !_isInRecommendedSection(noticeIcon)) {
          const parent = noticeIcon.closest('div');
          if (parent) {
            const noticeSpan = parent.querySelector('span:not([class*="ico"])');
            if (noticeSpan) {
              const noticeText = cleanText(noticeSpan.textContent);
              const monthMatch = noticeText.match(/(\d+)\s*Month/i);
              if (monthMatch) {
                const num = parseInt(monthMatch[1]);
                fields.notice_period = noticeText;
                fields.notice_period_days = num * 30;
              }
            }
          }
        }
      }

      // ── 2.5 NAUKRI LABELED LAYOUT (newer Naukri profile pages) ──
      // Format: "Experience\n19 Years\nCurrent CTC\n₹25 Lacs\nNotice Period\n3 Months"
      // These appear as stacked label/value pairs in distinct container divs.
      // We scan the DOM for div/li elements whose text starts with a known label,
      // then extract the sibling/next-line value. This is the DOM equivalent of
      // the backend label-aware regex and produces the highest accuracy.
      try {
        const LABEL_MAP = [
          { label: /^(Total\s*)?Experience\s*$/i,           key: 'total_experience_years', parser: _parseExpVal },
          { label: /^(Current|Present)?\s*CTC\s*$/i,        key: 'current_salary',         parser: _parseCtcVal },
          { label: /^Expected\s*(CTC|Salary)?\s*$/i,        key: 'expected_salary',        parser: _parseCtcVal },
          { label: /^Notice\s*Period\s*$/i,                 key: 'notice_period',          parser: _parseNoticeVal, withDays: true },
          { label: /^(Current)?\s*Location\s*$/i,           key: 'current_location',       parser: _parseLocVal },
        ];
        // Walk all low-leaf elements that contain only text (typical label elements)
        // v5.3.1: scoped to candidate root + recommended-section guard.
        const labelCandidates = _broadScope.querySelectorAll('div, li, span');
        for (const el of labelCandidates) {
          if (_isInRecommendedSection(el)) continue;
          const text = cleanText(el.textContent || '');
          if (!text || text.length > 60) continue;
          for (const m of LABEL_MAP) {
            if (!m.label.test(text)) continue;
            // Value is usually the next sibling or the next leaf in the subtree
            let valueText = '';
            let sib = el.nextElementSibling;
            if (sib) valueText = cleanText(sib.textContent || '');
            if (!valueText && el.parentElement) {
              // Fallback: look at parent for a child *after* this label
              const siblings = Array.from(el.parentElement.children);
              const idx = siblings.indexOf(el);
              if (idx >= 0 && idx + 1 < siblings.length) {
                valueText = cleanText(siblings[idx + 1].textContent || '');
              }
            }
            if (!valueText) continue;
            const parsed = m.parser(valueText);
            if (parsed == null) continue;
            if (m.withDays && typeof parsed === 'object') {
              if (!fields[m.key]) {
                fields[m.key] = parsed.label;
                fields.notice_period_days = parsed.days;
              }
            } else if (!fields[m.key]) {
              fields[m.key] = parsed;
            }
          }
        }
      } catch (_e) {
        // Non-fatal — labeled parser is additive
      }

      // ── 3. Summary bar: Experience | CTC | Notice | Location (Fallback) ──
      // Naukri shows these as key highlights, often in a horizontal bar
      const summarySelectors = [
        '[class*="keyHighlight"]', '[class*="key-highlight"]', '[class*="KeyHighlight"]',
        '[class*="profileHighlight"]', '[class*="profile-highlight"]',
        '[class*="summaryBar"]', '[class*="summary-bar"]',
        '[class*="quickInfo"]', '[class*="quick-info"]',
        '[class*="detailRow"]', '[class*="detail-row"]',
      ];

      let summaryEls = [];
      for (const sel of summarySelectors) {
        // v5.3.1: scoped to candidate root, filter recommended-section matches.
        const all = _broadScope.querySelectorAll(sel);
        summaryEls = [...all].filter(el => !_isInRecommendedSection(el));
        if (summaryEls.length > 0) break;
      }

      // Also try looking for structured label-value pairs
      const labelValueSelectors = [
        '[class*="infoLabel"]', '[class*="info-label"]',
        '[class*="detailLabel"]', '[class*="detail-label"]',
        '[class*="keyLabel"]', '[class*="key-label"]',
      ];

      // Parse all text from summary section for structured extraction
      const summaryTexts = [];
      summaryEls.forEach(el => {
        const t = cleanText(el.textContent);
        if (t) summaryTexts.push(t);
      });

      // Also scan label-value pairs
      // v5.3.1: scoped + recommended-section guard.
      for (const sel of labelValueSelectors) {
        _broadScope.querySelectorAll(sel).forEach(el => {
          if (_isInRecommendedSection(el)) return;
          const parent = el.parentElement;
          if (parent) {
            const t = cleanText(parent.textContent);
            if (t) summaryTexts.push(t);
          }
        });
      }

      const summaryText = summaryTexts.join(' | ');

      // Experience years (e.g., "10y 1m", "10y", "8 Years", "5.5 yrs")
      if (!fields.total_experience_years) {
        // Try compound "10y 1m" first
        let expMatch = summaryText.match(/(\d{1,2})\s*y\s+(\d{1,2})\s*m\b/i);
        if (expMatch) {
          const yrs = parseInt(expMatch[1]);
          const mos = parseInt(expMatch[2]);
          fields.total_experience_years = parseFloat((yrs + mos / 100).toFixed(2));
        } else {
          expMatch = summaryText.match(/(\d{1,2}(?:\.\d)?)\s*(?:y(?:ears?|rs?)?)/i);
          if (expMatch) {
            fields.total_experience_years = parseFloat(expMatch[1]);
          }
        }
      }

      // CTC parsing (₹ 25 Lacs, 25L, ₹ 25,00,000, 2500000)
      const ctcPattern = /(?:₹|rs\.?|inr)\s*(\d[\d,\.]*)\s*(lacs?|lakhs?|lpa|cr(?:ore)?|k)?/gi;
      const ctcMatches = [...summaryText.matchAll(ctcPattern)];
      for (let i = 0; i < ctcMatches.length; i++) {
        const m = ctcMatches[i];
        let val = parseFloat(m[1].replace(/,/g, ''));
        const unit = (m[2] || '').toLowerCase();
        if (unit.startsWith('lac') || unit.startsWith('lak') || unit === 'lpa') val *= 100000;
        else if (unit.startsWith('cr')) val *= 10000000;
        else if (unit === 'k') val *= 1000;
        else if (val < 200) val *= 100000; // bare number < 200 likely lacs

        if (val > 0 && val >= 50000 && val <= 50000000) { // sanity: ₹50K – ₹5 Cr annual
          if (i === 0 && !fields.current_salary) fields.current_salary = val;
          else if (i === 1 && !fields.expected_salary) fields.expected_salary = val;
        }
      }

      // Also try "Current CTC:" and "Expected CTC:" labeled patterns
      const labeledCtcCurrent = summaryText.match(/(?:current|curr\.?)\s*(?:ctc|salary|comp)\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*(\d[\d,\.]*)\s*(lacs?|lakhs?|lpa|cr(?:ore)?)?/i);
      if (labeledCtcCurrent && !fields.current_salary) {
        let val = parseFloat(labeledCtcCurrent[1].replace(/,/g, ''));
        const unit = (labeledCtcCurrent[2] || '').toLowerCase();
        if (unit.startsWith('lac') || unit.startsWith('lak') || unit === 'lpa') val *= 100000;
        else if (unit.startsWith('cr')) val *= 10000000;
        else if (val < 200) val *= 100000;
        if (val > 0 && val >= 50000 && val <= 50000000) fields.current_salary = val;
      }

      const labeledCtcExpected = summaryText.match(/(?:expected|exp\.?|prefer)\s*(?:ctc|salary|comp)\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*(\d[\d,\.]*)\s*(lacs?|lakhs?|lpa|cr(?:ore)?)?/i);
      if (labeledCtcExpected && !fields.expected_salary) {
        let val = parseFloat(labeledCtcExpected[1].replace(/,/g, ''));
        const unit = (labeledCtcExpected[2] || '').toLowerCase();
        if (unit.startsWith('lac') || unit.startsWith('lak') || unit === 'lpa') val *= 100000;
        else if (unit.startsWith('cr')) val *= 10000000;
        else if (val < 200) val *= 100000;
        if (val > 0 && val >= 50000 && val <= 50000000) fields.expected_salary = val;
      }

      // Notice period
      const noticeMatch = summaryText.match(/(\d+)\s*(month|day|week|year)s?\s*(?:notice)?/i) ||
                          summaryText.match(/notice\s*(?:period)?\s*[:\-]?\s*(\d+)\s*(month|day|week|year)s?/i) ||
                          summaryText.match(/(immediately?\s*(?:available)?|serving\s*notice)/i);
      if (noticeMatch) {
        if (noticeMatch[0].toLowerCase().includes('immediate')) {
          fields.notice_period = 'Immediate';
          fields.notice_period_days = 0;
        } else if (noticeMatch[0].toLowerCase().includes('serving')) {
          fields.notice_period = 'Serving Notice';
          fields.notice_period_days = 0;
        } else {
          const num = parseInt(noticeMatch[1]);
          const unit = (noticeMatch[2] || 'month').toLowerCase();
          if (unit.startsWith('month')) {
            fields.notice_period = `${num} Month${num > 1 ? 's' : ''}`;
            fields.notice_period_days = num * 30;
          } else if (unit.startsWith('day')) {
            fields.notice_period = `${num} Days`;
            fields.notice_period_days = num;
          } else if (unit.startsWith('week')) {
            fields.notice_period = `${num} Week${num > 1 ? 's' : ''}`;
            fields.notice_period_days = num * 7;
          } else if (unit.startsWith('year')) {
            fields.notice_period = `${num} Year${num > 1 ? 's' : ''}`;
            fields.notice_period_days = num * 365;
          }
        }
      }

      // Location — look for known patterns or dedicated location elements
      const locationSelectors = [
        '[class*="location"]', '[class*="Location"]',
        '[class*="currentCity"]', '[class*="current-city"]',
        'i.naukri-icon-location', 'i.naukri-icon-pin',
      ];
      for (const sel of locationSelectors) {
        const el = document.querySelector(sel);
        if (el) {
          const parent = el.closest('[class*="highlight"]') || el.closest('[class*="detail"]') || el.parentElement;
          const text = cleanText(parent ? parent.textContent : el.textContent);
          if (text && text.length > 1 && text.length < 80 && !/\d{4,}/.test(text)) {
            // Remove "Location:" prefix if present
            fields.current_location = text.replace(/^(?:location|city|current\s*location)\s*[:\-]\s*/i, '').trim();
            break;
          }
        }
      }

      // Fallback location from summary text
      if (!fields.current_location) {
        const locMatch = summaryText.match(/(?:location|city)\s*[:\-]\s*([A-Za-z][A-Za-z\s,]+?)(?:\s*[\|·\-]|$)/i);
        if (locMatch) {
          fields.current_location = locMatch[1].trim();
        }
      }

      // ── 3. Key Skills from chip/tag elements ──
      const skillSelectors = [
        '[class*="skillsTags"] [class*="chip"]', '[class*="skillsTags"] span',
        '[class*="skills-tags"] [class*="chip"]', '[class*="skills-tags"] span',
        '[class*="keySkill"] [class*="chip"]', '[class*="keySkill"] span',
        '[class*="key-skill"] [class*="chip"]', '[class*="key-skill"] span',
        '[class*="SkillTag"]', '[class*="skill-tag"]', '[class*="skillTag"]',
        '[class*="skillChip"]', '[class*="skill-chip"]',
      ];

      for (const sel of skillSelectors) {
        const els = document.querySelectorAll(sel);
        if (els.length > 0) {
          els.forEach(el => {
            const text = cleanText(el.textContent);
            if (text && text.length > 1 && text.length < 60 && !/^\d+$/.test(text) && !text.toLowerCase().includes('more')) {
              if (!fields.key_skills.includes(text)) fields.key_skills.push(text);
            }
          });
          if (fields.key_skills.length > 0) break;
        }
      }

      // Fallback: try the skills section heading + following chips
      if (fields.key_skills.length === 0) {
        const skillsSection = document.querySelector('[class*="skillsContainer"]') ||
                              document.querySelector('[class*="skills-container"]') ||
                              document.querySelector('[id*="skills"]');
        if (skillsSection) {
          const chips = skillsSection.querySelectorAll('span, [class*="chip"], [class*="tag"]');
          chips.forEach(el => {
            const text = cleanText(el.textContent);
            if (text && text.length > 1 && text.length < 60 && !/^\d+$/.test(text)) {
              if (!fields.key_skills.includes(text)) fields.key_skills.push(text);
            }
          });
        }
      }

      // ── 4. Education from education section ──
      const eduSelectors = [
        '[class*="education"]', '[class*="Education"]',
        '[class*="qualification"]', '[class*="Qualification"]',
        '#education', '#Education',
      ];

      for (const sel of eduSelectors) {
        const section = document.querySelector(sel);
        if (!section) continue;
        // Look for degree/institution/year text
        const items = section.querySelectorAll('[class*="item"]') ||
                      section.querySelectorAll('[class*="row"]') ||
                      section.querySelectorAll('li');
        if (items.length > 0) {
          items.forEach(item => {
            const text = cleanText(item.textContent);
            if (text && text.length > 5 && text.length < 200) {
              fields.education.push(text);
            }
          });
          if (fields.education.length > 0) break;
        }
        // Fallback: just get the section text
        const sectionText = cleanText(section.textContent);
        if (sectionText && sectionText.length > 10 && sectionText.length < 500) {
          fields.education.push(sectionText);
          break;
        }
      }

      // ── 5. ENHANCED: Work Experience Extraction ──
      const workExpSelectors = [
        '[class*="experienceContainer"]', '[class*="experience-container"]',
        '[class*="workHistory"]', '[class*="work-history"]',
        '[class*="employmentSection"]', '[class*="employment-section"]',
        '#experience', '#workExperience',
        '[id*="experience"]', '[id*="employment"]',
      ];

      for (const sel of workExpSelectors) {
        const section = document.querySelector(sel);
        if (!section) continue;

        // Look for individual job entries
        const jobSelectors = [
          '[class*="experienceItem"]', '[class*="experience-item"]',
          '[class*="jobItem"]', '[class*="job-item"]',
          '[class*="employmentItem"]', '[class*="employment-item"]',
          '[class*="companyBlock"]', '[class*="company-block"]',
        ];

        let jobs = [];
        for (const jobSel of jobSelectors) {
          jobs = section.querySelectorAll(jobSel);
          if (jobs.length > 0) break;
        }

        // If no structured items found, try to parse from text
        if (jobs.length === 0) {
          jobs = section.querySelectorAll('li, [class*="row"]');
        }

        if (jobs.length > 0) {
          jobs.forEach(job => {
            try {
              const jobText = cleanText(job.textContent);
              if (!jobText || jobText.length < 10) return;

              // Extract company name (usually bold or first heading)
              let company = null;
              const companyEl = job.querySelector('h3, h4, strong, b, [class*="company"], [class*="employer"]');
              if (companyEl) company = cleanText(companyEl.textContent);

              // Extract designation
              let designation = null;
              const designationEl = job.querySelector('[class*="designation"], [class*="title"], [class*="role"]');
              if (designationEl) designation = cleanText(designationEl.textContent);

              // Extract dates
              let from_date = null, to_date = null, duration = null;
              const dateMatch = jobText.match(/(\w{3,9}\s+\d{4})\s*(?:to|-|–)\s*(\w{3,9}\s+\d{4}|present|till\s*date|current)/i);
              if (dateMatch) {
                from_date = dateMatch[1];
                to_date = dateMatch[2].toLowerCase().includes('present') || dateMatch[2].toLowerCase().includes('current') || dateMatch[2].toLowerCase().includes('till') ? 'Present' : dateMatch[2];
              }

              // Extract duration (e.g., "2y 3m")
              const durationMatch = jobText.match(/(\d+)\s*y(?:ears?)?\s*(\d+)?\s*m(?:onths?)?/i) || 
                                    jobText.match(/(\d+)\s*(?:years?|yrs?)/i);
              if (durationMatch) {
                const years = parseInt(durationMatch[1]);
                const months = durationMatch[2] ? parseInt(durationMatch[2]) : 0;
                duration = months > 0 ? `${years}y ${months}m` : `${years}y`;
              }

              // Fallback: extract company/designation from text patterns
              if (!company || !designation) {
                const atMatch = jobText.match(/(.+?)\s+at\s+(.+?)(?:\s+[\|·]|$)/i);
                if (atMatch) {
                  if (!designation) designation = atMatch[1].split('\n')[0].trim();
                  if (!company) company = atMatch[2].split('\n')[0].trim();
                }
              }

              if (company || designation) {
                fields.work_experience.push({
                  company: company || 'Unknown Company',
                  designation: designation || 'Unknown Role',
                  from_date: from_date,
                  to_date: to_date,
                  duration: duration,
                  is_current: to_date === 'Present',
                  description: jobText.length < 500 ? jobText : jobText.substring(0, 500),
                });
              }
            } catch (e) {
              console.warn(`[VHC v${VERSION}] Work exp item parse error:`, e.message);
            }
          });
          if (fields.work_experience.length > 0) break;
        }
      }

      // ── 6. ENHANCED: Profile Summary Extraction ──
      const profileSummarySelectors = [
        '[class*="profileSummary"]', '[class*="profile-summary"]',
        '[class*="about"]', '[class*="About"]',
        '[class*="summary"]', '[class*="Summary"]',
        '#summary', '#about', '#profileSummary',
        '[id*="summary"]', '[id*="about"]',
      ];

      for (const sel of profileSummarySelectors) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const text = cleanText(el.textContent);
        if (text && text.length > 20 && text.length < 2000) {
          fields.profile_summary = text;
          break;
        }
      }

      // ── 7. ENHANCED: Preferred Locations Extraction ──
      const prefLocSelectors = [
        '[class*="preferredLocation"]', '[class*="preferred-location"]',
        '[class*="desiredLocation"]', '[class*="desired-location"]',
      ];

      for (const sel of prefLocSelectors) {
        const section = document.querySelector(sel);
        if (!section) continue;
        const chips = section.querySelectorAll('span, [class*="chip"], [class*="tag"]');
        if (chips.length > 0) {
          chips.forEach(chip => {
            const loc = cleanText(chip.textContent);
            if (loc && loc.length > 2 && loc.length < 50 && !fields.preferred_locations.includes(loc)) {
              fields.preferred_locations.push(loc);
            }
          });
          break;
        }
        // Fallback: parse from comma-separated text
        const text = cleanText(section.textContent);
        if (text) {
          const locs = text.split(/[,;]\s*/);
          locs.forEach(loc => {
            const clean = loc.trim();
            if (clean.length > 2 && clean.length < 50 && !fields.preferred_locations.includes(clean)) {
              fields.preferred_locations.push(clean);
            }
          });
        }
      }

      // Count how many fields we actually scraped
      let filledCount = 0;
      if (fields.name) filledCount++;
      if (fields.current_company) filledCount++;
      if (fields.current_designation) filledCount++;
      if (fields.current_salary) filledCount++;
      if (fields.notice_period) filledCount++;
      if (fields.current_location) filledCount++;
      if (fields.total_experience_years) filledCount++;
      if (fields.key_skills.length > 0) filledCount++;
      if (fields.work_experience.length > 0) filledCount++;
      if (fields.profile_summary) filledCount++;
      if (fields.education.length > 0) filledCount++;

      fields._dom_field_count = filledCount;
      fields._dom_scraped = filledCount >= 3; // Need at least 3 fields to trust DOM data

      console.log(`[VHC v${VERSION}] DOM Profile Fields: ${filledCount}/11 filled | ` +
        `name=${fields.name} company=${fields.current_company} desg=${fields.current_designation} ` +
        `ctc=${fields.current_salary} notice=${fields.notice_period} loc=${fields.current_location} ` +
        `exp=${fields.total_experience_years} skills=${fields.key_skills.length} ` +
        `work_exp=${fields.work_experience.length} edu=${fields.education.length} summary=${fields.profile_summary ? 'yes' : 'no'}`);

    } catch (err) {
      console.warn(`[VHC v${VERSION}] DOM field extraction error:`, err.message);
      fields._dom_scraped = false;
      fields._dom_field_count = 0;
    }

    return fields;
  }

  /**
   * MAIN CAPTURE — Multi-Source Cross-Validation Pipeline v5.4.1
   * 
   * v5.4.1 FIX: Added candidate profile validation to prevent background-tab
   * captures from scraping the recruiter's own contact info. The key changes:
   * 1. Wait for candidate profile to actually load before extracting
   * 2. Validate that we have candidate-specific content (not just page chrome)
   * 3. Extra safeguards against recruiter email/phone leaking through
   */
  async function performCapture(isManual) {
    const auth = await getAuthToken();
    if (!auth) return { success: false, error: 'Not logged in. Login via extension popup.' };

    showProgressBar();
    updateProgress(5, 'Waiting for page to settle...');

    // Step 0: Get recruiter credentials FIRST so we can filter them out everywhere
    const recruiterCreds = await getRecruiterCredentials();
    // v6.0.2 FIX (Sachin/ajit bug): snapshot the Naukri-session login email
    // (page chrome / header / user dropdown) so it is excluded from candidate
    // contact extraction even when it differs from the VHC login email.
    try {
      recruiterCreds.chromeEmails = snapshotChromeEmails();
    } catch (e) {
      recruiterCreds.chromeEmails = new Set();
      console.warn(`[VHC v${VERSION}] snapshotChromeEmails failed:`, e);
    }
    console.log(`[VHC v${VERSION}] Recruiter blocklist: email=${recruiterCreds.email || 'none'}, phone=${recruiterCreds.phone || 'none'}, chrome=[${[...recruiterCreds.chromeEmails].join(', ') || 'none'}]`);

    // Step 1: DOM stability check
    const stableTitle = await waitForDOMStability();
    updateProgress(8, 'Verifying candidate profile...');

    // Step 1.5 (v5.4.1 FIX): Wait for candidate profile to actually load
    // This is CRITICAL for background tabs where Naukri lazy-loads content
    const profileValidation = await waitForCandidateProfile();
    if (!profileValidation.ready) {
      console.warn(`[VHC v${VERSION}] Profile not ready: ${profileValidation.reason}`);
      updateProgress(0, 'Profile not loaded');
      hideProgressBar(2000);
      showToast('Profile not fully loaded. Switch to this tab and try again.', 'error');
      return { success: false, error: profileValidation.reason };
    }

    updateProgress(10, 'Scrolling page...');

    // Step 2: Scroll to load ALL content including CV iframe
    await scrollToLoadContent();
    // No extra sleep needed — scrollToLoadContent already settles via MutationObserver

    // Step 3: Extract name from title (validated in waitForCandidateProfile)
    updateProgress(15, 'Extracting candidate name...');
    const domName = profileValidation.candidateName || extractNameFromTitle();
    console.log(`[VHC v${VERSION}] Candidate name: "${domName}"`);

    // v5.4.1 FIX: Validate that the extracted name is NOT the recruiter's name
    if (domName && recruiterCreds.email) {
      const recruiterNameGuess = recruiterCreds.email.split('@')[0].replace(/[._]/g, ' ');
      if (domName.toLowerCase().includes(recruiterNameGuess.toLowerCase())) {
        console.warn(`[VHC v${VERSION}] ⚠️ Name "${domName}" looks like recruiter — aborting`);
        updateProgress(0, 'Wrong profile detected');
        hideProgressBar(2000);
        showToast('Captured recruiter profile instead of candidate. Switch tabs and retry.', 'error');
        return { success: false, error: 'Recruiter profile detected instead of candidate' };
      }
    }

    // Step 3.5: [3-LAYER] Extract structured DOM profile fields (Layer 1)
    updateProgress(17, 'Scanning profile structure...');
    const domFields = extractDOMProfileFields(domName);
    console.log(`[VHC v${VERSION}] DOM scrape: ${domFields._dom_field_count}/8 fields | dom_scraped=${domFields._dom_scraped}`);

    // Step 4: Snapshot EMAILS before click (for email diff)
    // Step 4+5: Snapshot emails AND click View Contact
    // clickViewContactButton() internally does BEFORE/AFTER diff on candidate root
    // so revealedPhones = only numbers that NEWLY appeared → guaranteed candidate phone
    updateProgress(20, 'Scanning page contacts...');
    const beforeEmails = snapshotPageEmails();
    console.log(`[VHC v${VERSION}] BEFORE emails: [${[...beforeEmails].join(', ')}]`);

    updateProgress(30, 'Revealing contact info...');
    const contactReveal = await clickViewContactButton();
    console.log(`[VHC v${VERSION}] Revealed phones (diff): [${contactReveal.revealedPhones.join(', ')}]`);

    // Step 6: Diff emails for email capture (phone diff already done inside clickViewContactButton)
    updateProgress(40, 'Analyzing revealed contacts...');
    const afterEmails = snapshotPageEmails();
    const newEmails = [...afterEmails].filter(e => !beforeEmails.has(e));
    const diff = {
      emails: newEmails,
      phones: contactReveal.revealedPhones, // diff-based: only newly appeared phones
    };
    console.log(`[VHC v${VERSION}] DIFF: new emails=[${diff.emails.join(', ')}], new phones=[${diff.phones.join(', ')}]`);

    // Step 7: Scan CV iframe (async — tries 3 strategies)
    updateProgress(50, 'Scanning CV preview...');
    const cvData = await acquireCVData(domName, cvWaitBudget());
    console.log(`[VHC v${VERSION}] CV: email=${cvData.email || 'none'}, phone=${cvData.phone || 'none'}, valid=${cvData.isValid}, text=${cvData.text.length}chars`);

    // Step 8: DOM selector fallback (recruiterCreds already fetched at start)
    const domSelectorData = extractFromDOMSelectors(recruiterCreds);

    // Step 9: MERGE — pass beforeEmails as Set for email fallback
    updateProgress(55, 'Cross-validating contacts...');
    const merged = mergeContacts(cvData, diff, domSelectorData, recruiterCreds, { emails: beforeEmails, phones: new Set() });
    console.log(`[VHC v${VERSION}] === FINAL: email=${merged.email || 'NONE'}, phone=${merged.phone || 'NONE'} ===`);

    // Step 9.5 (v6.0.1): BACKGROUND-TAB CONTACT RESCUE
    // In a hidden tab Naukri frequently never renders the contact section /
    // "View Contact" button (visibility-gated lazy rendering), so background
    // captures came back contactless ~100% of the time. If we're hidden and
    // found no contacts, ask the service worker to flash-activate this tab
    // (it restores the user's previous tab right after), wait for render,
    // then re-run the reveal + extraction once.
    let mergedFinal = merged;

    // Step 9.4 (v6.2.0): HIDDEN-TAB IN-PLACE RETRY — with the MAIN-world
    // visibility shim, Naukri renders in background tabs; if the first
    // reveal still missed (late lazy-mount), scroll-kick the page (scroll
    // events fire fine in hidden tabs), wait for the contact UI to mount,
    // and run the reveal once more — WITHOUT stealing the user's focus.
    if (document.hidden && !mergedFinal.email && !mergedFinal.phone) {
      console.log(`[VHC v${VERSION}] BG tab + no contacts — in-place retry (shim path)`);
      updateProgress(56, 'Retrying contact reveal (background)...');
      try { await scrollToLoadContent(); } catch (_) {}
      const uiMounted = await waitForContactUI(4000);
      console.log(`[VHC v${VERSION}] Contact UI mounted after kick: ${uiMounted}`);
      const revealR = await clickViewContactButton();
      const emailsR = [...snapshotPageEmails()].filter(e => !beforeEmails.has(e));
      const diffR = { emails: emailsR, phones: revealR.revealedPhones };
      const cvDataR = (cvData.phone || (cvData.text && cvData.text.length > 800))
        ? cvData : await acquireCVData(domName, 8000);
      const mergedR = mergeContacts(cvDataR, diffR, domSelectorData, recruiterCreds, { emails: beforeEmails, phones: new Set() });
      if (mergedR.email || mergedR.phone) {
        mergedFinal = mergedR;
        console.log(`[VHC v${VERSION}] === AFTER IN-PLACE RETRY: email=${mergedFinal.email || 'NONE'}, phone=${mergedFinal.phone || 'NONE'} ===`);
      }
    }

    // Step 9.5 (v6.0.1, now last resort): flash-activate parachute —
    // should virtually never fire with the shim in place.
    if (document.hidden && !mergedFinal.email && !mergedFinal.phone) {
      console.log(`[VHC v${VERSION}] BG tab + no contacts — requesting visibility assist`);
      const assist = await new Promise((resolve) => {
        try {
          chrome.runtime.sendMessage({ action: 'visibilityAssist' }, (r) => {
            if (chrome.runtime.lastError) resolve({ granted: false });
            else resolve(r || { granted: false });
          });
        } catch (_) { resolve({ granted: false }); }
      });
      if (assist.granted) {
        updateProgress(58, 'Activating tab to load contacts...');
        // Wait until actually visible (max 5s), then let Naukri render
        await new Promise((resolve) => {
          if (!document.hidden) return resolve();
          const t = setTimeout(() => { document.removeEventListener('visibilitychange', onVis); resolve(); }, 5000);
          const onVis = () => {
            if (!document.hidden) { clearTimeout(t); document.removeEventListener('visibilitychange', onVis); resolve(); }
          };
          document.addEventListener('visibilitychange', onVis);
        });
        await sleep(1200);
        await scrollToLoadContent();
        const reveal2 = await clickViewContactButton();
        const newEmails2 = [...snapshotPageEmails()].filter(e => !beforeEmails.has(e));
        const diff2 = { emails: newEmails2, phones: reveal2.revealedPhones };
        const cvData2 = (cvData.phone || (cvData.text && cvData.text.length > 800))
          ? cvData : await acquireCVData(domName, 6000);
        mergedFinal = mergeContacts(cvData2, diff2, domSelectorData, recruiterCreds, { emails: beforeEmails, phones: new Set() });
        console.log(`[VHC v${VERSION}] === AFTER ASSIST: email=${mergedFinal.email || 'NONE'}, phone=${mergedFinal.phone || 'NONE'} ===`);
        try { chrome.runtime.sendMessage({ action: 'visibilityAssistDone' }); } catch (_) {}
      }
    }

    // Step 10: Capture raw text
    updateProgress(60, 'Capturing page text...');
    const rawText = getRawPageText();

    if (rawText.length < 100) {
      updateProgress(0, 'Error: page text too short');
      hideProgressBar(2000);
      return { success: false, error: 'Page text too short. Make sure profile is fully loaded.' };
    }

    const naukriId = extractNaukriProfileId();
    const cvDownloadUrl = extractNaukriCVUrl();
    const activeJob = await getActiveJob();

    // Build combined text (CV as primary, page text as secondary)
    let combinedText = '';
    if (cvData.text.length > 100) {
      combinedText += '=== CANDIDATE CV/RESUME (PRIMARY SOURCE - most reliable) ===\n';
      combinedText += cvData.text.substring(0, 8000);
      if (cvData.sections && cvData.sections.linkedin) {
        combinedText += `\nLinkedIn: ${cvData.sections.linkedin}`;
      }
      combinedText += '\n\n=== NAUKRI PROFILE PAGE TEXT (secondary source) ===\n';
      combinedText += rawText.substring(0, 7000);
    } else {
      combinedText = rawText.substring(0, 15000);
    }

    // Step 11: Enqueue to background worker — INSTANT return, no blocking AI wait
    updateProgress(80, 'Adding to queue...');

    const enqueuePayload = {
      naukri_profile_id:    naukriId,
      naukri_profile_url:   window.location.href,
      page_title:           stableTitle,
      name:                 domName || null,
      email:                mergedFinal.email || null,
      phone:                mergedFinal.phone || null,
      raw_text:             combinedText.substring(0, 15000),
      cv_download_url:      cvDownloadUrl || null,
      recruiter_email:      recruiterCreds.email || null,
      recruiter_phone:      recruiterCreds.phone || null,
      scraped_at:           new Date().toISOString(),
      extension_version:    VERSION,
      source_platform:      'naukri',
      active_job_id:        activeJob?.job_id || null,
      active_job_title:     activeJob?.job_title || null,
      // ── 3-LAYER DOM fields (Layer 1) ──
      dom_fields:           domFields._dom_scraped ? domFields : null,
    };

    try {
      const result = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(
          { action: 'enqueueCapture', data: enqueuePayload },
          response => {
            if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
            else resolve(response);
          }
        );
      });

      lastCapturedUrl = window.location.href;

      if (result.action === 'duplicate') {
        updateProgress(100, `${domName || 'Profile'} already in queue`);
        hideProgressBar(3000);
        return { success: true, action: 'duplicate', name: domName };
      }

      updateProgress(100, `${domName || 'Profile'} queued (#${result.queued} in queue)`);
      if (activeJob?.job_title) {
        setTimeout(() => showToast(`📎 Will auto-shortlist to: ${activeJob.job_title}`, 'info'), 1500);
      }
      hideProgressBar(3500);
      return { success: true, action: 'queued', name: domName, queued: result.queued };

    } catch (enqueueError) {
      updateProgress(0, `Failed to queue: ${enqueueError.message}`);
      hideProgressBar(3000);
      return { success: false, error: enqueueError.message };
    }
  }

  async function manualCapture() {
    if (isCapturing) return { success: false, error: 'Capture in progress' };
    if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Refresh page' }; }
    isCapturing = true;
    console.log(`[VHC v${VERSION}] Manual capture triggered on platform: ${PLATFORM}`);
    try {
      if (PLATFORM === 'linkedin') return await performLinkedInCapture();
      if (PLATFORM === 'foundit')  return await performFounditCapture();
      return await performCapture(true);
    } catch (error) {
      if (error.message?.includes('Extension context invalidated')) handleInvalidContext();
      else showToast(`Error: ${error.message}`, 'error');
      return { success: false, error: error.message };
    } finally { isCapturing = false; }
  }

  async function autoCapture() {
    if (isCapturing || lastCapturedUrl === window.location.href) return;
    if (!isExtensionValid()) return;
    isCapturing = true;
    console.log(`[VHC v${VERSION}] Auto-capture starting on platform: ${PLATFORM}...`);
    try {
      if (PLATFORM === 'linkedin') await performLinkedInCapture();
      else if (PLATFORM === 'foundit')  await performFounditCapture();
      else await performCapture(false);
    } catch (e) {
      if (!e.message?.includes('Extension context')) console.error(`[VHC v${VERSION}]`, e);
    } finally { isCapturing = false; }
  }

  // ===================== MESSAGE LISTENER =====================
  try {
    if (isExtensionValid()) {
      chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        try {
          if (request.action === 'manualCapture') {
            // When the service worker forces a capture (background-tab / context-menu
            // flow), a stalled auto-capture in this hidden tab must not block us.
            // Chrome throttles timers in unfocused tabs, so autoCapture can hang on
            // timeouts. Override isCapturing + lastCapturedUrl for forced runs.
            if (request._forced) {
              isCapturing = false;
              lastCapturedUrl = null;
            }
            manualCapture().then(sendResponse).catch(e => sendResponse({ success: false, error: e.message }));
            return true;
          }
          if (request.action === 'bulkCapture')   {
            bulkCapture().then(sendResponse).catch(e => sendResponse({ success: false, error: e.message }));
            return true;
          }
          if (request.action === 'getPageInfo')   {
            sendResponse({
              url: window.location.href,
              isProfilePage: isProfilePage(),
              isSearchPage: isSearchPage(),
              platform: PLATFORM,
            });
            return true;
          }
          if (request.action === 'showEvaluation') {
            showEvaluationBanner(request.data);
            sendResponse({ success: true });
            return true;
          }
        } catch (e) {
          console.warn(`[VHC v${VERSION}] Error in onMessage handler:`, e.message);
          sendResponse({ success: false, error: e.message });
        }
      });
    }
  } catch (err) {
    console.error(`[VHC v${VERSION}] Failed to register message listener:`, err.message);
  }

  // ===================== UI =====================
  function addBulkCaptureButton() {
    const existing = document.getElementById('vhc-bulk-btn');
    if (existing) existing.remove();

    const btn = document.createElement('button');
    btn.id = 'vhc-bulk-btn';
    btn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
      Bulk Capture All
    `;
    btn.style.cssText = `
      position: fixed; bottom: 20px; right: 80px; z-index: 999999;
      background: linear-gradient(135deg, #7CB342, #558B2F);
      color: white; border: none; border-radius: 24px;
      padding: 10px 16px; font-size: 13px; font-weight: 600;
      cursor: pointer; box-shadow: 0 4px 14px rgba(124,179,66,0.45);
      display: flex; align-items: center; gap: 8px;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      transition: filter 0.2s, transform 0.1s;
    `;
    btn.onmouseenter = () => { btn.style.filter = 'brightness(1.1)'; };
    btn.onmouseleave = () => { btn.style.filter = ''; };

    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.innerHTML = `<span style="display:inline-block;width:14px;height:14px;border:2px solid #fff;border-radius:50%;border-top-color:transparent;animation:vhcSpin 0.8s linear infinite;"></span> Queuing...`;
      const result = await bulkCapture();
      btn.disabled = false;
      btn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
          <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
        </svg>
        Bulk Capture All
      `;
    });

    // Add spin keyframes
    if (!document.getElementById('vhc-bulk-style')) {
      const style = document.createElement('style');
      style.id = 'vhc-bulk-style';
      style.textContent = '@keyframes vhcSpin { to { transform: rotate(360deg); } }';
      document.head.appendChild(style);
    }

    document.body.appendChild(btn);
  }

  function addFloatingButton() {
    const existing = document.getElementById('vhc-floating-btn');
    if (existing) existing.remove();
    const btn = document.createElement('button');
    btn.id = 'vhc-floating-btn';
    btn.className = 'vhc-capture-btn';
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
    btn.title = `VHC AI Capture v${VERSION}`;
    btn.addEventListener('click', async () => { btn.classList.add('capturing'); await manualCapture(); btn.classList.remove('capturing'); });
    document.body.appendChild(btn);
  }

  // ===================== EVALUATION BANNER =====================
  function showEvaluationBanner(data) {
    // Remove any existing evaluation banner
    const existing = document.getElementById('vhc-eval-banner');
    if (existing) existing.remove();

    const { candidateName, verdict, criteria, summary, jobTitle } = data;
    if (!criteria || criteria.length === 0) return;

    const verdictConfig = {
      strong_match:    { label: 'Strong Match',    bg: '#f0fdf4', border: '#86efac', icon: '✓' },
      potential_match: { label: 'Potential Match',  bg: '#fefce8', border: '#fde047', icon: '~' },
      weak_match:      { label: 'Weak Match',       bg: '#fef2f2', border: '#fca5a5', icon: '✗' },
      unknown:         { label: 'Needs Review',     bg: '#f8fafc', border: '#cbd5e1', icon: '?' },
    };
    const v = verdictConfig[verdict] || verdictConfig.unknown;

    const colorStyles = {
      green:  { bg: '#f0fdf4', border: '#22c55e', dot: '#22c55e', text: '#15803d' },
      yellow: { bg: '#fefce8', border: '#eab308', dot: '#eab308', text: '#a16207' },
      red:    { bg: '#fef2f2', border: '#ef4444', dot: '#ef4444', text: '#b91c1c' },
    };

    let criteriaHTML = '';
    for (const c of criteria) {
      const cs = colorStyles[c.color] || colorStyles.yellow;
      criteriaHTML += `
        <div style="
          display: flex; align-items: flex-start; gap: 8px;
          padding: 6px 10px; margin: 3px 0; border-radius: 6px;
          background: ${cs.bg}; border-left: 3px solid ${cs.border};
          font-size: 12px; color: ${cs.text}; line-height: 1.4;
        ">
          <span style="
            width: 8px; height: 8px; border-radius: 50%;
            background: ${cs.dot}; flex-shrink: 0; margin-top: 4px;
          "></span>
          <span>${c.text}</span>
        </div>`;
    }

    const banner = document.createElement('div');
    banner.id = 'vhc-eval-banner';
    banner.innerHTML = `
      <div style="
        position: fixed; top: 16px; right: 16px; z-index: 2147483647;
        width: 380px; max-height: 80vh; overflow-y: auto;
        background: white; border-radius: 12px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.15), 0 0 0 1px rgba(0,0,0,0.05);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        animation: vhcEvalSlideIn 0.3s ease-out;
      ">
        <style>
          @keyframes vhcEvalSlideIn {
            from { opacity: 0; transform: translateX(20px); }
            to { opacity: 1; transform: translateX(0); }
          }
          @keyframes vhcEvalSlideOut {
            from { opacity: 1; transform: translateX(0); }
            to { opacity: 0; transform: translateX(20px); }
          }
        </style>

        <!-- Header -->
        <div style="
          padding: 14px 16px; display: flex; align-items: center; justify-content: space-between;
          background: ${v.bg}; border-bottom: 1px solid ${v.border};
          border-radius: 12px 12px 0 0;
        ">
          <div>
            <div style="font-size: 14px; font-weight: 700; color: #0f172a;">
              ${candidateName || 'Candidate'}
            </div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">
              vs ${jobTitle || 'Selected Mandate'}
            </div>
          </div>
          <div style="
            padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 700;
            background: ${v.border}; color: white; letter-spacing: 0.3px;
          ">${v.label}</div>
        </div>

        <!-- Score summary bar -->
        <div style="
          display: flex; gap: 0; padding: 0; background: #f8fafc;
          border-bottom: 1px solid #e2e8f0;
        ">
          <div style="flex: ${summary.green || 0}; height: 4px; background: #22c55e;"></div>
          <div style="flex: ${summary.yellow || 0}; height: 4px; background: #eab308;"></div>
          <div style="flex: ${summary.red || 0}; height: 4px; background: #ef4444;"></div>
        </div>

        <!-- Criteria list -->
        <div style="padding: 10px 12px; max-height: 350px; overflow-y: auto;">
          ${criteriaHTML}
        </div>

        <!-- Footer with counts -->
        <div style="
          padding: 8px 16px; display: flex; align-items: center; justify-content: space-between;
          background: #f8fafc; border-top: 1px solid #e2e8f0;
          border-radius: 0 0 12px 12px; font-size: 11px; color: #64748b;
        ">
          <div style="display: flex; gap: 12px;">
            <span style="color: #22c55e; font-weight: 600;">${summary.green || 0} match</span>
            <span style="color: #eab308; font-weight: 600;">${summary.yellow || 0} unsure</span>
            <span style="color: #ef4444; font-weight: 600;">${summary.red || 0} miss</span>
          </div>
          <button id="vhc-eval-close" style="
            background: none; border: 1px solid #cbd5e1; border-radius: 6px;
            padding: 3px 10px; font-size: 11px; color: #64748b; cursor: pointer;
          ">Dismiss</button>
        </div>
      </div>
    `;

    document.body.appendChild(banner);

    // Close button
    document.getElementById('vhc-eval-close').addEventListener('click', () => {
      const bannerEl = document.getElementById('vhc-eval-banner');
      if (bannerEl) {
        bannerEl.firstElementChild.style.animation = 'vhcEvalSlideOut 0.2s ease-in forwards';
        setTimeout(() => bannerEl.remove(), 250);
      }
    });

    // Auto-dismiss after 15 seconds
    setTimeout(() => {
      const bannerEl = document.getElementById('vhc-eval-banner');
      if (bannerEl) {
        bannerEl.firstElementChild.style.animation = 'vhcEvalSlideOut 0.2s ease-in forwards';
        setTimeout(() => bannerEl.remove(), 250);
      }
    }, 15000);
  }

  const identityCardStates = new WeakMap();
  const identityCardInfo = new WeakMap();
  const identityLinkHandlers = new WeakMap();
  const IDENTITY_RETRY_DELAYS = [1000, 2500, 6000, 12000];
  let identityScanTimer = null;
  let identityScanDue = 0;
  let cardObserver = null;

  function scheduleIdentityScan(delay = 300) {
    const due = Date.now() + delay;
    if (identityScanTimer && identityScanDue <= due) return;
    clearTimeout(identityScanTimer);
    identityScanDue = due;
    identityScanTimer = setTimeout(() => {
      identityScanTimer = null;
      identityScanDue = 0;
      checkAndMarkExistingProfiles();
    }, delay);
  }

  function identityFingerprint(card, info) {
    if (info) return JSON.stringify(info);
    return JSON.stringify([card.getAttribute('data-target-id') || '',
      (card.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 8000)]);
  }

  function clearIdentityBadge(card) {
    card.querySelectorAll('.vhc-existing-badge, .vhc-identity-status, .vhc-wrong-match-flag, .vhc-identity-alternative')
      .forEach(node => node.remove());
    card.classList.remove('vhc-dimmed-card');
    identityCardInfo.delete(card);
  }

  function invalidateIdentityCards() {
    for (const card of findCardElements()) {
      clearIdentityBadge(card);
      identityCardStates.delete(card);
    }
    scheduleIdentityScan(500);
  }

  // Capture and account changes can alter matching without a DOM change.
  // Clearing the state also makes in-flight replies for an old account stale.
  chrome.storage?.onChanged?.addListener((changes, area) => {
    if ((area === 'local' && changes.captureHistory) ||
        (area === 'sync' && (changes.vhc_user || changes.vhc_api_url ||
          (changes.vhc_token && !changes.vhc_token.newValue)))) invalidateIdentityCards();
  });

  function retryIdentityCard(card, state) {
    if (identityCardStates.get(card) !== state) return;
    state.status = 'retry';
    if (state.attempts > IDENTITY_RETRY_DELAYS.length) {
      state.status = 'exhausted';
      return;
    }
    const delay = IDENTITY_RETRY_DELAYS[state.attempts - 1];
    state.nextAttemptAt = Date.now() + delay;
    scheduleIdentityScan(delay);
  }

  async function checkAndMarkExistingProfiles() {
    if (!isExtensionValid()) return;
    const pending = [];
    for (const card of findCardElements()) {
      const info = scrapeSearchCardInfo(card);
      const fingerprint = identityFingerprint(card, info);
      let state = identityCardStates.get(card);
      if (state?.fingerprint === fingerprint) {
        if (['pending', 'done', 'exhausted'].includes(state.status)) continue;
        if (state.nextAttemptAt > Date.now()) {
          scheduleIdentityScan(state.nextAttemptAt - Date.now());
          continue;
        }
      } else {
        clearIdentityBadge(card);
        state = { fingerprint, attempts: 0, status: 'new' };
        identityCardStates.set(card, state);
      }
      state.attempts++;
      if (!info || !info.name || info.name === 'Unknown') {
        retryIdentityCard(card, state);
        continue;
      }
      state.status = 'pending';
      pending.push({ card, info, state });
    }
    if (!pending.length) return;
    let response = null;
    try {
      response = await new Promise(resolve => {
        let settled = false;
        const finish = value => {
          if (settled) return;
          settled = true;
          clearTimeout(timeout);
          resolve(value);
        };
        const timeout = setTimeout(() => finish(null), 60000);
        try {
          chrome.runtime.sendMessage({
            action: 'checkExisting',
            candidates: pending.map(({ info }) => ({
              name: info.name, naukri_id: info.naukri_id || null,
              source: info.source, source_id_kind: info.source_id_kind,
              headline: info.headline || '', location: info.location || '',
              profile_url: info.profileUrl,
              current_employer: info.current_employer || null,
              designation: info.designation || null,
              experience_years: info.experience_years ?? null,
              annual_ctc: info.annual_ctc ?? null,
              skills: info.skills || null, education: info.education || null,
              experience: (info.experience || []).slice(0, 5).map(({ company, title, location }) => ({
                company, title, ...(location ? { location } : {}),
              })),
              education_details: (info.education_details || []).slice(0, 3),
            })),
          }, result => finish(chrome.runtime.lastError ? null : result));
        } catch (_) { finish(null); }
      });
    } catch (_) { /* Missing response becomes a bounded retry below. */ }
    const results = new Map();
    const duplicateIndices = new Set();
    if (Array.isArray(response?.results)) {
      for (const result of response.results) {
        if (!result || !Number.isInteger(result.index)) continue;
        if (results.has(result.index)) duplicateIndices.add(result.index);
        results.set(result.index, result);
      }
    }
    pending.forEach(({ card, info, state }, index) => {
      if (card.isConnected === false || identityCardStates.get(card) !== state) return;
      // A virtualized list may reuse the element while the request is in flight.
      if (identityFingerprint(card, scrapeSearchCardInfo(card)) !== state.fingerprint) {
        clearIdentityBadge(card);
        identityCardStates.delete(card);
        scheduleIdentityScan();
        return;
      }
      const result = !duplicateIndices.has(index) && results.get(index);
      clearIdentityBadge(card);
      if (!result || !result.decision || response?.matcher_version !== 'identity-resolution-1' ||
          (result.decision === 'confirmed_duplicate' && result.exists !== true)) {
        markCardAsExisting(card, { ...info, decision: 'unavailable' });
        retryIdentityCard(card, state);
        return;
      }
      markCardAsExisting(card, {
        ...info, ...result,
        candidate_id: result.candidate_id || result.top_match?.candidate_id,
        audit_id: result.audit_id || response.audit_id || null,
        card_idx: result.audit_index ?? index,
      });
      const retryableRetrievalIssue = Array.isArray(result.reason_codes) &&
        result.reason_codes.some(code => typeof code === 'string' &&
          (code.startsWith('query_failed:') || code === 'inconsistent_candidate_snapshot'));
      if ((result.decision === 'unavailable' || result.service_status === 'unavailable' ||
           retryableRetrievalIssue) && result.service_status !== 'disabled') retryIdentityCard(card, state);
      else state.status = 'done';
    });
  }

  /**
   * Helper to find candidate card elements on search results page.
   */
  function findCardElements() {
    const cardSelectors = [
      '.tuple-card',                  // Naukri Resdex current (Feb 2026)
      '[class*="tuple-card"]',
      '[class*="candidateCard"]',
      '[class*="candidate-card"]',
      '[class*="resumeCard"]',
      '[class*="srp-tuple"]',
      '[class*="srpTuple"]',
      '[data-target-id]',
      '.tupleCard',
    ];

    let cards = [];
    for (const sel of cardSelectors) {
      cards = Array.from(document.querySelectorAll(sel));
      if (cards.length > 0) break;
    }
    return cards;
  }

  /**
   * Scrapes profile card info to prepare search check.
   * Extracts every visible signal from the Naukri tuple-card so the
   * backend can multi-signal verify identity (name alone is not enough).
   */
  function scrapeSearchCardInfo(cardEl) {
    try {
      // ── Profile URL + name ──
      const linkEl = cardEl.querySelector(
        'a.candidate-name, a.candidate-profile-summary, ' +
        'a[href*="preview"], a[href*="profile"], a[href*="resume"], a[href*="resdex"]'
      );
      const profileUrl = linkEl ? linkEl.href : null;
      if (!profileUrl || profileUrl.length > 2048) return null;

      const boundedText = (value, maximum) => {
        const text = cleanText(value || '');
        return text && text.length <= maximum ? text : null;
      };
      // Only an explicitly separated role and company are structured. Keep
      // multiword company names intact and reject another field's label.
      const employmentPair = value => {
        const match = cleanText(value || '').match(/^(.+?)\s+at\s+(.+)$/i);
        if (!match) return null;
        const title = boundedText(match[1], 500);
        const company = boundedText(match[2], 500);
        if (!title || !company || title.includes(':') ||
            /(?:\S+@\S+\.\S+|https?:\/\/)/i.test(title + ' ' + company)) return null;
        return { title, company };
      };

      // Preserve identifier provenance. Generic checkbox values, pid and sid
      // often identify a session or UI item and cannot prove person identity.
      const source = PLATFORM === 'linkedin' ? 'linkedin' : 'naukri';
      let naukri_id = null;
      let source_id_kind = 'unverified';
      if (source === 'naukri' && cardEl.getAttribute('data-target-id')) {
        naukri_id = cardEl.getAttribute('data-target-id');
        source_id_kind = 'data-target-id';
      }
      if (naukri_id && naukri_id.length > 256) {
        naukri_id = null;
        source_id_kind = 'unverified';
      }

      const nameEl = cardEl.querySelector(
        'a.candidate-name, [class*="candidateName"], [class*="candidate-name"], ' +
        '[class*="name"], h2, h3, [class*="title"]:first-of-type'
      );
      const name = cleanText(nameEl?.innerText) || 'Unknown';
      if (name.length > 300) return null;

      // ── Headline (Naukri's "candidate-profile-summary" e.g. "R&D Engineer with B.Tech in Pune") ──
      const headlineEl = cardEl.querySelector(
        '.candidate-profile-summary, [class*="candidate-headline"], ' +
        '[class*="headline"], [class*="designation"], [class*="currentTitle"]'
      );
      const headline = boundedText(headlineEl?.innerText, 2000);

      // ── Location ──
      const locEl = cardEl.querySelector(
        'span.location, [class*="location"], [class*="loc"], [class*="city"]'
      );
      const location = boundedText(locEl?.innerText, 300);

      // ── Current employer ──
      // Naukri renders this inside #currentEmp > .employment-detail
      // as `<button title="Find candidates from <Company>">`.
      let current_employer = null;
      let designation = null;
      const empWrap = cardEl.querySelector('#currentEmp, [class*="currentEmp"]');
      if (empWrap) {
        // Designation button has title="Find candidates who are currently <Designation>"
        const desigBtn = empWrap.querySelector('button[title*="currently "]');
        if (desigBtn) {
          const m = desigBtn.getAttribute('title').match(/currently\s+(.+)/i);
          if (m) designation = boundedText(m[1], 500);
        }
        // Company button has title="Find candidates from <Company>"
        const compBtn = empWrap.querySelector('button[title*="from "]');
        if (compBtn) {
          const m = compBtn.getAttribute('title').match(/from\s+(.+)/i);
          if (m) current_employer = boundedText(m[1], 500);
        }
        if (!current_employer) {
          // Preserve line boundaries so a date or the next field cannot become
          // part of a company. The old lazy regex captured only its first word.
          const lines = (empWrap.innerText || '').split(/\r?\n/).map(cleanText).filter(Boolean);
          const pair = lines.map(employmentPair).find(Boolean);
          if (pair) {
            if (!designation) designation = pair.title;
            current_employer = pair.company;
          }
        }
      }

      // No unverified previous-employer selectors or whole-page scrape. Accept
      // only explicitly labelled visible lines inside this particular card.
      const experience = [];
      const seenEmployment = new Set();
      const cardLines = (cardEl.innerText || '').split(/\r?\n/).slice(0, 200).map(cleanText).filter(Boolean);
      for (let i = 0; i < cardLines.length && experience.length < 5; i++) {
        const label = cardLines[i].match(/^(?:previous(?: employment| experience)?|past employment)\s*:\s*(.*)$/i);
        const heading = /^(?:previous employment|previous experience|past employment)$/i.test(cardLines[i]);
        if (!label && !heading) continue;
        const pair = employmentPair(label?.[1] || cardLines[i + 1]);
        if (!pair) continue;
        const key = (pair.title + '|' + pair.company).toLowerCase();
        if (seenEmployment.has(key)) continue;
        seenEmployment.add(key);
        experience.push({ ...pair, relationship: 'previous' });
      }

      // ── Experience (parse "2y 7m" from meta-data title="Experience") ──
      let experience_years = null;
      const expEl = cardEl.querySelector('[title="Experience"] + span, .meta-data span[title*="y "]');
      const expText = cleanText(expEl?.innerText || cardEl.querySelector('.meta-data span[title*="y "]')?.getAttribute('title') || '');
      if (expText) {
        const ym = expText.match(/(\d+)\s*y(?:ears?)?(?:\s*(\d+)\s*m(?:onths?)?)?/i);
        if (ym) {
          const yrs = parseInt(ym[1], 10);
          const mos = ym[2] ? parseInt(ym[2], 10) : 0;
          experience_years = +(yrs + mos / 12).toFixed(2);
          if (experience_years > 80 || mos > 11) experience_years = null;
        }
      }

      // ── Annual CTC (parse "₹ 4.20 Lacs" from meta-data title="Annual salary") ──
      let annual_ctc = null;
      const ctcEl = cardEl.querySelector('[title="Annual salary"] + span, .meta-data span[title*="Lacs"], .meta-data span[title*="₹"]');
      const ctcText = cleanText(ctcEl?.getAttribute?.('title') || ctcEl?.innerText || '');
      if (ctcText) {
        // "₹ 4.20 Lacs" → 420000;  "₹ 12.5 Lacs" → 1250000
        const m = ctcText.match(/([\d.]+)\s*lacs?/i);
        if (m) annual_ctc = Math.round(parseFloat(m[1]) * 100000);
        else {
          const m2 = ctcText.match(/([\d.]+)\s*cr/i);
          if (m2) annual_ctc = Math.round(parseFloat(m2[1]) * 10000000);
        }
      }

      if (annual_ctc !== null && (!Number.isFinite(annual_ctc) || annual_ctc < 0)) annual_ctc = null;

      // ── Skills (key-skills section: each .cand-skill button) ──
      let skills = null;
      const skillBtns = cardEl.querySelectorAll('.key-skills .cand-skill button, .candidate-skills [class*="skill"] button');
      if (skillBtns.length) {
        skills = Array.from(skillBtns)
          .map(b => cleanText(b.innerText || b.getAttribute('title') || ''))
          .map(s => s.replace(/^find candidates with keyword\s+/i, '').trim())
          .filter(s => s && s.length < 50)
          .slice(0, 15);
        if (!skills.length) skills = null;
      }

      // ── Education ("B.Tech / B.E. Dr Babasaheb Ambedkar... 2023") ──
      let education = null;
      const education_details = [];
      const eduEl = cardEl.querySelector('#education, [id*="education"], .education');
      if (eduEl) {
        const rawEducation = eduEl.getAttribute('title') || eduEl.innerText || '';
        education = boundedText(rawEducation, 2000);
        // Unlabelled degree/institution strings remain raw. Only explicit labels
        // justify splitting a credential into fields; dates are never guessed.
        let detail = {};
        const appendDetail = () => {
          if (Object.keys(detail).length && education_details.length < 3) education_details.push(detail);
          detail = {};
        };
        for (const line of rawEducation.split(/\r?\n|[;|]/).slice(0, 30)) {
          const match = cleanText(line).match(/^(degree|qualification|course|institution|institute|university|college|graduation(?: year)?|year of graduation)\s*:\s*(.+)$/i);
          if (!match) continue;
          const label = match[1].toLowerCase();
          const field = /^(degree|qualification|course)$/.test(label) ? 'degree'
            : /^(graduation|year of graduation)/.test(label) ? 'graduation_year' : 'institution';
          const value = field === 'graduation_year'
            ? (/^(19|20)\d{2}$/.test(match[2]) ? Number(match[2]) : null)
            : boundedText(match[2], field === 'degree' ? 300 : 500);
          if (value === null) continue;
          if (detail[field] !== undefined && detail[field] !== value) appendDetail();
          detail[field] = value;
        }
        appendDetail();
      }

      return {
        profileUrl, naukri_id, source, source_id_kind, name, headline, location,
        current_employer, designation,
        experience_years, annual_ctc,
        skills, education, experience, education_details,
      };
    } catch (_) {
      return null;
    }
  }

  function safeIdentityLink(value) {
    try {
      const url = new URL(value);
      return /^https?:$/.test(url.protocol) ? url.href : null;
    } catch (_) { return null; }
  }

  function markCardAsExisting(cardEl, info) {
    if (!cardEl || info.decision === 'no_match_found' || info.service_status === 'disabled') return;
    const confirmed = info.decision === 'confirmed_duplicate' && info.exists === true;
    const labels = {
      confirmed_duplicate: 'Already in database',
      probable_match: 'Possible database match',
      ambiguous: 'Multiple possible matches',
      conflicting_records: 'Conflicting profile details',
      insufficient_data: 'Not enough profile details',
      unavailable: 'Database check unavailable',
    };
    const label = labels[info.decision];
    if (!label) return;
    const nameEl = cardEl.querySelector(
      '[class*="name"], [class*="candidateName"], h2, h3, [class*="title"]:first-of-type'
    );
    if (!nameEl?.parentNode) return;
    const badge = document.createElement(info.candidate_id ? 'a' : 'span');
    // The hover preview binds only to .vhc-existing-badge and needs a real ID.
    badge.className = info.candidate_id ? 'vhc-existing-badge' : 'vhc-identity-status';
    badge.classList.add(confirmed ? 'vhc-confidence-high'
      : ['probable_match', 'ambiguous', 'conflicting_records'].includes(info.decision)
        ? 'vhc-confidence-medium' : 'vhc-confidence-unavailable');
    badge.innerText = label;
    const signals = Array.isArray(info.matched_signals) ? info.matched_signals.join(', ') : '';
    const conflicts = Array.isArray(info.conflicts) ? info.conflicts.join(', ') : '';
    const context = info.top_match?.context || {};
    const contextList = (value, limit = 3) => Array.isArray(value)
      ? value.filter(item => typeof item === 'string' && item.trim()).slice(0, limit).join(', ')
      : '';
    const contextSummary = [
      context.employer && `employer: ${context.employer}`,
      context.designation && `title: ${context.designation}`,
      context.location && `location: ${context.location}`,
      context.work_history?.length && `history: ${contextList(context.work_history)}`,
      context.education?.length && `education: ${contextList(context.education)}`,
      context.certifications?.length && `certifications: ${contextList(context.certifications)}`,
      context.projects?.length && `projects: ${contextList(context.projects)}`,
      context.languages?.length && `languages: ${contextList(context.languages)}`,
      context.skills?.length && `skills: ${contextList(context.skills)}`,
      context.experience_years != null && `experience: ${context.experience_years}y`,
    ].filter(Boolean).join(' · ');
    badge.title = label + (signals ? ' — Matching fields: ' + signals : '') +
      (conflicts ? ' — Conflicts: ' + conflicts : '') +
      (contextSummary ? ' — Database context: ' + contextSummary : '');
    if (info.candidate_id) {
      badge.dataset.vhcCandidateId = String(info.candidate_id);
      badge.target = '_blank';
      badge.rel = 'noopener noreferrer';
      badge.href = safeIdentityLink(info.profile_url || info.top_match?.profile_url) || '#';
      if (badge.getAttribute('href') === '#') {
        chrome.runtime.sendMessage(
          { action: 'getCandidateBankUrl', candidate_id: info.candidate_id },
          result => {
            if (chrome.runtime.lastError) return;
            const url = safeIdentityLink(result?.url);
            if (url) badge.href = url;
          }
        );
      }
      badge.addEventListener('click', event => {
        event.stopPropagation();
        // Preserve the existing badge-open activity tracking.
        try {
          chrome.runtime.sendMessage({
            action: 'trackCandidateCalled',
            candidate_id: info.candidate_id,
            source: 'badge_expand',
            candidate_name: info.name || null,
            naukri_id: info.naukri_id || null,
            page_url: window.location.href,
          });
        } catch (_) { /* telemetry must stay silent */ }
        if (badge.getAttribute('href') === '#') {
          event.preventDefault();
          chrome.runtime.sendMessage({ action: 'openCandidateProfile', candidate_id: info.candidate_id });
        }
      });
    }
    nameEl.parentNode.insertBefore(badge, nameEl.nextSibling);

    if (info.decision === 'ambiguous' && info.second_match?.candidate_id) {
      const alternative = document.createElement('a');
      alternative.className = 'vhc-identity-alternative';
      alternative.textContent = 'Other possible match';
      alternative.href = safeIdentityLink(info.second_match.profile_url) || '#';
      alternative.target = '_blank';
      alternative.rel = 'noopener noreferrer';
      alternative.addEventListener('click', event => {
        event.stopPropagation();
        if (alternative.getAttribute('href') === '#') {
          event.preventDefault();
          chrome.runtime.sendMessage({
            action: 'openCandidateProfile', candidate_id: info.second_match.candidate_id,
          });
        }
      });
      badge.parentNode.insertBefore(alternative, badge.nextSibling);
    }

    if (info.candidate_id && info.audit_id && info.provenance === 'backend') {
      const flag = document.createElement('a');
      flag.className = 'vhc-wrong-match-flag';
      flag.href = '#';
      flag.textContent = 'Wrong match?';
      flag.title = 'Report this suggestion for review.';
      flag.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        if (flag.dataset.vhcFlagged) return;
        flag.dataset.vhcFlagged = '1';
        flag.textContent = 'Sending…';
        chrome.runtime.sendMessage({
          action: 'reportWrongMatch', audit_id: info.audit_id, card_idx: info.card_idx,
          badge_candidate_id: info.candidate_id, card_name: info.name || null,
          card_headline: info.headline || null, card_employer: info.current_employer || null,
          card_location: info.location || null, page_url: window.location.href,
        }, response => {
          if (chrome.runtime.lastError || !response?.ok) {
            delete flag.dataset.vhcFlagged;
            flag.textContent = 'Report failed — retry';
            return;
          }
          flag.textContent = 'Reported';
          badge.innerText = 'Match flagged for review';
          badge.classList.remove('vhc-confidence-high');
          badge.classList.add('vhc-confidence-medium');
          cardEl.classList.remove('vhc-dimmed-card');
          identityCardInfo.delete(cardEl);
        });
      });
      badge.parentNode.insertBefore(flag, badge.nextSibling);
    }
    if (confirmed) {
      cardEl.classList.add('vhc-dimmed-card');
      identityCardInfo.set(cardEl, info);
      injectClickInterceptor(cardEl);
    }
  }

  // Listeners read the current card decision so a recycled card or a failed
  // recheck cannot retain an old duplicate confirmation dialog.
  function injectClickInterceptor(cardEl) {
    const links = cardEl.querySelectorAll('a[href*="profile"], a[href*="resume"], a[href*="preview"], a[href*="resdex"]');
    for (const link of links) {
      if (link.classList.contains('vhc-existing-badge') || identityLinkHandlers.has(link)) continue;
      const handler = event => {
        const info = identityCardInfo.get(cardEl);
        if (!info || (event.type === 'auxclick' && event.button !== 1)) return;
        const state = identityCardStates.get(cardEl);
        if (!state || identityFingerprint(cardEl, scrapeSearchCardInfo(cardEl)) !== state.fingerprint) {
          clearIdentityBadge(cardEl);
          scheduleIdentityScan();
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        showExistingConfirmDialog(info, () => {
          if (event.type === 'auxclick' || event.ctrlKey || event.metaKey || link.target === '_blank') {
            window.open(link.href, '_blank', 'noopener');
          } else {
            window.location.href = link.href;
          }
        });
      };
      identityLinkHandlers.set(link, handler);
      link.addEventListener('click', handler, true);
      link.addEventListener('auxclick', handler, true);
    }
  }

  /**
   * Renders a premium, glassmorphic modal confirmation dialog.
   */
  function showExistingConfirmDialog(info, onConfirm) {
    const existingModal = document.getElementById('vhc-confirm-modal-root');
    if (existingModal) existingModal.remove();

    const modalRoot = document.createElement('div');
    modalRoot.id = 'vhc-confirm-modal-root';
    
    const dateStr = info.captured_at 
      ? new Date(info.captured_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
      : 'recently';

    modalRoot.innerHTML = `
      <div class="vhc-modal-overlay">
        <div class="vhc-modal-container">
          <div class="vhc-modal-header">
            <div class="vhc-modal-icon-container">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="vhc-modal-icon"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
            </div>
            <h3>Profile Already Saved</h3>
          </div>
          <div class="vhc-modal-body">
            <p><strong>${escapeHTML(info.name)}</strong> was already captured in your VHC database on <strong>${escapeHTML(dateStr)}</strong>.</p>
            <p class="vhc-modal-desc">Opening this profile again might count against your limited Naukri views. Are you sure you want to view it?</p>
          </div>
          <div class="vhc-modal-footer">
            <button id="vhc-modal-btn-cancel" class="vhc-btn vhc-btn-secondary">No, Skip Profile</button>
            <button id="vhc-modal-btn-confirm" class="vhc-btn vhc-btn-primary">Yes, Open Anyway</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modalRoot);
    
    setTimeout(() => {
      const overlay = modalRoot.querySelector('.vhc-modal-overlay');
      if (overlay) overlay.classList.add('vhc-modal-visible');
    }, 10);

    const closeModal = () => {
      const overlay = modalRoot.querySelector('.vhc-modal-overlay');
      if (overlay) overlay.classList.remove('vhc-modal-visible');
      setTimeout(() => modalRoot.remove(), 300);
    };

    modalRoot.querySelector('#vhc-modal-btn-cancel').addEventListener('click', () => {
      closeModal();
    });

    modalRoot.querySelector('#vhc-modal-btn-confirm').addEventListener('click', () => {
      closeModal();
      onConfirm();
    });

    modalRoot.querySelector('.vhc-modal-overlay').addEventListener('click', (e) => {
      if (e.target.classList.contains('vhc-modal-overlay')) {
        closeModal();
      }
    });
  }

  /**
   * Sets up MutationObserver to catch infinite scroll lazy card loads.
   */
  function observeNewCards() {
    if (cardObserver) return;
    
    console.log(`[VHC v${VERSION}] Setting up MutationObserver for new candidate cards...`);
    
    const cardSelector = '.tuple-card, [class*="tuple-card"], [class*="candidateCard"], ' +
      '[class*="candidate-card"], [class*="resumeCard"], [class*="srp-tuple"], ' +
      '[class*="srpTuple"], .tupleCard, [data-target-id]';
    cardObserver = new MutationObserver(mutations => {
      for (const mutation of mutations) {
        const element = mutation.target.nodeType === Node.ELEMENT_NODE
          ? mutation.target : mutation.target.parentElement;
        if (element?.closest?.('.vhc-existing-badge, .vhc-identity-status, .vhc-wrong-match-flag, .vhc-identity-alternative')) continue;
        // Observe changes inside existing cards as well as newly inserted cards.
        // This catches lazy names and virtualized list elements being reused.
        if (element?.closest?.(cardSelector) ||
            Array.from(mutation.addedNodes || []).some(node =>
              node.nodeType === Node.ELEMENT_NODE &&
              (node.matches?.(cardSelector) || node.querySelector?.(cardSelector)))) {
          scheduleIdentityScan();
          break;
        }
      }
    });
    cardObserver.observe(document.body, {
      childList: true, subtree: true, characterData: true, attributes: true,
      attributeFilter: ['href', 'data-target-id', 'data-candidate-id', 'data-profile-id', 'title'],
    });
    scheduleIdentityScan(500);
  }

  function showToast(message, type = 'info') {
    const existing = document.getElementById('vhc-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.id = 'vhc-toast';
    toast.className = `vhc-toast vhc-toast-${type}`;
    toast.innerHTML = `<div class="vhc-toast-content"><span>${message}</span></div>`;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('vhc-toast-show'), 10);
    setTimeout(() => { toast.classList.remove('vhc-toast-show'); setTimeout(() => toast.remove(), 300); }, CONFIG.TOAST_DURATION);
  }

  async function getSettings() {
    if (!isExtensionValid()) return { enabled: true, showNotifications: true, autoCapture: true };
    try { return await new Promise((res, rej) => chrome.storage.sync.get({ enabled: true, showNotifications: true, autoCapture: true }, r => chrome.runtime.lastError ? rej(chrome.runtime.lastError) : res(r))); }
    catch (e) { return { enabled: true, showNotifications: true, autoCapture: true }; }
  }

  async function getAuthToken() {
    if (!isExtensionValid()) { handleInvalidContext(); return null; }
    try { return await new Promise((res, rej) => chrome.storage.sync.get(['vhc_token', 'vhc_api_url'], r => chrome.runtime.lastError ? rej(chrome.runtime.lastError) : res(r.vhc_token && r.vhc_api_url ? { token: r.vhc_token, apiUrl: r.vhc_api_url } : null))); }
    catch (e) { handleInvalidContext(); return null; }
  }

  // ===================== INIT =====================
  async function init() {
    console.log(`[VHC v${VERSION}] Initializing on ${PLATFORM || 'unknown'} platform...`);

    if (!PLATFORM) {
      console.log(`[VHC v${VERSION}] Unsupported platform — not initializing`);
      return;
    }

    addFloatingButton();
    const settings = await getSettings();
    if (!settings.enabled) return;
    const auth = await getAuthToken();
    if (!auth) { console.log(`[VHC v${VERSION}] Not authenticated`); return; }

    // Skip Naukri pages we explicitly do NOT want to operate on
    // (e.g. /v3/simcv — "Recruiters also viewed" / similar-CV suggestion view).
    // The page mounts a focal candidate top card alongside a list of 195+
    // suggested profiles, which causes the extension to grab the wrong person.
    if (PLATFORM === 'naukri' && isExcludedNaukriPage()) {
      console.log(`[VHC v${VERSION}] Excluded Naukri page (${window.location.pathname}) — extension idle (no auto-capture, no bulk button)`);
      return;
    }

    if (PLATFORM !== 'naukri') {
      // LinkedIn and Foundit: just show floating button + auto-capture on profile pages
      if (isProfilePage() && settings.autoCapture) {
        if (document.readyState !== 'complete') await new Promise(r => window.addEventListener('load', r));
        setTimeout(() => autoCapture(), CONFIG.CAPTURE_DELAY);
      }
      return;
    }

    // Naukri-specific: search page bulk button + profile page auto-capture
    //
    // ORDER MATTERS — Naukri's new ResDex preview overlay leaves the
    // underlying search-results DOM mounted behind the open profile, so
    // `isSearchPage()` returns true *even when a profile preview is open*.
    // We must check `isProfilePage()` first; only fall back to the search
    // branch if no profile is currently in view.
    if (isProfilePage()) {
      console.log(`[VHC v${VERSION}] Profile preview detected on Naukri — scheduling auto-capture`);
      if (document.readyState !== 'complete') await new Promise(r => window.addEventListener('load', r));
      if (settings.autoCapture) {
        setTimeout(() => autoCapture(), CONFIG.CAPTURE_DELAY);
      }
      // Also keep the bulk badge logic alive on the same page (results
      // are still rendered behind the preview overlay)
      if (isSearchPage()) {
        addBulkCaptureButton();
        checkAndMarkExistingProfiles();
        observeNewCards();
      }
      return;
    }

    if (isSearchPage()) {
      console.log(`[VHC v${VERSION}] Search/list page detected — bulk capture ready`);
      addBulkCaptureButton();

      // RUN CHECK AND MARK EXISTING PROFILES ON SEARCH PAGES
      checkAndMarkExistingProfiles();
      observeNewCards();
      return;
    }

    console.log(`[VHC v${VERSION}] Not a profile page`);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

})();
