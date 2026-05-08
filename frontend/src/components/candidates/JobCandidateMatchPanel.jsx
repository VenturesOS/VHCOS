import { useEffect, useState } from 'react';
import { Sparkles, Loader2, Users } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import api from '../../lib/api';
import { toast } from 'sonner';

/**
 * Auto-match candidates to a job. Uses the Talent Graph's job-text → candidate-vector
 * cosine ranking. Results include a similarity score so recruiters can pick a cutoff.
 *
 * Usage:
 *   <JobCandidateMatchPanel jobId={job.id} onSelect={(id) => openCandidate(id)} />
 */
export default function JobCandidateMatchPanel({ jobId, onSelect }) {
  const [matches, setMatches] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    if (!jobId) return;
    setLoading(true);
    try {
      const res = await api.get(`/talent-graph/match-job/${jobId}?limit=25`);
      setMatches(res.data?.matches || []);
      if (!res.data?.matches?.length) toast.info('No semantically-matching candidates found yet.');
    } catch (err) {
      const status = err?.response?.status;
      if (status === 404) toast.error('Job not found in talent graph yet.');
      else toast.error(err?.response?.data?.detail || 'Match failed');
      setMatches([]);
    } finally {
      setLoading(false);
    }
  };

  // Auto-run once on mount so recruiters see matches immediately
  useEffect(() => {
    if (jobId) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  return (
    <Card className="border-emerald-200" data-testid="job-match-panel">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base font-heading flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-emerald-600" />
            AI-Matched Candidates
            <Badge variant="outline" className="text-[10px] uppercase tracking-wider ml-2">
              Beta
            </Badge>
          </CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={run}
            disabled={loading}
            data-testid="job-match-refresh"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Refresh'}
          </Button>
        </div>
        <p className="text-xs text-slate-500 mt-1">
          Top candidates from your bank ranked by semantic match to this job's requirements.
        </p>
      </CardHeader>
      <CardContent>
        {matches === null && loading && (
          <div className="flex items-center gap-2 text-sm text-slate-500 py-3">
            <Loader2 className="w-4 h-4 animate-spin" /> Computing matches…
          </div>
        )}

        {matches !== null && matches.length === 0 && !loading && (
          <p className="text-sm text-slate-500 py-3 flex items-center gap-2">
            <Users className="w-4 h-4" /> No matches yet — make sure your candidate bank is indexed.
          </p>
        )}

        {matches && matches.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {matches.map((m) => (
              <button
                key={m.candidate_id}
                onClick={() => onSelect?.(m.candidate_id)}
                className="text-left border border-slate-200 hover:border-emerald-400 rounded-md p-3 transition-colors"
                data-testid={`job-match-${m.candidate_id}`}
              >
                <div className="flex items-start justify-between gap-2 mb-1">
                  <p className="font-medium text-sm truncate">{m.candidate_name || 'Unknown'}</p>
                  <Badge variant="outline" className="text-[10px] flex-shrink-0">
                    {(m.score * 100).toFixed(0)}%
                  </Badge>
                </div>
                <p className="text-xs text-slate-600 truncate">
                  {m.current_designation || '—'}
                  {m.current_employer && ` @ ${m.current_employer}`}
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  {m.experience_years ? `${m.experience_years}y` : '—'}
                  {m.current_location && ` · ${m.current_location}`}
                </p>
                {m.summary && (
                  <p className="text-[11px] text-slate-500 mt-2 line-clamp-2 whitespace-pre-line">
                    {m.summary}
                  </p>
                )}
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
