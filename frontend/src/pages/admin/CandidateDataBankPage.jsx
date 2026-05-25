import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { candidateBankAPI, jobAPI, bulkImportAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import { Upload, Database, Users, Plus, Files, AlertTriangle, ShieldCheck } from 'lucide-react';
import { CVUploadDialog } from '../../components/dialogs/CVUploadDialog';
import { useCandidateBankFilters } from '../../hooks/useCandidateBankFilters';
import { CandidateBankFilters } from '../../components/candidate-bank/CandidateBankFilters';
import { DuplicateManager } from '../../components/candidate-bank/DuplicateManager';
import { FailedCapturesTab } from '../../components/candidate-bank/FailedCapturesTab';
import { useAuth } from '../../lib/auth';

// Extracted sub-components
import { CandidateListItem } from '../../components/candidates/CandidateListItem';
import { CandidateDetailDialog } from '../../components/candidates/CandidateDetailDialog';
import { AddApplicantDialog } from '../../components/candidates/AddApplicantDialog';
import { AttachCVDialog } from '../../components/candidates/AttachCVDialog';
import { DeleteCandidateDialog } from '../../components/candidates/DeleteCandidateDialog';

export default function CandidateDataBankPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const deepLinkHandledRef = useRef(false);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [showCVUpload, setShowCVUpload] = useState(false);
  const [auditLog, setAuditLog] = useState([]);
  const [resumeHistory, setResumeHistory] = useState([]);
  const [activityHistory, setActivityHistory] = useState(null);
  const [showDeleteCandidate, setShowDeleteCandidate] = useState(false);

  // Cursor-based pagination state
  const [totalCandidates, setTotalCandidates] = useState(0);
  const [nextCursor, setNextCursor] = useState(null);
  const [pageSize] = useState(50);

  // Shared filter hook (with URL persistence)
  const filterHook = useCandidateBankFilters();
  const { currentPage, setCurrentPage, getApiParams, debouncedSearch, debouncedSkills } = filterHook;

  const [activeView, setActiveView] = useState('candidates');

  // Add as Applicant state
  const [showAddApplicant, setShowAddApplicant] = useState(false);
  const [applicantCandidate, setApplicantCandidate] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [editSalary, setEditSalary] = useState('');
  const [editNotice, setEditNotice] = useState('');
  const [editLocation, setEditLocation] = useState('');
  const [editExperience, setEditExperience] = useState('');
  const [linking, setLinking] = useState(false);

  // Attach CV state
  const [showAttachCV, setShowAttachCV] = useState(false);
  const [attachCVCandidate, setAttachCVCandidate] = useState(null);
  const [attachingCV, setAttachingCV] = useState(false);

  // Inline editing state
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [editProfileForm, setEditProfileForm] = useState({
    name: '', phone: '', location: '', experience_years: '', current_salary: '',
    notice_period: '', current_employer: '', designation: '', industry: '',
  });

  // Reset and fresh-load when filters change
  useEffect(() => {
    setCandidates([]);
    setNextCursor(null);
    loadCandidates({ fresh: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, debouncedSkills]);

  const loadCandidates = async ({ fresh = false, cursor = null } = {}) => {
    if (fresh) setLoading(true); else setLoadingMore(true);
    try {
      const params = getApiParams(1);
      if (cursor) { params.cursor = cursor; delete params.page; }
      const res = await candidateBankAPI.getAll(params);
      if (res.data.candidates) {
        setCandidates(prev => fresh ? res.data.candidates : [...prev, ...res.data.candidates]);
        setTotalCandidates(res.data.total);
        setNextCursor(res.data.next_cursor || null);
      } else {
        setCandidates(res.data);
        setTotalCandidates(res.data.length);
        setNextCursor(null);
      }
    } catch {
      toast.error('Failed to load candidates');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  const handleLoadMore = () => {
    if (nextCursor && !loadingMore) loadCandidates({ cursor: nextCursor });
  };

  // ─── Detail loading ───
  const loadCandidateDetails = async (candidate) => {
    setSelectedCandidate(candidate);
    try {
      const [fullRes, ...detailResults] = await Promise.all([
        candidateBankAPI.getById(candidate.id),
        candidateBankAPI.getAuditLog(candidate.id),
        candidateBankAPI.getResumeHistory(candidate.id),
        candidateBankAPI.getHistory(candidate.id),
      ]);
      if (fullRes.data) setSelectedCandidate(fullRes.data);
      const extract = (r) => r.status !== undefined ? (r.status === 'fulfilled' ? r.value.data : []) : (r.data || []);
      setAuditLog(extract(detailResults[0]));
      setResumeHistory(extract(detailResults[1]));
      setActivityHistory(extract(detailResults[2]));
    } catch {
      setAuditLog([]); setResumeHistory([]); setActivityHistory([]);
    }
  };

  // ─── Deep-link: open candidate from ?candidateId= URL param ───
  useEffect(() => {
    const cid = searchParams.get('candidateId');
    if (!cid || deepLinkHandledRef.current) return;
    deepLinkHandledRef.current = true;
    (async () => {
      try {
        const r = await candidateBankAPI.getById(cid);
        if (r?.data) {
          await loadCandidateDetails(r.data);
          // Strip query param so reloads don't re-trigger
          const next = new URLSearchParams(searchParams);
          next.delete('candidateId');
          setSearchParams(next, { replace: true });
        } else {
          toast.error('Candidate not found');
        }
      } catch {
        toast.error('Failed to open candidate');
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // ─── Profile editing ───
  const startEditingProfile = () => {
    if (!selectedCandidate) return;
    setEditProfileForm({
      name: selectedCandidate.name || '',
      phone: selectedCandidate.phone || '',
      location: selectedCandidate.location || '',
      experience_years: selectedCandidate.experience_years?.toString() || '0',
      current_salary: selectedCandidate.current_salary?.toString() || '',
      notice_period: selectedCandidate.notice_period || '',
      current_employer: selectedCandidate.current_employer || '',
      designation: selectedCandidate.designation || selectedCandidate.headline || '',
      industry: selectedCandidate.industry || '',
    });
    setIsEditingProfile(true);
  };

  const cancelEditingProfile = () => {
    setIsEditingProfile(false);
    setEditProfileForm({ name: '', phone: '', location: '', experience_years: '', current_salary: '', notice_period: '', current_employer: '', designation: '', industry: '' });
  };

  const saveProfileChanges = async () => {
    if (!selectedCandidate) return;
    setSavingProfile(true);
    try {
      await candidateBankAPI.updateSalaryNotice(
        selectedCandidate.id,
        editProfileForm.current_salary ? parseInt(editProfileForm.current_salary) : null,
        editProfileForm.notice_period,
        editProfileForm.location,
        editProfileForm.experience_years ? parseInt(editProfileForm.experience_years) : 0,
      );
      await candidateBankAPI.update(selectedCandidate.id, {
        name: editProfileForm.name, phone: editProfileForm.phone,
        headline: editProfileForm.designation, current_employer: editProfileForm.current_employer,
        designation: editProfileForm.designation, industry: editProfileForm.industry,
      });
      toast.success('Profile updated successfully');
      setIsEditingProfile(false);
      loadCandidates({ fresh: true });
      setSelectedCandidate(prev => ({
        ...prev, ...editProfileForm,
        experience_years: parseInt(editProfileForm.experience_years) || 0,
        current_salary: parseInt(editProfileForm.current_salary) || null,
      }));
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update profile');
    } finally {
      setSavingProfile(false);
    }
  };

  // ─── Delete ───
  const handleDeleteCandidate = async () => {
    if (!selectedCandidate) return;
    try {
      await candidateBankAPI.delete(selectedCandidate.id);
      toast.success('Candidate deleted successfully');
      setShowDeleteCandidate(false);
      setSelectedCandidate(null);
      loadCandidates({ fresh: true });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete candidate');
    }
  };

  // ─── Resume download ───
  const downloadResume = (candidate) => {
    if (!candidate.resume_url) { toast.error('No resume available'); return; }
    const token = localStorage.getItem('vhc_token');
    const url = candidateBankAPI.getResumeDownloadUrl(candidate.id);
    const link = document.createElement('a');
    link.href = `${url}?token=${token}`;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // ─── Add as Applicant ───
  const openAddApplicantDialog = async (candidate) => {
    setApplicantCandidate(candidate);
    setEditSalary(candidate.current_salary?.toString() || '');
    setEditNotice(candidate.notice_period || '');
    setEditLocation(candidate.location || '');
    setEditExperience(candidate.experience_years?.toString() || '0');
    setSelectedJobId('');
    try { const res = await jobAPI.getAll(); setJobs(res.data.filter(j => j.status === 'active')); } catch { /* ignore */ }
    setShowAddApplicant(true);
  };

  const handleAddAsApplicant = async () => {
    const salaryNum = parseInt(editSalary);
    const expNum = parseInt(editExperience);
    if (!editSalary || salaryNum <= 0) { toast.error('Current salary (INR) is mandatory'); return; }
    if (!editNotice) { toast.error('Notice period is mandatory'); return; }
    if (!editLocation?.trim()) { toast.error('Location is mandatory'); return; }
    if (editExperience === '' || isNaN(expNum) || expNum < 0) { toast.error('Experience (years) is mandatory'); return; }
    if (!selectedJobId) { toast.error('Please select a job'); return; }

    setLinking(true);
    try {
      const needsUpdate = salaryNum !== applicantCandidate.current_salary || editNotice !== applicantCandidate.notice_period || editLocation !== applicantCandidate.location || expNum !== applicantCandidate.experience_years;
      if (needsUpdate) await candidateBankAPI.updateSalaryNotice(applicantCandidate.id, salaryNum, editNotice, editLocation.trim(), expNum);
      const res = await candidateBankAPI.linkToJob(applicantCandidate.id, selectedJobId);
      toast.success(res.data.message);
      setShowAddApplicant(false);
      loadCandidates({ fresh: true });
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (typeof detail === 'object' && detail.message) {
        toast.error(detail.message);
        detail.errors?.forEach(err => toast.error(err));
      } else {
        toast.error(typeof detail === 'string' ? detail : 'Failed to add as applicant');
      }
    } finally {
      setLinking(false);
    }
  };

  // ─── Attach CV ───
  const openAttachCVDialog = (candidate) => { setAttachCVCandidate(candidate); setShowAttachCV(true); };

  const handleAttachCV = async (file) => {
    if (!file || !attachCVCandidate) return;
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'doc', 'docx'].includes(ext)) { toast.error('Please upload a PDF, DOC, or DOCX file'); return; }
    setAttachingCV(true);
    try {
      const res = await bulkImportAPI.attachCV(attachCVCandidate.id, file);
      toast.success(res.data.message || 'CV attached successfully');
      setShowAttachCV(false);
      setAttachCVCandidate(null);
      loadCandidates({ fresh: true });
      if (selectedCandidate?.id === attachCVCandidate.id) loadCandidateDetails({ ...selectedCandidate, cv_attached: true });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to attach CV');
    } finally {
      setAttachingCV(false);
    }
  };

  // ─── Render ───
  return (
    <div className="space-y-6" data-testid="candidate-bank-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Candidate Data Bank</h1>
          <p className="text-slate-500 mt-1">Centralized candidate database with deduplication</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => navigate('data-quality')} data-testid="data-quality-btn" className="text-xs sm:text-sm">
            <ShieldCheck className="w-4 h-4 mr-1 sm:mr-2" /> Data Quality
          </Button>
          <Button variant="outline" onClick={() => navigate('batch-upload')} data-testid="batch-upload-btn" className="text-xs sm:text-sm">
            <Files className="w-4 h-4 mr-1 sm:mr-2" /> Batch Upload
          </Button>
          <Button onClick={() => setShowCVUpload(true)} className="bg-[#7CB342] hover:bg-[#689F38] text-xs sm:text-sm" data-testid="add-candidate-btn">
            <Plus className="w-4 h-4 mr-1 sm:mr-2" /> Add Candidate
          </Button>
        </div>
      </div>

      {/* View Toggle */}
      <div className="flex gap-1 bg-slate-100 rounded-lg p-0.5 w-fit" data-testid="view-tabs">
        {[
          { key: 'candidates', icon: Database, label: 'Candidates' },
          { key: 'duplicates', icon: Users, label: 'Duplicates' },
          { key: 'failed_captures', icon: AlertTriangle, label: 'Failed Captures' },
        ].map(({ key, icon: Icon, label }) => (
          <button
            key={key}
            onClick={() => setActiveView(key)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${activeView === key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            data-testid={`view-tab-${key}`}
          >
            <Icon className="w-3.5 h-3.5 inline mr-1.5" /> {label}
          </button>
        ))}
      </div>

      {activeView === 'failed_captures' ? <FailedCapturesTab /> :
       activeView === 'duplicates' ? <DuplicateManager /> : (
        <>
          {/* Search & Filters */}
          <Card className="border-slate-200" data-testid="search-filters-card">
            <CandidateBankFilters {...filterHook} isAdmin={user?.role === 'admin'} onSearch={() => { setCandidates([]); setNextCursor(null); loadCandidates({ fresh: true }); }} />
          </Card>

          {/* Candidates List */}
          <Card className="border-slate-200">
            <CardHeader className="border-b border-slate-100 bg-slate-50/50">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="font-heading text-lg flex items-center gap-2">
                  <Database className="w-5 h-5 text-[#7CB342]" /> Candidates ({totalCandidates})
                </CardTitle>
                <div className="text-sm text-slate-500">Showing {candidates.length} of {totalCandidates}</div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {loading ? (
                <div className="flex items-center justify-center py-12"><div className="spinner" /></div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {candidates.map((c) => (
                    <CandidateListItem
                      key={c.id} candidate={c} navigate={navigate}
                      onSelect={loadCandidateDetails}
                      onAddApplicant={openAddApplicantDialog}
                      onAttachCV={openAttachCVDialog}
                      onDownloadResume={downloadResume}
                      isAdmin={user?.role === 'admin'}
                    />
                  ))}
                  {candidates.length === 0 && (
                    <div className="text-center py-12">
                      <Database className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                      <p className="text-slate-500 mb-2">No candidates in data bank</p>
                      <p className="text-sm text-slate-400 mb-4">Add candidates by uploading resumes or wait for job applications</p>
                      <Button onClick={() => setShowCVUpload(true)} className="bg-[#7CB342] hover:bg-[#689F38]">
                        <Upload className="w-4 h-4 mr-2" /> Upload First Resume
                      </Button>
                    </div>
                  )}
                </div>
              )}
              {!loading && nextCursor && (
                <div className="border-t border-slate-100 px-4 py-4 flex flex-col items-center gap-2 bg-slate-50/50">
                  <Button
                    variant="outline"
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="w-full sm:w-auto border-[#7CB342] text-[#7CB342] hover:bg-green-50"
                    data-testid="load-more-btn"
                  >
                    {loadingMore ? 'Loading...' : `Load More (${candidates.length} of ${totalCandidates})`}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Dialogs */}
          <CandidateDetailDialog
            candidate={selectedCandidate}
            onClose={() => setSelectedCandidate(null)}
            auditLog={auditLog} resumeHistory={resumeHistory} activityHistory={activityHistory}
            isEditing={isEditingProfile} editForm={editProfileForm}
            onEditFormChange={setEditProfileForm}
            onStartEdit={startEditingProfile} onCancelEdit={cancelEditingProfile}
            onSaveProfile={saveProfileChanges} savingProfile={savingProfile}
            onDownloadResume={downloadResume}
            onAttachCV={openAttachCVDialog}
            onDelete={() => setShowDeleteCandidate(true)}
            user={user}
          />

          <AddApplicantDialog
            open={showAddApplicant} onOpenChange={setShowAddApplicant}
            candidate={applicantCandidate} jobs={jobs}
            selectedJobId={selectedJobId} setSelectedJobId={setSelectedJobId}
            editSalary={editSalary} setEditSalary={setEditSalary}
            editNotice={editNotice} setEditNotice={setEditNotice}
            editLocation={editLocation} setEditLocation={setEditLocation}
            editExperience={editExperience} setEditExperience={setEditExperience}
            linking={linking} onConfirm={handleAddAsApplicant}
          />

          <AttachCVDialog
            open={showAttachCV} onOpenChange={setShowAttachCV}
            candidate={attachCVCandidate}
            onAttachCV={handleAttachCV} attaching={attachingCV}
          />

          <CVUploadDialog open={showCVUpload} onOpenChange={setShowCVUpload} onProfileSaved={() => loadCandidates({ fresh: true })} />

          <DeleteCandidateDialog
            open={showDeleteCandidate} onOpenChange={setShowDeleteCandidate}
            candidate={selectedCandidate} onConfirm={handleDeleteCandidate}
          />
        </>
      )}
    </div>
  );
}
