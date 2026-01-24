import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { candidateBankAPI, jobAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { Search, Upload, Database, User, Mail, Phone, MapPin, FileText, Clock, History, Plus, Files, Briefcase, DollarSign, AlertCircle, CalendarDays, Activity, TrendingUp } from 'lucide-react';

// Notice period options
const NOTICE_PERIODS = [
  "Immediate",
  "15 days",
  "30 days",
  "45 days",
  "60 days",
  "90 days",
  "90+ days"
];

export default function CandidateDataBankPage() {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [skills, setSkills] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [auditLog, setAuditLog] = useState([]);
  const [resumeHistory, setResumeHistory] = useState([]);
  const [activityHistory, setActivityHistory] = useState(null);  // Data Governance: Activity history
  const fileInputRef = useRef(null);
  const [uploadForm, setUploadForm] = useState({ email: '', name: '' });
  
  // Task 2: Add as Applicant state
  const [showAddApplicant, setShowAddApplicant] = useState(false);
  const [applicantCandidate, setApplicantCandidate] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [editSalary, setEditSalary] = useState('');
  const [editNotice, setEditNotice] = useState('');
  const [editLocation, setEditLocation] = useState('');  // Data Governance: mandatory field
  const [editExperience, setEditExperience] = useState('');  // Data Governance: mandatory field
  const [linking, setLinking] = useState(false);

  useEffect(() => {
    loadCandidates();
  }, []);

  // Load jobs for the Add as Applicant dialog
  const loadJobs = async () => {
    try {
      const res = await jobAPI.getAll();
      setJobs(res.data.filter(j => j.status === 'active'));
    } catch (error) {
      console.error('Failed to load jobs', error);
    }
  };

  // Open Add as Applicant dialog
  const openAddApplicantDialog = (candidate) => {
    setApplicantCandidate(candidate);
    setEditSalary(candidate.current_salary?.toString() || '');
    setEditNotice(candidate.notice_period || '');
    setEditLocation(candidate.location || '');  // Data Governance
    setEditExperience(candidate.experience_years?.toString() || '0');  // Data Governance
    setSelectedJobId('');
    loadJobs();
    setShowAddApplicant(true);
  };

  // Handle Add as Applicant
  const handleAddAsApplicant = async () => {
    // Validate mandatory fields (Data Governance)
    const salaryNum = parseInt(editSalary);
    const expNum = parseInt(editExperience);
    
    if (!editSalary || salaryNum <= 0) {
      toast.error('Current salary (INR) is mandatory');
      return;
    }
    if (!editNotice) {
      toast.error('Notice period is mandatory');
      return;
    }
    if (!editLocation || !editLocation.trim()) {
      toast.error('Location is mandatory');
      return;
    }
    if (editExperience === '' || isNaN(expNum) || expNum < 0) {
      toast.error('Experience (years) is mandatory');
      return;
    }
    if (!selectedJobId) {
      toast.error('Please select a job');
      return;
    }

    setLinking(true);
    try {
      // First update mandatory fields if changed
      const needsUpdate = (
        salaryNum !== applicantCandidate.current_salary || 
        editNotice !== applicantCandidate.notice_period ||
        editLocation !== applicantCandidate.location ||
        expNum !== applicantCandidate.experience_years
      );
      
      if (needsUpdate) {
        await candidateBankAPI.updateSalaryNotice(
          applicantCandidate.id, 
          salaryNum, 
          editNotice,
          editLocation.trim(),
          expNum
        );
      }

      // Then link to job
      const res = await candidateBankAPI.linkToJob(applicantCandidate.id, selectedJobId);
      toast.success(res.data.message);
      setShowAddApplicant(false);
      loadCandidates(); // Refresh to show updated data
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (typeof detail === 'object' && detail.message) {
        toast.error(detail.message);
        // Show specific field errors if present
        if (detail.errors) {
          detail.errors.forEach(err => toast.error(err));
        }
      } else if (typeof detail === 'string') {
        toast.error(detail);
      } else {
        toast.error('Failed to add as applicant');
      }
    } finally {
      setLinking(false);
    }
  };

  const loadCandidates = async () => {
    setLoading(true);
    try {
      const params = {};
      if (search) params.search = search;
      if (skills) params.skills = skills;
      const res = await candidateBankAPI.getAll(params);
      setCandidates(res.data);
    } catch (error) {
      toast.error('Failed to load candidates');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    loadCandidates();
  };

  const handleUpload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const res = await candidateBankAPI.add(file, uploadForm.email, uploadForm.name);
      toast.success(res.data.message);
      setShowUpload(false);
      setUploadForm({ email: '', name: '' });
      loadCandidates();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const loadCandidateDetails = async (candidate) => {
    setSelectedCandidate(candidate);
    try {
      const [auditRes, historyRes, activityRes] = await Promise.all([
        candidateBankAPI.getAuditLog(candidate.id),
        candidateBankAPI.getResumeHistory(candidate.id),
        candidateBankAPI.getHistory(candidate.id),  // Data Governance: Activity history
      ]);
      setAuditLog(auditRes.data);
      setResumeHistory(historyRes.data);
      setActivityHistory(activityRes.data);
    } catch (error) {
      console.error('Failed to load details');
    }
  };

  return (
    <div className="space-y-6" data-testid="candidate-bank-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Candidate Data Bank</h1>
          <p className="text-slate-500 mt-1">Centralized candidate database with deduplication</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => navigate('batch-upload')}
            data-testid="batch-upload-btn"
          >
            <Files className="w-4 h-4 mr-2" /> Batch Upload
          </Button>
          <Button
            onClick={() => setShowUpload(true)}
            className="bg-[#7CB342] hover:bg-[#689F38]"
            data-testid="add-candidate-btn"
          >
            <Plus className="w-4 h-4 mr-2" /> Add Candidate
          </Button>
        </div>
      </div>

      {/* Search & Filters */}
      <Card className="border-slate-200">
        <CardContent className="p-4">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name or email"
                className="pl-10"
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <div className="w-full md:w-64">
              <Input
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
                placeholder="Filter by skills (comma-separated)"
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <Button onClick={handleSearch} variant="outline">
              <Search className="w-4 h-4 mr-2" /> Search
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Candidates List */}
      <Card className="border-slate-200">
        <CardHeader className="border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Database className="w-5 h-5 text-[#7CB342]" />
            Candidates ({candidates.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="spinner" />
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {candidates.map((candidate) => (
                <div
                  key={candidate.id}
                  className="p-4 hover:bg-slate-50 transition-colors cursor-pointer"
                  onClick={() => loadCandidateDetails(candidate)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                        <span className="text-[#7CB342] font-semibold">
                          {candidate.name?.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <p className="font-medium text-slate-900">{candidate.name}</p>
                        <p className="text-sm text-slate-500">{candidate.headline || candidate.email}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="hidden md:flex flex-wrap gap-1 max-w-xs">
                        {candidate.skills?.slice(0, 4).map((skill) => (
                          <span
                            key={skill}
                            className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full"
                          >
                            {skill}
                          </span>
                        ))}
                        {(candidate.skills?.length || 0) > 4 && (
                          <span className="text-xs text-slate-400">+{candidate.skills.length - 4}</span>
                        )}
                      </div>
                      {/* Source Badge */}
                      <span className={`px-2 py-1 text-xs rounded-full font-medium ${
                        candidate.source === 'job_application' ? 'bg-blue-50 text-blue-600' :
                        candidate.source === 'recruiter_upload' ? 'bg-purple-50 text-purple-600' :
                        candidate.source === 'candidate_registration' ? 'bg-green-50 text-green-600' :
                        'bg-slate-100 text-slate-600'
                      }`}>
                        {candidate.source === 'job_application' ? 'Applied' :
                         candidate.source === 'recruiter_upload' ? 'Recruiter Upload' :
                         candidate.source === 'candidate_registration' ? 'Registered' :
                         'Direct Upload'}
                      </span>
                      {/* Status */}
                      {candidate.is_active !== false && (
                        <span className="w-2 h-2 bg-green-500 rounded-full" title="Active"></span>
                      )}
                      {/* Add as Applicant Button */}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          openAddApplicantDialog(candidate);
                        }}
                        className="text-[#7CB342] border-[#7CB342] hover:bg-green-50"
                        data-testid={`add-applicant-btn-${candidate.id}`}
                      >
                        <Briefcase className="w-4 h-4 mr-1" /> Add as Applicant
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
              {candidates.length === 0 && (
                <div className="text-center py-12">
                  <Database className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                  <p className="text-slate-500 mb-2">No candidates in data bank</p>
                  <p className="text-sm text-slate-400 mb-4">Add candidates by uploading resumes or wait for job applications</p>
                  <Button 
                    onClick={() => setShowUpload(true)}
                    className="bg-[#7CB342] hover:bg-[#689F38]"
                  >
                    <Upload className="w-4 h-4 mr-2" /> Upload First Resume
                  </Button>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upload Dialog */}
      <Dialog open={showUpload} onOpenChange={setShowUpload}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Add Candidate from Resume</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center">
              <input
                type="file"
                ref={fileInputRef}
                onChange={(e) => handleUpload(e.target.files?.[0])}
                accept=".pdf,.doc,.docx,.txt"
                className="hidden"
              />
              <Upload className="w-10 h-10 text-slate-400 mx-auto mb-2" />
              <p className="text-sm text-slate-500 mb-2">Upload resume (PDF, DOC, TXT)</p>
              <p className="text-xs text-slate-400 mb-4">AI will automatically parse and extract candidate data</p>
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                {uploading ? 'Processing...' : 'Choose File'}
              </Button>
            </div>
            <div className="space-y-2">
              <Input
                value={uploadForm.email}
                onChange={(e) => setUploadForm({ ...uploadForm, email: e.target.value })}
                placeholder="Override email (optional)"
              />
            </div>
            <div className="space-y-2">
              <Input
                value={uploadForm.name}
                onChange={(e) => setUploadForm({ ...uploadForm, name: e.target.value })}
                placeholder="Override name (optional)"
              />
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Candidate Detail Dialog */}
      <Dialog open={!!selectedCandidate} onOpenChange={() => setSelectedCandidate(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">Candidate Profile</DialogTitle>
          </DialogHeader>
          {selectedCandidate && (
            <Tabs defaultValue="profile" className="w-full">
              <TabsList className="mb-4">
                <TabsTrigger value="profile">Profile</TabsTrigger>
                <TabsTrigger value="activity" data-testid="activity-history-tab">
                  <Activity className="w-4 h-4 mr-1" /> Activity History
                </TabsTrigger>
                <TabsTrigger value="resumes">Resume History</TabsTrigger>
                <TabsTrigger value="audit">Audit Log</TabsTrigger>
              </TabsList>

              <TabsContent value="profile">
                <div className="space-y-4">
                  <div className="flex items-center gap-4">
                    <div className="w-16 h-16 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                      <span className="text-[#7CB342] font-bold text-2xl">
                        {selectedCandidate.name?.charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <h3 className="font-semibold text-xl">{selectedCandidate.name}</h3>
                      <p className="text-slate-500">{selectedCandidate.headline}</p>
                    </div>
                  </div>

                  {/* Data Governance: Profile Freshness Metadata */}
                  {(selectedCandidate.last_profile_updated_at || selectedCandidate.last_application_date) && (
                    <div className="bg-slate-50 rounded-lg p-3 flex flex-wrap gap-4 text-sm">
                      {selectedCandidate.last_profile_updated_at && (
                        <div className="flex items-center gap-2 text-slate-600">
                          <CalendarDays className="w-4 h-4 text-blue-500" />
                          <span>Profile Updated: {new Date(selectedCandidate.last_profile_updated_at).toLocaleDateString()}</span>
                        </div>
                      )}
                      {selectedCandidate.last_application_date && (
                        <div className="flex items-center gap-2 text-slate-600">
                          <Briefcase className="w-4 h-4 text-green-500" />
                          <span>Last Applied: {new Date(selectedCandidate.last_application_date).toLocaleDateString()}</span>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="flex items-center gap-2 text-slate-600">
                      <Mail className="w-4 h-4" /> {selectedCandidate.email}
                    </div>
                    {selectedCandidate.phone && (
                      <div className="flex items-center gap-2 text-slate-600">
                        <Phone className="w-4 h-4" /> {selectedCandidate.phone}
                      </div>
                    )}
                    {selectedCandidate.location && (
                      <div className="flex items-center gap-2 text-slate-600">
                        <MapPin className="w-4 h-4" /> {selectedCandidate.location}
                      </div>
                    )}
                    <div className="flex items-center gap-2 text-slate-600">
                      <Clock className="w-4 h-4" /> {selectedCandidate.experience_years || 0} years exp
                    </div>
                    {selectedCandidate.current_salary && (
                      <div className="flex items-center gap-2 text-slate-600">
                        <DollarSign className="w-4 h-4" /> {formatSalaryINR(selectedCandidate.current_salary)}
                      </div>
                    )}
                    {selectedCandidate.notice_period && (
                      <div className="flex items-center gap-2 text-slate-600">
                        <Clock className="w-4 h-4" /> Notice: {selectedCandidate.notice_period}
                      </div>
                    )}
                  </div>

                  {selectedCandidate.summary && (
                    <div>
                      <h4 className="font-medium mb-2">Summary</h4>
                      <p className="text-sm text-slate-600">{selectedCandidate.summary}</p>
                    </div>
                  )}

                  <div>
                    <h4 className="font-medium mb-2">Skills</h4>
                    <div className="flex flex-wrap gap-1">
                      {selectedCandidate.skills?.map((skill) => (
                        <span
                          key={skill}
                          className="px-2 py-1 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>

                  {selectedCandidate.experience?.length > 0 && (
                    <div>
                      <h4 className="font-medium mb-2">Experience</h4>
                      <div className="space-y-2">
                        {selectedCandidate.experience.map((exp, i) => (
                          <div key={i} className="p-3 bg-slate-50 rounded-lg">
                            <p className="font-medium">{exp.title}</p>
                            <p className="text-sm text-slate-500">{exp.company} • {exp.duration}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </TabsContent>

              {/* Data Governance: Activity History Tab */}
              <TabsContent value="activity" data-testid="activity-history-content">
                <div className="space-y-4">
                  {/* Summary Stats */}
                  {activityHistory?.summary && (
                    <div className="grid grid-cols-3 gap-3 mb-4">
                      <div className="bg-blue-50 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-blue-600">{activityHistory.summary.total_applications}</p>
                        <p className="text-xs text-blue-600">Total Applications</p>
                      </div>
                      <div className="bg-green-50 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-green-600">{activityHistory.summary.stages?.hired || 0}</p>
                        <p className="text-xs text-green-600">Hired</p>
                      </div>
                      <div className="bg-amber-50 rounded-lg p-3 text-center">
                        <p className="text-2xl font-bold text-amber-600">{activityHistory.summary.stages?.interview || 0}</p>
                        <p className="text-xs text-amber-600">Interviews</p>
                      </div>
                    </div>
                  )}

                  {/* Freshness Info */}
                  {activityHistory?.freshness && (
                    <div className="bg-slate-50 rounded-lg p-3 text-sm space-y-1">
                      <p className="font-medium text-slate-700 mb-2">Profile Freshness</p>
                      <div className="flex items-center gap-2 text-slate-600">
                        <CalendarDays className="w-4 h-4" />
                        Created: {activityHistory.freshness.profile_created_at ? new Date(activityHistory.freshness.profile_created_at).toLocaleDateString() : 'N/A'}
                      </div>
                      <div className="flex items-center gap-2 text-slate-600">
                        <TrendingUp className="w-4 h-4" />
                        Last Profile Update: {activityHistory.freshness.last_profile_updated_at ? new Date(activityHistory.freshness.last_profile_updated_at).toLocaleDateString() : 'Never'}
                      </div>
                      <div className="flex items-center gap-2 text-slate-600">
                        <Briefcase className="w-4 h-4" />
                        Last Application: {activityHistory.freshness.last_application_date ? new Date(activityHistory.freshness.last_application_date).toLocaleDateString() : 'Never'}
                      </div>
                    </div>
                  )}

                  {/* Application History */}
                  <div>
                    <h4 className="font-medium mb-2">Application History</h4>
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {activityHistory?.applications?.map((app) => (
                        <div key={app.application_id} className="p-3 bg-slate-50 rounded-lg text-sm border-l-4 border-[#7CB342]">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-medium text-slate-800">{app.job_title}</span>
                            <span className={`px-2 py-0.5 text-xs rounded-full ${
                              app.stage === 'hired' ? 'bg-green-100 text-green-700' :
                              app.stage === 'rejected' ? 'bg-red-100 text-red-700' :
                              app.stage === 'interview' ? 'bg-blue-100 text-blue-700' :
                              app.stage === 'offered' ? 'bg-purple-100 text-purple-700' :
                              'bg-slate-100 text-slate-600'
                            }`}>
                              {app.stage}
                            </span>
                          </div>
                          <p className="text-slate-500">{app.company_name}</p>
                          <div className="flex items-center gap-4 mt-1 text-xs text-slate-400">
                            <span>Applied: {new Date(app.applied_at).toLocaleDateString()}</span>
                            <span>Source: {app.source}</span>
                            {app.current_salary_at_application && (
                              <span>Salary: {formatSalaryINR(app.current_salary_at_application)}</span>
                            )}
                          </div>
                        </div>
                      ))}
                      {(!activityHistory?.applications || activityHistory.applications.length === 0) && (
                        <p className="text-slate-400 text-sm">No application history</p>
                      )}
                    </div>
                  </div>

                  {/* Profile Audit Trail */}
                  {activityHistory?.profile_audit?.length > 0 && (
                    <div>
                      <h4 className="font-medium mb-2">Recent Profile Changes</h4>
                      <div className="space-y-1 max-h-40 overflow-y-auto">
                        {activityHistory.profile_audit.map((entry, idx) => (
                          <div key={idx} className="p-2 bg-amber-50 rounded text-xs">
                            <span className="font-medium">{entry.field}</span>: {String(entry.old_value) || 'null'} → {String(entry.new_value)}
                            <span className="text-slate-400 ml-2">by {entry.changed_by_name} ({entry.changed_by_role})</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="resumes">
                <div className="space-y-3">
                  <p className="text-sm text-slate-500">
                    Active: {resumeHistory?.active_resume_id || 'None'}
                  </p>
                  {resumeHistory?.resume_versions?.map((resume) => (
                    <div
                      key={resume.id}
                      className={`p-3 rounded-lg border ${
                        resume.is_active ? 'border-[#7CB342] bg-[#DCFCE7]/20' : 'border-slate-200'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <FileText className="w-4 h-4 text-slate-400" />
                          <span className="font-medium">{resume.filename}</span>
                          {resume.is_active && (
                            <span className="px-2 py-0.5 bg-[#7CB342] text-white text-xs rounded-full">Active</span>
                          )}
                        </div>
                        <span className="text-xs text-slate-400">
                          {new Date(resume.uploaded_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  ))}
                  {(!resumeHistory?.resume_versions || resumeHistory.resume_versions.length === 0) && (
                    <p className="text-slate-400 text-sm">No resume history</p>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="audit">
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {auditLog.map((log) => (
                    <div key={log.id} className="p-3 bg-slate-50 rounded-lg text-sm">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-slate-700">
                          {log.field_changed}
                        </span>
                        <span className="text-xs text-slate-400">
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-slate-500">
                        <span className="text-red-500 line-through">{log.old_value || 'null'}</span>
                        {' → '}
                        <span className="text-green-600">{log.new_value}</span>
                      </p>
                      <p className="text-xs text-slate-400 mt-1">
                        By {log.updated_by_name} ({log.updated_by_role}) via {log.source}
                      </p>
                    </div>
                  ))}
                  {auditLog.length === 0 && (
                    <p className="text-slate-400 text-sm">No audit history</p>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>

      {/* Add as Applicant Dialog */}
      <Dialog open={showAddApplicant} onOpenChange={setShowAddApplicant}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <Briefcase className="w-5 h-5 text-[#7CB342]" />
              Add as Applicant
            </DialogTitle>
            <DialogDescription>
              Add this candidate to a job as an applicant. Salary and notice period are required.
            </DialogDescription>
          </DialogHeader>

          {applicantCandidate && (
            <div className="space-y-4 py-4">
              {/* Candidate Info */}
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                    <span className="text-[#7CB342] font-semibold">
                      {applicantCandidate.name?.charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <p className="font-medium text-slate-900">{applicantCandidate.name}</p>
                    <p className="text-sm text-slate-500">{applicantCandidate.email}</p>
                  </div>
                </div>
              </div>

              {/* Job Selection */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  <Briefcase className="w-4 h-4" />
                  Select Job / Mandate *
                </Label>
                <Select value={selectedJobId} onValueChange={setSelectedJobId}>
                  <SelectTrigger data-testid="job-select-dropdown">
                    <SelectValue placeholder="Choose a job..." />
                  </SelectTrigger>
                  <SelectContent>
                    {jobs.length > 0 ? jobs.map(job => (
                      <SelectItem key={job.id} value={job.id}>
                        {job.title} {job.company_name ? `- ${job.company_name}` : ''}
                      </SelectItem>
                    )) : (
                      <div className="px-2 py-1.5 text-sm text-slate-500">No active jobs available</div>
                    )}
                  </SelectContent>
                </Select>
              </div>

              {/* Salary - Editable */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  <DollarSign className="w-4 h-4" />
                  Current Salary (INR) *
                </Label>
                <Input
                  type="number"
                  value={editSalary}
                  onChange={(e) => setEditSalary(e.target.value)}
                  placeholder="e.g., 1500000"
                  className={!editSalary ? 'border-amber-400' : ''}
                  data-testid="salary-input"
                />
                {editSalary && parseInt(editSalary) > 0 && (
                  <p className="text-xs text-slate-500">{formatSalaryINR(parseInt(editSalary))}</p>
                )}
              </div>

              {/* Notice Period - Editable */}
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  <Clock className="w-4 h-4" />
                  Notice Period *
                </Label>
                <Select value={editNotice} onValueChange={setEditNotice}>
                  <SelectTrigger 
                    className={!editNotice ? 'border-amber-400' : ''}
                    data-testid="notice-select"
                  >
                    <SelectValue placeholder="Select..." />
                  </SelectTrigger>
                  <SelectContent>
                    {NOTICE_PERIODS.map(np => (
                      <SelectItem key={np} value={np}>{np}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Warning if fields missing */}
              {(!editSalary || !editNotice || !editLocation || editExperience === '') && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-amber-500 flex-shrink-0" />
                  <p className="text-sm text-amber-700">
                    All fields (salary, notice period, location, experience) are mandatory before adding as applicant.
                  </p>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddApplicant(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAddAsApplicant}
              disabled={linking || !editSalary || !editNotice || !editLocation || editExperience === '' || !selectedJobId}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="confirm-add-applicant-btn"
            >
              {linking ? 'Adding...' : 'Add as Applicant'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
