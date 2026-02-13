import { useState, useCallback } from 'react';
import { cvUploadAPI } from '../../lib/api';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { toast } from 'sonner';
import { Upload, FileText, Loader2, User, Mail, Phone, Briefcase, MapPin, X, Check, Pencil } from 'lucide-react';

export function CVUploadDialog({ open, onOpenChange, onProfileSaved }) {
  const [step, setStep] = useState('upload'); // upload | parsing | review
  const [file, setFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState(null);
  const [filename, setFilename] = useState('');

  const reset = useCallback(() => {
    setStep('upload');
    setFile(null);
    setParsing(false);
    setSaving(false);
    setProfile(null);
    setFilename('');
  }, []);

  const handleClose = () => {
    reset();
    onOpenChange(false);
  };

  const handleFileSelect = (e) => {
    const f = e.target.files?.[0];
    if (f) {
      const ext = f.name.split('.').pop().toLowerCase();
      if (!['pdf', 'docx', 'doc'].includes(ext)) {
        toast.error('Only PDF and DOCX files are supported');
        return;
      }
      if (f.size > 10 * 1024 * 1024) {
        toast.error('File too large (max 10MB)');
        return;
      }
      setFile(f);
      setFilename(f.name);
    }
  };

  const handleParse = async () => {
    if (!file) return;
    setParsing(true);
    setStep('parsing');
    try {
      const res = await cvUploadAPI.parse(file);
      const data = res.data;
      if (data.success && data.profile_data) {
        setProfile(data.profile_data);
        setStep('review');
        toast.success('CV parsed successfully');
      } else {
        toast.error('Failed to parse CV');
        setStep('upload');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to parse CV');
      setStep('upload');
    } finally {
      setParsing(false);
    }
  };

  const handleFieldChange = (field, value) => {
    setProfile(prev => ({ ...prev, [field]: value }));
  };

  const handleSkillRemove = (idx) => {
    setProfile(prev => ({
      ...prev,
      key_skills: prev.key_skills.filter((_, i) => i !== idx)
    }));
  };

  const handleSave = async () => {
    if (!profile?.name) {
      toast.error('Name is required');
      return;
    }
    setSaving(true);
    try {
      const res = await cvUploadAPI.save({ profile, filename });
      if (res.data.success) {
        toast.success(res.data.action === 'created' ? 'Candidate profile created' : 'Candidate profile updated');
        handleClose();
        onProfileSaved?.();
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="cv-upload-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="w-5 h-5 text-[#7CB342]" />
            {step === 'upload' && 'Upload CV'}
            {step === 'parsing' && 'Parsing CV...'}
            {step === 'review' && 'Review & Edit Profile'}
          </DialogTitle>
        </DialogHeader>

        {/* Step 1: Upload */}
        {step === 'upload' && (
          <div className="space-y-4">
            <div 
              className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-[#7CB342] transition-colors cursor-pointer"
              onClick={() => document.getElementById('cv-file-input').click()}
              data-testid="cv-dropzone"
            >
              <FileText className="w-12 h-12 mx-auto text-slate-400 mb-3" />
              <p className="text-slate-600 font-medium">
                {file ? file.name : 'Click to select or drag & drop a CV'}
              </p>
              <p className="text-sm text-slate-400 mt-1">PDF or DOCX, max 10MB</p>
              <input
                id="cv-file-input"
                type="file"
                accept=".pdf,.docx,.doc"
                onChange={handleFileSelect}
                className="hidden"
                data-testid="cv-file-input"
              />
            </div>
            {file && (
              <div className="flex items-center justify-between bg-slate-50 rounded-lg px-4 py-2">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-[#7CB342]" />
                  <span className="text-sm font-medium">{file.name}</span>
                  <span className="text-xs text-slate-400">({(file.size / 1024).toFixed(0)} KB)</span>
                </div>
                <Button variant="ghost" size="sm" onClick={() => { setFile(null); setFilename(''); }}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={handleClose}>Cancel</Button>
              <Button
                onClick={handleParse}
                disabled={!file}
                className="bg-[#7CB342] hover:bg-[#689F38]"
                data-testid="cv-parse-btn"
              >
                <Upload className="w-4 h-4 mr-2" /> Parse CV
              </Button>
            </DialogFooter>
          </div>
        )}

        {/* Step 2: Parsing */}
        {step === 'parsing' && (
          <div className="flex flex-col items-center justify-center py-12">
            <Loader2 className="w-10 h-10 text-[#7CB342] animate-spin mb-4" />
            <p className="text-slate-600 font-medium">AI is parsing the CV...</p>
            <p className="text-sm text-slate-400 mt-1">This may take a few seconds</p>
          </div>
        )}

        {/* Step 3: Review & Edit */}
        {step === 'review' && profile && (
          <div className="space-y-4">
            <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm text-green-700 flex items-center gap-2">
              <Pencil className="w-4 h-4" /> All fields are editable. Review and correct before saving.
            </div>

            {/* Basic Info */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-slate-500 flex items-center gap-1"><User className="w-3 h-3" /> Name *</Label>
                <Input
                  value={profile.name || ''}
                  onChange={e => handleFieldChange('name', e.target.value)}
                  data-testid="cv-name-input"
                />
              </div>
              <div>
                <Label className="text-xs text-slate-500 flex items-center gap-1"><Mail className="w-3 h-3" /> Email</Label>
                <Input
                  value={profile.email || ''}
                  onChange={e => handleFieldChange('email', e.target.value)}
                  data-testid="cv-email-input"
                />
              </div>
              <div>
                <Label className="text-xs text-slate-500 flex items-center gap-1"><Phone className="w-3 h-3" /> Phone</Label>
                <Input
                  value={profile.phone || ''}
                  onChange={e => handleFieldChange('phone', e.target.value)}
                  data-testid="cv-phone-input"
                />
              </div>
              <div>
                <Label className="text-xs text-slate-500 flex items-center gap-1"><MapPin className="w-3 h-3" /> Location</Label>
                <Input
                  value={profile.location || ''}
                  onChange={e => handleFieldChange('location', e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs text-slate-500 flex items-center gap-1"><Briefcase className="w-3 h-3" /> Current Company</Label>
                <Input
                  value={profile.current_company || ''}
                  onChange={e => handleFieldChange('current_company', e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs text-slate-500">Current Designation</Label>
                <Input
                  value={profile.current_designation || ''}
                  onChange={e => handleFieldChange('current_designation', e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs text-slate-500">Experience (years)</Label>
                <Input
                  type="number"
                  step="0.5"
                  value={profile.total_experience_years || ''}
                  onChange={e => handleFieldChange('total_experience_years', parseFloat(e.target.value) || null)}
                />
              </div>
              <div>
                <Label className="text-xs text-slate-500">Industry</Label>
                <Input
                  value={profile.current_industry || ''}
                  onChange={e => handleFieldChange('current_industry', e.target.value)}
                />
              </div>
            </div>

            {/* Summary */}
            <div>
              <Label className="text-xs text-slate-500">Profile Summary</Label>
              <textarea
                className="w-full mt-1 p-2 text-sm border border-slate-200 rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-[#7CB342]"
                rows={3}
                value={profile.profile_summary || ''}
                onChange={e => handleFieldChange('profile_summary', e.target.value)}
              />
            </div>

            {/* Skills */}
            <div>
              <Label className="text-xs text-slate-500">Skills</Label>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {(profile.key_skills || []).map((skill, idx) => (
                  <Badge key={idx} variant="secondary" className="text-xs px-2 py-0.5 gap-1">
                    {skill}
                    <X className="w-3 h-3 cursor-pointer hover:text-red-500" onClick={() => handleSkillRemove(idx)} />
                  </Badge>
                ))}
                <Input
                  className="w-32 h-6 text-xs"
                  placeholder="+ Add skill"
                  onKeyDown={e => {
                    if (e.key === 'Enter' && e.target.value.trim()) {
                      handleFieldChange('key_skills', [...(profile.key_skills || []), e.target.value.trim()]);
                      e.target.value = '';
                    }
                  }}
                />
              </div>
            </div>

            {/* Work Experience */}
            {profile.work_experience?.length > 0 && (
              <div>
                <Label className="text-xs text-slate-500">Work Experience ({profile.work_experience.length})</Label>
                <div className="space-y-2 mt-1">
                  {profile.work_experience.map((exp, idx) => (
                    <div key={idx} className="bg-slate-50 rounded-md p-2 text-sm">
                      <span className="font-medium">{exp.designation}</span>
                      <span className="text-slate-500"> at {exp.company}</span>
                      {exp.from_date && <span className="text-xs text-slate-400 ml-2">({exp.from_date} - {exp.to_date || 'Present'})</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Education */}
            {profile.education?.length > 0 && (
              <div>
                <Label className="text-xs text-slate-500">Education ({profile.education.length})</Label>
                <div className="space-y-2 mt-1">
                  {profile.education.map((edu, idx) => (
                    <div key={idx} className="bg-slate-50 rounded-md p-2 text-sm">
                      <span className="font-medium">{edu.degree}</span>
                      {edu.specialization && <span className="text-slate-500"> in {edu.specialization}</span>}
                      <span className="text-slate-500"> — {edu.institution}</span>
                      {edu.year_of_passing && <span className="text-xs text-slate-400 ml-2">({edu.year_of_passing})</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => { setStep('upload'); setProfile(null); }}>
                Re-upload
              </Button>
              <Button
                onClick={handleSave}
                disabled={saving || !profile.name}
                className="bg-[#7CB342] hover:bg-[#689F38]"
                data-testid="cv-save-btn"
              >
                {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Check className="w-4 h-4 mr-2" />}
                Save to Candidate Bank
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
