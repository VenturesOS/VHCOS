import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../lib/auth';
import { resumeAPI, candidateBankAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { toast } from 'sonner';
import {
  FileText, Download, Copy, Sparkles, Plus, X, ChevronDown,
  Briefcase, GraduationCap, Code, User, Loader2, Check, Search
} from 'lucide-react';

const TEMPLATES = [
  { id: 'ats_clean', label: 'ATS Clean', desc: 'Minimal, ATS-optimized single column' },
  { id: 'google_style', label: 'Google Style', desc: 'Clean modern layout inspired by top tech' },
  { id: 'modern', label: 'Modern Pro', desc: 'Two-column skills, contemporary design' },
];

export default function ResumeBuilderPage() {
  const { user } = useAuth();
  const isCandidate = user?.role === 'candidate';

  const [profile, setProfile] = useState({
    name: '', email: '', phone: '', location: '', linkedin: '', summary: '',
    skills: [], experience: [], education: [],
  });
  const [selectedTemplate, setSelectedTemplate] = useState('ats_clean');
  const [latex, setLatex] = useState('');
  const [activeTab, setActiveTab] = useState('preview');
  const [aiEnhancing, setAiEnhancing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [newSkill, setNewSkill] = useState('');
  const [candidateSearch, setCandidateSearch] = useState('');
  const [candidates, setCandidates] = useState([]);
  const [searchingCandidates, setSearchingCandidates] = useState(false);
  const [selectedCandidateId, setSelectedCandidateId] = useState(null);

  // Load profile on mount
  useEffect(() => {
    if (isCandidate) {
      loadMyProfile();
    } else {
      setLoading(false);
    }
  }, [isCandidate]);

  const loadMyProfile = async () => {
    try {
      const res = await resumeAPI.getMyProfile();
      if (res.data) setProfile(prev => ({ ...prev, ...res.data }));
    } catch (e) {
      toast.error('Failed to load profile');
    } finally {
      setLoading(false);
    }
  };

  const searchCandidates = async () => {
    if (!candidateSearch.trim()) return;
    setSearchingCandidates(true);
    try {
      const res = await candidateBankAPI.getAll({ search: candidateSearch, limit: 10 });
      const list = res.data?.candidates || res.data || [];
      setCandidates(list);
    } catch (e) {
      toast.error('Search failed');
    } finally {
      setSearchingCandidates(false);
    }
  };

  const loadCandidateProfile = async (candidateId) => {
    setLoading(true);
    setSelectedCandidateId(candidateId);
    try {
      const res = await resumeAPI.getCandidateProfile(candidateId);
      if (res.data) setProfile(prev => ({ ...prev, ...res.data }));
      setLatex('');
      toast.success('Candidate profile loaded');
    } catch (e) {
      toast.error('Failed to load candidate profile');
    } finally {
      setLoading(false);
    }
  };

  const generateLatex = async () => {
    setGenerating(true);
    try {
      const res = await resumeAPI.generate(profile, selectedTemplate);
      setLatex(res.data.latex);
      setActiveTab('preview');
      toast.success('Resume generated!');
    } catch (e) {
      toast.error('Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleAiEnhance = async () => {
    if (!profile.experience.length) return toast.error('Add experience first');
    setAiEnhancing(true);
    try {
      const updatedExp = await Promise.all(
        profile.experience.map(async (exp) => {
          if (!exp.bullets?.length) return exp;
          const res = await resumeAPI.aiEnhance(exp.bullets);
          return { ...exp, bullets: res.data.bullets || exp.bullets };
        })
      );
      setProfile(prev => ({ ...prev, experience: updatedExp }));
      toast.success('Bullets enhanced with AI!');
      // Re-generate if latex exists
      if (latex) {
        const res = await resumeAPI.generate({ ...profile, experience: updatedExp }, selectedTemplate);
        setLatex(res.data.latex);
      }
    } catch (e) {
      toast.error('AI enhancement failed');
    } finally {
      setAiEnhancing(false);
    }
  };

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(latex);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success('LaTeX copied to clipboard');
  }, [latex]);

  const handleDownload = useCallback(() => {
    const blob = new Blob([latex], { type: 'application/x-tex' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${profile.name?.replace(/\s+/g, '_') || 'resume'}.tex`;
    a.click();
    URL.revokeObjectURL(url);
  }, [latex, profile.name]);

  // Profile field updaters
  const updateField = (field, value) => setProfile(prev => ({ ...prev, [field]: value }));

  const addSkill = () => {
    if (newSkill.trim() && !profile.skills.includes(newSkill.trim())) {
      setProfile(prev => ({ ...prev, skills: [...prev.skills, newSkill.trim()] }));
      setNewSkill('');
    }
  };

  const removeSkill = (idx) => {
    setProfile(prev => ({ ...prev, skills: prev.skills.filter((_, i) => i !== idx) }));
  };

  const addExperience = () => {
    setProfile(prev => ({
      ...prev,
      experience: [...prev.experience, { company: '', title: '', duration: '', bullets: [''] }],
    }));
  };

  const updateExperience = (idx, field, value) => {
    setProfile(prev => {
      const exp = [...prev.experience];
      exp[idx] = { ...exp[idx], [field]: value };
      return { ...prev, experience: exp };
    });
  };

  const updateBullet = (expIdx, bulletIdx, value) => {
    setProfile(prev => {
      const exp = [...prev.experience];
      const bullets = [...exp[expIdx].bullets];
      bullets[bulletIdx] = value;
      exp[expIdx] = { ...exp[expIdx], bullets };
      return { ...prev, experience: exp };
    });
  };

  const addBullet = (expIdx) => {
    setProfile(prev => {
      const exp = [...prev.experience];
      exp[expIdx] = { ...exp[expIdx], bullets: [...exp[expIdx].bullets, ''] };
      return { ...prev, experience: exp };
    });
  };

  const removeBullet = (expIdx, bulletIdx) => {
    setProfile(prev => {
      const exp = [...prev.experience];
      exp[expIdx] = { ...exp[expIdx], bullets: exp[expIdx].bullets.filter((_, i) => i !== bulletIdx) };
      return { ...prev, experience: exp };
    });
  };

  const removeExperience = (idx) => {
    setProfile(prev => ({ ...prev, experience: prev.experience.filter((_, i) => i !== idx) }));
  };

  const addEducation = () => {
    setProfile(prev => ({
      ...prev,
      education: [...prev.education, { institution: '', degree: '', year: '', gpa: '' }],
    }));
  };

  const updateEducation = (idx, field, value) => {
    setProfile(prev => {
      const edu = [...prev.education];
      edu[idx] = { ...edu[idx], [field]: value };
      return { ...prev, education: edu };
    });
  };

  const removeEducation = (idx) => {
    setProfile(prev => ({ ...prev, education: prev.education.filter((_, i) => i !== idx) }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="resume-builder-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-bold text-slate-900">Resume Builder</h1>
          <p className="text-slate-500 text-sm mt-1">Generate a professional LaTeX resume</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button
            onClick={handleAiEnhance}
            disabled={aiEnhancing || !profile.experience.length}
            variant="outline"
            className="border-purple-300 text-purple-700 hover:bg-purple-50"
            data-testid="ai-enhance-btn"
          >
            {aiEnhancing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
            AI Enhance
          </Button>
          <Button
            onClick={generateLatex}
            disabled={generating || !profile.name}
            className="bg-[#7CB342] hover:bg-[#689F38]"
            data-testid="generate-resume-btn"
          >
            {generating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <FileText className="w-4 h-4 mr-2" />}
            Generate Resume
          </Button>
        </div>
      </div>

      {/* Candidate Search (for employer/recruiter/admin) */}
      {!isCandidate && (
        <Card className="border-slate-200" data-testid="candidate-search-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold">Select Candidate from Bank</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Input
                placeholder="Search by name, email, or skill..."
                value={candidateSearch}
                onChange={(e) => setCandidateSearch(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && searchCandidates()}
                data-testid="candidate-search-input"
                className="flex-1"
              />
              <Button onClick={searchCandidates} disabled={searchingCandidates} variant="outline" data-testid="search-candidates-btn">
                {searchingCandidates ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              </Button>
            </div>
            {candidates.length > 0 && (
              <div className="mt-3 max-h-48 overflow-y-auto border rounded-lg divide-y">
                {candidates.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => loadCandidateProfile(c.id)}
                    className={`w-full text-left px-3 py-2 hover:bg-slate-50 transition-colors text-sm ${
                      selectedCandidateId === c.id ? 'bg-green-50 border-l-2 border-[#7CB342]' : ''
                    }`}
                    data-testid={`candidate-option-${c.id}`}
                  >
                    <span className="font-medium text-slate-900">{c.name}</span>
                    <span className="text-slate-400 ml-2">{c.email}</span>
                    {c.skills?.length > 0 && (
                      <div className="text-xs text-slate-400 mt-0.5">{c.skills.slice(0, 5).join(', ')}</div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Profile Editor */}
        <div className="lg:col-span-1 space-y-4">
          {/* Template Selection */}
          <Card className="border-slate-200">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <FileText className="w-4 h-4 text-[#7CB342]" /> Template
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {TEMPLATES.map(t => (
                <button
                  key={t.id}
                  onClick={() => setSelectedTemplate(t.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-all ${
                    selectedTemplate === t.id
                      ? 'border-[#7CB342] bg-green-50 text-green-800'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                  data-testid={`template-${t.id}`}
                >
                  <div className="font-medium">{t.label}</div>
                  <div className="text-xs text-slate-500">{t.desc}</div>
                </button>
              ))}
            </CardContent>
          </Card>

          {/* Personal Info */}
          <Card className="border-slate-200">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <User className="w-4 h-4 text-[#7CB342]" /> Personal Info
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label className="text-xs text-slate-500">Full Name</Label>
                <Input value={profile.name} onChange={(e) => updateField('name', e.target.value)} data-testid="profile-name" />
              </div>
              <div>
                <Label className="text-xs text-slate-500">Email</Label>
                <Input value={profile.email} onChange={(e) => updateField('email', e.target.value)} data-testid="profile-email" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs text-slate-500">Phone</Label>
                  <Input value={profile.phone} onChange={(e) => updateField('phone', e.target.value)} data-testid="profile-phone" />
                </div>
                <div>
                  <Label className="text-xs text-slate-500">Location</Label>
                  <Input value={profile.location} onChange={(e) => updateField('location', e.target.value)} data-testid="profile-location" />
                </div>
              </div>
              <div>
                <Label className="text-xs text-slate-500">LinkedIn URL</Label>
                <Input value={profile.linkedin} onChange={(e) => updateField('linkedin', e.target.value)} placeholder="https://linkedin.com/in/..." data-testid="profile-linkedin" />
              </div>
              <div>
                <Label className="text-xs text-slate-500">Professional Summary</Label>
                <Textarea value={profile.summary} onChange={(e) => updateField('summary', e.target.value)} rows={3} data-testid="profile-summary" />
              </div>
            </CardContent>
          </Card>

          {/* Skills */}
          <Card className="border-slate-200">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Code className="w-4 h-4 text-[#7CB342]" /> Skills
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2 mb-3">
                <Input
                  value={newSkill}
                  onChange={(e) => setNewSkill(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addSkill())}
                  placeholder="Add a skill"
                  className="flex-1"
                  data-testid="add-skill-input"
                />
                <Button onClick={addSkill} size="sm" variant="outline" data-testid="add-skill-btn">
                  <Plus className="w-4 h-4" />
                </Button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {profile.skills.map((skill, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-xs text-slate-700"
                  >
                    {skill}
                    <button onClick={() => removeSkill(idx)} className="hover:text-red-500">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right: Experience + Education + Output */}
        <div className="lg:col-span-2 space-y-4">
          {/* Experience */}
          <Card className="border-slate-200">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Briefcase className="w-4 h-4 text-[#7CB342]" /> Experience
              </CardTitle>
              <Button onClick={addExperience} size="sm" variant="outline" data-testid="add-experience-btn">
                <Plus className="w-4 h-4 mr-1" /> Add
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {profile.experience.map((exp, expIdx) => (
                <div key={expIdx} className="border rounded-lg p-3 space-y-2 relative bg-slate-50/50">
                  <button
                    onClick={() => removeExperience(expIdx)}
                    className="absolute top-2 right-2 text-slate-400 hover:text-red-500"
                    data-testid={`remove-exp-${expIdx}`}
                  >
                    <X className="w-4 h-4" />
                  </button>
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      value={exp.title}
                      onChange={(e) => updateExperience(expIdx, 'title', e.target.value)}
                      placeholder="Job Title"
                      className="text-sm"
                    />
                    <Input
                      value={exp.company}
                      onChange={(e) => updateExperience(expIdx, 'company', e.target.value)}
                      placeholder="Company"
                      className="text-sm"
                    />
                  </div>
                  <Input
                    value={exp.duration}
                    onChange={(e) => updateExperience(expIdx, 'duration', e.target.value)}
                    placeholder="Duration (e.g., Jan 2022 - Present)"
                    className="text-sm"
                  />
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-500">Bullet Points</Label>
                    {exp.bullets.map((bullet, bIdx) => (
                      <div key={bIdx} className="flex gap-1.5">
                        <Input
                          value={bullet}
                          onChange={(e) => updateBullet(expIdx, bIdx, e.target.value)}
                          placeholder="Describe your achievement..."
                          className="flex-1 text-sm"
                        />
                        <button onClick={() => removeBullet(expIdx, bIdx)} className="text-slate-400 hover:text-red-500 shrink-0">
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                    <button
                      onClick={() => addBullet(expIdx)}
                      className="text-xs text-[#7CB342] hover:text-[#689F38] flex items-center gap-1"
                    >
                      <Plus className="w-3 h-3" /> Add bullet
                    </button>
                  </div>
                </div>
              ))}
              {!profile.experience.length && (
                <p className="text-sm text-slate-400 text-center py-4">No experience added yet</p>
              )}
            </CardContent>
          </Card>

          {/* Education */}
          <Card className="border-slate-200">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <GraduationCap className="w-4 h-4 text-[#7CB342]" /> Education
              </CardTitle>
              <Button onClick={addEducation} size="sm" variant="outline" data-testid="add-education-btn">
                <Plus className="w-4 h-4 mr-1" /> Add
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {profile.education.map((edu, idx) => (
                <div key={idx} className="border rounded-lg p-3 space-y-2 relative bg-slate-50/50">
                  <button
                    onClick={() => removeEducation(idx)}
                    className="absolute top-2 right-2 text-slate-400 hover:text-red-500"
                    data-testid={`remove-edu-${idx}`}
                  >
                    <X className="w-4 h-4" />
                  </button>
                  <Input
                    value={edu.institution}
                    onChange={(e) => updateEducation(idx, 'institution', e.target.value)}
                    placeholder="University / Institution"
                    className="text-sm"
                  />
                  <div className="grid grid-cols-3 gap-2">
                    <Input
                      value={edu.degree}
                      onChange={(e) => updateEducation(idx, 'degree', e.target.value)}
                      placeholder="Degree"
                      className="text-sm col-span-1"
                    />
                    <Input
                      value={edu.year}
                      onChange={(e) => updateEducation(idx, 'year', e.target.value)}
                      placeholder="Year"
                      className="text-sm"
                    />
                    <Input
                      value={edu.gpa || ''}
                      onChange={(e) => updateEducation(idx, 'gpa', e.target.value)}
                      placeholder="GPA (optional)"
                      className="text-sm"
                    />
                  </div>
                </div>
              ))}
              {!profile.education.length && (
                <p className="text-sm text-slate-400 text-center py-4">No education added yet</p>
              )}
            </CardContent>
          </Card>

          {/* Output: Preview / LaTeX */}
          {latex && (
            <Card className="border-slate-200" data-testid="resume-output-card">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className="flex gap-1 bg-slate-100 rounded-lg p-0.5">
                    <button
                      onClick={() => setActiveTab('preview')}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                        activeTab === 'preview' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                      }`}
                      data-testid="tab-preview"
                    >
                      Preview
                    </button>
                    <button
                      onClick={() => setActiveTab('latex')}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                        activeTab === 'latex' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                      }`}
                      data-testid="tab-latex"
                    >
                      LaTeX Code
                    </button>
                  </div>
                  <div className="flex gap-2">
                    <Button onClick={handleCopy} size="sm" variant="outline" data-testid="copy-latex-btn">
                      {copied ? <Check className="w-4 h-4 mr-1 text-green-600" /> : <Copy className="w-4 h-4 mr-1" />}
                      {copied ? 'Copied' : 'Copy'}
                    </Button>
                    <Button onClick={handleDownload} size="sm" variant="outline" data-testid="download-tex-btn">
                      <Download className="w-4 h-4 mr-1" /> .tex
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {activeTab === 'preview' ? (
                  <ResumePreview profile={profile} template={selectedTemplate} />
                ) : (
                  <div className="relative">
                    <pre className="bg-slate-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto max-h-[600px] overflow-y-auto font-mono">
                      {latex}
                    </pre>
                    <p className="text-xs text-slate-400 mt-2">
                      Compile with: pdflatex resume.tex or paste into <a href="https://www.overleaf.com" target="_blank" rel="noreferrer" className="text-[#7CB342] underline">Overleaf</a>
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Visual Preview Component ───────────────────────────────
function ResumePreview({ profile: p, template: tpl }) {
  const isModern = tpl === 'modern';
  const isGoogle = tpl === 'google_style';

  return (
    <div
      className="bg-white border rounded-lg shadow-inner p-8 max-h-[600px] overflow-y-auto"
      style={{ fontFamily: 'Georgia, "Times New Roman", serif', fontSize: '13px', lineHeight: '1.5', color: '#1a1a1a' }}
      data-testid="resume-preview"
    >
      {/* Header */}
      <div className={isModern ? 'text-center' : ''}>
        <h1 style={{
          fontSize: tpl === 'ats_clean' ? '18px' : '22px',
          fontWeight: 700,
          letterSpacing: tpl === 'ats_clean' ? '2px' : '0',
          textTransform: tpl === 'ats_clean' ? 'uppercase' : 'none',
          marginBottom: '4px',
        }}>
          {p.name || 'Your Name'}
        </h1>
        <p style={{ fontSize: '11px', color: '#666' }}>
          {[p.phone, p.email, p.location, p.linkedin].filter(Boolean).join(' | ')}
        </p>
      </div>

      <hr style={{ margin: '10px 0', borderColor: '#ccc' }} />

      {/* Summary */}
      {p.summary && (
        <>
          <h2 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '4px', color: '#333' }}>
            {isModern ? 'Professional Summary' : 'Summary'}
          </h2>
          <p style={{ fontSize: '12px', color: '#444', marginBottom: '12px' }}>{p.summary}</p>
        </>
      )}

      {/* Experience */}
      {p.experience?.length > 0 && (
        <>
          <h2 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '6px', color: '#333', borderBottom: '1px solid #ddd', paddingBottom: '2px' }}>
            Experience
          </h2>
          {p.experience.map((exp, i) => (
            <div key={i} style={{ marginBottom: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <strong style={{ fontSize: '12px' }}>{exp.title}</strong>
                <span style={{ fontSize: '11px', color: '#888' }}>{exp.duration}</span>
              </div>
              <div style={{ fontSize: '12px', fontStyle: 'italic', color: '#555' }}>{exp.company}</div>
              {exp.bullets?.length > 0 && (
                <ul style={{ marginTop: '4px', paddingLeft: '16px', fontSize: '11.5px', color: '#444' }}>
                  {exp.bullets.filter(Boolean).map((b, j) => <li key={j} style={{ marginBottom: '2px' }}>{b}</li>)}
                </ul>
              )}
            </div>
          ))}
        </>
      )}

      {/* Education */}
      {p.education?.length > 0 && (
        <>
          <h2 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '6px', color: '#333', borderBottom: '1px solid #ddd', paddingBottom: '2px' }}>
            Education
          </h2>
          {p.education.map((edu, i) => (
            <div key={i} style={{ marginBottom: '6px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong style={{ fontSize: '12px' }}>{edu.degree}</strong>
                <span style={{ fontSize: '11px', color: '#888' }}>{edu.year}</span>
              </div>
              <div style={{ fontSize: '12px', fontStyle: 'italic', color: '#555' }}>
                {edu.institution}{edu.gpa ? ` | GPA: ${edu.gpa}` : ''}
              </div>
            </div>
          ))}
        </>
      )}

      {/* Skills */}
      {p.skills?.length > 0 && (
        <>
          <h2 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '4px', color: '#333', borderBottom: '1px solid #ddd', paddingBottom: '2px' }}>
            {isModern ? 'Technical Skills' : 'Skills'}
          </h2>
          <p style={{ fontSize: '11.5px', color: '#444' }}>
            {isModern ? (
              <span style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 24px' }}>
                {p.skills.map((s, i) => <span key={i}>- {s}</span>)}
              </span>
            ) : (
              p.skills.join(' \u2022 ')
            )}
          </p>
        </>
      )}

      {!p.name && !p.summary && !p.experience?.length && (
        <p className="text-center text-slate-400 py-8">Fill in your profile details and click "Generate Resume"</p>
      )}
    </div>
  );
}
