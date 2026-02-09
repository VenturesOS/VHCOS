/**
 * VHC Talent OS - Naukri Resdex Profile Scraper v3.0
 * Specifically built for Naukri Resdex profile preview pages.
 * 
 * Key DOM structure (from real Naukri page):
 *   #rdxRoot > #cap-container  — main React app content
 *   .headGNBWrap               — top navigation (ignore)
 *   .footerHtml                — footer (ignore)
 *   #talentCloudBody           — talent cloud widget (hidden, ignore)
 *   #modalRoot                 — modal container (ignore)
 *
 * URL: resdex.naukri.com/v3/preview?tabKey=profile&sid=...
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

  console.log('[VHC Extension] Content script v3.0 loaded on:', window.location.href);

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

  /**
   * Get clean text from an element, excluding script/style tags and hidden elements.
   */
  function getCleanText(el) {
    if (!el) return '';
    // Clone the element so we can remove unwanted children
    const clone = el.cloneNode(true);
    // Remove script, style, noscript elements
    clone.querySelectorAll('script, style, noscript, iframe, [style*="display:none"], [style*="display: none"]').forEach(e => e.remove());
    return clone.innerText || clone.textContent || '';
  }

  // ===================== MAIN PROFILE CONTAINER =====================

  /**
   * The Naukri Resdex page renders inside #cap-container (within #rdxRoot).
   * Inside that, the profile is typically split into:
   *   - A main/left section with full profile details
   *   - A right/sidebar section with similar/suggested profiles
   *
   * Since the internal class names are React-generated and may change,
   * we use a heuristic: the main profile section is the FIRST large child
   * of #cap-container that contains detailed profile information.
   */
  function getMainContainer() {
    // Priority 1: #cap-container is the known main content area
    const capContainer = document.getElementById('cap-container');
    if (capContainer) {
      // Look for the main profile section inside cap-container
      // Naukri typically uses a flex/grid layout. The main profile is the wider left section.
      const children = capContainer.querySelectorAll(':scope > div > div, :scope > div');
      if (children.length > 0) {
        // Find the widest child that isn't tiny (likely main content vs sidebar)
        let mainChild = null;
        let maxWidth = 0;
        for (const child of children) {
          const rect = child.getBoundingClientRect();
          // Must be visible and substantial
          if (rect.width > 400 && rect.height > 200 && rect.width > maxWidth) {
            maxWidth = rect.width;
            mainChild = child;
          }
        }
        if (mainChild) {
          console.log('[VHC Extension] Found main profile container (width:', maxWidth + ')');
          return mainChild;
        }
      }
      console.log('[VHC Extension] Using #cap-container as main container');
      return capContainer;
    }

    // Priority 2: #rdxRoot
    const rdxRoot = document.getElementById('rdxRoot');
    if (rdxRoot) {
      console.log('[VHC Extension] Using #rdxRoot as main container');
      return rdxRoot;
    }

    console.log('[VHC Extension] Falling back to document.body');
    return document.body;
  }

  /**
   * Check if an element is in the sidebar/suggested profiles area.
   * Strategy: Check if the element is to the RIGHT of the page center,
   * or if it's inside a container that's narrower and positioned right.
   */
  function isInSidebar(element) {
    if (!element) return false;

    // Check by class/id patterns
    const sidebarPatterns = [
      'sidebar', 'rightsec', 'similar', 'matched', 'recommendation',
      'aimatched', 'rightsection', 'relatedprofile', 'othercandidate',
      'right-section', 'suggestedprofile', 'matchedprofile',
      'rightpanel', 'right-panel', 'sidecard', 'similarcandidate',
      'rightcol', 'right-col', 'rhs', 'rhspanel',
      'flyout', 'miniprofile', 'quickview', 'preview-card',
      'hoverpanel', 'tooltip-profile'
    ];
    
    let parent = element;
    let depth = 0;
    while (parent && parent !== document.body && depth < 15) {
      const cls = (parent.className || '').toString().toLowerCase();
      const id = (parent.id || '').toLowerCase();
      const tag = parent.tagName?.toLowerCase();
      
      if (tag === 'aside') return true;
      
      for (const p of sidebarPatterns) {
        if (cls.includes(p) || id.includes(p)) return true;
      }
      
      parent = parent.parentElement;
      depth++;
    }

    // Position-based check: if the element is in the right 35% of the page, likely sidebar
    const rect = element.getBoundingClientRect();
    const pageWidth = window.innerWidth;
    if (rect.left > pageWidth * 0.65 && rect.width < pageWidth * 0.4) {
      return true;
    }

    return false;
  }

  /** Query within main container, excluding sidebar */
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

  /** Get clean text from main profile area only */
  function getMainProfileText() {
    const main = getMainContainer();
    return getCleanText(main);
  }

  /** Find a section by heading text within main container */
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
    const url = window.location.href;
    const urlParams = new URLSearchParams(window.location.search);
    const sid = urlParams.get('sid');
    if (sid) return `naukri_${sid}`;
    const profileParam = urlParams.get('profile_id') || urlParams.get('profileId') || urlParams.get('id') || urlParams.get('pid');
    if (profileParam) return `naukri_${profileParam}`;
    const urlMatch = url.match(/\/(\d{5,})\/?/);
    if (urlMatch) return `naukri_${urlMatch[1]}`;
    // Hash fallback
    const urlPath = new URL(url).pathname + new URL(url).search;
    let hash = 0;
    for (let i = 0; i < urlPath.length; i++) {
      hash = ((hash << 5) - hash) + urlPath.charCodeAt(i);
      hash |= 0;
    }
    return `naukri_url_${Math.abs(hash).toString(36)}`;
  }

  function extractName() {
    const main = getMainContainer();

    // Strategy 1: Page <title> — Naukri titles are usually "CandidateName - Profile..."
    const pageTitle = document.querySelector('title');
    if (pageTitle) {
      let titleText = pageTitle.textContent;
      // Remove common suffixes
      titleText = titleText.replace(/\s*[-|–]\s*(Profile|Naukri|Resdex|Resume).*$/i, '').trim();
      titleText = titleText.replace(/\s*on\s+Naukri.*$/i, '').trim();
      if (titleText && titleText.length > 2 && titleText.length < 60 &&
          !/naukri|resdex|search|recruiter|login|home/i.test(titleText)) {
        console.log('[VHC Extension] Found name from page title:', titleText);
        return titleText;
      }
    }

    // Strategy 2: The FIRST h1 in main container (main profile name is always h1)
    const h1s = main.querySelectorAll('h1');
    for (const h1 of h1s) {
      if (isInSidebar(h1)) continue;
      const name = cleanText(h1.textContent);
      if (name && name.length > 2 && name.length < 60 && !/similar|suggest|recommend/i.test(name)) {
        console.log('[VHC Extension] Found name from h1:', name);
        return name;
      }
    }

    // Strategy 3: Breadcrumb — last item is usually the candidate name
    const breadcrumb = document.querySelector('[class*="breadcrumb"], [class*="Breadcrumb"]');
    if (breadcrumb) {
      const items = breadcrumb.querySelectorAll('span, a, li');
      if (items.length > 0) {
        const name = cleanText(items[items.length - 1].textContent);
        if (name && name.length > 2 && name.length < 60) {
          console.log('[VHC Extension] Found name from breadcrumb:', name);
          return name;
        }
      }
    }

    // Strategy 4: Look for name-like elements in the TOP portion of main container
    // The main profile name should be near the top of the page
    const candidates = main.querySelectorAll('[class*="name"], [class*="Name"], .name');
    for (const el of candidates) {
      if (isInSidebar(el)) continue;
      const rect = el.getBoundingClientRect();
      // Must be in the top 400px of the page and on the left side
      if (rect.top < 400 && rect.left < window.innerWidth * 0.6) {
        const name = cleanText(el.textContent);
        if (name && name.length > 2 && name.length < 60 && !/company|org|employer/i.test(el.className || '')) {
          console.log('[VHC Extension] Found name from top-positioned element:', name);
          return name;
        }
      }
    }

    console.log('[VHC Extension] Could not find name');
    return null;
  }

  function splitName(fullName) {
    if (!fullName) return {};
    const parts = fullName.trim().split(/\s+/);
    if (parts.length === 1) return { first_name: parts[0] };
    if (parts.length === 2) return { first_name: parts[0], last_name: parts[1] };
    return { first_name: parts[0], middle_name: parts.slice(1, -1).join(' '), last_name: parts[parts.length - 1] };
  }

  function extractEmail() {
    const main = getMainContainer();
    // Look for mailto links
    const mailtoLinks = main.querySelectorAll('a[href^="mailto:"]');
    for (const link of mailtoLinks) {
      if (isInSidebar(link)) continue;
      const email = link.href.replace('mailto:', '').trim().toLowerCase();
      if (email && email.includes('@')) {
        console.log('[VHC Extension] Found email from mailto:', email);
        return email;
      }
    }
    // Look for elements with email-like classes
    const emailEls = main.querySelectorAll('[class*="email"], [class*="Email"], [data-type="email"]');
    for (const el of emailEls) {
      if (isInSidebar(el)) continue;
      const text = el.textContent.trim();
      const m = text.match(/[\w.-]+@[\w.-]+\.\w+/);
      if (m) {
        console.log('[VHC Extension] Found email from element:', m[0]);
        return m[0].toLowerCase();
      }
    }
    // Regex scan of main text
    const mainText = getMainProfileText();
    const matches = mainText.match(/[\w.-]+@[\w.-]+\.(com|in|org|net|co\.in|io)/gi);
    if (matches) {
      for (const email of matches) {
        // Skip recruiter's own email
        if (!email.includes('@vhc.in') && !email.includes('naukri.com')) {
          console.log('[VHC Extension] Found email from text scan:', email);
          return email.toLowerCase();
        }
      }
    }
    console.log('[VHC Extension] Could not find email (may need to click "View" button)');
    return null;
  }

  function extractPhone() {
    const main = getMainContainer();
    const phoneEls = main.querySelectorAll('[class*="phone"], [class*="mobile"], [class*="Phone"], [class*="Mobile"], a[href^="tel:"]');
    for (const el of phoneEls) {
      if (isInSidebar(el)) continue;
      const text = el.href ? el.href.replace('tel:', '') : el.textContent;
      const m = text.match(/(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}/);
      if (m) {
        const phone = m[0].replace(/[\s-]/g, '');
        console.log('[VHC Extension] Found phone:', phone);
        return phone;
      }
    }
    const mainText = getMainProfileText();
    const m = mainText.match(/(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}/);
    if (m) {
      console.log('[VHC Extension] Found phone from text:', m[0]);
      return m[0].replace(/[\s-]/g, '');
    }
    console.log('[VHC Extension] Could not find phone (may need to click "View" button)');
    return null;
  }

  function extractPhotoUrl() {
    const main = getMainContainer();
    const imgs = main.querySelectorAll('img[src*="profile"], img[src*="photo"], img[src*="avatar"], img[class*="photo"], img[class*="avatar"], img[class*="profile"]');
    for (const img of imgs) {
      if (isInSidebar(img)) continue;
      if (img.src && !img.src.includes('default') && !img.src.includes('placeholder') && img.naturalWidth > 30) {
        return img.src;
      }
    }
    return null;
  }

  function extractHeadline() {
    const selectors = ['[class*="headline"]', '[class*="resumeHeadline"]', '[class*="tagline"]'];
    for (const s of selectors) {
      const el = qsMain(s);
      if (el && el.textContent.trim().length > 10) return cleanText(el.textContent);
    }
    return null;
  }

  function extractProfileSummary() {
    const selectors = ['[class*="summary"]', '[class*="Synopsis"]', '[class*="about"]'];
    for (const s of selectors) {
      const el = qsMain(s);
      if (el && el.textContent.trim().length > 30) return cleanText(el.textContent);
    }
    const sec = findSection(['profile summary', 'summary', 'about me', 'about']);
    if (sec) {
      const text = getCleanText(sec);
      if (text && text.length > 30) return cleanText(text);
    }
    return null;
  }

  function extractCurrentEmployment() {
    const result = { company: null, designation: null, department: null, industry: null };
    const mainText = getMainProfileText();

    // Pattern: Look for "Current" section text — but exclude script content
    // Split by newlines and find lines with relevant keywords
    const lines = mainText.split('\n').map(l => l.trim()).filter(l => l.length > 0 && l.length < 200);
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      
      // Company name is often after "at" or standalone near "Current"
      if (/^current$/i.test(line) || /current\s*(company|employer|organization)/i.test(line)) {
        // Next non-empty line might be company
        if (i + 1 < lines.length && lines[i + 1].length > 1 && lines[i + 1].length < 100) {
          if (!result.company) {
            result.company = cleanText(lines[i + 1]);
            console.log('[VHC Extension] Found company from "Current" line:', result.company);
          }
        }
      }
      
      // Designation
      if (/designation|job\s*title|role/i.test(line) && i + 1 < lines.length) {
        const next = lines[i + 1];
        if (next.length > 2 && next.length < 100 && !/window\.|document\.|function/i.test(next)) {
          if (!result.designation) {
            result.designation = cleanText(next);
            console.log('[VHC Extension] Found designation:', result.designation);
          }
        }
      }
    }

    // Fallback: specific elements
    if (!result.company) {
      const el = qsMain('[class*="currentCompany"], [class*="company"], [class*="orgName"], [class*="companyName"], [class*="employer"]');
      if (el) result.company = cleanText(el.textContent);
    }
    if (!result.designation) {
      const el = qsMain('[class*="designation"], [class*="jobTitle"], [class*="currentDesig"]');
      if (el) result.designation = cleanText(el.textContent);
    }

    // Industry from text
    for (const line of lines) {
      const indMatch = line.match(/^Industry[:\s]*(.+)/i);
      if (indMatch && indMatch[1].length < 100) {
        result.industry = cleanText(indMatch[1]);
        break;
      }
    }

    return result;
  }

  function extractTotalExperience() {
    const mainText = getMainProfileText();
    // Look for experience patterns — "X Years Y Months" or "X Yrs"
    const patterns = [
      /(\d+(?:\.\d+)?)\s*(?:Years?|Yrs?)\s*(?:(\d+)\s*(?:Months?|Mos?))?/i,
      /(?:Total|Overall)\s*(?:Experience|Exp)[:\s]*(\d+(?:\.\d+)?)\s*(?:Years?|Yrs?)/i,
      /Experience[:\s]*(\d+(?:\.\d+)?)\s*(?:Years?|Yrs?)/i,
    ];
    for (const p of patterns) {
      const m = mainText.match(p);
      if (m) {
        let years = parseFloat(m[1]);
        if (m[2]) years += parseInt(m[2]) / 12;
        console.log('[VHC Extension] Found experience years:', years);
        return years;
      }
    }
    return null;
  }

  function extractWorkExperience() {
    const experiences = [];
    const sec = findSection(['employment', 'work experience', 'experience']);
    if (!sec) return experiences;

    // Look for repeated blocks — each job entry
    const entries = sec.querySelectorAll('[class*="exp"], [class*="Exp"], [class*="employment"], [class*="Employment"], [class*="work"]');
    const seen = new Set();
    for (const entry of entries) {
      if (isInSidebar(entry)) continue;
      const text = getCleanText(entry);
      if (text.length < 10 || seen.has(text)) continue;
      seen.add(text);
      
      const exp = {};
      // First strong/bold text is usually designation
      const bold = entry.querySelector('strong, b, [class*="title"], [class*="desig"], h3, h4');
      if (bold) exp.designation = cleanText(bold.textContent);
      
      // Company
      const compEl = entry.querySelector('[class*="company"], [class*="org"], [class*="Company"]');
      if (compEl) exp.company = cleanText(compEl.textContent);
      
      // Dates
      const dateEl = entry.querySelector('[class*="duration"], [class*="date"], [class*="period"]');
      if (dateEl) {
        exp.duration = cleanText(dateEl.textContent);
        const fromTo = dateEl.textContent.match(/(\w+[\s']?\d{2,4})\s*[-–to]+\s*(\w+[\s']?\d{2,4}|present|current|till\s*date)/i);
        if (fromTo) {
          exp.from_date = cleanText(fromTo[1]);
          exp.to_date = /present|current|till/i.test(fromTo[2]) ? null : cleanText(fromTo[2]);
          exp.is_current = /present|current|till/i.test(fromTo[2]);
        }
      }
      
      // Description
      const descEl = entry.querySelector('[class*="description"], [class*="desc"], [class*="detail"]');
      if (descEl) exp.description = cleanText(descEl.textContent);
      
      // Location
      const locEl = entry.querySelector('[class*="location"], [class*="city"]');
      if (locEl) exp.location = cleanText(locEl.textContent);

      if (exp.designation || exp.company) experiences.push(exp);
    }
    return experiences;
  }

  function extractEducation() {
    const educations = [];
    const sec = findSection(['education', 'qualification', 'academic']);
    if (!sec) return educations;

    const entries = sec.querySelectorAll('[class*="edu"], [class*="Edu"], [class*="qual"], [class*="Qual"]');
    for (const entry of entries) {
      if (isInSidebar(entry)) continue;
      const edu = {};
      const degreeEl = entry.querySelector('[class*="degree"], [class*="course"], h3, h4, strong, b');
      if (degreeEl) edu.degree = cleanText(degreeEl.textContent);
      const instEl = entry.querySelector('[class*="institution"], [class*="university"], [class*="college"]');
      if (instEl) edu.institution = cleanText(instEl.textContent);
      const yearEl = entry.querySelector('[class*="year"], [class*="passout"]');
      if (yearEl) {
        const ym = yearEl.textContent.match(/(\d{4})/);
        if (ym) edu.year_of_passing = ym[1];
      }
      if (edu.degree || edu.institution) educations.push(edu);
    }
    return educations;
  }

  function extractKeySkills() {
    const skills = new Set();
    const sec = findSection(['key skills', 'skills']);
    if (sec) {
      const chips = sec.querySelectorAll('span, a, [class*="chip"], [class*="tag"], [class*="skill"], [class*="Skill"]');
      chips.forEach(el => {
        if (isInSidebar(el)) return;
        const skill = cleanText(el.textContent);
        if (skill && skill.length > 1 && skill.length < 50 && !/key\s*skills?|skills?:/i.test(skill)) {
          skills.add(skill);
        }
      });
    }
    // Fallback: look for skill containers anywhere in main
    if (skills.size === 0) {
      const containers = qsaMain('[class*="keySkill"], [class*="KeySkill"], [class*="skill-list"], [class*="skillList"]');
      for (const container of containers) {
        const chips = container.querySelectorAll('span, a');
        chips.forEach(el => {
          const skill = cleanText(el.textContent);
          if (skill && skill.length > 1 && skill.length < 50) skills.add(skill);
        });
      }
    }
    console.log('[VHC Extension] Found skills:', skills.size);
    return [...skills];
  }

  function extractITSkills() {
    const itSkills = [];
    const sec = findSection(['it skills', 'technical skills', 'software skills']);
    if (!sec) return itSkills;
    const rows = sec.querySelectorAll('tr, [class*="skillRow"], [class*="row"]');
    for (const row of rows) {
      const cells = row.querySelectorAll('td, [class*="cell"], span');
      if (cells.length >= 2) {
        const skill = {
          name: cleanText(cells[0]?.textContent),
          version: cleanText(cells[1]?.textContent),
          last_used: cells.length > 2 ? cleanText(cells[2]?.textContent) : null,
          experience_years: null
        };
        if (cells.length > 3) {
          const m = (cells[3]?.textContent || '').match(/(\d+)/);
          if (m) skill.experience_years = parseInt(m[1]);
        }
        if (skill.name && skill.name.length > 1) itSkills.push(skill);
      }
    }
    return itSkills;
  }

  function extractCertifications() {
    const certs = [];
    const sec = findSection(['certification', 'certificate']);
    if (!sec) return certs;
    const entries = sec.querySelectorAll('[class*="cert"], li, [class*="item"]');
    for (const entry of entries) {
      if (isInSidebar(entry)) continue;
      const nameEl = entry.querySelector('h4, h3, strong, b, [class*="name"]') || entry;
      const name = cleanText(nameEl.textContent);
      if (name && name.length > 2 && name.length < 200) {
        const cert = { name };
        const authEl = entry.querySelector('[class*="authority"], [class*="issuer"]');
        if (authEl) cert.issuing_authority = cleanText(authEl.textContent);
        certs.push(cert);
      }
    }
    return certs;
  }

  function extractProjects() {
    const projects = [];
    const sec = findSection(['project']);
    if (!sec) return projects;
    const entries = sec.querySelectorAll('[class*="project"], [class*="Project"], li');
    for (const entry of entries) {
      if (isInSidebar(entry)) continue;
      const titleEl = entry.querySelector('h4, h3, strong, b, [class*="title"]') || entry;
      const title = cleanText(titleEl.textContent);
      if (title && title.length > 2 && title.length < 200) {
        const proj = { title };
        const descEl = entry.querySelector('[class*="description"], [class*="desc"]');
        if (descEl) proj.description = cleanText(descEl.textContent);
        projects.push(proj);
      }
    }
    return projects;
  }

  function extractLanguages() {
    const langs = [];
    const sec = findSection(['language']);
    if (!sec) return langs;
    const entries = sec.querySelectorAll('[class*="lang"], li, tr');
    for (const entry of entries) {
      if (isInSidebar(entry)) continue;
      const text = cleanText(entry.textContent);
      if (!text || text.length < 2 || /languages?:/i.test(text)) continue;
      const lang = { language: text };
      const profMatch = text.match(/(beginner|proficient|expert|native|fluent|intermediate)/i);
      if (profMatch) {
        lang.proficiency = profMatch[1];
        lang.language = cleanText(text.replace(profMatch[0], ''));
      }
      if (lang.language) langs.push(lang);
    }
    return langs;
  }

  function extractOnlineProfiles() {
    const profiles = [];
    const sec = findSection(['online profile', 'social profile', 'portfolio']);
    if (sec) {
      const links = sec.querySelectorAll('a[href]');
      for (const link of links) {
        const url = link.href;
        if (!url || url.includes('naukri.com')) continue;
        let platform = 'Other';
        if (url.includes('linkedin')) platform = 'LinkedIn';
        else if (url.includes('github')) platform = 'GitHub';
        else if (url.includes('twitter') || url.includes('x.com')) platform = 'Twitter';
        profiles.push({ platform, url });
      }
    }
    return profiles;
  }

  function extractPersonalDetails() {
    const details = {};
    const mainText = getMainProfileText();
    const lines = mainText.split('\n').map(l => l.trim());

    const patterns = {
      date_of_birth: /(?:DOB|Date\s*of\s*Birth|Born)[:\s]*([^\n|,]+)/i,
      gender: /Gender[:\s]*(Male|Female|Other|Transgender)/i,
      marital_status: /(?:Marital\s*Status)[:\s]*(Single|Married|Unmarried|Divorced|Widowed|Separated)/i,
      nationality: /Nationality[:\s]*([^\n|,]+)/i,
      category: /Category[:\s]*(General|OBC|SC|ST|EWS|[^\n|,]{2,20})/i,
    };

    for (const [key, regex] of Object.entries(patterns)) {
      const m = mainText.match(regex);
      if (m) details[key] = cleanText(m[1]);
    }

    if (/passport/i.test(mainText)) {
      details.has_passport = true;
    }

    return Object.keys(details).length > 0 ? details : null;
  }

  function extractCareerPreferences() {
    const prefs = {};
    const mainText = getMainProfileText();
    const lines = mainText.split('\n').map(l => l.trim()).filter(l => l.length > 0 && l.length < 200);

    // Salary — look for "Rs X Lacs" or "X LPA" or just numeric values near salary keywords
    for (const line of lines) {
      if (/current\s*(ctc|salary|annual)/i.test(line) || /ctc/i.test(line)) {
        const m = line.match(/(?:₹|Rs\.?\s*)?(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA|L|PA)/i);
        if (m) {
          prefs.current_salary = Math.round(parseFloat(m[1].replace(/,/g, '')) * 100000);
          console.log('[VHC Extension] Found current salary:', prefs.current_salary);
          break;
        }
        // Try plain number (in lakhs)
        const m2 = line.match(/(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA|L)/i);
        if (m2) {
          prefs.current_salary = Math.round(parseFloat(m2[1]) * 100000);
          console.log('[VHC Extension] Found current salary:', prefs.current_salary);
          break;
        }
      }
    }

    // Expected salary
    for (const line of lines) {
      if (/expected|expects?/i.test(line)) {
        const m = line.match(/(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA|L)/i);
        if (m) {
          prefs.expected_salary = Math.round(parseFloat(m[1]) * 100000);
          break;
        }
      }
    }

    // Notice period
    const noticeMatch = mainText.match(/Notice\s*(?:Period)?[:\s]*(\d+\s*(?:Month|Day|Week)s?|Immediate(?:ly)?)/i);
    if (noticeMatch) {
      prefs.notice_period = cleanText(noticeMatch[1]);
      if (prefs.notice_period.toLowerCase().includes('immediate')) prefs.notice_period = 'Immediate';
      console.log('[VHC Extension] Found notice period:', prefs.notice_period);
    }

    if (/serving\s*notice/i.test(mainText)) prefs.is_serving_notice = true;

    // Location
    const locEl = qsMain('[class*="location"], [class*="Location"], [class*="city"], [class*="City"]');
    if (locEl) prefs.current_location = cleanText(locEl.textContent);
    
    if (!prefs.current_location) {
      const locMatch = mainText.match(/(?:Current\s*)?Location[:\s]*([A-Za-z\s,]+?)(?:\s*\||$|\n)/i);
      if (locMatch) prefs.current_location = cleanText(locMatch[1]);
    }

    // Preferred locations
    const prefLocMatch = mainText.match(/Pref(?:erred)?\.?\s*(?:locations?|loc)[:\s]*([^\n]+)/i);
    if (prefLocMatch) {
      prefs.preferred_locations = prefLocMatch[1].split(/[,\/]/).map(l => cleanText(l)).filter(Boolean);
    }

    return Object.keys(prefs).length > 0 ? prefs : null;
  }

  // ===================== MAIN SCRAPING FUNCTION =====================

  async function scrapeProfileData() {
    console.log('[VHC Extension] Scraping profile data from MAIN profile area...');

    const name = extractName();
    const nameParts = splitName(name);
    const currentEmployment = extractCurrentEmployment();
    const careerPreferences = extractCareerPreferences();
    const personalDetails = extractPersonalDetails();
    const onlineProfiles = extractOnlineProfiles();
    const totalExp = extractTotalExperience();

    const data = {
      naukri_profile_id: extractNaukriProfileId(),
      naukri_profile_url: window.location.href,
      naukri_resume_id: null,
      name: name,
      first_name: nameParts.first_name || null,
      middle_name: nameParts.middle_name || null,
      last_name: nameParts.last_name || null,
      photo_url: extractPhotoUrl(),
      email: extractEmail(),
      alternate_email: null,
      phone: extractPhone(),
      alternate_phone: null,
      headline: extractHeadline(),
      resume_headline: extractHeadline(),
      profile_summary: extractProfileSummary(),
      current_company: currentEmployment.company,
      current_designation: currentEmployment.designation,
      current_department: currentEmployment.department,
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
      github_url: (onlineProfiles.find(p => p.platform === 'GitHub') || {}).url || null,
      personal_details: personalDetails,
      career_preferences: careerPreferences,
      has_resume: !!document.querySelector('[class*="download"], [class*="attachedCV"], [class*="resumeDownload"]'),
      scraped_at: new Date().toISOString()
    };

    if (data.education.length > 0) {
      data.highest_qualification = data.education[0].degree;
    }

    console.log('[VHC Extension] Extracted data summary: ', {
      name: data.name,
      email: data.email,
      phone: data.phone,
      company: data.current_company,
      skills: data.key_skills?.length || 0,
      experience: data.work_experience?.length || 0,
      education: data.education?.length || 0,
    });

    console.log('[VHC Extension] Scraped profile:', data.name);
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
    console.log('[VHC Extension] Scrolling to load content...');
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
    console.log('[VHC Extension] Scroll complete');
  }

  async function manualCapture() {
    if (isCapturing) return { success: false, error: 'Capture already in progress' };
    if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Extension context invalidated. Please refresh.' }; }
    isCapturing = true;
    console.log('[VHC Extension] Manual capture triggered');
    try {
      const auth = await getAuthToken();
      if (!auth) return { success: false, error: 'Not logged in to VHC. Please login via extension popup.' };

      showToast('Capturing profile...', 'info');
      await scrollToLoadContent();
      await sleep(1000);

      const profileData = await scrapeProfileData();
      if (!profileData || !profileData.name) {
        return { success: false, error: 'Could not extract profile data. Make sure you are on a profile page.' };
      }

      if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Extension context lost.' }; }

      const response = await chrome.runtime.sendMessage({ action: 'captureProfile', data: profileData });
      if (response && response.success) {
        lastCapturedUrl = window.location.href;
        const msgs = { created: 'added to VHC!', updated: 'profile updated!', exists: 'already up-to-date', queued: 'queued for sync' };
        showToast(`${profileData.name} ${msgs[response.action] || 'captured'}`, response.action === 'created' ? 'success' : 'info');
        return { success: true, action: response.action, name: profileData.name };
      } else {
        showToast(response?.error || 'Unknown error', 'error');
        return { success: false, error: response?.error };
      }
    } catch (error) {
      if (error.message?.includes('Extension context invalidated')) {
        handleInvalidContext();
      } else {
        showToast(`Error: ${error.message}`, 'error');
      }
      return { success: false, error: error.message };
    } finally {
      isCapturing = false;
    }
  }

  async function captureProfile() {
    if (isCapturing || lastCapturedUrl === window.location.href) return;
    if (!isExtensionValid()) return;
    isCapturing = true;
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
          else if (response.action === 'updated') showToast(`${profileData.name} profile updated`, 'info');
        }
      }
    } catch (error) {
      if (!error.message?.includes('Extension context invalidated')) {
        console.error('[VHC Extension] Capture error:', error);
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

  // ===================== UI ELEMENTS =====================

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
    console.log('[VHC Extension] Floating button added');
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
    setTimeout(() => {
      toast.classList.remove('vhc-toast-show');
      setTimeout(() => toast.remove(), 300);
    }, CONFIG.TOAST_DURATION);
  }

  // ===================== HELPERS =====================

  async function getSettings() {
    if (!isExtensionValid()) return { enabled: true, showNotifications: true, autoCapture: true };
    try {
      return await new Promise((resolve, reject) => {
        chrome.storage.sync.get({ enabled: true, showNotifications: true, autoCapture: true }, (result) => {
          if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
          else resolve(result);
        });
      });
    } catch (e) {
      return { enabled: true, showNotifications: true, autoCapture: true };
    }
  }

  async function getAuthToken() {
    if (!isExtensionValid()) { handleInvalidContext(); return null; }
    try {
      return await new Promise((resolve, reject) => {
        chrome.storage.sync.get(['vhc_token', 'vhc_api_url'], (result) => {
          if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
          else resolve(result.vhc_token && result.vhc_api_url ? { token: result.vhc_token, apiUrl: result.vhc_api_url } : null);
        });
      });
    } catch (e) {
      handleInvalidContext();
      return null;
    }
  }

  // ===================== INIT =====================

  async function init() {
    console.log('[VHC Extension] Initializing...');
    addFloatingButton();
    const settings = await getSettings();
    if (!settings.enabled) return;
    const auth = await getAuthToken();
    if (!auth) return;
    if (!isProfilePage()) return;
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
