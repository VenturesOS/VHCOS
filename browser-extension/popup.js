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
});
