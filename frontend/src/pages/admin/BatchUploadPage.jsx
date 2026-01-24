import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { candidateBankAPI, jobAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { 
  Upload, FileText, User, Mail, Phone, AlertTriangle, Check, X, 
  DollarSign, Clock, Briefcase, Plus, Trash2, ArrowLeft, Save
} from 'lucide-react';

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
  
  // State
  const [files, setFiles] = useState([]);
  const [parsing, setParsing] = useState(false);
  const [parsedCandidates, setParsedCandidates] = useState([]);
  const [saving, setSaving] = useState(false);
  const [jobs, setJobs] = useState([]);
  
  // Duplicate handling dialog
  const [duplicateDialog, setDuplicateDialog] = useState(null);
  
  // Link to job dialog
  const [linkDialog, setLinkDialog] = useState(null);
  const [selectedJob, setSelectedJob] = useState('');

  // Load jobs for linking
  const loadJobs = async () => {
    try {
      const res = await jobAPI.getAll();
      setJobs(res.data.filter(j => j.status === 'active'));
    } catch (error) {
      console.error('Failed to load jobs', error);
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

  // Parse uploaded files
  const handleParse = async () => {
    if (files.length === 0) {
      toast.error('Please select files to upload');
      return;
    }
    
    setParsing(true);
    
    try {
      const res = await candidateBankAPI.batchParse(files);
      
      // Transform results for editing
      const candidates = res.data.results.map(r => ({
        ...r,
        editing: {
          name: r.parsed_data?.name || '',
          email: r.parsed_data?.email || '',
          phone: r.parsed_data?.phone || '',
          skills: r.parsed_data?.skills || [],
          experience_summary: r.parsed_data?.experience_summary || '',
          current_salary: '',  // MANDATORY - user must fill
          notice_period: '',   // MANDATORY - user must fill
          location: r.parsed_data?.location || '',  // MANDATORY - Data Governance
          experience_years: r.parsed_data?.experience_years?.toString() || '0',  // MANDATORY - Data Governance
        },
        isValid: false,  // Not valid until all mandatory fields filled
        errors: []
      }));
      
      setParsedCandidates(candidates);
      loadJobs();
      
      toast.success(`Parsed ${res.data.parsed} of ${res.data.total} files`);
      
      if (res.data.failed > 0) {
        toast.warning(`${res.data.failed} files failed to parse`);
      }
    } catch (error) {
      toast.error('Failed to parse files');
      console.error(error);
    } finally {
      setParsing(false);
    }
  };

  // Update candidate editing fields
  const updateCandidate = (tempId, field, value) => {
    setParsedCandidates(prev => prev.map(c => {
      if (c.temp_id !== tempId) return c;
      
      const newEditing = { ...c.editing, [field]: value };
      
      // Validate (Data Governance: all mandatory fields)
      const errors = [];
      if (!newEditing.name?.trim()) errors.push('Name is required');
      if (!newEditing.email?.trim()) errors.push('Email is required');
      if (!newEditing.current_salary || parseInt(newEditing.current_salary) <= 0) {
        errors.push('Current salary is required');
      }
      if (!newEditing.notice_period) errors.push('Notice period is required');
      if (!newEditing.location?.trim()) errors.push('Location is required');
      if (newEditing.experience_years === '' || parseInt(newEditing.experience_years) < 0) {
        errors.push('Experience (years) is required');
      }
      
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
        current_salary: parseInt(c.editing.current_salary),
        notice_period: c.editing.notice_period,
        location: c.editing.location,  // Data Governance: mandatory
        experience_years: parseInt(c.editing.experience_years),  // Data Governance: mandatory
        file_id: c.file_id,
        fingerprint: c.fingerprint
      }));
      
      const res = await candidateBankAPI.batchSave(payload);
      
      toast.success(res.data.message);
      
      // Clear state and redirect
      setFiles([]);
      setParsedCandidates([]);
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
            <h1 className="font-heading text-3xl font-bold text-slate-900">Batch CV Upload</h1>
            <p className="text-slate-500">Upload up to 10 CVs at once</p>
          </div>
        </div>
      </div>

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
                  disabled={parsing}
                  className="mt-4 bg-[#7CB342] hover:bg-[#689F38]"
                  data-testid="parse-btn"
                >
                  {parsing ? 'Parsing...' : 'Parse CVs'}
                </Button>
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
              {/* Mandatory Fields Notice */}
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-amber-800">
                  <strong>Salary & Notice Period are mandatory.</strong> All candidates must have these fields filled before saving.
                </div>
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

      {/* Duplicate Warning Dialog */}
      <Dialog open={!!duplicateDialog} onOpenChange={() => setDuplicateDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              Duplicate Candidate Detected
            </DialogTitle>
            <DialogDescription>
              A candidate with matching information already exists in the database.
            </DialogDescription>
          </DialogHeader>
          
          {duplicateDialog?.existingCandidate && (
            <div className="bg-slate-50 rounded-lg p-4 space-y-2">
              <div className="flex items-center gap-2">
                <User className="w-4 h-4 text-slate-500" />
                <span className="font-medium">{duplicateDialog.existingCandidate.name}</span>
              </div>
              <div className="text-sm text-slate-600">
                <p>Added: {new Date(duplicateDialog.existingCandidate.created_at).toLocaleDateString()}</p>
                {duplicateDialog.existingCandidate.current_salary && (
                  <p>Salary: {formatSalaryINR(duplicateDialog.existingCandidate.current_salary)}</p>
                )}
                {duplicateDialog.existingCandidate.notice_period && (
                  <p>Notice: {duplicateDialog.existingCandidate.notice_period}</p>
                )}
              </div>
            </div>
          )}
          
          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button variant="outline" onClick={() => setDuplicateDialog(null)}>
              Cancel
            </Button>
            <Button 
              variant="outline"
              onClick={() => handleDuplicateAction('link')}
              className="text-purple-600 border-purple-200 hover:bg-purple-50"
            >
              <Briefcase className="w-4 h-4 mr-2" />
              Apply Existing to Job
            </Button>
            <Button 
              onClick={() => handleDuplicateAction('update')}
              className="bg-amber-500 hover:bg-amber-600"
            >
              Update Existing
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Link to Job Dialog */}
      <Dialog open={!!linkDialog} onOpenChange={() => setLinkDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Add as Applicant</DialogTitle>
            <DialogDescription>
              Select a job to add {linkDialog?.candidate?.name} as an applicant
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Select Job / Mandate</Label>
              <Select value={selectedJob} onValueChange={setSelectedJob}>
                <SelectTrigger data-testid="select-job-dropdown">
                  <SelectValue placeholder="Choose a job..." />
                </SelectTrigger>
                <SelectContent>
                  {jobs.map(job => (
                    <SelectItem key={job.id} value={job.id}>
                      {job.title} - {job.company_name || 'Company'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            {linkDialog?.candidate && (
              <div className="bg-slate-50 rounded-lg p-3 text-sm">
                <p><strong>Candidate:</strong> {linkDialog.candidate.name}</p>
                {linkDialog.candidate.current_salary && (
                  <p><strong>Salary:</strong> {formatSalaryINR(linkDialog.candidate.current_salary)}</p>
                )}
                {linkDialog.candidate.notice_period && (
                  <p><strong>Notice:</strong> {linkDialog.candidate.notice_period}</p>
                )}
              </div>
            )}
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setLinkDialog(null)}>Cancel</Button>
            <Button 
              onClick={handleLinkToJob}
              disabled={!selectedJob}
              className="bg-[#7CB342] hover:bg-[#689F38]"
            >
              Add as Applicant
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Candidate Preview Card Component
function CandidateCard({ candidate, onUpdate, onAddSkill, onRemoveSkill, onRemove, onShowDuplicate, onLinkToJob }) {
  const [newSkill, setNewSkill] = useState('');
  
  if (!candidate.success) {
    return (
      <div className="border border-red-200 bg-red-50 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <X className="w-5 h-5 text-red-500" />
            <span className="font-medium text-red-700">{candidate.filename}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={onRemove}>
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
        <p className="text-sm text-red-600 mt-1">{candidate.error}</p>
      </div>
    );
  }
  
  const isDuplicate = candidate.duplicate_check?.is_duplicate;
  
  return (
    <div 
      className={`border rounded-lg p-4 ${
        isDuplicate ? 'border-amber-300 bg-amber-50' :
        candidate.isValid ? 'border-green-300 bg-green-50' :
        'border-slate-200 bg-white'
      }`}
      data-testid={`candidate-card-${candidate.temp_id}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-slate-500" />
          <span className="text-sm text-slate-600">{candidate.filename}</span>
          {isDuplicate && (
            <Badge variant="outline" className="text-amber-600 border-amber-300">
              <AlertTriangle className="w-3 h-3 mr-1" />
              Duplicate
            </Badge>
          )}
          {candidate.isValid && !isDuplicate && (
            <Badge variant="outline" className="text-green-600 border-green-300">
              <Check className="w-3 h-3 mr-1" />
              Ready
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
          {isDuplicate && (
            <Button variant="outline" size="sm" onClick={onShowDuplicate}>
              <AlertTriangle className="w-4 h-4 mr-1" />
              Resolve
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={onRemove}>
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      </div>
      
      {/* Validation Errors */}
      {candidate.errors?.length > 0 && (
        <div className="mb-4 p-2 bg-red-100 border border-red-200 rounded text-sm text-red-700">
          {candidate.errors.map((err, i) => (
            <p key={i}>• {err}</p>
          ))}
        </div>
      )}
      
      {/* Editable Fields */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Name */}
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Name *</Label>
          <Input
            value={candidate.editing.name}
            onChange={(e) => onUpdate('name', e.target.value)}
            placeholder="Full name"
            data-testid={`name-input-${candidate.temp_id}`}
          />
        </div>
        
        {/* Email */}
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Email *</Label>
          <Input
            value={candidate.editing.email}
            onChange={(e) => onUpdate('email', e.target.value)}
            placeholder="Email address"
            type="email"
            data-testid={`email-input-${candidate.temp_id}`}
          />
        </div>
        
        {/* Phone */}
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Phone</Label>
          <Input
            value={candidate.editing.phone}
            onChange={(e) => onUpdate('phone', e.target.value)}
            placeholder="Phone number"
          />
        </div>
        
        {/* Current Salary - MANDATORY */}
        <div className="space-y-1">
          <Label className="text-xs text-slate-500 flex items-center gap-1">
            <DollarSign className="w-3 h-3" />
            Current Salary (INR) *
          </Label>
          <Input
            value={candidate.editing.current_salary}
            onChange={(e) => onUpdate('current_salary', e.target.value)}
            placeholder="e.g., 1500000"
            type="number"
            className={!candidate.editing.current_salary ? 'border-amber-400' : ''}
            data-testid={`salary-input-${candidate.temp_id}`}
          />
        </div>
        
        {/* Notice Period - MANDATORY */}
        <div className="space-y-1">
          <Label className="text-xs text-slate-500 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            Notice Period *
          </Label>
          <Select 
            value={candidate.editing.notice_period}
            onValueChange={(v) => onUpdate('notice_period', v)}
          >
            <SelectTrigger 
              className={!candidate.editing.notice_period ? 'border-amber-400' : ''}
              data-testid={`notice-input-${candidate.temp_id}`}
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
        
        {/* Skills */}
        <div className="space-y-1 md:col-span-2">
          <Label className="text-xs text-slate-500">Skills</Label>
          <div className="flex flex-wrap gap-2 mb-2">
            {candidate.editing.skills.map((skill, i) => (
              <Badge key={i} variant="secondary" className="flex items-center gap-1">
                {skill}
                <button onClick={() => onRemoveSkill(skill)} className="ml-1 hover:text-red-500">
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              value={newSkill}
              onChange={(e) => setNewSkill(e.target.value)}
              placeholder="Add skill..."
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  onAddSkill(newSkill);
                  setNewSkill('');
                }
              }}
            />
            <Button 
              variant="outline" 
              size="sm"
              onClick={() => {
                onAddSkill(newSkill);
                setNewSkill('');
              }}
            >
              <Plus className="w-4 h-4" />
            </Button>
          </div>
        </div>
        
        {/* Experience Summary */}
        <div className="space-y-1 md:col-span-2">
          <Label className="text-xs text-slate-500">Experience Summary</Label>
          <Textarea
            value={candidate.editing.experience_summary}
            onChange={(e) => onUpdate('experience_summary', e.target.value)}
            placeholder="Brief summary of experience..."
            rows={2}
          />
        </div>
      </div>
    </div>
  );
}
