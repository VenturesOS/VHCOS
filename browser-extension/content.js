/**
 * VHC Talent OS - Naukri Resdex Profile Scraper v3.8.0
 * 
 * AI-Powered Extraction Pipeline:
 * 1. Scroll page to load all content (including lazy-loaded CV preview)
 * 2. Extract name from page title (most reliable source)
 * 3. Load recruiter credentials from chrome.storage as BLOCKLIST
 * 4. Extract email/phone from targeted DOM selectors, excluding recruiter's own
 * 5. Capture cleaned text from the page (light noise removal only)
 * 6. Send everything to backend AI endpoint with DOM hints + recruiter identity
 * 7. Send extracted data DIRECTLY to capture endpoint
 */

(function() {
  'use strict';

  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  const VERSION = '3.8.0';
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
   * Extract email and phone from the PROFILE AREA of the page.
   * 
   * Strategy: Use the candidate's name (from title) to find where the profile
   * content starts in the page text. Then scan for email/phone patterns ONLY
   * in that area, skipping the header/nav where the recruiter's info lives.
   * 
   * Also tries: mailto links, tel links, and auto-clicking "View Contact".
   */
  function extractContactFromDOM(candidateName, recruiterCreds = {}) {
    const contacts = { email: null, phone: null };
    const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
    const phoneRegex = /(\+91[\s.-]?)?[6-9]\d{4}[\s.-]?\d{5}/g;
    const indianMobileRegex = /(?:\+91[\s.-]?)?[6-9]\d{9}/;

    const rEmail = recruiterCreds.email || null;
    const rPhone = recruiterCreds.phone || null;
    if (rEmail) console.log(`[VHC v${VERSION}] Recruiter email blocklist: ${rEmail}`);
    if (rPhone) console.log(`[VHC v${VERSION}] Recruiter phone blocklist: ${rPhone}`);

    function skipEmail(e) {
      if (!e) return true;
      const eLower = e.toLowerCase().trim();
      if (eLower.includes('@naukri.com') || eLower.includes('support@') || 
          eLower.includes('noreply@') || eLower.includes('@example.') ||
          eLower.includes('info@naukri') || eLower.includes('recruiter@naukri')) return true;
      if (isRecruiterEmail(eLower, rEmail)) {
        console.log(`[VHC v${VERSION}] BLOCKED recruiter email: ${eLower}`);
        return true;
      }
      return false;
    }

    function skipPhone(p) {
      if (!p) return true;
      if (isRecruiterPhone(p, rPhone)) {
        console.log(`[VHC v${VERSION}] BLOCKED recruiter phone: ${p}`);
        return true;
      }
      return false;
    }

    // --- Strategy 1: mailto: and tel: links (most reliable) ---
    const mailtoLinks = document.querySelectorAll('a[href^="mailto:"]');
    for (const a of mailtoLinks) {
      const email = a.getAttribute('href').replace('mailto:', '').split('?')[0].trim().toLowerCase();
      if (!skipEmail(email)) {
        contacts.email = email;
        console.log(`[VHC v${VERSION}] DOM email (mailto): ${email}`);
        break;
      }
    }

    const telLinks = document.querySelectorAll('a[href^="tel:"]');
    for (const a of telLinks) {
      const phone = a.getAttribute('href').replace('tel:', '').replace(/[\s.-]/g, '');
      if (phone && phone.length >= 10 && !skipPhone(phone)) {
        contacts.phone = phone;
        console.log(`[VHC v${VERSION}] DOM phone (tel): ${phone}`);
        break;
      }
    }

    // --- Strategy 2: Profile-area text scan ---
    if (!contacts.email || !contacts.phone) {
      const bodyText = document.body.innerText || '';
      
      let profileStartIdx = 0;
      if (candidateName) {
        const nameIdx = bodyText.indexOf(candidateName);
        if (nameIdx > 0) {
          profileStartIdx = nameIdx;
          console.log(`[VHC v${VERSION}] Profile text starts at char ${nameIdx} (name: "${candidateName}")`);
        }
      }
      
      const profileText = bodyText.substring(profileStartIdx);
      
      if (!contacts.email) {
        const emails = profileText.match(emailRegex);
        if (emails) {
          for (const e of emails) {
            const eLower = e.toLowerCase();
            if (skipEmail(eLower)) continue;
            contacts.email = eLower;
            console.log(`[VHC v${VERSION}] DOM email (profile area scan): ${eLower}`);
            break;
          }
        }
      }

      if (!contacts.phone) {
        const phones = profileText.match(phoneRegex);
        if (phones) {
          for (const p of phones) {
            const cleaned = p.replace(/[\s.-]/g, '');
            if (indianMobileRegex.test(cleaned) && cleaned.length >= 10 && !skipPhone(cleaned)) {
              contacts.phone = cleaned;
              console.log(`[VHC v${VERSION}] DOM phone (profile area scan): ${cleaned}`);
              break;
            }
          }
        }
      }
    }

    console.log(`[VHC v${VERSION}] Final DOM contacts: email=${contacts.email || 'none'}, phone=${contacts.phone || 'none'}`);
    return contacts;
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
   * MAIN CAPTURE: 
   * 1. Get raw text
   * 2. Send to AI extraction endpoint
   * 3. Send extracted data to capture endpoint
   */
  async function performCapture(isManual) {
    const auth = await getAuthToken();
    if (!auth) return { success: false, error: 'Not logged in. Login via extension popup.' };

    if (isManual) showToast('Capturing profile with AI...', 'info');

    // Step 1: Scroll and load all content
    await scrollToLoadContent();
    await sleep(1000);
    
    // Step 1.5: Auto-click "View Contact" to reveal hidden phone/email
    await clickViewContactButton();
    
    // Load recruiter credentials for blocklist filtering
    const recruiterCreds = await getRecruiterCredentials();
    console.log(`[VHC v${VERSION}] Recruiter blocklist loaded: email=${recruiterCreds.email || 'none'}, phone=${recruiterCreds.phone || 'none'}`);
    
    // Extract name from page title (most reliable source)
    const domName = extractNameFromTitle();
    
    // Extract contacts using name-anchored profile area scan + recruiter blocklist
    const domContacts = extractContactFromDOM(domName, recruiterCreds);
    console.log(`[VHC v${VERSION}] DOM-extracted: name="${domName}", email="${domContacts.email}", phone="${domContacts.phone}"`);
    
    // CROSS-VALIDATION: If we have both a name and email, verify they co-exist on this page.
    // If the candidate's name doesn't appear within ~2000 chars of the email in the page text,
    // the email is likely stale (left over from a previous profile in SPA navigation).
    if (domName && domContacts.email) {
      const bodyText = document.body.innerText || '';
      const emailIdx = bodyText.indexOf(domContacts.email);
      const nameIdx = bodyText.indexOf(domName);
      if (emailIdx >= 0 && nameIdx >= 0) {
        const distance = Math.abs(emailIdx - nameIdx);
        if (distance > 3000) {
          console.warn(`[VHC v${VERSION}] STALE EMAIL DETECTED: "${domContacts.email}" is ${distance} chars away from name "${domName}". Clearing.`);
          domContacts.email = null;
        }
      } else if (emailIdx < 0) {
        // Email not found in visible text at all — might be from a cached DOM element
        console.warn(`[VHC v${VERSION}] Email "${domContacts.email}" not found in visible text. Might be stale. Keeping for AI to verify.`);
      }
    }
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
          await sleep(2000 * attempt);
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
            naukri_profile_id: naukriId,
            dom_extracted_name: domName || null,
            dom_extracted_email: domContacts.email || null,
            dom_extracted_phone: domContacts.phone || null,
            recruiter_email: recruiterCreds.email || null,
            recruiter_phone: recruiterCreds.phone || null
          })
        });

        aiResult = await aiResponse.json();
        
        if (aiResult.success) break;
        
        if (aiResult.error && (aiResult.error.includes('429') || aiResult.error.includes('rate'))) {
          console.log(`[VHC v${VERSION}] Rate limited, will retry...`);
          continue;
        }
        break;
        
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

    // Step 3: Build capture payload — prefer DOM-extracted values over AI
    const finalName = domName || profileData.name;
    const capturePayload = {
      naukri_profile_id: naukriId,
      naukri_profile_url: window.location.href,
      name: finalName,
      first_name: finalName?.split(/[\s.]+/)[0] || null,
      last_name: finalName?.split(/[\s.]+/).slice(-1)[0] || null,
      email: domContacts.email || profileData.email || null,
      phone: domContacts.phone || profileData.phone || null,
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
