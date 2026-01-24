import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API_BASE = `${BACKEND_URL}/api`;

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

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('vhc_token');
      localStorage.removeItem('vhc_user');
      window.location.href = '/login';
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

// Company APIs
export const companyAPI = {
  create: (data) => api.post('/companies', data),
  getAll: () => api.get('/companies'),
  getById: (id) => api.get(`/companies/${id}`),
  update: (id, data) => api.put(`/companies/${id}`, data),
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

// Revenue APIs
export const revenueAPI = {
  calculate: (applicationId, offeredSalary) => api.post('/revenue/calculate', null, { params: { application_id: applicationId, offered_salary: offeredSalary } }),
  override: (revenueId, manualOverride, reason) => api.put(`/revenue/${revenueId}/override`, null, { params: { manual_override: manualOverride, reason } }),
  getPipeline: (params) => api.get('/revenue/pipeline', { params }),
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
  getAssignments: (jobId) => api.get(`/jobs/${jobId}/assignments`),
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

// AI Matching APIs
export const matchingAPI = {
  parseResume: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/ai/parse-resume', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  parseJD: (text, file) => {
    const formData = new FormData();
    if (text) formData.append('jd_text', text);
    if (file) formData.append('file', file);
    return api.post('/ai/parse-jd', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  findCandidates: (params) => api.post('/matching/find-candidates', params),
  getJobsForCandidate: () => api.get('/matching/jobs-for-candidate'),
};

// Candidate Data Bank APIs
export const candidateBankAPI = {
  add: (file, email, name) => {
    const formData = new FormData();
    formData.append('file', file);
    if (email) formData.append('email', email);
    if (name) formData.append('name', name);
    return api.post('/candidate-bank/add', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getAll: (params) => api.get('/candidate-bank', { params }),
  getById: (id) => api.get(`/candidate-bank/${id}`),
  update: (id, data) => api.put(`/candidate-bank/${id}`, data),
  getAuditLog: (id) => api.get(`/candidate-bank/${id}/audit-log`),
  getResumeHistory: (id) => api.get(`/candidate-bank/${id}/resume-history`),
  // Data Governance: Get candidate activity history (internal only)
  getHistory: (id) => api.get(`/candidate-bank/${id}/history`),
  // Resume download URL (use window.open or anchor tag)
  getResumeDownloadUrl: (id) => `${API_BASE}/candidate-bank/${id}/download-resume`,
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
  linkToJob: (candidateId, jobId) => api.post('/applications/link-candidate', { candidate_id: candidateId, job_id: jobId }),
};

export default api;
