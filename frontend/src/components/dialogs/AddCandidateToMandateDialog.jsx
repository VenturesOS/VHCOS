import { useState, useEffect, useCallback } from 'react';
import { candidateBankAPI, jobAPI } from '../../lib/api';
import api from '../../lib/api';
import CandidateProfileDialog from '../shared/CandidateProfileDialog';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { toast } from 'sonner';
import {
  Search, User, Mail, MapPin, Briefcase, Loader2, Check, UserPlus,
  Target, Sparkles, BookOpen, Phone, Eye,
  DollarSign, Clock, RefreshCw, Zap, AlertTriangle
} from 'lucide-react';

function scoreColor(s) {
  if (s >= 75) return 'stroke-green-500';
  if (s >= 50) return 'stroke-amber-500';
  if (s >= 30) return 'stroke-orange-500';
  return 'stroke-red-500';
}
function scoreBadge(s) {
  if (s >= 75) return 'bg-green-100 text-green-700 border-green-200';
  if (s >= 50) return 'bg-amber-100 text-amber-700 border-amber-200';
  if (s >= 30) return 'bg-orange-100 text-orange-700 border-orange-200';
  return 'bg-red-100 text-red-700 border-red-200';
}
function scoreLabel(s) {
  if (s >= 75) return 'Strong Fit';
  if (s >= 50) return 'Good Fit';
  if (s >= 30) return 'Weak Fit';
  return 'Mismatch';
}

function DimBar({ label, value }) {
  if (value == null) return null;
  const bg = value >= 75 ? 'bg-green-500' : value >= 50 ? 'bg-amber-500' : value >= 30 ? 'bg-orange-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-14 text-slate-500 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${bg}`} style={{ width: `${value}%` }} />
      </div>
      <span className="w-6 text-right text-slate-600 font-medium">{value}</span>
    </div>
  );
}

function CandidateCard({ candidate, linking, onLink, onViewProfile, showScore = false }) {
  const c = candidate;
  const cid = c.candidate_id || c.id;
  const score = c.score;

  return (
    <div className="border border-slate-200 rounded-lg hover:border-[#7CB342] transition-colors" data-testid={`candidate-card-${cid}`}>
      <div className="flex items-center gap-3 p-3">
        {/* Score circle */}
        {showScore && score != null && (
          <div className="relative w-11 h-11 shrink-0">
            <svg viewBox="0 0 36 36" className="w-11 h-11 -rotate-90">
              <circle cx="18" cy="18" r="16" fill="none" stroke="#e2e8f0" strokeWidth="3" />
              <circle cx="18" cy="18" r="16" fill="none" className={scoreColor(score)}
                strokeWidth="3" strokeDasharray={`${score} ${100 - score}`} strokeLinecap="round" />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-xs font-bold">{score}</span>
          </div>
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              className="font-medium text-slate-900 hover:text-[#7CB342] hover:underline truncate text-left"
              onClick={() => onViewProfile(cid)}
              data-testid={`view-profile-${cid}`}
            >
              {c.name || c.candidate_name}
            </button>
            {(c.designation || c.current_designation) && (
              <Badge variant="secondary" className="text-[10px] px-1.5">{c.designation || c.current_designation}</Badge>
            )}
            {showScore && score != null && (
              <Badge className={`text-[10px] px-1.5 border ${scoreBadge(score)}`}>{scoreLabel(score)}</Badge>
            )}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5 text-xs text-slate-500">
            {(c.email || c.candidate_email) && (
              <span className="flex items-center gap-1"><Mail className="w-3 h-3" /> {c.email || c.candidate_email}</span>
            )}
            {c.phone && (
              <span className="flex items-center gap-1"><Phone className="w-3 h-3" /> {c.phone}</span>
            )}
            {c.location && (
              <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {c.location}</span>
            )}
            {c.current_employer && (
              <span className="flex items-center gap-1"><Briefcase className="w-3 h-3" /> {c.current_employer}</span>
            )}
            {c.experience_years != null && (
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {c.experience_years}yr</span>
            )}
            {c.current_salary && (
              <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" /> {c.current_salary}</span>
            )}
            {c.notice_period && (
              <span className="flex items-center gap-1 text-amber-600"><Clock className="w-3 h-3" /> NP: {c.notice_period}</span>
            )}
          </div>

          {/* Matched/Missing Skills inline */}
          {showScore && (c.matched_skills?.length > 0 || c.missing_skills?.length > 0) && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {(c.matched_skills || []).slice(0, 6).map(s => (
                <Badge key={s} className="text-[10px] px-1 py-0 bg-green-100 text-green-700 border-green-200">{s}</Badge>
              ))}
              {(c.missing_skills || []).slice(0, 3).map(s => (
                <Badge key={s} variant="outline" className="text-[10px] px-1 py-0 text-red-600 border-red-200">{s}</Badge>
              ))}
            </div>
          )}

          {/* Score dimension bars */}
          {showScore && (
            <div className="mt-2 grid grid-cols-4 gap-x-3 gap-y-0.5">
              <DimBar label="Skills" value={c.skill_match_score} />
              <DimBar label="Exp" value={c.experience_match_score} />
              <DimBar label="CTC" value={c.ctc_fit_score} />
              <DimBar label="Location" value={c.location_fit_score} />
              <DimBar label="Notice" value={c.notice_fit_score} />
              <DimBar label="Stability" value={c.stability_score} />
              <DimBar label="Text Sim" value={c.tfidf_score ? Math.round(c.tfidf_score) : null} />
              {c.data_completeness != null && c.data_completeness < 60 && (
                <div className="flex items-center gap-1 text-[10px] text-amber-600 col-span-1">
                  <AlertTriangle className="w-3 h-3" /> {Math.round(c.data_completeness)}% data
                </div>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="ghost" size="icon" className="h-8 w-8"
            onClick={() => onViewProfile(cid)}
            title="View Full Profile"
            data-testid={`view-btn-${cid}`}
          >
            <Eye className="w-4 h-4 text-slate-500" />
          </Button>
          <Button
            size="sm"
            className="bg-[#7CB342] hover:bg-[#689F38] h-8 text-xs"
            onClick={() => onLink(c)}
            disabled={linking === cid}
            data-testid={`link-btn-${cid}`}
          >
            {linking === cid ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <><Check className="w-3.5 h-3.5 mr-1" /> Add</>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}


export function AddCandidateToMandateDialog({ open, onOpenChange, job, onCandidateLinked }) {
  const [search, setSearch] = useState('');
  const [candidates, setCandidates] = useState([]);
  const [sourcedCandidates, setSourcedCandidates] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [maybeCandidates, setMaybeCandidates] = useState([]);
  const [suggestionsStatus, setSuggestionsStatus] = useState('not_started');
  const [loadingSourced, setLoadingSourced] = useState(false);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [loading, setLoading] = useState(false);
  const [linking, setLinking] = useState(null);
  const [activeTab, setActiveTab] = useState('sourced');
  const [profileCandidate, setProfileCandidate] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);

  const handleViewProfile = async (candidateId) => {
    setProfileLoading(true);
    try {
      const res = await candidateBankAPI.getById(candidateId);
      setProfileCandidate(res.data);
    } catch {
      toast.error('Failed to load candidate profile');
    } finally {
      setProfileLoading(false);
    }
  };

  const loadSourcedCandidates = useCallback(async () => {
    if (!job?.id) return;
    setLoadingSourced(true);
    try {
      // Load ALL candidates captured under this mandate — no cap.
      // Backend limits each page to 100, so we loop the cursor until exhausted.
      const acc = [];
      let cursor = null;
      let safety = 20; // hard stop at 2000 candidates just in case
      do {
        const params = { mandate_id: job.id, limit: 100 };
        if (cursor) params.cursor = cursor;
        const res = await candidateBankAPI.getAll(params);
        const page = res.data?.candidates || res.data || [];
        acc.push(...page);
        cursor = res.data?.next_cursor || null;
        safety -= 1;
      } while (cursor && safety > 0);
      setSourcedCandidates(acc);
    } catch {
      setSourcedCandidates([]);
    } finally {
      setLoadingSourced(false);
    }
  }, [job?.id]);

  const loadSuggestions = useCallback(async () => {
    if (!job?.id) return;
    setLoadingSuggestions(true);
    try {
      // Talent Graph — semantic match candidates to this job's profile
      const res = await api.get(`/talent-graph/match-job/${job.id}?limit=30`);
      const matches = res.data?.matches || [];
      // Normalize to the shape `CandidateCard` expects (it reads `score` 0-100,
      // Talent Graph returns 0-1 cosine similarity → multiply)
      const mapped = matches.map((m) => ({
        candidate_id: m.candidate_id,
        id: m.candidate_id,
        name: m.candidate_name,
        designation: m.current_designation,
        current_designation: m.current_designation,
        current_employer: m.current_employer,
        location: m.current_location,
        experience_years: m.experience_years,
        score: Math.round((m.score || 0) * 100),
        ai_summary: m.summary,
      }));
      setSuggestions(mapped);
      setMaybeCandidates([]); // Talent Graph doesn't separate maybes
      setSuggestionsStatus('completed');
    } catch (err) {
      const status = err?.response?.status;
      if (status === 404) {
        setSuggestions([]);
        setSuggestionsStatus('not_started');
      } else {
        setSuggestions([]);
        setSuggestionsStatus('completed');
      }
    } finally {
      setLoadingSuggestions(false);
    }
  }, [job?.id]);

  const searchCandidates = useCallback(async (query) => {
    if (!query || query.length < 2) { setCandidates([]); return; }
    setLoading(true);
    try {
      const res = await candidateBankAPI.getAll({ search: query, page: 1, per_page: 20 });
      setCandidates(res.data.candidates || res.data || []);
    } catch {
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => searchCandidates(search), 300);
    return () => clearTimeout(t);
  }, [search, searchCandidates]);

  useEffect(() => {
    if (open) {
      setSearch(''); setCandidates([]); setLinking(null);
      setActiveTab('sourced'); setProfileCandidate(null);
      loadSourcedCandidates(); loadSuggestions();
    }
  }, [open, loadSourcedCandidates, loadSuggestions]);

  useEffect(() => {
    // Talent Graph is synchronous — no need to poll. Kept as a no-op so
    // existing render logic continues to work even if the status flips.
  }, [open, suggestionsStatus, loadSuggestions]);

  const handleRefresh = async () => {
    if (!job?.id) return;
    setSuggestionsStatus('processing'); setSuggestions([]); setMaybeCandidates([]);
    try {
      await loadSuggestions();
      toast.success('AI matches refreshed');
    } catch {
      toast.error('Failed to refresh');
      setSuggestionsStatus('completed');
    }
  };

  const handleLink = async (candidate) => {
    const cid = candidate.candidate_id || candidate.id;
    if (!job?.id || !cid) return;
    setLinking(cid);
    try {
      await candidateBankAPI.linkToJob(cid, job.id);
      toast.success(`${candidate.name || candidate.candidate_name} added to ${job.title}`);
      onCandidateLinked?.();
      setSourcedCandidates(prev => prev.filter(c => (c.candidate_id || c.id) !== cid));
      setSuggestions(prev => prev.filter(c => c.candidate_id !== cid));
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'object' && detail.message) toast.error(detail.message);
      else if (typeof detail === 'string' && detail.includes('already linked')) toast.info('Already linked to this job');
      else toast.error(detail || 'Failed to add candidate');
    } finally {
      setLinking(null);
    }
  };

  const tabs = [
    { key: 'sourced', label: 'Sourced', icon: Target, count: sourcedCandidates.length },
    { key: 'suggestions', label: 'System Suggestion', icon: Sparkles, count: suggestions.length + maybeCandidates.length },
    { key: 'search', label: 'Search Bank', icon: BookOpen, count: null },
  ];

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl max-h-[88vh] overflow-hidden flex flex-col" data-testid="add-candidate-mandate-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 font-heading">
              <UserPlus className="w-5 h-5 text-[#7CB342]" />
              Add Candidate to Mandate
            </DialogTitle>
            <DialogDescription>
              {job?.title} {job?.company_name ? `— ${job.company_name}` : ''}
            </DialogDescription>
          </DialogHeader>

          {/* Three-Tab Toggle */}
          <div className="flex gap-1 bg-slate-100 rounded-lg p-0.5" data-testid="candidate-tabs">
            {tabs.map(t => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${
                  activeTab === t.key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                }`}
                data-testid={`tab-${t.key}`}
              >
                <t.icon className="w-3.5 h-3.5" />
                {t.label}
                {t.count != null && (
                  <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] ${
                    activeTab === t.key ? 'bg-[#7CB342] text-white' : 'bg-slate-200 text-slate-600'
                  }`}>{t.count}</span>
                )}
              </button>
            ))}
          </div>

          {/* Sourced Tab */}
          {activeTab === 'sourced' && (
            <div className="flex-1 overflow-y-auto space-y-2 min-h-[200px] max-h-[500px] pr-1">
              {loadingSourced && <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 text-[#7CB342] animate-spin" /></div>}
              {!loadingSourced && sourcedCandidates.length === 0 && (
                <div className="text-center py-12 text-slate-400">
                  <Target className="w-10 h-10 mx-auto mb-3 opacity-40" />
                  <p className="font-medium">No sourced candidates yet</p>
                  <p className="text-xs mt-1">Candidates captured via the Chrome Extension with this mandate active will appear here</p>
                </div>
              )}
              {sourcedCandidates.map(c => (
                <CandidateCard key={c.id} candidate={c} linking={linking} onLink={handleLink} onViewProfile={handleViewProfile} />
              ))}
            </div>
          )}

          {/* System Suggestions Tab */}
          {activeTab === 'suggestions' && (
            <div className="flex-1 overflow-y-auto min-h-[200px] max-h-[500px] pr-1 space-y-2">
              <div className="flex items-center justify-between sticky top-0 bg-white z-10 pb-1">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  {suggestionsStatus === 'processing' && <><Loader2 className="w-3.5 h-3.5 animate-spin text-amber-500" /> Computing semantic matches...</>}
                  {suggestionsStatus === 'completed' && suggestions.length > 0 && <><Zap className="w-3.5 h-3.5 text-green-600" /> {suggestions.length} matches — sorted by similarity</>}
                  {suggestionsStatus === 'completed' && suggestions.length === 0 && <><AlertTriangle className="w-3.5 h-3.5 text-slate-400" /> No talent-graph matches yet — try Refresh once your candidate bank is indexed</>}
                  {suggestionsStatus === 'not_started' && <><AlertTriangle className="w-3.5 h-3.5 text-slate-400" /> Talent Graph not indexed — run admin backfill</>}
                </div>
                <Button variant="ghost" size="sm" className="text-xs h-7" onClick={handleRefresh} data-testid="refresh-suggestions-btn">
                  <RefreshCw className="w-3 h-3 mr-1" /> Refresh
                </Button>
              </div>
              {loadingSuggestions && suggestions.length === 0 && <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 text-[#7CB342] animate-spin" /></div>}
              {!loadingSuggestions && suggestions.length === 0 && suggestionsStatus !== 'processing' && (
                <div className="text-center py-12 text-slate-400">
                  <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-40" />
                  <p className="font-medium">No AI suggestions available</p>
                  <p className="text-xs mt-1">Click Refresh to re-run the Talent Graph match</p>
                </div>
              )}
              {suggestions.map(c => (
                <CandidateCard key={c.candidate_id} candidate={c} linking={linking} onLink={handleLink} onViewProfile={handleViewProfile} showScore />
              ))}

              {/* Maybe Candidates Section */}
              {maybeCandidates.length > 0 && (
                <div className="mt-4 pt-3 border-t border-dashed border-amber-300">
                  <div className="flex items-center gap-2 mb-2 px-1">
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                    <span className="text-xs font-semibold text-amber-700">Maybe Candidates</span>
                    <span className="text-[10px] text-amber-500 bg-amber-50 px-1.5 py-0.5 rounded-full">{maybeCandidates.length} with incomplete data</span>
                  </div>
                  <p className="text-[11px] text-slate-400 mb-2 px-1">Strong skill match but missing key data (CTC, location, etc.). Review & update their profiles for accurate scoring.</p>
                  {maybeCandidates.map(c => (
                    <CandidateCard key={c.candidate_id} candidate={c} linking={linking} onLink={handleLink} onViewProfile={handleViewProfile} showScore />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Search Bank Tab */}
          {activeTab === 'search' && (
            <>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <Input value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by name, email, skills, location..." className="pl-10"
                  data-testid="candidate-search-input" autoFocus />
              </div>
              <div className="flex-1 overflow-y-auto space-y-2 min-h-[200px] max-h-[470px] pr-1">
                {loading && <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 text-[#7CB342] animate-spin" /></div>}
                {!loading && search.length >= 2 && candidates.length === 0 && (
                  <div className="text-center py-12 text-slate-400">
                    <User className="w-10 h-10 mx-auto mb-3 opacity-40" />
                    <p className="font-medium">No candidates found for "{search}"</p>
                  </div>
                )}
                {!loading && search.length < 2 && (
                  <div className="text-center py-12 text-slate-400">
                    <BookOpen className="w-10 h-10 mx-auto mb-3 opacity-40" />
                    <p className="font-medium">Search your Candidate Bank</p>
                    <p className="text-xs mt-1">Type at least 2 characters to search</p>
                  </div>
                )}
                {candidates.map(c => (
                  <CandidateCard key={c.id} candidate={c} linking={linking} onLink={handleLink} onViewProfile={handleViewProfile} />
                ))}
              </div>
            </>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Full Profile Dialog — opens over the Add Candidate dialog */}
      <CandidateProfileDialog
        candidate={profileCandidate}
        isOpen={!!profileCandidate}
        onClose={() => setProfileCandidate(null)}
        showEditButton={false}
      />
    </>
  );
}
