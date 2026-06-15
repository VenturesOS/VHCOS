/**
 * TalentSearchABPage — Hybrid vs Lexical side-by-side search.
 *
 * One-week A/B validation surface for the new BGE+cross-encoder hybrid
 * retrieval. Powers `/talent-search` route. Once the team confirms
 * hybrid quality, we cut over Advanced Search to use the same endpoint
 * (`talentSearchAPI.search`) and retire the lexical-only path.
 *
 * Design:
 *   - One search box (natural language, e.g. "senior react developer in bangalore")
 *   - Two result columns: hybrid (left, default) + lexical (right, current)
 *   - Per-column timing footer so we can compare latency too
 *   - Click "View profile" → opens candidate-bank deep-link
 *   - Click "Shortlist to mandate" → existing matching/shortlist flow
 */
import { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { talentSearchAPI, jobAPI, matchingAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { Sparkles, FileText, Briefcase, MapPin, Clock, ExternalLink, Loader2, GitCompare, Zap } from 'lucide-react';

const EXAMPLE_QUERIES = [
  'senior react developer with AWS in Bangalore',
  'machine learning engineer fintech 5 to 10 years',
  'finance manager Mumbai CA qualified',
  'devops engineer kubernetes terraform remote',
  'product manager B2B SaaS Hyderabad',
];

function ResultCard({ candidate, onShortlist, onView, columnVariant }) {
  const isHybrid = columnVariant === 'hybrid';
  return (
    <Card
      className="mb-3 hover:shadow-md transition-shadow"
      data-testid={`talent-search-${columnVariant}-result-${candidate.id}`}
    >
      <CardContent className="p-4">
        <div className="flex justify-between items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3
                className="font-semibold text-base truncate"
                data-testid={`talent-search-name-${candidate.id}`}
              >
                {candidate.name || '(unnamed)'}
              </h3>
              {isHybrid && candidate.score != null && (
                <Badge variant="secondary" className="text-xs shrink-0">
                  {Number(candidate.score).toFixed(3)}
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground truncate">
              <Briefcase className="inline h-3 w-3 mr-1" />
              {candidate.current_designation || '—'}
              {candidate.current_employer ? ` @ ${candidate.current_employer}` : ''}
            </p>
            <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-xs text-muted-foreground">
              {candidate.current_location && (
                <span><MapPin className="inline h-3 w-3 mr-0.5" />{candidate.current_location}</span>
              )}
              {candidate.experience_years != null && (
                <span><Clock className="inline h-3 w-3 mr-0.5" />{candidate.experience_years} yrs</span>
              )}
              {candidate.industry && (
                <span className="truncate max-w-[160px]">{candidate.industry}</span>
              )}
            </div>
            {Array.isArray(candidate.skills) && candidate.skills.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {candidate.skills.slice(0, 6).map((s, i) => (
                  <span
                    key={i}
                    className="text-[10px] bg-muted px-1.5 py-0.5 rounded"
                  >
                    {typeof s === 'string' ? s : s?.name || ''}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex flex-col gap-1 shrink-0">
            <Button
              size="sm" variant="outline"
              onClick={() => onView(candidate)}
              data-testid={`talent-search-view-${candidate.id}`}
            >
              <ExternalLink className="h-3 w-3 mr-1" />View
            </Button>
            <Button
              size="sm" variant="ghost"
              onClick={() => onShortlist(candidate)}
              data-testid={`talent-search-shortlist-${candidate.id}`}
            >
              Shortlist
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function TalentSearchABPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [shortlistJobId, setShortlistJobId] = useState('');

  useEffect(() => {
    jobAPI.getAll().then(r => setJobs(r.data || [])).catch(() => {});
  }, []);

  const handleSearch = useCallback(async (e) => {
    e?.preventDefault?.();
    if (!query.trim() || query.trim().length < 3) {
      toast.error('Type at least 3 characters');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const res = await talentSearchAPI.search({
        query: query.trim(),
        limit: 25,
        compare_lexical: true,
      });
      setResult(res.data);
    } catch (err) {
      console.error('[TalentSearch] failed', err);
      toast.error(err?.response?.data?.detail || 'Search failed');
    } finally {
      setLoading(false);
    }
  }, [query]);

  const handleView = (c) => {
    navigate(`/candidate-bank?candidateId=${c.id}`);
  };

  const handleShortlist = useCallback(async (c) => {
    if (!shortlistJobId) {
      toast.error('Pick a mandate above first');
      return;
    }
    try {
      await matchingAPI.shortlistCandidate(c.id, shortlistJobId);
      toast.success(`Shortlisted ${c.name}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Shortlist failed');
    }
  }, [shortlistJobId]);

  const hybridCount = result?.hybrid?.length || 0;
  const lexicalCount = result?.lexical?.length || 0;

  return (
    <div className="space-y-4" data-testid="talent-search-page">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <Sparkles className="h-7 w-7 text-primary" />
          Talent Search <span className="text-sm font-normal text-muted-foreground">(A/B preview)</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Hybrid (BGE semantic + cross-encoder rerank + LTR) vs the current
          regex-only search. Side-by-side for 1 week — pick a query, see
          which side surfaces the right candidates.
        </p>
      </div>

      {/* Search box */}
      <Card>
        <CardContent className="p-4">
          <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-2">
            <Input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. senior react developer with AWS in Bangalore"
              className="flex-1"
              data-testid="talent-search-input"
            />
            <Button
              type="submit"
              disabled={loading}
              data-testid="talent-search-submit"
            >
              {loading ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Sparkles className="h-4 w-4 mr-1" />}
              Search
            </Button>
          </form>
          <div className="flex flex-wrap gap-1 mt-2">
            <span className="text-xs text-muted-foreground self-center mr-1">Try:</span>
            {EXAMPLE_QUERIES.map((q, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setQuery(q)}
                className="text-xs px-2 py-0.5 rounded border hover:bg-muted"
                data-testid={`talent-search-example-${i}`}
              >
                {q}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 mt-3 text-xs">
            <span className="text-muted-foreground">Shortlist target mandate:</span>
            <Select value={shortlistJobId} onValueChange={setShortlistJobId}>
              <SelectTrigger className="h-8 w-[260px]" data-testid="talent-search-job-select">
                <SelectValue placeholder="Pick a mandate to enable shortlisting…" />
              </SelectTrigger>
              <SelectContent>
                {jobs.map((j) => (
                  <SelectItem key={j.id} value={j.id}>
                    {j.title}{j.company_name ? ` — ${j.company_name}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* HYBRID column */}
          <Card data-testid="talent-search-hybrid-column">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-base">
                <span className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-amber-500" />
                  Hybrid (new) — {hybridCount} results
                </span>
                <Badge variant="outline" className="text-xs">
                  {result.took_ms?.hybrid || 0}ms
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 max-h-[70vh] overflow-y-auto">
              {hybridCount === 0 ? (
                <p className="text-sm text-muted-foreground py-6 text-center">No hybrid matches.</p>
              ) : (
                result.hybrid.map((c) => (
                  <ResultCard
                    key={c.id || c.name}
                    candidate={c}
                    onShortlist={handleShortlist}
                    onView={handleView}
                    columnVariant="hybrid"
                  />
                ))
              )}
            </CardContent>
          </Card>

          {/* LEXICAL column */}
          <Card data-testid="talent-search-lexical-column">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-base">
                <span className="flex items-center gap-2">
                  <GitCompare className="h-4 w-4 text-muted-foreground" />
                  Lexical (current) — {lexicalCount} results
                </span>
                <Badge variant="outline" className="text-xs">
                  {result.took_ms?.lexical || 0}ms
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 max-h-[70vh] overflow-y-auto">
              {lexicalCount === 0 ? (
                <p className="text-sm text-muted-foreground py-6 text-center">No lexical matches.</p>
              ) : (
                (result.lexical || []).map((c) => (
                  <ResultCard
                    key={c.id || c.name}
                    candidate={c}
                    onShortlist={handleShortlist}
                    onView={handleView}
                    columnVariant="lexical"
                  />
                ))
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Extracted-filters debug strip */}
      {result?.filters && Object.values(result.filters).some(
        (v) => v != null && (Array.isArray(v) ? v.length > 0 : true),
      ) && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1">
              <FileText className="h-3 w-3" /> AI-extracted filters from your query
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <pre className="text-xs bg-muted/50 rounded p-2 overflow-x-auto">
              {JSON.stringify(result.filters, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
