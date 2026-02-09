/**
 * VHC Talent OS - Naukri Resdex Profile Scraper v3.2
 * 
 * Strategy: Instead of relying on DOM class names (which are React-generated),
 * we extract the FULL visible text from the main profile area and parse it
 * using known section headings and patterns from real Naukri profiles.
 *
 * Naukri profile sections (from real PDF export):
 *   - Breadcrumb with candidate name
 *   - Quick info bar: experience, salary, location, notice period
 *   - Resume headline
 *   - Profile summary
 *   - Work Experience (multiple entries)
 *   - Education (multiple entries)  
 *   - Key skills (tags)
 *   - IT Skills (table)
 *   - Certifications
 *   - Projects
 *   - Languages
 *   - Personal details (DOB, gender, marital status, category)
 *   - Career preferences (desired location, job type, employment type)
 */

(function() {
  'use strict';

  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  const VERSION = '3.2.0';
  const CONFIG = {
    CAPTURE_DELAY: 4000,
    SCROLL_DELAY: 800,
    TOAST_DURATION: 4000,
  };

  let isCapturing = false;
  let lastCapturedUrl = null;

  console.log(`[VHC Extension v${VERSION}] Content script loaded on:`, window.location.href);

  // ===================== EXTENSION CONTEXT GUARD =====================
  function isExtensionValid() {
    try { return !!(chrome && chrome.runtime && chrome.runtime.id); } catch (e) { return false; }
  }
  function handleInvalidContext() {
    showToast('Extension was updated. Please refresh this page (F5).', 'error');
  }

  // ===================== UTILITY =====================
  function cleanText(text) {
    if (!text) return null;
    return text.replace(/\s+/g, ' ').replace(/[\n\r\t]/g, ' ').trim() || null;
  }
  function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

  // ===================== SIDEBAR DETECTION =====================

  /** Find the "AI matched similar profiles" sidebar and return it */
  function findSidebarContainer() {
    // Look for text "AI matched" or "similar profiles" or "also viewed"
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
    while (walker.nextNode()) {
      const text = walker.currentNode.textContent.trim().toLowerCase();
      if (text.includes('ai matched') || text.includes('similar profiles') || text.includes('also viewed')) {
        // Walk up to find a substantial container
        let el = walker.currentNode.parentElement;
        while (el && el !== document.body) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 200 && rect.height > 200) return el;
          el = el.parentElement;
        }
      }
    }
    return null;
  }

  function isInSidebar(element) {
    if (!element) return false;
    const sidebar = findSidebarContainer();
    if (sidebar && sidebar.contains(element)) return true;
    // Position check: right 30% of viewport
    const rect = element.getBoundingClientRect();
    if (rect.width > 0 && rect.left > window.innerWidth * 0.68 && rect.width < window.innerWidth * 0.35) return true;
    return false;
  }

  // ===================== MAIN PROFILE TEXT =====================

  /**
   * Extract ALL visible text from the main profile area, 
   * excluding sidebar, scripts, styles, and hidden elements.
   */
  function getMainProfileText() {
    const container = document.getElementById('cap-container') || document.getElementById('rdxRoot') || document.body;
    const clone = container.cloneNode(true);
    
    // Remove unwanted elements
    clone.querySelectorAll('script, style, noscript, iframe, svg, [aria-hidden="true"]').forEach(e => e.remove());
    
    // Remove sidebar from clone
    const sidebarPatterns = ['similar', 'aimatched', 'ai-matched', 'also-viewed', 'alsoviewed', 'comment'];
    clone.querySelectorAll('*').forEach(el => {
      const cls = (el.className || '').toString().toLowerCase();
      for (const p of sidebarPatterns) {
        if (cls.includes(p)) { el.remove(); return; }
      }
    });
    
    // Also remove elements that are positioned in the right sidebar area
    // (We can't check getBoundingClientRect on cloned elements, so we skip this)
    
    const text = (clone.innerText || clone.textContent || '').trim();
    return text;
  }

  // ===================== TEXT-BASED EXTRACTION =====================

  function extractNaukriProfileId() {
    const urlParams = new URLSearchParams(window.location.search);
    const sid = urlParams.get('sid');
    if (sid) return `naukri_${sid}`;
    const profileParam = urlParams.get('profile_id') || urlParams.get('profileId') || urlParams.get('id');
    if (profileParam) return `naukri_${profileParam}`;
    return `naukri_${Date.now()}`;
  }

  function extractName() {
    // Strategy 1: Breadcrumb — "N profile found > CandidateName"
    const allText = document.body.innerText;
    const breadcrumbMatch = allText.match(/\d+\s*profile[s]?\s*found[\s>»]+([A-Za-z][A-Za-z.\s]+)/i);
    if (breadcrumbMatch) {
      const name = cleanText(breadcrumbMatch[1]);
      if (name && name.length > 2 && name.length < 60) {
        console.log(`[VHC v${VERSION}] Name from breadcrumb: ${name}`);
        return name;
      }
    }

    // Strategy 2: Page title
    const title = document.title;
    if (title) {
      const titleName = title.replace(/\s*[-|–]\s*(Profile|Naukri|Resdex|Resume|Search).*$/i, '').trim();
      if (titleName.length > 2 && titleName.length < 60 && !/naukri|resdex|search|recruiter/i.test(titleName)) {
        console.log(`[VHC v${VERSION}] Name from title: ${titleName}`);
        return titleName;
      }
    }

    // Strategy 3: First large text element in left/top area
    const container = document.getElementById('cap-container') || document.body;
    const candidates = container.querySelectorAll('h1, h2, [class*="name"], [class*="Name"]');
    for (const el of candidates) {
      if (isInSidebar(el)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.top > 50 && rect.top < 400 && rect.left < window.innerWidth * 0.5) {
        const name = cleanText(el.textContent);
        if (name && name.length > 2 && name.length < 60 && !/search|decode|naukri|similar|add to|view/i.test(name)) {
          console.log(`[VHC v${VERSION}] Name from element: ${name}`);
          return name;
        }
      }
    }
    return null;
  }

  function splitName(fullName) {
    if (!fullName) return {};
    const parts = fullName.trim().split(/[\s.]+/).filter(Boolean);
    if (parts.length === 1) return { first_name: parts[0] };
    if (parts.length === 2) return { first_name: parts[0], last_name: parts[1] };
    return { first_name: parts[0], middle_name: parts.slice(1, -1).join(' '), last_name: parts[parts.length - 1] };
  }

  /**
   * Parse the full profile text into sections using known Naukri headings.
   */
  function parseProfileSections(fullText) {
    const sections = {};
    const sectionHeadings = [
      'resume headline', 'profile summary', 'work experience', 'employment',
      'education', 'key skills', 'it skills', 'technical skills',
      'certifications', 'projects', 'languages', 'personal details',
      'career profile', 'desired job profile', 'online profile',
      'current salary', 'expected salary', 'notice period'
    ];
    
    const lines = fullText.split('\n');
    let currentSection = 'header';
    sections[currentSection] = [];
    
    for (const line of lines) {
      const trimmedLower = line.trim().toLowerCase();
      let matched = false;
      for (const heading of sectionHeadings) {
        if (trimmedLower === heading || trimmedLower.startsWith(heading + ':') || 
            trimmedLower.startsWith(heading + ' :') ||
            (trimmedLower.includes(heading) && trimmedLower.length < heading.length + 20)) {
          currentSection = heading.replace(/\s+/g, '_');
          sections[currentSection] = [];
          matched = true;
          break;
        }
      }
      if (!matched && line.trim()) {
        if (!sections[currentSection]) sections[currentSection] = [];
        sections[currentSection].push(line.trim());
      }
    }
    
    return sections;
  }

  function extractFromText(fullText) {
    const data = {};
    const sections = parseProfileSections(fullText);
    
    console.log(`[VHC v${VERSION}] Parsed sections:`, Object.keys(sections).filter(k => sections[k].length > 0));

    // --- Experience years ---
    const expMatch = fullText.match(/(\d+)\s*(?:Years?|Yrs?|y)\s*(?:(\d+)\s*(?:Months?|Mos?|m))?/i);
    if (expMatch) {
      data.total_experience_years = parseFloat(expMatch[1]) + (expMatch[2] ? parseInt(expMatch[2]) / 12 : 0);
      console.log(`[VHC v${VERSION}] Experience: ${data.total_experience_years}`);
    }

    // --- Current salary ---
    const salaryMatch = fullText.match(/₹\s*(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA)/i) ||
                        fullText.match(/Rs\.?\s*(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA)/i) ||
                        fullText.match(/(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh)\s*(?:PA|per\s*annum)?/i);
    if (salaryMatch) {
      data.current_salary = Math.round(parseFloat(salaryMatch[1]) * 100000);
      console.log(`[VHC v${VERSION}] Salary: ${data.current_salary}`);
    }

    // --- Notice period ---
    const noticeMatch = fullText.match(/(?:Notice\s*(?:Period)?[:\s]*)?(\d+)\s*(?:Month|Months)/i) ||
                        fullText.match(/(Immediate(?:ly)?)/i);
    if (noticeMatch) {
      data.notice_period = noticeMatch[1].toLowerCase().includes('immediate') ? 'Immediate' : `${noticeMatch[1]} Month${parseInt(noticeMatch[1]) > 1 ? 's' : ''}`;
      console.log(`[VHC v${VERSION}] Notice: ${data.notice_period}`);
    }

    // --- Location ---
    const locMatch = fullText.match(/(?:Current\s*)?(?:Location|City)[:\s]*([A-Za-z\s]+?)(?:\n|$|\|)/i);
    if (locMatch) data.location = cleanText(locMatch[1]);
    // Also try: location is often shown after experience/salary in the quick info bar
    const prefLocMatch = fullText.match(/(?:Pref\.?\s*location|Desired\s*(?:Location|City))\s*(?:Preference)?[:\s]*([^\n]+)/i);
    if (prefLocMatch) {
      data.preferred_locations = prefLocMatch[1].split(/[,\/]/).map(l => cleanText(l)).filter(Boolean);
    }

    // --- Current role ---
    const currentMatch = fullText.match(/Current\s+(.+?)\s+at\s+(.+?)\s+(?:since|from)/i);
    if (currentMatch) {
      data.current_designation = cleanText(currentMatch[1]);
      data.current_company = cleanText(currentMatch[2]);
      console.log(`[VHC v${VERSION}] Current: ${data.current_designation} at ${data.current_company}`);
    }

    // --- Resume headline ---
    if (sections.resume_headline?.length > 0) {
      data.headline = sections.resume_headline.join(' ').substring(0, 500);
      console.log(`[VHC v${VERSION}] Headline: ${data.headline.substring(0, 60)}...`);
    }

    // --- Profile summary ---
    if (sections.profile_summary?.length > 0) {
      data.profile_summary = sections.profile_summary.join('\n').substring(0, 3000);
      console.log(`[VHC v${VERSION}] Summary: ${data.profile_summary.substring(0, 60)}...`);
    }

    // --- Email ---
    const emailMatch = fullText.match(/[\w.-]+@[\w.-]+\.(com|in|org|net|co\.in|io|gmail\.com)/i);
    if (emailMatch && !emailMatch[0].includes('naukri.com')) {
      data.email = emailMatch[0].toLowerCase();
      console.log(`[VHC v${VERSION}] Email: ${data.email}`);
    }

    // --- Phone ---
    const phoneMatch = fullText.match(/(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}/);
    if (phoneMatch) {
      data.phone = phoneMatch[0].replace(/[\s-]/g, '');
      console.log(`[VHC v${VERSION}] Phone: ${data.phone}`);
    }

    // --- Key skills ---
    if (sections.key_skills?.length > 0) {
      const skillText = sections.key_skills.join(' ');
      // Skills are usually comma-separated or pipe-separated or in spans
      data.key_skills = skillText.split(/[,|•·]/).map(s => cleanText(s)).filter(s => s && s.length > 1 && s.length < 50);
      console.log(`[VHC v${VERSION}] Skills: ${data.key_skills.length}`);
    }

    // --- Education ---
    if (sections.education?.length > 0) {
      data.education = [];
      let currentEdu = {};
      for (const line of sections.education) {
        const degreeMatch = line.match(/^(MBA|B\.?Tech|M\.?Tech|B\.?Sc|M\.?Sc|BCA|MCA|B\.?E|M\.?E|B\.?Com|M\.?Com|PGDM|PhD|Diploma|Bachelor|Master|MS|BSc|MSc).*/i);
        if (degreeMatch) {
          if (currentEdu.degree) data.education.push(currentEdu);
          currentEdu = { degree: cleanText(line) };
        } else if (line.match(/university|institute|college|school/i) && currentEdu.degree) {
          currentEdu.institution = cleanText(line);
        } else if (line.match(/^\d{4}$/) && currentEdu.degree) {
          currentEdu.year_of_passing = line.trim();
        }
      }
      if (currentEdu.degree) data.education.push(currentEdu);
      console.log(`[VHC v${VERSION}] Education entries: ${data.education.length}`);
    }

    // --- Personal details ---
    const dobMatch = fullText.match(/(?:DOB|Date\s*of\s*Birth|Born)[:\s]*(\d{1,2}\s*\w+[\s,]*\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})/i);
    if (dobMatch) data.date_of_birth = cleanText(dobMatch[1]);
    const genderMatch = fullText.match(/Gender[:\s]*(Male|Female|Other|Transgender)/i);
    if (genderMatch) data.gender = genderMatch[1];
    const maritalMatch = fullText.match(/Marital\s*Status[:\s]*(Single|Married|Unmarried|Divorced|Widowed|Separated|Single\/unmarried)/i);
    if (maritalMatch) data.marital_status = cleanText(maritalMatch[1]);
    const categoryMatch = fullText.match(/Category[:\s]*(General|OBC|SC|ST|EWS)/i);
    if (categoryMatch) data.category = categoryMatch[1];

    // --- Languages ---
    if (sections.languages?.length > 0) {
      data.languages = [];
      for (const line of sections.languages) {
        const langMatch = line.match(/^([A-Za-z]+)\s*[-–:]/);
        if (langMatch) {
          const lang = { language: langMatch[1] };
          if (/expert/i.test(line)) lang.proficiency = 'Expert';
          else if (/proficient/i.test(line)) lang.proficiency = 'Proficient';
          else if (/beginner/i.test(line)) lang.proficiency = 'Beginner';
          data.languages.push(lang);
        }
      }
    }

    // --- Certifications ---
    if (sections.certifications?.length > 0) {
      data.certifications = sections.certifications
        .filter(l => l.length > 3 && l.length < 200)
        .map(name => ({ name: cleanText(name) }));
      console.log(`[VHC v${VERSION}] Certifications: ${data.certifications.length}`);
    }

    return data;
  }

  // ===================== SKILL EXTRACTION (DOM-based fallback) =====================

  function extractSkillsFromDOM() {
    const skills = new Set();
    const container = document.getElementById('cap-container') || document.body;
    // Skills are usually in spans/chips near a "Key Skills" heading
    const allSpans = container.querySelectorAll('span, a');
    let nearSkillSection = false;
    for (const el of allSpans) {
      if (isInSidebar(el)) continue;
      const text = el.textContent.trim();
      if (/key\s*skills/i.test(text)) { nearSkillSection = true; continue; }
      if (nearSkillSection && text.length > 1 && text.length < 50) {
        // Stop if we hit another section heading
        if (/^(IT Skills|Education|Work|Employment|Certification|Project|Language|Personal)/i.test(text)) break;
        if (!/key\s*skills|show more|show less|edit/i.test(text)) {
          skills.add(text);
        }
      }
    }
    return [...skills];
  }

  // ===================== PHOTO =====================

  function extractPhotoUrl() {
    const container = document.getElementById('cap-container') || document.body;
    for (const img of container.querySelectorAll('img')) {
      if (isInSidebar(img)) continue;
      const rect = img.getBoundingClientRect();
      if (rect.width >= 50 && rect.width <= 250 && rect.top < 500 && rect.left < window.innerWidth * 0.5) {
        if (img.src && !img.src.includes('logo') && !img.src.includes('icon') && !img.src.includes('sprite') && !img.src.includes('svg')) {
          return img.src;
        }
      }
    }
    return null;
  }

  // ===================== MAIN SCRAPING FUNCTION =====================

  async function scrapeProfileData() {
    console.log(`[VHC v${VERSION}] Starting profile scrape...`);

    const name = extractName();
    if (!name) {
      console.log(`[VHC v${VERSION}] ERROR: Could not find candidate name`);
      return null;
    }

    const nameParts = splitName(name);
    const fullText = getMainProfileText();
    
    console.log(`[VHC v${VERSION}] Main profile text length: ${fullText.length} chars`);
    
    // Parse all data from text
    const textData = extractFromText(fullText);
    
    // Try DOM-based skill extraction as fallback
    let skills = textData.key_skills || [];
    if (skills.length === 0) {
      skills = extractSkillsFromDOM();
      console.log(`[VHC v${VERSION}] Skills from DOM fallback: ${skills.length}`);
    }

    const data = {
      naukri_profile_id: extractNaukriProfileId(),
      naukri_profile_url: window.location.href,
      name: name,
      first_name: nameParts.first_name || null,
      middle_name: nameParts.middle_name || null,
      last_name: nameParts.last_name || null,
      photo_url: extractPhotoUrl(),
      email: textData.email || null,
      phone: textData.phone || null,
      headline: textData.headline || null,
      resume_headline: textData.headline || null,
      profile_summary: textData.profile_summary || null,
      current_company: textData.current_company || null,
      current_designation: textData.current_designation || null,
      current_industry: null,
      total_experience_years: textData.total_experience_years || null,
      total_experience_months: textData.total_experience_years ? Math.round(textData.total_experience_years * 12) : null,
      work_experience: [],
      education: textData.education || [],
      key_skills: skills,
      it_skills: [],
      certifications: textData.certifications || [],
      projects: [],
      languages: textData.languages || [],
      online_profiles: [],
      personal_details: {},
      career_preferences: {
        current_salary: textData.current_salary || null,
        notice_period: textData.notice_period || null,
        current_location: textData.location || null,
        preferred_locations: textData.preferred_locations || [],
      },
      scraped_at: new Date().toISOString(),
      raw_profile_text: fullText.substring(0, 8000),
      extension_version: VERSION
    };

    // Add personal details if found
    if (textData.date_of_birth) data.personal_details.date_of_birth = textData.date_of_birth;
    if (textData.gender) data.personal_details.gender = textData.gender;
    if (textData.marital_status) data.personal_details.marital_status = textData.marital_status;
    if (textData.category) data.personal_details.category = textData.category;

    // Set highest qualification
    if (data.education.length > 0) {
      data.highest_qualification = data.education[0].degree;
    }

    console.log(`[VHC v${VERSION}] === EXTRACTION RESULT ===`);
    console.log(`[VHC v${VERSION}] Name: ${data.name}`);
    console.log(`[VHC v${VERSION}] Email: ${data.email}`);
    console.log(`[VHC v${VERSION}] Phone: ${data.phone}`);
    console.log(`[VHC v${VERSION}] Company: ${data.current_company}`);
    console.log(`[VHC v${VERSION}] Designation: ${data.current_designation}`);
    console.log(`[VHC v${VERSION}] Experience: ${data.total_experience_years}`);
    console.log(`[VHC v${VERSION}] Salary: ${data.career_preferences?.current_salary}`);
    console.log(`[VHC v${VERSION}] Notice: ${data.career_preferences?.notice_period}`);
    console.log(`[VHC v${VERSION}] Location: ${data.career_preferences?.current_location}`);
    console.log(`[VHC v${VERSION}] Skills: ${data.key_skills?.length}`);
    console.log(`[VHC v${VERSION}] Education: ${data.education?.length}`);
    console.log(`[VHC v${VERSION}] Headline: ${data.headline ? 'Yes' : 'No'}`);
    console.log(`[VHC v${VERSION}] Summary: ${data.profile_summary ? 'Yes' : 'No'}`);
    console.log(`[VHC v${VERSION}] Raw text length: ${data.raw_profile_text?.length}`);
    console.log(`[VHC v${VERSION}] ========================`);

    return data;
  }

  // ===================== CAPTURE FLOW =====================

  function isProfilePage() {
    return /resdex|profile|viewResume|view-resume|cvPreview|preview/i.test(window.location.href);
  }

  async function scrollToLoadContent() {
    console.log(`[VHC v${VERSION}] Scrolling to load all content...`);
    const totalHeight = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
    const step = window.innerHeight * 0.6;
    let pos = 0;
    while (pos < totalHeight) {
      pos += step;
      window.scrollTo({ top: pos, behavior: 'smooth' });
      await sleep(CONFIG.SCROLL_DELAY);
    }
    // Scroll back to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
    await sleep(1000);
    console.log(`[VHC v${VERSION}] Scroll complete (page height: ${totalHeight}px)`);
  }

  async function manualCapture() {
    if (isCapturing) return { success: false, error: 'Capture in progress' };
    if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Refresh page' }; }
    isCapturing = true;
    console.log(`[VHC v${VERSION}] Manual capture triggered`);
    try {
      const auth = await getAuthToken();
      if (!auth) return { success: false, error: 'Not logged in. Login via popup.' };
      showToast('Capturing profile...', 'info');
      await scrollToLoadContent();
      await sleep(1500);
      const profileData = await scrapeProfileData();
      if (!profileData || !profileData.name) return { success: false, error: 'Could not extract profile.' };
      if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Context lost.' }; }
      const response = await chrome.runtime.sendMessage({ action: 'captureProfile', data: profileData });
      if (response?.success) {
        lastCapturedUrl = window.location.href;
        const msgs = { created: 'added to VHC!', updated: 'profile updated!', exists: 'up-to-date', queued: 'queued' };
        showToast(`${profileData.name} ${msgs[response.action] || 'captured'}`, response.action === 'created' ? 'success' : 'info');
        return { success: true, action: response.action, name: profileData.name };
      }
      showToast(response?.error || 'Error', 'error');
      return { success: false, error: response?.error };
    } catch (error) {
      if (error.message?.includes('Extension context invalidated')) handleInvalidContext();
      else showToast(`Error: ${error.message}`, 'error');
      return { success: false, error: error.message };
    } finally { isCapturing = false; }
  }

  async function captureProfile() {
    if (isCapturing || lastCapturedUrl === window.location.href) return;
    if (!isExtensionValid()) return;
    isCapturing = true;
    try {
      const profileData = await scrapeProfileData();
      if (!profileData?.name) return;
      if (!isExtensionValid()) return;
      const response = await chrome.runtime.sendMessage({ action: 'captureProfile', data: profileData });
      if (response?.success) {
        lastCapturedUrl = window.location.href;
        const settings = await getSettings();
        if (settings.showNotifications) {
          if (response.action === 'created') showToast(`${profileData.name} added to VHC`, 'success');
          else if (response.action === 'updated') showToast(`${profileData.name} updated`, 'info');
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
    btn.title = `VHC Capture v${VERSION}`;
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
    try { return await new Promise((res, rej) => { chrome.storage.sync.get({ enabled: true, showNotifications: true, autoCapture: true }, r => { if (chrome.runtime.lastError) rej(chrome.runtime.lastError); else res(r); }); }); }
    catch (e) { return { enabled: true, showNotifications: true, autoCapture: true }; }
  }

  async function getAuthToken() {
    if (!isExtensionValid()) { handleInvalidContext(); return null; }
    try { return await new Promise((res, rej) => { chrome.storage.sync.get(['vhc_token', 'vhc_api_url'], r => { if (chrome.runtime.lastError) rej(chrome.runtime.lastError); else res(r.vhc_token && r.vhc_api_url ? { token: r.vhc_token, apiUrl: r.vhc_api_url } : null); }); }); }
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
    await scrollToLoadContent();
    setTimeout(() => captureProfile(), CONFIG.CAPTURE_DELAY);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

})();
