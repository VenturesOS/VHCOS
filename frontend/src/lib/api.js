import axios from 'axios';
import { captureApiError } from './errorCapture';

// Use relative URL to avoid CORS issues on custom domains
const API_BASE = '/api';

// Create axios instance
const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('vhc_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors + auto-capture API failures
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('vhc_token');
      localStorage.removeItem('vhc_user');
      window.location.href = '/login';
    }
    // Auto-capture API errors for System Health monitoring
    if (error.response) {
      captureApiError(
        error.config?.method?.toUpperCase(),
        error.config?.url,
        error.response.status,
        error.response.data,
      );
    }
    return Promise.reject(error);
  }
);

// Auth APIs
export const authAPI = {
  login: (email, password) => api.post('/auth/login', { email, password }),
  register: (data) => api.post('/auth/register', data),
  getMe: () => api.get('/auth/me'),
  resetPassword: (currentPassword, newPassword) => api.post('/auth/reset-password', { current_password: currentPassword, new_password: newPassword }),
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }),
  forgotPasswordReset: (token, newPassword) => api.post('/auth/forgot-password/reset', { token, new_password: newPassword }),
};

// User APIs (Admin)
export const userAPI = {
  getAll: () => api.get('/users'),
  getById: (id) => api.get(`/users/${id}`),
  update: (id, data) => api.put(`/users/${id}`, data),
  delete: (id) => api.delete(`/users/${id}`),
  // Admin-specific endpoints
  create: (data) => api.post('/admin/users', data),
  resetPassword: (id, newPassword) => api.post(`/admin/users/${id}/reset-password`, { new_password: newPassword }),
  toggleStatus: (id) => api.post(`/admin/users/${id}/toggle-status`),
  getEmployers: () => api.get('/admin/employers'),
  assignRecruiter: (recruiterId, employerId) => api.post('/admin/assign-recruiter', null, { params: { recruiter_id: recruiterId, employer_id: employerId } }),
  getEmployerCompanies: (employerId) => api.get(`/employers/${employerId}/companies`),
};

// Admin APIs
export const adminAPI = {
  getPipeline: (params) => api.get('/admin/pipeline', { params }),
};

// Job APIs
export const jobAPI = {
  create: (data) => api.post('/jobs', data),
  getAll: (params) => api.get('/jobs', { params }),
  browse: (params) => api.get('/jobs/browse', { params }),
  getById: (id) => api.get(`/jobs/${id}`),
  update: (id, data) => api.put(`/jobs/${id}`, data),
  delete: (id) => api.delete(`/jobs/${id}`),
  getApplicants: (jobId, params) => api.get(`/jobs/${jobId}/applicants`, { params }),
  // Career Page Publishing Control (Internal OS Enhancement)
  updateCareerPageStatus: (jobId, newStatus, reason) => 
    api.post(`/jobs/${jobId}/career-page-status`, { new_status: newStatus, reason }),
  getCareerPageHistory: (jobId) => api.get(`/jobs/${jobId}/career-page-history`),
  // Public career page jobs
  getCareerPageJobs: () => api.get('/career-page/jobs'),
  // Shareable Job Link Control (Career Page)
  updateShareableLink: (jobId, enabled) => api.put(`/jobs/${jobId}/shareable-link`, { enabled }),
  // Mandate Shareable Link Control (Independent of Career Page)
  updateMandateShareableLink: (jobId, enabled) => api.put(`/jobs/${jobId}/mandate-shareable-link`, { enabled }),
  // JD Parser
  parseJD: (jdText) => api.post('/jobs/parse-jd', { jd_text: jdText }),
};

// Application APIs
export const applicationAPI = {
  create: (data) => api.post('/applications', data),
  getAll: (params) => api.get('/applications', { params }),
  getById: (id) => api.get(`/applications/${id}`),
  update: (id, data) => api.put(`/applications/${id}`, data),
  updateDetails: (id, data) => api.put(`/applications/${id}/details`, data),
  getEditHistory: (id) => api.get(`/applications/${id}/edit-history`),
  addNote: (id, content) => api.post(`/applications/${id}/notes`, { content }),
  downloadResume: (id) => `${API_BASE}/applications/${id}/resume`,
  delete: (id) => api.delete(`/applications/${id}`),
};

// Candidate APIs
export const candidateAPI = {
  getProfile: () => api.get('/profile'),
  updateProfile: (data) => api.put('/profile', data),
  uploadResume: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/profile/resume', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getAll: () => api.get('/candidates'),
  getById: (id) => api.get(`/candidates/${id}`),
  downloadResume: (id) => `${API_BASE}/candidates/${id}/resume`,
};

// CV Upload APIs
export const cvUploadAPI = {
  parse: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/cv-upload/parse', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 });
  },
  save: (data) => api.post('/cv-upload/save', data),
};

// Company APIs
export const companyAPI = {
  create: (data) => api.post('/companies', data),
  getAll: () => api.get('/companies'),
  getById: (id) => api.get(`/companies/${id}`),
  update: (id, data) => api.put(`/companies/${id}`, data),
  delete: (id) => api.delete(`/companies/${id}`),
  assignEmployer: (companyId, employerId) => api.put(`/companies/${companyId}/assign-employer`, null, { params: { employer_id: employerId } }),
};

// Team APIs (Admin only - Phase A Governance)
export const teamAPI = {
  create: (data) => api.post('/teams', data),
  getAll: () => api.get('/teams'),
  getById: (id) => api.get(`/teams/${id}`),
  update: (id, data) => api.put(`/teams/${id}`, data),
  delete: (id) => api.delete(`/teams/${id}`),
};

// Employer Portal APIs (Internal OS Enhancement)
export const employerPortalAPI = {
  // My Team panel - team members, mandates, pipelines, revenue
  getMyTeam: () => api.get('/employer/my-team'),
  // Companies panel - assigned companies with commercials, mandates, pipelines
  getMyCompanies: () => api.get('/employer/companies'),
  // Pipeline view - all applications with stage control
  getPipeline: (params) => api.get('/employer/pipeline', { params }),
};

// Referral APIs (Phase A Governance)
export const referralAPI = {
  create: (data) => api.post('/referrals', data),
  getAll: (params) => api.get('/referrals', { params }),
  getById: (id) => api.get(`/referrals/${id}`),
  transition: (id, newStatus, reason) => api.post(`/referrals/${id}/transition`, { new_status: newStatus, reason }),
  linkCandidate: (id, candidateId) => api.post(`/referrals/${id}/link-candidate`, null, { params: { candidate_id: candidateId } }),
};

// Admin Governance APIs (Phase A)
export const governanceAPI = {
  getHierarchy: () => api.get('/admin/hierarchy'),
  getPendingJobs: () => api.get('/jobs/pending-approval'),
  transitionJob: (jobId, newStatus, reason) => api.post(`/jobs/${jobId}/transition`, { new_status: newStatus, reason }),
};

// Commercial Intelligence APIs
export const commercialAPI = {
  create: (data) => api.post('/commercials', data),
  getAll: (params) => api.get('/commercials', { params }),
  getById: (id) => api.get(`/commercials/${id}`),
  update: (id, data) => api.put(`/commercials/${id}`, data),
  delete: (id) => api.delete(`/commercials/${id}`),
};

// Analytics APIs
export const analyticsAPI = {
  getAdmin: (params) => api.get('/analytics/admin', { params }),
  getEmployer: (params) => api.get('/analytics/employer', { params }),
  getCompanyPipeline: (companyId) => api.get(`/companies/${companyId}/pipeline`),
};

// JD Parsing API
export const jdAPI = {
  parse: (data) => {
    const formData = new FormData();
    if (data.jd_text) formData.append('jd_text', data.jd_text);
    if (data.jd_file) formData.append('jd_file', data.jd_file);
    return api.post('/jobs/parse-jd', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
};

// Mandate Assignment API
export const mandateAPI = {
  assignRecruiters: (jobId, recruiterIds) => api.post(`/jobs/${jobId}/assign-recruiters`, recruiterIds),
  removeRecruiter: (jobId, recruiterId) => api.delete(`/jobs/${jobId}/assign-recruiters/${recruiterId}`),
  getAssignments: (jobId) => api.get(`/jobs/${jobId}/assignments`),
  getTeamRecruiters: () => api.get('/employer/team-recruiters'),
};

// Message APIs
export const messageAPI = {
  send: (data) => api.post('/messages', data),
  getInbox: () => api.get('/messages'),
  getSent: () => api.get('/messages', { params: { sent: true } }),
  markRead: (id) => api.put(`/messages/${id}/read`),
};

// Stats APIs
export const statsAPI = {
  admin: () => api.get('/stats/admin'),
  recruiter: () => api.get('/stats/recruiter'),
  employer: () => api.get('/stats/employer'),
  candidate: () => api.get('/stats/candidate'),
};

// Settings APIs
export const settingsAPI = {
  get: () => api.get('/settings'),
  update: (data) => api.put('/settings', data),
};

// LinkedIn Integration APIs
export const linkedinAPI = {
  getSettings: () => api.get('/linkedin/settings'),
  updateSettings: (data) => api.put('/linkedin/settings', data),
  getStatus: () => api.get('/linkedin/status'),
  authorize: () => api.get('/linkedin/authorize'),
  testPost: () => api.post('/linkedin/test-post'),
  getPostHistory: (limit = 20) => api.get(`/linkedin/post-history?limit=${limit}`),
  disconnect: () => api.delete('/linkedin/disconnect'),
};

// Tracker APIs
export const trackerAPI = {
  // Master columns
  getColumns: () => api.get('/tracker/columns'),
  // Templates
  getTemplates: (params) => api.get('/tracker/templates', { params }),
  getTemplate: (id) => api.get(`/tracker/templates/${id}`),
  createTemplate: (data) => api.post('/tracker/templates', data),
  updateTemplate: (id, data) => api.put(`/tracker/templates/${id}`, data),
  cloneTemplate: (id, name) => api.post(`/tracker/templates/${id}/clone?name=${encodeURIComponent(name)}`),
  deleteTemplate: (id) => api.delete(`/tracker/templates/${id}`),
  // Trackers
  getTrackers: (params) => api.get('/tracker/trackers', { params }),
  getTracker: (id) => api.get(`/tracker/trackers/${id}`),
  createTracker: (data) => api.post('/tracker/trackers', data),
  deleteTracker: (id) => api.delete(`/tracker/trackers/${id}`),
  duplicateTracker: (id, data) => api.post(`/tracker/trackers/${id}/duplicate`, data),
  // Rows
  addRow: (trackerId, data) => api.post(`/tracker/trackers/${trackerId}/rows`, data),
  updateRow: (trackerId, rowId, data) => api.put(`/tracker/trackers/${trackerId}/rows/${rowId}`, data),
  updateRowStatus: (trackerId, rowId, status) => api.put(`/tracker/trackers/${trackerId}/rows/${rowId}/status`, { submission_status: status }),
  deleteRow: (trackerId, rowId) => api.delete(`/tracker/trackers/${trackerId}/rows/${rowId}`),
  // Validation & Events
  validate: (trackerId) => api.get(`/tracker/trackers/${trackerId}/validation`),
  getEvents: (params) => api.get('/tracker/events', { params }),
  // Export & Import
  exportExcel: (trackerId) => api.get(`/tracker/trackers/${trackerId}/export`, { responseType: 'blob' }),
  uploadFile: (trackerId, file) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post(`/tracker/trackers/${trackerId}/upload`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  parseTemplateFile: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post('/tracker/parse-template-file', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
};


// AI Matching APIs
export const matchingAPI = {
  parseResume: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/ai/parse-resume', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  /**
   * Parse Job Description using AI
   * @param {string} text - JD text (for paste mode)
   * @param {File} file - JD file (for upload mode - PDF, DOC, DOCX)
   * @param {string} inputType - 'paste' or 'upload'
   */
  parseJD: (text, file, inputType = 'paste') => {
    const formData = new FormData();
    if (text) formData.append('jd_text', text);
    if (file) formData.append('jd_file', file);
    formData.append('input_type', inputType);
    return api.post('/jobs/parse-jd', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  findCandidates: (params) => api.post('/matching/find-candidates', params),
  getMatchJobStatus: (jobId) => api.get(`/matching/jobs/${jobId}/status`),
  getMatchHistory: () => api.get('/matching/history'),
  getMatchHistoryDetail: (id) => api.get(`/matching/history/${id}`),
  getJobsForCandidate: () => api.get('/matching/jobs-for-candidate'),
  // Shortlist candidate from AI screening - adds to job pipeline
  shortlistCandidate: (candidateId, jobId, notes = null) => 
    api.post('/matching/shortlist', { candidate_id: candidateId, job_id: jobId, notes }),
};

export const aiSearchAPI = {
  search: (params) => api.post('/ai-search', params),
};

// Bug Reports APIs
export const bugReportsAPI = {
  create: (data) => api.post('/bug-reports', data),
  getAll: (status) => api.get('/bug-reports', { params: status ? { status } : {} }),
  getOne: (id) => api.get(`/bug-reports/${id}`),
  update: (id, params) => api.put(`/bug-reports/${id}`, null, { params }),
  getStats: () => api.get('/bug-reports/stats/summary'),
};

// System Errors APIs (Admin)
export const systemErrorsAPI = {
  getAll: (params) => api.get('/system-errors', { params }),
  getStats: () => api.get('/system-errors/stats'),
  clear: (days) => api.delete('/system-errors/clear', { params: { days } }),
};

// Contact Form APIs (Admin)
export const contactAPI = {
  getAll: (status) => api.get('/contact-submissions', { params: status ? { status } : {} }),
  updateStatus: (id, status) => api.put(`/contact-submissions/${id}/status`, null, { params: { new_status: status } }),
  delete: (id) => api.delete(`/contact-submissions/${id}`),
};

// Blog Engine APIs
export const pillarPageAPI = {
  getBySlug: (slug) => api.get(`/pillar-pages/${slug}`),
  adminList: () => api.get('/admin/pillar-pages'),
  adminGet: (slug) => api.get(`/admin/pillar-pages/${slug}`),
  adminCreate: (data) => api.post('/admin/pillar-pages', data),
  adminUpdate: (slug, data) => api.put(`/admin/pillar-pages/${slug}`, data),
  adminDelete: (slug) => api.delete(`/admin/pillar-pages/${slug}`),
};

export const seoDashboardAPI = {
  getLive: () => api.get('/admin/seo-dashboard'),
  createSnapshot: () => api.post('/admin/seo-snapshot'),
  getSnapshots: () => api.get('/admin/seo-snapshots'),
  getAlerts: () => api.get('/admin/seo-alerts'),
  resolveAlert: (id) => api.post(`/admin/seo-alerts/resolve/${id}`),
};

export const digestAPI = {
  list: () => api.get('/admin/blog-digests'),
  trigger: () => api.post('/admin/blog-digest/trigger'),
  preview: (weekKey) => api.get('/admin/blog-digest/preview', { params: weekKey ? { week_key: weekKey } : {} }),
  send: (segments, weekKey) => api.post('/admin/blog-digest/send', { segments, week_key: weekKey || null }),
  recipients: (segments) => api.get('/admin/blog-digest/recipients', { params: { segments } }),
  sendLogs: () => api.get('/admin/blog-digest/send-logs'),
  subscriptionStats: () => api.get('/admin/blog-digest/subscription-stats'),
};

export const revenueAPI = {
  forecast: (applicationId, expectedCtc) => api.post('/revenue/forecast', { application_id: applicationId, expected_ctc: expectedCtc }),
  offered: (appId, data) => api.post(`/revenue/offered/${appId}`, data),
  hired: (appId, data) => api.post(`/revenue/hired/${appId}`, data),
  joined: (appId, data) => api.post(`/revenue/joined/${appId}`, data),
  records: (params) => api.get('/revenue/records', { params }),
  byApplication: (appId) => api.get(`/revenue/by-application/${appId}`),
  aggregateByCompany: (from, to) => api.get('/revenue/aggregate/by-company', { params: { from_date: from, to_date: to } }),
  aggregateByJob: (from, to) => api.get('/revenue/aggregate/by-job', { params: { from_date: from, to_date: to } }),
  aggregateByRecruiter: (from, to) => api.get('/revenue/aggregate/by-recruiter', { params: { from_date: from, to_date: to } }),
};

export const blogAPI = {
  // Admin
  generate: (data) => api.post('/blog/generate', data),
  adminList: (params) => api.get('/blog/admin/list', { params }),
  adminGet: (id) => api.get(`/blog/admin/${id}`),
  adminUpdate: (id, data) => api.put(`/blog/admin/${id}`, data),
  publish: (id) => api.put(`/blog/admin/${id}/publish`),
  unpublish: (id) => api.put(`/blog/admin/${id}/unpublish`),
  adminDelete: (id) => api.delete(`/blog/admin/${id}`),
  // Public
  employerList: (page) => api.get('/blog/employer', { params: { page } }),
  employerBySlug: (slug) => api.get(`/blog/employer/${slug}`),
  candidateList: (page, category) => api.get('/blog/candidate', { params: { page, category } }),
  candidateBySlug: (slug) => api.get(`/blog/candidate/${slug}`),
  // Analytics
  trackEvent: (data) => api.post('/blog/track', data),
  analyticsStats: (days) => api.get('/blog/analytics/stats', { params: { days } }),
  analyticsViews: (days) => api.get('/blog/analytics/views-over-time', { params: { days } }),
  analyticsTopBlogs: (days, limit) => api.get('/blog/analytics/top-blogs', { params: { days, limit } }),
  analyticsTopClicks: (days, limit) => api.get('/blog/analytics/top-clicks', { params: { days, limit } }),
  // Schedule
  getSchedule: () => api.get('/blog/schedule/config'),
  updateSchedule: (data) => api.put('/blog/schedule/config', data),
  triggerPublish: (blogType) => api.post(`/blog/schedule/trigger?blog_type=${blogType}`),
  getScheduleLog: (limit) => api.get('/blog/schedule/log', { params: { limit } }),
  // AI Topic Research
  researchTopics: (data) => api.post('/blog/research-topics', data),
  // Sitemap & Digest
  sendDigest: () => api.post('/blog/send-digest'),
};

// Candidate Data Bank APIs
export const candidateBankAPI = {
  add: (file, email, name) => {
    const formData = new FormData();
    formData.append('file', file);
    if (email) formData.append('email', email);
    if (name) formData.append('name', name);
    return api.post('/candidate-bank/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getAll: (params) => api.get('/candidate-bank', { params }),
  getById: (id) => api.get(`/candidate-bank/${id}`),
  update: (id, data) => api.patch(`/candidate-bank/${id}`, data),
  getAuditLog: (id) => api.get(`/candidate-bank/${id}/audit-log`),
  getResumeHistory: (id) => api.get(`/candidate-bank/${id}/resume-history`),
  // Data Governance: Get candidate activity history (internal only)
  getHistory: (id) => api.get(`/candidate-bank/${id}/history`),
  // Resume download URL (use window.open or anchor tag)
  getResumeDownloadUrl: (id) => `${API_BASE}/candidate-bank/${id}/download-resume`,
  getAtsCvUrl: (id) => `${API_BASE}/candidate-bank/${id}/ats-cv`,
  // Phase-2: Batch upload
  batchParse: (files) => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    return api.post('/candidate-bank/batch-parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  batchSave: (candidates) => api.post('/candidate-bank/batch-save', { candidates }),
  // Data Governance: Update mandatory fields (salary, notice, location, experience)
  updateMandatoryFields: (id, data) => 
    api.put(`/candidate-bank/${id}/salary-notice`, null, { 
      params: { 
        current_salary: data.currentSalary, 
        notice_period: data.noticePeriod,
        location: data.location,
        experience_years: data.experienceYears
      } 
    }),
  // Backward compatible alias
  updateSalaryNotice: (id, currentSalary, noticePeriod, location, experienceYears) => 
    api.put(`/candidate-bank/${id}/salary-notice`, null, { 
      params: { 
        current_salary: currentSalary, 
        notice_period: noticePeriod,
        location,
        experience_years: experienceYears
      } 
    }),
  // Phase-2: Link candidate to job
  linkToJob: (candidateId, jobId, expectedSalary) => api.post('/applications/link-candidate', { 
    candidate_id: candidateId, 
    job_id: jobId,
    expected_salary: expectedSalary
  }),
  // Attach CV to bulk-imported candidate (no CV initially)
  attachCV: (candidateId, file) => {
    const formData = new FormData();
    formData.append('cv_file', file);
    return api.put(`/admin/bulk-import/attach-cv/${candidateId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

// Extension API (Naukri profile capture)
export const extensionAPI = {
  getProfile: (candidateId) => api.get(`/extension/profile/${candidateId}`),
  getStats: () => api.get('/extension/stats'),
};

// Bulk Import APIs (Admin only)
export const bulkImportAPI = {
  // Download template
  downloadTemplate: () => api.get('/admin/bulk-import/template', { responseType: 'blob' }),
  // Parse Excel (Mode A)
  parseExcel: (file) => {
    const formData = new FormData();
    formData.append('excel_file', file);
    return api.post('/admin/bulk-import/excel', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  // Parse CV/ZIP (Mode B)
  parseCVZip: (file) => {
    const formData = new FormData();
    formData.append('zip_file', file);
    return api.post('/admin/bulk-import/cv-zip', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  // Save candidates
  save: (batchId, mode, candidates) => api.post('/admin/bulk-import/save', {
    batch_id: batchId,
    mode,
    candidates
  }),
  // Get all batches
  getBatches: () => api.get('/admin/bulk-import/batches'),
  // Get batch details
  getBatchDetails: (batchId) => api.get(`/admin/bulk-import/batches/${batchId}`),
  // Get restricted candidates
  getRestrictedCandidates: () => api.get('/admin/bulk-import/restricted-candidates'),
  // Attach CV to candidate
  attachCV: (candidateId, file) => {
    const formData = new FormData();
    formData.append('cv_file', file);
    return api.put(`/admin/bulk-import/attach-cv/${candidateId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

// Attendance & Leave Management APIs
export const attendanceAPI = {
  // Attendance
  checkIn: (data) => api.post('/attendance/check-in', data),
  checkOut: (data) => api.post('/attendance/check-out', data),
  getMyAttendance: (params) => api.get('/attendance/my', { params }),
  getTodayStatus: () => api.get('/attendance/today'),
  getTeamAttendance: (params) => api.get('/attendance/team', { params }),
  getAllAttendance: (params) => api.get('/attendance/all', { params }),
  adminMark: (data) => api.post('/attendance/admin/mark', data),
  getMonthlyReport: (params) => api.get('/attendance/report/monthly', { params }),
  exportExcel: (params) => api.get('/attendance/report/export', { params, responseType: 'blob' }),
  getSettings: () => api.get('/attendance/settings'),
  updateSettings: (data) => api.put('/attendance/settings', data),
  // Leave
  requestLeave: (data) => api.post('/attendance/leave/request', data),
  getMyLeaveRequests: (params) => api.get('/attendance/leave/requests/my', { params }),
  getPendingLeaves: () => api.get('/attendance/leave/requests/pending'),
  getAllLeaveRequests: (params) => api.get('/attendance/leave/requests/all', { params }),
  approveLeave: (id, data) => api.put(`/attendance/leave/requests/${id}/approve`, data || {}),
  rejectLeave: (id, data) => api.put(`/attendance/leave/requests/${id}/reject`, data || {}),
  getMyLeaveBalance: (params) => api.get('/attendance/leave/balance', { params }),
  getUserLeaveBalance: (userId, params) => api.get(`/attendance/leave/balance/${userId}`, { params }),
  setUserLeaveBalance: (userId, data, params) => api.put(`/attendance/leave/admin/balance/${userId}`, data, { params }),
  getAllLeaveBalances: (params) => api.get('/attendance/leave/admin/balances', { params }),
  // Holidays
  getHolidays: (params) => api.get('/attendance/holidays', { params }),
  createHoliday: (data) => api.post('/attendance/holidays', data),
  updateHoliday: (id, data) => api.put(`/attendance/holidays/${id}`, data),
  deleteHoliday: (id) => api.delete(`/attendance/holidays/${id}`),
  // Analytics & Intelligence
  getAnalytics: (params) => api.get('/attendance/analytics', { params }),
  getHealthScores: (params) => api.get('/attendance/analytics/health-scores', { params }),
  getNotifications: (params) => api.get('/attendance/analytics/notifications', { params }),
  markNotificationRead: (id) => api.put(`/attendance/analytics/notifications/${id}/read`),
  markAllRead: () => api.put('/attendance/analytics/notifications/read-all'),
  getCronLogs: (params) => api.get('/attendance/analytics/cron-logs', { params }),
  triggerReminders: () => api.post('/attendance/analytics/cron/trigger-reminders'),
  triggerAutoAbsent: () => api.post('/attendance/analytics/cron/trigger-auto-absent'),
  // Pause & Reset
  getStatus: () => api.get('/attendance/status'),
  preLaunchReset: (data) => api.post('/attendance/admin/pre-launch-reset', data),
};

// ─── Resume Generator ──────────────────────────────────────
export const resumeAPI = {
  getTemplates: () => api.get('/resume/templates'),
  generate: (profile, templateId) => api.post('/resume/generate', { profile, template_id: templateId }),
  getMyProfile: () => api.get('/resume/my-profile'),
  getCandidateProfile: (candidateId) => api.get(`/resume/candidate/${candidateId}`),
  aiEnhance: (bullets) => api.post('/resume/ai-enhance', { bullets }),
};

export default api;
