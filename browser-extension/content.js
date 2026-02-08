/**
 * VHC Talent OS - Naukri Profile Scraper
 * Content script that runs on Naukri profile pages
 */

(function() {
  'use strict';

  // Prevent multiple injections
  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  // Configuration
  const CONFIG = {
    CAPTURE_DELAY: 3000,  // 3 seconds to ensure full page load
    SCROLL_DELAY: 500,    // Delay between scrolls
    TOAST_DURATION: 4000, // Toast notification duration
    RETRY_ATTEMPTS: 3
  };

  // State
  let isCapturing = false;
  let lastCapturedUrl = null;

  /**
   * Initialize the extension
   */
  async function init() {
    console.log('[VHC Extension] Initializing on:', window.location.href);
    
    // Check if extension is enabled
    const settings = await getSettings();
    if (!settings.enabled) {
      console.log('[VHC Extension] Auto-capture disabled');
      return;
    }

    // Check if user is logged in
    const auth = await getAuthToken();
    if (!auth) {
      console.log('[VHC Extension] User not logged in to VHC');
      showToast('⚠️ Please login to VHC Talent OS', 'warning');
      return;
    }

    // Wait for page to fully load, including lazy-loaded content
    await waitForPageLoad();
    
    // Scroll to load all content
    await scrollToLoadContent();
    
    // Start capture after delay
    setTimeout(() => captureProfile(), CONFIG.CAPTURE_DELAY);
  }

  /**
   * Wait for page to be fully loaded
   */
  function waitForPageLoad() {
    return new Promise((resolve) => {
      if (document.readyState === 'complete') {
        resolve();
      } else {
        window.addEventListener('load', resolve);
      }
    });
  }

  /**
   * Scroll down the page to trigger lazy loading
   */
  async function scrollToLoadContent() {
    const scrollHeight = document.documentElement.scrollHeight;
    const viewportHeight = window.innerHeight;
    let currentPosition = 0;

    while (currentPosition < scrollHeight) {
      currentPosition += viewportHeight * 0.8;
      window.scrollTo(0, currentPosition);
      await sleep(CONFIG.SCROLL_DELAY);
    }

    // Scroll back to top
    window.scrollTo(0, 0);
    await sleep(500);
  }

  /**
   * Main profile capture function
   */
  async function captureProfile() {
    if (isCapturing) return;
    if (lastCapturedUrl === window.location.href) {
      console.log('[VHC Extension] Already captured this URL');
      return;
    }

    isCapturing = true;
    console.log('[VHC Extension] Starting profile capture...');

    try {
      const profileData = await scrapeProfileData();
      
      if (!profileData || !profileData.name) {
        console.log('[VHC Extension] Could not extract profile data');
        showToast('⚠️ Could not extract profile data', 'warning');
        return;
      }

      console.log('[VHC Extension] Scraped profile:', profileData.name);
      
      // Send to background script for API call
      const response = await chrome.runtime.sendMessage({
        action: 'captureProfile',
        data: profileData
      });

      if (response.success) {
        lastCapturedUrl = window.location.href;
        
        if (response.action === 'created') {
          showToast(`✅ ${profileData.name} added to VHC`, 'success');
        } else if (response.action === 'updated') {
          showToast(`🔄 ${profileData.name} profile updated`, 'info');
        } else if (response.action === 'exists') {
          showToast(`ℹ️ ${profileData.name} already up-to-date`, 'info');
        } else if (response.action === 'queued') {
          showToast(`📥 ${profileData.name} queued for sync`, 'info');
        }
      } else {
        showToast(`❌ Failed: ${response.error}`, 'error');
      }

    } catch (error) {
      console.error('[VHC Extension] Capture error:', error);
      showToast('❌ Error capturing profile', 'error');
    } finally {
      isCapturing = false;
    }
  }

  /**
   * Scrape all profile data from the page
   */
  async function scrapeProfileData() {
    const data = {
      // Source identification
      naukri_profile_id: extractNaukriProfileId(),
      naukri_profile_url: window.location.href,
      naukri_last_updated: extractProfileLastUpdated(),
      scraped_at: new Date().toISOString(),

      // Basic info
      name: extractName(),
      email: extractEmail(),
      phone: extractPhone(),
      photo_url: extractPhotoUrl(),
      
      // Professional info
      headline: extractHeadline(),
      summary: extractSummary(),
      current_company: extractCurrentCompany(),
      current_designation: extractCurrentDesignation(),
      
      // Compensation
      current_salary: extractCurrentSalary(),
      expected_salary: extractExpectedSalary(),
      notice_period: extractNoticePeriod(),
      
      // Location
      location: extractLocation(),
      preferred_locations: extractPreferredLocations(),
      
      // Experience
      experience_years: extractTotalExperience(),
      experience: extractWorkHistory(),
      
      // Education
      education: extractEducation(),
      
      // Skills
      skills: extractKeySkills(),
      skills_detailed: extractDetailedSkills(),
      
      // Additional
      certifications: extractCertifications(),
      projects: extractProjects(),
      languages: extractLanguages(),
      
      // Personal details
      date_of_birth: extractDOB(),
      gender: extractGender(),
      marital_status: extractMaritalStatus(),
      
      // Preferences
      industry_preference: extractIndustryPreference(),
      functional_area: extractFunctionalArea(),
      
      // Resume
      resume_available: checkResumeAvailable()
    };

    return data;
  }

  // ============== EXTRACTION FUNCTIONS ==============

  function extractNaukriProfileId() {
    // Try to extract from URL
    const urlMatch = window.location.href.match(/\/(\d+)\/?(\?|$)/);
    if (urlMatch) return `naukri_${urlMatch[1]}`;
    
    // Try from page content
    const profileIdEl = document.querySelector('[data-profile-id], [id*="profileId"]');
    if (profileIdEl) return `naukri_${profileIdEl.getAttribute('data-profile-id') || profileIdEl.id}`;
    
    // Generate from email if available
    const email = extractEmail();
    if (email) return `naukri_${btoa(email).replace(/[^a-zA-Z0-9]/g, '').substring(0, 20)}`;
    
    return `naukri_${Date.now()}`;
  }

  function extractProfileLastUpdated() {
    const selectors = [
      '.lastUpdatedOn', '.profileLastUpdated', '.updateDate',
      '[class*="lastUpdate"]', '[class*="profileUpdate"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent.trim();
        const dateMatch = text.match(/(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})/);
        if (dateMatch) return dateMatch[1];
      }
    }
    return null;
  }

  function extractName() {
    const selectors = [
      '.name', '.fullname', '.candidate-name', '.profileName',
      'h1[class*="name"]', '.resumeName', '[class*="candidateName"]',
      '.naukri-profile-name', '#name', '.user-name'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && el.textContent.trim()) {
        return cleanText(el.textContent);
      }
    }
    
    // Try meta tags
    const metaName = document.querySelector('meta[name="candidate-name"], meta[property="profile:name"]');
    if (metaName) return metaName.content;
    
    return null;
  }

  function extractEmail() {
    const selectors = [
      '.email', '[class*="email"]', 'a[href^="mailto:"]',
      '.contactEmail', '.profile-email'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.href?.replace('mailto:', '') || el.textContent;
        const emailMatch = text.match(/[\w.-]+@[\w.-]+\.\w+/);
        if (emailMatch) return emailMatch[0].toLowerCase();
      }
    }
    
    // Search in page content
    const pageText = document.body.innerText;
    const emailMatch = pageText.match(/[\w.-]+@[\w.-]+\.(com|in|org|net|co\.in)/i);
    if (emailMatch) return emailMatch[0].toLowerCase();
    
    return null;
  }

  function extractPhone() {
    const selectors = [
      '.phone', '.mobile', '[class*="phone"]', '[class*="mobile"]',
      'a[href^="tel:"]', '.contactNumber'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.href?.replace('tel:', '') || el.textContent;
        const phoneMatch = text.match(/(\+91[\s-]?)?[6-9]\d{9}/);
        if (phoneMatch) return phoneMatch[0].replace(/[\s-]/g, '');
      }
    }
    
    return null;
  }

  function extractPhotoUrl() {
    const selectors = [
      '.profile-photo img', '.profilePic img', '.user-image img',
      '[class*="profilePhoto"] img', '.candidate-photo img'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && el.src && !el.src.includes('default') && !el.src.includes('placeholder')) {
        return el.src;
      }
    }
    return null;
  }

  function extractHeadline() {
    const selectors = [
      '.headline', '.resumeHeadline', '.profile-headline',
      '[class*="headline"]', '.tagline', '.title'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && el.textContent.trim().length > 10) {
        return cleanText(el.textContent);
      }
    }
    return null;
  }

  function extractSummary() {
    const selectors = [
      '.summary', '.profileSummary', '.about-me', '.profile-summary',
      '[class*="summary"]', '[class*="about"]', '.keySkillsSummary'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && el.textContent.trim().length > 50) {
        return cleanText(el.textContent);
      }
    }
    return null;
  }

  function extractCurrentCompany() {
    const selectors = [
      '.currentCompany', '.company', '[class*="currentEmployer"]',
      '.orgName', '.employer', '[class*="companyName"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) return cleanText(el.textContent);
    }
    
    // Try from experience section - first entry
    const expSection = document.querySelector('.experience, [class*="experience"]');
    if (expSection) {
      const companyEl = expSection.querySelector('.company, .orgName, [class*="company"]');
      if (companyEl) return cleanText(companyEl.textContent);
    }
    
    return null;
  }

  function extractCurrentDesignation() {
    const selectors = [
      '.designation', '.currentDesignation', '[class*="designation"]',
      '.jobTitle', '.title', '[class*="jobTitle"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) return cleanText(el.textContent);
    }
    return null;
  }

  function extractCurrentSalary() {
    const selectors = [
      '.currentSalary', '.salary', '[class*="salary"]',
      '[class*="ctc"]', '.annualSalary'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent;
        // Extract number (in lakhs)
        const match = text.match(/(\d+(?:\.\d+)?)\s*(lakh|lac|lpa|l)/i);
        if (match) {
          return Math.round(parseFloat(match[1]) * 100000);
        }
        // Try plain number
        const numMatch = text.match(/(\d+(?:,\d+)*)/);
        if (numMatch) {
          const num = parseInt(numMatch[1].replace(/,/g, ''));
          // If less than 100, assume lakhs
          return num < 100 ? num * 100000 : num;
        }
      }
    }
    return null;
  }

  function extractExpectedSalary() {
    const selectors = [
      '.expectedSalary', '[class*="expected"]', '[class*="expectation"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent;
        const match = text.match(/(\d+(?:\.\d+)?)\s*(lakh|lac|lpa|l)/i);
        if (match) {
          return Math.round(parseFloat(match[1]) * 100000);
        }
      }
    }
    return null;
  }

  function extractNoticePeriod() {
    const selectors = [
      '.noticePeriod', '[class*="notice"]', '.availability'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent.toLowerCase();
        if (text.includes('immediate')) return 'Immediate';
        if (text.includes('15 day')) return '15 Days';
        if (text.includes('1 month') || text.includes('30 day')) return '1 Month';
        if (text.includes('2 month') || text.includes('60 day')) return '2 Months';
        if (text.includes('3 month') || text.includes('90 day')) return '3 Months';
        
        const match = text.match(/(\d+)\s*(day|week|month)/i);
        if (match) return `${match[1]} ${match[2]}s`;
        
        return cleanText(el.textContent);
      }
    }
    return null;
  }

  function extractLocation() {
    const selectors = [
      '.location', '.currentLocation', '[class*="location"]',
      '.city', '.address'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) return cleanText(el.textContent);
    }
    return null;
  }

  function extractPreferredLocations() {
    const selectors = [
      '.preferredLocation', '[class*="preferredLocation"]',
      '[class*="preferred"]'
    ];
    
    const locations = [];
    for (const selector of selectors) {
      const elements = document.querySelectorAll(selector);
      elements.forEach(el => {
        const loc = cleanText(el.textContent);
        if (loc && !locations.includes(loc)) {
          locations.push(loc);
        }
      });
    }
    return locations;
  }

  function extractTotalExperience() {
    const selectors = [
      '.experience', '.totalExperience', '[class*="experience"]',
      '.workExp', '.expYears'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent;
        // Match patterns like "7 years", "7.5 yrs", "7 yrs 6 months"
        const yearsMatch = text.match(/(\d+(?:\.\d+)?)\s*(?:years?|yrs?)/i);
        if (yearsMatch) {
          return Math.round(parseFloat(yearsMatch[1]));
        }
      }
    }
    return 0;
  }

  function extractWorkHistory() {
    const experience = [];
    const expSections = document.querySelectorAll(
      '.experience-section, .workExperience, [class*="experienceList"] > *, ' +
      '.exp-section, [class*="employment"] > *, .job-history > *'
    );
    
    expSections.forEach((section, index) => {
      const exp = {
        company: extractFromSection(section, ['.company', '.orgName', '[class*="company"]']),
        designation: extractFromSection(section, ['.designation', '.title', '[class*="title"]']),
        from_date: extractFromSection(section, ['.fromDate', '.startDate', '[class*="from"]']),
        to_date: extractFromSection(section, ['.toDate', '.endDate', '[class*="to"]']),
        duration: extractFromSection(section, ['.duration', '.tenure', '[class*="duration"]']),
        description: extractFromSection(section, ['.description', '.jobDesc', '[class*="desc"]']),
        location: extractFromSection(section, ['.location', '[class*="location"]'])
      };
      
      if (exp.company || exp.designation) {
        // Check if current job
        if (!exp.to_date || exp.to_date.toLowerCase().includes('present')) {
          exp.to_date = null;
          exp.is_current = true;
        }
        
        // Calculate duration in months if not available
        if (!exp.duration && exp.from_date) {
          exp.duration_months = calculateDurationMonths(exp.from_date, exp.to_date);
        }
        
        experience.push(exp);
      }
    });
    
    return experience;
  }

  function extractEducation() {
    const education = [];
    const eduSections = document.querySelectorAll(
      '.education-section, .educationList > *, [class*="education"] > *, ' +
      '.qualification > *, .academics > *'
    );
    
    eduSections.forEach(section => {
      const edu = {
        degree: extractFromSection(section, ['.degree', '.qualification', '[class*="degree"]']),
        institution: extractFromSection(section, ['.institution', '.college', '.university', '[class*="institute"]']),
        year: extractFromSection(section, ['.year', '.passoutYear', '[class*="year"]']),
        score: extractFromSection(section, ['.score', '.percentage', '.cgpa', '[class*="score"]']),
        specialization: extractFromSection(section, ['.specialization', '.stream', '[class*="special"]'])
      };
      
      if (edu.degree || edu.institution) {
        education.push(edu);
      }
    });
    
    return education;
  }

  function extractKeySkills() {
    const skills = [];
    const skillSelectors = [
      '.keySkills span', '.skills span', '.skill-tag', 
      '[class*="skill"] span', '.chip', '.tag'
    ];
    
    for (const selector of skillSelectors) {
      const elements = document.querySelectorAll(selector);
      elements.forEach(el => {
        const skill = cleanText(el.textContent);
        if (skill && skill.length > 1 && skill.length < 50 && !skills.includes(skill)) {
          skills.push(skill);
        }
      });
    }
    
    return skills;
  }

  function extractDetailedSkills() {
    const skills = [];
    const skillSections = document.querySelectorAll(
      '.itSkills tr, .skillsList > *, [class*="skillDetail"] > *'
    );
    
    skillSections.forEach(section => {
      const skill = {
        skill: extractFromSection(section, ['.skillName', 'td:first-child', '[class*="name"]']),
        version: extractFromSection(section, ['.version', 'td:nth-child(2)']),
        experience_years: extractFromSection(section, ['.exp', '.experience', 'td:nth-child(3)']),
        proficiency: extractFromSection(section, ['.proficiency', '.level', 'td:nth-child(4)'])
      };
      
      if (skill.skill) {
        // Parse experience years
        if (skill.experience_years) {
          const match = skill.experience_years.match(/(\d+)/);
          skill.experience_years = match ? parseInt(match[1]) : null;
        }
        skills.push(skill);
      }
    });
    
    return skills;
  }

  function extractCertifications() {
    const certs = [];
    const certSections = document.querySelectorAll(
      '.certification, .certifications > *, [class*="certificate"] > *'
    );
    
    certSections.forEach(section => {
      const cert = {
        name: extractFromSection(section, ['.certName', '.title', '[class*="name"]']),
        issuer: extractFromSection(section, ['.issuer', '.authority', '[class*="issuer"]']),
        year: extractFromSection(section, ['.year', '.date', '[class*="year"]'])
      };
      
      if (cert.name) certs.push(cert);
    });
    
    return certs;
  }

  function extractProjects() {
    const projects = [];
    const projectSections = document.querySelectorAll(
      '.project, .projects > *, [class*="project"] > *'
    );
    
    projectSections.forEach(section => {
      const project = {
        title: extractFromSection(section, ['.title', '.projectName', '[class*="title"]']),
        description: extractFromSection(section, ['.description', '.details', '[class*="desc"]']),
        role: extractFromSection(section, ['.role', '[class*="role"]']),
        duration: extractFromSection(section, ['.duration', '[class*="duration"]'])
      };
      
      if (project.title) projects.push(project);
    });
    
    return projects;
  }

  function extractLanguages() {
    const languages = [];
    const langSections = document.querySelectorAll(
      '.language, .languages > *, [class*="language"] > *'
    );
    
    langSections.forEach(section => {
      const lang = {
        language: extractFromSection(section, ['.langName', '.name', '[class*="name"]']),
        proficiency: extractFromSection(section, ['.proficiency', '.level', '[class*="level"]'])
      };
      
      if (lang.language) languages.push(lang);
    });
    
    return languages;
  }

  function extractDOB() {
    const selectors = [
      '.dob', '.dateOfBirth', '[class*="birth"]', '[class*="dob"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent;
        const dateMatch = text.match(/(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})/);
        if (dateMatch) return dateMatch[1];
      }
    }
    return null;
  }

  function extractGender() {
    const selectors = [
      '.gender', '[class*="gender"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent.toLowerCase();
        if (text.includes('male') && !text.includes('female')) return 'Male';
        if (text.includes('female')) return 'Female';
        if (text.includes('other')) return 'Other';
      }
    }
    return null;
  }

  function extractMaritalStatus() {
    const selectors = [
      '.maritalStatus', '[class*="marital"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent.toLowerCase();
        if (text.includes('single')) return 'Single';
        if (text.includes('married')) return 'Married';
        return cleanText(el.textContent);
      }
    }
    return null;
  }

  function extractIndustryPreference() {
    const selectors = [
      '.industryPreference', '[class*="industry"]', '.preferredIndustry'
    ];
    
    const industries = [];
    for (const selector of selectors) {
      const elements = document.querySelectorAll(selector);
      elements.forEach(el => {
        const ind = cleanText(el.textContent);
        if (ind && !industries.includes(ind)) industries.push(ind);
      });
    }
    return industries;
  }

  function extractFunctionalArea() {
    const selectors = [
      '.functionalArea', '[class*="functional"]', '.department'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) return cleanText(el.textContent);
    }
    return null;
  }

  function checkResumeAvailable() {
    const downloadBtn = document.querySelector(
      '[class*="download"], [class*="resume"] a, .downloadResume'
    );
    return !!downloadBtn;
  }

  // ============== HELPER FUNCTIONS ==============

  function extractFromSection(section, selectors) {
    for (const selector of selectors) {
      const el = section.querySelector(selector);
      if (el && el.textContent.trim()) {
        return cleanText(el.textContent);
      }
    }
    return null;
  }

  function cleanText(text) {
    if (!text) return null;
    return text
      .replace(/\s+/g, ' ')
      .replace(/[\n\r\t]/g, ' ')
      .trim();
  }

  function calculateDurationMonths(fromDate, toDate) {
    // Simple calculation - can be enhanced
    try {
      const from = new Date(fromDate);
      const to = toDate ? new Date(toDate) : new Date();
      const months = (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth());
      return Math.max(0, months);
    } catch {
      return null;
    }
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // ============== STORAGE FUNCTIONS ==============

  async function getSettings() {
    return new Promise(resolve => {
      chrome.storage.sync.get({
        enabled: true,
        showNotifications: true,
        autoCapture: true
      }, resolve);
    });
  }

  async function getAuthToken() {
    return new Promise(resolve => {
      chrome.storage.sync.get(['vhc_token', 'vhc_api_url'], (result) => {
        if (result.vhc_token && result.vhc_api_url) {
          resolve({
            token: result.vhc_token,
            apiUrl: result.vhc_api_url
          });
        } else {
          resolve(null);
        }
      });
    });
  }

  // ============== UI FUNCTIONS ==============

  function showToast(message, type = 'info') {
    // Remove existing toast
    const existing = document.getElementById('vhc-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'vhc-toast';
    toast.className = `vhc-toast vhc-toast-${type}`;
    toast.innerHTML = `
      <div class="vhc-toast-content">
        <img src="${chrome.runtime.getURL('icons/icon32.png')}" class="vhc-toast-icon" />
        <span>${message}</span>
      </div>
    `;

    document.body.appendChild(toast);

    // Animate in
    setTimeout(() => toast.classList.add('vhc-toast-show'), 10);

    // Remove after duration
    setTimeout(() => {
      toast.classList.remove('vhc-toast-show');
      setTimeout(() => toast.remove(), 300);
    }, CONFIG.TOAST_DURATION);
  }

  // ============== START ==============
  
  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
