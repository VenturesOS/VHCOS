/**
 * VHC Talent OS - Naukri Resdex Profile Scraper v3.3
 * 
 * NEW APPROACH: AI-Powered Extraction
 * 1. Scroll page to load all content
 * 2. Capture raw visible text from the page
 * 3. Send to backend AI endpoint (OpenAI) for structured extraction
 * 4. Send extracted data to capture endpoint
 * 
 * This eliminates DOM parsing issues since OpenAI can understand any text format.
 */

(function() {
  'use strict';

  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  const VERSION = '3.3.0';
  const CONFIG = {
    CAPTURE_DELAY: 4000,
    SCROLL_DELAY: 800,
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
   * Get ALL visible text from the page, excluding sidebar and scripts.
   * KEY FIX: Use innerText directly on the live DOM element (not a clone).
   */
  function getRawPageText() {
    let text = '';
    
    // Try #cap-container first
    const container = document.getElementById('cap-container');
    if (container) {
      text = container.innerText || '';
      console.log(`[VHC v${VERSION}] Text from #cap-container: ${text.length} chars`);
    }
    
    // If too short, use body
    if (text.length < 200) {
      text = document.body.innerText || '';
      console.log(`[VHC v${VERSION}] Text from body: ${text.length} chars`);
    }
    
    if (text.length < 50) return text;
    
    // Find where profile content starts (skip nav)
    const profileStart = text.search(/\d+\s*profile[s]?\s*found/i);
    if (profileStart > 0 && profileStart < 500) {
      text = text.substring(profileStart);
    }
    
    // DO NOT trim at "AI matched similar profiles" — the CV preview with 
    // email/phone appears AFTER the main profile but BEFORE or MIXED with sidebar.
    // Instead, we keep everything and let AI sort it out.
    // AI prompt already instructs to extract from the candidate's own data only.
    
    return text.trim();
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
    
    // First pass: scroll to bottom slowly to trigger lazy loading
    let lastHeight = 0;
    let currentHeight = document.documentElement.scrollHeight;
    let pos = 0;
    const step = window.innerHeight * 0.5;
    
    while (pos < currentHeight) {
      pos += step;
      window.scrollTo({ top: pos, behavior: 'smooth' });
      await sleep(CONFIG.SCROLL_DELAY);
      currentHeight = document.documentElement.scrollHeight; // May grow as content loads
    }
    
    // Wait for lazy-loaded content (CV preview) to render
    await sleep(2000);
    
    // Second pass: page may have grown after first scroll, scroll to new bottom
    const newHeight = document.documentElement.scrollHeight;
    if (newHeight > currentHeight + 200) {
      console.log(`[VHC v${VERSION}] Page grew from ${currentHeight} to ${newHeight}, scrolling more...`);
      pos = currentHeight;
      while (pos < newHeight) {
        pos += step;
        window.scrollTo({ top: pos, behavior: 'smooth' });
        await sleep(CONFIG.SCROLL_DELAY);
      }
      await sleep(2000);
    }
    
    // Scroll back to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
    await sleep(1000);
    
    const finalHeight = document.documentElement.scrollHeight;
    console.log(`[VHC v${VERSION}] Scroll complete. Final page height: ${finalHeight}px`);
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

    // Step 4: Send to capture endpoint via background script
    if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Context lost.' }; }
    
    const response = await chrome.runtime.sendMessage({ action: 'captureProfile', data: capturePayload });
    
    if (response?.success) {
      lastCapturedUrl = window.location.href;
      const msgs = { created: 'added to VHC!', updated: 'profile updated!', exists: 'up-to-date' };
      if (isManual) showToast(`${capturePayload.name} ${msgs[response.action] || 'captured'}`, 'success');
      return { success: true, action: response.action, name: capturePayload.name };
    }

    return { success: false, error: response?.error || 'Capture failed' };
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
