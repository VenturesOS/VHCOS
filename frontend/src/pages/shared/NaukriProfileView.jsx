import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { extensionAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import { ArrowLeft, User, Mail, Phone, MapPin, Briefcase, GraduationCap,
  Clock, Globe, Award, FolderOpen, Languages, FileText,
  Building2, Calendar, ExternalLink, ChevronRight, Download, RefreshCw, Paperclip, Upload, Trash2
} from 'lucide-react';
import { candidateBankAPI, bulkImportAPI } from '../../lib/api';
import { Textarea } from '../../components/ui/textarea';
import CandidateActivityTimeline from '../../components/shared/CandidateActivityTimeline';

function Section({ title, icon: Icon, children, testId }) {
  return (
    <div className="mb-6" data-testid={testId}>
      <h3 className="font-heading text-base font-semibold text-slate-800 flex items-center gap-2 mb-3 pb-2 border-b border-slate-100">
        {Icon && <Icon className="w-4 h-4 text-[#7CB342]" />}
        {title}
      </h3>
      {children}
    </div>
  );
}

function InfoRow({ label, value, icon: Icon }) {
  if (!value && value !== 0) return null;
  return (
    <div className="flex items-start gap-2 py-1.5 text-sm">
      {Icon && <Icon className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />}
      <span className="text-slate-500 min-w-[120px]">{label}</span>
      <span className="text-slate-800 font-medium">{value}</span>
    </div>
  );
}

function TimelineCard({ title, subtitle, duration, description, location, isCurrent }) {
  return (
    <div className="relative pl-6 pb-6 last:pb-0">
      <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full border-2 border-[#7CB342] bg-white" />
      <div className="absolute left-[5px] top-4 bottom-0 w-0.5 bg-slate-200 last:hidden" />
      <div className="bg-slate-50 rounded-lg p-4 border border-slate-100">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-slate-900">{title}</p>
            {subtitle && <p className="text-sm text-slate-600 mt-0.5">{subtitle}</p>}
          </div>
          {isCurrent && <Badge className="bg-[#DCFCE7] text-[#7CB342] text-xs">Current</Badge>}
        </div>
        {duration && <p className="text-xs text-slate-400 mt-1">{duration}</p>}
        {location && <p className="text-xs text-slate-400 flex items-center gap-1"><MapPin className="w-3 h-3" />{location}</p>}
        {description && <p className="text-sm text-slate-600 mt-2">{description}</p>}
      </div>
    </div>
  );
}

export default function NaukriProfileView() {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reEnriching, setReEnriching] = useState(false);
  const [attachingCV, setAttachingCV] = useState(false);
  const cvInputRef = { current: null };
  const [notes, setNotes] = useState([]);
  const [newNote, setNewNote] = useState('');
  const [addingNote, setAddingNote] = useState(false);

  const loadProfile = useCallback(async () => {
    try {
      const res = await extensionAPI.getProfile(candidateId);
      if (res.data) {
        setProfile(res.data);
      } else {
        setProfile(null);
      }
    } catch (error) {
      // Don't let 401 interceptor redirect — handle gracefully
      if (error.response?.status !== 401) {
        toast.error('Failed to load profile');
      }
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, [candidateId]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  // Auto-enrich: if profile loads with missing critical fields, trigger re-enrichment silently
  useEffect(() => {
    if (!profile || reEnriching) return;
    const missingCritical = !profile.location && !profile.current_employer && !profile.designation;
    const hasRawText = profile.raw_profile_text || profile.raw_text_for_enrichment || profile.raw_page_text;
    const isStale = profile.ai_enrichment_source === 'spacy_only' || profile.ai_enrichment_source === 'regex_only';
    if ((missingCritical || isStale) && hasRawText !== false) {
      setReEnriching(true);
      extensionAPI.reEnrich(profile.id)
        .then((res) => {
          const count = res.data?.fields_updated?.length || 0;
          if (count > 0) {
            toast.success(`Auto-enriched profile: ${count} fields updated`);
            loadProfile();
          }
        })
        .catch(() => {})
        .finally(() => setReEnriching(false));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.id]);

  // Notes
  const loadNotes = async () => {
    try {
      const res = await candidateBankAPI.getNotes(candidateId);
      setNotes(res.data || []);
    } catch { /* silent */ }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (candidateId) loadNotes(); }, [candidateId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" data-testid="profile-loading">
        <div className="animate-spin w-8 h-8 border-2 border-[#7CB342] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="text-center py-20" data-testid="profile-not-found">
        <p className="text-slate-500 mb-4">Profile not found or could not be loaded.</p>
        <Button variant="outline" onClick={() => navigate(-1)}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Go Back
        </Button>
      </div>
    );
  }

  const downloadAtsCv = () => {
    const token = localStorage.getItem('vhc_token');
    const atsUrl = candidateBankAPI.getAtsCvUrl(profile.id);
    const link = document.createElement('a');
    link.href = `${atsUrl}?token=${token}`;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const downloadResume = () => {
    if (!profile.resume_url && !profile.active_resume_id) {
      toast.error('No resume uploaded for this candidate');
      return;
    }
    const token = localStorage.getItem('vhc_token');
    const url = candidateBankAPI.getResumeDownloadUrl(profile.id);
    const link = document.createElement('a');
    link.href = `${url}?token=${token}`;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleAttachCV = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'doc', 'docx'].includes(ext)) {
      toast.error('Please upload a PDF, DOC, or DOCX file');
      return;
    }
    setAttachingCV(true);
    try {
      const res = await bulkImportAPI.attachCV(profile.id, file);
      toast.success(res.data.message || 'CV attached successfully');
      loadProfile();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to attach CV');
    } finally {
      setAttachingCV(false);
      if (e.target) e.target.value = '';
    }
  };

  const handleAddNote = async () => {
    if (!newNote.trim()) return;
    setAddingNote(true);
    try {
      await candidateBankAPI.addNote(candidateId, newNote.trim());
      setNewNote('');
      loadNotes();
      toast.success('Note added');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add note');
    } finally {
      setAddingNote(false);
    }
  };

  const handleDeleteNote = async (noteId) => {
    try {
      await candidateBankAPI.deleteNote(candidateId, noteId);
      loadNotes();
      toast.success('Note deleted');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Cannot delete this note');
    }
  };

  // Safe accessors for nested data
  const p = {
    ...profile,
    experience: profile.experience || [],
    education: profile.education || [],
    skills: profile.skills || [],
    it_skills: profile.it_skills || [],
    certifications_detailed: profile.certifications_detailed || [],
    languages: profile.languages || [],
    projects: profile.projects || [],
    online_profiles: profile.online_profiles || [],
    preferred_locations: profile.preferred_locations || [],
    preferred_industry: profile.preferred_industry || [],
    preferred_functional_area: profile.preferred_functional_area || [],
    preferred_role: profile.preferred_role || [],
    preferred_job_type: profile.preferred_job_type || [],
    preferred_employment_type: profile.preferred_employment_type || [],
    preferred_shift: profile.preferred_shift || [],
    source_details: profile.source_details || {},
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto" data-testid="naukri-profile-view">
      {/* Back button */}
      <Button variant="ghost" onClick={() => navigate(-1)} className="text-slate-600 hover:text-slate-800 -ml-2" data-testid="back-button">
        <ArrowLeft className="w-4 h-4 mr-1" /> Back to Candidate Bank
      </Button>

      {/* Profile Header */}
      <Card className="border-slate-200 overflow-hidden">
        <div className="bg-gradient-to-r from-slate-800 to-slate-700 px-6 py-5">
          <div className="flex items-center gap-4">
            {p.photo_url ? (
              <img src={p.photo_url} alt={p.name} className="w-16 h-16 rounded-full border-2 border-white object-cover" />
            ) : (
              <div className="w-16 h-16 rounded-full bg-[#7CB342] flex items-center justify-center border-2 border-white">
                <span className="text-white font-bold text-2xl">{(p.name || '?').charAt(0).toUpperCase()}</span>
              </div>
            )}
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-heading font-bold text-white truncate" data-testid="profile-name">{p.name || 'Unknown'}</h1>
              <p className="text-slate-300 text-sm truncate">{p.designation || p.headline || ''}</p>
              {p.current_employer && (
                <p className="text-slate-400 text-sm flex items-center gap-1 mt-0.5">
                  <Building2 className="w-3 h-3" /> {p.current_employer}
                </p>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              <div className="flex items-center gap-2">
                {(profile.resume_url || profile.active_resume_id) && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={downloadResume}
                    className="text-[#7CB342] border-[#7CB342] hover:bg-green-50 h-7 text-xs"
                    data-testid="profile-download-cv-btn"
                  >
                    <Download className="w-3 h-3 mr-1" /> Download CV
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={downloadAtsCv}
                  className="text-blue-600 border-blue-400 hover:bg-blue-50 h-7 text-xs"
                  data-testid="profile-ats-cv-btn"
                >
                  <FileText className="w-3 h-3 mr-1" /> Resume (.tex)
                </Button>
                <label className="inline-flex">
                  <input type="file" accept=".pdf,.doc,.docx" className="hidden" onChange={handleAttachCV} disabled={attachingCV} />
                  <Button
                    variant="outline"
                    size="sm"
                    asChild
                    className="text-purple-600 border-purple-400 hover:bg-purple-50 h-7 text-xs cursor-pointer"
                    data-testid="profile-attach-cv-btn"
                  >
                    <span>
                      {attachingCV ? <RefreshCw className="w-3 h-3 mr-1 animate-spin" /> : <Paperclip className="w-3 h-3 mr-1" />}
                      {attachingCV ? 'Uploading...' : 'Attach CV'}
                    </span>
                  </Button>
                </label>
                {reEnriching && (
                  <span className="flex items-center gap-1.5 text-xs text-amber-600" data-testid="profile-auto-enriching">
                    <RefreshCw className="w-3 h-3 animate-spin" /> Enriching profile...
                  </span>
                )}
              </div>
              <Badge className="bg-[#7CB342] text-white text-xs">
                {p.source === 'cv_upload' ? 'CV Upload' : 'Naukri Sourced'}
              </Badge>
              {p.naukri_profile_url && (
                <a href={p.naukri_profile_url} target="_blank" rel="noopener noreferrer" className="text-xs text-slate-400 hover:text-white flex items-center gap-1">
                  View on Naukri <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Quick info bar */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-slate-100">
          {[
            { icon: Mail, label: p.email || 'Hidden on Naukri', muted: !p.email },
            { icon: Phone, label: p.phone || 'Hidden on Naukri', muted: !p.phone },
            { icon: MapPin, label: p.location || p.preferred_locations[0] || 'N/A' },
            { icon: Clock, label: p.experience_years ? `${p.experience_years} yrs exp` : 'N/A' },
            { icon: Briefcase, label: p.notice_period || 'N/A' },
          ].map((item, i) => (
            <div key={item.label} className="bg-white px-4 py-2.5 flex items-center gap-2 text-sm">
              <item.icon className="w-4 h-4 text-slate-400 flex-shrink-0" />
              <span className={`truncate ${item.muted ? 'text-slate-400 italic' : 'text-slate-700'}`}>{item.label}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Main content tabs */}
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="mb-4 bg-slate-100">
          <TabsTrigger value="overview" data-testid="tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="experience" data-testid="tab-experience">Experience</TabsTrigger>
          <TabsTrigger value="education" data-testid="tab-education">Education</TabsTrigger>
          <TabsTrigger value="skills" data-testid="tab-skills">Skills</TabsTrigger>
          <TabsTrigger value="personal" data-testid="tab-personal">Personal</TabsTrigger>
          <TabsTrigger value="preferences" data-testid="tab-preferences">Preferences</TabsTrigger>
          <TabsTrigger value="timeline" data-testid="tab-timeline">Timeline</TabsTrigger>
          <TabsTrigger value="notes" data-testid="tab-notes">Notes ({notes.length})</TabsTrigger>
        </TabsList>

        {/* OVERVIEW TAB */}
        <TabsContent value="overview">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              {p.summary && (
                <Section title="Profile Summary" icon={User} testId="section-summary">
                  <p className="text-sm text-slate-600 leading-relaxed">{p.summary}</p>
                </Section>
              )}
              {p.skills.length > 0 && (
                <Section title="Key Skills" testId="section-skills">
                  <div className="flex flex-wrap gap-1.5">
                    {p.skills.map((skill, i) => (
                      <Badge key={`skill-${skill}-${i}`} variant="secondary" className="bg-[#DCFCE7] text-[#558B2F] text-xs px-2.5 py-1">{skill}</Badge>
                    ))}
                  </div>
                </Section>
              )}
              {p.experience.length > 0 && (
                <Section title="Recent Experience" icon={Briefcase} testId="section-recent-exp">
                  {p.experience.slice(0, 3).map((exp, i) => (
                    <TimelineCard key={`exp-${exp.company}-${i}`} title={exp.designation || exp.title || 'Role'} subtitle={exp.company} duration={exp.duration || `${exp.from_date || ''} - ${exp.to_date || 'Present'}`} location={exp.location} description={exp.description} isCurrent={exp.is_current} />
                  ))}
                  {p.experience.length > 3 && <p className="text-xs text-slate-400 pl-6">+{p.experience.length - 3} more positions</p>}
                </Section>
              )}
            </div>
            <div className="space-y-4">
              <Card className="border-slate-200">
                <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-700">Compensation</CardTitle></CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <InfoRow label="Current CTC" value={p.current_salary ? formatSalaryINR(p.current_salary) : null} />
                  <InfoRow label="Expected CTC" value={p.expected_salary ? formatSalaryINR(p.expected_salary) : null} />
                  <InfoRow label="Notice Period" value={p.notice_period} />
                </CardContent>
              </Card>
              {(p.highest_qualification || p.education.length > 0) && (
                <Card className="border-slate-200">
                  <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-700">Education</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {p.highest_qualification && <InfoRow label="Highest" value={p.highest_qualification} />}
                    {p.education.slice(0, 2).map((edu, i) => (
                      <div key={`edu-side-${edu.degree}-${i}`} className="py-1 border-t border-slate-50 first:border-0">
                        <p className="font-medium text-slate-800">{edu.degree}</p>
                        {edu.institution && <p className="text-slate-500 text-xs">{edu.institution}</p>}
                        {edu.year_of_passing && <p className="text-slate-400 text-xs">{edu.year_of_passing}</p>}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
              <Card className="border-slate-200">
                <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-700">Source Details</CardTitle></CardHeader>
                <CardContent className="space-y-1 text-xs text-slate-500">
                  <p>Captured by: {p.source_details.captured_by_name || 'N/A'}</p>
                  <p>Captured at: {p.source_details.captured_at ? new Date(p.source_details.captured_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : 'N/A'}</p>
                  <p>Extension v{p.source_details.extension_version || '2.0.0'}</p>
                  {p.naukri_profile_updated && <p>Naukri Updated: {p.naukri_profile_updated}</p>}
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        {/* EXPERIENCE TAB */}
        <TabsContent value="experience">
          <Section title="Work Experience" icon={Briefcase} testId="section-work-experience">
            {p.experience.length > 0 ? (
              p.experience.map((exp, i) => (
                <TimelineCard key={`exp-${exp.company}-${i}`} title={exp.designation || exp.title || 'Role'} subtitle={exp.company} duration={exp.duration || `${exp.from_date || ''} - ${exp.to_date || 'Present'}`} location={exp.location} description={exp.description} isCurrent={exp.is_current} />
              ))
            ) : (
              <p className="text-slate-400 text-sm text-center py-8">No work experience data captured</p>
            )}
          </Section>
        </TabsContent>

        {/* EDUCATION TAB */}
        <TabsContent value="education">
          <Section title="Education" icon={GraduationCap} testId="section-education">
            {p.education.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {p.education.map((edu, i) => (
                  <Card key={`edu-${edu.degree}-${i}`} className="border-slate-200">
                    <CardContent className="p-4">
                      <p className="font-semibold text-slate-900">{edu.degree || 'Degree'}</p>
                      {edu.specialization && <p className="text-sm text-[#7CB342]">{edu.specialization}</p>}
                      {edu.institution && <p className="text-sm text-slate-600 mt-1">{edu.institution}</p>}
                      {edu.university && <p className="text-xs text-slate-400">{edu.university}</p>}
                      <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                        {edu.year_of_passing && <span>{edu.year_of_passing}</span>}
                        {edu.score && <span>Score: {edu.score}</span>}
                        {edu.degree_type && <Badge variant="outline" className="text-xs">{edu.degree_type}</Badge>}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : (
              <p className="text-slate-400 text-sm text-center py-8">No education data captured</p>
            )}
            {p.certifications_detailed.length > 0 && (
              <Section title="Certifications" icon={Award} testId="section-certifications">
                <div className="space-y-2">
                  {p.certifications_detailed.map((cert, i) => (
                    <div key={`cert-${cert.name}-${i}`} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                      <Award className="w-5 h-5 text-amber-500 flex-shrink-0" />
                      <div>
                        <p className="font-medium text-sm text-slate-800">{cert.name}</p>
                        {cert.issuing_authority && <p className="text-xs text-slate-500">{cert.issuing_authority}</p>}
                        {cert.issue_date && <p className="text-xs text-slate-400">{cert.issue_date}</p>}
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </Section>
        </TabsContent>

        {/* SKILLS TAB */}
        <TabsContent value="skills">
          {p.skills.length > 0 && (
            <Section title="Key Skills" testId="section-key-skills">
              <div className="flex flex-wrap gap-2">
                {p.skills.map((skill, i) => (
                  <Badge key={`skill-${skill}-${i}`} variant="secondary" className="bg-[#DCFCE7] text-[#558B2F] px-3 py-1.5">{skill}</Badge>
                ))}
              </div>
            </Section>
          )}
          {p.it_skills.length > 0 && (
            <Section title="IT / Technical Skills" testId="section-it-skills">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="bg-slate-50 text-left">
                    <th className="px-4 py-2 font-medium text-slate-600">Skill</th>
                    <th className="px-4 py-2 font-medium text-slate-600">Version</th>
                    <th className="px-4 py-2 font-medium text-slate-600">Last Used</th>
                    <th className="px-4 py-2 font-medium text-slate-600">Experience</th>
                  </tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {p.it_skills.map((skill, i) => (
                      <tr key={`skill-${skill.name}-${i}`} className="hover:bg-slate-50">
                        <td className="px-4 py-2 font-medium text-slate-800">{skill.name}</td>
                        <td className="px-4 py-2 text-slate-600">{skill.version || '-'}</td>
                        <td className="px-4 py-2 text-slate-600">{skill.last_used || '-'}</td>
                        <td className="px-4 py-2 text-slate-600">{skill.experience_years ? `${skill.experience_years} yrs` : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}
          {p.languages.length > 0 && (
            <Section title="Languages" icon={Languages} testId="section-languages">
              <div className="flex flex-wrap gap-2">
                {p.languages.map((lang, i) => (
                  <div key={`lang-${lang.language}-${i}`} className="px-3 py-2 bg-slate-50 rounded-lg border border-slate-100 text-sm">
                    <span className="font-medium text-slate-800">{lang.language}</span>
                    {lang.proficiency && <span className="text-slate-400 ml-1">({lang.proficiency})</span>}
                  </div>
                ))}
              </div>
            </Section>
          )}
          {p.projects.length > 0 && (
            <Section title="Projects" icon={FolderOpen} testId="section-projects">
              <div className="space-y-3">
                {p.projects.map((proj, i) => (
                  <Card key={`proj-${proj.title}-${i}`} className="border-slate-200">
                    <CardContent className="p-4">
                      <p className="font-semibold text-slate-900">{proj.title}</p>
                      {proj.role && <p className="text-sm text-[#7CB342]">Role: {proj.role}</p>}
                      {proj.client && <p className="text-xs text-slate-500">Client: {proj.client}</p>}
                      {proj.description && <p className="text-sm text-slate-600 mt-2">{proj.description}</p>}
                      {proj.status && <Badge variant="outline" className="mt-2 text-xs">{proj.status}</Badge>}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </Section>
          )}
          {p.skills.length === 0 && p.it_skills.length === 0 && (
            <p className="text-slate-400 text-sm text-center py-8">No skills data captured</p>
          )}
        </TabsContent>

        {/* PERSONAL TAB */}
        <TabsContent value="personal">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Section title="Personal Details" icon={User} testId="section-personal-details">
              <div className="space-y-1">
                <InfoRow label="Date of Birth" value={p.date_of_birth} icon={Calendar} />
                <InfoRow label="Age" value={p.age} />
                <InfoRow label="Gender" value={p.gender} />
                <InfoRow label="Marital Status" value={p.marital_status} />
                <InfoRow label="Nationality" value={p.nationality} />
                <InfoRow label="Category" value={p.category} />
                <InfoRow label="Passport" value={p.has_passport ? `Yes${p.passport_number ? ` (${p.passport_number})` : ''}` : null} />
                {p.differently_abled && <InfoRow label="Differently Abled" value="Yes" />}
              </div>
            </Section>
            <Section title="Address" icon={MapPin} testId="section-address">
              <div className="space-y-3">
                {(p.current_address || p.current_city) ? (
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Current Address</p>
                    <p className="text-sm text-slate-700">{[p.current_address, p.current_city, p.current_state, p.current_country, p.current_pincode].filter(Boolean).join(', ')}</p>
                  </div>
                ) : null}
                {(p.permanent_address || p.permanent_city) ? (
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Permanent Address</p>
                    <p className="text-sm text-slate-700">{[p.permanent_address, p.permanent_city, p.permanent_state, p.permanent_country, p.permanent_pincode].filter(Boolean).join(', ')}</p>
                  </div>
                ) : null}
                {!p.current_address && !p.current_city && !p.permanent_address && !p.permanent_city && (
                  <p className="text-slate-400 text-sm">No address data captured</p>
                )}
              </div>
            </Section>
            {p.online_profiles.length > 0 && (
              <Section title="Online Profiles" icon={Globe} testId="section-online-profiles">
                <div className="space-y-2">
                  {p.online_profiles.map((op, i) => (
                    <a key={op.url || `op-${i}`} href={op.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 p-2 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                      <Globe className="w-4 h-4 text-[#7CB342]" />
                      <span className="font-medium text-slate-700">{op.platform}</span>
                      <ExternalLink className="w-3 h-3 text-slate-400 ml-auto" />
                    </a>
                  ))}
                </div>
              </Section>
            )}
          </div>
        </TabsContent>

        {/* PREFERENCES TAB */}
        <TabsContent value="preferences">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Section title="Salary & Notice" testId="section-salary-notice">
              <div className="space-y-1">
                <InfoRow label="Current CTC" value={p.current_salary ? formatSalaryINR(p.current_salary) : null} />
                <InfoRow label="Expected CTC" value={p.expected_salary ? formatSalaryINR(p.expected_salary) : null} />
                <InfoRow label="Notice Period" value={p.notice_period} />
                {p.is_serving_notice && <InfoRow label="Serving Notice" value="Yes" />}
                {p.last_working_day && <InfoRow label="Last Working Day" value={p.last_working_day} />}
                {p.notice_negotiable && <InfoRow label="Negotiable" value="Yes" />}
              </div>
            </Section>
            <Section title="Location Preferences" testId="section-location-prefs">
              <div className="space-y-1">
                <InfoRow label="Current Location" value={p.location} icon={MapPin} />
                {p.preferred_locations.length > 0 && (
                  <div className="py-1.5">
                    <p className="text-sm text-slate-500 mb-1">Preferred Locations</p>
                    <div className="flex flex-wrap gap-1">{p.preferred_locations.map((loc, i) => (<Badge key={`loc-${loc}`} variant="outline" className="text-xs">{loc}</Badge>))}</div>
                  </div>
                )}
                {p.willing_to_relocate && <InfoRow label="Willing to Relocate" value="Yes" />}
              </div>
            </Section>
            <Section title="Industry & Role" testId="section-industry-role">
              <div className="space-y-1">
                <InfoRow label="Industry" value={p.industry} />
                {p.preferred_industry.length > 0 && (
                  <div className="py-1.5">
                    <p className="text-sm text-slate-500 mb-1">Preferred Industry</p>
                    <div className="flex flex-wrap gap-1">{p.preferred_industry.map((ind, i) => (<Badge key={`ind-${ind}`} variant="outline" className="text-xs">{ind}</Badge>))}</div>
                  </div>
                )}
                {p.preferred_functional_area.length > 0 && (
                  <div className="py-1.5">
                    <p className="text-sm text-slate-500 mb-1">Functional Area</p>
                    <div className="flex flex-wrap gap-1">{p.preferred_functional_area.map((fa, i) => (<Badge key={`fa-${fa}`} variant="outline" className="text-xs">{fa}</Badge>))}</div>
                  </div>
                )}
                {p.preferred_role.length > 0 && (
                  <div className="py-1.5">
                    <p className="text-sm text-slate-500 mb-1">Preferred Role</p>
                    <div className="flex flex-wrap gap-1">{p.preferred_role.map((r, i) => (<Badge key={`role-${r}`} variant="outline" className="text-xs">{r}</Badge>))}</div>
                  </div>
                )}
              </div>
            </Section>
            <Section title="Job Type Preferences" testId="section-job-type-prefs">
              <div className="space-y-1">
                {p.preferred_job_type.length > 0 && <InfoRow label="Job Type" value={p.preferred_job_type.join(', ')} />}
                {p.preferred_employment_type.length > 0 && <InfoRow label="Employment" value={p.preferred_employment_type.join(', ')} />}
                {p.preferred_shift.length > 0 && <InfoRow label="Shift" value={p.preferred_shift.join(', ')} />}
                {p.work_from_home && <InfoRow label="WFH" value="Preferred" />}
                {p.remote_work_preference && <InfoRow label="Remote" value={p.remote_work_preference} />}
              </div>
            </Section>
          </div>
        </TabsContent>

        <TabsContent value="timeline">
          <Card className="bg-zinc-950 border-zinc-800">
            <CardHeader>
              <CardTitle className="text-zinc-100 text-base">Activity Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <CandidateActivityTimeline candidateId={candidateId} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notes">
          <Card className="border-slate-200">
            <CardContent className="p-4 space-y-4">
              {/* Add Note */}
              <div className="space-y-2">
                <Textarea
                  value={newNote}
                  onChange={(e) => setNewNote(e.target.value)}
                  placeholder="Add a note about this candidate... (e.g., Called — interested, needs 2 weeks to decide)"
                  rows={3}
                  className="resize-none"
                  data-testid="note-input"
                />
                <div className="flex justify-end">
                  <Button size="sm" onClick={handleAddNote} disabled={addingNote || !newNote.trim()} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="add-note-btn">
                    {addingNote ? 'Saving...' : 'Add Note'}
                  </Button>
                </div>
              </div>
              {/* Notes List */}
              {notes.length === 0 && (
                <p className="text-slate-400 text-sm text-center py-6">No notes yet. Add the first note above.</p>
              )}
              <div className="space-y-3">
                {notes.map((n) => (
                  <div key={n.id} className="p-3 bg-slate-50 rounded-lg border border-slate-100" data-testid={`note-${n.id}`}>
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-slate-800 whitespace-pre-wrap flex-1">{n.text}</p>
                      <button onClick={() => handleDeleteNote(n.id)} className="text-slate-300 hover:text-red-500 shrink-0" title="Delete note">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <div className="flex items-center gap-2 mt-2 text-[11px] text-slate-400">
                      <span className="font-medium text-slate-500">{n.created_by_name}</span>
                      <span>{n.created_by_role}</span>
                      <span>{new Date(n.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
