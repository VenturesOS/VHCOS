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

  const VERSION = '3.8.2';
  const CONFIG = {
    CAPTURE_DELAY: 4000,
    SCROLL_DELAY: 600,
    TOAST_DURATION: 5000,
  };

  let isCapturing = false;
  let lastCapturedUrl = null;
  let lastPageUrl = window.location.href;

  console.log(`[VHC v${VERSION}] Content script loaded on:`, window.location.href);

  // SPA navigation detection: reset state when URL changes
  setInterval(() => {
    if (window.location.href !== lastPageUrl) {
      console.log(`[VHC v${VERSION}] URL changed: ${lastPageUrl} -> ${window.location.href}`);
      lastPageUrl = window.location.href;
      lastCapturedUrl = null; // Allow re-capture on new page
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
   * Reads the page title twice with a gap — if it changes, waits more.
   * Returns the stable title.
   */
  async function waitForDOMStability() {
    const title1 = document.title;
    console.log(`[VHC v${VERSION}] DOM stability check: title1="${title1}"`);
    await sleep(1500);
    const title2 = document.title;
    if (title1 !== title2) {
      console.log(`[VHC v${VERSION}] Title changed during wait: "${title1}" -> "${title2}", waiting more...`);
      await sleep(2000);
      const title3 = document.title;
      console.log(`[VHC v${VERSION}] Final title: "${title3}"`);
      return title3;
    }
    return title2;
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
  async function clickViewContactButton() {
    const buttonTexts = [
      'View Contact', 'View contact', 'view contact',
      'View Phone', 'View phone', 'view phone',
      'View Number', 'View number',
      'Show Contact', 'Show Phone', 'Show Number',
      'Reveal Contact', 'Reveal Phone',
      'View mobile', 'View Mobile',
    ];

    let clicked = false;

    for (const text of buttonTexts) {
      const buttons = document.querySelectorAll('button, a, span, div');
      for (const btn of buttons) {
        const btnText = (btn.innerText || btn.textContent || '').trim();
        if (btnText === text || btnText.toLowerCase().includes('view contact') || 
            btnText.toLowerCase().includes('view phone') || btnText.toLowerCase().includes('view number')) {
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
          const el = document.querySelector(sel);
          if (el) {
            el.click();
            clicked = true;
            console.log(`[VHC v${VERSION}] Clicked view contact via selector: ${sel}`);
            break;
          }
        } catch (_) {}
      }
    }

    if (clicked) {
      await sleep(2000);
      console.log(`[VHC v${VERSION}] Waited 2s for contact reveal`);
    } else {
      console.log(`[VHC v${VERSION}] No "View Contact" button found (contact may already be visible)`);
    }

    return clicked;
  }

  function extractNaukriProfileId() {
    const urlParams = new URLSearchParams(window.location.search);
    const sid = urlParams.get('sid');
    if (sid) return `naukri_${sid}`;
    const pid = urlParams.get('profile_id') || urlParams.get('profileId') || urlParams.get('id');
    if (pid) return `naukri_${pid}`;
    return `naukri_${Date.now()}`;
  }

  // ===================== MULTI-SOURCE CONTACT EXTRACTION =====================

  const EMAIL_REGEX = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
  const PHONE_REGEX = /(?:\+91[\s.-]?)?[6-9]\d{4}[\s.-]?\d{5}/g;
  const INDIAN_MOBILE = /(?:\+91[\s.-]?)?[6-9]\d{9}/;

  function cleanPhone(p) { return p.replace(/[\s.+\-()]/g, '').slice(-10); }

  function isNaukriSystemEmail(e) {
    const lower = (e || '').toLowerCase();
    return lower.includes('@naukri.com') || lower.includes('support@') ||
           lower.includes('noreply@') || lower.includes('@example.') ||
           lower.includes('info@naukri') || lower.includes('recruiter@naukri') ||
           lower.endsWith('@vhc.in');
  }

  /**
   * Snapshot all emails and phones currently visible on the page.
   * Returns { emails: Set, phones: Set }
   */
  function snapshotPageContacts() {
    const text = document.body.innerText || '';
    const emails = new Set();
    const phones = new Set();

    const emailMatches = text.match(EMAIL_REGEX) || [];
    emailMatches.forEach(e => {
      const lower = e.toLowerCase().trim();
      if (!isNaukriSystemEmail(lower)) emails.add(lower);
    });

    const phoneMatches = text.match(PHONE_REGEX) || [];
    phoneMatches.forEach(p => {
      const cleaned = cleanPhone(p);
      if (cleaned.length === 10 && INDIAN_MOBILE.test(cleaned)) phones.add(cleaned);
    });

    // Also check mailto/tel links
    document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
      const e = a.getAttribute('href').replace('mailto:', '').split('?')[0].trim().toLowerCase();
      if (e && !isNaukriSystemEmail(e)) emails.add(e);
    });
    document.querySelectorAll('a[href^="tel:"]').forEach(a => {
      const p = cleanPhone(a.getAttribute('href').replace('tel:', ''));
      if (p.length === 10) phones.add(p);
    });

    return { emails, phones };
  }

  /**
   * Diff two contact snapshots. Returns NEW contacts that appeared in `after`.
   */
  function diffContacts(before, after) {
    const newEmails = [...after.emails].filter(e => !before.emails.has(e));
    const newPhones = [...after.phones].filter(p => !before.phones.has(p));
    return { emails: newEmails, phones: newPhones };
  }

  /**
   * Scan the CV preview iframe for email, phone, and text content.
   * The CV only contains candidate data — no recruiter contamination.
   */
  function scanCVIframe(candidateName) {
    const result = { email: null, phone: null, text: '', isValid: false };

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
      result.text = cvText.substring(0, 10000);
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
          result.text = cvText.substring(0, 10000); // Still send text for AI to check
          return result;
        }
        result.isValid = true;
        console.log(`[VHC v${VERSION}] CV sanity check PASSED: contains name "${candidateName}"`);
      } else {
        result.isValid = true; // No name to check against, trust it
      }

      // Extract emails from CV
      const cvEmails = cvText.match(EMAIL_REGEX) || [];
      for (const e of cvEmails) {
        const lower = e.toLowerCase().trim();
        if (!isNaukriSystemEmail(lower)) {
          result.email = lower;
          console.log(`[VHC v${VERSION}] CV email: ${lower}`);
          break;
        }
      }

      // Extract phones from CV
      const cvPhones = cvText.match(PHONE_REGEX) || [];
      for (const p of cvPhones) {
        const cleaned = cleanPhone(p);
        if (cleaned.length === 10 && INDIAN_MOBILE.test(cleaned)) {
          result.phone = cleaned;
          console.log(`[VHC v${VERSION}] CV phone: ${cleaned}`);
          break;
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

    } catch (err) {
      console.warn(`[VHC v${VERSION}] CV iframe scan error:`, err.message);
    }

    return result;
  }

  /**
   * Extract contacts using Naukri's DOM selectors as a fallback.
   * i.naukri-icon-email → parent title, and [title*="@"] in #rdxRoot
   */
  function extractFromDOMSelectors(recruiterCreds = {}) {
    const contacts = { email: null, phone: null };
    const rEmail = recruiterCreds.email || null;

    function isRecruiterOrSystem(e) {
      if (!e) return true;
      if (isNaukriSystemEmail(e)) return true;
      if (rEmail && e.toLowerCase().trim() === rEmail.toLowerCase().trim()) return true;
      return false;
    }

    // Email via naukri icon
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

    // Email via title attribute containing @
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

    return contacts;
  }

  /**
   * MERGE contacts from all sources using trust hierarchy:
   * CV iframe > Before/After Diff > DOM selectors > AI
   */
  function mergeContacts(cvData, diffData, domData, recruiterCreds) {
    const rEmail = (recruiterCreds.email || '').toLowerCase().trim();
    const rPhone = cleanPhone(recruiterCreds.phone || '');

    function isRecruiterContact(email, phone) {
      if (email && rEmail && email.toLowerCase().trim() === rEmail) return true;
      if (phone && rPhone && cleanPhone(phone) === rPhone) return true;
      return false;
    }

    // Email: CV > Diff > DOM
    let finalEmail = null;
    if (cvData.isValid && cvData.email && !isRecruiterContact(cvData.email, null)) {
      finalEmail = cvData.email;
      console.log(`[VHC v${VERSION}] MERGE email: from CV iframe ✓`);
    } else if (diffData.emails.length > 0) {
      // Pick the first non-recruiter diff email
      for (const e of diffData.emails) {
        if (!isRecruiterContact(e, null) && !isNaukriSystemEmail(e)) {
          finalEmail = e;
          console.log(`[VHC v${VERSION}] MERGE email: from Before/After diff ✓`);
          break;
        }
      }
    }
    if (!finalEmail && domData.email && !isRecruiterContact(domData.email, null)) {
      finalEmail = domData.email;
      console.log(`[VHC v${VERSION}] MERGE email: from DOM selectors ✓`);
    }

    // Phone: CV > Diff > (no DOM phone strategy yet)
    let finalPhone = null;
    if (cvData.isValid && cvData.phone && !isRecruiterContact(null, cvData.phone)) {
      finalPhone = cvData.phone;
      console.log(`[VHC v${VERSION}] MERGE phone: from CV iframe ✓`);
    } else if (diffData.phones.length > 0) {
      for (const p of diffData.phones) {
        if (!isRecruiterContact(null, p)) {
          finalPhone = p;
          console.log(`[VHC v${VERSION}] MERGE phone: from Before/After diff ✓`);
          break;
        }
      }
    }

    console.log(`[VHC v${VERSION}] MERGE result: email=${finalEmail || 'none'}, phone=${finalPhone || 'none'}`);
    return { email: finalEmail, phone: finalPhone };
  }

  // ===================== CAPTURE FLOW =====================

  function isProfilePage() {
    return /resdex|profile|viewResume|view-resume|cvPreview|preview/i.test(window.location.href);
  }

  async function scrollToLoadContent() {
    console.log(`[VHC v${VERSION}] Scrolling to load ALL content including CV preview...`);

    const step = window.innerHeight * 0.5;
    let pos = 0;
    let currentHeight = document.documentElement.scrollHeight;

    while (pos < currentHeight) {
      pos += step;
      window.scrollTo({ top: pos, behavior: 'smooth' });
      await sleep(CONFIG.SCROLL_DELAY);
      currentHeight = document.documentElement.scrollHeight;
    }

    await sleep(2500);

    let newHeight = document.documentElement.scrollHeight;
    if (newHeight > currentHeight + 100) {
      console.log(`[VHC v${VERSION}] Page grew ${currentHeight} -> ${newHeight}, scrolling more...`);
      while (pos < newHeight) {
        pos += step;
        window.scrollTo({ top: pos, behavior: 'smooth' });
        await sleep(CONFIG.SCROLL_DELAY);
      }
      await sleep(2000);
    }

    const textBefore = (document.body.innerText || '').length;
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
    await sleep(1500);
    const textAfter = (document.body.innerText || '').length;

    if (textAfter > textBefore + 200) {
      console.log(`[VHC v${VERSION}] Late content detected (+${textAfter - textBefore} chars), waiting more...`);
      await sleep(2000);
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
    await sleep(500);

    console.log(`[VHC v${VERSION}] Scroll complete. Final page height: ${document.documentElement.scrollHeight}px, text: ${(document.body.innerText || '').length} chars`);
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
    await sleep(1000);

    // Step 3: Extract name from title
    updateProgress(15, 'Extracting candidate name...');
    const domName = extractNameFromTitle();
    console.log(`[VHC v${VERSION}] Candidate name: "${domName}"`);

    // Step 4: SNAPSHOT contacts BEFORE "View Contact" click
    updateProgress(20, 'Scanning page contacts...');
    const beforeSnapshot = snapshotPageContacts();
    console.log(`[VHC v${VERSION}] BEFORE: ${beforeSnapshot.emails.size} emails [${[...beforeSnapshot.emails].join(', ')}], ${beforeSnapshot.phones.size} phones [${[...beforeSnapshot.phones].join(', ')}]`);

    // Step 5: Click "View Contact"
    updateProgress(30, 'Revealing contact info...');
    await clickViewContactButton();

    // Step 6: SNAPSHOT AFTER and compute DIFF
    updateProgress(40, 'Analyzing revealed contacts...');
    const afterSnapshot = snapshotPageContacts();
    const diff = diffContacts(beforeSnapshot, afterSnapshot);
    console.log(`[VHC v${VERSION}] AFTER: ${afterSnapshot.emails.size} emails, ${afterSnapshot.phones.size} phones`);
    console.log(`[VHC v${VERSION}] DIFF: new emails=[${diff.emails.join(', ')}], new phones=[${diff.phones.join(', ')}]`);

    // Step 7: Scan CV iframe
    updateProgress(50, 'Scanning CV preview...');
    const cvData = scanCVIframe(domName);
    console.log(`[VHC v${VERSION}] CV: email=${cvData.email || 'none'}, phone=${cvData.phone || 'none'}, valid=${cvData.isValid}, text=${cvData.text.length}chars`);

    // Step 8: DOM selector fallback
    const recruiterCreds = await getRecruiterCredentials();
    const domSelectorData = extractFromDOMSelectors(recruiterCreds);

    // Step 9: MERGE all sources (CV > Diff > DOM > AI)
    updateProgress(55, 'Cross-validating contacts...');
    const merged = mergeContacts(cvData, diff, domSelectorData, recruiterCreds);
    console.log(`[VHC v${VERSION}] === FINAL: email=${merged.email || 'NONE'}, phone=${merged.phone || 'NONE'} ===`);

    // Step 10: Capture text and send to AI
    updateProgress(60, 'Capturing page text...');
    const rawText = getRawPageText();

    if (rawText.length < 100) {
      updateProgress(0, 'Error: page text too short');
      hideProgressBar(2000);
      return { success: false, error: 'Page text too short. Make sure profile is fully loaded.' };
    }

    const naukriId = extractNaukriProfileId();
    updateProgress(70, 'AI analyzing profile...');

    // Combine page text + CV text for richer AI extraction
    let combinedText = rawText.substring(0, 12000);
    if (cvData.text.length > 100) {
      combinedText += '\n\n=== CANDIDATE CV CONTENT ===\n' + cvData.text.substring(0, 5000);
    }

    let aiResult;
    for (let attempt = 0; attempt <= 2; attempt++) {
      try {
        if (attempt > 0) await sleep(2000 * attempt);
        const aiResponse = await fetch(`${auth.apiUrl}/api/extension/ai-extract`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${auth.token}` },
          body: JSON.stringify({
            raw_text: combinedText.substring(0, 15000),
            page_url: window.location.href,
            page_title: stableTitle,
            naukri_profile_id: naukriId,
            dom_extracted_name: domName || null,
            dom_extracted_email: merged.email || null,
            dom_extracted_phone: merged.phone || null,
            recruiter_email: recruiterCreds.email || null,
            recruiter_phone: recruiterCreds.phone || null
          })
        });
        aiResult = await aiResponse.json();
        if (aiResult.success) break;
        if (aiResult.error?.includes('429') || aiResult.error?.includes('rate')) continue;
        break;
      } catch (e) {
        if (attempt === 2) { updateProgress(0, 'AI failed'); hideProgressBar(2000); return { success: false, error: e.message }; }
      }
    }

    if (!aiResult?.success || !aiResult?.profile_data) {
      updateProgress(0, 'AI extraction failed');
      hideProgressBar(2000);
      return { success: false, error: aiResult?.error || 'AI extraction returned no data' };
    }

    const profileData = aiResult.profile_data;
    if (!profileData.name) {
      updateProgress(0, 'Could not find candidate name');
      hideProgressBar(2000);
      return { success: false, error: 'AI could not find candidate name.' };
    }

    updateProgress(85, 'Saving to VHC...');

    // Step 11: Build capture payload — MERGED contacts override AI
    const finalName = domName || profileData.name;
    const capturePayload = {
      naukri_profile_id: naukriId,
      naukri_profile_url: window.location.href,
      name: finalName,
      first_name: finalName?.split(/[\s.]+/)[0] || null,
      last_name: finalName?.split(/[\s.]+/).slice(-1)[0] || null,
      email: merged.email || profileData.email || null,
      phone: merged.phone || profileData.phone || null,
      headline: profileData.headline || null,
      resume_headline: profileData.headline || null,
      profile_summary: profileData.profile_summary || null,
      current_company: profileData.current_company || null,
      current_designation: profileData.current_designation || null,
      current_industry: profileData.current_industry || null,
      total_experience_years: profileData.total_experience_years || null,
      total_experience_months: profileData.total_experience_years ? Math.round(profileData.total_experience_years * 12) : null,
      total_experience_display: profileData.total_experience_years ? `${profileData.total_experience_years} years` : null,
      work_experience: profileData.work_experience || [],
      education: profileData.education || [],
      key_skills: profileData.key_skills || [],
      it_skills: profileData.it_skills || [],
      certifications: profileData.certifications || [],
      projects: profileData.projects || [],
      languages: profileData.languages || [],
      online_profiles: profileData.online_profiles || [],
      linkedin_url: (profileData.online_profiles || []).find(p => p.platform === 'LinkedIn')?.url || null,
      personal_details: {
        date_of_birth: profileData.date_of_birth || null,
        gender: profileData.gender || null,
        marital_status: profileData.marital_status || null,
        nationality: profileData.nationality || null,
        category: profileData.category || null,
      },
      career_preferences: {
        current_salary: profileData.current_salary || null,
        expected_salary: profileData.expected_salary || null,
        notice_period: profileData.notice_period || null,
        current_location: profileData.location || null,
        preferred_locations: profileData.preferred_locations || [],
      },
      highest_qualification: (profileData.education || [])[0]?.degree || null,
      scraped_at: new Date().toISOString(),
      raw_profile_text: rawText.substring(0, 8000),
      extension_version: VERSION
    };

    console.log(`[VHC v${VERSION}] Capture payload:`, { name: capturePayload.name, email: capturePayload.email, phone: capturePayload.phone, skills: capturePayload.key_skills?.length });

    // Step 12: Send to capture endpoint
    try {
      const captureResponse = await fetch(`${auth.apiUrl}/api/extension/capture`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${auth.token}` },
        body: JSON.stringify(capturePayload)
      });

      if (!captureResponse.ok) {
        const errorData = await captureResponse.json().catch(() => ({}));
        const errorMsg = errorData.detail || `HTTP ${captureResponse.status}`;
        updateProgress(0, `Error: ${errorMsg}`);
        hideProgressBar(3000);
        return { success: false, error: errorMsg };
      }

      const result = await captureResponse.json();
      lastCapturedUrl = window.location.href;
      const msgs = { created: 'added to VHC!', updated: 'profile updated!', exists: 'up-to-date' };
      updateProgress(100, `${capturePayload.name} ${msgs[result.action] || 'captured'}`);
      hideProgressBar(4000);
      return { success: true, action: result.action, name: capturePayload.name };
    } catch (captureError) {
      updateProgress(0, `Failed: ${captureError.message}`);
      hideProgressBar(3000);
      return { success: false, error: captureError.message };
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
      if (request.action === 'getPageInfo') { sendResponse({ url: window.location.href, isProfilePage: isProfilePage() }); return true; }
    });
  }

  // ===================== UI =====================
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
    if (!isProfilePage()) { console.log(`[VHC v${VERSION}] Not a profile page`); return; }
    if (document.readyState !== 'complete') await new Promise(r => window.addEventListener('load', r));
    setTimeout(() => autoCapture(), CONFIG.CAPTURE_DELAY);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

})();
