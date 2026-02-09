/**
 * VHC Talent OS - Naukri Profile Scraper v2.0
 * Content script that runs on Naukri profile pages
 * Captures ALL available data fields for 1:1 profile matching
 *
 * Output format matches CompleteNaukriProfileInput backend schema exactly.
 */

(function() {
  'use strict';

  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  const CONFIG = {
    CAPTURE_DELAY: 3000,
    SCROLL_DELAY: 500,
    TOAST_DURATION: 4000,
    RETRY_ATTEMPTS: 3
  };

  let isCapturing = false;
  let lastCapturedUrl = null;

  console.log('[VHC Extension] Content script v2.0 loaded on:', window.location.href);

  // ===================== EXTENSION CONTEXT GUARD =====================

  function isExtensionValid() {
    try {
      return !!(chrome && chrome.runtime && chrome.runtime.id);
    } catch (e) {
      return false;
    }
  }

  function handleInvalidContext() {
    showToast('Extension was updated. Please refresh this page (F5) to reconnect.', 'error');
  }

  // ===================== UTILITY HELPERS =====================

  function cleanText(text) {
    if (!text) return null;
    return text.replace(/\s+/g, ' ').replace(/[\n\r\t]/g, ' ').trim() || null;
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function isInSidebar(element) {
    if (!element) return false;
    const patterns = [
      'sidebar', 'rightsec', 'similar', 'matched', 'recommendation',
      'aimatched', 'recruitersviewed', 'rightsection', 'comment',
      'relatedprofile', 'othercandidate'
    ];
    let parent = element;
    while (parent && parent !== document.body) {
      const cls = (parent.className || '').toLowerCase();
      const id = (parent.id || '').toLowerCase();
      for (const p of patterns) {
        if (cls.includes(p) || id.includes(p)) return true;
      }
      parent = parent.parentElement;
    }
    return false;
  }

  function isUserOwnContact(email) {
    if (!email) return false;
    const headerArea = document.querySelector('header, nav, .header, .navbar, [class*="Header"]');
    if (headerArea && headerArea.innerText.toLowerCase().includes(email.toLowerCase())) return true;
    if (email.includes('@vhc.in')) return true;
    return false;
  }

  /** Get all visible text from the main profile area (exclude sidebar). */
  function getMainProfileText() {
    const main = document.querySelector('.leftSection, .mainContent, .profileContent, main, article');
    return main ? main.innerText : document.body.innerText;
  }

  /** Query selector scoped to main profile area only. */
  function qsMain(selector) {
    const els = document.querySelectorAll(selector);
    for (const el of els) {
      if (!isInSidebar(el)) return el;
    }
    return null;
  }

  /** Query selector ALL scoped to main profile area. */
  function qsaMain(selector) {
    return [...document.querySelectorAll(selector)].filter(el => !isInSidebar(el));
  }

  // ===================== SECTION FINDER =====================

  /**
   * Naukri Resdex profile pages are organized into labelled sections.
   * This helper finds a section by its heading text and returns the
   * container element so we can extract structured data from it.
   */
  function findSection(headingTexts) {
    if (!Array.isArray(headingTexts)) headingTexts = [headingTexts];
    const headings = qsaMain('h2, h3, h4, .sectionTitle, [class*="sectionTitle"], [class*="SectionTitle"], .heading, [class*="heading"]');
    for (const h of headings) {
      const hText = (h.textContent || '').trim().toLowerCase();
      for (const target of headingTexts) {
        if (hText.includes(target.toLowerCase())) {
          // Return the parent section container
          return h.closest('section, .section, [class*="Section"], [class*="section"]') || h.parentElement;
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
    const urlMatch = url.match(/\/(\d+)\/?(\?|$|&)/);
    if (urlMatch) return `naukri_${urlMatch[1]}`;
    const mainArea = document.querySelector('.leftSection, .mainContent, .profileContent');
    if (mainArea) {
      const profileIdEl = mainArea.querySelector('[data-profile-id], [id*="profileId"]');
      if (profileIdEl) {
        const id = profileIdEl.getAttribute('data-profile-id') || profileIdEl.id;
        if (id) return `naukri_${id}`;
      }
    }
    return `naukri_${btoa(url).replace(/[^a-zA-Z0-9]/g, '').substring(0, 20)}`;
  }

  function extractName() {
    // Breadcrumb — most reliable for Resdex
    const breadcrumb = document.querySelector('.breadcrumb, [class*="breadcrumb"], [class*="Breadcrumb"]');
    if (breadcrumb) {
      const items = breadcrumb.querySelectorAll('span, a, li');
      if (items.length > 0) {
        const name = cleanText(items[items.length - 1].textContent);
        if (name && name.length > 2 && name.length < 60 && !name.includes('Similar') && !name.includes('profile')) {
          return name;
        }
      }
    }
    // Page header
    const pageTitle = qsMain('h1, [class*="profileTitle"], [class*="candidateName"]');
    if (pageTitle) {
      const name = cleanText(pageTitle.textContent);
      if (name && name.length > 2 && name.length < 60) return name;
    }
    // Specific selectors
    const selectors = [
      '.profileCard .name', '.leftSection .name', '.mainContent .name',
      '[class*="leftSec"] .name', '[class*="profileCard"] .name'
    ];
    for (const s of selectors) {
      const el = qsMain(s);
      if (el) {
        const name = cleanText(el.textContent);
        if (name && name.length > 2 && name.length < 60) return name;
      }
    }
    // Generic .name
    for (const el of qsaMain('.name, [class*="Name"]')) {
      const name = cleanText(el.textContent);
      if (name && name.length > 2 && name.length < 60 && !name.toLowerCase().includes('name:')) return name;
    }
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
    const selectors = ['.email', '[class*="email"]', '[class*="Email"]', 'a[href^="mailto:"]'];
    for (const s of selectors) {
      for (const el of qsaMain(s)) {
        const text = el.href ? el.href.replace('mailto:', '') : el.textContent;
        const m = text.match(/[\w.-]+@[\w.-]+\.\w+/);
        if (m && !isUserOwnContact(m[0])) return m[0].toLowerCase();
      }
    }
    const mainText = getMainProfileText();
    const matches = mainText.match(/[\w.-]+@[\w.-]+\.(com|in|org|net|co\.in|io)/gi);
    if (matches) {
      for (const email of matches) {
        if (!isUserOwnContact(email)) return email.toLowerCase();
      }
    }
    return null;
  }

  function extractPhone() {
    const selectors = ['.phone', '.mobile', '[class*="phone"]', '[class*="mobile"]', '[class*="Phone"]', '[class*="Mobile"]', 'a[href^="tel:"]'];
    for (const s of selectors) {
      for (const el of qsaMain(s)) {
        const text = el.href ? el.href.replace('tel:', '') : el.textContent;
        const m = text.match(/(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}/);
        if (m) return m[0].replace(/[\s-]/g, '');
      }
    }
    const mainText = getMainProfileText();
    const m = mainText.match(/(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}/);
    if (m) return m[0].replace(/[\s-]/g, '');
    return null;
  }

  function extractPhotoUrl() {
    const selectors = [
      '.profile-photo img', '.profilePic img', '.user-image img',
      '[class*="profilePhoto"] img', '.candidate-photo img', '.photo img', '[class*="avatar"] img'
    ];
    for (const s of selectors) {
      const el = qsMain(s);
      if (el && el.src && !el.src.includes('default') && !el.src.includes('placeholder')) return el.src;
    }
    return null;
  }

  function extractHeadline() {
    const selectors = ['.headline', '.resumeHeadline', '.profile-headline', '[class*="headline"]', '.tagline'];
    for (const s of selectors) {
      const el = qsMain(s);
      if (el && el.textContent.trim().length > 10) return cleanText(el.textContent);
    }
    return null;
  }

  function extractProfileSummary() {
    const selectors = ['.summary', '.profileSummary', '.about-me', '.profile-summary', '[class*="summary"]', '.synopsis'];
    for (const s of selectors) {
      const el = qsMain(s);
      if (el && el.textContent.trim().length > 30) return cleanText(el.textContent);
    }
    // Also check labelled section
    const sec = findSection(['profile summary', 'summary', 'about me', 'about']);
    if (sec) {
      const text = cleanText(sec.textContent);
      if (text && text.length > 30) return text;
    }
    return null;
  }

  function extractCurrentEmployment() {
    const result = { company: null, designation: null, department: null, industry: null };
    const pageText = getMainProfileText();

    // Pattern: "Current — Designation at Company since Date"
    const currentMatch = pageText.match(/Current[:\s—-]*(.+?)(?:at|@)\s+(.+?)(?:\s+since|\s*$)/i);
    if (currentMatch) {
      result.designation = cleanText(currentMatch[1]);
      result.company = cleanText(currentMatch[2].replace(/\s+since.*/, ''));
    }

    // Fallback selectors
    if (!result.company) {
      const el = qsMain('.currentCompany, .company, [class*="currentEmployer"], .orgName, [class*="companyName"]');
      if (el) result.company = cleanText(el.textContent);
    }
    if (!result.designation) {
      const el = qsMain('.designation, .currentDesignation, [class*="designation"], .jobTitle, [class*="jobTitle"]');
      if (el) result.designation = cleanText(el.textContent);
    }

    // Industry
    const indMatch = pageText.match(/Industry[:\s]*([^\n|]+)/i);
    if (indMatch) result.industry = cleanText(indMatch[1]);

    // Department
    const deptMatch = pageText.match(/Department[:\s]*([^\n|]+)/i);
    if (deptMatch) result.department = cleanText(deptMatch[1]);

    return result;
  }

  function extractTotalExperience() {
    const pageText = getMainProfileText();
    // "15y", "15 years", "15 yrs"
    const m = pageText.match(/(\d+(?:\.\d+)?)\s*(?:y(?:ears?|rs?)?|yoe)/i);
    if (m) return parseFloat(m[1]);
    const el = qsMain('.experience, .totalExperience, [class*="experience"]');
    if (el) {
      const m2 = el.textContent.match(/(\d+(?:\.\d+)?)\s*(?:years?|yrs?)/i);
      if (m2) return parseFloat(m2[1]);
    }
    return null;
  }

  function extractWorkExperience() {
    const experiences = [];
    // Try to find Experience section
    const sec = findSection(['employment', 'work experience', 'experience']);
    if (!sec) return experiences;

    // Each experience entry is typically a card or repeated block
    const entries = sec.querySelectorAll('.experience-card, .expCard, [class*="expCard"], [class*="ExperienceCard"], [class*="employment-card"], .workExp');
    for (const entry of entries) {
      if (isInSidebar(entry)) continue;
      const exp = {};
      const titleEl = entry.querySelector('.designation, .title, [class*="designation"], [class*="title"], h3, h4');
      if (titleEl) exp.designation = cleanText(titleEl.textContent);
      const compEl = entry.querySelector('.company, .orgName, [class*="company"], [class*="org"]');
      if (compEl) exp.company = cleanText(compEl.textContent);
      const dateEl = entry.querySelector('.duration, .dates, [class*="duration"], [class*="date"]');
      if (dateEl) {
        const dateText = dateEl.textContent;
        exp.duration = cleanText(dateText);
        const fromTo = dateText.match(/(\w+[\s']?\d{2,4})\s*[-–to]+\s*(\w+[\s']?\d{2,4}|present|current)/i);
        if (fromTo) {
          exp.from_date = cleanText(fromTo[1]);
          exp.to_date = fromTo[2].toLowerCase().includes('present') ? null : cleanText(fromTo[2]);
          exp.is_current = fromTo[2].toLowerCase().includes('present') || fromTo[2].toLowerCase().includes('current');
        }
      }
      const descEl = entry.querySelector('.description, .jobDescription, [class*="description"]');
      if (descEl) exp.description = cleanText(descEl.textContent);
      const locEl = entry.querySelector('.location, [class*="location"]');
      if (locEl) exp.location = cleanText(locEl.textContent);

      if (exp.designation || exp.company) {
        experiences.push(exp);
      }
    }

    // Fallback: parse from text if no structured cards found
    if (experiences.length === 0) {
      const text = sec.innerText;
      // Simple heuristic: split by company-like patterns
      const blocks = text.split(/\n(?=[A-Z][\w\s]+(?:at|@)\s)/);
      for (const block of blocks) {
        const atMatch = block.match(/(.+?)(?:at|@)\s+(.+?)(?:\n|$)/);
        if (atMatch) {
          experiences.push({
            designation: cleanText(atMatch[1]),
            company: cleanText(atMatch[2])
          });
        }
      }
    }

    return experiences;
  }

  function extractEducation() {
    const educations = [];
    const sec = findSection(['education', 'qualification', 'academic']);
    if (sec) {
      const entries = sec.querySelectorAll('.education-card, .eduCard, [class*="eduCard"], [class*="EducationCard"], .qualCard');
      for (const entry of entries) {
        if (isInSidebar(entry)) continue;
        const edu = {};
        const degreeEl = entry.querySelector('.degree, .course, [class*="degree"], [class*="course"], h3, h4');
        if (degreeEl) edu.degree = cleanText(degreeEl.textContent);
        const instEl = entry.querySelector('.institution, .university, .college, [class*="institution"], [class*="university"]');
        if (instEl) edu.institution = cleanText(instEl.textContent);
        const yearEl = entry.querySelector('.year, .passout, [class*="year"], [class*="passout"]');
        if (yearEl) {
          const ym = yearEl.textContent.match(/(\d{4})/);
          if (ym) edu.year_of_passing = ym[1];
        }
        const scoreEl = entry.querySelector('.score, .percentage, .cgpa, [class*="score"], [class*="grade"]');
        if (scoreEl) edu.score = cleanText(scoreEl.textContent);
        const typeEl = entry.querySelector('[class*="courseType"], [class*="fullTime"]');
        if (typeEl) edu.degree_type = cleanText(typeEl.textContent);

        if (edu.degree || edu.institution) educations.push(edu);
      }
    }

    // Fallback: look for "Highest degree" line
    if (educations.length === 0) {
      const pageText = getMainProfileText();
      const m = pageText.match(/Highest\s*(?:degree|qualification)[:\s]*([^\n]+)/i);
      if (m) educations.push({ degree: cleanText(m[1]) });
    }

    return educations;
  }

  function extractKeySkills() {
    const skills = new Set();
    const selectors = ['.keySkills', '.skills', '[class*="keySkill"]', '[class*="KeySkill"]'];
    for (const s of selectors) {
      const container = qsMain(s);
      if (container) {
        const chips = container.querySelectorAll('span, .chip, .tag, a, [class*="skill"], [class*="chip"]');
        chips.forEach(el => {
          const skill = cleanText(el.textContent);
          if (skill && skill.length > 1 && skill.length < 50) skills.add(skill);
        });
      }
    }

    // Also look for skills in a labelled section
    const sec = findSection(['key skills', 'skills']);
    if (sec) {
      const chips = sec.querySelectorAll('span, .chip, .tag, a');
      chips.forEach(el => {
        const skill = cleanText(el.textContent);
        if (skill && skill.length > 1 && skill.length < 50) skills.add(skill);
      });
    }

    return [...skills];
  }

  function extractITSkills() {
    const itSkills = [];
    const sec = findSection(['it skills', 'technical skills', 'software skills']);
    if (!sec) return itSkills;

    // IT skills are often in a table: Skill | Version | Last Used | Experience
    const rows = sec.querySelectorAll('tr, .skillRow, [class*="skillRow"]');
    for (const row of rows) {
      const cells = row.querySelectorAll('td, .cell, span');
      if (cells.length >= 2) {
        const skill = {
          name: cleanText(cells[0]?.textContent),
          version: cleanText(cells[1]?.textContent),
          last_used: cells.length > 2 ? cleanText(cells[2]?.textContent) : null,
          experience_years: null
        };
        if (cells.length > 3) {
          const expMatch = (cells[3]?.textContent || '').match(/(\d+)/);
          if (expMatch) skill.experience_years = parseInt(expMatch[1]);
        }
        if (skill.name) itSkills.push(skill);
      }
    }
    return itSkills;
  }

  function extractCertifications() {
    const certs = [];
    const sec = findSection(['certification', 'certificate']);
    if (!sec) return certs;

    const entries = sec.querySelectorAll('.certCard, [class*="certCard"], [class*="CertCard"], .certification-item, li');
    for (const entry of entries) {
      if (isInSidebar(entry)) continue;
      const cert = {};
      const nameEl = entry.querySelector('.name, .certName, h4, h3, [class*="name"]') || entry;
      cert.name = cleanText(nameEl.textContent);
      const authEl = entry.querySelector('.authority, .issuer, [class*="authority"], [class*="issuer"]');
      if (authEl) cert.issuing_authority = cleanText(authEl.textContent);
      const dateEl = entry.querySelector('.date, [class*="date"]');
      if (dateEl) cert.issue_date = cleanText(dateEl.textContent);
      if (cert.name && cert.name.length > 2) certs.push(cert);
    }
    return certs;
  }

  function extractProjects() {
    const projects = [];
    const sec = findSection(['project']);
    if (!sec) return projects;

    const entries = sec.querySelectorAll('.projectCard, [class*="projectCard"], [class*="ProjectCard"], li');
    for (const entry of entries) {
      if (isInSidebar(entry)) continue;
      const proj = {};
      const titleEl = entry.querySelector('.title, .projectTitle, h4, h3, [class*="title"]') || entry;
      proj.title = cleanText(titleEl.textContent);
      const descEl = entry.querySelector('.description, [class*="description"]');
      if (descEl) proj.description = cleanText(descEl.textContent);
      const statusEl = entry.querySelector('.status, [class*="status"]');
      if (statusEl) proj.status = cleanText(statusEl.textContent);
      const roleEl = entry.querySelector('.role, [class*="role"]');
      if (roleEl) proj.role = cleanText(roleEl.textContent);
      if (proj.title && proj.title.length > 2) projects.push(proj);
    }
    return projects;
  }

  function extractLanguages() {
    const langs = [];
    const sec = findSection(['language']);
    if (!sec) return langs;

    const entries = sec.querySelectorAll('.langRow, [class*="langRow"], [class*="language-item"], li, tr');
    for (const entry of entries) {
      if (isInSidebar(entry)) continue;
      const text = cleanText(entry.textContent);
      if (!text || text.length < 2) continue;
      const lang = { language: text };
      const profMatch = text.match(/(beginner|proficient|expert|native|fluent|intermediate)/i);
      if (profMatch) {
        lang.proficiency = profMatch[1];
        lang.language = cleanText(text.replace(profMatch[0], ''));
      }
      // Read/Write/Speak checkboxes
      const checks = entry.querySelectorAll('input[type="checkbox"]:checked, .checked, [class*="checked"]');
      const labels = entry.querySelectorAll('.label, td, span');
      const fullText = entry.textContent.toLowerCase();
      lang.read = fullText.includes('read');
      lang.write = fullText.includes('write');
      lang.speak = fullText.includes('speak');
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
        else if (url.includes('stackoverflow')) platform = 'StackOverflow';
        profiles.push({ platform, url });
      }
    }
    // Also scan for LinkedIn/GitHub links anywhere in main area
    for (const a of qsaMain('a[href*="linkedin.com"], a[href*="github.com"]')) {
      const url = a.href;
      const platform = url.includes('linkedin') ? 'LinkedIn' : 'GitHub';
      if (!profiles.some(p => p.url === url)) {
        profiles.push({ platform, url });
      }
    }
    return profiles;
  }

  function extractPersonalDetails() {
    const details = {};
    const pageText = getMainProfileText();
    const sec = findSection(['personal detail', 'personal info']);
    const text = sec ? sec.innerText : pageText;

    const patterns = {
      date_of_birth: /(?:DOB|Date\s*of\s*Birth|Born)[:\s]*([^\n|,]+)/i,
      gender: /Gender[:\s]*(Male|Female|Other|Transgender)/i,
      marital_status: /(?:Marital\s*Status|Married)[:\s]*(Single|Married|Unmarried|Divorced|Widowed|Separated)/i,
      nationality: /Nationality[:\s]*([^\n|,]+)/i,
      category: /Category[:\s]*(General|OBC|SC|ST|EWS|[^\n|,]+)/i,
    };

    for (const [key, regex] of Object.entries(patterns)) {
      const m = text.match(regex);
      if (m) details[key] = cleanText(m[1]);
    }

    // Passport
    if (/passport/i.test(text)) {
      details.has_passport = true;
      const passMatch = text.match(/Passport\s*(?:No|Number)?[:\s]*([A-Z0-9]+)/i);
      if (passMatch) details.passport_number = passMatch[1];
    }

    // Address
    const addrMatch = text.match(/(?:Current\s*)?Address[:\s]*([^\n]+)/i);
    if (addrMatch) details.current_address = cleanText(addrMatch[1]);

    // Differently abled
    if (/differently\s*abled[:\s]*yes/i.test(text)) {
      details.differently_abled = true;
    }

    return Object.keys(details).length > 0 ? details : null;
  }

  function extractCareerPreferences() {
    const prefs = {};
    const pageText = getMainProfileText();

    // Current salary — "Rs X Lacs" / "X LPA"
    const salaryMatch = pageText.match(/(?:Current\s*(?:CTC|Salary|Annual\s*Salary))[:\s]*(?:Rs\.?\s*|INR\s*)?(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA|L)/i);
    if (salaryMatch) {
      prefs.current_salary = Math.round(parseFloat(salaryMatch[1]) * 100000);
    } else {
      // Try standalone salary pattern near top
      const m = pageText.match(/(?:₹|Rs\.?\s*)(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA)/i);
      if (m) prefs.current_salary = Math.round(parseFloat(m[1]) * 100000);
    }

    // Expected salary
    const expMatch = pageText.match(/(?:Expected|Expects?)[:\s]*(?:₹|Rs\.?\s*)?(\d+(?:\.\d+)?)\s*(?:Lacs?|Lakh|LPA)/i);
    if (expMatch) prefs.expected_salary = Math.round(parseFloat(expMatch[1]) * 100000);

    // Notice period
    const noticePatterns = [
      /Notice\s*(?:Period)?[:\s]*(\d+\s*(?:Month|Day|Week)s?|Immediate(?:ly)?)/i,
      /(\d+)\s*(?:Month|Months)\s*(?:notice)?/i,
      /(Immediate(?:ly)?)/i
    ];
    for (const p of noticePatterns) {
      const m = pageText.match(p);
      if (m) {
        let notice = m[1].trim();
        if (notice.toLowerCase().includes('immediate')) notice = 'Immediate';
        prefs.notice_period = notice;
        break;
      }
    }
    // Serving notice
    if (/serving\s*notice/i.test(pageText)) prefs.is_serving_notice = true;

    // Current location
    const locMatch = pageText.match(/(?:Current\s*Location|Location)[:\s]*([A-Za-z\s,]+?)(?:\s*\||$|\n)/i);
    if (locMatch) prefs.current_location = cleanText(locMatch[1]);
    if (!prefs.current_location) {
      // Try emoji location indicator
      const emojiLoc = pageText.match(/📍\s*([A-Za-z\s,]+?)(?:\s*\||$|\n)/);
      if (emojiLoc) prefs.current_location = cleanText(emojiLoc[1]);
    }
    if (!prefs.current_location) {
      const el = qsMain('.location, .currentLocation, [class*="location"], .city, [class*="Location"]');
      if (el) prefs.current_location = cleanText(el.textContent);
    }

    // Preferred locations
    const prefLocMatch = pageText.match(/Pref(?:erred)?\.?\s*(?:locations?|loc)[:\s]*([^\n+]+)/i);
    if (prefLocMatch) {
      prefs.preferred_locations = prefLocMatch[1].split(/[,\/]/).map(l => cleanText(l)).filter(Boolean);
    }

    // Preferred industry
    const indMatch = pageText.match(/(?:Preferred\s*)?Industry[:\s]*([^\n|]+)/i);
    if (indMatch) {
      prefs.preferred_industry = indMatch[1].split(/[,\/]/).map(i => cleanText(i)).filter(Boolean);
    }

    // Functional area
    const faMatch = pageText.match(/Functional\s*Area[:\s]*([^\n|]+)/i);
    if (faMatch) {
      prefs.preferred_functional_area = faMatch[1].split(/[,\/]/).map(f => cleanText(f)).filter(Boolean);
    }

    // Role category
    const roleMatch = pageText.match(/Role\s*(?:Category)?[:\s]*([^\n|]+)/i);
    if (roleMatch) {
      prefs.preferred_role = roleMatch[1].split(/[,\/]/).map(r => cleanText(r)).filter(Boolean);
    }

    return Object.keys(prefs).length > 0 ? prefs : null;
  }

  function extractProfileLastUpdated() {
    const selectors = ['.lastUpdatedOn', '.profileLastUpdated', '.updateDate', '[class*="lastUpdate"]', '[class*="Modified"]', '[class*="Active"]'];
    for (const s of selectors) {
      const el = qsMain(s);
      if (el) {
        const text = el.textContent.trim();
        const dateMatch = text.match(/(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})/);
        if (dateMatch) return dateMatch[1];
        if (/today|active today/i.test(text)) return new Date().toISOString().split('T')[0];
      }
    }
    return null;
  }

  function extractResumeInfo() {
    const downloadBtn = document.querySelector('[class*="download"], .downloadResume, [class*="attachedCV"], [class*="resumeDownload"]');
    const hasResume = !!downloadBtn;
    let title = null;
    const titleEl = qsMain('[class*="resumeTitle"], .resumeTitle');
    if (titleEl) title = cleanText(titleEl.textContent);
    return { has_resume: hasResume, resume_title: title };
  }

  /** Capture raw text of each major section for debugging */
  function extractRawSections() {
    const sections = {};
    const sectionNames = ['employment', 'education', 'key skills', 'it skills', 'certification', 'project', 'personal detail', 'career profile', 'online profile', 'language'];
    for (const name of sectionNames) {
      const sec = findSection([name]);
      if (sec) sections[name] = sec.innerText.substring(0, 2000);
    }
    return Object.keys(sections).length > 0 ? sections : null;
  }

  // ===================== MAIN SCRAPING FUNCTION =====================

  async function scrapeProfileData() {
    console.log('[VHC Extension] Scraping COMPLETE profile data...');

    const name = extractName();
    const nameParts = splitName(name);
    const currentEmployment = extractCurrentEmployment();
    const careerPreferences = extractCareerPreferences();
    const personalDetails = extractPersonalDetails();
    const onlineProfiles = extractOnlineProfiles();
    const resumeInfo = extractResumeInfo();
    const totalExp = extractTotalExperience();

    // Build the data object matching CompleteNaukriProfileInput exactly
    const data = {
      // Naukri Identification
      naukri_profile_id: extractNaukriProfileId(),
      naukri_profile_url: window.location.href,
      naukri_resume_id: null,

      // Basic Info
      name: name,
      first_name: nameParts.first_name || null,
      middle_name: nameParts.middle_name || null,
      last_name: nameParts.last_name || null,
      photo_url: extractPhotoUrl(),

      // Contact
      email: extractEmail(),
      alternate_email: null,
      phone: extractPhone(),
      alternate_phone: null,

      // Professional Identity
      headline: extractHeadline(),
      resume_headline: extractHeadline(),
      profile_summary: extractProfileSummary(),

      // Current Employment
      current_company: currentEmployment.company,
      current_designation: currentEmployment.designation,
      current_department: currentEmployment.department,
      current_industry: currentEmployment.industry,
      current_role_category: null,
      employment_status: null,

      // Experience
      total_experience_years: totalExp,
      total_experience_months: totalExp ? Math.round(totalExp * 12) : null,
      total_experience_display: totalExp ? `${totalExp} years` : null,
      work_experience: extractWorkExperience(),

      // Education
      highest_qualification: null,
      highest_degree: null,
      education: extractEducation(),

      // Skills
      key_skills: extractKeySkills(),
      key_skills_display: null,
      it_skills: extractITSkills(),
      soft_skills: [],
      tools: [],

      // Certifications
      certifications: extractCertifications(),

      // Projects
      projects: extractProjects(),

      // Languages
      languages: extractLanguages(),

      // Online Profiles
      online_profiles: onlineProfiles,
      linkedin_url: (onlineProfiles.find(p => p.platform === 'LinkedIn') || {}).url || null,
      github_url: (onlineProfiles.find(p => p.platform === 'GitHub') || {}).url || null,
      portfolio_url: null,

      // Personal Details (nested object)
      personal_details: personalDetails,

      // Career Preferences (nested object)
      career_preferences: careerPreferences,

      // Additional
      accomplishments: null,
      about_me: null,
      additional_info: null,

      // Resume
      has_resume: resumeInfo.has_resume,
      resume_title: resumeInfo.resume_title,
      resume_format: null,

      // Timestamps
      profile_created_on: null,
      profile_last_updated: extractProfileLastUpdated(),
      last_active: null,

      // Activity
      response_rate: null,

      // Raw data for debugging
      raw_profile_text: getMainProfileText().substring(0, 5000),
      raw_sections: extractRawSections(),

      // Scrape metadata
      scraped_at: new Date().toISOString()
    };

    // Set highest education from first entry
    if (data.education.length > 0) {
      data.highest_qualification = data.education[0].degree;
      data.highest_degree = data.education[0].degree;
    }

    console.log('[VHC Extension] Extracted complete profile:', {
      name: data.name,
      email: data.email,
      phone: data.phone,
      company: data.current_company,
      skills: data.key_skills?.length || 0,
      experience: data.work_experience?.length || 0,
      education: data.education?.length || 0,
      certifications: data.certifications?.length || 0,
      languages: data.languages?.length || 0,
      hasPersonalDetails: !!data.personal_details,
      hasCareerPrefs: !!data.career_preferences
    });

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
  }

  async function manualCapture() {
    if (isCapturing) return { success: false, error: 'Capture already in progress' };
    if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Extension context invalidated. Please refresh the page.' }; }
    isCapturing = true;
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

      if (!isExtensionValid()) { handleInvalidContext(); return { success: false, error: 'Extension context lost during capture.' }; }

      const response = await chrome.runtime.sendMessage({ action: 'captureProfile', data: profileData });
      if (response && response.success) {
        lastCapturedUrl = window.location.href;
        const msgs = { created: 'added to VHC!', updated: 'profile updated!', exists: 'already up-to-date', queued: 'queued for sync' };
        showToast(`${profileData.name} ${msgs[response.action] || 'captured'}`, response.action === 'created' ? 'success' : 'info');
        return { success: true, action: response.action, name: profileData.name };
      } else {
        showToast(response?.error || 'Unknown error', 'error');
        return { success: false, error: response?.error || 'Unknown error' };
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
      if (error.message?.includes('Extension context invalidated')) {
        console.warn('[VHC Extension] Context invalidated during auto-capture. Refresh page to reconnect.');
      } else {
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
      console.warn('[VHC Extension] getSettings failed:', e.message);
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
      console.warn('[VHC Extension] getAuthToken failed:', e.message);
      handleInvalidContext();
      return null;
    }
  }

  // ===================== INIT =====================

  async function init() {
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
