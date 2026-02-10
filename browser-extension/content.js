/**
 * VHC Talent OS - Naukri Resdex Profile Scraper v3.5
 * 
 * AI-Powered Extraction Pipeline:
 * 1. Scroll page to load all content (including lazy-loaded CV preview)
 * 2. Capture clean text from the page (stripping nav/sidebar noise)
 * 3. Send to backend AI endpoint (OpenAI) for structured extraction
 * 4. Send extracted data DIRECTLY to capture endpoint (bypassing service worker)
 */

(function() {
  'use strict';

  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  const VERSION = '3.6.1';
  const CONFIG = {
    CAPTURE_DELAY: 4000,
    SCROLL_DELAY: 600,
    TOAST_DURATION: 5000,
  };

  let isCapturing = false;
  let lastCapturedUrl = null;

  console.log(`[VHC v${VERSION}] Content script loaded on:`, window.location.href);

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
      // Resdex v3 preview containers (common patterns)
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
      // Generic fallback containers
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

    // Remove EVERYTHING that is not profile content
    const noiseSelectors = [
      // Standard HTML noise
      'nav', 'header', 'footer', 'aside', 'script', 'style', 'noscript', 'iframe', 'svg',
      // Naukri-specific navigation & header
      '[class*="naukri-header"]', '[class*="naukri-footer"]',
      '[class*="topnav"]', '[class*="topNav"]', '[class*="top-nav"]',
      '[class*="leftNav"]', '[class*="leftSec"]', '[class*="left-nav"]', '[class*="left-panel"]',
      '[class*="navbar"]', '[class*="navBar"]',
      '[class*="headerContainer"]', '[class*="header-container"]',
      '[class*="menuContainer"]', '[class*="menu-container"]',
      '[class*="sideMenu"]', '[class*="side-menu"]',
      '[class*="globalNav"]', '[class*="global-nav"]',
      // Similar profiles sidebar
      '[class*="similar-profile"]', '[class*="similarProfile"]', '[class*="similar_profile"]',
      '[class*="related-profile"]', '[class*="relatedProfile"]',
      '[id*="similar"]', '[id*="related"]',
      // Chatbot, cookie, ads
      '[class*="chatbot"]', '[class*="cookie"]', '[class*="banner-ad"]', '[class*="ad-container"]',
      '[class*="intercom"]', '[class*="helpWidget"]',
      // Save/folder UI elements
      '[class*="saveForLater"]', '[class*="save-for-later"]',
      '[class*="folderList"]', '[class*="folder-list"]',
      // Search bar & filters (not profile content)
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
   * Post-process extracted text to remove known navigation/noise patterns.
   * This catches noise that DOM stripping missed.
   */
  function postProcessText(text) {
    if (!text || text.length < 50) return text;

    // Split into lines and filter out navigation/noise lines
    const lines = text.split('\n');
    const noisePatterns = [
      /^(Jobs & Responses|Resdex|Reports|Recent|Search)$/i,
      /^(Home|Dashboard|Inbox|Notifications|Settings|Help|Logout)$/i,
      /^(Profiles saved for later|No profiles saved|Now you can save)$/i,
      /^(Save for later|Add to folder|Send NVite|Forward|Report profile)$/i,
      /^(Sort by|Customize|Filters|Clear all|Apply)$/i,
      /^(Prev|Next|Print|Back to search)$/i,
      /^(Decode India|Download the app|naukri\.com|recruiter\.naukri)$/i,
      /^\d+\s*profiles?\s*found$/i,
    ];

    const cleanLines = [];
    let profileContentStarted = false;

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      // Skip short lines that match noise patterns
      if (trimmed.length < 60 && noisePatterns.some(p => p.test(trimmed))) {
        continue;
      }

      // Detect where actual profile content starts:
      // Usually after "X profiles found" or a candidate name with designation
      if (!profileContentStarted) {
        if (/\d+\s*profiles?\s*found/i.test(trimmed)) {
          profileContentStarted = true;
          continue; // Skip the "X profiles found" line itself
        }
        // If the line looks like a person name + title, start here
        if (/^[A-Z][a-z]+ [A-Z]/.test(trimmed) && trimmed.length > 5 && trimmed.length < 80) {
          profileContentStarted = true;
        }
      }

      if (profileContentStarted || cleanLines.length > 0) {
        cleanLines.push(trimmed);
      }
    }

    // If profile content was never detected, use all non-noise lines
    const result = cleanLines.length > 10 ? cleanLines.join('\n') : lines.filter(l => {
      const t = l.trim();
      return t && !noisePatterns.some(p => p.test(t));
    }).join('\n');

    console.log(`[VHC v${VERSION}] Post-processed: ${text.length} -> ${result.length} chars`);
    return result.trim();
  }

  // ===================== DOM CONTACT EXTRACTION =====================

  /**
   * Directly extract email and phone from the DOM before AI processing.
   * These are used as "hints" so the AI doesn't confuse the candidate's
   * contact info with the logged-in recruiter's info.
   */
  function extractContactFromDOM() {
    const contacts = { email: null, phone: null };
    const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
    const phoneRegex = /(?:\+91[\s-]?)?(?:\d[\s-]?){10}/g;

    // --- EMAIL ---

    // Strategy 1: Look for mailto: links (most reliable)
    const mailtoLinks = document.querySelectorAll('a[href^="mailto:"]');
    for (const a of mailtoLinks) {
      const href = a.getAttribute('href');
      const email = href.replace('mailto:', '').split('?')[0].trim().toLowerCase();
      if (email && !email.includes('@naukri.com') && !email.includes('support@') && !email.includes('noreply@')) {
        contacts.email = email;
        console.log(`[VHC v${VERSION}] DOM email (mailto): ${email}`);
        break;
      }
    }

    // Strategy 2: Look for elements near the candidate info card that contain email patterns
    if (!contacts.email) {
      // Look in elements that commonly hold contact info on Resdex
      const contactSelectors = [
        '[class*="contact"]', '[class*="Contact"]',
        '[class*="email"]', '[class*="Email"]', '[class*="mail"]',
        '[class*="personalInfo"]', '[class*="personal-info"]',
        '[class*="candidateInfo"]', '[class*="candidate-info"]',
        '[class*="profileCard"]', '[class*="profile-card"]',
        '[class*="infoCard"]', '[class*="info-card"]',
        // Resdex-specific patterns
        '[class*="topCard"]', '[class*="top-card"]',
        '[class*="quickInfo"]', '[class*="quick-info"]',
        '[class*="contactDetail"]', '[class*="contact-detail"]',
      ];

      for (const sel of contactSelectors) {
        try {
          const els = document.querySelectorAll(sel);
          for (const el of els) {
            const text = el.innerText || el.textContent || '';
            const emails = text.match(emailRegex);
            if (emails) {
              for (const e of emails) {
                const eLower = e.toLowerCase();
                if (!eLower.includes('@naukri.com') && !eLower.includes('support@') && !eLower.includes('noreply@')) {
                  contacts.email = eLower;
                  console.log(`[VHC v${VERSION}] DOM email (selector ${sel}): ${eLower}`);
                  break;
                }
              }
              if (contacts.email) break;
            }
          }
        } catch (_) {}
        if (contacts.email) break;
      }
    }

    // Strategy 3: Scan all visible text near phone numbers / "Call candidate" buttons
    if (!contacts.email) {
      // The email is usually near the phone/call button area
      const callButtons = document.querySelectorAll('[class*="call"], [class*="Call"], [class*="phone"], [class*="Phone"], [class*="whatsapp"], [class*="WhatsApp"]');
      for (const btn of callButtons) {
        // Check parent and sibling elements
        const parent = btn.parentElement?.parentElement || btn.parentElement;
        if (parent) {
          const parentText = parent.innerText || '';
          const emails = parentText.match(emailRegex);
          if (emails) {
            for (const e of emails) {
              const eLower = e.toLowerCase();
              if (!eLower.includes('@naukri.com') && !eLower.includes('support@') && !eLower.includes('noreply@')) {
                contacts.email = eLower;
                console.log(`[VHC v${VERSION}] DOM email (near call btn): ${eLower}`);
                break;
              }
            }
            if (contacts.email) break;
          }
        }
      }
    }

    // Strategy 4: Regex scan the top portion of the page (first ~2000 chars of body text)
    if (!contacts.email) {
      const bodyText = document.body.innerText || '';
      // Scan a reasonable portion that would contain the profile card
      const topText = bodyText.substring(0, 3000);
      const emails = topText.match(emailRegex);
      if (emails) {
        for (const e of emails) {
          const eLower = e.toLowerCase();
          if (!eLower.includes('@naukri.com') && !eLower.includes('support@') && !eLower.includes('noreply@')) {
            contacts.email = eLower;
            console.log(`[VHC v${VERSION}] DOM email (body scan): ${eLower}`);
            break;
          }
        }
      }
    }

    // --- PHONE ---
    // Look for phone near "Call candidate" or contact area
    const phoneEls = document.querySelectorAll('[class*="phone"], [class*="Phone"], [class*="mobile"], [class*="Mobile"], [class*="contact"], [class*="Contact"]');
    for (const el of phoneEls) {
      const text = el.innerText || el.textContent || '';
      const phones = text.match(phoneRegex);
      if (phones) {
        contacts.phone = phones[0].replace(/[\s-]/g, '');
        console.log(`[VHC v${VERSION}] DOM phone: ${contacts.phone}`);
        break;
      }
    }

    return contacts;
  }

  function extractNaukriProfileId() {
    const urlParams = new URLSearchParams(window.location.search);
    const sid = urlParams.get('sid');
    if (sid) return `naukri_${sid}`;
    const pid = urlParams.get('profile_id') || urlParams.get('profileId') || urlParams.get('id');
    if (pid) return `naukri_${pid}`;
    return `naukri_${Date.now()}`;
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

    // First pass: smooth scroll to bottom to trigger lazy loading
    while (pos < currentHeight) {
      pos += step;
      window.scrollTo({ top: pos, behavior: 'smooth' });
      await sleep(CONFIG.SCROLL_DELAY);
      currentHeight = document.documentElement.scrollHeight;
    }

    // Wait for lazy-loaded content (CV preview often takes time)
    await sleep(2500);

    // Second pass: page may have grown, scroll to the new bottom
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

    // Third pass: re-read check — the CV viewer may have rendered additional text
    const textBefore = (document.body.innerText || '').length;
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
    await sleep(1500);
    const textAfter = (document.body.innerText || '').length;

    if (textAfter > textBefore + 200) {
      console.log(`[VHC v${VERSION}] Late content detected (+${textAfter - textBefore} chars), waiting more...`);
      await sleep(2000);
    }

    // Scroll back to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
    await sleep(500);

    console.log(`[VHC v${VERSION}] Scroll complete. Final page height: ${document.documentElement.scrollHeight}px, text: ${(document.body.innerText || '').length} chars`);
  }

  /**
   * MAIN CAPTURE: 
   * 1. Get raw text
   * 2. Send to AI extraction endpoint
   * 3. Send extracted data to capture endpoint
   */
  async function performCapture(isManual) {
    const auth = await getAuthToken();
    if (!auth) return { success: false, error: 'Not logged in. Login via extension popup.' };

    if (isManual) showToast('Capturing profile with AI...', 'info');

    // Step 1: Scroll and get raw text
    await scrollToLoadContent();
    await sleep(1000);
    
    // Extract contacts directly from DOM BEFORE text cleaning (more reliable)
    const domContacts = extractContactFromDOM();
    console.log(`[VHC v${VERSION}] DOM-extracted contacts:`, domContacts);
    
    const rawText = getRawPageText();
    console.log(`[VHC v${VERSION}] Raw text captured: ${rawText.length} chars`);
    console.log(`[VHC v${VERSION}] First 200 chars: ${rawText.substring(0, 200)}`);

    if (rawText.length < 100) {
      return { success: false, error: 'Page text too short. Make sure profile is fully loaded.' };
    }

    const naukriId = extractNaukriProfileId();

    // Step 2: Send to AI extraction endpoint
    if (isManual) showToast('AI analyzing profile...', 'info');
    console.log(`[VHC v${VERSION}] Sending ${rawText.length} chars to AI extraction...`);

    let aiResult;
    const maxRetries = 2;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        if (attempt > 0) {
          console.log(`[VHC v${VERSION}] Retry attempt ${attempt}...`);
          await sleep(2000 * attempt); // Wait 2s, 4s between retries
        }
        const aiResponse = await fetch(`${auth.apiUrl}/api/extension/ai-extract`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${auth.token}`
          },
          body: JSON.stringify({
            raw_text: rawText.substring(0, 15000),
            page_url: window.location.href,
            page_title: document.title,
            naukri_profile_id: naukriId
          })
        });

        aiResult = await aiResponse.json();
        
        if (aiResult.success) break; // Success, exit retry loop
        
        // If rate limited, retry
        if (aiResult.error && (aiResult.error.includes('429') || aiResult.error.includes('rate'))) {
          console.log(`[VHC v${VERSION}] Rate limited, will retry...`);
          continue;
        }
        break; // Other error, don't retry
        
      } catch (e) {
        console.error(`[VHC v${VERSION}] AI extraction error (attempt ${attempt}):`, e);
        if (attempt === maxRetries) {
          return { success: false, error: `AI extraction failed: ${e.message}` };
        }
      }
    }
    
    console.log(`[VHC v${VERSION}] AI extraction result:`, aiResult?.success ? 'SUCCESS' : 'FAILED', aiResult?.error || '');

    if (!aiResult.success || !aiResult.profile_data) {
      return { success: false, error: aiResult.error || 'AI extraction returned no data' };
    }

    const profileData = aiResult.profile_data;
    console.log(`[VHC v${VERSION}] AI extracted name: ${profileData.name}`);

    if (!profileData.name) {
      return { success: false, error: 'AI could not find candidate name in the text.' };
    }

    // Step 3: Build capture payload from AI data
    const capturePayload = {
      naukri_profile_id: naukriId,
      naukri_profile_url: window.location.href,
      name: profileData.name,
      first_name: profileData.name?.split(/[\s.]+/)[0] || null,
      last_name: profileData.name?.split(/[\s.]+/).slice(-1)[0] || null,
      email: profileData.email || null,
      phone: profileData.phone || null,
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

    console.log(`[VHC v${VERSION}] Sending capture with:`, {
      name: capturePayload.name,
      email: capturePayload.email,
      skills: capturePayload.key_skills?.length,
      experience: capturePayload.work_experience?.length,
      education: capturePayload.education?.length,
    });

    // Step 4: Send to capture endpoint DIRECTLY (not via background script)
    // This avoids service worker termination issues in Manifest V3
    console.log(`[VHC v${VERSION}] Sending capture directly to API...`);
    
    try {
      const captureResponse = await fetch(`${auth.apiUrl}/api/extension/capture`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${auth.token}`
        },
        body: JSON.stringify(capturePayload)
      });

      if (!captureResponse.ok) {
        const errorData = await captureResponse.json().catch(() => ({}));
        const errorMsg = errorData.detail || `HTTP ${captureResponse.status}`;
        console.error(`[VHC v${VERSION}] Capture API error:`, errorMsg);
        if (isManual) showToast(`Error: ${errorMsg}`, 'error');
        return { success: false, error: errorMsg };
      }

      const result = await captureResponse.json();
      console.log(`[VHC v${VERSION}] Capture result:`, result);
      
      lastCapturedUrl = window.location.href;
      const msgs = { created: 'added to VHC!', updated: 'profile updated!', exists: 'up-to-date' };
      if (isManual) showToast(`${capturePayload.name} ${msgs[result.action] || 'captured'}`, 'success');
      return { success: true, action: result.action, name: capturePayload.name };
    } catch (captureError) {
      console.error(`[VHC v${VERSION}] Capture fetch error:`, captureError);
      if (isManual) showToast(`Capture failed: ${captureError.message}`, 'error');
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
      const result = await performCapture(false);
      if (result.success) {
        const settings = await getSettings();
        if (settings.showNotifications) {
          showToast(`${result.name} ${result.action === 'created' ? 'added to VHC' : 'updated'}`, 
                    result.action === 'created' ? 'success' : 'info');
        }
      }
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
