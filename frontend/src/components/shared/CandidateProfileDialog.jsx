/**
 * Reusable Candidate Profile Dialog Component
 * Shows complete candidate profile with all mandatory fields and edit capability
 * Used across: Candidate Bank, AI Screening, Pipeline, and anywhere candidate profile is shown
 */
import { useState, useEffect } from 'react';
import { candidateBankAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Textarea } from '../ui/textarea';
import { toast } from 'sonner';
import {
  User,
  Mail,
  Phone,
  MapPin,
  Clock,
  Briefcase,
  DollarSign,
  Building2,
  GraduationCap,
  Sparkles,
  Download,
  Edit2,
  Save,
  X,
  FileText,
  Activity,
  Calendar,
  ShieldAlert,
  Paperclip,
  CheckCircle2
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

export default function CandidateProfileDialog({
  candidate,
  isOpen,
  onClose,
  onUpdate,
  showDownloadResume = true,
  showEditButton = true
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [auditLog, setAuditLog] = useState([]);
  const [resumeHistory, setResumeHistory] = useState([]);
  const [activityHistory, setActivityHistory] = useState(null);
  
  // Edit form state
  const [editForm, setEditForm] = useState({
    name: '',
    email: '',
    phone: '',
    location: '',
    experience_years: '',
    current_salary: '',
    notice_period: '',
    current_employer: '',
    designation: '',
    industry: '',
    ug_course: '',
    date_of_birth: '',
    headline: '',
    summary: ''
  });

  // Load additional data when dialog opens
  useEffect(() => {
    if (candidate && isOpen) {
      loadCandidateDetails();
      // Initialize edit form with candidate data
      setEditForm({
        name: candidate.name || '',
        email: candidate.email || '',
        phone: candidate.phone || '',
        location: candidate.location || '',
        experience_years: candidate.experience_years?.toString() || '0',
        current_salary: candidate.current_salary?.toString() || '',
        notice_period: candidate.notice_period || '',
        current_employer: candidate.current_employer || '',
        designation: candidate.designation || candidate.headline || '',
        industry: candidate.industry || '',
        ug_course: candidate.ug_course || '',
        date_of_birth: candidate.date_of_birth || '',
        headline: candidate.headline || '',
        summary: candidate.summary || ''
      });
    }
  }, [candidate, isOpen]);

  const loadCandidateDetails = async () => {
    if (!candidate?.id) return;
    try {
      const [fullRes, auditRes, historyRes, activityRes] = await Promise.all([
        candidateBankAPI.getById(candidate.id),
        candidateBankAPI.getAuditLog(candidate.id),
        candidateBankAPI.getResumeHistory(candidate.id),
        candidateBankAPI.getHistory(candidate.id)
      ]);
      // Merge full record into candidate for Naukri-specific fields
      if (fullRes.data) {
        Object.assign(candidate, fullRes.data);
      }
      setAuditLog(auditRes.data || []);
      setResumeHistory(historyRes.data || {});
      setActivityHistory(activityRes.data || null);
    } catch (error) {
      console.error('Failed to load candidate details:', error);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Update mandatory fields via API
      await candidateBankAPI.updateSalaryNotice(
        candidate.id,
        editForm.current_salary ? parseInt(editForm.current_salary) : null,
        editForm.notice_period,
        editForm.location,
        editForm.experience_years ? parseInt(editForm.experience_years) : 0
      );
      
      // Update other fields
      await candidateBankAPI.update(candidate.id, {
        name: editForm.name,
        phone: editForm.phone,
        headline: editForm.designation || editForm.headline,
        summary: editForm.summary,
        current_employer: editForm.current_employer,
        designation: editForm.designation,
        industry: editForm.industry,
        ug_course: editForm.ug_course,
        date_of_birth: editForm.date_of_birth
      });
      
      toast.success('Profile updated successfully');
      setIsEditing(false);
      if (onUpdate) onUpdate();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setIsEditing(false);
    // Reset form to original values
    setEditForm({
      name: candidate.name || '',
      email: candidate.email || '',
      phone: candidate.phone || '',
      location: candidate.location || '',
      experience_years: candidate.experience_years?.toString() || '0',
      current_salary: candidate.current_salary?.toString() || '',
      notice_period: candidate.notice_period || '',
      current_employer: candidate.current_employer || '',
      designation: candidate.designation || candidate.headline || '',
      industry: candidate.industry || '',
      ug_course: candidate.ug_course || '',
      date_of_birth: candidate.date_of_birth || '',
      headline: candidate.headline || '',
      summary: candidate.summary || ''
    });
  };

  const downloadResume = () => {
    if (!candidate?.resume_url && !candidate?.active_resume_id) {
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

  const downloadAtsCv = () => {
    const token = localStorage.getItem('vhc_token');
    const atsUrl = candidateBankAPI.getAtsCvUrl(candidate.id);
    const link = document.createElement('a');
    link.href = `${atsUrl}?token=${token}`;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!candidate) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="font-heading text-xl">Candidate Profile</DialogTitle>
            <div className="flex items-center gap-2">
              {showDownloadResume && (candidate.resume_url || candidate.active_resume_id) && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={downloadResume}
                  className="text-[#7CB342] border-[#7CB342] hover:bg-green-50"
                  data-testid="download-resume-btn"
                >
                  <Download className="w-4 h-4 mr-1" /> Download CV
                </Button>
              )}
              {showEditButton && !isEditing && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsEditing(true)}
                  data-testid="edit-profile-btn"
                >
                  <Edit2 className="w-4 h-4 mr-1" /> Edit
                </Button>
              )}
              {isEditing && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCancel}
                  >
                    <X className="w-4 h-4 mr-1" /> Cancel
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleSave}
                    disabled={saving}
                    className="bg-[#7CB342] hover:bg-[#689F38]"
                    data-testid="save-profile-btn"
                  >
                    <Save className="w-4 h-4 mr-1" /> {saving ? 'Saving...' : 'Save'}
                  </Button>
                </>
              )}
            </div>
          </div>
        </DialogHeader>

        <Tabs defaultValue="profile" className="w-full mt-4">
          <TabsList className="mb-4">
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="experience">Experience</TabsTrigger>
            <TabsTrigger value="education">Education</TabsTrigger>
            <TabsTrigger value="activity">Activity</TabsTrigger>
            <TabsTrigger value="audit">Audit Log</TabsTrigger>
          </TabsList>

          {/* Profile Tab */}
          <TabsContent value="profile">
            <div className="space-y-6">
              {/* Bulk Import Banner */}
              {candidate.source === 'bulk_import' && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <ShieldAlert className="w-5 h-5 text-amber-600 mt-0.5" />
                    <div className="flex-1">
                      <p className="font-medium text-amber-800 text-sm">Bulk Import Candidate</p>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs">
                        <Badge variant="outline" className="border-amber-300">
                          Type: {candidate.bulk_import_type || 'N/A'}
                        </Badge>
                        <Badge variant="outline" className={candidate.cv_attached ? 'border-green-300 text-green-700' : 'border-red-300 text-red-700'}>
                          CV: {candidate.cv_attached ? 'Attached' : 'Not attached'}
                        </Badge>
                        {candidate.bulk_import_restricted && (
                          <Badge variant="outline" className="border-amber-500 text-amber-700">
                            Admin Only
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Header with Avatar */}
              <div className="flex items-center gap-4">
                <div className="w-20 h-20 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                  <span className="text-[#7CB342] font-bold text-3xl">
                    {(isEditing ? editForm.name : candidate.name)?.charAt(0).toUpperCase() || '?'}
                  </span>
                </div>
                <div className="flex-1">
                  {isEditing ? (
                    <Input
                      value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      className="text-xl font-semibold mb-1"
                      placeholder="Full Name"
                    />
                  ) : (
                    <h2 className="text-xl font-semibold text-slate-900">{candidate.name || 'Unknown'}</h2>
                  )}
                  {isEditing ? (
                    <Input
                      value={editForm.designation}
                      onChange={(e) => setEditForm({ ...editForm, designation: e.target.value })}
                      className="text-sm"
                      placeholder="Designation/Headline"
                    />
                  ) : (
                    <p className="text-slate-500">{candidate.designation || candidate.headline || '-'}</p>
                  )}
                </div>
              </div>

              {/* Contact & Basic Info */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Contact No */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <Phone className="w-4 h-4" /> Contact No. *
                  </Label>
                  {isEditing ? (
                    <Input
                      value={editForm.phone}
                      onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                      placeholder="Phone number"
                    />
                  ) : (
                    <p className="font-medium">{candidate.phone || <span className="text-amber-600">Unknown</span>}</p>
                  )}
                </div>

                {/* Email */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <Mail className="w-4 h-4" /> Email *
                  </Label>
                  <p className="font-medium">{candidate.email || <span className="text-amber-600">Unknown</span>}</p>
                </div>

                {/* Work Experience */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <Briefcase className="w-4 h-4" /> Work Experience *
                  </Label>
                  {isEditing ? (
                    <Input
                      type="number"
                      min="0"
                      value={editForm.experience_years}
                      onChange={(e) => setEditForm({ ...editForm, experience_years: e.target.value })}
                      placeholder="Years of experience"
                    />
                  ) : (
                    <p className="font-medium">{candidate.experience_years || 0} years</p>
                  )}
                </div>

                {/* Current CTC */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <DollarSign className="w-4 h-4" /> Current CTC *
                  </Label>
                  {isEditing ? (
                    <div>
                      <Input
                        type="number"
                        value={editForm.current_salary}
                        onChange={(e) => setEditForm({ ...editForm, current_salary: e.target.value })}
                        placeholder="Annual salary in INR"
                      />
                      {editForm.current_salary && (
                        <p className="text-xs text-slate-500 mt-1">{formatSalaryINR(parseInt(editForm.current_salary))}</p>
                      )}
                    </div>
                  ) : (
                    <p className="font-medium">
                      {candidate.current_salary ? formatSalaryINR(candidate.current_salary) : <span className="text-amber-600">Unknown</span>}
                    </p>
                  )}
                </div>

                {/* Current Location */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <MapPin className="w-4 h-4" /> Current Location *
                  </Label>
                  {isEditing ? (
                    <Input
                      value={editForm.location}
                      onChange={(e) => setEditForm({ ...editForm, location: e.target.value })}
                      placeholder="City, State"
                    />
                  ) : (
                    <p className="font-medium">{candidate.location || <span className="text-amber-600">Unknown</span>}</p>
                  )}
                </div>

                {/* Notice Period */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <Clock className="w-4 h-4" /> Notice Period *
                  </Label>
                  {isEditing ? (
                    <Select value={editForm.notice_period} onValueChange={(v) => setEditForm({ ...editForm, notice_period: v })}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select notice period" />
                      </SelectTrigger>
                      <SelectContent>
                        {NOTICE_PERIODS.map(np => (
                          <SelectItem key={np} value={np}>{np}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <p className="font-medium">{candidate.notice_period || <span className="text-amber-600">Unknown</span>}</p>
                  )}
                </div>

                {/* Current Employer */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <Building2 className="w-4 h-4" /> Current Employer *
                  </Label>
                  {isEditing ? (
                    <Input
                      value={editForm.current_employer}
                      onChange={(e) => setEditForm({ ...editForm, current_employer: e.target.value })}
                      placeholder="Company name"
                    />
                  ) : (
                    <p className="font-medium">{candidate.current_employer || <span className="text-amber-600">Unknown</span>}</p>
                  )}
                </div>

                {/* Current Designation */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <Briefcase className="w-4 h-4" /> Current Designation *
                  </Label>
                  {isEditing ? (
                    <Input
                      value={editForm.designation}
                      onChange={(e) => setEditForm({ ...editForm, designation: e.target.value })}
                      placeholder="Job title"
                    />
                  ) : (
                    <p className="font-medium">{candidate.designation || candidate.headline || <span className="text-amber-600">Unknown</span>}</p>
                  )}
                </div>

                {/* Industry */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <Building2 className="w-4 h-4" /> Industry 
                    {candidate.industry_source === 'ai_detected' && (
                      <Badge variant="secondary" className="bg-green-100 text-green-700 text-xs ml-1">
                        <Sparkles className="w-3 h-3 mr-1" /> AI Detected
                      </Badge>
                    )}
                  </Label>
                  {isEditing ? (
                    <Input
                      value={editForm.industry}
                      onChange={(e) => setEditForm({ ...editForm, industry: e.target.value })}
                      placeholder="Industry/Sector"
                    />
                  ) : (
                    <p className="font-medium">{candidate.industry || '-'}</p>
                  )}
                </div>

                {/* Date of Birth */}
                <div className="space-y-1">
                  <Label className="flex items-center gap-2 text-slate-600">
                    <Calendar className="w-4 h-4" /> Date of Birth / Age
                  </Label>
                  {isEditing ? (
                    <Input
                      value={editForm.date_of_birth}
                      onChange={(e) => setEditForm({ ...editForm, date_of_birth: e.target.value })}
                      placeholder="DOB or Age"
                    />
                  ) : (
                    <p className="font-medium">{candidate.date_of_birth || '-'}</p>
                  )}
                </div>
              </div>

              {/* Skills */}
              {candidate.skills?.length > 0 && (
                <div className="space-y-2">
                  <Label className="text-slate-600">Skills</Label>
                  <div className="flex flex-wrap gap-1">
                    {candidate.skills.map((skill, i) => (
                      <Badge key={i} variant="secondary" className="bg-[#DCFCE7] text-[#7CB342]">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Summary */}
              <div className="space-y-2">
                <Label className="text-slate-600">Summary</Label>
                {isEditing ? (
                  <Textarea
                    value={editForm.summary}
                    onChange={(e) => setEditForm({ ...editForm, summary: e.target.value })}
                    placeholder="Professional summary..."
                    rows={3}
                  />
                ) : (
                  <p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">
                    {candidate.summary || 'No summary available'}
                  </p>
                )}
              </div>
            </div>
          </TabsContent>

          {/* Experience Tab */}
          <TabsContent value="experience">
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Work Experience</h3>
              {candidate.experience?.length > 0 ? (
                <div className="space-y-3">
                  {candidate.experience.map((exp, i) => (
                    <div key={i} className="p-4 bg-slate-50 rounded-lg border-l-4 border-[#7CB342]">
                      <p className="font-semibold text-slate-900">{exp.designation || exp.title || 'Position'}</p>
                      <p className="text-sm text-slate-600">{exp.company || 'Company'}</p>
                      <p className="text-xs text-slate-400 mt-1">
                        {exp.from_date && exp.to_date ? `${exp.from_date} – ${exp.to_date}` : exp.duration || ''}
                      </p>
                      {(exp.location || exp.department) && (
                        <p className="text-xs text-slate-400">{[exp.location, exp.department].filter(Boolean).join(' · ')}</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 text-center py-8">No experience data available</p>
              )}
            </div>
          </TabsContent>

          {/* Education Tab */}
          <TabsContent value="education">
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Education</h3>
              
              {/* UG Course from bulk import */}
              {candidate.ug_course && (
                <div className="p-4 bg-slate-50 rounded-lg border-l-4 border-blue-500">
                  <div className="flex items-center gap-2 mb-1">
                    <GraduationCap className="w-4 h-4 text-blue-600" />
                    <span className="font-semibold text-slate-900">Undergraduate Course</span>
                  </div>
                  <p className="text-sm text-slate-600">{candidate.ug_course}</p>
                </div>
              )}
              
              {candidate.education?.length > 0 ? (
                <div className="space-y-3">
                  {candidate.education.map((edu, i) => (
                    <div key={i} className="p-4 bg-slate-50 rounded-lg border-l-4 border-blue-500">
                      <p className="font-semibold text-slate-900">{edu.degree || 'Degree'}</p>
                      {edu.specialization && <p className="text-sm text-slate-500">{edu.specialization}</p>}
                      <p className="text-sm text-slate-600">{edu.institution || edu.university || edu.school || ''}</p>
                      {(edu.year || edu.pass_out_year) && <p className="text-xs text-slate-400 mt-1">{edu.year || edu.pass_out_year}</p>}
                    </div>
                  ))}
                </div>
              ) : !candidate.ug_course && (
                <p className="text-slate-500 text-center py-8">No education data available</p>
              )}
            </div>
          </TabsContent>

          {/* Activity Tab */}
          <TabsContent value="activity">
            <div className="space-y-4">
              {/* Summary Stats */}
              {activityHistory?.summary && (
                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="bg-blue-50 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-blue-600">{activityHistory.summary.total_applications || 0}</p>
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

              {/* Application History */}
              <div>
                <h4 className="font-semibold mb-2">Application History</h4>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {activityHistory?.applications?.map((app) => (
                    <div key={app.application_id} className="p-3 bg-slate-50 rounded-lg text-sm border-l-4 border-[#7CB342]">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-slate-800">{app.job_title}</span>
                        <Badge className={
                          app.stage === 'hired' ? 'bg-green-100 text-green-700' :
                          app.stage === 'rejected' ? 'bg-red-100 text-red-700' :
                          app.stage === 'interview' ? 'bg-blue-100 text-blue-700' :
                          'bg-slate-100 text-slate-600'
                        }>
                          {app.stage}
                        </Badge>
                      </div>
                      <p className="text-slate-500">{app.company_name}</p>
                      <p className="text-xs text-slate-400 mt-1">
                        Applied: {new Date(app.applied_at).toLocaleDateString()}
                      </p>
                    </div>
                  ))}
                  {(!activityHistory?.applications || activityHistory.applications.length === 0) && (
                    <p className="text-slate-400 text-sm text-center py-4">No application history</p>
                  )}
                </div>
              </div>
            </div>
          </TabsContent>

          {/* Audit Log Tab */}
          <TabsContent value="audit">
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {auditLog.length > 0 ? (
                auditLog.map((log, i) => (
                  <div key={i} className="p-3 bg-slate-50 rounded-lg text-sm">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-slate-700">{log.field_changed}</span>
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
                      By {log.updated_by_name} ({log.updated_by_role})
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-slate-400 text-sm text-center py-8">No audit history</p>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
