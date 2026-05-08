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
  FileText, Download, Copy, Sparkles, Plus, X, ChevronDown, ChevronUp,
  Briefcase, GraduationCap, Code, User, Loader2, Check, Search, Eye, Edit2, FileDown
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
  const [pdfUrl, setPdfUrl] = useState(null);
  const [compilingPdf, setCompilingPdf] = useState(false);
  const [activeTab, setActiveTab] = useState('pdf');
  const [aiEnhancing, setAiEnhancing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [newSkill, setNewSkill] = useState('');
  const [candidateSearch, setCandidateSearch] = useState('');
  const [candidates, setCandidates] = useState([]);
  const [searchingCandidates, setSearchingCandidates] = useState(false);
  const [selectedCandidateId, setSelectedCandidateId] = useState(null);
  const [editOpen, setEditOpen] = useState(false);
  const [pdfAvailable, setPdfAvailable] = useState(true);

  const loadMyProfile = useCallback(async () => {
    try {
      const res = await resumeAPI.getMyProfile();
      if (res.data) {
        const loaded = { ...profile, ...res.data };
        setProfile(loaded);
        if (loaded.name) {
          generateAndCompile(loaded, selectedTemplate);
        }
      }
    } catch (e) {
      toast.error('Failed to load profile');
    } finally {
      setLoading(false);
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load profile on mount — PDF is always available via fpdf2
  useEffect(() => {
    if (isCandidate) {
      loadMyProfile();
    } else {
      setLoading(false);
    }
  }, [isCandidate, loadMyProfile]);

  // Cleanup PDF blob URL on unmount
  useEffect(() => {
    return () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); };
  }, [pdfUrl]);

  const compilePdf = async (profileData) => {
    if (!pdfAvailable) return;
    setCompilingPdf(true);
    try {
      // Use generatePdf (pure Python, works in all environments)
      const res = await resumeAPI.generatePdf(profileData, selectedTemplate);
      const blob = new Blob([res.data], { type: 'application/pdf' });
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
      const url = URL.createObjectURL(blob);
      setPdfUrl(url);
      setActiveTab('pdf');
    } catch (e) {
      if (e.response?.status === 503) {
        setPdfAvailable(false);
        setActiveTab('preview');
        return;
      }
      toast.error('PDF generation failed');
    } finally {
      setCompilingPdf(false);
    }
  };

  const generateAndCompile = async (profileData, template) => {
    setGenerating(true);
    try {
      const res = await resumeAPI.generate(profileData, template);
      const newLatex = res.data.latex;
      setLatex(newLatex);
      // Generate PDF from profile data directly (fpdf2 — works everywhere)
      compilePdf(profileData);
    } catch (e) {
      toast.error('Generation failed');
    } finally {
      setGenerating(false);
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
      if (res.data) {
        const loaded = { ...profile, ...res.data };
        setProfile(loaded);
        generateAndCompile(loaded, selectedTemplate);
      }
      toast.success('Candidate profile loaded');
    } catch (e) {
      toast.error('Failed to load candidate profile');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    generateAndCompile(profile, selectedTemplate);
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
      const updated = { ...profile, experience: updatedExp };
      setProfile(updated);
      toast.success('Bullets enhanced with AI!');
      generateAndCompile(updated, selectedTemplate);
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

  const handleDownloadTex = useCallback(() => {
    const blob = new Blob([latex], { type: 'application/x-tex' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${profile.name?.replace(/\s+/g, '_') || 'resume'}.tex`;
    a.click();
    URL.revokeObjectURL(url);
  }, [latex, profile.name]);

  const handleDownloadPdf = useCallback(() => {
    if (!pdfUrl) return;
    const a = document.createElement('a');
    a.href = pdfUrl;
    a.download = `${profile.name?.replace(/\s+/g, '_') || 'resume'}.pdf`;
    a.click();
  }, [pdfUrl, profile.name]);

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

  const isProcessing = generating || compilingPdf;

  return (
    <div className="space-y-6" data-testid="resume-builder-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-bold text-slate-900">Resume Builder</h1>
          <p className="text-slate-500 text-sm mt-1">Generate a professional resume with live PDF preview</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button
            onClick={handleAiEnhance}
            disabled={aiEnhancing || !profile.experience.length || isProcessing}
            variant="outline"
            className="border-purple-300 text-purple-700 hover:bg-purple-50"
            data-testid="ai-enhance-btn"
          >
            {aiEnhancing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
            AI Enhance
          </Button>
          <Button
            onClick={handleGenerate}
            disabled={isProcessing || !profile.name}
            className="bg-[#7CB342] hover:bg-[#689F38]"
            data-testid="generate-resume-btn"
          >
            {isProcessing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <FileText className="w-4 h-4 mr-2" />}
            {isProcessing ? 'Compiling...' : (latex ? 'Regenerate' : 'Generate')} Resume
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

      {/* Preview-First Layout */}
      <div className="space-y-6">
        {/* Resume Output — Always visible */}
        <Card className="border-slate-200" data-testid="resume-output-card">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex gap-1 bg-slate-100 rounded-lg p-0.5">
                <button
                  onClick={() => setActiveTab('pdf')}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'pdf' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                  }`}
                  data-testid="tab-pdf"
                >
                  <FileDown className="w-3.5 h-3.5 inline mr-1.5" />PDF
                </button>
                <button
                  onClick={() => setActiveTab('preview')}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'preview' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                  }`}
                  data-testid="tab-preview"
                >
                  <Eye className="w-3.5 h-3.5 inline mr-1.5" />Preview
                </button>
                <button
                  onClick={() => setActiveTab('latex')}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'latex' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                  }`}
                  data-testid="tab-latex"
                >
                  LaTeX
                </button>
              </div>
              <div className="flex gap-2">
                {pdfUrl && (
                  <Button onClick={handleDownloadPdf} size="sm" className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="download-pdf-btn">
                    <Download className="w-4 h-4 mr-1" /> PDF
                  </Button>
                )}
                {latex && (
                  <>
                    <Button onClick={handleCopy} size="sm" variant="outline" data-testid="copy-latex-btn">
                      {copied ? <Check className="w-4 h-4 mr-1 text-green-600" /> : <Copy className="w-4 h-4 mr-1" />}
                      {copied ? 'Copied' : 'Copy'}
                    </Button>
                    <Button onClick={handleDownloadTex} size="sm" variant="outline" data-testid="download-tex-btn">
                      <Download className="w-4 h-4 mr-1" /> .tex
                    </Button>
                  </>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {activeTab === 'pdf' ? (
              pdfUrl ? (
                <div className="rounded-lg overflow-hidden border bg-slate-100" data-testid="pdf-viewer">
                  <iframe
                    src={pdfUrl}
                    title="Resume PDF Preview"
                    className="w-full border-0"
                    style={{ height: '680px' }}
                  />
                </div>
              ) : compilingPdf ? (
                <div className="flex flex-col items-center justify-center py-16 text-slate-400" data-testid="pdf-compiling">
                  <Loader2 className="w-8 h-8 animate-spin text-[#7CB342] mb-3" />
                  <p className="text-sm font-medium">Compiling PDF...</p>
                  <p className="text-xs mt-1">Converting LaTeX to PDF</p>
                </div>
              ) : (
                <div className="text-center py-16 text-slate-400" data-testid="pdf-empty">
                  <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">{profile.name ? 'Click "Generate Resume" to see your PDF' : 'Search for a candidate or fill in your details to generate a PDF'}</p>
                </div>
              )
            ) : activeTab === 'preview' ? (
              <ResumePreview profile={profile} template={selectedTemplate} />
            ) : latex ? (
              <div className="relative">
                <pre className="bg-slate-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto max-h-[600px] overflow-y-auto font-mono">
                  {latex}
                </pre>
                <p className="text-xs text-slate-400 mt-2">
                  Compile with: pdflatex resume.tex or paste into <a href="https://www.overleaf.com" target="_blank" rel="noreferrer" className="text-[#7CB342] underline">Overleaf</a>
                </p>
              </div>
            ) : (
              <div className="text-center py-8 text-slate-400 text-sm">
                Click "Generate Resume" to create the LaTeX code
              </div>
            )}
          </CardContent>
        </Card>

        {/* Collapsible Edit Section */}
        <Card className="border-slate-200">
          <CardHeader
            className="pb-3 cursor-pointer select-none hover:bg-slate-50 transition-colors rounded-t-lg"
            onClick={() => setEditOpen(!editOpen)}
          >
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Edit2 className="w-4 h-4 text-[#7CB342]" /> Edit Profile Details
              </CardTitle>
              {editOpen ? <ChevronUp className="w-5 h-5 text-slate-400" /> : <ChevronDown className="w-5 h-5 text-slate-400" />}
            </div>
          </CardHeader>
          {editOpen && (
            <CardContent>
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column */}
                <div className="space-y-4">
                  {/* Template Selection */}
                  <div>
                    <Label className="text-xs text-slate-500 font-semibold flex items-center gap-1.5 mb-2">
                      <FileText className="w-3.5 h-3.5 text-[#7CB342]" /> Template
                    </Label>
                    <div className="space-y-1.5">
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
                    </div>
                  </div>

                  {/* Personal Info */}
                  <div>
                    <Label className="text-xs text-slate-500 font-semibold flex items-center gap-1.5 mb-2">
                      <User className="w-3.5 h-3.5 text-[#7CB342]" /> Personal Info
                    </Label>
                    <div className="space-y-2">
                      <Input value={profile.name} onChange={(e) => updateField('name', e.target.value)} placeholder="Full Name" data-testid="profile-name" />
                      <Input value={profile.email} onChange={(e) => updateField('email', e.target.value)} placeholder="Email" data-testid="profile-email" />
                      <div className="grid grid-cols-2 gap-2">
                        <Input value={profile.phone} onChange={(e) => updateField('phone', e.target.value)} placeholder="Phone" data-testid="profile-phone" />
                        <Input value={profile.location} onChange={(e) => updateField('location', e.target.value)} placeholder="Location" data-testid="profile-location" />
                      </div>
                      <Input value={profile.linkedin} onChange={(e) => updateField('linkedin', e.target.value)} placeholder="LinkedIn URL" data-testid="profile-linkedin" />
                      <Textarea value={profile.summary} onChange={(e) => updateField('summary', e.target.value)} rows={3} placeholder="Professional Summary" data-testid="profile-summary" />
                    </div>
                  </div>

                  {/* Skills */}
                  <div>
                    <Label className="text-xs text-slate-500 font-semibold flex items-center gap-1.5 mb-2">
                      <Code className="w-3.5 h-3.5 text-[#7CB342]" /> Skills
                    </Label>
                    <div className="flex gap-2 mb-2">
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
                        <span key={`skill-${skill}-${idx}`} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-xs text-slate-700">
                          {skill}
                          <button onClick={() => removeSkill(idx)} className="hover:text-red-500"><X className="w-3 h-3" /></button>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Right Column: Experience + Education */}
                <div className="lg:col-span-2 space-y-4">
                  {/* Experience */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <Label className="text-xs text-slate-500 font-semibold flex items-center gap-1.5">
                        <Briefcase className="w-3.5 h-3.5 text-[#7CB342]" /> Experience
                      </Label>
                      <Button onClick={addExperience} size="sm" variant="outline" data-testid="add-experience-btn">
                        <Plus className="w-4 h-4 mr-1" /> Add
                      </Button>
                    </div>
                    <div className="space-y-3">
                      {profile.experience.map((exp, expIdx) => (
                        <div key={expIdx} className="border rounded-lg p-3 space-y-2 relative bg-slate-50/50">
                          <button onClick={() => removeExperience(expIdx)} className="absolute top-2 right-2 text-slate-400 hover:text-red-500" data-testid={`remove-exp-${expIdx}`}>
                            <X className="w-4 h-4" />
                          </button>
                          <div className="grid grid-cols-2 gap-2">
                            <Input value={exp.title} onChange={(e) => updateExperience(expIdx, 'title', e.target.value)} placeholder="Job Title" className="text-sm" />
                            <Input value={exp.company} onChange={(e) => updateExperience(expIdx, 'company', e.target.value)} placeholder="Company" className="text-sm" />
                          </div>
                          <Input value={exp.duration} onChange={(e) => updateExperience(expIdx, 'duration', e.target.value)} placeholder="Duration (e.g., Jan 2022 - Present)" className="text-sm" />
                          <div className="space-y-1.5">
                            <Label className="text-xs text-slate-500">Bullet Points</Label>
                            {exp.bullets.map((bullet, bIdx) => (
                              <div key={bIdx} className="flex gap-1.5">
                                <Input value={bullet} onChange={(e) => updateBullet(expIdx, bIdx, e.target.value)} placeholder="Describe your achievement..." className="flex-1 text-sm" />
                                <button onClick={() => removeBullet(expIdx, bIdx)} className="text-slate-400 hover:text-red-500 shrink-0"><X className="w-3.5 h-3.5" /></button>
                              </div>
                            ))}
                            <button onClick={() => addBullet(expIdx)} className="text-xs text-[#7CB342] hover:text-[#689F38] flex items-center gap-1">
                              <Plus className="w-3 h-3" /> Add bullet
                            </button>
                          </div>
                        </div>
                      ))}
                      {!profile.experience.length && (
                        <p className="text-sm text-slate-400 text-center py-4">No experience added yet</p>
                      )}
                    </div>
                  </div>

                  {/* Education */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <Label className="text-xs text-slate-500 font-semibold flex items-center gap-1.5">
                        <GraduationCap className="w-3.5 h-3.5 text-[#7CB342]" /> Education
                      </Label>
                      <Button onClick={addEducation} size="sm" variant="outline" data-testid="add-education-btn">
                        <Plus className="w-4 h-4 mr-1" /> Add
                      </Button>
                    </div>
                    <div className="space-y-3">
                      {profile.education.map((edu, idx) => (
                        <div key={`edu-${edu.institution}-${idx}`} className="border rounded-lg p-3 space-y-2 relative bg-slate-50/50">
                          <button onClick={() => removeEducation(idx)} className="absolute top-2 right-2 text-slate-400 hover:text-red-500" data-testid={`remove-edu-${idx}`}>
                            <X className="w-4 h-4" />
                          </button>
                          <Input value={edu.institution} onChange={(e) => updateEducation(idx, 'institution', e.target.value)} placeholder="University / Institution" className="text-sm" />
                          <div className="grid grid-cols-3 gap-2">
                            <Input value={edu.degree} onChange={(e) => updateEducation(idx, 'degree', e.target.value)} placeholder="Degree" className="text-sm" />
                            <Input value={edu.year} onChange={(e) => updateEducation(idx, 'year', e.target.value)} placeholder="Year" className="text-sm" />
                            <Input value={edu.gpa || ''} onChange={(e) => updateEducation(idx, 'gpa', e.target.value)} placeholder="GPA (optional)" className="text-sm" />
                          </div>
                        </div>
                      ))}
                      {!profile.education.length && (
                        <p className="text-sm text-slate-400 text-center py-4">No education added yet</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          )}
        </Card>
      </div>
    </div>
  );
}

// Visual Preview Component
function ResumePreview({ profile: p, template: tpl }) {
  const isModern = tpl === 'modern';

  if (!p.name && !p.summary && !p.experience?.length && !p.skills?.length) {
    return (
      <div className="text-center py-12 text-slate-400" data-testid="resume-preview-empty">
        <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">Search for a candidate above to preview their resume</p>
      </div>
    );
  }

  return (
    <div
      className="bg-white border rounded-lg shadow-inner p-8 max-h-[600px] overflow-y-auto"
      style={{ fontFamily: 'Georgia, "Times New Roman", serif', fontSize: '13px', lineHeight: '1.5', color: '#1a1a1a' }}
      data-testid="resume-preview"
    >
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
      {p.summary && (
        <>
          <h2 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '4px', color: '#333' }}>
            {isModern ? 'Professional Summary' : 'Summary'}
          </h2>
          <p style={{ fontSize: '12px', color: '#444', marginBottom: '12px' }}>{p.summary}</p>
        </>
      )}
      {p.experience?.length > 0 && (
        <>
          <h2 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '6px', color: '#333', borderBottom: '1px solid #ddd', paddingBottom: '2px' }}>Experience</h2>
          {p.experience.map((exp, i) => (
            <div key={`prev-exp-${exp.company}-${i}`} style={{ marginBottom: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <strong style={{ fontSize: '12px' }}>{exp.title}</strong>
                <span style={{ fontSize: '11px', color: '#888' }}>{exp.duration}</span>
              </div>
              <div style={{ fontSize: '12px', fontStyle: 'italic', color: '#555' }}>{exp.company}</div>
              {exp.bullets?.length > 0 && (
                <ul style={{ marginTop: '4px', paddingLeft: '16px', fontSize: '11.5px', color: '#444' }}>
                  {exp.bullets.filter(Boolean).map((b, j) => <li key={`bullet-${j}`} style={{ marginBottom: '2px' }}>{b}</li>)}
                </ul>
              )}
            </div>
          ))}
        </>
      )}
      {p.education?.length > 0 && (
        <>
          <h2 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '6px', color: '#333', borderBottom: '1px solid #ddd', paddingBottom: '2px' }}>Education</h2>
          {p.education.map((edu, i) => (
            <div key={`prev-edu-${edu.degree}-${i}`} style={{ marginBottom: '6px' }}>
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
      {p.skills?.length > 0 && (
        <>
          <h2 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '4px', color: '#333', borderBottom: '1px solid #ddd', paddingBottom: '2px' }}>
            {isModern ? 'Technical Skills' : 'Skills'}
          </h2>
          <p style={{ fontSize: '11.5px', color: '#444' }}>
            {isModern ? (
              <span style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 24px' }}>
                {p.skills.map((s, i) => <span key={`skill-${s}`}>- {s}</span>)}
              </span>
            ) : (
              p.skills.join(' \u2022 ')
            )}
          </p>
        </>
      )}
    </div>
  );
}
