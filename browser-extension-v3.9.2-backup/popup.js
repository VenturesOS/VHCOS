/**
 * VHC Talent OS - Popup Script v3.8.0
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
  
  // Progress bar elements
  const taskProgress = document.getElementById('taskProgress');
  const progressFill = document.getElementById('progressFill');
  const progressStepText = document.getElementById('progressStepText');
  const progressPercent = document.getElementById('progressPercent');
  const progressTick = document.getElementById('progressTick');
  
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
  
  // Progress bar helpers
  function setProgress(percent, stepText) {
    taskProgress.classList.add('visible');
    progressFill.style.width = percent + '%';
    progressStepText.textContent = stepText;
    progressPercent.textContent = percent + '%';
    
    if (percent >= 100) {
      progressTick.classList.add('show');
    } else {
      progressTick.classList.remove('show');
    }
  }
  
  function resetProgress() {
    taskProgress.classList.remove('visible');
    progressFill.style.width = '0%';
    progressStepText.textContent = '';
    progressPercent.textContent = '0%';
    progressTick.classList.remove('show');
  }
  
  // Manual capture handler
  manualCaptureBtn.addEventListener('click', async () => {
    manualCaptureBtn.disabled = true;
    manualCaptureBtn.innerHTML = '<span class="loading"></span> Capturing...';
    hideCaptureStatus();
    
    // Start progress animation
    setProgress(10, 'Scrolling page...');
    
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      
      if (!tab) {
        showCaptureStatus('error', 'No active tab found');
        resetProgress();
        manualCaptureBtn.disabled = false;
        manualCaptureBtn.textContent = 'Capture This Profile';
        return;
      }
      
      if (!tab.url.includes('naukri.com')) {
        showCaptureStatus('error', 'Not a Naukri page. Open a Naukri profile first.');
        resetProgress();
        manualCaptureBtn.disabled = false;
        manualCaptureBtn.textContent = 'Capture This Profile';
        return;
      }
      
      // Simulate progress steps while capture runs
      setProgress(20, 'Loading page content...');
      
      const progressTimer1 = setTimeout(() => setProgress(40, 'Extracting contacts...'), 3000);
      const progressTimer2 = setTimeout(() => setProgress(60, 'AI analyzing profile...'), 7000);
      const progressTimer3 = setTimeout(() => setProgress(80, 'Saving to VHC...'), 15000);
      
      const responsePromise = chrome.tabs.sendMessage(tab.id, { action: 'manualCapture' });
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), 30000)
      );
      
      try {
        const response = await Promise.race([responsePromise, timeoutPromise]);
        
        // Clear pending timers
        clearTimeout(progressTimer1);
        clearTimeout(progressTimer2);
        clearTimeout(progressTimer3);
        
        if (response && response.success) {
          setProgress(100, 'Complete');
          
          if (response.action === 'created') {
            showCaptureStatus('success', `${response.name || 'Profile'} added to VHC!`);
          } else if (response.action === 'updated') {
            showCaptureStatus('success', `${response.name || 'Profile'} updated in VHC!`);
          } else if (response.action === 'exists') {
            showCaptureStatus('info', `${response.name || 'Profile'} already up-to-date`);
            setProgress(100, 'Already captured');
          } else if (response.action === 'queued') {
            showCaptureStatus('info', `${response.name || 'Profile'} queued for sync`);
            setProgress(100, 'Queued');
          }
        } else if (response) {
          clearTimeout(progressTimer1);
          clearTimeout(progressTimer2);
          clearTimeout(progressTimer3);
          resetProgress();
          showCaptureStatus('error', response.error || 'Capture failed.');
        }
      } catch (raceError) {
        clearTimeout(progressTimer1);
        clearTimeout(progressTimer2);
        clearTimeout(progressTimer3);
        
        if (raceError.message === 'timeout') {
          setProgress(90, 'Still processing...');
          showCaptureStatus('info', 'Capture running on page. Check the page for results.');
        } else {
          throw raceError;
        }
      }
      
    } catch (error) {
      resetProgress();
      
      if (error.message && error.message.includes('Receiving end does not exist')) {
        showCaptureStatus('error', 'Extension not active. Please refresh the Naukri page.');
      } else if (error.message && error.message.includes('Could not establish connection')) {
        showCaptureStatus('error', 'Content script not loaded. Refresh the Naukri page.');
      } else {
        showCaptureStatus('info', 'Capture triggered. Check the page for results.');
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
    
    chrome.storage.sync.get(['vhc_api_url'], (result) => {
      if (result.vhc_api_url) {
        document.getElementById('apiUrl').value = result.vhc_api_url;
      }
    });
  }
  
  async function showDashboard(user) {
    loginSection.style.display = 'none';
    dashboardSection.style.display = 'block';
    
    document.getElementById('userName').textContent = user.name || 'User';
    document.getElementById('userRole').textContent = user.role || 'Member';
    
    chrome.storage.sync.get(['vhc_api_url'], (result) => {
      document.getElementById('apiUrlDisplay').textContent = result.vhc_api_url || '-';
    });
    
    chrome.storage.sync.get(['enabled', 'showNotifications'], (result) => {
      document.getElementById('settingEnabled').checked = result.enabled !== false;
      document.getElementById('settingNotifications').checked = result.showNotifications !== false;
    });
    
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
        if ((tab.url.includes('/v3/preview') && tab.url.includes('tabKey=profile')) ||
            tab.url.includes('viewResume') || tab.url.includes('view-resume') || 
            tab.url.includes('cvPreview')) {
          setPageStatus('green', 'Naukri profile page detected');
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
  
  function showError(message) {
    loginError.textContent = message;
    loginError.style.display = 'block';
    setTimeout(() => {
      loginError.style.display = 'none';
    }, 5000);
  }
  
  function showCaptureStatus(type, message) {
    captureStatus.textContent = message;
    captureStatus.className = `capture-result visible ${type}`;
    
    if (type !== 'error') {
      setTimeout(() => {
        captureStatus.classList.remove('visible');
        // Also hide progress bar after success fades
        if (type === 'success') {
          setTimeout(() => resetProgress(), 500);
        }
      }, 8000);
    }
  }
  
  function hideCaptureStatus() {
    captureStatus.className = 'capture-result';
  }
});
