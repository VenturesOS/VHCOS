import { useEffect, useState } from 'react';
import { Users, Loader2 } from 'lucide-react';
import { Badge } from '../ui/badge';
import api from '../../lib/api';

/**
 * Compact "Find similar candidates" panel rendered inside the candidate
 * detail dialog. Pulls top-K vector-similar candidates from the Talent Graph.
 */
export default function SimilarCandidatesPanel({ candidateId, onSelect }) {
  const [matches, setMatches] = useState(null); // null = loading
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!candidateId) return;
    let cancelled = false;
    setMatches(null);
    setError(null);
    api
      .get(`/talent-graph/similar/${candidateId}?limit=8`)
      .then((res) => {
        if (cancelled) return;
        setMatches(res.data?.matches || []);
      })
      .catch((err) => {
        if (cancelled) return;
        const status = err?.response?.status;
        if (status === 404) {
          setError('not_indexed');
        } else {
          setError('error');
        }
        setMatches([]);
      });
    return () => {
      cancelled = true;
    };
  }, [candidateId]);

  return (
    <div data-testid="similar-candidates-panel" className="border-t border-slate-200 pt-4 mt-4">
      <div className="flex items-center gap-2 mb-3">
        <Users className="w-4 h-4 text-[#7CB342]" />
        <h4 className="font-heading text-sm font-semibold">Similar candidates</h4>
        <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
          AI
        </Badge>
      </div>

      {matches === null && (
        <div className="flex items-center gap-2 text-xs text-slate-500 py-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Computing matches…
        </div>
      )}

      {matches !== null && matches.length === 0 && (
        <p className="text-xs text-slate-500 py-2">
          {error === 'not_indexed'
            ? 'This candidate has not been indexed yet — open them once and they auto-index, or run the admin backfill.'
            : 'No similar candidates found in the talent graph.'}
        </p>
      )}

      {matches && matches.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {matches.map((m) => (
            <button
              key={m.candidate_id}
              onClick={() => onSelect?.(m.candidate_id)}
              className="text-left border border-slate-200 hover:border-[#7CB342] rounded-md p-2.5 transition-colors"
              data-testid={`similar-candidate-${m.candidate_id}`}
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <p className="font-medium text-xs truncate">{m.candidate_name || 'Unknown'}</p>
                <Badge variant="outline" className="text-[9px] flex-shrink-0">
                  {(m.score * 100).toFixed(0)}%
                </Badge>
              </div>
              <p className="text-[11px] text-slate-600 truncate">
                {m.current_designation || '—'}
                {m.current_employer && ` @ ${m.current_employer}`}
              </p>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {m.experience_years ? `${m.experience_years}y` : '—'}
                {m.current_location && ` · ${m.current_location}`}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
