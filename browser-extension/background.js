/**
 * VHC Talent OS - Background Service Worker
 * Handles API communication and offline queue
 */

// Configuration
const CONFIG = {
  SYNC_INTERVAL: 30000,  // 30 seconds
  MAX_QUEUE_SIZE: 100,
  RETRY_DELAY: 5000
};

// Initialize
chrome.runtime.onInstalled.addListener(() => {
  console.log('[VHC Extension] Installed');
  
  // Set default settings
  chrome.storage.sync.set({
    enabled: true,
    showNotifications: true,
    autoCapture: true,
    stats: {
      captured_today: 0,
      captured_week: 0,
      captured_total: 0,
      updated_total: 0,
      last_reset: new Date().toDateString()
    }
  });
  
  // Initialize offline queue
  chrome.storage.local.set({ offlineQueue: [] });
  
  // Set up periodic sync
  chrome.alarms.create('syncQueue', { periodInMinutes: 1 });
});

// Handle alarms
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'syncQueue') {
    processOfflineQueue();
  }
});

// Listen for messages from content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'captureProfile') {
    handleProfileCapture(request.data)
      .then(sendResponse)
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true; // Keep channel open for async response
  }
  
  if (request.action === 'getStats') {
    getStats().then(sendResponse);
    return true;
  }
  
  if (request.action === 'login') {
    handleLogin(request.data).then(sendResponse);
    return true;
  }
  
  if (request.action === 'logout') {
    handleLogout().then(sendResponse);
    return true;
  }
  
  if (request.action === 'checkAuth') {
    checkAuth().then(sendResponse);
    return true;
  }

  if (request.action === 'apiProxy') {
    handleApiProxy(request.data).then(sendResponse).catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }
});

/**
 * Handle profile capture from content script
 */
async function handleProfileCapture(profileData) {
  try {
    const auth = await getAuth();
    
    if (!auth) {
      return { success: false, error: 'Not logged in' };
    }
    
    // Check if online
    if (!navigator.onLine) {
      await addToQueue(profileData);
      return { success: true, action: 'queued' };
    }
    
    // Send to API
    const response = await fetch(`${auth.apiUrl}/api/extension/capture`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`
      },
      body: JSON.stringify(profileData)
    });
    
    if (!response.ok) {
      if (response.status === 401) {
        // Token expired
        await handleLogout();
        return { success: false, error: 'Session expired. Please login again.' };
      }
      
      const error = await response.json();
      throw new Error(error.detail || 'API error');
    }
    
    const result = await response.json();
    
    // Update stats
    await updateStats(result.action);
    
    return {
      success: true,
      action: result.action,  // 'created', 'updated', 'exists'
      candidate_id: result.candidate_id
    };
    
  } catch (error) {
    console.error('[VHC Extension] Capture error:', error);
    
    // If network error, queue for later
    if (error.name === 'TypeError' || error.message.includes('network')) {
      await addToQueue(profileData);
      return { success: true, action: 'queued' };
    }
    
    return { success: false, error: error.message };
  }
}

/**
 * Add profile to offline queue
 */
async function addToQueue(profileData) {
  return new Promise((resolve) => {
    chrome.storage.local.get(['offlineQueue'], (result) => {
      const queue = result.offlineQueue || [];
      
      // Check for duplicates
      const exists = queue.some(item => 
        item.naukri_profile_id === profileData.naukri_profile_id
      );
      
      if (!exists && queue.length < CONFIG.MAX_QUEUE_SIZE) {
        queue.push({
          ...profileData,
          queued_at: new Date().toISOString()
        });
        
        chrome.storage.local.set({ offlineQueue: queue }, resolve);
      } else {
        resolve();
      }
    });
  });
}

/**
 * Process offline queue when online
 */
async function processOfflineQueue() {
  if (!navigator.onLine) return;
  
  const auth = await getAuth();
  if (!auth) return;
  
  chrome.storage.local.get(['offlineQueue'], async (result) => {
    const queue = result.offlineQueue || [];
    if (queue.length === 0) return;
    
    console.log(`[VHC Extension] Processing ${queue.length} queued profiles`);
    
    const newQueue = [];
    
    for (const profileData of queue) {
      try {
        const response = await fetch(`${auth.apiUrl}/api/extension/capture`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${auth.token}`
          },
          body: JSON.stringify(profileData)
        });
        
        if (response.ok) {
          const result = await response.json();
          await updateStats(result.action);
          console.log(`[VHC Extension] Synced: ${profileData.name}`);
        } else if (response.status !== 401) {
          // Keep in queue if not auth error
          newQueue.push(profileData);
        }
        
      } catch (error) {
        // Keep in queue on error
        newQueue.push(profileData);
      }
      
      // Small delay between requests
      await new Promise(r => setTimeout(r, 500));
    }
    
    chrome.storage.local.set({ offlineQueue: newQueue });
  });
}

/**
 * Update capture statistics
 */
async function updateStats(action) {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['stats'], (result) => {
      const stats = result.stats || {
        captured_today: 0,
        captured_week: 0,
        captured_total: 0,
        updated_total: 0,
        last_reset: new Date().toDateString()
      };
      
      // Reset daily counter if needed
      const today = new Date().toDateString();
      if (stats.last_reset !== today) {
        stats.captured_today = 0;
        stats.last_reset = today;
        
        // Reset weekly on Sunday
        if (new Date().getDay() === 0) {
          stats.captured_week = 0;
        }
      }
      
      // Update counters
      if (action === 'created') {
        stats.captured_today++;
        stats.captured_week++;
        stats.captured_total++;
      } else if (action === 'updated') {
        stats.updated_total++;
      }
      
      chrome.storage.sync.set({ stats }, resolve);
    });
  });
}

/**
 * Get current stats
 */
async function getStats() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['stats'], (result) => {
      resolve(result.stats || {
        captured_today: 0,
        captured_week: 0,
        captured_total: 0,
        updated_total: 0
      });
    });
    
    // Also get queue size
    chrome.storage.local.get(['offlineQueue'], (result) => {
      const queueSize = (result.offlineQueue || []).length;
      // Stats will include queue size
    });
  });
}

/**
 * Handle login
 */
async function handleLogin(credentials) {
  try {
    const response = await fetch(`${credentials.apiUrl}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: credentials.email,
        password: credentials.password
      })
    });
    
    // Check content type before parsing — non-JSON means wrong URL or server error
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      return { success: false, error: 'Invalid Portal URL. Please check the URL and try again.' };
    }
    
    const data = await response.json();
    
    if (!response.ok) {
      return { success: false, error: data.detail || 'Login failed' };
    }
    
    // Store auth info (include phone for recruiter blocklist in content.js)
    await new Promise((resolve) => {
      chrome.storage.sync.set({
        vhc_token: data.access_token,
        vhc_api_url: credentials.apiUrl,
        vhc_user: {
          email: credentials.email,
          name: data.user?.name || credentials.email,
          role: data.user?.role || 'unknown',
          phone: data.user?.phone || null
        }
      }, resolve);
    });
    
    return { success: true, user: data.user };
    
  } catch (error) {
    if (error.message.includes('JSON') || error.name === 'SyntaxError') {
      return { success: false, error: 'Invalid Portal URL. Please check the URL and try again.' };
    }
    if (error.name === 'TypeError' || error.message.includes('fetch')) {
      return { success: false, error: 'Cannot reach server. Please check the Portal URL.' };
    }
    return { success: false, error: error.message };
  }
}

/**
 * Handle logout
 */
async function handleLogout() {
  return new Promise((resolve) => {
    chrome.storage.sync.remove(['vhc_token', 'vhc_api_url', 'vhc_user'], () => {
      resolve({ success: true });
    });
  });
}

/**
 * Check authentication status
 */
async function checkAuth() {
  const auth = await getAuth();
  if (!auth) {
    return { authenticated: false };
  }
  
  return new Promise((resolve) => {
    chrome.storage.sync.get(['vhc_user'], (result) => {
      resolve({
        authenticated: true,
        user: result.vhc_user
      });
    });
  });
}

/**
 * Get stored auth credentials
 */
async function getAuth() {
  return new Promise((resolve) => {
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

// Listen for online/offline events
self.addEventListener('online', () => {
  console.log('[VHC Extension] Back online, processing queue...');
  processOfflineQueue();
});
