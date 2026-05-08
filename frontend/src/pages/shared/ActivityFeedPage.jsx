import { useState, useEffect, useCallback } from 'react';
import { activityAPI } from '../../lib/api';
import { ActivityEntry } from '../../components/shared/CandidateActivityTimeline';
import {
  Activity, Filter, ChevronDown, BarChart3, TrendingUp
} from 'lucide-react';

export default function ActivityFeedPage() {
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState('');
  const [actions, setActions] = useState([]);
  const [showFilter, setShowFilter] = useState(false);
  const [stats, setStats] = useState(null);
  const limit = 40;

  const fetchFeed = useCallback(async () => {
    try {
      setLoading(true);
      const params = { page, limit };
      if (actionFilter) params.action = actionFilter;
      const { data } = await activityAPI.getGlobalFeed(params);
      setEntries(data.entries || []);
      setTotal(data.total || 0);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [page, actionFilter]);

  useEffect(() => {
    activityAPI.getActions().then(({ data }) => setActions(data.actions || [])).catch(() => {});
    activityAPI.getStats().then(({ data }) => setStats(data)).catch(() => {});
  }, []);

  useEffect(() => { fetchFeed(); }, [fetchFeed]);

  const topActions = stats?.by_action
    ? Object.entries(stats.by_action)
        .sort((a, b) => b[1].count - a[1].count)
        .slice(0, 5)
    : [];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100" data-testid="activity-feed-page">
      {/* Header */}
      <div className="border-b border-zinc-800/80 bg-zinc-900/40">
        <div className="max-w-5xl mx-auto px-6 py-6">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-lg bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center">
              <Activity size={18} className="text-indigo-400" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-zinc-100" data-testid="activity-feed-title">Activity Feed</h1>
              <p className="text-xs text-zinc-500">All candidate actions across the platform</p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Main feed */}
          <div className="lg:col-span-3 space-y-4">
            {/* Filter bar */}
            <div className="flex items-center justify-between bg-zinc-900/40 border border-zinc-800/60 rounded-lg px-4 py-3">
              <p className="text-xs text-zinc-500" data-testid="feed-total-count">{total} activities</p>
              <div className="relative">
                <button
                  onClick={() => setShowFilter(!showFilter)}
                  className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 px-2.5 py-1.5 rounded-md bg-zinc-800/60 border border-zinc-700/50 transition-colors"
                  data-testid="feed-filter-btn"
                >
                  <Filter size={12} />
                  {actionFilter ? actions.find(a => a.value === actionFilter)?.label || 'Filter' : 'All Actions'}
                  <ChevronDown size={12} />
                </button>
                {showFilter && (
                  <div className="absolute right-0 top-full mt-1 z-20 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl py-1 min-w-[200px] max-h-[320px] overflow-y-auto">
                    <button
                      onClick={() => { setActionFilter(''); setShowFilter(false); setPage(1); }}
                      className={`w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-700/50 ${!actionFilter ? 'text-zinc-200 font-medium' : 'text-zinc-400'}`}
                    >
                      All Actions
                    </button>
                    {actions.map(a => (
                      <button
                        key={a.value}
                        onClick={() => { setActionFilter(a.value); setShowFilter(false); setPage(1); }}
                        className={`w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-700/50 ${actionFilter === a.value ? 'text-zinc-200 font-medium' : 'text-zinc-400'}`}
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Timeline entries */}
            {loading && entries.length === 0 ? (
              <div className="flex items-center justify-center py-16" data-testid="feed-loading">
                <div className="animate-spin w-6 h-6 border-2 border-zinc-600 border-t-zinc-300 rounded-full" />
              </div>
            ) : entries.length === 0 ? (
              <div className="text-center py-16 bg-zinc-900/30 border border-zinc-800/60 rounded-lg" data-testid="feed-empty">
                <Activity className="w-10 h-10 text-zinc-700 mx-auto mb-3" />
                <p className="text-sm text-zinc-500">No activity yet</p>
                <p className="text-xs text-zinc-600 mt-1">Actions will appear here as your team works with candidates</p>
              </div>
            ) : (
              <div className="bg-zinc-900/30 border border-zinc-800/60 rounded-lg p-5">
                {entries.map(entry => (
                  <ActivityEntry key={entry.id} entry={entry} showCandidate />
                ))}
              </div>
            )}

            {/* Pagination */}
            {total > limit && (
              <div className="flex items-center justify-center gap-3 pt-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-30 px-4 py-2 rounded-md bg-zinc-800/60 border border-zinc-700/50 transition-colors"
                  data-testid="feed-prev-page"
                >
                  Previous
                </button>
                <span className="text-xs text-zinc-500">Page {page} of {Math.ceil(total / limit)}</span>
                <button
                  onClick={() => setPage(p => p + 1)}
                  disabled={page >= Math.ceil(total / limit)}
                  className="text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-30 px-4 py-2 rounded-md bg-zinc-800/60 border border-zinc-700/50 transition-colors"
                  data-testid="feed-next-page"
                >
                  Next
                </button>
              </div>
            )}
          </div>

          {/* Sidebar stats */}
          <div className="space-y-4">
            <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <BarChart3 size={14} className="text-zinc-500" />
                <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Quick Stats</h3>
              </div>
              <div className="text-2xl font-bold text-zinc-100 mb-1" data-testid="total-actions-count">
                {stats?.total_actions?.toLocaleString() || '0'}
              </div>
              <p className="text-xs text-zinc-500">Total actions logged</p>
            </div>

            {topActions.length > 0 && (
              <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <TrendingUp size={14} className="text-zinc-500" />
                  <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Top Actions</h3>
                </div>
                <div className="space-y-2.5">
                  {topActions.map(([key, val]) => (
                    <div key={key} className="flex items-center justify-between">
                      <span className="text-xs text-zinc-400 truncate">{val.label}</span>
                      <span className="text-xs font-medium text-zinc-300 tabular-nums">{val.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
