import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../lib/auth';
import { useNavigate } from 'react-router-dom';
import { candidateBankAPI, jobAPI, matchingAPI, sourcingAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { Search, Filter, ChevronDown, ChevronUp, MapPin, Briefcase, Clock, Phone, Mail, DollarSign, Building2, GraduationCap, Users, X, UserPlus, ExternalLink, Loader2, CheckCircle, Tag, Brain } from 'lucide-react';
import { AutocompleteInput } from '../../components/shared/AutocompleteInput';

const NOTICE_OPTIONS = [
  { label: 'Any', value: '' },
  { label: 'Immediate', value: '0' },
  { label: '0-15 days', value: '15' },
  { label: '1 month', value: '30' },
  { label: '2 months', value: '60' },
  { label: '3 months', value: '90' },
  { label: '3+ months', value: '999' },
];

const INDUSTRY_OPTIONS = [
  'IT/Software', 'BFSI', 'Manufacturing', 'Healthcare', 'Telecom',
  'Retail/E-commerce', 'Consulting', 'Education', 'Real Estate',
  'Media/Entertainment', 'Logistics', 'Energy', 'Automotive', 'FMCG',
];

const EDUCATION_OPTIONS = [
  { label: 'Any', value: '' },
  { label: 'UG (B.Tech, B.E., B.Sc, BCA, etc.)', value: 'UG' },
  { label: 'PG (M.Tech, MBA, MCA, M.Sc, etc.)', value: 'PG' },
  { label: 'Doctorate (Ph.D)', value: 'DOCTORATE' },
];

export default function AdvancedSearchPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [totalFound, setTotalFound] = useState(0);
  const [jobs, setJobs] = useState([]);
  const [addApplicantCandidate, setAddApplicantCandidate] = useState(null);
  const [addApplicantJobId, setAddApplicantJobId] = useState('');
  const [addingApplicant, setAddingApplicant] = useState(false);
  const [shortlisted, setShortlisted] = useState(new Set());

  const [expandedSections, setExpandedSections] = useState({
    employment: true, education: false, additional: false,
  });

  const [filters, setFilters] = useState({
    keywords: '', excludeKeywords: '', skills: '',
    minExp: '', maxExp: '', location: '',
    industry: '', company: '', excludeCompany: '',
    designation: '', noticePeriod: '',
    educationLevel: '', gender: '',
    hasResume: false, hasPhone: false, hasEmail: false,
    smartTags: '',
  });
  // Phase 54 — Smart Re-rank toggle. When ON AND keywords are non-empty,
  // the page calls /sourcing/rerank (XGBoost LTR + k-Means + PCA) using
  // keywords as the NL query. Falls back to structured filter search if
  // the toggle is OFF or keywords are empty (legacy behaviour).
  const [smartRerank, setSmartRerank] = useState(false);
  const [rerankMeta, setRerankMeta] = useState(null);

  useEffect(() => {
    jobAPI.getAll().then(res => setJobs(res.data)).catch(() => {});
  }, []);

  const toggleSection = (section) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const update = (key, value) => setFilters(f => ({ ...f, [key]: value }));

  const handleSearch = useCallback(async () => {
    setLoading(true);
    setResults([]);
    setRerankMeta(null);
    try {
      // Phase 54 ML path: when Smart Re-rank is ON and the user provided
      // keywords, semantic search beats keyword regex on candidate_bank.
      if (smartRerank && filters.keywords?.trim()) {
        const res = await sourcingAPI.rerank({
          query: filters.keywords.trim(),
          top_k: 50,
          diversify: true,
        });
        const cands = res.data.candidates || [];
        setResults(cands);
        setTotalFound(cands.length);
        setRerankMeta({
          pool: res.data.total_pool,
          model_loaded: res.data.model_loaded,
          timing: res.data.timing_ms,
          meta: res.data.model_meta,
        });
        if (cands.length === 0) {
          toast.info('No candidates matched. Try broadening the keywords or turn off Smart Re-rank.');
        } else {
          const ms = res.data.timing_ms?.total || 0;
          toast.success(`Smart re-ranked ${cands.length} of ${res.data.total_pool} candidates (${ms}ms)`);
        }
        return;
      }

      const params = { limit: 50 };
      if (filters.keywords) params.search = filters.keywords;
      if (filters.skills) params.skills = filters.skills;
      if (filters.location) params.location = filters.location;
      if (filters.company) params.company = filters.company;
      if (filters.minExp) params.min_experience = filters.minExp;
      if (filters.maxExp) params.max_experience = filters.maxExp;
      if (filters.designation) params.designation = filters.designation;
      if (filters.industry) params.industry = filters.industry;
      if (filters.noticePeriod) params.notice_period_max = parseInt(filters.noticePeriod);
      if (filters.educationLevel) params.education_level = filters.educationLevel;
      if (filters.gender && filters.gender !== 'all') params.gender = filters.gender;
      if (filters.excludeCompany) params.exclude_company = filters.excludeCompany;
      if (filters.excludeKeywords) params.exclude_keywords = filters.excludeKeywords;
      if (filters.hasResume) params.has_resume = 'yes';
      if (filters.hasPhone) params.has_phone = true;
      if (filters.hasEmail) params.has_email = true;
      if (filters.smartTags) params.smart_tags = filters.smartTags;

      const res = await candidateBankAPI.getAll(params);
      setResults(res.data.candidates || []);
      setTotalFound(res.data.total || 0);
      if ((res.data.candidates || []).length === 0) {
        toast.info('No candidates matched. Try broadening your filters.');
      } else {
        toast.success(`Found ${res.data.total} matching candidates`);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Search failed');
    } finally {
      setLoading(false);
    }
  }, [filters, smartRerank]);

  const clearFilters = () => {
    setFilters({
      keywords: '', excludeKeywords: '', skills: '',
      minExp: '', maxExp: '', location: '',
      industry: '', company: '', excludeCompany: '',
      designation: '', noticePeriod: '',
      educationLevel: '', gender: '',
      hasResume: false, hasPhone: false, hasEmail: false,
      smartTags: '',
    });
    setResults([]);
  };

  const handleViewProfile = (candidateId) => {
    const basePath = user?.role === 'recruiter' ? '/recruiter' : user?.role === 'employer' ? '/employer' : '/admin';
    navigate(`${basePath}/naukri-profile/${candidateId}`);
  };

  const handleAddApplicant = async () => {
    if (!addApplicantJobId || !addApplicantCandidate) return;
    setAddingApplicant(true);
    try {
      const res = await matchingAPI.shortlistCandidate(addApplicantCandidate.id, addApplicantJobId);
      toast.success(`${addApplicantCandidate.name} added to ${res.data.job_title}`);
      setShortlisted(prev => new Set([...prev, addApplicantCandidate.id]));
      setAddApplicantCandidate(null);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add');
    } finally {
      setAddingApplicant(false);
    }
  };

  const activeFilterCount = Object.entries(filters).filter(([k, v]) => {
    if (typeof v === 'boolean') return v;
    return v && v !== '';
  }).length;

  return (
    <div className="space-y-6" data-testid="advanced-search-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Search Candidates</h1>
        <p className="text-slate-500 mt-1">Advanced filters to find the perfect match from {totalFound > 0 ? `${totalFound.toLocaleString()} candidates` : 'your talent bank'}</p>
      </div>

      {/* Keywords & Skills */}
      <Card className="border-slate-200">
        <CardContent className="p-5 space-y-4">
          <div>
            <Label className="text-sm font-medium mb-1.5 block">Keywords</Label>
            <AutocompleteInput value={filters.keywords} onChange={v => update('keywords', v)}
              placeholder="Enter keywords like skills, designation and company"
              field="all" className="text-sm" data-testid="search-keywords" />
            <p className="text-[10px] text-slate-400 mt-1">Searches across skills, designation, summary, headline. Synonyms auto-expanded.</p>
          </div>
          <div>
            <Label className="text-sm font-medium mb-1.5 block text-red-500">+ Exclude Keywords</Label>
            <Input value={filters.excludeKeywords} onChange={e => update('excludeKeywords', e.target.value)}
              placeholder="Comma-separated keywords to exclude" className="text-sm" data-testid="exclude-keywords" />
          </div>
          <div>
            <Label className="text-sm font-medium mb-1.5 block">IT Skills</Label>
            <AutocompleteInput value={filters.skills} onChange={v => update('skills', v)}
              placeholder="e.g. Java, React, Python (comma-separated)" field="skills"
              className="text-sm" data-testid="search-skills" />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Min Experience</Label>
              <Input type="number" min="0" value={filters.minExp} onChange={e => update('minExp', e.target.value)}
                placeholder="0" className="text-sm" data-testid="min-exp" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Max Experience</Label>
              <Input type="number" min="0" value={filters.maxExp} onChange={e => update('maxExp', e.target.value)}
                placeholder="30" className="text-sm" data-testid="max-exp" />
            </div>
            <div className="col-span-2">
              <Label className="text-xs text-slate-500 mb-1 block">Location</Label>
              <AutocompleteInput value={filters.location} onChange={v => update('location', v)}
                placeholder="e.g. Bangalore, Mumbai, Delhi" field="location"
                className="text-sm" data-testid="search-location" />
            </div>
          </div>
          <div>
            <Label className="text-xs text-slate-500 mb-1.5 block">Smart Tags</Label>
            <Input value={filters.smartTags} onChange={e => update('smartTags', e.target.value)}
              placeholder="e.g. Senior (5-10yr), Java Developer, Immediate Joiner"
              className="text-sm" data-testid="search-smart-tags" />
            <p className="text-[10px] text-slate-400 mt-1">Comma-separated. Matches candidates with ALL specified tags.</p>
          </div>
        </CardContent>
      </Card>

      {/* Employment Details */}
      <Card className="border-slate-200">
        <button className="w-full flex items-center justify-between p-5" onClick={() => toggleSection('employment')} data-testid="toggle-employment">
          <h3 className="font-heading font-semibold text-base text-slate-900 flex items-center gap-2">
            <Briefcase className="w-4 h-4 text-slate-500" /> Employment Details
          </h3>
          {expandedSections.employment ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </button>
        {expandedSections.employment && (
          <CardContent className="pt-0 pb-5 px-5 space-y-4">
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Industry</Label>
              <Select value={filters.industry || '_any'} onValueChange={v => update('industry', v === '_any' ? '' : v)}>
                <SelectTrigger className="text-sm" data-testid="filter-industry"><SelectValue placeholder="Any industry" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_any">Any Industry</SelectItem>
                  {INDUSTRY_OPTIONS.map(i => <SelectItem key={i} value={i}>{i}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Company</Label>
                <Input value={filters.company} onChange={e => update('company', e.target.value)}
                  placeholder="Search current company" className="text-sm" data-testid="filter-company" />
              </div>
              <div>
                <Label className="text-xs text-red-400 mb-1 block">Exclude Company</Label>
                <Input value={filters.excludeCompany} onChange={e => update('excludeCompany', e.target.value)}
                  placeholder="Exclude candidates from..." className="text-sm" data-testid="exclude-company" />
              </div>
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Designation</Label>
              <AutocompleteInput value={filters.designation} onChange={v => update('designation', v)}
                placeholder="e.g. Senior Software Engineer, HR Manager" field="designation"
                className="text-sm" data-testid="filter-designation" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-2 block">Notice Period / Availability</Label>
              <div className="flex flex-wrap gap-2">
                {NOTICE_OPTIONS.map(opt => (
                  <button key={opt.value} onClick={() => update('noticePeriod', filters.noticePeriod === opt.value ? '' : opt.value)}
                    className={`px-3 py-1.5 text-xs rounded-full border transition-all ${
                      filters.noticePeriod === opt.value
                        ? 'bg-[#7CB342] text-white border-[#7CB342]'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                    }`} data-testid={`notice-${opt.value || 'any'}`}>
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Education Details */}
      <Card className="border-slate-200">
        <button className="w-full flex items-center justify-between p-5" onClick={() => toggleSection('education')} data-testid="toggle-education">
          <h3 className="font-heading font-semibold text-base text-slate-900 flex items-center gap-2">
            <GraduationCap className="w-4 h-4 text-slate-500" /> Education Details
          </h3>
          {expandedSections.education ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </button>
        {expandedSections.education && (
          <CardContent className="pt-0 pb-5 px-5 space-y-4">
            <div>
              <Label className="text-xs text-slate-500 mb-2 block">Qualification Level</Label>
              <div className="flex flex-wrap gap-2">
                {EDUCATION_OPTIONS.map(opt => (
                  <button key={opt.value} onClick={() => update('educationLevel', filters.educationLevel === opt.value ? '' : opt.value)}
                    className={`px-3 py-1.5 text-xs rounded-full border transition-all ${
                      filters.educationLevel === opt.value
                        ? 'bg-[#7CB342] text-white border-[#7CB342]'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                    }`} data-testid={`edu-${opt.value || 'any'}`}>
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Additional Details */}
      <Card className="border-slate-200">
        <button className="w-full flex items-center justify-between p-5" onClick={() => toggleSection('additional')} data-testid="toggle-additional">
          <h3 className="font-heading font-semibold text-base text-slate-900 flex items-center gap-2">
            <Users className="w-4 h-4 text-slate-500" /> Additional Details
          </h3>
          {expandedSections.additional ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </button>
        {expandedSections.additional && (
          <CardContent className="pt-0 pb-5 px-5 space-y-4">
            <div>
              <Label className="text-xs text-slate-500 mb-2 block">Gender</Label>
              <div className="flex gap-2">
                {['all', 'male', 'female'].map(g => (
                  <button key={g} onClick={() => update('gender', filters.gender === g ? '' : g)}
                    className={`px-3 py-1.5 text-xs rounded-full border transition-all capitalize ${
                      filters.gender === g ? 'bg-[#7CB342] text-white border-[#7CB342]'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                    }`} data-testid={`gender-${g}`}>
                    {g === 'all' ? 'All candidates' : `${g} candidates`}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-2 block">Show only candidates with</Label>
              <div className="flex flex-wrap gap-2">
                {[
                  { key: 'hasPhone', label: 'Verified mobile', icon: Phone },
                  { key: 'hasEmail', label: 'Verified email', icon: Mail },
                  { key: 'hasResume', label: 'Attached resume', icon: Building2 },
                ].map(opt => (
                  <button key={opt.key} onClick={() => update(opt.key, !filters[opt.key])}
                    className={`px-3 py-1.5 text-xs rounded-full border transition-all flex items-center gap-1.5 ${
                      filters[opt.key] ? 'bg-[#7CB342] text-white border-[#7CB342]'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                    }`} data-testid={`toggle-${opt.key}`}>
                    <opt.icon className="w-3 h-3" /> {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Search Actions */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 sticky bottom-0 z-10 bg-white/90 backdrop-blur-sm py-3 px-1 -mx-1 border-t border-slate-100">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Filter className="w-4 h-4" />
          <span>{activeFilterCount} filter{activeFilterCount !== 1 ? 's' : ''} active</span>
          {activeFilterCount > 0 && (
            <button onClick={clearFilters} className="text-red-500 hover:underline text-xs flex items-center gap-1" data-testid="clear-all-filters">
              <X className="w-3 h-3" /> Clear all
            </button>
          )}
        </div>
        <Button onClick={handleSearch} disabled={loading} className="bg-[#7CB342] hover:bg-[#689F38] w-full sm:w-auto px-8"
          data-testid="advanced-search-btn">
          {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
          {loading ? 'Searching...' : 'Find Candidates'}
        </Button>
      </div>

      {/* Phase 54 — Smart Re-rank toggle (uses keywords as semantic query) */}
      <div className="flex flex-wrap items-center gap-3 px-1 -mt-2">
        <label
          className={`flex items-center gap-2 cursor-pointer text-sm transition-colors
            ${filters.keywords?.trim() ? 'text-slate-700 hover:text-slate-900' : 'text-slate-400 cursor-not-allowed'}`}
          title={filters.keywords?.trim() ? '' : 'Add keywords above to enable Smart Re-rank'}
        >
          <input
            type="checkbox"
            checked={smartRerank}
            disabled={!filters.keywords?.trim()}
            onChange={(e) => setSmartRerank(e.target.checked)}
            className="rounded border-slate-300 text-[#7CB342] focus:ring-[#7CB342]"
            data-testid="smart-rerank-toggle"
          />
          <Brain className={`w-4 h-4 ${filters.keywords?.trim() ? 'text-[#7CB342]' : 'text-slate-300'}`} />
          <span className="font-medium">Smart Re-rank</span>
          <span className="text-xs text-slate-400">
            (XGBoost LTR trained on your team's hires — best for natural-language searches)
          </span>
        </label>
        {rerankMeta?.timing && (
          <span className="ml-auto text-xs text-slate-500" data-testid="rerank-meta">
            {rerankMeta.pool} pool · {rerankMeta.timing.total}ms
            {rerankMeta.meta?.auc ? ` · AUC ${rerankMeta.meta.auc}` : ''}
          </span>
        )}
      </div>

      {/* Results */}
      {results.length > 0 && (
        <Card className="border-slate-200" data-testid="search-results">
          <CardHeader>
            <CardTitle className="font-heading text-lg">{totalFound.toLocaleString()} Candidates Found</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-slate-100">
              {results.map((c) => (
                <div key={c.id} className="p-4 hover:bg-slate-50 transition-colors" data-testid={`result-${c.id}`}>
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                        <span className="text-[#7CB342] font-semibold">{c.name?.charAt(0)?.toUpperCase() || '?'}</span>
                      </div>
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900 truncate">{c.name}</p>
                        <p className="text-sm text-slate-500 truncate">
                          {c.designation || c.headline}{(c.designation || c.headline) && c.current_employer ? ' at ' : ''}{c.current_employer}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap shrink-0">
                      {c.experience_years > 0 && <span className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded">{c.experience_years} yrs</span>}
                      {c.location && <span className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded flex items-center gap-1"><MapPin className="w-2.5 h-2.5" />{c.location}</span>}
                      {c.notice_period && <span className="text-xs bg-amber-50 text-amber-600 px-2 py-1 rounded flex items-center gap-1"><Clock className="w-2.5 h-2.5" />{c.notice_period}</span>}
                      {c.current_salary > 0 && <span className="text-xs bg-green-50 text-green-600 px-2 py-1 rounded">{(c.current_salary / 100000).toFixed(1)}L</span>}
                    </div>
                  </div>
                  {/* Smart Tags */}
                  {c.smart_tags?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {c.smart_tags.slice(0, 5).map(tag => (
                        <span key={tag} className="px-1.5 py-0.5 text-[10px] bg-indigo-50 text-indigo-600 rounded border border-indigo-100 font-medium">{tag}</span>
                      ))}
                      {c.smart_tags.length > 5 && <span className="text-[10px] text-indigo-400">+{c.smart_tags.length - 5}</span>}
                    </div>
                  )}
                  {/* Why this match? — LTR explanation chips (Phase 54.4) */}
                  {c.match_reasons?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5 items-center" data-testid={`match-reasons-${c.id}`}>
                      <span className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Why</span>
                      {c.match_reasons.map((r, i) => (
                        <span key={r.feature || i}
                          data-testid={`reason-chip-${c.id}-${r.feature || i}`}
                          title={`Feature: ${r.feature}${r.weight ? ` · gain ${r.weight.toFixed(1)}` : ''}`}
                          className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-50 text-emerald-700 text-[11px] rounded-full border border-emerald-200 font-medium">
                          <CheckCircle className="w-2.5 h-2.5" />
                          {r.label}
                        </span>
                      ))}
                    </div>
                  )}
                  {/* Skills */}
                  {c.skills?.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {c.skills.slice(0, 6).map(s => <span key={s} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full">{s}</span>)}
                      {c.skills.length > 6 && <span className="text-xs text-slate-400">+{c.skills.length - 6}</span>}
                    </div>
                  )}
                  {/* Actions */}
                  <div className="mt-3 flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => handleViewProfile(c.id)} data-testid={`view-${c.id}`}>
                      <ExternalLink className="w-3.5 h-3.5 mr-1.5" /> View Profile
                    </Button>
                    {shortlisted.has(c.id) ? (
                      <Button size="sm" disabled className="bg-green-600 text-white"><CheckCircle className="w-3.5 h-3.5 mr-1.5" /> Added</Button>
                    ) : (
                      <Button size="sm" variant="outline" className="border-[#7CB342] text-[#7CB342]"
                        onClick={() => setAddApplicantCandidate(c)} data-testid={`add-${c.id}`}>
                        <UserPlus className="w-3.5 h-3.5 mr-1.5" /> Add to Pipeline
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Add Applicant Dialog */}
      {addApplicantCandidate && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setAddApplicantCandidate(null)}>
          <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()} data-testid="add-applicant-dialog">
            <h3 className="font-heading font-semibold text-lg mb-4">Add to Pipeline</h3>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                <span className="text-[#7CB342] font-semibold">{addApplicantCandidate.name?.charAt(0)?.toUpperCase()}</span>
              </div>
              <div>
                <p className="font-medium">{addApplicantCandidate.name}</p>
                <p className="text-sm text-slate-500">{addApplicantCandidate.designation}</p>
              </div>
            </div>
            <Label className="text-sm mb-2 block">Select Job Mandate *</Label>
            <Select value={addApplicantJobId} onValueChange={setAddApplicantJobId}>
              <SelectTrigger><SelectValue placeholder="Choose a mandate..." /></SelectTrigger>
              <SelectContent>
                {jobs.map(j => <SelectItem key={j.id} value={j.id}>{j.title} - {j.location}</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="flex gap-3 mt-4">
              <Button variant="outline" className="flex-1" onClick={() => setAddApplicantCandidate(null)}>Cancel</Button>
              <Button className="flex-1 bg-[#7CB342] hover:bg-[#689F38]" disabled={!addApplicantJobId || addingApplicant}
                onClick={handleAddApplicant}>
                {addingApplicant ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <UserPlus className="w-4 h-4 mr-2" />}
                Add
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
