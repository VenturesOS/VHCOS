import { useState, useEffect } from 'react';
import { matchingAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { History, Search, Clock, Users, Zap, Brain, ChevronRight, ArrowLeft, Star, AlertCircle } from 'lucide-react';

export default function MatchHistoryPage() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSearch, setSelectedSearch] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => { loadHistory(); }, []);

  const loadHistory = async () => {
    try {
      const res = await matchingAPI.getMatchHistory();
      setHistory(res.data);
    } catch {
      toast.error('Failed to load match history');
    } finally {
      setLoading(false);
    }
  };

  const viewDetail = async (item) => {
    setSelectedSearch(item);
    setDetailLoading(true);
    try {
      const res = await matchingAPI.getMatchHistoryDetail(item.id);
      setDetailData(res.data);
    } catch {
      toast.error('Failed to load match details');
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setSelectedSearch(null);
    setDetailData(null);
  };

  const formatDate = (ts) => {
    if (!ts) return '—';
    const d = new Date(ts);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const getScoreColor = (score) => {
    if (score >= 80) return 'text-green-600 bg-green-50 border-green-200';
    if (score >= 60) return 'text-[#7CB342] bg-[#DCFCE7] border-[#7CB342]/20';
    if (score >= 40) return 'text-amber-600 bg-amber-50 border-amber-200';
    return 'text-slate-500 bg-slate-100 border-slate-200';
  };

  // Detail view
  if (selectedSearch) {
    const results = detailData?.top_results || [];
    return (
      <div className="space-y-6" data-testid="match-history-detail">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={closeDetail} data-testid="back-to-history-btn">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          <div>
            <h1 className="font-heading text-2xl font-bold text-slate-900">
              {selectedSearch.job_title || 'Custom JD Search'}
            </h1>
            <p className="text-sm text-slate-500">{formatDate(selectedSearch.timestamp)}</p>
          </div>
          <span className={`ml-auto px-3 py-1 rounded-full text-xs font-medium ${
            selectedSearch.mode === 'full_ai' ? 'bg-indigo-50 text-indigo-600' : 'bg-[#DCFCE7] text-[#7CB342]'
          }`}>
            {selectedSearch.mode === 'full_ai' ? 'Full AI Match' : 'Quick Match'}
          </span>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-[#7CB342]">{selectedSearch.matched_count || 0}</p>
            <p className="text-xs text-slate-500">Matched (50%+)</p>
          </CardContent></Card>
          <Card><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-slate-700">{selectedSearch.ai_scored_count || 0}</p>
            <p className="text-xs text-slate-500">Scored</p>
          </CardContent></Card>
          <Card><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-slate-700">{selectedSearch.total_time_seconds || '—'}s</p>
            <p className="text-xs text-slate-500">Time Taken</p>
          </CardContent></Card>
          <Card><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-slate-700">{results.length}</p>
            <p className="text-xs text-slate-500">Top Results Saved</p>
          </CardContent></Card>
        </div>

        {/* Filters used */}
        {detailData?.filters && Object.values(detailData.filters).some(v => v) && (
          <Card>
            <CardContent className="py-3">
              <p className="text-sm text-slate-500 mb-1">Filters applied:</p>
              <div className="flex flex-wrap gap-2">
                {detailData.filters.location && <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">Location: {detailData.filters.location}</span>}
                {detailData.filters.min_exp != null && <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">Min Exp: {detailData.filters.min_exp}y</span>}
                {detailData.filters.max_exp != null && <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">Max Exp: {detailData.filters.max_exp}y</span>}
                {detailData.filters.skills?.map(s => <span key={s} className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">Skill: {s}</span>)}
              </div>
            </CardContent>
          </Card>
        )}

        {/* JD text if present */}
        {detailData?.jd_text && (
          <Card>
            <CardContent className="py-3">
              <p className="text-sm text-slate-500 mb-1">Job Description Used:</p>
              <p className="text-sm text-slate-700 line-clamp-3">{detailData.jd_text}</p>
            </CardContent>
          </Card>
        )}

        {/* Results */}
        {detailLoading ? (
          <div className="text-center py-12 text-slate-400">Loading results...</div>
        ) : results.length > 0 ? (
          <Card data-testid="history-results-list">
            <CardHeader><CardTitle className="font-heading text-lg">Top Matching Candidates</CardTitle></CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-slate-100">
                {results.map((r, idx) => (
                  <div key={r.candidate_id || idx} className="p-4 hover:bg-slate-50 transition-colors"
                    data-testid={`history-result-${idx}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center text-[#7CB342] font-semibold">
                          {r.candidate_name?.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-medium text-slate-900">{r.candidate_name}</p>
                          <p className="text-xs text-slate-500">{r.candidate_email}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        {r.matched_skills?.slice(0, 3).map(s => (
                          <span key={s} className="hidden md:inline px-2 py-0.5 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full">{s}</span>
                        ))}
                        <div className={`px-3 py-1.5 rounded-lg font-bold border text-sm ${getScoreColor(r.score)}`}>{r.score}%</div>
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-slate-500 line-clamp-1">{r.explanation}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="text-center py-12 text-slate-400">
            <AlertCircle className="w-8 h-8 mx-auto mb-2" />
            No saved results for this search
          </div>
        )}
      </div>
    );
  }

  // List view
  return (
    <div className="space-y-6" data-testid="match-history-page">
      <div>
        <h1 className="font-heading text-3xl font-bold text-slate-900">Match History</h1>
        <p className="text-slate-500 mt-1">Review past candidate matching searches and results</p>
      </div>

      {loading ? (
        <div className="text-center py-16 text-slate-400">Loading history...</div>
      ) : history.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <History className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500 font-medium">No match history yet</p>
            <p className="text-sm text-slate-400 mt-1">Run a candidate search from Find Candidates to see results here</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3" data-testid="history-list">
          {history.map((item) => (
            <Card key={item.id} className="hover:shadow-sm transition-shadow cursor-pointer border-slate-200"
              onClick={() => viewDetail(item)} data-testid={`history-item-${item.id}`}>
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                      {item.mode === 'full_ai'
                        ? <Brain className="w-5 h-5 text-indigo-500" />
                        : <Zap className="w-5 h-5 text-[#7CB342]" />}
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium text-slate-900 truncate">
                        {item.job_title || 'Custom JD Search'}
                      </p>
                      <div className="flex items-center gap-3 text-xs text-slate-500 mt-0.5">
                        <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{formatDate(item.timestamp)}</span>
                        <span className="flex items-center gap-1"><Users className="w-3 h-3" />{item.matched_count || 0} matched</span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          item.mode === 'full_ai' ? 'bg-indigo-50 text-indigo-600' : 'bg-[#DCFCE7] text-[#7CB342]'
                        }`}>{item.mode === 'full_ai' ? 'Full AI' : 'Quick'}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right hidden sm:block">
                      <p className="text-sm font-semibold text-slate-700">{item.ai_scored_count || 0} scored</p>
                      <p className="text-xs text-slate-400">{item.total_time_seconds ? `${item.total_time_seconds}s` : '—'}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
