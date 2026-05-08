import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import {
  Mail, Phone, MapPin, FileText, Clock, Activity, TrendingUp, Download, Paperclip,
  ShieldAlert, Building2, Sparkles, ExternalLink, Trash2, CalendarDays, Briefcase, DollarSign,
} from 'lucide-react';
import { NOTICE_PERIODS } from '../candidate-bank/CandidateBankFilters';
import { formatSalaryINR } from '../../lib/currency';
import SimilarCandidatesPanel from './SimilarCandidatesPanel';

export function CandidateDetailDialog({
  candidate, onClose,
  auditLog, resumeHistory, activityHistory,
  isEditing, editForm, onEditFormChange,
  onStartEdit, onCancelEdit, onSaveProfile, savingProfile,
  onDownloadResume, onAttachCV, onDelete,
  user,
}) {
  if (!candidate) return null;

  const updateField = (key, value) => onEditFormChange({ ...editForm, [key]: value });

  return (
    <Dialog open={!!candidate} onOpenChange={() => { onClose(); onCancelEdit(); }}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto w-[95vw] sm:w-auto">
        <DialogHeader>
          <DialogTitle className="font-heading">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <span>Candidate Profile</span>
              <div className="flex items-center gap-2 flex-wrap">
                {(candidate.cv_attached || candidate.resume_url) && (
                  <Button variant="outline" size="sm" onClick={() => onDownloadResume(candidate)} className="text-[#7CB342] border-[#7CB342] hover:bg-green-50 text-xs" data-testid="download-cv-btn">
                    <Download className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Download CV</span>
                  </Button>
                )}
                {!candidate.cv_attached && !candidate.resume_url && (
                  <Button variant="outline" size="sm" onClick={() => onAttachCV(candidate)} className="text-amber-600 border-amber-400 hover:bg-amber-50 text-xs" data-testid="attach-cv-btn">
                    <Paperclip className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Attach CV</span>
                  </Button>
                )}
                {!isEditing ? (
                  <Button variant="outline" size="sm" onClick={onStartEdit} data-testid="edit-profile-btn">
                    <Activity className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Edit</span>
                  </Button>
                ) : (
                  <>
                    <Button variant="outline" size="sm" onClick={onCancelEdit}>Cancel</Button>
                    <Button size="sm" onClick={onSaveProfile} disabled={savingProfile} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="save-profile-btn">
                      {savingProfile ? 'Saving...' : 'Save'}
                    </Button>
                  </>
                )}
                {user?.role === 'admin' && (
                  <Button variant="ghost" size="sm" onClick={onDelete} className="text-red-500 hover:text-red-700 hover:bg-red-50" data-testid="delete-candidate-btn">
                    <Trash2 className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Delete</span>
                  </Button>
                )}
              </div>
            </div>
          </DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="profile" className="w-full">
          <TabsList className="mb-4 w-full flex overflow-x-auto">
            <TabsTrigger value="profile" className="flex-1 text-xs sm:text-sm">Profile</TabsTrigger>
            <TabsTrigger value="experience" className="flex-1 text-xs sm:text-sm">Experience</TabsTrigger>
            <TabsTrigger value="education" className="flex-1 text-xs sm:text-sm">Education</TabsTrigger>
            <TabsTrigger value="activity" data-testid="activity-history-tab" className="flex-1 text-xs sm:text-sm">Activity</TabsTrigger>
            <TabsTrigger value="audit" className="flex-1 text-xs sm:text-sm">Audit</TabsTrigger>
          </TabsList>

          {/* Profile Tab */}
          <TabsContent value="profile">
            <ProfileTab
              candidate={candidate} isEditing={isEditing}
              editForm={editForm} updateField={updateField}
            />
            {!isEditing && candidate.id && (
              <SimilarCandidatesPanel
                candidateId={candidate.id}
                onSelect={(id) => {
                  if (typeof window !== 'undefined') {
                    window.dispatchEvent(new CustomEvent('vhc:open-candidate', { detail: { id } }));
                  }
                }}
              />
            )}
          </TabsContent>

          {/* Experience Tab */}
          <TabsContent value="experience">
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Work Experience</h3>
              {candidate.experience?.length > 0 ? (
                <div className="space-y-3">
                  {candidate.experience.map((exp, i) => (
                    <div key={`exp-${exp.company}-${i}`} className="p-4 bg-slate-50 rounded-lg border-l-4 border-[#7CB342]">
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
              {candidate.ug_course && (
                <div className="p-4 bg-slate-50 rounded-lg border-l-4 border-blue-500">
                  <div className="flex items-center gap-2 mb-1">
                    <FileText className="w-4 h-4 text-blue-600" />
                    <span className="font-semibold text-slate-900">Undergraduate Course</span>
                  </div>
                  <p className="text-sm text-slate-600">{candidate.ug_course}</p>
                </div>
              )}
              {candidate.education?.length > 0 ? (
                <div className="space-y-3">
                  {candidate.education.map((edu, i) => (
                    <div key={`edu-${edu.degree}-${i}`} className="p-4 bg-slate-50 rounded-lg border-l-4 border-blue-500">
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
          <TabsContent value="activity" data-testid="activity-history-content">
            <ActivityTab activityHistory={activityHistory} />
          </TabsContent>

          {/* Resume History Tab */}
          <TabsContent value="resumes">
            <div className="space-y-3">
              <p className="text-sm text-slate-500">Active: {resumeHistory?.active_resume_id || 'None'}</p>
              {resumeHistory?.resume_versions?.map((resume) => (
                <div key={resume.id} className={`p-3 rounded-lg border ${resume.is_active ? 'border-[#7CB342] bg-[#DCFCE7]/20' : 'border-slate-200'}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-slate-400" />
                      <span className="font-medium">{resume.filename}</span>
                      {resume.is_active && <span className="px-2 py-0.5 bg-[#7CB342] text-white text-xs rounded-full">Active</span>}
                    </div>
                    <span className="text-xs text-slate-400">{new Date(resume.uploaded_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
                  </div>
                </div>
              ))}
              {(!resumeHistory?.resume_versions || resumeHistory.resume_versions.length === 0) && (
                <p className="text-slate-400 text-sm">No resume history</p>
              )}
            </div>
          </TabsContent>

          {/* Audit Tab */}
          <TabsContent value="audit">
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {auditLog.map((log) => (
                <div key={log.id} className="p-3 bg-slate-50 rounded-lg text-sm">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-slate-700">{log.field_changed}</span>
                    <span className="text-xs text-slate-400">{new Date(log.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
                  </div>
                  <p className="text-slate-500">
                    <span className="text-red-500 line-through">{log.old_value || 'null'}</span>
                    {' → '}
                    <span className="text-green-600">{log.new_value}</span>
                  </p>
                  <p className="text-xs text-slate-400 mt-1">By {log.updated_by_name} ({log.updated_by_role}) via {log.source}</p>
                </div>
              ))}
              {auditLog.length === 0 && <p className="text-slate-400 text-sm">No audit history</p>}
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

/* ────── Sub-sections ────── */

function ProfileTab({ candidate, isEditing, editForm, updateField }) {
  return (
    <div className="space-y-4">
      {/* Bulk Import Banner */}
      {candidate.source === 'bulk_import' && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="flex items-start gap-2">
            <ShieldAlert className="w-5 h-5 text-amber-600 mt-0.5" />
            <div className="flex-1">
              <p className="font-medium text-amber-800 text-sm">Bulk Import Candidate</p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <Badge variant="outline" className="border-amber-300">Type: {candidate.bulk_import_type || 'N/A'}</Badge>
                <Badge variant="outline" className={candidate.cv_attached ? 'border-green-300 text-green-700' : 'border-red-300 text-red-700'}>
                  CV: {candidate.cv_attached ? 'Attached' : 'Not attached'}
                </Badge>
                {candidate.bulk_import_restricted && <Badge variant="outline" className="border-amber-500 text-amber-700">Admin Only</Badge>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Extension Source Banner */}
      {(candidate.source === 'naukri_extension' || candidate.source === 'linkedin_extension' || candidate.source === 'foundit_extension' || candidate.source === 'naukri_mailer_extension') && (
        <SourceBanner candidate={candidate} />
      )}

      {/* AI Summary */}
      {!isEditing && candidate.ai_summary && (
        <div
          className="rounded-lg border border-emerald-200 bg-gradient-to-r from-emerald-50 to-white p-3"
          data-testid="ai-summary-card"
        >
          <div className="flex items-center gap-2 mb-1.5">
            <Sparkles className="w-4 h-4 text-emerald-600" />
            <p className="text-xs font-semibold text-emerald-800 uppercase tracking-wider">AI Summary</p>
          </div>
          <p className="text-sm text-slate-700 whitespace-pre-line leading-relaxed">
            {candidate.ai_summary}
          </p>
        </div>
      )}

      {/* Header with Avatar */}
      <div className="flex items-center gap-3 sm:gap-4">
        <div className="w-12 h-12 sm:w-16 sm:h-16 rounded-full bg-[#DCFCE7] flex items-center justify-center flex-shrink-0">
          <span className="text-[#7CB342] font-bold text-xl sm:text-2xl">
            {(isEditing ? editForm.name : candidate.name)?.charAt(0).toUpperCase() || '?'}
          </span>
        </div>
        <div className="flex-1">
          {isEditing ? (
            <Input value={editForm.name} onChange={(e) => updateField('name', e.target.value)} className="text-xl font-semibold mb-1" placeholder="Full Name" />
          ) : (
            <h3 className="font-semibold text-xl">{candidate.name || 'Unknown'}</h3>
          )}
          {isEditing ? (
            <Input value={editForm.designation} onChange={(e) => updateField('designation', e.target.value)} className="text-sm" placeholder="Designation/Headline" />
          ) : (
            <p className="text-slate-500">{candidate.designation || candidate.headline || '-'}</p>
          )}
        </div>
      </div>

      {/* Fields Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-50 p-4 rounded-lg">
        <FieldRow icon={Phone} label="Contact No. *" isEditing={isEditing}
          editNode={<Input value={editForm.phone} onChange={(e) => updateField('phone', e.target.value)} placeholder="Phone number" />}
          displayValue={candidate.phone}
        />
        <FieldRow icon={Mail} label="Email *" displayValue={candidate.email} />
        <FieldRow icon={Clock} label="Work Experience *" isEditing={isEditing}
          editNode={<Input type="number" min="0" value={editForm.experience_years} onChange={(e) => updateField('experience_years', e.target.value)} placeholder="Years" />}
          displayValue={`${candidate.experience_years || 0} years`}
        />
        <FieldRow icon={DollarSign} label="Current CTC *" isEditing={isEditing}
          editNode={
            <div>
              <Input type="number" value={editForm.current_salary} onChange={(e) => updateField('current_salary', e.target.value)} placeholder="Annual salary in INR" />
              {editForm.current_salary && <p className="text-xs text-slate-500 mt-1">{formatSalaryINR(parseInt(editForm.current_salary))}</p>}
            </div>
          }
          displayValue={candidate.current_salary ? formatSalaryINR(candidate.current_salary) : null}
        />
        <FieldRow icon={MapPin} label="Current Location *" isEditing={isEditing}
          editNode={<Input value={editForm.location} onChange={(e) => updateField('location', e.target.value)} placeholder="City, State" />}
          displayValue={candidate.location}
        />
        <FieldRow icon={Clock} label="Notice Period *" isEditing={isEditing}
          editNode={
            <Select value={editForm.notice_period} onValueChange={(v) => updateField('notice_period', v)}>
              <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
              <SelectContent>{NOTICE_PERIODS.map(np => <SelectItem key={np} value={np}>{np}</SelectItem>)}</SelectContent>
            </Select>
          }
          displayValue={candidate.notice_period}
        />
        <FieldRow icon={Building2} label="Current Employer *" isEditing={isEditing}
          editNode={<Input value={editForm.current_employer} onChange={(e) => updateField('current_employer', e.target.value)} placeholder="Company name" />}
          displayValue={candidate.current_employer}
        />
        <FieldRow icon={Briefcase} label="Current Designation *" isEditing={isEditing}
          editNode={<Input value={editForm.designation} onChange={(e) => updateField('designation', e.target.value)} placeholder="Job title" />}
          displayValue={candidate.designation || candidate.headline}
        />
        <div className="space-y-1">
          <p className="text-xs text-slate-500 flex items-center gap-1">
            <Building2 className="w-3 h-3" /> Industry
            {candidate.industry_source === 'ai_detected' && (
              <Badge variant="secondary" className="bg-green-100 text-green-700 text-xs ml-1"><Sparkles className="w-2 h-2 mr-0.5" /> AI</Badge>
            )}
          </p>
          {isEditing ? (
            <Input value={editForm.industry} onChange={(e) => updateField('industry', e.target.value)} placeholder="Industry/Sector" />
          ) : (
            <p className="font-medium">{candidate.industry || '-'}</p>
          )}
        </div>
        <FieldRow icon={CalendarDays} label="Date of Birth / Age" displayValue={candidate.date_of_birth || '-'} />
      </div>

      {/* Profile Freshness */}
      <div className="flex items-center gap-4 text-xs text-slate-500 border-t pt-3">
        {candidate.last_profile_updated_at && (
          <span className="flex items-center gap-1"><CalendarDays className="w-3 h-3" /> Profile Updated: {new Date(candidate.last_profile_updated_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
        )}
        {candidate.last_application_date && (
          <span className="flex items-center gap-1"><FileText className="w-3 h-3" /> Last Applied: {new Date(candidate.last_application_date).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
        )}
      </div>

      {/* Skills */}
      {candidate.skills?.length > 0 && (
        <div>
          <h4 className="font-medium mb-2 text-sm text-slate-700">Skills</h4>
          <div className="flex flex-wrap gap-1">
            {candidate.skills.map((skill, i) => (
              <Badge key={`skill-${skill}-${i}`} variant="secondary" className="bg-[#DCFCE7] text-[#7CB342]">{skill}</Badge>
            ))}
          </div>
        </div>
      )}

      {/* Summary */}
      {candidate.summary && (
        <div>
          <h4 className="font-medium mb-2 text-sm text-slate-700">Summary</h4>
          <p className="text-sm text-slate-600 bg-white p-3 rounded-lg border">{candidate.summary}</p>
        </div>
      )}
    </div>
  );
}

function FieldRow({ icon: Icon, label, isEditing, editNode, displayValue }) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-slate-500 flex items-center gap-1"><Icon className="w-3 h-3" /> {label}</p>
      {isEditing && editNode ? editNode : (
        <p className="font-medium">{displayValue || <span className="text-amber-600">Unknown</span>}</p>
      )}
    </div>
  );
}

function SourceBanner({ candidate }) {
  const isLinkedin = candidate.source === 'linkedin_extension';
  const isFoundit = candidate.source === 'foundit_extension';
  const colors = isLinkedin ? { bg: 'bg-blue-50 border-blue-200', text: 'text-blue-600', title: 'text-blue-800' }
    : isFoundit ? { bg: 'bg-purple-50 border-purple-200', text: 'text-purple-600', title: 'text-purple-800' }
    : { bg: 'bg-orange-50 border-orange-200', text: 'text-orange-600', title: 'text-orange-800' };
  const sourceName = isLinkedin ? 'LinkedIn' : isFoundit ? 'Foundit' : candidate.source === 'naukri_mailer_extension' ? 'Naukri Mailer' : 'Naukri';

  return (
    <div className={`border rounded-lg p-3 ${colors.bg}`}>
      <div className="flex items-start gap-2">
        <FileText className={`w-5 h-5 mt-0.5 ${colors.text}`} />
        <div className="flex-1">
          <p className={`font-medium text-sm ${colors.title}`}>{sourceName} Sourced Profile</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {candidate.source_details?.captured_by_name && (
              <Badge variant="outline" className="border-orange-300">Captured by: {candidate.source_details.captured_by_name}</Badge>
            )}
            {candidate.naukri_profile_url && (
              <a href={candidate.naukri_profile_url} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-orange-300 text-orange-700 hover:bg-orange-100">
                View on Naukri <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ActivityTab({ activityHistory }) {
  return (
    <div className="space-y-4">
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

      {activityHistory?.freshness && (
        <div className="bg-slate-50 rounded-lg p-3 text-sm space-y-1">
          <p className="font-medium text-slate-700 mb-2">Profile Freshness</p>
          <div className="flex items-center gap-2 text-slate-600">
            <CalendarDays className="w-4 h-4" /> Created: {activityHistory.freshness.profile_created_at ? new Date(activityHistory.freshness.profile_created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' }) : 'N/A'}
          </div>
          <div className="flex items-center gap-2 text-slate-600">
            <TrendingUp className="w-4 h-4" /> Last Profile Update: {activityHistory.freshness.last_profile_updated_at ? new Date(activityHistory.freshness.last_profile_updated_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' }) : 'Never'}
          </div>
          <div className="flex items-center gap-2 text-slate-600">
            <Briefcase className="w-4 h-4" /> Last Application: {activityHistory.freshness.last_application_date ? new Date(activityHistory.freshness.last_application_date).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' }) : 'Never'}
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
                  app.stage === 'offered' ? 'bg-purple-100 text-purple-700' :
                  'bg-slate-100 text-slate-600'
                }`}>{app.stage}</span>
              </div>
              <p className="text-slate-500">{app.company_name}</p>
              <div className="flex items-center gap-4 mt-1 text-xs text-slate-400">
                <span>Applied: {new Date(app.applied_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
                <span>Source: {app.source}</span>
                {app.current_salary_at_application && <span>Salary: {formatSalaryINR(app.current_salary_at_application)}</span>}
              </div>
            </div>
          ))}
          {(!activityHistory?.applications || activityHistory.applications.length === 0) && (
            <p className="text-slate-400 text-sm">No application history</p>
          )}
        </div>
      </div>

      {activityHistory?.profile_audit?.length > 0 && (
        <div>
          <h4 className="font-medium mb-2">Recent Profile Changes</h4>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {activityHistory.profile_audit.map((entry, idx) => (
              <div key={`audit-${entry.field}-${idx}`} className="p-2 bg-amber-50 rounded text-xs">
                <span className="font-medium">{entry.field}</span>: {String(entry.old_value) || 'null'} → {String(entry.new_value)}
                <span className="text-slate-400 ml-2">by {entry.changed_by_name} ({entry.changed_by_role})</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
