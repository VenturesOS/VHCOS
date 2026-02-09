/**
 * VHC Talent OS - Naukri Profile Scraper
 * Content script that runs on Naukri profile pages
 * 
 * IMPORTANT: This script specifically targets the MAIN profile area
 * and excludes sidebar elements like "AI matched similar profiles"
 */

(function() {
  'use strict';

  // Prevent multiple injections
  if (window.vhcExtensionLoaded) return;
  window.vhcExtensionLoaded = true;

  // Configuration
  const CONFIG = {
    CAPTURE_DELAY: 3000,
    SCROLL_DELAY: 500,
    TOAST_DURATION: 4000,
    RETRY_ATTEMPTS: 3
  };

  // State
  let isCapturing = false;
  let lastCapturedUrl = null;

  console.log('[VHC Extension] Content script loaded on:', window.location.href);

  /**
   * Get the MAIN profile container - exclude sidebars
   */
  function getMainProfileContainer() {
    // Naukri Resdex specific - main profile is usually in these containers
    const mainSelectors = [
      '.mainContent',
      '.profileContent', 
      '.leftSection',
      '.profile-left',
      '[class*="leftSec"]',
      '[class*="mainProfile"]',
      '[class*="profileDetail"]',
      '.candidate-profile-main',
      // Generic but more specific
      'main',
      'article'
    ];
    
    for (const selector of mainSelectors) {
      const el = document.querySelector(selector);
      if (el) {
        console.log('[VHC Extension] Using main container:', selector);
        return el;
      }
    }
    
    // Fallback: Try to find the container that has the main profile info
    // but EXCLUDE the sidebar
    const body = document.body;
    
    // Exclude sidebar elements
    const sidebars = document.querySelectorAll(
      '[class*="rightSec"], [class*="sidebar"], [class*="similar"], ' +
      '[class*="Sidebar"], [class*="matched"], [class*="recommendation"], ' +
      '.aiMatched, .recruitersViewed, [class*="RightSection"]'
    );
    
    return body;
  }

  /**
   * Check if element is inside a sidebar or excluded area
   */
  function isInSidebar(element) {
    if (!element) return false;
    
    const sidebarPatterns = [
      'sidebar', 'rightSec', 'similar', 'matched', 'recommendation',
      'aiMatched', 'recruitersViewed', 'RightSection', 'rightSection',
      'Comment', 'comment', 'relatedProfile', 'otherCandidate'
    ];
    
    let parent = element;
    while (parent && parent !== document.body) {
      const className = parent.className || '';
      const id = parent.id || '';
      
      for (const pattern of sidebarPatterns) {
        if (className.toLowerCase().includes(pattern.toLowerCase()) ||
            id.toLowerCase().includes(pattern.toLowerCase())) {
          return true;
        }
      }
      parent = parent.parentElement;
    }
    return false;
  }

  /**
   * Check if this looks like a user's own contact (logged-in user)
   */
  function isUserOwnContact(email, phone) {
    // Get text from header/nav area which usually shows logged-in user info
    const headerArea = document.querySelector('header, nav, .header, .navbar, [class*="Header"]');
    if (headerArea) {
      const headerText = headerArea.innerText.toLowerCase();
      if (email && headerText.includes(email.toLowerCase())) {
        return true;
      }
    }
    
    // Check if email domain is vhc.in (internal user)
    if (email && email.includes('@vhc.in')) {
      return true;
    }
    
    return false;
  }

  /**
   * Listen for messages from popup
   */
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    console.log('[VHC Extension] Received message:', request.action);
    
    if (request.action === 'manualCapture') {
      manualCapture().then(sendResponse);
      return true;
    }
    
    if (request.action === 'getPageInfo') {
      sendResponse({
        url: window.location.href,
        isProfilePage: isProfilePage()
      });
      return true;
    }
  });

  /**
   * Manual capture triggered from popup
   */
  async function manualCapture() {
    console.log('[VHC Extension] Manual capture triggered');
    
    if (isCapturing) {
      return { success: false, error: 'Capture already in progress' };
    }
    
    isCapturing = true;
    
    try {
      const auth = await getAuthToken();
      if (!auth) {
        return { success: false, error: 'Not logged in to VHC. Please login via extension popup.' };
      }
      
      showToast('🔄 Capturing profile...', 'info');
      
      // Scroll to load all content first
      await scrollToLoadContent();
      await sleep(1000);
      
      // Scrape the profile
      const profileData = await scrapeProfileData();
      
      if (!profileData || !profileData.name) {
        return { success: false, error: 'Could not extract profile data. Make sure you are on a profile page.' };
      }
      
      // Validate we're not capturing sidebar profile
      if (profileData._warning) {
        console.warn('[VHC Extension] Warning:', profileData._warning);
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
          showToast(`✅ ${profileData.name} added to VHC!`, 'success');
        } else if (response.action === 'updated') {
          showToast(`🔄 ${profileData.name} profile updated!`, 'info');
        } else if (response.action === 'exists') {
          showToast(`ℹ️ ${profileData.name} already up-to-date`, 'info');
        } else if (response.action === 'queued') {
          showToast(`📥 ${profileData.name} queued for sync`, 'info');
        }
        
        return { success: true, action: response.action, name: profileData.name };
      } else {
        showToast(`❌ ${response.error}`, 'error');
        return { success: false, error: response.error };
      }
      
    } catch (error) {
      console.error('[VHC Extension] Manual capture error:', error);
      showToast(`❌ Error: ${error.message}`, 'error');
      return { success: false, error: error.message };
    } finally {
      isCapturing = false;
    }
  }

  /**
   * Check if current page is a profile page
   */
  function isProfilePage() {
    const url = window.location.href;
    return url.includes('resdex') || 
           url.includes('profile') || 
           url.includes('viewResume') || 
           url.includes('view-resume') || 
           url.includes('cvPreview') ||
           url.includes('preview');
  }

  /**
   * Initialize the extension
   */
  async function init() {
    console.log('[VHC Extension] Initializing...');
    
    addFloatingButton();
    
    const settings = await getSettings();
    if (!settings.enabled) {
      console.log('[VHC Extension] Auto-capture disabled');
      return;
    }

    const auth = await getAuthToken();
    if (!auth) {
      console.log('[VHC Extension] User not logged in to VHC');
      return;
    }

    if (!isProfilePage()) {
      console.log('[VHC Extension] Not a profile page, skipping auto-capture');
      return;
    }

    await waitForPageLoad();
    await scrollToLoadContent();
    
    setTimeout(() => captureProfile(), CONFIG.CAPTURE_DELAY);
  }

  /**
   * Add floating capture button
   */
  function addFloatingButton() {
    const existing = document.getElementById('vhc-floating-btn');
    if (existing) existing.remove();
    
    const btn = document.createElement('button');
    btn.id = 'vhc-floating-btn';
    btn.className = 'vhc-capture-btn';
    btn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
    `;
    btn.title = 'Capture to VHC Talent OS';
    
    btn.addEventListener('click', async () => {
      btn.classList.add('capturing');
      await manualCapture();
      btn.classList.remove('capturing');
    });
    
    document.body.appendChild(btn);
    console.log('[VHC Extension] Floating button added');
  }

  function waitForPageLoad() {
    return new Promise((resolve) => {
      if (document.readyState === 'complete') {
        resolve();
      } else {
        window.addEventListener('load', resolve);
      }
    });
  }

  async function scrollToLoadContent() {
    console.log('[VHC Extension] Scrolling to load content...');
    const scrollHeight = document.documentElement.scrollHeight;
    const viewportHeight = window.innerHeight;
    let currentPosition = 0;

    while (currentPosition < scrollHeight) {
      currentPosition += viewportHeight * 0.8;
      window.scrollTo(0, currentPosition);
      await sleep(CONFIG.SCROLL_DELAY);
    }

    window.scrollTo(0, 0);
    await sleep(500);
    console.log('[VHC Extension] Scroll complete');
  }

  async function captureProfile() {
    if (isCapturing) return;
    if (lastCapturedUrl === window.location.href) {
      console.log('[VHC Extension] Already captured this URL');
      return;
    }

    isCapturing = true;
    console.log('[VHC Extension] Starting auto-capture...');

    try {
      const profileData = await scrapeProfileData();
      
      if (!profileData || !profileData.name) {
        console.log('[VHC Extension] Could not extract profile data');
        return;
      }

      console.log('[VHC Extension] Scraped profile:', profileData.name);
      
      const response = await chrome.runtime.sendMessage({
        action: 'captureProfile',
        data: profileData
      });

      if (response.success) {
        lastCapturedUrl = window.location.href;
        
        const settings = await getSettings();
        if (settings.showNotifications) {
          if (response.action === 'created') {
            showToast(`✅ ${profileData.name} added to VHC`, 'success');
          } else if (response.action === 'updated') {
            showToast(`🔄 ${profileData.name} profile updated`, 'info');
          }
        }
      }

    } catch (error) {
      console.error('[VHC Extension] Capture error:', error);
    } finally {
      isCapturing = false;
    }
  }

  /**
   * MAIN SCRAPING FUNCTION - Targets main profile area only
   */
  async function scrapeProfileData() {
    console.log('[VHC Extension] Scraping profile data from MAIN profile area...');
    
    const data = {
      naukri_profile_id: extractNaukriProfileId(),
      naukri_profile_url: window.location.href,
      naukri_last_updated: extractProfileLastUpdated(),
      scraped_at: new Date().toISOString(),

      name: extractMainProfileName(),
      email: extractMainProfileEmail(),
      phone: extractMainProfilePhone(),
      photo_url: extractPhotoUrl(),
      
      headline: extractHeadline(),
      summary: extractSummary(),
      current_company: extractCurrentCompany(),
      current_designation: extractCurrentDesignation(),
      
      current_salary: extractCurrentSalary(),
      expected_salary: extractExpectedSalary(),
      notice_period: extractNoticePeriod(),
      
      location: extractLocation(),
      preferred_locations: extractPreferredLocations(),
      
      experience_years: extractTotalExperience(),
      experience: extractWorkHistory(),
      
      education: extractEducation(),
      
      skills: extractKeySkills(),
      skills_detailed: extractDetailedSkills(),
      
      certifications: extractCertifications(),
      projects: extractProjects(),
      languages: extractLanguages(),
      
      date_of_birth: extractDOB(),
      gender: extractGender(),
      marital_status: extractMaritalStatus(),
      
      industry_preference: extractIndustryPreference(),
      functional_area: extractFunctionalArea(),
      
      resume_available: checkResumeAvailable()
    };

    console.log('[VHC Extension] Extracted data summary:', {
      name: data.name,
      email: data.email,
      phone: data.phone,
      company: data.current_company,
      skills: data.skills?.length || 0
    });

    return data;
  }

  // ============== MAIN PROFILE EXTRACTION (Avoiding Sidebar) ==============

  function extractMainProfileName() {
    // NAUKRI RESDEX SPECIFIC - The main profile name is usually in:
    // 1. The breadcrumb area (Similar profiles > NAME)
    // 2. The main left section header
    
    // Try breadcrumb first - most reliable for Resdex
    const breadcrumb = document.querySelector('.breadcrumb, [class*="breadcrumb"], [class*="Breadcrumb"]');
    if (breadcrumb) {
      // Get the last item in breadcrumb which is the profile name
      const items = breadcrumb.querySelectorAll('span, a, li');
      if (items.length > 0) {
        const lastName = items[items.length - 1];
        const name = cleanText(lastName.textContent);
        if (name && name.length > 2 && name.length < 60 && !name.includes('Similar') && !name.includes('profile')) {
          console.log('[VHC Extension] Found name from breadcrumb:', name);
          return name;
        }
      }
    }
    
    // Try the page title/header - look for profile header specifically
    const pageTitle = document.querySelector('h1, [class*="profileTitle"], [class*="candidateName"]');
    if (pageTitle && !isInSidebar(pageTitle)) {
      const name = cleanText(pageTitle.textContent);
      if (name && name.length > 2 && name.length < 60) {
        console.log('[VHC Extension] Found name from page title:', name);
        return name;
      }
    }
    
    // Naukri Resdex specific selectors - MAIN PROFILE AREA
    const mainProfileSelectors = [
      // These are typically in the MAIN profile area, not sidebar
      '.profileCard .name',
      '.leftSection .name',
      '.mainContent .name',
      '.profile-details .name',
      '.candidate-info .name',
      '[class*="leftSec"] .name',
      '[class*="profileCard"] .name'
    ];
    
    for (const selector of mainProfileSelectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el)) {
        const name = cleanText(el.textContent);
        if (name && name.length > 2 && name.length < 60) {
          console.log('[VHC Extension] Found name from main selector:', name, selector);
          return name;
        }
      }
    }
    
    // Try generic .name but ONLY in main area (not sidebar)
    const allNames = document.querySelectorAll('.name, [class*="Name"]');
    for (const el of allNames) {
      if (!isInSidebar(el)) {
        const name = cleanText(el.textContent);
        // Make sure it's not a label like "Full Name:" 
        if (name && name.length > 2 && name.length < 60 && 
            !name.toLowerCase().includes('name:') &&
            !name.toLowerCase().includes('full name')) {
          console.log('[VHC Extension] Found name from generic selector:', name);
          return name;
        }
      }
    }
    
    console.log('[VHC Extension] Could not find main profile name');
    return null;
  }

  function extractMainProfileEmail() {
    // First, find email elements that are NOT in sidebar
    const emailSelectors = [
      '.email', '[class*="email"]', '[class*="Email"]',
      'a[href^="mailto:"]'
    ];
    
    for (const selector of emailSelectors) {
      const elements = document.querySelectorAll(selector);
      for (const el of elements) {
        // Skip if in sidebar
        if (isInSidebar(el)) {
          console.log('[VHC Extension] Skipping sidebar email element');
          continue;
        }
        
        const text = el.href?.replace('mailto:', '') || el.textContent;
        const emailMatch = text.match(/[\w.-]+@[\w.-]+\.\w+/);
        if (emailMatch) {
          const email = emailMatch[0].toLowerCase();
          
          // Check if this is user's own email
          if (isUserOwnContact(email, null)) {
            console.log('[VHC Extension] Skipping own contact email:', email);
            continue;
          }
          
          console.log('[VHC Extension] Found email:', email);
          return email;
        }
      }
    }
    
    // Search in main content area only - more carefully
    const mainContent = document.querySelector('.leftSection, .mainContent, .profileContent, main');
    if (mainContent) {
      const text = mainContent.innerText;
      // Look for email pattern but exclude common user email domains
      const emailMatches = text.match(/[\w.-]+@[\w.-]+\.(com|in|org|net|co\.in|io)/gi);
      if (emailMatches) {
        for (const email of emailMatches) {
          const lowerEmail = email.toLowerCase();
          // Skip if it's user's own email or internal domain
          if (!isUserOwnContact(lowerEmail, null)) {
            console.log('[VHC Extension] Found email from main content:', lowerEmail);
            return lowerEmail;
          }
        }
      }
    }
    
    console.log('[VHC Extension] Could not find email (may need to click "View" button)');
    return null;
  }

  function extractMainProfilePhone() {
    // Naukri often hides phone behind "View phone number" button
    // First try visible phone numbers in main area
    
    const phoneSelectors = [
      '.phone', '.mobile', '[class*="phone"]', '[class*="mobile"]',
      '[class*="Phone"]', '[class*="Mobile"]', 'a[href^="tel:"]'
    ];
    
    for (const selector of phoneSelectors) {
      const elements = document.querySelectorAll(selector);
      for (const el of elements) {
        // Skip if in sidebar
        if (isInSidebar(el)) {
          console.log('[VHC Extension] Skipping sidebar phone element');
          continue;
        }
        
        const text = el.href?.replace('tel:', '') || el.textContent;
        const phoneMatch = text.match(/(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}/);
        if (phoneMatch) {
          const phone = phoneMatch[0].replace(/[\s-]/g, '');
          
          // Check if this is user's own phone
          if (isUserOwnContact(null, phone)) {
            console.log('[VHC Extension] Skipping own phone:', phone);
            continue;
          }
          
          console.log('[VHC Extension] Found phone:', phone);
          return phone;
        }
      }
    }
    
    // Search in main content area only
    const mainContent = document.querySelector('.leftSection, .mainContent, .profileContent, main');
    if (mainContent) {
      const text = mainContent.innerText;
      const phoneMatch = text.match(/(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}/);
      if (phoneMatch) {
        const phone = phoneMatch[0].replace(/[\s-]/g, '');
        if (!isUserOwnContact(null, phone)) {
          console.log('[VHC Extension] Found phone from main content:', phone);
          return phone;
        }
      }
    }
    
    console.log('[VHC Extension] Could not find phone (may need to click "View phone number")');
    return null;
  }

  function extractNaukriProfileId() {
    const url = window.location.href;
    
    // Try to extract from URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const sid = urlParams.get('sid');
    if (sid) {
      return `naukri_${sid}`;
    }
    
    // Try URL pattern
    const urlMatch = url.match(/\/(\d+)\/?(\?|$|&)/);
    if (urlMatch) return `naukri_${urlMatch[1]}`;
    
    // Try data attributes in main area
    const mainArea = document.querySelector('.leftSection, .mainContent, .profileContent');
    if (mainArea) {
      const profileIdEl = mainArea.querySelector('[data-profile-id], [id*="profileId"]');
      if (profileIdEl) {
        const id = profileIdEl.getAttribute('data-profile-id') || profileIdEl.id;
        if (id) return `naukri_${id}`;
      }
    }
    
    // Generate from URL hash
    const urlHash = btoa(url).replace(/[^a-zA-Z0-9]/g, '').substring(0, 20);
    return `naukri_${urlHash}`;
  }

  function extractProfileLastUpdated() {
    const selectors = [
      '.lastUpdatedOn', '.profileLastUpdated', '.updateDate',
      '[class*="lastUpdate"]', '[class*="Modified"]', '[class*="Active"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el)) {
        const text = el.textContent.trim();
        const dateMatch = text.match(/(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})/);
        if (dateMatch) return dateMatch[1];
        
        // Try relative dates
        if (text.toLowerCase().includes('today') || text.toLowerCase().includes('active today')) {
          return new Date().toISOString().split('T')[0];
        }
      }
    }
    return null;
  }

  function extractPhotoUrl() {
    const selectors = [
      '.profile-photo img', '.profilePic img', '.user-image img',
      '[class*="profilePhoto"] img', '.candidate-photo img', '.photo img',
      '[class*="avatar"] img'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el) && el.src && 
          !el.src.includes('default') && 
          !el.src.includes('placeholder')) {
        return el.src;
      }
    }
    return null;
  }

  function extractHeadline() {
    const selectors = [
      '.headline', '.resumeHeadline', '.profile-headline',
      '[class*="headline"]', '.tagline'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el) && el.textContent.trim().length > 10) {
        return cleanText(el.textContent);
      }
    }
    return null;
  }

  function extractSummary() {
    const selectors = [
      '.summary', '.profileSummary', '.about-me', '.profile-summary',
      '[class*="summary"]', '.synopsis'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el) && el.textContent.trim().length > 50) {
        return cleanText(el.textContent);
      }
    }
    return null;
  }

  function extractCurrentCompany() {
    // Look for company in main profile area - Resdex shows as "Current" line
    const currentLine = Array.from(document.querySelectorAll('*')).find(el => {
      const text = el.textContent;
      return text.includes('Current') && text.includes('at') && !isInSidebar(el);
    });
    
    if (currentLine) {
      // Parse "Manager - Talent Acquisition at Philips since Feb '22"
      const text = currentLine.textContent;
      const atMatch = text.match(/at\s+([^since]+)/i);
      if (atMatch) {
        const company = cleanText(atMatch[1]);
        console.log('[VHC Extension] Found company from "Current" line:', company);
        return company;
      }
    }
    
    const selectors = [
      '.currentCompany', '.company', '[class*="currentEmployer"]',
      '.orgName', '.employer', '[class*="companyName"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el)) {
        const text = cleanText(el.textContent);
        if (text && text.length > 2) {
          console.log('[VHC Extension] Found company:', text);
          return text;
        }
      }
    }
    
    return null;
  }

  function extractCurrentDesignation() {
    // Look for designation in main profile - usually before "at Company"
    const currentLine = Array.from(document.querySelectorAll('*')).find(el => {
      const text = el.textContent;
      return text.includes('Current') && text.includes('at') && !isInSidebar(el);
    });
    
    if (currentLine) {
      // Parse "Manager - Talent Acquisition at Philips"
      const text = currentLine.textContent;
      const parts = text.split('at');
      if (parts.length > 1) {
        let designation = parts[0].replace('Current', '').replace(/^\s*[-:]\s*/, '').trim();
        if (designation) {
          console.log('[VHC Extension] Found designation from "Current" line:', designation);
          return designation;
        }
      }
    }
    
    const selectors = [
      '.designation', '.currentDesignation', '[class*="designation"]',
      '.jobTitle', '.title', '[class*="jobTitle"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el)) {
        const text = cleanText(el.textContent);
        if (text && text.length > 2 && text.length < 100) {
          return text;
        }
      }
    }
    return null;
  }

  function extractCurrentSalary() {
    // Naukri shows salary like "₹ 24 Lacs (expects: ₹ 32 Lacs)"
    const pageText = document.body.innerText;
    
    // Look for current salary pattern
    const salaryMatch = pageText.match(/₹\s*(\d+(?:\.\d+)?)\s*(?:Lacs?|lakh|lpa)/i);
    if (salaryMatch) {
      const salary = Math.round(parseFloat(salaryMatch[1]) * 100000);
      console.log('[VHC Extension] Found current salary:', salary);
      return salary;
    }
    
    const selectors = [
      '.currentSalary', '.salary', '[class*="salary"]',
      '[class*="ctc"]', '.annualSalary'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el)) {
        const text = el.textContent;
        const match = text.match(/(\d+(?:\.\d+)?)\s*(lakh|lac|lpa|l)/i);
        if (match) {
          return Math.round(parseFloat(match[1]) * 100000);
        }
      }
    }
    return null;
  }

  function extractExpectedSalary() {
    // Look for "expects: ₹ X Lacs" pattern
    const pageText = document.body.innerText;
    const expectMatch = pageText.match(/expects?:?\s*₹?\s*(\d+(?:\.\d+)?)\s*(?:Lacs?|lakh|lpa)/i);
    if (expectMatch) {
      const salary = Math.round(parseFloat(expectMatch[1]) * 100000);
      console.log('[VHC Extension] Found expected salary:', salary);
      return salary;
    }
    
    const selectors = ['.expectedSalary', '[class*="expected"]'];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el)) {
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
    // Naukri shows notice period like "◷ 2 Months"
    const pageText = document.body.innerText;
    
    // Common patterns
    const patterns = [
      /notice[:\s]*(\d+\s*(?:month|day|week)s?|immediate)/i,
      /(\d+)\s*(?:Month|Months)/i,
      /(Immediate(?:ly)?)/i,
      /serving\s+(\d+\s*(?:month|day)s?)/i
    ];
    
    for (const pattern of patterns) {
      const match = pageText.match(pattern);
      if (match) {
        let notice = match[1].trim();
        // Normalize
        if (notice.toLowerCase().includes('immediate')) return 'Immediate';
        if (notice.includes('1') && notice.toLowerCase().includes('month')) return '1 Month';
        if (notice.includes('2') && notice.toLowerCase().includes('month')) return '2 Months';
        if (notice.includes('3') && notice.toLowerCase().includes('month')) return '3 Months';
        
        console.log('[VHC Extension] Found notice period:', notice);
        return notice;
      }
    }
    
    return null;
  }

  function extractLocation() {
    // Naukri shows location like "📍 New Delhi"
    const pageText = document.body.innerText;
    
    // Look for location indicator
    const locationMatch = pageText.match(/📍\s*([A-Za-z\s,]+?)(?:\s*\||$|\n)/);
    if (locationMatch) {
      const location = cleanText(locationMatch[1]);
      console.log('[VHC Extension] Found location:', location);
      return location;
    }
    
    const selectors = [
      '.location', '.currentLocation', '[class*="location"]',
      '.city', '[class*="Location"]'
    ];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el)) {
        const text = cleanText(el.textContent);
        if (text && text.length > 2 && text.length < 100) {
          return text;
        }
      }
    }
    return null;
  }

  function extractPreferredLocations() {
    const locations = [];
    
    // Look for "Pref. locations" section
    const prefSection = Array.from(document.querySelectorAll('*')).find(el => 
      el.textContent.includes('Pref. locations') && !isInSidebar(el)
    );
    
    if (prefSection) {
      const text = prefSection.textContent;
      // Extract locations after "Pref. locations"
      const locsMatch = text.match(/Pref\.\s*locations[:\s]*([^]+?)(?:\+\d+|$)/i);
      if (locsMatch) {
        const locs = locsMatch[1].split(/[,\/]/).map(l => cleanText(l)).filter(l => l && l.length > 2);
        return locs;
      }
    }
    
    return locations;
  }

  function extractTotalExperience() {
    // Naukri shows experience like "💼 15y"
    const pageText = document.body.innerText;
    
    // Pattern for "15y" or "15 years" etc
    const expMatch = pageText.match(/(\d+(?:\.\d+)?)\s*(?:y(?:ears?|rs?)?|yoe)/i);
    if (expMatch) {
      const years = Math.round(parseFloat(expMatch[1]));
      console.log('[VHC Extension] Found experience years:', years);
      return years;
    }
    
    const selectors = ['.experience', '.totalExperience', '[class*="experience"]'];
    
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !isInSidebar(el)) {
        const text = el.textContent;
        const yearsMatch = text.match(/(\d+(?:\.\d+)?)\s*(?:years?|yrs?)/i);
        if (yearsMatch) {
          return Math.round(parseFloat(yearsMatch[1]));
        }
      }
    }
    return 0;
  }

  function extractWorkHistory() {
    // This needs more complex parsing - for now return empty
    return [];
  }

  function extractEducation() {
    // Look for "Highest degree" in main profile
    const eduText = document.body.innerText;
    const degreeMatch = eduText.match(/Highest\s*degree[:\s]*([^\n]+)/i);
    
    if (degreeMatch) {
      return [{
        degree: cleanText(degreeMatch[1]),
        institution: null,
        year: null
      }];
    }
    
    return [];
  }

  function extractKeySkills() {
    const skills = [];
    
    // Find skills section in main area
    const skillsSection = document.querySelector('.keySkills, .skills, [class*="skill"]');
    if (skillsSection && !isInSidebar(skillsSection)) {
      const skillElements = skillsSection.querySelectorAll('span, .chip, .tag, [class*="skill"]');
      skillElements.forEach(el => {
        const skill = cleanText(el.textContent);
        if (skill && skill.length > 1 && skill.length < 50 && !skills.includes(skill)) {
          skills.push(skill);
        }
      });
    }
    
    // Also check Profile detail section
    const profileDetail = document.querySelector('.profileDetail, [class*="Profile detail"]');
    if (profileDetail) {
      const skillElements = profileDetail.querySelectorAll('span, .chip, .tag');
      skillElements.forEach(el => {
        const skill = cleanText(el.textContent);
        if (skill && skill.length > 1 && skill.length < 50 && !skills.includes(skill)) {
          skills.push(skill);
        }
      });
    }
    
    console.log('[VHC Extension] Found skills:', skills.length);
    return skills;
  }

  function extractDetailedSkills() {
    return [];
  }

  function extractCertifications() {
    return [];
  }

  function extractProjects() {
    return [];
  }

  function extractLanguages() {
    return [];
  }

  function extractDOB() {
    return null;
  }

  function extractGender() {
    return null;
  }

  function extractMaritalStatus() {
    return null;
  }

  function extractIndustryPreference() {
    return [];
  }

  function extractFunctionalArea() {
    return null;
  }

  function checkResumeAvailable() {
    const downloadBtn = document.querySelector('[class*="download"], .downloadResume, [class*="attachedCV"]');
    return !!downloadBtn;
  }

  // ============== HELPER FUNCTIONS ==============

  function cleanText(text) {
    if (!text) return null;
    return text
      .replace(/\s+/g, ' ')
      .replace(/[\n\r\t]/g, ' ')
      .trim();
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

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

  // ============== START ==============
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
