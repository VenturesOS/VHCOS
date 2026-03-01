/**
 * VHC Talent OS - Naukri Resdex Profile Scraper v3.8.2
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

  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  const VERSION = '4.5.0';
  const CONFIG = {
    CAPTURE_DELAY: 2000,
    SCROLL_DELAY: 150,
    TOAST_DURATION: 5000,
    BULK_SCROLL_DELAY: 600,     // wait per scroll step when loading list pages
    BULK_MAX_CANDIDATES: 100,   // cap per bulk sweep
  };

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

      // Clean up any lingering UI from previous page capture
      const oldBar = document.getElementById('vhc-progress-bar');
      if (oldBar) oldBar.remove();
      const oldToast = document.getElementById('vhc-toast');
      if (oldToast) oldToast.remove();
      isCapturing = false; // Reset in case previous capture was mid-flight

      // Re-trigger auto-capture if navigated to a profile page
      if (isProfilePage() && !isCapturing) {
        getSettings().then(settings => {
          if (settings.enabled && settings.autoCapture) {
            console.log(`[VHC v${VERSION}] Navigated to profile page, scheduling auto-capture`);
            setTimeout(() => autoCapture(), CONFIG.CAPTURE_DELAY);
          }
        });
      }

      // Show bulk button if navigated to a search/list page
      if (isSearchPage()) {
        getAuthToken().then(auth => {
          if (auth) {
            console.log(`[VHC v${VERSION}] Navigated to search page, showing bulk capture button`);
            setTimeout(() => addBulkCaptureButton(), 1500);
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
    const title = document.title || '';
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
      // Poll for a NEW phone to appear in candidate root (max 4s, check every 300ms)
      const revealedPhones = await new Promise((resolve) => {
        let attempts = 0;
        const maxAttempts = 14; // 4.2s max
        const interval = setInterval(() => {
          attempts++;
          const phonesAfter = snapshotPhonesInRoot();
          const newPhones = diffPhoneSets(phonesBeforeClick, phonesAfter);
          if (newPhones.length > 0) {
            clearInterval(interval);
            console.log(`[VHC v${VERSION}] ✅ New phone revealed after ${attempts * 300}ms: [${newPhones.join(', ')}]`);
            resolve(newPhones);
          } else if (attempts >= maxAttempts) {
            clearInterval(interval);
            console.log(`[VHC v${VERSION}] Timeout — no new phone appeared after click`);
            resolve([]);
          }
        }, 300);
      });
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
   */
  function scanCVIframe(candidateName) {
    const result = { email: null, phone: null, text: '', isValid: false, sections: {} };

    try {
      // Find the CV iframe
      const iframeEl = document.querySelector('iframe#cv-iframe') ||
                       document.querySelector('iframe[name="cv-iframe"]') ||
                       document.querySelector('#cv-iframe iframe') ||
                       document.querySelector('.iframe-cv-iframe iframe') ||
                       document.querySelector('iframe[src*="cv/view"]');

      if (!iframeEl) {
        console.log(`[VHC v${VERSION}] CV iframe not found`);
        return result;
      }

      // Access iframe content
      let iframeDoc;
      try {
        iframeDoc = iframeEl.contentDocument || iframeEl.contentWindow?.document;
      } catch (e) {
        console.warn(`[VHC v${VERSION}] Cannot access CV iframe (cross-origin?):`, e.message);
        return result;
      }

      if (!iframeDoc || !iframeDoc.body) {
        console.log(`[VHC v${VERSION}] CV iframe document empty`);
        return result;
      }

      const cvText = iframeDoc.body.innerText || iframeDoc.body.textContent || '';
      result.text = cvText.substring(0, 12000);
      console.log(`[VHC v${VERSION}] CV iframe text: ${cvText.length} chars`);

      if (cvText.length < 50) {
        console.log(`[VHC v${VERSION}] CV text too short, likely not loaded`);
        return result;
      }

      // Sanity check: does CV contain the candidate's name?
      if (candidateName) {
        const nameParts = candidateName.split(/\s+/).filter(w => w.length > 2);
        const nameFound = nameParts.some(part =>
          cvText.toLowerCase().includes(part.toLowerCase())
        );
        if (!nameFound) {
          console.warn(`[VHC v${VERSION}] CV does NOT contain candidate name "${candidateName}". May be a bad upload. Ignoring CV contacts.`);
          result.text = cvText.substring(0, 12000);
          return result;
        }
        result.isValid = true;
        console.log(`[VHC v${VERSION}] CV sanity check PASSED: contains name "${candidateName}"`);
      } else {
        result.isValid = true;
      }

      // ===== DEEP EXTRACTION FROM CV =====

      // Extract emails
      const cvEmails = cvText.match(EMAIL_REGEX) || [];
      for (const e of cvEmails) {
        const lower = e.toLowerCase().trim();
        if (!isNaukriSystemEmail(lower)) {
          result.email = lower;
          console.log(`[VHC v${VERSION}] CV email: ${lower}`);
          break;
        }
      }

      // Extract phones — FIX v4.3: dual-pass extractor
      const cvPhoneSet = extractPhonesFromText(cvText);
      const cvPhonesArray = [...cvPhoneSet];
      if (cvPhonesArray.length > 0) {
        result.phone = cvPhonesArray[0];
        console.log(`[VHC v${VERSION}] CV phone: ${result.phone} (found ${cvPhonesArray.length} total)`);
      }

      // Also check tel: links inside iframe
      if (!result.phone) {
        const telLinks = iframeDoc.querySelectorAll('a[href^="tel:"]');
        for (const a of telLinks) {
          const c = cleanPhone(a.getAttribute('href').replace('tel:', ''));
          if (isValidIndianMobile(c)) { result.phone = c; break; }
        }
      }

      // Also try mailto/tel links inside iframe
      if (!result.email) {
        const mailtoLinks = iframeDoc.querySelectorAll('a[href^="mailto:"]');
        for (const a of mailtoLinks) {
          const e = a.getAttribute('href').replace('mailto:', '').split('?')[0].trim().toLowerCase();
          if (e && !isNaukriSystemEmail(e)) { result.email = e; break; }
        }
      }

      // ===== DEEP SECTION EXTRACTION =====
      // Extract structured sections from CV text for richer AI input
      const lines = cvText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
      
      // Detect section headers and group content
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

      // Log what we found
      const foundSections = Object.keys(sections).filter(k => sections[k].length > 0);
      console.log(`[VHC v${VERSION}] CV deep scan: found sections [${foundSections.join(', ')}]`);

      // Extract LinkedIn URL from CV
      const linkedinMatch = cvText.match(/(?:https?:\/\/)?(?:www\.)?linkedin\.com\/in\/[a-zA-Z0-9_-]+/i);
      if (linkedinMatch) {
        result.sections.linkedin = linkedinMatch[0];
        console.log(`[VHC v${VERSION}] CV LinkedIn: ${linkedinMatch[0]}`);
      }

      // Extract additional emails
      const allCvEmails = (cvText.match(EMAIL_REGEX) || []).map(e => e.toLowerCase().trim()).filter(e => !isNaukriSystemEmail(e));
      if (allCvEmails.length > 1) {
        result.sections.additionalEmails = allCvEmails.slice(1);
      }

      // Extract additional phone numbers
      if (cvPhonesArray.length > 1) {
        result.sections.additionalPhones = cvPhonesArray.slice(1);
      }

    } catch (err) {
      console.warn(`[VHC v${VERSION}] CV iframe scan error:`, err.message);
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
   * v4.4 trust hierarchy:
   *   EMAIL: CV iframe > Email diff (after View Contact) > BEFORE snapshot > DOM
   *   PHONE: CV iframe > Revealed phones (from contact section) > DOM selectors
   *
   * Phone NEVER falls back to BEFORE snapshot — that contains recruiter's number.
   * Phone sources are now guaranteed to come from the contact section only.
   */
  function mergeContacts(cvData, diffData, domData, recruiterCreds, beforeSnapshot) {
    const rEmail = (recruiterCreds.email || '').toLowerCase().trim();
    const rPhone = cleanPhone(recruiterCreds.phone || '');

    function isRecruiterEmail(e) {
      if (!e) return false;
      return rEmail && e.toLowerCase().trim() === rEmail;
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
      for (const e of beforeSnapshot.emails) {
        if (!isBadEmail(e)) { finalEmail = e; emailSource = 'Already-visible'; break; }
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

    console.log(`[VHC v${VERSION}] MERGE email: ${finalEmail || 'NONE'} [source: ${emailSource}]`);
    console.log(`[VHC v${VERSION}] MERGE phone: ${finalPhone || 'NONE'} [source: ${phoneSource}]`);
    return { email: finalEmail, phone: finalPhone };
  }

  // ===================== CAPTURE FLOW =====================

  // ===================== SEARCH/LIST PAGE DETECTION =====================

  function isSearchPage() {
    const pathname = window.location.pathname;
    const search   = window.location.search;
    // Naukri Resdex search results / candidate listing pages
    if (pathname.includes('/v3/search') || pathname.includes('/resdex')) return true;
    if (search.includes('searchId') || search.includes('srcPage')) return true;
    if (document.querySelector('[class*="candidateCard"], [class*="candidate-card"], [class*="resumeCard"]')) return true;
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
    // sid param
    const sidMatch = url.match(/[?&]sid=([^&]+)/i);
    if (sidMatch) return sidMatch[1];
    return null;
  }

  function isProfilePage() {
    const pathname = window.location.pathname;
    const search = window.location.search;
    // Only match individual profile pages, NOT search/index pages
    if (pathname.includes('/v3/preview') && search.includes('tabKey=profile')) return true;
    // Legacy Naukri profile URL patterns
    if (/viewResume|view-resume|cvPreview/i.test(pathname)) return true;
    return false;
  }

  async function scrollToLoadContent() {
    console.log(`[VHC v${VERSION}] Smart scroll: trigger lazy-load without slow smooth scrolling...`);

    const MAX_SCROLL_TIME = 5000; // hard cap: never scroll for more than 5s total
    const startTime = Date.now();

    // Strategy 1: Jump to bottom instantly — triggers all lazy-load observers at once
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
    await sleep(400);

    // Strategy 2: Wait for content to settle using MutationObserver (instead of fixed sleeps)
    await new Promise((resolve) => {
      let quietTimer = null;
      const QUIET_PERIOD = 400; // content settled if no new DOM nodes for 400ms
      const remaining = MAX_SCROLL_TIME - (Date.now() - startTime);
      const maxTimer = setTimeout(resolve, Math.max(remaining, 500));

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
      await sleep(CONFIG.SCROLL_DELAY); // now 150ms each = 450ms total for 3 jumps
    }

    // Return to top so UI looks normal
    window.scrollTo({ top: 0, behavior: 'instant' });
    await sleep(200);

    const elapsed = Date.now() - startTime;
    console.log(`[VHC v${VERSION}] Scroll complete in ${elapsed}ms. text: ${(document.body.innerText || '').length} chars`);
  }

  /**
   * MAIN CAPTURE — Multi-Source Cross-Validation Pipeline v3.8.2
   */
  async function performCapture(isManual) {
    const auth = await getAuthToken();
    if (!auth) return { success: false, error: 'Not logged in. Login via extension popup.' };

    showProgressBar();
    updateProgress(5, 'Waiting for page to settle...');

    // Step 1: DOM stability check
    const stableTitle = await waitForDOMStability();
    updateProgress(8, 'Scrolling page...');

    // Step 2: Scroll to load ALL content including CV iframe
    await scrollToLoadContent();
    // No extra sleep needed — scrollToLoadContent already settles via MutationObserver

    // Step 3: Extract name from title
    updateProgress(15, 'Extracting candidate name...');
    const domName = extractNameFromTitle();
    console.log(`[VHC v${VERSION}] Candidate name: "${domName}"`);

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

    // Step 7: Scan CV iframe
    updateProgress(50, 'Scanning CV preview...');
    const cvData = scanCVIframe(domName);
    console.log(`[VHC v${VERSION}] CV: email=${cvData.email || 'none'}, phone=${cvData.phone || 'none'}, valid=${cvData.isValid}, text=${cvData.text.length}chars`);

    // Step 8: DOM selector fallback (recruiterCreds used for filtering)
    const recruiterCreds = await getRecruiterCredentials();
    const domSelectorData = extractFromDOMSelectors(recruiterCreds);

    // Step 9: MERGE — pass beforeEmails as Set for email fallback
    updateProgress(55, 'Cross-validating contacts...');
    const merged = mergeContacts(cvData, diff, domSelectorData, recruiterCreds, { emails: beforeEmails, phones: new Set() });
    console.log(`[VHC v${VERSION}] === FINAL: email=${merged.email || 'NONE'}, phone=${merged.phone || 'NONE'} ===`);

    // Step 10: Capture raw text
    updateProgress(60, 'Capturing page text...');
    const rawText = getRawPageText();

    if (rawText.length < 100) {
      updateProgress(0, 'Error: page text too short');
      hideProgressBar(2000);
      return { success: false, error: 'Page text too short. Make sure profile is fully loaded.' };
    }

    const naukriId = extractNaukriProfileId();

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
      email:                merged.email || null,
      phone:                merged.phone || null,
      raw_text:             combinedText.substring(0, 15000),
      recruiter_email:      recruiterCreds.email || null,
      recruiter_phone:      recruiterCreds.phone || null,
      scraped_at:           new Date().toISOString(),
      extension_version:    VERSION,
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
    console.log(`[VHC v${VERSION}] Manual capture triggered`);
    try {
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
    console.log(`[VHC v${VERSION}] Auto-capture starting...`);
    try {
      await performCapture(false);
    } catch (e) {
      if (!e.message?.includes('Extension context')) console.error(`[VHC v${VERSION}]`, e);
    } finally { isCapturing = false; }
  }

  // ===================== MESSAGE LISTENER =====================
  if (isExtensionValid()) {
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (request.action === 'manualCapture') { manualCapture().then(sendResponse); return true; }
      if (request.action === 'bulkCapture')   { bulkCapture().then(sendResponse); return true; }
      if (request.action === 'getPageInfo')   {
        sendResponse({
          url: window.location.href,
          isProfilePage: isProfilePage(),
          isSearchPage: isSearchPage(),
        });
        return true;
      }
    });
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
    console.log(`[VHC v${VERSION}] Initializing...`);
    addFloatingButton();
    const settings = await getSettings();
    if (!settings.enabled) return;
    const auth = await getAuthToken();
    if (!auth) { console.log(`[VHC v${VERSION}] Not authenticated`); return; }

    if (isSearchPage()) {
      console.log(`[VHC v${VERSION}] Search/list page detected — bulk capture ready`);
      addBulkCaptureButton();
      return;
    }

    if (!isProfilePage()) { console.log(`[VHC v${VERSION}] Not a profile page`); return; }
    if (document.readyState !== 'complete') await new Promise(r => window.addEventListener('load', r));
    setTimeout(() => autoCapture(), CONFIG.CAPTURE_DELAY);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

})();
