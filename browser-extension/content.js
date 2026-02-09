/**
 * VHC Talent OS - Naukri Resdex Profile Scraper v3.1
 * Built from real Naukri Resdex page DOM analysis.
 *
 * Page layout (confirmed from screenshots):
 *   - Breadcrumb: "X profile found > CandidateName" (MOST RELIABLE for name)
 *   - LEFT: Main profile card (photo, name, experience, salary, location, current role, education, skills, contact)
 *   - RIGHT: "AI matched similar profiles" section with tabs "Profile details" / "Recruiters also viewed"
 *            Contains small profile cards of OTHER candidates — MUST BE EXCLUDED
 *   - RIGHT: "No comments" / "Add comments" section
 *
 * DOM: #rdxRoot > #cap-container > React SPA content
 */

(function() {
  'use strict';

  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  const CONFIG = {
    CAPTURE_DELAY: 3000,
    SCROLL_DELAY: 500,
    TOAST_DURATION: 4000,
  };

  let isCapturing = false;
  let lastCapturedUrl = null;

  console.log('[VHC Extension v3.2] Content script loaded on:', window.location.href);

  // ===================== EXTENSION CONTEXT GUARD =====================

  function isExtensionValid() {
    try { return !!(chrome && chrome.runtime && chrome.runtime.id); } catch (e) { return false; }
  }

  function handleInvalidContext() {
    showToast('Extension was updated. Please refresh this page (F5).', 'error');
  }

  // ===================== UTILITY HELPERS =====================

  function cleanText(text) {
    if (!text) return null;
    return text.replace(/\s+/g, ' ').replace(/[\n\r\t]/g, ' ').trim() || null;
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /** Get text from element, stripping script/style/hidden elements */
  function getCleanText(el) {
    if (!el) return '';
    const clone = el.cloneNode(true);
    clone.querySelectorAll('script, style, noscript, iframe, [style*="display:none"], [style*="display: none"]').forEach(e => e.remove());
    // Also remove any "AI matched similar profiles" sections from clone
    removeSidebarFromClone(clone);
    return (clone.innerText || clone.textContent || '').trim();
  }

  /** Remove sidebar/similar-profiles sections from a cloned element */
  function removeSidebarFromClone(clone) {
    // Find and remove any element containing "similar profiles", "AI matched", "also viewed" headings
    const allEls = clone.querySelectorAll('*');
    for (const el of allEls) {
      const text = (el.textContent || '').trim().toLowerCase();
      const cls = (el.className || '').toString().toLowerCase();
      // If this is a heading/title for the sidebar section, remove its parent container
      if (
        (text.includes('ai matched') && text.includes('similar')) ||
        (text.includes('similar profiles')) ||
        (text.includes('also viewed')) ||
        cls.includes('similar') ||
        cls.includes('aimatched') ||
        cls.includes('comment')
      ) {
        // Remove the closest section-like parent
        const container = el.closest('[class*="section"], [class*="Section"], [class*="panel"], [class*="Panel"], [class*="card"], [class*="Card"]') || el.parentElement;
        if (container && container !== clone) {
          container.remove();
          break; // Re-scanning after removal
        }
      }
    }
  }

  // ===================== SIDEBAR DETECTION =====================

  /**
   * Identify the "AI matched similar profiles" container and mark it.
   * This is the RIGHT sidebar section that shows other candidates.
   * We find it by looking for headings containing "similar profiles" or "AI matched".
   */
  function getSidebarContainer() {
    const allElements = document.querySelectorAll('*');
    for (const el of allElements) {
      const text = (el.textContent || '').trim();
      // The heading "AI matched similar profiles" identifies the sidebar
      if (/AI\s*matched\s*similar\s*profiles/i.test(text) && text.length < 100) {
        // Find the container that holds this heading AND the profile cards below
        let container = el;
        while (container.parentElement && container.parentElement.tagName !== 'BODY') {
          const rect = container.getBoundingClientRect();
          // The sidebar container is typically 300-500px wide on the right
          if (rect.width > 200 && rect.width < 600 && rect.height > 200) {
            return container;
          }
          container = container.parentElement;
        }
        return el.parentElement?.parentElement || el.parentElement;
      }
    }
    return null;
  }

  /** Check if element is inside the sidebar / similar-profiles area */
  function isInSidebar(element) {
    if (!element) return false;

    // Method 1: Check if inside the known sidebar container
    const sidebarContainer = getSidebarContainer();
    if (sidebarContainer && sidebarContainer.contains(element)) return true;

    // Method 2: Pattern-based class/id check
    const sidebarPatterns = [
      'similar', 'matched', 'recommendation', 'aimatched', 'ai-matched',
      'rightsection', 'right-section', 'rightpanel', 'right-panel',
      'suggestedprofile', 'alsoviewed', 'also-viewed',
      'comment', 'sidecard', 'miniprofile', 'quickview'
    ];
    let parent = element;
    let depth = 0;
    while (parent && parent !== document.body && depth < 15) {
      const cls = (parent.className || '').toString().toLowerCase();
      const id = (parent.id || '').toLowerCase();
      if (parent.tagName?.toLowerCase() === 'aside') return true;
      for (const p of sidebarPatterns) {
        if (cls.includes(p) || id.includes(p)) return true;
      }
      parent = parent.parentElement;
      depth++;
    }

    // Method 3: Position check — if in the right 30% of viewport and narrow
    const rect = element.getBoundingClientRect();
    if (rect.width > 0 && rect.left > window.innerWidth * 0.7 && rect.width < window.innerWidth * 0.35) {
      return true;
    }

    return false;
  }

  // ===================== SCOPED QUERIES =====================

  function getMainContainer() {
    return document.getElementById('cap-container') || document.getElementById('rdxRoot') || document.body;
  }

  function qsMain(selector) {
    const main = getMainContainer();
    const els = main.querySelectorAll(selector);
    for (const el of els) {
      if (!isInSidebar(el)) return el;
    }
    return null;
  }

  function qsaMain(selector) {
    const main = getMainContainer();
    return [...main.querySelectorAll(selector)].filter(el => !isInSidebar(el));
  }

  function getMainProfileText() {
    const main = getMainContainer();
    return getCleanText(main);
  }

  function findSection(headingTexts) {
    if (!Array.isArray(headingTexts)) headingTexts = [headingTexts];
    const main = getMainContainer();
    const headings = main.querySelectorAll('h2, h3, h4, [class*="heading"], [class*="Heading"], [class*="title"], [class*="Title"]');
    for (const h of headings) {
      if (isInSidebar(h)) continue;
      const hText = (h.textContent || '').trim().toLowerCase();
      for (const target of headingTexts) {
        if (hText.includes(target.toLowerCase())) {
          return h.closest('section, [class*="section"], [class*="Section"]') || h.parentElement;
        }
      }
    }
    return null;
  }

  // ===================== EXTRACTION FUNCTIONS =====================

  function extractNaukriProfileId() {
    const urlParams = new URLSearchParams(window.location.search);
    const sid = urlParams.get('sid');
    if (sid) return `naukri_${sid}`;
    const profileParam = urlParams.get('profile_id') || urlParams.get('profileId') || urlParams.get('id');
    if (profileParam) return `naukri_${profileParam}`;
    const urlMatch = window.location.href.match(/\/(\d{5,})\/?/);
    if (urlMatch) return `naukri_${urlMatch[1]}`;
    return `naukri_${Date.now()}`;
  }

  /**
   * CRITICAL: Extract the correct candidate name.
   * Strategy (in order of reliability for Naukri Resdex):
   *   1. Breadcrumb — Shows "X profile found > CandidateName" (MOST RELIABLE)
   *   2. Page <title> — Usually "CandidateName - something"
   *   3. First name-like element in the LEFT portion of the page (NOT sidebar)
   */
  function extractName() {
    // === Strategy 1: BREADCRUMB (most reliable on Naukri Resdex) ===
    // The breadcrumb on Naukri shows: icon > "X profile found" > "CandidateName"
    // From screenshot: "1 profile found > Bhanupriya.R"
    // Look for ALL elements that could be breadcrumb items
    const breadcrumbSelectors = [
      '[class*="breadcrumb"] a:last-child',
      '[class*="breadcrumb"] span:last-child',
      '[class*="breadcrumb"] li:last-child',
      '[class*="Breadcrumb"] a:last-child',
      '[class*="Breadcrumb"] span:last-child',
    ];
    for (const sel of breadcrumbSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        const name = cleanText(el.textContent);
        if (name && name.length > 2 && name.length < 60 && !/profile.*found|search|resdex/i.test(name)) {
          console.log('[VHC Extension v3.2] Found name from breadcrumb selector:', name);
          return name;
        }
      }
    }

    // Try broader breadcrumb detection — look for the text pattern "X profile found > Name"
    const allTextElements = document.querySelectorAll('span, a, li, div');
    for (const el of allTextElements) {
      const text = el.textContent.trim();
      // Match "N profile found" pattern — the NEXT sibling or child should be the name
      if (/\d+\s*profile.*found/i.test(text) && text.length < 40) {
        // Check next sibling elements
        let sibling = el.nextElementSibling;
        while (sibling) {
          const name = cleanText(sibling.textContent);
          if (name && name.length > 2 && name.length < 60 && !/profile|found|search/i.test(name)) {
            console.log('[VHC Extension v3.2] Found name from breadcrumb (next to "profile found"):', name);
            return name;
          }
          sibling = sibling.nextElementSibling;
        }
        // Check parent's children after this element
        const parent = el.parentElement;
        if (parent) {
          const children = [...parent.children];
          const idx = children.indexOf(el);
          for (let i = idx + 1; i < children.length; i++) {
            const name = cleanText(children[i].textContent);
            if (name && name.length > 2 && name.length < 60 && !/profile|found|search/i.test(name)) {
              console.log('[VHC Extension v3.2] Found name from breadcrumb (parent child):', name);
              return name;
            }
          }
        }
      }
    }

    // Also try: look for bold text in breadcrumb area (top of page, first 150px)
    const topBoldElements = document.querySelectorAll('strong, b, [class*="bold"], [class*="Bold"]');
    for (const el of topBoldElements) {
      const rect = el.getBoundingClientRect();
      if (rect.top < 150 && rect.top > 50 && !isInSidebar(el)) {
        const name = cleanText(el.textContent);
        if (name && name.length > 2 && name.length < 60 && !/profile|found|search|resdex|naukri|print|report/i.test(name)) {
          console.log('[VHC Extension v3.2] Found name from top bold element:', name);
          return name;
        }
      }
    }

    // === Strategy 2: Page <title> ===
    const pageTitle = document.querySelector('title');
    if (pageTitle) {
      let titleText = pageTitle.textContent;
      titleText = titleText.replace(/\s*[-|–]\s*(Profile|Naukri|Resdex|Resume|Search).*$/i, '').trim();
      titleText = titleText.replace(/\s*on\s+Naukri.*$/i, '').trim();
      if (titleText && titleText.length > 2 && titleText.length < 60 &&
          !/naukri|resdex|search|recruiter|login|home/i.test(titleText)) {
        console.log('[VHC Extension v3.2] Found name from page title:', titleText);
        return titleText;
      }
    }

    // === Strategy 3: First large name in LEFT portion of main content ===
    const main = getMainContainer();
    // Look for name-like elements that are: in the left 60%, in the top 500px, NOT in sidebar
    const nameEls = main.querySelectorAll(
      '[class*="name"], [class*="Name"], h1, h2, [class*="candidateName"], [class*="profileName"]'
    );
    for (const el of nameEls) {
      if (isInSidebar(el)) continue;
      const rect = el.getBoundingClientRect();
      // Must be in left portion and upper part of page
      if (rect.left < window.innerWidth * 0.55 && rect.top < 500 && rect.top > 100 && rect.width > 50) {
        const name = cleanText(el.textContent);
        if (name && name.length > 2 && name.length < 60 && 
            !/company|org|employer|add to|send|save|forward|schedule|comment|view/i.test(name)) {
          console.log('[VHC Extension v3.2] Found name from left-positioned element:', name, 
                      `(x:${Math.round(rect.left)}, y:${Math.round(rect.top)}, w:${Math.round(rect.width)})`);
          return name;
        }
      }
    }

    console.log('[VHC Extension v3.2] WARNING: Could not find candidate name');
    return null;
  }

  function splitName(fullName) {
    if (!fullName) return {};
    const parts = fullName.trim().split(/[\s.]+/).filter(Boolean);
    if (parts.length === 1) return { first_name: parts[0] };
    if (parts.length === 2) return { first_name: parts[0], last_name: parts[1] };
    return { first_name: parts[0], middle_name: parts.slice(1, -1).join(' '), last_name: parts[parts.length - 1] };
  }

  function extractEmail() {
    const main = getMainContainer();
    // Look for mailto links NOT in sidebar
    for (const link of main.querySelectorAll('a[href^="mailto:"]')) {
      if (isInSidebar(link)) continue;
      const email = link.href.replace('mailto:', '').trim().toLowerCase();
      if (email.includes('@') && !email.includes('naukri.com') && !email.includes('@vhc.in')) {
        console.log('[VHC Extension v3.2] Found email from mailto:', email);
        return email;
      }
    }
    // Look for email-like elements
    for (const el of main.querySelectorAll('[class*="email"], [class*="Email"]')) {
      if (isInSidebar(el)) continue;
      const m = el.textContent.match(/[\w.-]+@[\w.-]+\.\w+/);
      if (m && !m[0].includes('naukri.com')) {
        console.log('[VHC Extension v3.2] Found email from element:', m[0]);
        return m[0].toLowerCase();
      }
    }
    // Look for visible email text in LEFT part of page
    const mainText = getMainProfileText();
    const matches = mainText.match(/[\w.-]+@[\w.-]+\.(com|in|org|net|co\.in|io|gmail\.com)/gi);
    if (matches) {
      for (const email of matches) {
        if (!email.includes('naukri.com') && !email.includes('@vhc.in')) {
          console.log('[VHC Extension v3.2] Found email from text:', email);
          return email.toLowerCase();
        }
      }
    }
    console.log('[VHC Extension v3.2] Could not find email');
    return null;
  }

  function extractPhone() {
    const main = getMainContainer();
    for (const el of main.querySelectorAll('[class*="phone"], [class*="mobile"], [class*="Phone"], [class*="Mobile"], a[href^="tel:"]')) {
      if (isInSidebar(el)) continue;
      const text = el.href ? el.href.replace('tel:', '') : el.textContent;
      const m = text.match(/(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}/);
      if (m) {
        console.log('[VHC Extension v3.2] Found phone:', m[0]);
        return m[0].replace(/[\s-]/g, '');
      }
    }
    console.log('[VHC Extension v3.2] Could not find phone');
    return null;
  }

  function extractPhotoUrl() {
    const main = getMainContainer();
    for (const img of main.querySelectorAll('img')) {
      if (isInSidebar(img)) continue;
      const rect = img.getBoundingClientRect();
      // Profile photo is usually 60-200px, in the left portion, top area
      if (rect.width >= 50 && rect.width <= 250 && rect.top < 600 && rect.left < window.innerWidth * 0.5) {
        if (img.src && !img.src.includes('logo') && !img.src.includes('icon') && !img.src.includes('sprite')) {
          console.log('[VHC Extension v3.2] Found photo URL');
          return img.src;
        }
      }
    }
    return null;
  }

  function extractCurrentEmployment() {
    const result = { company: null, designation: null, department: null, industry: null };
    const mainText = getMainProfileText();
    
    // From screenshot: "Current   Customer Success Manager at Numeric UPS since Oct ... 1 Month"
    const currentMatch = mainText.match(/Current\s+(.+?)\s+at\s+(.+?)\s+since/i);
    if (currentMatch) {
      result.designation = cleanText(currentMatch[1]);
      result.company = cleanText(currentMatch[2]);
      console.log('[VHC Extension v3.2] Found current role:', result.designation, 'at', result.company);
    }

    // Fallback: separate patterns
    if (!result.designation) {
      const lines = mainText.split('\n').filter(l => l.trim().length > 0 && l.trim().length < 200);
      for (let i = 0; i < lines.length; i++) {
        if (/^Current$/i.test(lines[i].trim()) && i + 1 < lines.length) {
          const nextLine = lines[i + 1].trim();
          if (nextLine.length > 3 && !/window\.|document\.|function|script|nLogger/i.test(nextLine)) {
            const atMatch = nextLine.match(/(.+?)\s+at\s+(.+?)(?:\s+since|$)/i);
            if (atMatch) {
              result.designation = cleanText(atMatch[1]);
              result.company = cleanText(atMatch[2].replace(/\s+since.*/, ''));
            } else {
              result.designation = cleanText(nextLine);
            }
            break;
          }
        }
      }
    }

    return result;
  }

  function extractTotalExperience() {
    const mainText = getMainProfileText();
    // From screenshot: "9y" or "9y 0m"
    const patterns = [
      /(\d+)y\s*(\d+)?m/i,
      /(\d+(?:\.\d+)?)\s*(?:Years?|Yrs?)\s*(?:(\d+)\s*(?:Months?|Mos?))?/i,
      /Experience[:\s]*(\d+(?:\.\d+)?)/i,
    ];
    for (const p of patterns) {
      const m = mainText.match(p);
      if (m) {
        let years = parseFloat(m[1]);
        if (m[2]) years += parseInt(m[2]) / 12;
        console.log('[VHC Extension v3.2] Found experience:', years, 'years');
        return years;
      }
    }
    return null;
  }

  function extractCurrentSalary() {
    const mainText = getMainProfileText();
    // From screenshot: "₹ 11 Lacs" or "₹11 Lacs"
    const patterns = [
      /₹\s*(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA)/i,
      /Rs\.?\s*(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA)/i,
      /(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA)/i,
    ];
    for (const p of patterns) {
      const m = mainText.match(p);
      if (m) {
        const salary = Math.round(parseFloat(m[1]) * 100000);
        console.log('[VHC Extension v3.2] Found salary:', salary);
        return salary;
      }
    }
    return null;
  }

  function extractLocation() {
    const mainText = getMainProfileText();
    // From screenshot: location shown with pin icon, "Chennai"
    // Look for "Pref. location   CityName" pattern
    const prefLocMatch = mainText.match(/Pref\.?\s*location\s+([A-Za-z\s,]+?)(?:\n|$)/i);
    if (prefLocMatch) {
      console.log('[VHC Extension v3.2] Found preferred location:', prefLocMatch[1]);
      return cleanText(prefLocMatch[1]);
    }
    // Try general location pattern
    const locEl = qsMain('[class*="location"], [class*="Location"], [class*="city"]');
    if (locEl) {
      const loc = cleanText(locEl.textContent);
      if (loc && loc.length < 50) {
        console.log('[VHC Extension v3.2] Found location from element:', loc);
        return loc;
      }
    }
    return null;
  }

  function extractNotice() {
    const mainText = getMainProfileText();
    const m = mainText.match(/(\d+)\s*(?:Month|Months?)\s*(?:notice)?/i);
    if (m) {
      const notice = `${m[1]} Month${parseInt(m[1]) > 1 ? 's' : ''}`;
      console.log('[VHC Extension v3.2] Found notice:', notice);
      return notice;
    }
    if (/immediate/i.test(mainText)) return 'Immediate';
    return null;
  }

  function extractHighestDegree() {
    const mainText = getMainProfileText();
    // From screenshot: "Highest degree  Bachelor of Elementary Education (B.El.Ed) Sree Sasth..."
    const m = mainText.match(/Highest\s*degree\s+(.+?)(?:\n|$)/i);
    if (m) {
      console.log('[VHC Extension v3.2] Found highest degree:', m[1].substring(0, 60));
      return cleanText(m[1]);
    }
    return null;
  }

  function extractKeySkills() {
    const skills = new Set();
    const sec = findSection(['key skills', 'skills']);
    if (sec) {
      for (const el of sec.querySelectorAll('span, a, [class*="chip"], [class*="tag"], [class*="skill"]')) {
        if (isInSidebar(el)) continue;
        const skill = cleanText(el.textContent);
        if (skill && skill.length > 1 && skill.length < 50 && !/key\s*skills?|skills?:/i.test(skill)) {
          skills.add(skill);
        }
      }
    }
    // Also look for pipe-separated skills in the main text (common Naukri format)
    // From sidebar screenshot: "Email | Cold Calling | Customer Relationship..."
    // But this is the SIDEBAR data — we must avoid it
    console.log('[VHC Extension v3.2] Found skills:', skills.size);
    return [...skills];
  }

  function extractITSkills() {
    const itSkills = [];
    const sec = findSection(['it skills', 'technical skills']);
    if (!sec) return itSkills;
    for (const row of sec.querySelectorAll('tr, [class*="skillRow"], [class*="row"]')) {
      const cells = row.querySelectorAll('td, [class*="cell"], span');
      if (cells.length >= 2) {
        const skill = { name: cleanText(cells[0]?.textContent) };
        if (cells.length > 1) skill.version = cleanText(cells[1]?.textContent);
        if (cells.length > 2) skill.last_used = cleanText(cells[2]?.textContent);
        if (cells.length > 3) {
          const m = (cells[3]?.textContent || '').match(/(\d+)/);
          if (m) skill.experience_years = parseInt(m[1]);
        }
        if (skill.name) itSkills.push(skill);
      }
    }
    return itSkills;
  }

  function extractWorkExperience() {
    const experiences = [];
    const sec = findSection(['employment', 'work experience', 'experience']);
    if (!sec) return experiences;
    // Each job is a repeated block
    for (const entry of sec.querySelectorAll('[class*="exp"], [class*="Exp"], [class*="employment"]')) {
      if (isInSidebar(entry)) continue;
      const exp = {};
      const bold = entry.querySelector('strong, b, [class*="title"], [class*="desig"], h3, h4');
      if (bold) exp.designation = cleanText(bold.textContent);
      const compEl = entry.querySelector('[class*="company"], [class*="org"]');
      if (compEl) exp.company = cleanText(compEl.textContent);
      const dateEl = entry.querySelector('[class*="duration"], [class*="date"]');
      if (dateEl) {
        exp.duration = cleanText(dateEl.textContent);
        const fromTo = dateEl.textContent.match(/(\w+[\s']?\d{2,4})\s*[-–to]+\s*(\w+[\s']?\d{2,4}|present|current|till\s*date)/i);
        if (fromTo) {
          exp.from_date = cleanText(fromTo[1]);
          exp.to_date = /present|current|till/i.test(fromTo[2]) ? null : cleanText(fromTo[2]);
          exp.is_current = /present|current|till/i.test(fromTo[2]);
        }
      }
      if (exp.designation || exp.company) experiences.push(exp);
    }
    return experiences;
  }

  function extractEducation() {
    const educations = [];
    const sec = findSection(['education', 'qualification']);
    if (sec) {
      for (const entry of sec.querySelectorAll('[class*="edu"], [class*="Edu"], [class*="qual"]')) {
        if (isInSidebar(entry)) continue;
        const edu = {};
        const degreeEl = entry.querySelector('[class*="degree"], [class*="course"], h3, h4, strong');
        if (degreeEl) edu.degree = cleanText(degreeEl.textContent);
        const instEl = entry.querySelector('[class*="institution"], [class*="university"], [class*="college"]');
        if (instEl) edu.institution = cleanText(instEl.textContent);
        if (edu.degree || edu.institution) educations.push(edu);
      }
    }
    // If no structured education found, try highest degree text
    if (educations.length === 0) {
      const highest = extractHighestDegree();
      if (highest) educations.push({ degree: highest });
    }
    return educations;
  }

  function extractCertifications() {
    const certs = [];
    const sec = findSection(['certification', 'certificate']);
    if (!sec) return certs;
    for (const entry of sec.querySelectorAll('[class*="cert"], li')) {
      if (isInSidebar(entry)) continue;
      const name = cleanText(entry.textContent);
      if (name && name.length > 2 && name.length < 200) certs.push({ name });
    }
    return certs;
  }

  function extractProjects() {
    const projects = [];
    const sec = findSection(['project']);
    if (!sec) return projects;
    for (const entry of sec.querySelectorAll('[class*="project"], li')) {
      if (isInSidebar(entry)) continue;
      const title = cleanText(entry.querySelector('h4, h3, strong, [class*="title"]')?.textContent || entry.textContent);
      if (title && title.length > 2) projects.push({ title });
    }
    return projects;
  }

  function extractLanguages() {
    const langs = [];
    const sec = findSection(['language']);
    if (!sec) return langs;
    for (const entry of sec.querySelectorAll('[class*="lang"], li, tr')) {
      if (isInSidebar(entry)) continue;
      const text = cleanText(entry.textContent);
      if (text && text.length > 1 && text.length < 50 && !/languages?:/i.test(text)) {
        langs.push({ language: text });
      }
    }
    return langs;
  }

  function extractOnlineProfiles() {
    const profiles = [];
    const sec = findSection(['online profile', 'social profile']);
    if (sec) {
      for (const link of sec.querySelectorAll('a[href]')) {
        const url = link.href;
        if (!url || url.includes('naukri.com')) continue;
        let platform = 'Other';
        if (url.includes('linkedin')) platform = 'LinkedIn';
        else if (url.includes('github')) platform = 'GitHub';
        profiles.push({ platform, url });
      }
    }
    return profiles;
  }

  function extractPersonalDetails() {
    const details = {};
    const mainText = getMainProfileText();
    const patterns = {
      date_of_birth: /(?:DOB|Date\s*of\s*Birth)[:\s]*([^\n|,]+)/i,
      gender: /Gender[:\s]*(Male|Female|Other|Transgender)/i,
      marital_status: /Marital\s*Status[:\s]*(Single|Married|Unmarried|Divorced|Widowed)/i,
      nationality: /Nationality[:\s]*([^\n|,]+)/i,
    };
    for (const [key, regex] of Object.entries(patterns)) {
      const m = mainText.match(regex);
      if (m) details[key] = cleanText(m[1]);
    }
    return Object.keys(details).length > 0 ? details : null;
  }

  // ===================== MAIN SCRAPING FUNCTION =====================

  async function scrapeProfileData() {
    console.log('[VHC Extension v3.2] Scraping profile data from MAIN profile area...');

    // Log what container we're using
    const container = getMainContainer();
    console.log('[VHC Extension v3.2] Main container:', container.id || container.tagName, 
                'width:', container.offsetWidth);

    // Log sidebar detection
    const sidebar = getSidebarContainer();
    console.log('[VHC Extension v3.2] Sidebar container found:', !!sidebar);

    const name = extractName();
    const nameParts = splitName(name);
    const currentEmployment = extractCurrentEmployment();
    const onlineProfiles = extractOnlineProfiles();
    const totalExp = extractTotalExperience();
    const location = extractLocation();
    const salary = extractCurrentSalary();

    const data = {
      naukri_profile_id: extractNaukriProfileId(),
      naukri_profile_url: window.location.href,
      name: name,
      first_name: nameParts.first_name || null,
      last_name: nameParts.last_name || null,
      photo_url: extractPhotoUrl(),
      email: extractEmail(),
      phone: extractPhone(),
      headline: null,
      profile_summary: null,
      current_company: currentEmployment.company,
      current_designation: currentEmployment.designation,
      current_industry: currentEmployment.industry,
      total_experience_years: totalExp,
      total_experience_months: totalExp ? Math.round(totalExp * 12) : null,
      total_experience_display: totalExp ? `${totalExp} years` : null,
      work_experience: extractWorkExperience(),
      education: extractEducation(),
      key_skills: extractKeySkills(),
      it_skills: extractITSkills(),
      certifications: extractCertifications(),
      projects: extractProjects(),
      languages: extractLanguages(),
      online_profiles: onlineProfiles,
      linkedin_url: (onlineProfiles.find(p => p.platform === 'LinkedIn') || {}).url || null,
      personal_details: extractPersonalDetails(),
      career_preferences: {
        current_salary: salary,
        notice_period: extractNotice(),
        current_location: location,
      },
      scraped_at: new Date().toISOString(),
      raw_profile_text: getMainProfileText().substring(0, 5000),
      extension_version: '3.2.0'
    };

    // Highest degree
    const highest = extractHighestDegree();
    if (highest) data.highest_qualification = highest;

    console.log('[VHC Extension v3.2] === EXTRACTION RESULT ===');
    console.log('[VHC Extension v3.2] Name:', data.name);
    console.log('[VHC Extension v3.2] Email:', data.email);
    console.log('[VHC Extension v3.2] Phone:', data.phone);
    console.log('[VHC Extension v3.2] Company:', data.current_company);
    console.log('[VHC Extension v3.2] Designation:', data.current_designation);
    console.log('[VHC Extension v3.2] Experience:', data.total_experience_years);
    console.log('[VHC Extension v3.2] Skills:', data.key_skills?.length);
    console.log('[VHC Extension v3.2] ========================');

    return data;
  }

  // ===================== CAPTURE FLOW =====================

  function isProfilePage() {
    const url = window.location.href;
    return url.includes('resdex') || url.includes('profile') ||
           url.includes('viewResume') || url.includes('view-resume') ||
           url.includes('cvPreview') || url.includes('preview');
  }

  async function scrollToLoadContent() {
    console.log('[VHC Extension v3.2] Scrolling to load content...');
    const scrollHeight = document.documentElement.scrollHeight;
    const viewportHeight = window.innerHeight;
    let pos = 0;
    while (pos < scrollHeight) {
      pos += viewportHeight * 0.8;
      window.scrollTo(0, pos);
      await sleep(CONFIG.SCROLL_DELAY);
    }
    window.scrollTo(0, 0);
    await sleep(500);
    console.log('[VHC Extension v3.2] Scroll complete');
  }

  async function manualCapture() {
    if (isCapturing) return { success: false, error: 'Capture already in progress' };
    if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Extension context invalidated. Refresh page.' }; }
    isCapturing = true;
    console.log('[VHC Extension v3.2] Manual capture triggered');
    try {
      const auth = await getAuthToken();
      if (!auth) return { success: false, error: 'Not logged in. Login via extension popup.' };
      showToast('Capturing profile...', 'info');
      await scrollToLoadContent();
      await sleep(1000);
      const profileData = await scrapeProfileData();
      if (!profileData || !profileData.name) {
        return { success: false, error: 'Could not extract profile. Are you on a profile page?' };
      }
      if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Context lost.' }; }
      const response = await chrome.runtime.sendMessage({ action: 'captureProfile', data: profileData });
      if (response && response.success) {
        lastCapturedUrl = window.location.href;
        const msgs = { created: 'added to VHC!', updated: 'profile updated!', exists: 'already up-to-date', queued: 'queued for sync' };
        showToast(`${profileData.name} ${msgs[response.action] || 'captured'}`, response.action === 'created' ? 'success' : 'info');
        return { success: true, action: response.action, name: profileData.name };
      }
      showToast(response?.error || 'Unknown error', 'error');
      return { success: false, error: response?.error };
    } catch (error) {
      if (error.message?.includes('Extension context invalidated')) handleInvalidContext();
      else showToast(`Error: ${error.message}`, 'error');
      return { success: false, error: error.message };
    } finally {
      isCapturing = false;
    }
  }

  async function captureProfile() {
    if (isCapturing || lastCapturedUrl === window.location.href) return;
    if (!isExtensionValid()) return;
    isCapturing = true;
    console.log('[VHC Extension v3.2] Starting auto-capture...');
    try {
      const profileData = await scrapeProfileData();
      if (!profileData || !profileData.name) return;
      if (!isExtensionValid()) return;
      const response = await chrome.runtime.sendMessage({ action: 'captureProfile', data: profileData });
      if (response && response.success) {
        lastCapturedUrl = window.location.href;
        const settings = await getSettings();
        if (settings.showNotifications) {
          if (response.action === 'created') showToast(`${profileData.name} added to VHC`, 'success');
          else if (response.action === 'updated') showToast(`${profileData.name} updated`, 'info');
        }
      }
    } catch (error) {
      if (!error.message?.includes('Extension context invalidated')) {
        console.error('[VHC Extension v3.2] Auto-capture error:', error);
      }
    } finally {
      isCapturing = false;
    }
  }

  // ===================== MESSAGE LISTENER =====================

  if (isExtensionValid()) {
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (request.action === 'manualCapture') {
        manualCapture().then(sendResponse);
        return true;
      }
      if (request.action === 'getPageInfo') {
        sendResponse({ url: window.location.href, isProfilePage: isProfilePage() });
        return true;
      }
    });
  }

  // ===================== UI =====================

  function addFloatingButton() {
    const existing = document.getElementById('vhc-floating-btn');
    if (existing) existing.remove();
    const btn = document.createElement('button');
    btn.id = 'vhc-floating-btn';
    btn.className = 'vhc-capture-btn';
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
    btn.title = 'Capture to VHC Talent OS';
    btn.addEventListener('click', async () => {
      btn.classList.add('capturing');
      await manualCapture();
      btn.classList.remove('capturing');
    });
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
    try {
      return await new Promise((resolve, reject) => {
        chrome.storage.sync.get({ enabled: true, showNotifications: true, autoCapture: true }, r => {
          if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
          else resolve(r);
        });
      });
    } catch (e) { return { enabled: true, showNotifications: true, autoCapture: true }; }
  }

  async function getAuthToken() {
    if (!isExtensionValid()) { handleInvalidContext(); return null; }
    try {
      return await new Promise((resolve, reject) => {
        chrome.storage.sync.get(['vhc_token', 'vhc_api_url'], r => {
          if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
          else resolve(r.vhc_token && r.vhc_api_url ? { token: r.vhc_token, apiUrl: r.vhc_api_url } : null);
        });
      });
    } catch (e) { handleInvalidContext(); return null; }
  }

  // ===================== INIT =====================

  async function init() {
    console.log('[VHC Extension v3.2] Initializing...');
    addFloatingButton();
    const settings = await getSettings();
    if (!settings.enabled) return;
    const auth = await getAuthToken();
    if (!auth) { console.log('[VHC Extension v3.2] Not authenticated, skipping auto-capture'); return; }
    if (!isProfilePage()) { console.log('[VHC Extension v3.2] Not a profile page, skipping'); return; }
    if (document.readyState !== 'complete') await new Promise(r => window.addEventListener('load', r));
    await scrollToLoadContent();
    setTimeout(() => captureProfile(), CONFIG.CAPTURE_DELAY);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
