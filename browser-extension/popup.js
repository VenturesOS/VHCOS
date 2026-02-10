/**
 * VHC Talent OS - Popup Script
 */

document.addEventListener('DOMContentLoaded', async () => {
  // Elements
  const loginSection = document.getElementById('loginSection');
  const dashboardSection = document.getElementById('dashboardSection');
  const loginBtn = document.getElementById('loginBtn');
  const logoutBtn = document.getElementById('logoutBtn');
  const loginError = document.getElementById('loginError');
  const manualCaptureBtn = document.getElementById('manualCaptureBtn');
  const captureStatus = document.getElementById('captureStatus');
  const statusDot = document.getElementById('statusDot');
  const pageStatusText = document.getElementById('pageStatusText');
  
  // Check auth status
  const authStatus = await chrome.runtime.sendMessage({ action: 'checkAuth' });
  
  if (authStatus.authenticated) {
    showDashboard(authStatus.user);
  } else {
    showLogin();
  }
  
  // Login handler
  loginBtn.addEventListener('click', async () => {
    const apiUrl = document.getElementById('apiUrl').value.trim().replace(/\/$/, '');
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    
    if (!apiUrl || !email || !password) {
      showError('Please fill in all fields');
      return;
    }
    
    loginBtn.disabled = true;
    loginBtn.innerHTML = '<span class="loading"></span> Logging in...';
    
    try {
      const response = await chrome.runtime.sendMessage({
        action: 'login',
        data: { apiUrl, email, password }
      });
      
      if (response.success) {
        showDashboard({ name: response.user?.name || email, role: response.user?.role || 'user' });
      } else {
        showError(response.error || 'Login failed');
      }
    } catch (error) {
      showError('Connection error. Please try again.');
    }
    
    loginBtn.disabled = false;
    loginBtn.textContent = 'Login to VHC';
  });
  
  // Logout handler
  logoutBtn.addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ action: 'logout' });
    showLogin();
  });
  
  // Manual capture handler
  manualCaptureBtn.addEventListener('click', async () => {
    manualCaptureBtn.disabled = true;
    manualCaptureBtn.innerHTML = '<span class="loading"></span> Capturing...';
    showCaptureStatus('info', 'AI capture started on page. This takes 10-20 seconds...');
    
    try {
      // Get the active tab
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      
      if (!tab) {
        showCaptureStatus('error', 'No active tab found');
        manualCaptureBtn.disabled = false;
        manualCaptureBtn.textContent = 'Capture This Profile';
        return;
      }
      
      // Check if it's a Naukri page
      if (!tab.url.includes('naukri.com')) {
        showCaptureStatus('error', 'Not a Naukri page. Please open a Naukri profile.');
        manualCaptureBtn.disabled = false;
        manualCaptureBtn.textContent = 'Capture This Profile';
        return;
      }
      
      // Fire the capture command — content.js will show a toast on the page
      // We use a short timeout wrapper because the capture takes 10-30s and the
      // message channel may close if the popup loses focus.
      const responsePromise = chrome.tabs.sendMessage(tab.id, { action: 'manualCapture' });
      
      // Race between response and a 30-second timeout
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), 30000)
      );
      
      try {
        const response = await Promise.race([responsePromise, timeoutPromise]);
        
        if (response && response.success) {
          if (response.action === 'created') {
            showCaptureStatus('success', `${response.name || 'Profile'} added to VHC!`);
          } else if (response.action === 'updated') {
            showCaptureStatus('success', `${response.name || 'Profile'} updated in VHC!`);
          } else if (response.action === 'exists') {
            showCaptureStatus('info', `${response.name || 'Profile'} already up-to-date`);
          } else if (response.action === 'queued') {
            showCaptureStatus('info', `${response.name || 'Profile'} queued for sync`);
          }
          loadStats();
        } else if (response) {
          showCaptureStatus('error', response.error || 'Capture failed.');
        }
      } catch (raceError) {
        if (raceError.message === 'timeout') {
          // The capture is likely still running on the page — don't show error
          showCaptureStatus('info', 'Capture is running on the page. Check the page for results.');
        } else {
          throw raceError; // Re-throw non-timeout errors
        }
      }
      
    } catch (error) {
      console.error('Manual capture error:', error);
      if (error.message && error.message.includes('Receiving end does not exist')) {
        showCaptureStatus('error', 'Extension not active on this page. Please refresh the Naukri page.');
      } else if (error.message && error.message.includes('Could not establish connection')) {
        showCaptureStatus('error', 'Content script not loaded. Please refresh the Naukri page.');
      } else {
        showCaptureStatus('info', 'Capture triggered. Check the page for toast notification with results.');
      }
    } finally {
      manualCaptureBtn.disabled = false;
      manualCaptureBtn.textContent = 'Capture This Profile';
    }
  });
  
  // Settings handlers
  document.getElementById('settingEnabled').addEventListener('change', (e) => {
    chrome.storage.sync.set({ enabled: e.target.checked });
  });
  
  document.getElementById('settingNotifications').addEventListener('change', (e) => {
    chrome.storage.sync.set({ showNotifications: e.target.checked });
  });
  
  // Functions
  function showLogin() {
    loginSection.style.display = 'flex';
    dashboardSection.style.display = 'none';
    
    // Load saved URL if any
    chrome.storage.sync.get(['vhc_api_url'], (result) => {
      if (result.vhc_api_url) {
        document.getElementById('apiUrl').value = result.vhc_api_url;
      }
    });
  }
  
  async function showDashboard(user) {
    loginSection.style.display = 'none';
    dashboardSection.style.display = 'block';
    
    // Show user info
    document.getElementById('userName').textContent = user.name || 'User';
    document.getElementById('userRole').textContent = user.role || 'Member';
    
    // Show API URL
    chrome.storage.sync.get(['vhc_api_url'], (result) => {
      document.getElementById('apiUrlDisplay').textContent = result.vhc_api_url || '-';
    });
    
    // Load settings
    chrome.storage.sync.get(['enabled', 'showNotifications'], (result) => {
      document.getElementById('settingEnabled').checked = result.enabled !== false;
      document.getElementById('settingNotifications').checked = result.showNotifications !== false;
    });
    
    // Load stats
    loadStats();
    
    // Check queue
    chrome.storage.local.get(['offlineQueue'], (result) => {
      const queue = result.offlineQueue || [];
      const queueStatus = document.getElementById('queueStatus');
      
      if (queue.length > 0) {
        queueStatus.classList.add('visible');
        document.getElementById('queueCount').textContent = queue.length;
      } else {
        queueStatus.classList.remove('visible');
      }
    });
    
    // Check current page status
    checkPageStatus();
  }
  
  async function checkPageStatus() {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      
      if (!tab || !tab.url) {
        setPageStatus('gray', 'Unknown page');
        return;
      }
      
      if (tab.url.includes('naukri.com')) {
        if (tab.url.includes('/profile') || tab.url.includes('viewResume') || 
            tab.url.includes('view-resume') || tab.url.includes('cvPreview') ||
            tab.url.includes('preview') || tab.url.includes('resdex')) {
          setPageStatus('green', '✓ Naukri profile page detected');
          manualCaptureBtn.disabled = false;
        } else {
          setPageStatus('yellow', 'Naukri page (not a profile)');
          manualCaptureBtn.disabled = true;
        }
      } else {
        setPageStatus('gray', 'Not a Naukri page');
        manualCaptureBtn.disabled = true;
      }
    } catch (error) {
      setPageStatus('red', 'Error checking page');
    }
  }
  
  function setPageStatus(color, text) {
    statusDot.className = `status-dot ${color}`;
    pageStatusText.textContent = text;
  }
  
  async function loadStats() {
    const stats = await chrome.runtime.sendMessage({ action: 'getStats' });
    
    document.getElementById('statToday').textContent = stats.captured_today || 0;
    document.getElementById('statWeek').textContent = stats.captured_week || 0;
    document.getElementById('statTotal').textContent = stats.captured_total || 0;
    document.getElementById('statUpdated').textContent = stats.updated_total || 0;
  }
  
  function showError(message) {
    loginError.textContent = message;
    loginError.style.display = 'block';
    setTimeout(() => {
      loginError.style.display = 'none';
    }, 5000);
  }
  
  function showCaptureStatus(type, message) {
    captureStatus.textContent = message;
    captureStatus.className = `capture-status visible ${type}`;
    
    // Auto-hide after 10 seconds for success/info
    if (type !== 'error') {
      setTimeout(() => {
        captureStatus.classList.remove('visible');
      }, 10000);
    }
  }
});
