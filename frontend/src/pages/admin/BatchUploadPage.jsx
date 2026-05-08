import { useState, useRef, useEffect, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import { candidateBankAPI, cvUploadAPI, jobAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { DuplicateWarningDialog, LinkToJobDialog } from '../../components/admin/batch-upload/BatchUploadDialogs';
import CandidateCard from '../../components/admin/batch-upload/CandidateCard';
import { toast } from 'sonner';
import { 
  Upload, FileText, User, Mail, Phone, AlertTriangle, Check, X, 
  DollarSign, Clock, Briefcase, Plus, Trash2, ArrowLeft, Save, Loader2, Link2,
  History, FileSpreadsheet,
} from 'lucide-react';
import { useBatchUpload } from '../../contexts/BatchUploadContext';

// Naukri Excel import — lazy-loaded so the CV-upload tab stays light
const BulkImportContent = lazy(() => import('./BulkImportPage'));
const ImportHistoryContent = lazy(() => import('./ImportHistoryPage'));
const TabLoader = () => (
  <div className="flex items-center justify-center h-32">
    <Loader2 className="w-6 h-6 animate-spin text-[#7CB342]" />
  </div>
);

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

export default function BatchUploadPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const { tasks: bgTasks, isActive: bgActive, stats: bgStats, startBatch } = useBatchUpload();
  
  // State
  const [files, setFiles] = useState([]);
  const [parsedCandidates, setParsedCandidates] = useState([]);
  const [saving, setSaving] = useState(false);
  const [jobs, setJobs] = useState([]);
  
  // Duplicate handling dialog
  const [duplicateDialog, setDuplicateDialog] = useState(null);
  
  // Link to job dialog
  const [linkDialog, setLinkDialog] = useState(null);
  const [selectedJob, setSelectedJob] = useState('');
  const [batchMandateId, setBatchMandateId] = useState('');

  // Sync completed background tasks into parsedCandidates
  useEffect(() => {
    if (!bgActive && bgTasks.length > 0) {
      const allDone = bgTasks.every(t => t.status === 'completed' || t.status === 'failed');
      if (allDone && parsedCandidates.length === 0) {
        const results = bgTasks.map(task => {
          if (task.status === 'completed' && task.result) {
            const pd = task.result.profile_data || {};
            return {
              temp_id: task.id,
              filename: task.filename,
              status: 'parsed',
              success: true,
              error: null,
              parsed_data: {
                name: pd.name || '', email: pd.email || pd.personal_email || '',
                phone: pd.phone || pd.mobile || '', skills: pd.key_skills || [],
                experience_summary: pd.profile_summary || pd.headline || '',
                experience_years: pd.total_experience_years, location: pd.location || '',
                current_company: pd.current_company || '', designation: pd.current_designation || '',
                work_experience: pd.work_experience || [], education: pd.education || [],
                headline: pd.headline || '',
              },
              duplicate_check: null,
              raw_parsed: pd,
              editing: {
                name: pd.name || '', email: pd.email || pd.personal_email || '',
                phone: pd.phone || pd.mobile || '', skills: pd.key_skills || [],
                experience_summary: pd.profile_summary || pd.headline || '',
                current_salary: '', notice_period: '', location: pd.location || '',
                experience_years: pd.total_experience_years?.toString() || '',
              },
              isValid: !!(pd.name),
              errors: [],
            };
          }
          return {
            temp_id: task.id, filename: task.filename, status: 'failed',
            success: false, error: task.error || 'Parse failed',
            parsed_data: null, duplicate_check: null,
            editing: { name: '', email: '', phone: '', skills: [], experience_summary: '', current_salary: '', notice_period: '', location: '', experience_years: '' },
            isValid: false, errors: ['Parse failed'],
          };
        });
        setParsedCandidates(results);
        loadJobs();
      }
    }
  }, [bgActive, bgTasks, parsedCandidates.length]);

  // Load jobs for linking
  const loadJobs = async () => {
    try {
      const res = await jobAPI.getAll();
      setJobs(res.data.filter(j => j.status === 'active'));
    } catch (error) {
    }
  };

  // Handle file selection
  const handleFileSelect = (e) => {
    const selectedFiles = Array.from(e.target.files);
    
    if (selectedFiles.length > 10) {
      toast.error('Maximum 10 files allowed per batch');
      return;
    }
    
    // Validate file types
    const validFiles = selectedFiles.filter(f => 
      f.name.toLowerCase().endsWith('.pdf') || 
      f.name.toLowerCase().endsWith('.doc') || 
      f.name.toLowerCase().endsWith('.docx')
    );
    
    if (validFiles.length !== selectedFiles.length) {
      toast.warning('Some files were skipped. Only PDF, DOC, DOCX allowed.');
    }
    
    setFiles(validFiles);
    setParsedCandidates([]);
  };

  // Parse state - tracks per-file progress (displayed from global context)
  const parseProgress = {
    current: bgStats.completed + bgStats.failed,
    total: bgStats.total || files.length,
    currentFile: bgTasks.find(t => t.status === 'parsing' || t.status === 'uploading')?.filename || '',
  };

  // Parse uploaded files — delegates to global BatchUploadContext
  const handleParse = async () => {
    if (files.length === 0) {
      toast.error('Please select files to upload');
      return;
    }
    
    setParsedCandidates([]);
    startBatch(files);
    toast.success(`Started parsing ${files.length} files in background. You can navigate away safely.`);
  };

  // Update candidate editing fields
  const updateCandidate = (tempId, field, value) => {
    setParsedCandidates(prev => prev.map(c => {
      if (c.temp_id !== tempId) return c;
      
      const newEditing = { ...c.editing, [field]: value };
      
      // Only name is required
      const errors = [];
      if (!newEditing.name?.trim()) errors.push('Name is required');
      
      return {
        ...c,
        editing: newEditing,
        isValid: errors.length === 0,
        errors
      };
    }));
  };

  // Add skill to candidate
  const addSkill = (tempId, skill) => {
    if (!skill.trim()) return;
    
    setParsedCandidates(prev => prev.map(c => {
      if (c.temp_id !== tempId) return c;
      if (c.editing.skills.includes(skill.trim())) return c;
      
      return {
        ...c,
        editing: {
          ...c.editing,
          skills: [...c.editing.skills, skill.trim()]
        }
      };
    }));
  };

  // Remove skill from candidate
  const removeSkill = (tempId, skill) => {
    setParsedCandidates(prev => prev.map(c => {
      if (c.temp_id !== tempId) return c;
      
      return {
        ...c,
        editing: {
          ...c.editing,
          skills: c.editing.skills.filter(s => s !== skill)
        }
      };
    }));
  };

  // Remove candidate from batch
  const removeCandidate = (tempId) => {
    setParsedCandidates(prev => prev.filter(c => c.temp_id !== tempId));
    toast.info('Candidate removed from batch');
  };

  // Handle duplicate action
  const handleDuplicateAction = (action) => {
    const { candidate, existingCandidate } = duplicateDialog;
    
    if (action === 'update') {
      // Mark this candidate to update the existing record
      setParsedCandidates(prev => prev.map(c => {
        if (c.temp_id !== candidate.temp_id) return c;
        return {
          ...c,
          duplicate_action: 'update',
          existing_candidate_id: existingCandidate.id
        };
      }));
      toast.info('Will update existing candidate');
    } else if (action === 'link') {
      // Open link to job dialog
      setLinkDialog({
        candidate: existingCandidate,
        fromDuplicate: true
      });
    }
    
    setDuplicateDialog(null);
  };

  // Link existing candidate to job
  const handleLinkToJob = async () => {
    if (!selectedJob || !linkDialog?.candidate) {
      toast.error('Please select a job');
      return;
    }
    
    try {
      await candidateBankAPI.linkToJob(linkDialog.candidate.id, selectedJob);
      toast.success(`Linked ${linkDialog.candidate.name} to job`);
      
      // Remove from batch if was a duplicate
      if (linkDialog.fromDuplicate) {
        setParsedCandidates(prev => prev.filter(c => 
          c.duplicate_check?.existing_candidate?.id !== linkDialog.candidate.id
        ));
      }
      
      setLinkDialog(null);
      setSelectedJob('');
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (typeof detail === 'object' && detail.message) {
        toast.error(detail.message);
      } else {
        toast.error('Failed to link candidate to job');
      }
    }
  };

  // Save all candidates (atomic)
  const handleSaveAll = async () => {
    // Validate all candidates
    const invalidCandidates = parsedCandidates.filter(c => c.success && !c.isValid);
    
    if (invalidCandidates.length > 0) {
      toast.error(`${invalidCandidates.length} candidates have missing required fields`);
      return;
    }
    
    const validCandidates = parsedCandidates.filter(c => c.success && c.isValid);
    
    if (validCandidates.length === 0) {
      toast.error('No valid candidates to save');
      return;
    }
    
    setSaving(true);
    
    try {
      const payload = validCandidates.map(c => ({
        temp_id: c.temp_id,
        name: c.editing.name,
        email: c.editing.email,
        phone: c.editing.phone,
        skills: c.editing.skills,
        experience_summary: c.editing.experience_summary,
        current_salary: c.editing.current_salary ? parseInt(c.editing.current_salary) : null,
        notice_period: c.editing.notice_period || null,
        location: c.editing.location || null,
        experience_years: c.editing.experience_years ? parseInt(c.editing.experience_years) : null,
        file_id: c.file_id,
        fingerprint: c.fingerprint
      }));
      
      const res = await candidateBankAPI.batchSave(payload, (batchMandateId && batchMandateId !== 'none') ? batchMandateId : null);
      
      const linkedCount = res.data.linked || 0;
      let msg = res.data.message || `Saved ${res.data.saved} candidates`;
      if (linkedCount > 0) {
        const linkedJob = jobs.find(j => j.id === batchMandateId);
        msg += `. Linked ${linkedCount} to ${linkedJob?.title || 'mandate'}`;
      }
      toast.success(msg);
      
      // Clear state and redirect
      setFiles([]);
      setParsedCandidates([]);
      setBatchMandateId('');
      navigate('/admin/candidate-bank');
      
    } catch (error) {
      const detail = error.response?.data?.detail;
      
      if (typeof detail === 'object') {
        toast.error(detail.message || 'Save failed');
        
        // Highlight validation errors
        if (detail.errors) {
          detail.errors.forEach(err => {
            setParsedCandidates(prev => prev.map(c => {
              if (c.temp_id !== err.temp_id) return c;
              return { ...c, errors: err.errors };
            }));
          });
        }
      } else {
        toast.error('Failed to save candidates');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="batch-upload-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate(-1)}>
            <ArrowLeft className="w-4 h-4 mr-2" /> Back
          </Button>
          <div>
            <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Batch Upload</h1>
            <p className="text-slate-500">Upload CVs in bulk or import a Naukri search result</p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="cv" className="w-full">
        <TabsList className="bg-slate-100 p-1">
          <TabsTrigger value="cv" data-testid="tab-cv-upload" className="text-xs sm:text-sm gap-1.5">
            <Upload className="w-3.5 h-3.5" /> CV Upload
          </TabsTrigger>
          <TabsTrigger value="naukri" data-testid="tab-naukri-excel" className="text-xs sm:text-sm gap-1.5">
            <FileSpreadsheet className="w-3.5 h-3.5" /> Naukri Excel
          </TabsTrigger>
          <TabsTrigger value="history" data-testid="tab-import-history" className="text-xs sm:text-sm gap-1.5">
            <History className="w-3.5 h-3.5" /> Import History
          </TabsTrigger>
        </TabsList>

        <TabsContent value="cv" className="mt-4 space-y-6">

      {/* Step 1: File Upload */}
      {parsedCandidates.length === 0 && (
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <Upload className="w-5 h-5 text-[#7CB342]" />
              Step 1: Select CVs
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div 
              className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-[#7CB342] transition-colors cursor-pointer"
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.doc,.docx"
                onChange={handleFileSelect}
                className="hidden"
                data-testid="batch-file-input"
              />
              <FileText className="w-12 h-12 mx-auto text-slate-400 mb-4" />
              <p className="text-slate-600 mb-2">
                Click to select files or drag and drop
              </p>
              <p className="text-sm text-slate-400">
                PDF, DOC, DOCX • Max 10 files
              </p>
            </div>
            
            {files.length > 0 && (
              <div className="mt-4">
                <p className="font-medium text-slate-700 mb-2">{files.length} file(s) selected:</p>
                <ul className="space-y-1">
                  {files.map((f, i) => (
                    <li key={i} className="text-sm text-slate-600 flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      {f.name}
                    </li>
                  ))}
                </ul>
                <Button 
                  onClick={handleParse}
                  disabled={bgActive}
                  className="mt-4 bg-[#7CB342] hover:bg-[#689F38]"
                  data-testid="parse-btn"
                >
                  {bgActive 
                    ? `Parsing ${parseProgress.current + 1}/${parseProgress.total}...` 
                    : 'Parse CVs'}
                </Button>
                {bgActive && parseProgress.currentFile && (
                  <div className="mt-2 space-y-1">
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div 
                        className="bg-[#7CB342] h-2 rounded-full transition-all duration-500"
                        style={{ width: `${((parseProgress.current) / parseProgress.total) * 100}%` }}
                      />
                    </div>
                    <p className="text-xs text-slate-500 truncate">
                      Processing: {parseProgress.currentFile}
                    </p>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Step 2: Preview & Edit */}
      {parsedCandidates.length > 0 && (
        <>
          <Card className="border-slate-200">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="font-heading flex items-center gap-2">
                <User className="w-5 h-5 text-[#7CB342]" />
                Step 2: Review & Edit ({parsedCandidates.filter(c => c.success).length} candidates)
              </CardTitle>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => {
                  setFiles([]);
                  setParsedCandidates([]);
                  setBatchMandateId('');
                }}>
                  Start Over
                </Button>
                <Button
                  onClick={handleSaveAll}
                  disabled={saving || parsedCandidates.filter(c => c.success && c.isValid).length === 0}
                  className="bg-[#7CB342] hover:bg-[#689F38]"
                  data-testid="save-all-btn"
                >
                  <Save className="w-4 h-4 mr-2" />
                  {saving ? 'Saving...' : `Save All (${parsedCandidates.filter(c => c.success && c.isValid).length})`}
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Info Notice */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-start gap-2">
                <AlertTriangle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-blue-800">
                  <strong>Only Name is required.</strong> Fill in as many fields as possible for better candidate matching. Salary, notice period, location, and experience are optional.
                </div>
              </div>

              {/* Link to Mandate (batch-level) */}
              <div className="border border-indigo-200 bg-indigo-50/50 rounded-lg p-4" data-testid="batch-mandate-link">
                <Label className="text-sm font-medium text-indigo-700 flex items-center gap-1.5 mb-2">
                  <Link2 className="w-3.5 h-3.5" /> Link to Mandate (Optional)
                </Label>
                <Select value={batchMandateId} onValueChange={setBatchMandateId}>
                  <SelectTrigger data-testid="batch-mandate-select" className="bg-white">
                    <SelectValue placeholder="Select a mandate to link..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No mandate</SelectItem>
                    {jobs.map(job => (
                      <SelectItem key={job.id} value={job.id}>
                        {job.title} — {job.company_name || 'Company'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-indigo-600 mt-1.5">
                  All candidates in this batch will be saved to Candidate Bank and also added as applicants to the selected mandate.
                </p>
              </div>

              {/* Candidate Cards */}
              {parsedCandidates.map((candidate) => (
                <CandidateCard
                  key={candidate.temp_id}
                  candidate={candidate}
                  onUpdate={(field, value) => updateCandidate(candidate.temp_id, field, value)}
                  onAddSkill={(skill) => addSkill(candidate.temp_id, skill)}
                  onRemoveSkill={(skill) => removeSkill(candidate.temp_id, skill)}
                  onRemove={() => removeCandidate(candidate.temp_id)}
                  onShowDuplicate={() => setDuplicateDialog({
                    candidate,
                    existingCandidate: candidate.duplicate_check?.existing_candidate
                  })}
                  onLinkToJob={() => {
                    loadJobs();
                    setLinkDialog({ candidate: candidate.duplicate_check?.existing_candidate, fromDuplicate: false });
                  }}
                />
              ))}
            </CardContent>
          </Card>
        </>
      )}

      <DuplicateWarningDialog duplicateDialog={duplicateDialog} onClose={() => setDuplicateDialog(null)} onAction={handleDuplicateAction} />
      <LinkToJobDialog linkDialog={linkDialog} onClose={() => setLinkDialog(null)} jobs={jobs} selectedJob={selectedJob} setSelectedJob={setSelectedJob} onLink={handleLinkToJob} />
        </TabsContent>

        <TabsContent value="naukri" className="mt-4">
          <Suspense fallback={<TabLoader />}><BulkImportContent /></Suspense>
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <Suspense fallback={<TabLoader />}><ImportHistoryContent /></Suspense>
        </TabsContent>
      </Tabs>
    </div>
  );
}