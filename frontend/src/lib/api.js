import axios from 'axios';
import { captureApiError } from './errorCapture';

// Use REACT_APP_BACKEND_URL if set (for AWS/custom domain deployments),
// otherwise fall back to relative '/api' (for same-origin/ingress setups)
const envUrl = process.env.REACT_APP_BACKEND_URL;
const API_BASE = envUrl ? `${envUrl.replace(/\/+$/, '')}/api` : '/api';

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

// ── Refresh token rotation state ──
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (token) resolve(token);
    else reject(error);
  });
  failedQueue = [];
};

// Handle auth errors: attempt refresh before logout + auto-capture API failures
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Only attempt refresh on 401, not on the refresh endpoint itself, and not already retried
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/refresh') &&
      !originalRequest.url?.includes('/auth/login')
    ) {
      const refreshToken = localStorage.getItem('vhc_refresh_token');

      if (refreshToken) {
        // If already refreshing, queue this request
        if (isRefreshing) {
          return new Promise((resolve, reject) => {
            failedQueue.push({ resolve, reject });
          }).then((newToken) => {
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return api(originalRequest);
          });
        }

        originalRequest._retry = true;
        isRefreshing = true;

        try {
          const res = await axios.post(`${API_BASE}/auth/refresh`, {
            refresh_token: refreshToken,
          });
          const { access_token, refresh_token: newRefresh } = res.data;

          localStorage.setItem('vhc_token', access_token);
          if (newRefresh) localStorage.setItem('vhc_refresh_token', newRefresh);
          if (res.data.user) localStorage.setItem('vhc_user', JSON.stringify(res.data.user));

          api.defaults.headers.common.Authorization = `Bearer ${access_token}`;
          processQueue(null, access_token);

          // Retry the original request with new token
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          return api(originalRequest);
        } catch (refreshError) {
          processQueue(refreshError, null);
          // Refresh failed — full logout
          localStorage.removeItem('vhc_token');
          localStorage.removeItem('vhc_refresh_token');
          localStorage.removeItem('vhc_user');
          if (window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
          return Promise.reject(refreshError);
        } finally {
          isRefreshing = false;
        }
      }

      // No refresh token — immediate logout
      localStorage.removeItem('vhc_token');
      localStorage.removeItem('vhc_refresh_token');
      localStorage.removeItem('vhc_user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
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
  migrateEmail: (id, newEmail) => api.post(`/admin/users/${id}/migrate-email`, { new_email: newEmail }),
  getEmployers: () => api.get('/admin/employers'),
  assignRecruiter: (recruiterId, employerId) => api.post('/admin/assign-recruiter', null, { params: { recruiter_id: recruiterId, employer_id: employerId } }),
  getEmployerCompanies: (employerId) => api.get(`/employers/${employerId}/companies`),
};

// Admin APIs
export const adminAPI = {
  getPipeline: (params) => api.get('/admin/pipeline', { params }),
  getPipelineFilters: (params) => api.get('/admin/pipeline/filters', { params }),  // Phase 54.12
  getHiringFunnel: (params) => api.get('/hiring-funnel', { params }),
  getCompanyProfile: (companyId) => api.get(`/companies/${companyId}/profile`),
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
  getSuggestions: (jobId) => api.get(`/jobs/${jobId}/suggestions`),
  refreshSuggestions: (jobId) => api.post(`/jobs/${jobId}/suggestions/refresh`),
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
  employerApproval: (id, data) => api.post(`/applications/${id}/employer-approval`, data),
  getPendingApproval: (params) => api.get('/applications/pending-approval', { params }),
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
    return api.post('/cv-upload/parse', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  getParseStatus: (taskId) => api.get(`/cv-upload/parse/${taskId}`),
  /**
   * Parse a CV and poll until the background task completes.
   * Returns the completed task result or throws on failure.
   */
  parseAndPoll: async (file, { onProgress, pollInterval = 3000, maxAttempts = 90 } = {}) => {
    const res = await cvUploadAPI.parse(file);
    const taskId = res.data.task_id;
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, pollInterval));
      const status = await cvUploadAPI.getParseStatus(taskId);
      onProgress?.(status.data);
      if (status.data.status === 'completed') return status.data.result;
      if (status.data.status === 'failed') throw new Error(status.data.error || 'Parsing failed');
    }
    throw new Error('CV parsing timed out. Please try again.');
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
  getDuplicateEmployers: () => api.get('/teams/duplicate-employers'),
};

// Bills / Invoices — Phase 55.6
export const billsAPI = {
  list: (params = {}) => api.get('/bills', { params }),
  getById: (id) => api.get(`/bills/${id}`),
  create: (payload) => api.post('/bills', payload),
  update: (id, payload) => api.put(`/bills/${id}`, payload),
  cancel: (id) => api.delete(`/bills/${id}`),
  pdfUrl: (id) => `${API_BASE}/bills/${id}/pdf`,
  previewMail: (id) => api.post(`/bills/${id}/preview-mail`),
  send: (id, payload = {}) => api.post(`/bills/${id}/send`, payload),
  markPaid: (id) => api.post(`/bills/${id}/mark-paid`),
  // Bank accounts (fix.docx 2026-09-15)
  listBankAccounts: () => api.get('/bills/bank-accounts'),
  createBankAccount: (data) => api.post('/bills/bank-accounts', data),
  updateBankAccount: (id, data) => api.put(`/bills/bank-accounts/${id}`, data),
  deleteBankAccount: (id) => api.delete(`/bills/bank-accounts/${id}`),
};

// Employer Portal APIs (Internal OS Enhancement)
export const employerPortalAPI = {
  // My Team panel - team members, mandates, pipelines, revenue
  getMyTeam: () => api.get('/employer/my-team'),
  // Companies panel - assigned companies with commercials, mandates, pipelines
  getMyCompanies: () => api.get('/employer/companies'),
  // Pipeline view - all applications with stage control
  getPipeline: (params) => api.get('/employer/pipeline', { params }),
  // Employer self-create company (auto-assigned)
  createCompany: (data) => api.post('/employer/companies', data),
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
  getPendingJobs: () => api.get('/jobs/pending-approval'),
  transitionJob: (jobId, newStatus, reason) => api.post(`/jobs/${jobId}/transition`, { new_status: newStatus, reason }),
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

// Team Lead APIs — recruiter promoted to acting-employer by their employer/admin
export const teamLeadAPI = {
  grant: (recruiterId, employerId = null) =>
    api.post('/team-lead/grant', { recruiter_id: recruiterId, ...(employerId ? { employer_id: employerId } : {}) }),
  revoke: (recruiterId) => api.post('/team-lead/revoke', { recruiter_id: recruiterId }),
  getScope: () => api.get('/team-lead/scope'),
  listForEmployer: (employerId) => api.get(`/team-lead/list/${employerId}`),
};

// Asha Agent APIs — v2 virtual recruiter
export const ashaAPI = {
  getConfig: () => api.get('/agent/config'),
  listSessions: (params) => api.get('/agent/sessions', { params }),
  getSession: (id) => api.get(`/agent/sessions/${id}`),
  reverse: (id) => api.post(`/agent/sessions/${id}/reverse`),
  takeover: (id) => api.post(`/agent/sessions/${id}/takeover`),
  send: (id, text) => api.post(`/agent/sessions/${id}/send`, { text }),
  resume: (id) => api.post(`/agent/sessions/${id}/resume`),
  analytics: (params) => api.get('/agent/analytics', { params }),
  listSlots: (mandateId) => api.get('/agent/slots', { params: { mandate_id: mandateId } }),
  addSlot: (payload) => api.post('/agent/slots', payload),
  deleteSlot: (slotId) => api.delete(`/agent/slots/${slotId}`),
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
  apiKeyUsage: () => api.get('/api-keys/usage'),
  extractionQuality: () => api.get('/stats/extraction-quality'),
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
  listOrganizations: () => api.get('/linkedin/organizations'),
  testPost: () => api.post('/linkedin/test-post'),
  getPostHistory: (limit = 20) => api.get(`/linkedin/post-history?limit=${limit}`),
  disconnect: () => api.delete('/linkedin/disconnect'),
  // Job draft flow — stopgap until w_organization_social scope approval.
  listJobDrafts: (params) => api.get('/linkedin/job-drafts', { params }),
  getJobDraft: (jobId) => api.get(`/linkedin/job-drafts/${jobId}`),
  toggleJobDraftPosted: (jobId, posted) =>
    api.post(`/linkedin/job-drafts/${jobId}/toggle-posted`, { posted }),
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
  reorderColumns: (trackerId, columns) => api.put(`/tracker/trackers/${trackerId}/columns`, columns),
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

// Talent Search v2 — hybrid (semantic + lexical) retrieval with A/B
// comparison. Powered by `/api/talent/search`. Returns both `hybrid`
// (BGE vector + cross-encoder rerank + LTR) and `lexical` (the old
// regex-only path) so the team can validate side-by-side before cutover.
export const talentSearchAPI = {
  search: (params) => api.post('/talent/search', params),
};

// Phase 54 — ML-powered sourcing (XGBoost LTR + k-Means diversification +
// PCA-compressed embeddings). Used by AdvancedSearchPage and
// FindCandidatesPage AI tab to re-rank vector-search results by historical
// "did this candidate progress past sourced?" probability.
export const sourcingAPI = {
  // POST /api/sourcing/rerank — top-K re-ranked + diversified candidates
  // params: { job_id?, query?, top_k?, diversify? }
  rerank: (params) => api.post('/sourcing/rerank', params),
  // GET /api/sourcing/health — model_loaded, AUC, RAM. For Admin diag tile.
  health: () => api.get('/sourcing/health'),
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

// Phase 54.15 — Daily Team Performance Digest (WhatsApp-ready)
export const teamDigestAPI = {
  today:        () => api.get('/admin/daily-digest'),
  byDate:       (date) => api.get(`/admin/daily-digest/${date}`),
  recent:       (days = 7) => api.get('/admin/daily-digest/recent', { params: { days } }),
  regenerate:   () => api.post('/admin/daily-digest/regenerate'),
  regenForDate: (date) => api.post(`/admin/daily-digest/${date}/regenerate`),
  whatsappStatus:   () => api.get('/admin/daily-digest/whatsapp/status'),
  whatsappSendTest: () => api.post('/admin/daily-digest/whatsapp/send-test'),
};

export const revenueAPI = {
  forecast: (applicationId, expectedCtc) => api.post('/revenue/forecast', { application_id: applicationId, expected_ctc: expectedCtc }),
  offered: (appId, data) => api.post(`/revenue/offered/${appId}`, data),
  hired: (appId, data) => api.post(`/revenue/hired/${appId}`, data),
  joined: (appId, data) => api.post(`/revenue/joined/${appId}`, data),
  byApplication: (appId) => api.get(`/revenue/by-application/${appId}`),
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
  // Auto-Generation Pipeline
  bulkGenerate: (data) => api.post('/blog/bulk-generate', data),
  triggerPipeline: () => api.post('/blog/auto-pipeline'),
  getPipelineStatus: () => api.get('/blog/pipeline-status'),
  // AI Topic Research
  researchTopics: (data) => api.post('/blog/research-topics', data),
  // Sitemap & Digest
  sendDigest: () => api.post('/blog/send-digest'),
  // Joinings (fix.docx 2026-09-15)
  listJoinings: (params = {}) => api.get('/blog/joinings', { params }),
  updateJoining: (applicationId, data) => api.patch(`/blog/joinings/${applicationId}`, data),
};

// "Candidates called" tracking (fix.docx) — fire-and-forget. `source` is
// one of badge_expand | profile_modal | called_button.
export const trackCandidateCalled = (candidateId, source, extra = {}) => {
  if (!candidateId) return Promise.resolve();
  return api
    .post('/extension/candidate-called', { candidate_id: candidateId, source, ...extra })
    .catch(() => {});
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
  autocomplete: (params) => api.get('/candidate-bank/autocomplete', { params }),
  getNotes: (candidateId) => api.get(`/candidate-bank/notes/${candidateId}`),
  addNote: (candidateId, text) => api.post(`/candidate-bank/notes/${candidateId}`, { text }),
  deleteNote: (candidateId, noteId) => api.delete(`/candidate-bank/notes/${candidateId}/${noteId}`),
  getPhoneBlocklist: () => api.get('/candidate-bank/data-quality/phone-blocklist'),
  addToBlocklist: (numbers) => api.post('/candidate-bank/data-quality/phone-blocklist', { numbers }),
  removeFromBlocklist: (phone) => api.delete(`/candidate-bank/data-quality/phone-blocklist/${phone}`),
  cleanupBlockedNumbers: () => api.post('/candidate-bank/data-quality/phone-blocklist/cleanup'),
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
      timeout: 60000, // 60s per file — frontend sends one file at a time
    });
  },
  batchSave: (candidates, mandateId) => api.post('/candidate-bank/batch-save', { candidates, mandate_id: mandateId || null }),
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
  // Duplicate Detection
  checkDuplicates: (data) => api.post('/candidate-bank/check-duplicates', data),
  delete: (id) => api.delete(`/candidate-bank/${id}`),
  findAllDuplicates: () => api.get('/candidate-bank/find-all-duplicates'),
  mergeDuplicates: (candidateIds, masterId = null) => api.post(
    '/candidate-bank/merge-duplicates',
    masterId ? { candidate_ids: candidateIds, master_id: masterId } : { candidate_ids: candidateIds },
  ),
  mergeAllDuplicates: () => api.post('/candidate-bank/merge-all-duplicates'),
  // Data Quality
  dataQualityStats: () => api.get('/candidate-bank/data-quality/stats'),
  dataQualityTeamStats: () => api.get('/candidate-bank/data-quality/team-stats'),
  dataQualityIncomplete: (params) => api.get('/candidate-bank/data-quality/incomplete', { params }),
  dataQualityUpdate: (id, data) => api.put(`/candidate-bank/data-quality/update/${id}`, data),
  // Failed Capture Recovery
  getFailedCaptures: (params) => api.get('/candidate-bank/failed-captures', { params }),
  saveFailedCapture: (id, data) => api.post(`/candidate-bank/failed-captures/${id}/save-to-bank`, data),
  bulkDismissCaptures: (ids) => api.post('/candidate-bank/failed-captures/bulk-dismiss', { ids }),
  autoClassifyCaptures: (autoDismiss = false) => api.post('/candidate-bank/failed-captures/auto-classify', { auto_dismiss: autoDismiss }),
};

// Extension API (Naukri profile capture)
export const extensionAPI = {
  getProfile: (candidateId) => api.get(`/extension/profile/${candidateId}`),
  getStats: () => api.get('/extension/stats'),
  reEnrich: (candidateId) => api.post(`/extension/re-enrich/${candidateId}`),
};

// Bulk Import APIs (Admin only)
export const bulkImportAPI = {
  // Download template
  downloadTemplate: () => api.get('/admin/bulk-import/template', { responseType: 'blob' }),
  // Parse Excel (Mode A) — supports multiple files
  parseExcel: (files) => {
    const formData = new FormData();
    const fileList = Array.isArray(files) ? files : [files];
    fileList.forEach(f => formData.append('excel_files', f));
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
  bulkAttachCV: (files) => {
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    return api.post('/admin/bulk-import/bulk-attach-cv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
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
  getGeoViolations: (params) => api.get('/attendance/geo-violations', { params }),
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
  // Employer Team Attendance (read-only)
  getEmployerTeamAttendance: (params) => api.get('/attendance/team/all', { params }),
  getEmployerTeamMonthlyReport: (params) => api.get('/attendance/team/report/monthly', { params }),
  getEmployerTeamToday: () => api.get('/attendance/team/today'),
};

// ─── Resume Generator ──────────────────────────────────────
export const resumeAPI = {
  getTemplates: () => api.get('/resume/templates'),
  generate: (profile, templateId) => api.post('/resume/generate', { profile, template_id: templateId }),
  getMyProfile: () => api.get('/resume/my-profile'),
  getCandidateProfile: (candidateId) => api.get(`/resume/candidate/${candidateId}`),
  aiEnhance: (bullets) => api.post('/resume/ai-enhance', { bullets }),
  compilePdf: (latex) => api.post('/resume/compile-pdf', { latex }, { responseType: 'blob' }),
  generatePdf: (profile, templateId) => api.post('/resume/generate-pdf', { profile, template_id: templateId }, { responseType: 'blob' }),
  getCapabilities: () => api.get('/resume/capabilities'),
};

// ─── Account Manager ──────────────────────────────────────
export const accountManagerAPI = {
  assign: (recruiterId, companyIds) => api.post('/account-manager/assign', { recruiter_id: recruiterId, company_ids: companyIds }),
  removeCompany: (recruiterId, companyId) => api.post('/account-manager/remove-company', { recruiter_id: recruiterId, company_id: companyId }),
  getMyCompanies: () => api.get('/account-manager/my-companies'),
  getCompanyJobs: (companyId) => api.get(`/account-manager/company/${companyId}/jobs`),
  getCompanyPipeline: (companyId) => api.get(`/account-manager/company/${companyId}/pipeline`),
  getCompanyAnalytics: (companyId) => api.get(`/account-manager/company/${companyId}/analytics`),
  getRecruiters: () => api.get('/account-manager/recruiters'),
  assignCandidate: (applicationId, recruiterId) => api.post('/account-manager/assign-candidate', { application_id: applicationId, recruiter_id: recruiterId }),
  getDashboardStats: () => api.get('/account-manager/dashboard-stats'),
};

// ─── Notifications ──────────────────────────────────────
export const notificationAPI = {
  getAll: (params) => api.get('/notifications', { params }),
  getUnreadCount: () => api.get('/notifications/unread-count'),
  markRead: (id) => api.put(`/notifications/${id}/read`),
  markAllRead: () => api.put('/notifications/read-all'),
  deleteOne: (id) => api.delete(`/notifications/${id}`),
  getPreferences: () => api.get('/notifications/preferences'),
  updatePreferences: (prefs) => api.put('/notifications/preferences', prefs),
};

export const activityAPI = {
  getCandidateActivity: (candidateId, params) => api.get(`/activity/candidate/${candidateId}`, { params }),
  getGlobalFeed: (params) => api.get('/activity/feed', { params }),
  getStats: (params) => api.get('/activity/stats', { params }),
  getActions: () => api.get('/activity/actions'),
};

// ─── API Metrics (System Health Dashboard) ──────────────
export const apiMetricsAPI = {
  getOverview: (range = '1h') => api.get('/system-health/api-metrics/overview', { params: { range } }),
  getTimeseries: (range = '1h') => api.get('/system-health/api-metrics/timeseries', { params: { range } }),
  getTopEndpoints: (range = '1h', sort = 'errors') => api.get('/system-health/api-metrics/top-endpoints', { params: { range, sort } }),
  getDbHealth: () => api.get('/system-health/api-metrics/db-health'),
};

// ─── Finance API (Accounts Role) ──────────────────────────
export const financeAPI = {
  // Invoices
  listInvoices: (params) => api.get('/finance/invoices', { params }),
  createInvoice: (data) => api.post('/finance/invoices', data),
  getInvoice: (id) => api.get(`/finance/invoices/${id}`),
  updateInvoice: (id, data) => api.patch(`/finance/invoices/${id}`, data),
  sendInvoice: (id) => api.post(`/finance/invoices/${id}/send`),
  markPaid: (id) => api.post(`/finance/invoices/${id}/mark-paid`),
  deleteInvoice: (id) => api.delete(`/finance/invoices/${id}`),
  // Clients
  listClients: (params) => api.get('/finance/clients', { params }),
  createClient: (data) => api.post('/finance/clients', data),
  updateClient: (id, data) => api.patch(`/finance/clients/${id}`, data),
  deleteClient: (id) => api.delete(`/finance/clients/${id}`),
  // Expenses
  listExpenses: (params) => api.get('/finance/expenses', { params }),
  createExpense: (data) => api.post('/finance/expenses', data),
  updateExpense: (id, data) => api.patch(`/finance/expenses/${id}`, data),
  deleteExpense: (id) => api.delete(`/finance/expenses/${id}`),
  // Dashboard & Reports
  revenueDashboard: (period) => api.get('/finance/revenue-dashboard', { params: { period } }),
  reportPnL: (params) => api.get('/finance/reports/pnl', { params }),
  reportAging: () => api.get('/finance/reports/aging'),
  reportGST: (params) => api.get('/finance/reports/gst-summary', { params }),
  // Exports
  exportInvoices: (params) => api.get('/finance/export/invoices', { params }),
  exportExpenses: (params) => api.get('/finance/export/expenses', { params }),
};

export default api;
