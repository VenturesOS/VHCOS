import { useState, useRef, useEffect, useCallback } from 'react';
import { matchingAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { Search, Upload, Sparkles, Filter, ChevronDown, ChevronUp, AlertCircle, Star, Zap, Brain, Loader2, CheckCircle } from 'lucide-react';

export default function FindCandidatesPage() {
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
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

  const [filters, setFilters] = useState({
    location: '', qualification: '', skills: '',
    minExperience: '', maxExperience: '',
  });

  useEffect(() => { loadJobs(); }, []);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const loadJobs = async () => {
    try { const res = await jobAPI.getAll(); setJobs(res.data); }
    catch { /* silently fail */ }
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

  return (
    <div className="space-y-6" data-testid="find-candidates-page">
      <div>
        <h1 className="font-heading text-3xl font-bold text-slate-900">Find Matching Candidates</h1>
        <p className="text-slate-500 mt-1">AI-powered candidate matching based on job requirements</p>
      </div>

      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-[#7CB342]" />
            Job Requirements
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="job" className="w-full">
            <TabsList className="mb-4">
              <TabsTrigger value="job">Select Existing Job</TabsTrigger>
              <TabsTrigger value="text">Paste JD Text</TabsTrigger>
              <TabsTrigger value="file">Upload JD File</TabsTrigger>
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
          </Tabs>

          {/* Filters Toggle */}
          <div className="mt-4">
            <Button variant="ghost" className="text-slate-600" onClick={() => setShowFilters(!showFilters)}
              data-testid="toggle-filters-btn">
              <Filter className="w-4 h-4 mr-2" />Must-Have Filters
              {showFilters ? <ChevronUp className="w-4 h-4 ml-2" /> : <ChevronDown className="w-4 h-4 ml-2" />}
            </Button>
            {showFilters && (
              <div className="mt-4 p-4 bg-slate-50 rounded-lg grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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

          {/* Match Mode Toggle & Search */}
          <div className="mt-6 flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-3" data-testid="match-mode-toggle">
              <Label className="text-sm text-slate-600 font-medium">Match Mode:</Label>
              <div className="flex items-center bg-slate-100 p-1 rounded-xl">
                <button onClick={() => setMatchMode('quick')} data-testid="quick-match-btn"
                  className={`flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg transition-all ${
                    matchMode === 'quick' ? 'bg-white text-[#7CB342] font-semibold shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                  <Zap className="w-4 h-4" /> Quick Match
                </button>
                <button onClick={() => setMatchMode('full_ai')} data-testid="full-ai-match-btn"
                  className={`flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg transition-all ${
                    matchMode === 'full_ai' ? 'bg-white text-indigo-600 font-semibold shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                  <Brain className="w-4 h-4" /> Full AI Match
                </button>
              </div>
              <span className="text-xs text-slate-400 max-w-[200px]">
                {matchMode === 'quick'
                  ? 'Keyword + semantic scoring. ~2-5 sec.'
                  : 'LLM-powered deep analysis. Runs in background ~1-3 min.'}
              </span>
            </div>
            <Button onClick={handleSearch} disabled={loading} className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="search-candidates-btn">
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
              Find Matching Candidates
            </Button>
          </div>
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

      {/* Results */}
      {results.length > 0 && (
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
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                        <span className="text-[#7CB342] font-semibold">{result.candidate_name?.charAt(0).toUpperCase()}</span>
                      </div>
                      <div>
                        <p className="font-medium text-slate-900">{result.candidate_name}</p>
                        <p className="text-sm text-slate-500">{result.candidate_email}</p>
                        {result.filtered_out && (
                          <p className="text-xs text-red-500 flex items-center gap-1 mt-1">
                            <AlertCircle className="w-3 h-3" />{result.filter_reason}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      {result.matched_skills?.length > 0 && (
                        <div className="hidden md:flex flex-wrap gap-1 max-w-xs">
                          {result.matched_skills.slice(0, 3).map((skill) => (
                            <span key={skill} className="px-2 py-0.5 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full">{skill}</span>
                          ))}
                        </div>
                      )}
                      <div className={`px-4 py-2 rounded-lg font-bold border ${getScoreColor(result.score)}`}>{result.score}%</div>
                    </div>
                  </div>
                  <p className="mt-2 text-sm text-slate-600 line-clamp-2">{result.explanation}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Candidate Detail Modal */}
      <Dialog open={!!selectedCandidate} onOpenChange={() => setSelectedCandidate(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle className="font-heading">Candidate Details</DialogTitle></DialogHeader>
          {selectedCandidate && (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                  <span className="text-[#7CB342] font-bold text-2xl">{selectedCandidate.candidate_name?.charAt(0).toUpperCase()}</span>
                </div>
                <div>
                  <h3 className="font-semibold text-xl">{selectedCandidate.candidate_name}</h3>
                  <p className="text-slate-500">{selectedCandidate.candidate_email}</p>
                </div>
                <div className={`ml-auto px-4 py-2 rounded-lg font-bold border ${getScoreColor(selectedCandidate.score)}`}>
                  {selectedCandidate.score}% Match
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div><p className="text-slate-500">Skill Match</p><p className="font-semibold">{selectedCandidate.skill_match_score || 'N/A'}%</p></div>
                <div><p className="text-slate-500">Experience</p><p className="font-semibold">{selectedCandidate.experience_match_score || 'N/A'}%</p></div>
                <div><p className="text-slate-500">Semantic</p><p className="font-semibold">{selectedCandidate.semantic_score != null ? `${selectedCandidate.semantic_score}%` : 'N/A'}</p></div>
              </div>
              <div>
                <h4 className="font-medium mb-2 text-[#7CB342]">Matched Skills</h4>
                <div className="flex flex-wrap gap-1">
                  {selectedCandidate.matched_skills?.map((skill) => (
                    <span key={skill} className="px-2 py-1 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full">{skill}</span>
                  ))}
                  {!selectedCandidate.matched_skills?.length && <span className="text-slate-400">None</span>}
                </div>
              </div>
              <div>
                <h4 className="font-medium mb-2 text-amber-600">Missing Skills</h4>
                <div className="flex flex-wrap gap-1">
                  {selectedCandidate.missing_skills?.map((skill) => (
                    <span key={skill} className="px-2 py-1 bg-amber-50 text-amber-600 text-xs rounded-full">{skill}</span>
                  ))}
                  {!selectedCandidate.missing_skills?.length && <span className="text-slate-400">None</span>}
                </div>
              </div>
              {selectedCandidate.strengths?.length > 0 && (
                <div>
                  <h4 className="font-medium mb-2">Strengths</h4>
                  <ul className="text-sm text-slate-600 space-y-1">
                    {selectedCandidate.strengths.map((s, i) => (
                      <li key={i} className="flex items-start gap-2"><Star className="w-4 h-4 text-[#7CB342] shrink-0 mt-0.5" />{s}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="bg-slate-50 p-4 rounded-lg">
                <h4 className="font-medium mb-2">AI Assessment</h4>
                <p className="text-sm text-slate-600">{selectedCandidate.explanation}</p>
              </div>
              <div className="border-t pt-4 mt-4">
                <p className="text-xs text-slate-400 mb-3 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />AI recommendation is advisory. Final decision requires human approval.
                </p>
                {!selectedJobId && (
                  <p className="text-xs text-amber-600 mb-3 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />Select a job above to enable shortlisting
                  </p>
                )}
                <div className="flex gap-3">
                  <Button variant="outline" className="flex-1 text-slate-600 hover:bg-slate-100"
                    data-testid="save-later-btn"
                    onClick={() => { toast.info('Candidate marked for further review'); setSelectedCandidate(null); }}>
                    Save for Later
                  </Button>
                  {shortlistedCandidates.has(selectedCandidate.candidate_id) ? (
                    <Button className="flex-1 bg-green-600 cursor-default" disabled
                      data-testid="shortlist-candidate-btn">
                      <CheckCircle className="w-4 h-4 mr-2" />
                      Already Shortlisted
                    </Button>
                  ) : (
                    <Button className="flex-1 bg-[#7CB342] hover:bg-[#689F38]"
                      data-testid="shortlist-candidate-btn"
                      disabled={!selectedJobId || shortlistingId === selectedCandidate.candidate_id}
                      onClick={() => handleShortlist(selectedCandidate)}>
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
    </div>
  );
}
