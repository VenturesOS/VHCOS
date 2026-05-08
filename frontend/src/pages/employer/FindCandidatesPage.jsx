import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../lib/auth';
import { matchingAPI, jobAPI, aiSearchAPI, sourcingAPI } from '../../lib/api';
import api from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { Search, Upload, Sparkles, Filter, ChevronDown, ChevronUp, AlertCircle, Star, Zap, Brain, Loader2, CheckCircle, ExternalLink, UserPlus, MapPin, Briefcase, Building2, Phone, Mail, DollarSign, Clock } from 'lucide-react';
import SemanticSearchPanel from '../../components/candidates/SemanticSearchPanel';

export default function FindCandidatesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState(searchParams.get('job_id') || '');
  const [jdText, setJdText] = useState('');
  const [jdFile, setJdFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const [matchMode, setMatchMode] = useState('quick');
  const [bgJobId, setBgJobId] = useState(null);
  const [bgProgress, setBgProgress] = useState(0);
  const [shortlistingId, setShortlistingId] = useState(null);
  const [shortlistedCandidates, setShortlistedCandidates] = useState(new Set());
  const [shortlistJobId, setShortlistJobId] = useState('');
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);

  // AI Search state
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiResults, setAiResults] = useState([]);
  const [aiFilters, setAiFilters] = useState(null);
  const [aiLog, setAiLog] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [showFilterPreview, setShowFilterPreview] = useState(false);
  // Phase 54: ML re-rank toggle. When ON, the AI tab uses the new
  // /sourcing/rerank endpoint (XGBoost LTR + k-Means diversification +
  // PCA-compressed embeddings) instead of the legacy /ai-search filter
  // pipeline. Default ON because the LTR model trained on 14k applications
  // outperforms keyword-extracted filters for natural-language prompts.
  const [aiRerank, setAiRerank] = useState(true);
  const [aiRerankMeta, setAiRerankMeta] = useState(null);
  const [activeTab, setActiveTab] = useState('job');
  // Add as Applicant dialog state
  const [addApplicantCandidate, setAddApplicantCandidate] = useState(null);
  const [addApplicantJobId, setAddApplicantJobId] = useState('');
  const [addingApplicant, setAddingApplicant] = useState(false);

  const [filters, setFilters] = useState({
    location: '', qualification: '', skills: '',
    minExperience: '', maxExperience: '', keyword: '',
  });

  useEffect(() => { loadJobs(); }, []);

  // Auto-trigger search when job_id is provided via URL
  useEffect(() => {
    const jobIdFromUrl = searchParams.get('job_id');
    if (jobIdFromUrl && jobs.length > 0 && jobs.find(j => j.id === jobIdFromUrl)) {
      setSelectedJobId(jobIdFromUrl);
      // Small delay to let state settle
      const timer = setTimeout(() => {
        document.getElementById('find-candidates-search-btn')?.click();
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [jobs, searchParams]);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const loadJobs = async () => {
    try { const res = await jobAPI.getAll(); setJobs(res.data); }
    catch { /* silently fail */ }
  };

  const handleAISearch = async () => {
    if (!aiPrompt.trim() || aiPrompt.trim().length < 5) {
      toast.error('Please enter a more detailed search prompt.');
      return;
    }
    setAiLoading(true);
    setAiResults([]);
    setAiFilters(null);
    setAiLog(null);
    setAiRerankMeta(null);
    try {
      if (aiRerank) {
        // Phase 54 ML path: vector search → XGBoost LTR → k-Means diversify
        const res = await sourcingAPI.rerank({
          query: aiPrompt,
          top_k: 50,
          diversify: true,
          job_id: selectedJobId || undefined,
        });
        const cands = res.data.candidates || [];
        setAiResults(cands);
        setAiRerankMeta({
          model_loaded: res.data.model_loaded,
          pool: res.data.total_pool,
          timing: res.data.timing_ms,
          meta: res.data.model_meta,
        });
        if (cands.length === 0) {
          toast.info('No candidates matched. Try broadening the prompt or turn off Smart Re-rank.');
        } else {
          const ms = res.data.timing_ms?.total || 0;
          toast.success(`Smart re-ranked ${cands.length} of ${res.data.total_pool} candidates (${ms}ms)`);
        }
      } else {
        // Legacy path: NL prompt → filter extraction → structured search
        const res = await aiSearchAPI.search({ prompt: aiPrompt, limit: 50, generate_explanations: true });
        setAiResults(res.data.candidates || []);
        setAiFilters(res.data.filters_used || null);
        setAiLog(res.data.log || null);
        if ((res.data.candidates || []).length === 0) {
          toast.info('No candidates matched your criteria. Try broadening your search.');
        } else {
          toast.success(`Found ${res.data.total} matching candidates`);
        }
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'AI Search failed. Please try again.');
    } finally {
      setAiLoading(false);
    }
  };

  const pollMatchJob = useCallback((jobId) => {
    setBgJobId(jobId);
    setBgProgress(0);
    pollRef.current = setInterval(async () => {
      try {
        const res = await matchingAPI.getMatchJobStatus(jobId);
        const data = res.data;
        setBgProgress(data.progress || 0);
        if (data.status === 'completed' && data.results) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setResults(data.results);
          setBgJobId(null);
          setLoading(false);
          const matchedCount = data.results.filter(r => !r.filtered_out && r.score >= 50).length;
          toast.success(`Full AI Match complete: ${matchedCount} matching candidates`);
        } else if (data.status === 'failed') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setBgJobId(null);
          setLoading(false);
          toast.error(data.error || 'AI matching failed');
        }
      } catch {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setBgJobId(null);
        setLoading(false);
        toast.error('Failed to check match status');
      }
    }, 3000);
  }, []);

  const handleSearch = async () => {
    if (!selectedJobId && !jdText && !jdFile) {
      toast.error('Please select a job or enter job description');
      return;
    }
    setLoading(true);
    setResults([]);
    setBgJobId(null);
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }

    try {
      const params = { match_mode: matchMode, limit: 100 };
      if (selectedJobId) params.job_id = selectedJobId;
      else if (jdText) params.jd_text = jdText;
      if (filters.location) params.must_have_location = filters.location;
      if (filters.qualification) params.must_have_qualification = filters.qualification;
      if (filters.skills) params.must_have_skills = filters.skills.split(',').map(s => s.trim());
      if (filters.minExperience) params.min_experience = parseInt(filters.minExperience);
      if (filters.maxExperience) params.max_experience = parseInt(filters.maxExperience);
      if (filters.keyword) params.keyword = filters.keyword;

      const res = await matchingAPI.findCandidates(params);
      const data = res.data;

      // Check if Full AI returned a background job
      if (data.length === 1 && data[0].candidate_id === '__background_job__') {
        const jobId = data[0].candidate_email;
        toast.info('Full AI Match started in background. Polling for results...');
        pollMatchJob(jobId);
        return;
      }

      setResults(data);
      setLoading(false);
      const matchedCount = data.filter(r => !r.filtered_out && r.score >= 50).length;
      toast.success(`Found ${matchedCount} matching candidates out of ${data.length} total`);
    } catch (error) {
      setLoading(false);
      toast.error(error.response?.data?.detail || 'Search failed');
    }
  };

  const getScoreColor = (score) => {
    if (score >= 80) return 'text-green-600 bg-green-50 border-green-200';
    if (score >= 60) return 'text-[#7CB342] bg-[#DCFCE7] border-[#7CB342]/20';
    if (score >= 40) return 'text-amber-600 bg-amber-50 border-amber-200';
    return 'text-slate-500 bg-slate-100 border-slate-200';
  };

  const handleShortlist = async (candidate) => {
    // Use selectedJobId or shortlistJobId (from the dialog job picker)
    const jobId = selectedJobId || shortlistJobId;
    if (!jobId) {
      toast.error('Please select a job mandate to shortlist the candidate for');
      return;
    }
    
    setShortlistingId(candidate.candidate_id);
    try {
      const res = await matchingAPI.shortlistCandidate(candidate.candidate_id, jobId);
      setShortlistedCandidates(prev => new Set([...prev, candidate.candidate_id]));
      toast.success(`${res.data.candidate_name} has been shortlisted for ${res.data.job_title}`);
      setSelectedCandidate(null);
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to shortlist candidate';
      toast.error(errorMsg);
    } finally {
      setShortlistingId(null);
    }
  };

  const handleViewProfile = (candidateId) => {
    const basePath = user?.role === 'recruiter' ? '/recruiter' : user?.role === 'employer' ? '/employer' : '/admin';
    navigate(`${basePath}/naukri-profile/${candidateId}`);
  };

  const handleAddAsApplicant = async () => {
    if (!addApplicantJobId || !addApplicantCandidate) return;
    setAddingApplicant(true);
    try {
      const res = await matchingAPI.shortlistCandidate(addApplicantCandidate.id, addApplicantJobId);
      toast.success(`${addApplicantCandidate.name} added as applicant for ${res.data.job_title}`);
      setShortlistedCandidates(prev => new Set([...prev, addApplicantCandidate.id]));
      setAddApplicantCandidate(null);
      setAddApplicantJobId('');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add as applicant');
    } finally {
      setAddingApplicant(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="find-candidates-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Find Matching Candidates</h1>
        <p className="text-slate-500 mt-1">AI-powered candidate matching based on job requirements</p>
      </div>

      {/* Semantic Talent Graph search — describes-by-intent search */}
      <SemanticSearchPanel
        onViewFullProfile={(id) => handleViewProfile(id)}
        onSelectCandidate={async (r) => {
          // r is the full match row from /talent-graph/search:
          //   { candidate_id, candidate_name, current_designation, current_employer,
          //     experience_years, current_location, summary, score (0..1) }
          try {
            const id = r.candidate_id;
            // Fetch the full candidate record for richer dialog fields
            const cand = await api.get(`/candidate-bank/${id}`).catch(() => null);
            const c = cand?.data || {};
            // ai_summary is mirrored onto candidate_bank when the embedding was
            // upserted; fall back to the dedicated talent-graph summary endpoint.
            let aiSummary = c.ai_summary || r.summary || null;
            if (!aiSummary) {
              const sumRes = await api.get(`/talent-graph/summary/${id}`).catch(() => null);
              aiSummary = sumRes?.data?.summary || null;
            }

            const skills = c.key_skills || c.skills || [];
            const eduLine = (() => {
              if (c.highest_qualification) return c.highest_qualification;
              const e = (c.education || [])[0];
              if (!e) return null;
              return [e.degree, e.specialization, e.institute].filter(Boolean).join(' · ');
            })();
            const realPct = Math.round((r.score || 0) * 100);

            setSelectedCandidate({
              _source: 'semantic',                          // flag: hide JD-only blocks
              candidate_id: id,
              candidate_name: c.name || r.candidate_name,
              designation: c.current_designation || r.current_designation,
              current_employer: c.current_employer || c.current_company || r.current_employer,
              location: c.current_location || c.location || r.current_location,
              experience_years: c.experience_years || c.total_experience_years || r.experience_years,
              candidate_email: c.email,
              email: c.email,
              phone: c.phone,
              current_salary: c.current_salary,
              expected_salary: c.expected_salary,
              notice_period: c.notice_period,
              industry: c.current_industry || c.industry,
              education: eduLine,
              headline: c.resume_headline || c.headline,
              skills,                                       // dialog reads `skills`
              key_skills: skills,                           // belt-and-suspenders
              ai_summary: aiSummary,
              explanation: aiSummary,                       // shown under "AI Assessment"
              semantic_score: realPct,                      // populates the Semantic tile
              score: realPct,                               // header big % — REAL cosine
            });
          } catch (e) {
            toast.error('Could not open candidate');
          }
        }}
      />

      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-[#7CB342]" />
            Job Requirements
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="mb-4 w-full flex overflow-x-auto">
              <TabsTrigger value="job" className="flex-1 min-w-0 text-xs sm:text-sm">Select Job</TabsTrigger>
              <TabsTrigger value="text" className="flex-1 min-w-0 text-xs sm:text-sm">Paste JD</TabsTrigger>
              <TabsTrigger value="file" className="flex-1 min-w-0 text-xs sm:text-sm">Upload JD</TabsTrigger>
              <TabsTrigger value="ai" data-testid="ai-search-tab" className="flex-1 min-w-0 gap-1 text-xs sm:text-sm"
                onClick={(e) => { e.preventDefault(); navigate(`/${user?.role === 'recruiter' ? 'recruiter' : user?.role === 'employer' ? 'employer' : 'admin'}/advanced-search`); }}>
                <Search className="w-3.5 h-3.5 hidden sm:inline" /> Advanced Search
              </TabsTrigger>
            </TabsList>
            <TabsContent value="job">
              <Select value={selectedJobId} onValueChange={setSelectedJobId}>
                <SelectTrigger data-testid="job-select">
                  <SelectValue placeholder="Select a job posting" />
                </SelectTrigger>
                <SelectContent>
                  {jobs.map((job) => (
                    <SelectItem key={job.id} value={job.id}>{job.title} - {job.location}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </TabsContent>
            <TabsContent value="text">
              <Textarea value={jdText} onChange={(e) => setJdText(e.target.value)}
                placeholder="Paste the full job description here..." rows={6} data-testid="jd-text-input" />
            </TabsContent>
            <TabsContent value="file">
              <div className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center">
                <input type="file" ref={fileInputRef} onChange={(e) => setJdFile(e.target.files?.[0])}
                  accept=".pdf,.doc,.docx,.txt" className="hidden" />
                <Upload className="w-10 h-10 text-slate-400 mx-auto mb-2" />
                <p className="text-sm text-slate-500 mb-2">{jdFile ? jdFile.name : 'Upload PDF, DOC, or TXT file'}</p>
                <Button variant="outline" onClick={() => fileInputRef.current?.click()}>Choose File</Button>
              </div>
            </TabsContent>
            <TabsContent value="ai">
              <div className="space-y-4">
                <div className="relative">
                  <Textarea value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)}
                    placeholder={"Describe the candidate you're looking for in natural language...\n\nExamples:\n• Find HR managers with payroll and statutory compliance, 5-10 years, from Pune or Mumbai\n• CA with GST auditing experience, not from Big 4, stable profile\n• Plant HR with union negotiation experience in manufacturing OEM, not dealership"}
                    rows={5} className="resize-none pr-4" data-testid="ai-search-input" />
                </div>
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3 flex-wrap">
                    <Button variant="ghost" size="sm" className="text-slate-500 text-xs"
                      onClick={() => setShowFilterPreview(!showFilterPreview)} data-testid="toggle-filter-preview">
                      <Filter className="w-3.5 h-3.5 mr-1.5" />
                      {showFilterPreview ? 'Hide' : 'Show'} Filter Preview
                    </Button>
                    {aiLog && (
                      <span className="text-xs text-slate-400">
                        {aiLog.model} &middot; {aiLog.time_s}s &middot; {aiLog.tokens?.total_tokens || 0} tokens
                      </span>
                    )}
                  </div>
                  <Button onClick={handleAISearch} disabled={aiLoading} className="bg-[#7CB342] hover:bg-[#689F38] w-full sm:w-auto"
                    data-testid="ai-search-btn">
                    {aiLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
                    {aiLoading ? 'Searching...' : 'AI Search'}
                  </Button>
                </div>
                {/* Phase 54 — Smart Re-rank toggle (XGBoost LTR + k-Means) */}
                <div className="flex items-center gap-3 px-1 py-2">
                  <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-600 hover:text-slate-900">
                    <input
                      type="checkbox"
                      checked={aiRerank}
                      onChange={(e) => setAiRerank(e.target.checked)}
                      className="rounded border-slate-300 text-[#7CB342] focus:ring-[#7CB342]"
                      data-testid="ai-rerank-toggle"
                    />
                    <Brain className="w-4 h-4 text-[#7CB342]" />
                    <span className="font-medium">Smart Re-rank</span>
                    <span className="text-xs text-slate-400">
                      (ML-trained on your team's hires — recommended)
                    </span>
                  </label>
                  {aiRerankMeta?.timing && (
                    <span className="ml-auto text-xs text-slate-500" data-testid="ai-rerank-meta">
                      {aiRerankMeta.pool} pool · re-ranked in {aiRerankMeta.timing.total}ms
                      {aiRerankMeta.meta?.auc ? ` · AUC ${aiRerankMeta.meta.auc}` : ''}
                    </span>
                  )}
                </div>
                {showFilterPreview && aiFilters && (
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono overflow-auto max-h-48"
                    data-testid="filter-preview">
                    <pre className="whitespace-pre-wrap text-slate-600">{JSON.stringify(aiFilters, null, 2)}</pre>
                  </div>
                )}
              </div>
            </TabsContent>
          </Tabs>

          {/* Filters Toggle — only for JD-based tabs */}
          {activeTab !== 'ai' && (
          <div className="mt-4">
            <Button variant="ghost" className="text-slate-600" onClick={() => setShowFilters(!showFilters)}
              data-testid="toggle-filters-btn">
              <Filter className="w-4 h-4 mr-2" />Must-Have Filters
              {showFilters ? <ChevronUp className="w-4 h-4 ml-2" /> : <ChevronDown className="w-4 h-4 ml-2" />}
            </Button>
            {showFilters && (
              <div className="mt-4 p-4 bg-slate-50 rounded-lg grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div className="col-span-full space-y-2"><Label>Keyword Search</Label>
                  <Input value={filters.keyword} onChange={(e) => setFilters({ ...filters, keyword: e.target.value })} 
                    placeholder="Search across summary, headline, designation..." data-testid="keyword-filter-input" /></div>
                <div className="space-y-2"><Label>Location (Required)</Label>
                  <Input value={filters.location} onChange={(e) => setFilters({ ...filters, location: e.target.value })} placeholder="e.g., New York" /></div>
                <div className="space-y-2"><Label>Qualification (Required)</Label>
                  <Input value={filters.qualification} onChange={(e) => setFilters({ ...filters, qualification: e.target.value })} placeholder="e.g., Bachelor's, MBA" /></div>
                <div className="space-y-2"><Label>Mandatory Skills (comma-separated)</Label>
                  <Input value={filters.skills} onChange={(e) => setFilters({ ...filters, skills: e.target.value })} placeholder="e.g., Python, React" /></div>
                <div className="space-y-2"><Label>Min Experience (years)</Label>
                  <Input type="number" value={filters.minExperience} onChange={(e) => setFilters({ ...filters, minExperience: e.target.value })} placeholder="0" /></div>
                <div className="space-y-2"><Label>Max Experience (years)</Label>
                  <Input type="number" value={filters.maxExperience} onChange={(e) => setFilters({ ...filters, maxExperience: e.target.value })} placeholder="10" /></div>
              </div>
            )}
          </div>
          )}

          {/* Match Mode Toggle & Search — only for JD-based tabs */}
          {activeTab !== 'ai' && (
          <div className="mt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex flex-col sm:flex-row sm:items-center gap-3" data-testid="match-mode-toggle">
              <Label className="text-sm text-slate-600 font-medium">Match Mode:</Label>
              <div className="flex items-center bg-slate-100 p-1 rounded-xl">
                <button onClick={() => setMatchMode('quick')} data-testid="quick-match-btn"
                  className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 text-sm rounded-lg transition-all ${
                    matchMode === 'quick' ? 'bg-white text-[#7CB342] font-semibold shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                  <Zap className="w-4 h-4" /> Quick Match
                </button>
                <button onClick={() => setMatchMode('full_ai')} data-testid="full-ai-match-btn"
                  className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 text-sm rounded-lg transition-all ${
                    matchMode === 'full_ai' ? 'bg-white text-indigo-600 font-semibold shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                  <Brain className="w-4 h-4" /> Full AI
                </button>
              </div>
              <span className="text-xs text-slate-400 max-w-[250px]">
                {matchMode === 'quick'
                  ? 'Keyword + semantic scoring. ~2-5 sec.'
                  : 'LLM-powered deep analysis. ~1-3 min.'}
              </span>
            </div>
            <Button onClick={handleSearch} disabled={loading} className="bg-[#7CB342] hover:bg-[#689F38] w-full sm:w-auto"
              id="find-candidates-search-btn" data-testid="search-candidates-btn">
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
              Find Matching Candidates
            </Button>
          </div>
          )}
        </CardContent>
      </Card>

      {/* Background Job Progress */}
      {bgJobId && (
        <Card className="border-indigo-200 bg-indigo-50/50" data-testid="bg-job-progress">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <Loader2 className="w-5 h-5 text-indigo-600 animate-spin" />
              <div className="flex-1">
                <p className="text-sm font-medium text-indigo-700">Full AI Match in progress...</p>
                <div className="mt-2 h-2 bg-indigo-100 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                    style={{ width: `${bgProgress}%` }} />
                </div>
                <p className="text-xs text-indigo-500 mt-1">{bgProgress}% complete — LLM is scoring each candidate</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* AI Search Results */}
      {aiResults.length > 0 && activeTab === 'ai' && (
        <Card className="border-slate-200" data-testid="ai-search-results">
          <CardHeader>
            <CardTitle className="font-heading text-lg flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-[#7CB342]" />
              AI Search Results ({aiResults.length} candidates)
              {aiLog && <span className="text-xs font-normal text-slate-400 ml-2">{aiLog.model} &middot; {aiLog.time_s}s</span>}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-slate-100">
              {aiResults.map((c, idx) => (
                <div key={c.id || idx} data-testid={`ai-result-${c.id || idx}`}
                  className="p-4 hover:bg-slate-50 transition-colors">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                        <span className="text-[#7CB342] font-semibold">{c.name?.charAt(0)?.toUpperCase() || '?'}</span>
                      </div>
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900 truncate">{c.name}</p>
                        <p className="text-sm text-slate-500 truncate">
                          {c.designation}{c.designation && c.current_employer ? ' at ' : ''}{c.current_employer}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap ml-0 sm:ml-auto shrink-0">
                      {c.experience_years > 0 && (
                        <span className="text-xs text-slate-500 bg-slate-100 px-2 py-1 rounded">{c.experience_years} yrs</span>
                      )}
                      {c.location && (
                        <span className="text-xs text-slate-500 bg-slate-100 px-2 py-1 rounded">{c.location}</span>
                      )}
                      {c.notice_period && (
                        <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded">{c.notice_period}</span>
                      )}
                    </div>
                  </div>
                  {(c.skills || []).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {c.skills.slice(0, 6).map((s) => (
                        <span key={s} className="px-2 py-0.5 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full">{s}</span>
                      ))}
                      {c.skills.length > 6 && <span className="text-xs text-slate-400">+{c.skills.length - 6} more</span>}
                    </div>
                  )}
                  {/* Why this match? — LTR explanation chips (Phase 54.4) */}
                  {c.match_reasons?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5 items-center" data-testid={`ai-match-reasons-${c.id || idx}`}>
                      <span className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Why</span>
                      {c.match_reasons.map((r, i) => (
                        <span key={r.feature || i}
                          data-testid={`ai-reason-chip-${c.id || idx}-${r.feature || i}`}
                          title={`Feature: ${r.feature}${r.weight ? ` · gain ${r.weight.toFixed(1)}` : ''}`}
                          className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-50 text-emerald-700 text-[11px] rounded-full border border-emerald-200 font-medium">
                          <CheckCircle className="w-2.5 h-2.5" />
                          {r.label}
                        </span>
                      ))}
                    </div>
                  )}
                  {c.ai_explanation && (
                    <div className="mt-2 flex items-start gap-1.5" data-testid={`ai-explanation-${c.id || idx}`}>
                      <Brain className="w-3.5 h-3.5 text-indigo-500 shrink-0 mt-0.5" />
                      <p className="text-xs text-slate-600 leading-relaxed">{c.ai_explanation}</p>
                    </div>
                  )}
                  {/* Action buttons */}
                  <div className="mt-3 flex items-center gap-2 flex-wrap">
                    <Button variant="outline" size="sm" onClick={() => handleViewProfile(c.id)}
                      data-testid={`view-profile-btn-${c.id || idx}`}>
                      <ExternalLink className="w-3.5 h-3.5 mr-1.5" />View Full Profile
                    </Button>
                    {shortlistedCandidates.has(c.id) ? (
                      <Button size="sm" disabled className="bg-green-600 text-white" data-testid={`added-applicant-${c.id || idx}`}>
                        <CheckCircle className="w-3.5 h-3.5 mr-1.5" />Added
                      </Button>
                    ) : (
                      <Button size="sm" variant="outline" className="border-[#7CB342] text-[#7CB342] hover:bg-[#DCFCE7]"
                        onClick={() => setAddApplicantCandidate(c)} data-testid={`add-applicant-btn-${c.id || idx}`}>
                        <UserPlus className="w-3.5 h-3.5 mr-1.5" />Add as Applicant
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {results.length > 0 && activeTab !== 'ai' && (
        <Card className="border-slate-200" data-testid="match-results">
          <CardHeader>
            <CardTitle className="font-heading text-lg">
              Matching Candidates ({results.filter(r => !r.filtered_out).length} matched, {results.filter(r => r.filtered_out).length} filtered)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-slate-100">
              {results.map((result) => (
                <div key={result.candidate_id} data-testid={`candidate-result-${result.candidate_id}`}
                  className={`p-4 hover:bg-slate-50 transition-colors cursor-pointer ${result.filtered_out ? 'opacity-50 bg-slate-50' : ''}`}
                  onClick={() => setSelectedCandidate(result)}>
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="flex items-start gap-4 min-w-0 flex-1">
                      <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                        <span className="text-[#7CB342] font-semibold">{result.candidate_name?.charAt(0).toUpperCase()}</span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="font-medium text-slate-900">{result.candidate_name}</p>
                          {result.source && (
                            <span className="px-2 py-0.5 text-[10px] rounded-full font-medium bg-slate-100 text-slate-500">
                              {result.source === 'naukri_extension' ? 'Naukri' : result.source === 'cv_upload' ? 'CV' : result.source === 'bulk_import' ? 'Import' : result.source}
                            </span>
                          )}
                        </div>
                        {(result.designation || result.current_employer) && (
                          <p className="text-sm text-slate-600 truncate">
                            {result.designation}{result.designation && result.current_employer ? ' at ' : ''}{result.current_employer}
                          </p>
                        )}
                        {!result.designation && !result.current_employer && result.candidate_email && (
                          <p className="text-sm text-slate-500 truncate">{result.candidate_email}</p>
                        )}
                        {result.filtered_out && (
                          <p className="text-xs text-red-500 flex items-center gap-1 mt-1">
                            <AlertCircle className="w-3 h-3" />{result.filter_reason}
                          </p>
                        )}
                        {/* Profile details row */}
                        <div className="flex items-center gap-3 mt-1.5 flex-wrap text-xs text-slate-500">
                          {result.location && (
                            <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{result.location}</span>
                          )}
                          {result.experience_years > 0 && (
                            <span className="flex items-center gap-1"><Briefcase className="w-3 h-3" />{result.experience_years} yrs</span>
                          )}
                          {result.current_salary > 0 && (
                            <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" />{(result.current_salary / 100000).toFixed(1)}L</span>
                          )}
                          {result.notice_period && (
                            <span className="flex items-center gap-1 text-amber-600"><Clock className="w-3 h-3" />{result.notice_period}</span>
                          )}
                          {result.phone && (
                            <span className="flex items-center gap-1"><Phone className="w-3 h-3" />{result.phone}</span>
                          )}
                        </div>
                        {/* Skills */}
                        {(result.skills?.length > 0 || result.matched_skills?.length > 0) && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {(result.matched_skills || []).map((skill) => (
                              <span key={`m-${skill}`} className="px-2 py-0.5 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full">{skill}</span>
                            ))}
                            {(result.skills || []).filter(s => !(result.matched_skills || []).includes(s)).slice(0, 5).map((skill) => (
                              <span key={`s-${skill}`} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full">{skill}</span>
                            ))}
                            {(result.skills || []).length > (result.matched_skills || []).length + 5 && (
                              <span className="text-xs text-slate-400">+{result.skills.length - (result.matched_skills || []).length - 5} more</span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className={`px-3 py-1.5 sm:px-4 sm:py-2 rounded-lg font-bold border shrink-0 ${getScoreColor(result.score)}`}>{result.score}%</div>
                  </div>
                  <p className="mt-2 text-sm text-slate-600 line-clamp-2 ml-16">{result.explanation}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Candidate Detail Modal */}
      <Dialog open={!!selectedCandidate} onOpenChange={() => setSelectedCandidate(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading">Candidate Profile</DialogTitle></DialogHeader>
          {selectedCandidate && (
            <div className="space-y-4">
              {/* Header */}
              <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                <div className="flex items-center gap-4 min-w-0 flex-1">
                  <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                    <span className="text-[#7CB342] font-bold text-xl sm:text-2xl">{selectedCandidate.candidate_name?.charAt(0).toUpperCase()}</span>
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-semibold text-lg sm:text-xl truncate">{selectedCandidate.candidate_name}</h3>
                    {(selectedCandidate.designation || selectedCandidate.current_employer) && (
                      <p className="text-slate-600 text-sm">
                        {selectedCandidate.designation}{selectedCandidate.designation && selectedCandidate.current_employer ? ' at ' : ''}{selectedCandidate.current_employer}
                      </p>
                    )}
                    {selectedCandidate.headline && !selectedCandidate.designation && (
                      <p className="text-slate-600 text-sm truncate">{selectedCandidate.headline}</p>
                    )}
                  </div>
                </div>
                <div className={`sm:ml-auto px-4 py-2 rounded-lg font-bold border self-start ${getScoreColor(selectedCandidate.score)}`}>
                  {selectedCandidate.score}% Match
                </div>
              </div>

              {/* Contact & Basic Info Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm bg-slate-50 rounded-lg p-4">
                {selectedCandidate.candidate_email && (
                  <div className="flex items-center gap-2 text-slate-600">
                    <Mail className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="truncate">{selectedCandidate.candidate_email}</span>
                  </div>
                )}
                {selectedCandidate.phone && (
                  <div className="flex items-center gap-2 text-slate-600">
                    <Phone className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span>{selectedCandidate.phone}</span>
                  </div>
                )}
                {selectedCandidate.location && (
                  <div className="flex items-center gap-2 text-slate-600">
                    <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span>{selectedCandidate.location}</span>
                  </div>
                )}
                {selectedCandidate.experience_years > 0 && (
                  <div className="flex items-center gap-2 text-slate-600">
                    <Briefcase className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span>{selectedCandidate.experience_years} yrs experience</span>
                  </div>
                )}
                {selectedCandidate.current_salary > 0 && (
                  <div className="flex items-center gap-2 text-slate-600">
                    <DollarSign className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span>CTC: {(selectedCandidate.current_salary / 100000).toFixed(1)}L</span>
                  </div>
                )}
                {selectedCandidate.expected_salary > 0 && (
                  <div className="flex items-center gap-2 text-slate-600">
                    <DollarSign className="w-3.5 h-3.5 text-green-400 shrink-0" />
                    <span>Expected: {(selectedCandidate.expected_salary / 100000).toFixed(1)}L</span>
                  </div>
                )}
                {selectedCandidate.notice_period && (
                  <div className="flex items-center gap-2 text-amber-600">
                    <Clock className="w-3.5 h-3.5 shrink-0" />
                    <span>{selectedCandidate.notice_period}</span>
                  </div>
                )}
                {selectedCandidate.industry && (
                  <div className="flex items-center gap-2 text-slate-600">
                    <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span>{selectedCandidate.industry}</span>
                  </div>
                )}
                {selectedCandidate.education && (
                  <div className="flex items-center gap-2 text-slate-600 col-span-2">
                    <span className="text-slate-400 text-xs font-medium">EDU:</span>
                    <span className="truncate">{selectedCandidate.education}</span>
                  </div>
                )}
              </div>

              {/* Match Scores — for JD-based matches we show 3 sub-scores;
                  for semantic search we show one big "Semantic Match" tile
                  populated with the REAL cosine similarity (no more N/A). */}
              {selectedCandidate._source === 'semantic' ? (
                <div className="bg-indigo-50 rounded-lg p-4 text-center" data-testid="semantic-match-tile">
                  <p className="text-slate-500 text-xs uppercase tracking-wider">Semantic similarity</p>
                  <p className="font-bold text-2xl text-indigo-700 mt-1">
                    {selectedCandidate.semantic_score ?? selectedCandidate.score}%
                  </p>
                  <p className="text-[11px] text-slate-500 mt-1">
                    Cosine similarity vs your search query (0–100). Skill / experience sub-scores
                    require a job description — open this candidate from a JD-based match for the full breakdown.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-3 sm:gap-4 text-sm">
                  <div className="bg-blue-50 rounded-lg p-3 text-center">
                    <p className="text-slate-500 text-xs">Skill Match</p>
                    <p className="font-bold text-lg text-blue-700">{selectedCandidate.skill_match_score || 'N/A'}{selectedCandidate.skill_match_score ? '%' : ''}</p>
                  </div>
                  <div className="bg-purple-50 rounded-lg p-3 text-center">
                    <p className="text-slate-500 text-xs">Experience</p>
                    <p className="font-bold text-lg text-purple-700">{selectedCandidate.experience_match_score || 'N/A'}{selectedCandidate.experience_match_score ? '%' : ''}</p>
                  </div>
                  <div className="bg-indigo-50 rounded-lg p-3 text-center">
                    <p className="text-slate-500 text-xs">Semantic</p>
                    <p className="font-bold text-lg text-indigo-700">{selectedCandidate.semantic_score != null ? `${selectedCandidate.semantic_score}%` : 'N/A'}</p>
                  </div>
                </div>
              )}

              {/* All Skills */}
              {selectedCandidate.skills?.length > 0 && (
                <div>
                  <h4 className="font-medium mb-2 text-slate-700 text-sm">All Skills</h4>
                  <div className="flex flex-wrap gap-1">
                    {selectedCandidate.skills.map((skill) => (
                      <span key={skill} className={`px-2 py-0.5 text-xs rounded-full ${
                        (selectedCandidate.matched_skills || []).includes(skill)
                          ? 'bg-[#DCFCE7] text-[#7CB342] font-medium'
                          : 'bg-slate-100 text-slate-600'
                      }`}>{skill}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Matched / Missing Skills — only meaningful when there's a JD */}
              {selectedCandidate._source !== 'semantic' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <h4 className="font-medium mb-2 text-[#7CB342] text-sm">Matched Skills</h4>
                    <div className="flex flex-wrap gap-1">
                      {selectedCandidate.matched_skills?.map((skill) => (
                        <span key={skill} className="px-2 py-1 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full">{skill}</span>
                      ))}
                      {!selectedCandidate.matched_skills?.length && <span className="text-slate-400 text-xs">None</span>}
                    </div>
                  </div>
                  <div>
                    <h4 className="font-medium mb-2 text-amber-600 text-sm">Missing Skills</h4>
                    <div className="flex flex-wrap gap-1">
                      {selectedCandidate.missing_skills?.map((skill) => (
                        <span key={skill} className="px-2 py-1 bg-amber-50 text-amber-600 text-xs rounded-full">{skill}</span>
                      ))}
                      {!selectedCandidate.missing_skills?.length && <span className="text-slate-400 text-xs">None</span>}
                    </div>
                  </div>
                </div>
              )}

              {selectedCandidate._source !== 'semantic' && selectedCandidate.strengths?.length > 0 && (
                <div>
                  <h4 className="font-medium mb-2 text-sm">Strengths</h4>
                  <ul className="text-sm text-slate-600 space-y-1">
                    {selectedCandidate.strengths.map((s, i) => (
                      <li key={`reason-${i}`} className="flex items-start gap-2"><Star className="w-4 h-4 text-[#7CB342] shrink-0 mt-0.5" />{s}</li>
                    ))}
                  </ul>
                </div>
              )}
              {(selectedCandidate.explanation || selectedCandidate.ai_summary) && (
                <div className="bg-slate-50 p-4 rounded-lg" data-testid="candidate-ai-summary">
                  <h4 className="font-medium mb-2 text-sm">
                    {selectedCandidate._source === 'semantic' ? 'AI Summary' : 'AI Assessment'}
                  </h4>
                  <p className="text-sm text-slate-600 whitespace-pre-line">
                    {selectedCandidate.explanation || selectedCandidate.ai_summary}
                  </p>
                </div>
              )}
              <div className="border-t pt-4 mt-4">
                <p className="text-xs text-slate-400 mb-3 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />AI recommendation is advisory. Final decision requires human approval.
                </p>
                {!selectedJobId && (
                  <div className={`mb-3 p-3 rounded-lg ${shortlistJobId ? 'bg-green-50 border border-green-200' : 'bg-amber-50 border border-amber-200'}`}>
                    <Label className={`text-xs font-medium mb-1.5 block ${shortlistJobId ? 'text-green-700' : 'text-amber-700'}`}>
                      {shortlistJobId ? 'Job mandate selected' : 'Select a job mandate to shortlist for:'}
                    </Label>
                    <Select value={shortlistJobId} onValueChange={setShortlistJobId}>
                      <SelectTrigger data-testid="shortlist-job-select" className="h-9 text-sm bg-white">
                        <SelectValue placeholder="Choose a job mandate..." />
                      </SelectTrigger>
                      <SelectContent>
                        {jobs.map((job) => (
                          <SelectItem key={job.id} value={job.id}>{job.title} - {job.location}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <div className="flex gap-2 sm:gap-3 flex-wrap">
                  <Button variant="outline" className="flex-1 min-w-[120px] gap-1.5"
                    data-testid="view-full-profile-btn"
                    onClick={() => { const id = selectedCandidate.candidate_id; setSelectedCandidate(null); handleViewProfile(id); }}>
                    <ExternalLink className="w-4 h-4" />
                    View Full Profile
                  </Button>
                  <Button variant="outline" className="flex-1 min-w-[120px] text-slate-600 hover:bg-slate-100"
                    data-testid="save-later-btn"
                    onClick={() => { toast.info('Candidate marked for further review'); setSelectedCandidate(null); }}>
                    Save for Later
                  </Button>
                  {shortlistedCandidates.has(selectedCandidate.candidate_id) ? (
                    <Button className="flex-1 min-w-[160px] bg-green-600 cursor-default" disabled
                      data-testid="shortlist-candidate-btn">
                      <CheckCircle className="w-4 h-4 mr-2" />
                      Already Shortlisted
                    </Button>
                  ) : (
                    <Button className="flex-1 min-w-[160px] bg-[#7CB342] hover:bg-[#689F38]"
                      data-testid="shortlist-candidate-btn"
                      disabled={shortlistingId === selectedCandidate.candidate_id}
                      onClick={() => {
                        const jobId = selectedJobId || shortlistJobId;
                        if (!jobId) {
                          toast.error('Please select a job mandate above to shortlist this candidate');
                          return;
                        }
                        handleShortlist(selectedCandidate);
                      }}>
                      {shortlistingId === selectedCandidate.candidate_id ? (
                        <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Shortlisting...</>
                      ) : (
                        'Shortlist Candidate'
                      )}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Add as Applicant Dialog */}
      <Dialog open={!!addApplicantCandidate} onOpenChange={() => { setAddApplicantCandidate(null); setAddApplicantJobId(''); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="font-heading">Add as Applicant</DialogTitle></DialogHeader>
          {addApplicantCandidate && (
            <div className="space-y-4" data-testid="add-applicant-dialog">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                  <span className="text-[#7CB342] font-semibold">{addApplicantCandidate.name?.charAt(0)?.toUpperCase() || '?'}</span>
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-slate-900 truncate">{addApplicantCandidate.name}</p>
                  <p className="text-sm text-slate-500 truncate">{addApplicantCandidate.designation}</p>
                </div>
              </div>
              <div>
                <Label className="text-sm font-medium mb-2 block">Select Job Mandate *</Label>
                <Select value={addApplicantJobId} onValueChange={setAddApplicantJobId}>
                  <SelectTrigger data-testid="add-applicant-job-select">
                    <SelectValue placeholder="Choose a job mandate..." />
                  </SelectTrigger>
                  <SelectContent>
                    {jobs.map((job) => (
                      <SelectItem key={job.id} value={job.id}>{job.title} - {job.location}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={() => { setAddApplicantCandidate(null); setAddApplicantJobId(''); }}>Cancel</Button>
                <Button className="flex-1 bg-[#7CB342] hover:bg-[#689F38]" disabled={!addApplicantJobId || addingApplicant}
                  onClick={handleAddAsApplicant} data-testid="confirm-add-applicant-btn">
                  {addingApplicant ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <UserPlus className="w-4 h-4 mr-2" />}
                  Add to Pipeline
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
