import { useState } from 'react';
import { Sparkles, Loader2, X, ExternalLink, Eye } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import api from '../../lib/api';
import { toast } from 'sonner';

/**
 * Free-form semantic search across the entire candidate bank.
 * Mounted at the top of the Candidate Bank pages for both recruiters & admins.
 *
 *   "Senior ML engineer with fintech experience, open to relocate to Bangalore"
 *
 * Returns the top-N matches with cosine score. Caller decides what to do with
 * each result via:
 *   • onSelectCandidate(result)  — open the in-page detail dialog
 *   • onViewFullProfile(id)      — navigate to the full candidate profile page
 */
export default function SemanticSearchPanel({ onSelectCandidate, onViewFullProfile }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null); // null = idle, [] = no matches
  const [loading, setLoading] = useState(false);
  // LTR Phase 1 — session id from /talent-graph/search response, round-
  // tripped to /ltr/action when the user interacts with a result. Fire-
  // and-forget so it never blocks the UX.
  const [ltrSessionId, setLtrSessionId] = useState(null);

  const logLtrAction = (candidateId, action, rank) => {
    if (!ltrSessionId || !candidateId) return;
    api.post('/ltr/action', {
      session_id: ltrSessionId,
      candidate_id: candidateId,
      action,
      rank,
    }).catch(() => {});  // never block UX
  };

  const runSearch = async () => {
    const q = (query || '').trim();
    if (q.length < 4) {
      toast.error('Type at least 4 characters');
      return;
    }
    setLoading(true);
    try {
      const res = await api.post('/talent-graph/search', {
        query: q,
        limit: 25,
        min_score: 0.4,
      });
      setResults(res.data?.matches || []);
      setLtrSessionId(res.data?.ltr_session_id || null);
    } catch (err) {
      const status = err?.response?.status;
      if (status === 404) toast.error('Talent Graph not yet indexed. Run backfill first.');
      else toast.error(err?.response?.data?.detail || 'Semantic search failed');
      setResults([]);
      setLtrSessionId(null);
    } finally {
      setLoading(false);
    }
  };

  const onKey = (e) => {
    if (e.key === 'Enter' && !loading) runSearch();
  };

  const clear = () => {
    setQuery('');
    setResults(null);
  };

  // Match-pct → colour (matches the JD-based result card colours)
  const scoreColour = (pct) => {
    if (pct >= 80) return 'text-green-700 bg-green-50 border-green-200';
    if (pct >= 65) return 'text-[#7CB342] bg-[#DCFCE7] border-[#7CB342]/30';
    if (pct >= 50) return 'text-amber-700 bg-amber-50 border-amber-200';
    return 'text-slate-600 bg-slate-50 border-slate-200';
  };

  return (
    <Card className="border-slate-200" data-testid="semantic-search-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-heading flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#7CB342]" />
          AI-powered candidate search
          <Badge variant="outline" className="ml-2 text-[10px] uppercase tracking-wider">
            Beta
          </Badge>
        </CardTitle>
        <p className="text-xs text-slate-500 mt-1">
          Search by intent — e.g. <em>"product manager with B2B SaaS in Bangalore, open to relocate"</em>.
          Results are ranked by semantic similarity, not keywords.
        </p>
      </CardHeader>
      <CardContent>
        <div className="flex gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKey}
            placeholder="Describe the candidate you're looking for…"
            disabled={loading}
            data-testid="semantic-search-input"
          />
          <Button
            onClick={runSearch}
            disabled={loading || query.trim().length < 4}
            data-testid="semantic-search-btn"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Search'}
          </Button>
          {results !== null && (
            <Button variant="ghost" onClick={clear} data-testid="semantic-search-clear">
              <X className="w-4 h-4" />
            </Button>
          )}
        </div>

        {results !== null && (
          <div className="mt-4 space-y-2" data-testid="semantic-search-results">
            {results.length === 0 ? (
              <p className="text-sm text-slate-500 py-4 text-center">
                No semantic matches found. Try broader phrasing or lower the strictness.
              </p>
            ) : (
              <>
                <p className="text-xs text-slate-500 mb-2">
                  Top {results.length} matches — ranked by cosine similarity
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {results.map((r, idx) => {
                    const pct = Math.round((r.score || 0) * 100);
                    return (
                      <div
                        key={r.candidate_id}
                        className="border border-slate-200 hover:border-[#7CB342] rounded-md p-3 transition-colors flex flex-col"
                        data-testid={`semantic-result-${r.candidate_id}`}
                      >
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <p className="font-medium text-sm truncate">
                            {r.candidate_name || 'Unknown'}
                          </p>
                          <Badge
                            className={`text-[10px] flex-shrink-0 font-bold border ${scoreColour(pct)}`}
                            title="Cosine similarity"
                            data-testid={`semantic-result-score-${r.candidate_id}`}
                          >
                            {pct}% match
                          </Badge>
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-2">
                          {r.current_designation
                            ? <>
                                {r.current_designation}
                                {r.current_employer && <span className="text-slate-500"> @ {r.current_employer}</span>}
                              </>
                            : (r.current_employer
                                ? <span className="text-slate-500">@ {r.current_employer}</span>
                                : <span className="text-slate-400 italic">Title not on record</span>)}
                        </p>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          {r.experience_years ? `${r.experience_years}y` : '—'}
                          {r.current_location && ` · ${r.current_location}`}
                          {typeof r._keyword_overlap === 'number' && r._keyword_overlap > 0 && (
                            <span
                              className="ml-2 inline-flex items-center gap-1 text-[10px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded"
                              title="Fraction of your search keywords found in the candidate's profile"
                              data-testid={`semantic-result-kwoverlap-${r.candidate_id}`}
                            >
                              {Math.round(r._keyword_overlap * 100)}% kw
                            </span>
                          )}
                        </p>
                        {r.summary && (
                          <p className="text-[11px] text-slate-500 mt-2 line-clamp-2 whitespace-pre-line">
                            {r.summary}
                          </p>
                        )}
                        <div className="flex gap-2 mt-3 pt-2 border-t border-slate-100">
                          <Button
                            size="sm"
                            variant="outline"
                            className="flex-1 h-7 text-[11px] gap-1"
                            onClick={() => {
                              logLtrAction(r.candidate_id, 'click_profile', idx);
                              onSelectCandidate?.(r);
                            }}
                            data-testid={`semantic-result-quickview-${r.candidate_id}`}
                          >
                            <Eye className="w-3 h-3" /> Quick view
                          </Button>
                          <Button
                            size="sm"
                            className="flex-1 h-7 text-[11px] gap-1 bg-[#7CB342] hover:bg-[#689F38]"
                            onClick={() => {
                              logLtrAction(r.candidate_id, 'click_profile', idx);
                              onViewFullProfile?.(r.candidate_id);
                            }}
                            data-testid={`semantic-result-fullprofile-${r.candidate_id}`}
                          >
                            <ExternalLink className="w-3 h-3" /> Full profile
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
