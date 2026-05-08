import { useState, useEffect, useCallback } from 'react';
import { activityAPI } from '../../lib/api';
import {
  UserPlus, RefreshCw, Upload, Send, Link, ArrowRight,
  MessageSquare, CheckCircle, Target, Eye, Star, XCircle,
  Edit, Activity, Filter, ChevronDown
} from 'lucide-react';

const ICON_MAP = {
  UserPlus, RefreshCw, Upload, Send, Link, ArrowRight,
  MessageSquare, CheckCircle, Target, Eye, Star, XCircle,
  Edit, Activity, Replace: RefreshCw,
};

const COLOR_MAP = {
  emerald: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  blue: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  violet: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
  sky: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  amber: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  slate: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
  green: 'bg-green-500/15 text-green-400 border-green-500/30',
  orange: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  gray: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  yellow: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  red: 'bg-red-500/15 text-red-400 border-red-500/30',
  indigo: 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30',
};

const DOT_COLOR_MAP = {
  emerald: 'bg-emerald-400', blue: 'bg-blue-400', violet: 'bg-violet-400',
  sky: 'bg-sky-400', amber: 'bg-amber-400', slate: 'bg-slate-400',
  green: 'bg-green-400', orange: 'bg-orange-400', gray: 'bg-gray-400',
  yellow: 'bg-yellow-400', red: 'bg-red-400', indigo: 'bg-indigo-400',
};

function TimeAgo({ timestamp }) {
  const now = new Date();
  const t = new Date(timestamp);
  const diff = (now - t) / 1000;
  if (diff < 60) return <span>just now</span>;
  if (diff < 3600) return <span>{Math.floor(diff / 60)}m ago</span>;
  if (diff < 86400) return <span>{Math.floor(diff / 3600)}h ago</span>;
  if (diff < 604800) return <span>{Math.floor(diff / 86400)}d ago</span>;
  return <span>{t.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' })}</span>;
}

function ActivityEntry({ entry, showCandidate = false }) {
  const style = entry.style || { icon: 'Activity', color: 'gray' };
  const IconComp = ICON_MAP[style.icon] || Activity;
  const colorClass = COLOR_MAP[style.color] || COLOR_MAP.gray;
  const dotColor = DOT_COLOR_MAP[style.color] || DOT_COLOR_MAP.gray;

  return (
    <div className="relative flex gap-4 pb-6 last:pb-0 group" data-testid={`activity-entry-${entry.action}`}>
      {/* Timeline line */}
      <div className="absolute left-[17px] top-10 bottom-0 w-px bg-zinc-700/50 group-last:hidden" />
      
      {/* Icon */}
      <div className={`relative z-10 flex-shrink-0 w-9 h-9 rounded-full border flex items-center justify-center ${colorClass}`}>
        <IconComp size={15} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pt-0.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            {showCandidate && entry.candidate_name && (
              <span className="text-sm font-medium text-zinc-200 mr-1.5">{entry.candidate_name}</span>
            )}
            <p className="text-sm text-zinc-300 leading-relaxed">{entry.description}</p>
            <div className="flex items-center gap-2 mt-1">
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotColor}`} />
              <span className="text-xs text-zinc-500">{entry.performed_by_name}</span>
              <span className="text-xs text-zinc-600">·</span>
              <span className="text-xs text-zinc-500">
                <TimeAgo timestamp={entry.timestamp} />
              </span>
            </div>
          </div>
          <span className="text-[10px] uppercase tracking-wider text-zinc-600 font-medium whitespace-nowrap mt-1 px-1.5 py-0.5 rounded bg-zinc-800/50">
            {entry.action_label || entry.action}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function CandidateActivityTimeline({ candidateId }) {
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState('');
  const [actions, setActions] = useState([]);
  const [showFilter, setShowFilter] = useState(false);
  const limit = 30;

  const fetchActivity = useCallback(async () => {
    try {
      setLoading(true);
      const params = { page, limit };
      if (actionFilter) params.action = actionFilter;
      const { data } = await activityAPI.getCandidateActivity(candidateId, params);
      setEntries(data.entries || []);
      setTotal(data.total || 0);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [candidateId, page, actionFilter]);

  useEffect(() => {
    activityAPI.getActions().then(({ data }) => setActions(data.actions || [])).catch(() => {});
  }, []);

  useEffect(() => { fetchActivity(); }, [fetchActivity]);

  if (loading && entries.length === 0) {
    return (
      <div className="flex items-center justify-center py-12" data-testid="activity-loading">
        <div className="animate-spin w-5 h-5 border-2 border-zinc-600 border-t-zinc-300 rounded-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="candidate-activity-timeline">
      {/* Filter bar */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-zinc-500">{total} activities</p>
        <div className="relative">
          <button
            onClick={() => setShowFilter(!showFilter)}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 px-2.5 py-1.5 rounded-md bg-zinc-800/60 border border-zinc-700/50 transition-colors"
            data-testid="activity-filter-btn"
          >
            <Filter size={12} />
            {actionFilter ? actions.find(a => a.value === actionFilter)?.label || 'Filter' : 'All Actions'}
            <ChevronDown size={12} />
          </button>
          {showFilter && (
            <div className="absolute right-0 top-full mt-1 z-20 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl py-1 min-w-[180px]">
              <button
                onClick={() => { setActionFilter(''); setShowFilter(false); setPage(1); }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-700/50 ${!actionFilter ? 'text-zinc-200' : 'text-zinc-400'}`}
              >
                All Actions
              </button>
              {actions.map(a => (
                <button
                  key={a.value}
                  onClick={() => { setActionFilter(a.value); setShowFilter(false); setPage(1); }}
                  className={`w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-700/50 ${actionFilter === a.value ? 'text-zinc-200' : 'text-zinc-400'}`}
                >
                  {a.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Timeline */}
      {entries.length === 0 ? (
        <div className="text-center py-8" data-testid="activity-empty">
          <Activity className="w-8 h-8 text-zinc-600 mx-auto mb-2" />
          <p className="text-sm text-zinc-500">No activity recorded yet</p>
        </div>
      ) : (
        <div className="pl-1">
          {entries.map(entry => (
            <ActivityEntry key={entry.id} entry={entry} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > limit && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-30 px-3 py-1 rounded bg-zinc-800/60 border border-zinc-700/50"
          >
            Previous
          </button>
          <span className="text-xs text-zinc-500">Page {page} of {Math.ceil(total / limit)}</span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={page >= Math.ceil(total / limit)}
            className="text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-30 px-3 py-1 rounded bg-zinc-800/60 border border-zinc-700/50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

export { ActivityEntry, TimeAgo };
