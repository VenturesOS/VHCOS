import { useState, useRef } from 'react';
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
import { Search, Upload, Sparkles, User, Filter, ChevronDown, ChevronUp, Mail, MapPin, Briefcase, Star, AlertCircle } from 'lucide-react';
import { useEffect } from 'react';

export default function FindCandidatesPage() {
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [jdText, setJdText] = useState('');
  const [jdFile, setJdFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const fileInputRef = useRef(null);
  
  // Must-have filters
  const [filters, setFilters] = useState({
    location: '',
    qualification: '',
    skills: '',
    minExperience: '',
    maxExperience: '',
  });

  useEffect(() => {
    loadJobs();
  }, []);

  const loadJobs = async () => {
    try {
      const res = await jobAPI.getAll();
      setJobs(res.data);
    } catch (error) {
      console.error('Failed to load jobs');
    }
  };

  const handleSearch = async () => {
    if (!selectedJobId && !jdText && !jdFile) {
      toast.error('Please select a job or enter job description');
      return;
    }

    setLoading(true);
    setResults([]);

    try {
      const params = {};
      
      if (selectedJobId) {
        params.job_id = selectedJobId;
      } else if (jdText) {
        params.jd_text = jdText;
      }
      
      // Add must-have filters
      if (filters.location) params.must_have_location = filters.location;
      if (filters.qualification) params.must_have_qualification = filters.qualification;
      if (filters.skills) params.must_have_skills = filters.skills.split(',').map(s => s.trim());
      if (filters.minExperience) params.min_experience = parseInt(filters.minExperience);
      if (filters.maxExperience) params.max_experience = parseInt(filters.maxExperience);

      const res = await matchingAPI.findCandidates(params);
      setResults(res.data);
      
      const matchedCount = res.data.filter(r => !r.filtered_out && r.score >= 50).length;
      toast.success(`Found ${matchedCount} matching candidates out of ${res.data.length} total`);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  const getScoreColor = (score) => {
    if (score >= 80) return 'text-green-600 bg-green-50';
    if (score >= 60) return 'text-[#7CB342] bg-[#DCFCE7]';
    if (score >= 40) return 'text-amber-600 bg-amber-50';
    return 'text-slate-500 bg-slate-100';
  };

  return (
    <div className="space-y-6" data-testid="find-candidates-page">
      <div>
        <h1 className="font-heading text-3xl font-bold text-slate-900">Find Matching Candidates</h1>
        <p className="text-slate-500 mt-1">AI-powered candidate matching based on job requirements</p>
      </div>

      {/* Search Input */}
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
                    <SelectItem key={job.id} value={job.id}>
                      {job.title} - {job.location}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </TabsContent>

            <TabsContent value="text">
              <Textarea
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="Paste the full job description here..."
                rows={6}
                data-testid="jd-text-input"
              />
            </TabsContent>

            <TabsContent value="file">
              <div className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={(e) => setJdFile(e.target.files?.[0])}
                  accept=".pdf,.doc,.docx,.txt"
                  className="hidden"
                />
                <Upload className="w-10 h-10 text-slate-400 mx-auto mb-2" />
                <p className="text-sm text-slate-500 mb-2">
                  {jdFile ? jdFile.name : 'Upload PDF, DOC, or TXT file'}
                </p>
                <Button
                  variant="outline"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Choose File
                </Button>
              </div>
            </TabsContent>
          </Tabs>

          {/* Filters Toggle */}
          <div className="mt-4">
            <Button
              variant="ghost"
              className="text-slate-600"
              onClick={() => setShowFilters(!showFilters)}
            >
              <Filter className="w-4 h-4 mr-2" />
              Must-Have Filters
              {showFilters ? <ChevronUp className="w-4 h-4 ml-2" /> : <ChevronDown className="w-4 h-4 ml-2" />}
            </Button>

            {showFilters && (
              <div className="mt-4 p-4 bg-slate-50 rounded-lg grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>Location (Required)</Label>
                  <Input
                    value={filters.location}
                    onChange={(e) => setFilters({ ...filters, location: e.target.value })}
                    placeholder="e.g., New York"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Qualification (Required)</Label>
                  <Input
                    value={filters.qualification}
                    onChange={(e) => setFilters({ ...filters, qualification: e.target.value })}
                    placeholder="e.g., Bachelor's, MBA"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Mandatory Skills (comma-separated)</Label>
                  <Input
                    value={filters.skills}
                    onChange={(e) => setFilters({ ...filters, skills: e.target.value })}
                    placeholder="e.g., Python, React"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Min Experience (years)</Label>
                  <Input
                    type="number"
                    value={filters.minExperience}
                    onChange={(e) => setFilters({ ...filters, minExperience: e.target.value })}
                    placeholder="0"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Max Experience (years)</Label>
                  <Input
                    type="number"
                    value={filters.maxExperience}
                    onChange={(e) => setFilters({ ...filters, maxExperience: e.target.value })}
                    placeholder="10"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="mt-6 flex justify-end">
            <Button
              onClick={handleSearch}
              disabled={loading}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="search-candidates-btn"
            >
              {loading ? (
                <div className="spinner w-4 h-4 border-2 border-white border-t-transparent mr-2" />
              ) : (
                <Search className="w-4 h-4 mr-2" />
              )}
              Find Matching Candidates
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {results.length > 0 && (
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading text-lg">
              Matching Candidates ({results.filter(r => !r.filtered_out).length} matched, {results.filter(r => r.filtered_out).length} filtered)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-slate-100">
              {results.map((result) => (
                <div
                  key={result.candidate_id}
                  className={`p-4 hover:bg-slate-50 transition-colors cursor-pointer ${
                    result.filtered_out ? 'opacity-50 bg-slate-50' : ''
                  }`}
                  onClick={() => setSelectedCandidate(result)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                        <span className="text-[#7CB342] font-semibold">
                          {result.candidate_name?.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <p className="font-medium text-slate-900">{result.candidate_name}</p>
                        <p className="text-sm text-slate-500">{result.candidate_email}</p>
                        {result.filtered_out && (
                          <p className="text-xs text-red-500 flex items-center gap-1 mt-1">
                            <AlertCircle className="w-3 h-3" />
                            {result.filter_reason}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      {result.matched_skills?.length > 0 && (
                        <div className="hidden md:flex flex-wrap gap-1 max-w-xs">
                          {result.matched_skills.slice(0, 3).map((skill) => (
                            <span
                              key={skill}
                              className="px-2 py-0.5 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className={`px-4 py-2 rounded-lg font-bold ${getScoreColor(result.score)}`}>
                        {result.score}%
                      </div>
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
          <DialogHeader>
            <DialogTitle className="font-heading">Candidate Details</DialogTitle>
          </DialogHeader>
          {selectedCandidate && (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                  <span className="text-[#7CB342] font-bold text-2xl">
                    {selectedCandidate.candidate_name?.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <h3 className="font-semibold text-xl">{selectedCandidate.candidate_name}</h3>
                  <p className="text-slate-500">{selectedCandidate.candidate_email}</p>
                </div>
                <div className={`ml-auto px-4 py-2 rounded-lg font-bold ${getScoreColor(selectedCandidate.score)}`}>
                  {selectedCandidate.score}% Match
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-slate-500">Skill Match</p>
                  <p className="font-semibold">{selectedCandidate.skill_match_score || 'N/A'}%</p>
                </div>
                <div>
                  <p className="text-slate-500">Experience Match</p>
                  <p className="font-semibold">{selectedCandidate.experience_match_score || 'N/A'}%</p>
                </div>
              </div>

              <div>
                <h4 className="font-medium mb-2 text-[#7CB342]">Matched Skills</h4>
                <div className="flex flex-wrap gap-1">
                  {selectedCandidate.matched_skills?.map((skill) => (
                    <span key={skill} className="px-2 py-1 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full">
                      {skill}
                    </span>
                  ))}
                  {!selectedCandidate.matched_skills?.length && <span className="text-slate-400">None</span>}
                </div>
              </div>

              <div>
                <h4 className="font-medium mb-2 text-amber-600">Missing Skills</h4>
                <div className="flex flex-wrap gap-1">
                  {selectedCandidate.missing_skills?.map((skill) => (
                    <span key={skill} className="px-2 py-1 bg-amber-50 text-amber-600 text-xs rounded-full">
                      {skill}
                    </span>
                  ))}
                  {!selectedCandidate.missing_skills?.length && <span className="text-slate-400">None</span>}
                </div>
              </div>

              <div>
                <h4 className="font-medium mb-2">Strengths</h4>
                <ul className="text-sm text-slate-600 space-y-1">
                  {selectedCandidate.strengths?.map((s, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <Star className="w-4 h-4 text-[#7CB342] shrink-0 mt-0.5" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="bg-slate-50 p-4 rounded-lg">
                <h4 className="font-medium mb-2">AI Assessment</h4>
                <p className="text-sm text-slate-600">{selectedCandidate.explanation}</p>
              </div>

              {/* Action Buttons - Phase 1: Advisory Only */}
              <div className="border-t pt-4 mt-4">
                <p className="text-xs text-slate-400 mb-3 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  AI recommendation is advisory. Final decision requires human approval.
                </p>
                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    className="flex-1 text-slate-600 hover:bg-slate-100"
                    onClick={() => {
                      toast.info('Candidate marked for further review');
                      setSelectedCandidate(null);
                    }}
                  >
                    Save for Later
                  </Button>
                  <Button
                    className="flex-1 bg-[#7CB342] hover:bg-[#689F38]"
                    onClick={() => {
                      toast.success('Candidate shortlisted! Recruiter will follow up.');
                      setSelectedCandidate(null);
                    }}
                  >
                    Shortlist Candidate
                  </Button>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
