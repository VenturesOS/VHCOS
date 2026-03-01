import { useState, useEffect, useRef, useCallback } from 'react';
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
import { Search, Upload, Database, Mail, Phone, MapPin, FileText, Clock, Briefcase, DollarSign, AlertCircle, CalendarDays, Activity, TrendingUp, Download, Info, Filter, X, ChevronDown, ChevronUp, EyeOff, Building2, Code, Calendar } from 'lucide-react';
import { CVUploadDialog } from '../../components/dialogs/CVUploadDialog';

const NOTICE_PERIODS = [
  "Immediate",
  "15 days",
  "30 days",
  "45 days",
  "60 days",
  "90 days",
  "90+ days"
];

export default function RecruiterCandidateBankPage() {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [skills, setSkills] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showCVUpload, setShowCVUpload] = useState(false);
  const [resumeHistory, setResumeHistory] = useState([]);
  const [activityHistory, setActivityHistory] = useState(null);
  const fileInputRef = useRef(null);
  const [uploadForm, setUploadForm] = useState({ email: '', name: '' });
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Filters state
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState({
    phone: '',
    email: '',
    location: '',
    company: '',
    noticePeriod: '',
    minExperience: '',
    maxExperience: '',
    minSalary: '',
    maxSalary: '',
    source: '',
    hasResume: '',
    contactHidden: '',
    capturedAfter: '',
    capturedBefore: '',
  });

  const activeFilterCount = Object.values(filters).filter(v => v !== '').length + (skills ? 1 : 0);
  
  // Add as Applicant state
  const [showAddApplicant, setShowAddApplicant] = useState(false);
  const [applicantCandidate, setApplicantCandidate] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [editSalary, setEditSalary] = useState('');
  const [editNotice, setEditNotice] = useState('');
  const [editLocation, setEditLocation] = useState('');
  const [editExperience, setEditExperience] = useState('');
  const [expectedCTC, setExpectedCTC] = useState('');
  const [expectedCTCType, setExpectedCTCType] = useState('amount'); // 'amount' or 'percentage'
  const [linking, setLinking] = useState(false);

  useEffect(() => {
    loadCandidates();
  }, []);

  const loadJobs = async () => {
    try {
      const res = await jobAPI.getAll();
      setJobs(res.data.filter(j => j.status === 'active'));
    } catch (error) {
      console.error('Failed to load jobs');
    }
  };

  const openAddApplicantDialog = (candidate) => {
    setApplicantCandidate(candidate);
    setEditSalary(candidate.current_salary?.toString() || '');
    setEditNotice(candidate.notice_period || '');
    setEditLocation(candidate.location || '');
    setEditExperience(candidate.experience_years?.toString() || '0');
    setExpectedCTC('');
    setExpectedCTCType('amount');
    setSelectedJobId('');
    loadJobs();
    setShowAddApplicant(true);
  };

  // Calculate expected CTC based on type
  const calculateExpectedCTC = () => {
    if (!expectedCTC) return null;
    const currentSalary = parseInt(editSalary) || 0;
    if (expectedCTCType === 'percentage') {
      const hikePercent = parseFloat(expectedCTC);
      return Math.round(currentSalary * (1 + hikePercent / 100));
    }
    return parseInt(expectedCTC);
  };

  const handleAddAsApplicant = async () => {
    const salaryNum = parseInt(editSalary);
    const expNum = parseInt(editExperience);
    const expectedSalary = calculateExpectedCTC();
    
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

      const res = await candidateBankAPI.linkToJob(applicantCandidate.id, selectedJobId, expectedSalary);
      toast.success(res.data.message);
      setShowAddApplicant(false);
      loadCandidates();
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (typeof detail === 'object' && detail.message) {
        toast.error(detail.message);
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

  const downloadResume = (candidate) => {
    if (!candidate.resume_url) {
      toast.error('No resume available for this candidate');
      return;
    }
    const token = localStorage.getItem('vhc_token');
    const downloadUrl = candidateBankAPI.getResumeDownloadUrl(candidate.id);
    const link = document.createElement('a');
    link.href = `${downloadUrl}?token=${token}`;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const loadCandidates = async (page = 1) => {
    setLoading(true);
    try {
      const params = { page, limit: 20 };
      if (search) params.search = search;
      if (skills) params.skills = skills;
      if (filters.phone) params.phone = filters.phone;
      if (filters.email) params.email = filters.email;
      if (filters.location) params.location = filters.location;
      if (filters.company) params.company = filters.company;
      if (filters.noticePeriod) params.notice_period = filters.noticePeriod;
      if (filters.minExperience !== '') params.min_experience = parseInt(filters.minExperience);
      if (filters.maxExperience !== '') params.max_experience = parseInt(filters.maxExperience);
      if (filters.minSalary !== '') params.min_salary = parseInt(filters.minSalary);
      if (filters.maxSalary !== '') params.max_salary = parseInt(filters.maxSalary);
      if (filters.source) params.source = filters.source;
      if (filters.hasResume) params.has_resume = filters.hasResume;
      if (filters.contactHidden) params.contact_hidden = filters.contactHidden;
      if (filters.capturedAfter) params.captured_after = filters.capturedAfter;
      if (filters.capturedBefore) params.captured_before = filters.capturedBefore;

      const res = await candidateBankAPI.getAll(params);
      const data = res.data;
      if (data && Array.isArray(data.candidates)) {
        setCandidates(data.candidates);
        setTotalCount(data.total || data.candidates.length);
        setTotalPages(data.pages || 1);
        setCurrentPage(data.page || 1);
      } else if (Array.isArray(data)) {
        setCandidates(data);
        setTotalCount(data.length);
      } else {
        setCandidates([]);
        setTotalCount(0);
      }
    } catch (error) {
      toast.error('Failed to load candidates');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    loadCandidates(1);
  };

  const clearFilters = () => {
    setFilters({
      phone: '', email: '', location: '', company: '', noticePeriod: '',
      minExperience: '', maxExperience: '', minSalary: '', maxSalary: '',
      source: '', hasResume: '', contactHidden: '', capturedAfter: '', capturedBefore: '',
    });
    setSkills('');
    setSearch('');
  };

  const updateFilter = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  // Quick date helper
  const setDatePreset = (preset) => {
    const now = new Date();
    let after = '';
    if (preset === 'today') {
      after = now.toISOString().split('T')[0];
    } else if (preset === 'week') {
      const d = new Date(now); d.setDate(d.getDate() - 7);
      after = d.toISOString().split('T')[0];
    } else if (preset === 'month') {
      const d = new Date(now); d.setMonth(d.getMonth() - 1);
      after = d.toISOString().split('T')[0];
    }
    setFilters(prev => ({ ...prev, capturedAfter: after, capturedBefore: '' }));
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setUploading(true);
    try {
      const res = await candidateBankAPI.add(file, uploadForm.email, uploadForm.name);
      toast.success(`Candidate ${res.data.action}: ${res.data.candidate_id}`);
      setShowUpload(false);
      setUploadForm({ email: '', name: '' });
      loadCandidates();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to upload resume');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const loadCandidateDetails = async (candidate) => {
    setSelectedCandidate(candidate);
    try {
      const results = await Promise.allSettled([
        candidateBankAPI.getResumeHistory(candidate.id),
        candidateBankAPI.getHistory(candidate.id),
      ]);
      setResumeHistory(results[0].status === 'fulfilled' ? (results[0].value.data?.resume_versions || []) : []);
      setActivityHistory(results[1].status === 'fulfilled' ? results[1].value.data : []);
    } catch (error) {
      console.error('Failed to load details');
      setResumeHistory([]);
      setActivityHistory([]);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-heading font-bold text-slate-900">Candidate Data Bank</h1>
          <p className="text-sm text-slate-500 mt-1">
            Candidates parsed and applicants to your mandates
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button 
            variant="outline"
            size="sm"
            onClick={() => setShowCVUpload(true)}
            data-testid="cv-upload-btn"
          >
            <Upload className="w-4 h-4 mr-1 sm:mr-2" /> Upload CV
          </Button>
          <Button 
            size="sm"
            onClick={() => setShowUpload(true)}
            className="bg-[#7CB342] hover:bg-[#689F38]"
            data-testid="upload-resume-btn"
          >
            <Upload className="w-4 h-4 mr-1 sm:mr-2" /> Add
          </Button>
        </div>
      </div>

      {/* Access Control Info */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-start gap-3">
        <Info className="w-5 h-5 text-blue-600 mt-0.5" />
        <div className="text-sm text-blue-800">
          <p className="font-medium">Access Control:</p>
          <p>You can only see candidates that you have parsed or candidates who have applied to jobs under your assigned mandates.</p>
        </div>
      </div>

      {/* Search */}
      <Card className="border-slate-200">
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
            <div className="flex-1">
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name or email"
                className="pl-10"
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <div className="flex-1">
              <Input
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
                placeholder="Filter by skills (comma separated)"
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <Button onClick={handleSearch} variant="outline" className="w-full sm:w-auto">
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
                  className="p-3 sm:p-4 hover:bg-slate-50 transition-colors cursor-pointer"
                  onClick={() => loadCandidateDetails(candidate)}
                  data-testid={`candidate-row-${candidate.id}`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                    <div className="flex items-center gap-3 sm:gap-4 min-w-0 flex-1">
                      <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                        <span className="text-[#7CB342] font-semibold text-sm sm:text-base">
                          {candidate.name?.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900 truncate">{candidate.name}</p>
                        <p className="text-sm text-slate-500 truncate">{candidate.headline || candidate.email}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap ml-13 sm:ml-0">
                      <div className="hidden lg:flex flex-wrap gap-1 max-w-xs">
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
                      {candidate.resume_url && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            downloadResume(candidate);
                          }}
                          className="text-slate-600 hover:text-[#7CB342] p-1 sm:p-2"
                          title="Download Resume"
                        >
                          <Download className="w-4 h-4" />
                        </Button>
                      )}
                      {candidate.source === 'naukri_extension' && (
                        <>
                          <span className="px-2 py-1 text-xs rounded-full font-medium bg-orange-50 text-orange-600">Naukri</span>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`../naukri-profile/${candidate.id}`);
                            }}
                            className="text-orange-600 border-orange-300 hover:bg-orange-50 hidden sm:inline-flex"
                            data-testid={`view-naukri-profile-${candidate.id}`}
                          >
                            <FileText className="w-4 h-4 sm:mr-1" /> <span className="hidden md:inline">Full Profile</span>
                          </Button>
                        </>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          openAddApplicantDialog(candidate);
                        }}
                        className="text-[#7CB342] border-[#7CB342] hover:bg-green-50 text-xs sm:text-sm"
                      >
                        <Briefcase className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Add</span>
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
              {candidates.length === 0 && (
                <div className="text-center py-12">
                  <Database className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                  <p className="text-slate-500 mb-2">No candidates available</p>
                  <p className="text-sm text-slate-400 mb-4">Upload resumes to start building your candidate pool</p>
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
            <DialogDescription>
              Upload a resume to parse and add a new candidate to your data bank.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Resume File (PDF, DOC, DOCX)</Label>
              <Input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.doc,.docx"
                onChange={handleUpload}
                disabled={uploading}
              />
            </div>
            <div className="space-y-2">
              <Label>Email (optional)</Label>
              <Input
                value={uploadForm.email}
                onChange={(e) => setUploadForm({ ...uploadForm, email: e.target.value })}
                placeholder="Override email if not parseable"
              />
            </div>
            <div className="space-y-2">
              <Label>Name (optional)</Label>
              <Input
                value={uploadForm.name}
                onChange={(e) => setUploadForm({ ...uploadForm, name: e.target.value })}
                placeholder="Override name if not parseable"
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
                <TabsTrigger value="activity">
                  <Activity className="w-4 h-4 mr-1" /> Activity History
                </TabsTrigger>
                <TabsTrigger value="resumes">Resumes</TabsTrigger>
              </TabsList>

              <TabsContent value="profile">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
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
                    {selectedCandidate.resume_url && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => downloadResume(selectedCandidate)}
                        className="text-[#7CB342] border-[#7CB342] hover:bg-green-50"
                      >
                        <Download className="w-4 h-4 mr-2" /> Download Resume
                      </Button>
                    )}
                  </div>

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
                </div>
              </TabsContent>

              <TabsContent value="activity">
                <div className="space-y-4">
                  {activityHistory?.summary && (
                    <div className="grid grid-cols-3 gap-3">
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

                  {activityHistory?.freshness && (
                    <div className="bg-slate-50 rounded-lg p-3 text-sm space-y-1">
                      <p className="font-medium text-slate-700 mb-2">Profile Freshness</p>
                      <div className="flex items-center gap-2 text-slate-600">
                        <CalendarDays className="w-4 h-4" />
                        Created: {activityHistory.freshness.profile_created_at ? new Date(activityHistory.freshness.profile_created_at).toLocaleDateString() : 'N/A'}
                      </div>
                      <div className="flex items-center gap-2 text-slate-600">
                        <TrendingUp className="w-4 h-4" />
                        Last Update: {activityHistory.freshness.last_profile_updated_at ? new Date(activityHistory.freshness.last_profile_updated_at).toLocaleDateString() : 'Never'}
                      </div>
                    </div>
                  )}

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
                              'bg-slate-100 text-slate-600'
                            }`}>
                              {app.stage}
                            </span>
                          </div>
                          <p className="text-slate-500">{app.company_name}</p>
                          <div className="flex items-center gap-4 mt-1 text-xs text-slate-400">
                            <span>Applied: {new Date(app.applied_at).toLocaleDateString()}</span>
                          </div>
                        </div>
                      ))}
                      {(!activityHistory?.applications || activityHistory.applications.length === 0) && (
                        <p className="text-slate-400 text-sm">No application history</p>
                      )}
                    </div>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="resumes">
                <div className="space-y-3">
                  {resumeHistory?.map((resume, idx) => (
                    <div key={idx} className="p-3 bg-slate-50 rounded-lg flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <FileText className="w-5 h-5 text-slate-400" />
                        <div>
                          <p className="font-medium text-sm">{resume.filename}</p>
                          <p className="text-xs text-slate-500">
                            Uploaded: {new Date(resume.uploaded_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      {resume.is_active && (
                        <span className="px-2 py-1 bg-green-100 text-green-600 text-xs rounded-full">Active</span>
                      )}
                    </div>
                  ))}
                  {(!resumeHistory || resumeHistory.length === 0) && (
                    <p className="text-slate-400 text-sm">No resume history</p>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>

      {/* Add as Applicant Dialog */}
      <Dialog open={showAddApplicant} onOpenChange={setShowAddApplicant}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Add as Applicant</DialogTitle>
            <DialogDescription>
              Link this candidate to a job from your assigned mandates.
            </DialogDescription>
          </DialogHeader>
          {applicantCandidate && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                  <span className="text-[#7CB342] font-semibold">
                    {applicantCandidate.name?.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <p className="font-medium">{applicantCandidate.name}</p>
                  <p className="text-sm text-slate-500">{applicantCandidate.email}</p>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Select Job/Mandate *</Label>
                <Select value={selectedJobId} onValueChange={setSelectedJobId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a job..." />
                  </SelectTrigger>
                  <SelectContent>
                    {jobs.map(job => (
                      <SelectItem key={job.id} value={job.id}>
                        {job.title} - {job.company_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Current Salary (INR) *</Label>
                <Input
                  type="number"
                  value={editSalary}
                  onChange={(e) => setEditSalary(e.target.value)}
                  placeholder="e.g., 1500000"
                  className={!editSalary ? 'border-amber-400' : ''}
                />
              </div>

              <div className="space-y-2">
                <Label>Notice Period *</Label>
                <Select value={editNotice} onValueChange={setEditNotice}>
                  <SelectTrigger className={!editNotice ? 'border-amber-400' : ''}>
                    <SelectValue placeholder="Select..." />
                  </SelectTrigger>
                  <SelectContent>
                    {NOTICE_PERIODS.map(np => (
                      <SelectItem key={np} value={np}>{np}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Location *</Label>
                <Input
                  type="text"
                  value={editLocation}
                  onChange={(e) => setEditLocation(e.target.value)}
                  placeholder="e.g., Mumbai, Delhi"
                  className={!editLocation ? 'border-amber-400' : ''}
                />
              </div>

              <div className="space-y-2">
                <Label>Experience (years) *</Label>
                <Input
                  type="number"
                  min="0"
                  value={editExperience}
                  onChange={(e) => setEditExperience(e.target.value)}
                  placeholder="e.g., 5"
                  className={editExperience === '' ? 'border-amber-400' : ''}
                />
              </div>

              {/* Expected CTC Section */}
              <div className="space-y-2 p-4 bg-green-50 rounded-lg border border-green-200">
                <Label className="flex items-center gap-2 text-green-700">
                  <TrendingUp className="w-4 h-4" />
                  Expected CTC
                </Label>
                <div className="flex gap-2">
                  <Select value={expectedCTCType} onValueChange={setExpectedCTCType}>
                    <SelectTrigger className="w-[140px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="amount">Amount (₹)</SelectItem>
                      <SelectItem value="percentage">Hike (%)</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input
                    type="number"
                    min="0"
                    value={expectedCTC}
                    onChange={(e) => setExpectedCTC(e.target.value)}
                    placeholder={expectedCTCType === 'amount' ? 'e.g., 1500000' : 'e.g., 30'}
                    className="flex-1"
                  />
                </div>
                {expectedCTC && editSalary && (
                  <p className="text-sm text-green-700">
                    Expected: <strong>{formatSalaryINR(calculateExpectedCTC())}</strong>
                    {expectedCTCType === 'percentage' && (
                      <span className="ml-2 text-green-600">
                        ({expectedCTC}% hike from {formatSalaryINR(parseInt(editSalary))})
                      </span>
                    )}
                  </p>
                )}
              </div>

              {(!editSalary || !editNotice || !editLocation || editExperience === '') && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-amber-500 flex-shrink-0" />
                  <p className="text-sm text-amber-700">
                    All fields are mandatory before adding as applicant.
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
            >
              {linking ? 'Adding...' : 'Add as Applicant'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CVUploadDialog 
        open={showCVUpload} 
        onOpenChange={setShowCVUpload} 
        onProfileSaved={loadCandidates} 
      />
    </div>
  );
}
