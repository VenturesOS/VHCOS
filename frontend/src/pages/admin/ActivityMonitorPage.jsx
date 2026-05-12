import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
} from 'recharts';
import {
  Users, Activity, Eye, UserPlus, Briefcase, ClipboardList,
  LogIn, Upload, FileText, MessageSquare, GitBranch, RefreshCw,
  TrendingUp, TrendingDown, AlertTriangle, Calendar, Search,
} from 'lucide-react';

const envUrl = process.env.REACT_APP_BACKEND_URL;
const API_BASE = envUrl ? `${envUrl.replace(/\/+$/, '')}/api` : '/api';
function getToken() { return localStorage.getItem('vhc_token'); }
async function fetchJSON(url) {
  const res = await fetch(`${API_BASE}${url}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

const METRIC_DEFS = [
  { key: 'profiles_captured', label: 'Profiles Captured', icon: UserPlus, color: 'text-emerald-600', bg: 'bg-emerald-50', desc: 'Extension + manual captures' },
  { key: 'profiles_viewed', label: 'Profiles Viewed', icon: Eye, color: 'text-blue-600', bg: 'bg-blue-50', desc: 'Profile page opens' },
  { key: 'profiles_updated', label: 'Profiles Updated', icon: RefreshCw, color: 'text-indigo-600', bg: 'bg-indigo-50', desc: 'Capture re-updates' },
  { key: 'profiles_edited', label: 'Profiles Edited', icon: FileText, color: 'text-violet-600', bg: 'bg-violet-50', desc: 'Manual field edits' },
  { key: 'applications_created', label: 'Pipeline Adds', icon: GitBranch, color: 'text-purple-600', bg: 'bg-purple-50', desc: 'Candidates added to jobs' },
  { key: 'stage_changes', label: 'Stage Changes', icon: ClipboardList, color: 'text-amber-600', bg: 'bg-amber-50', desc: 'Pipeline stage moves' },
  { key: 'mandates_created', label: 'Mandates Created', icon: Briefcase, color: 'text-cyan-600', bg: 'bg-cyan-50', desc: 'New jobs posted' },
  { key: 'trackers_created', label: 'Trackers Created', icon: ClipboardList, color: 'text-teal-600', bg: 'bg-teal-50', desc: 'Submission trackers' },
  { key: 'cv_uploads', label: 'CV Uploads', icon: Upload, color: 'text-orange-600', bg: 'bg-orange-50', desc: 'Resume file uploads' },
  { key: 'batch_uploads', label: 'Batch Uploads', icon: Upload, color: 'text-rose-600', bg: 'bg-rose-50', desc: 'Excel bulk imports' },
  { key: 'notes_added', label: 'Notes Added', icon: MessageSquare, color: 'text-pink-600', bg: 'bg-pink-50', desc: 'Candidate notes/comments' },
  { key: 'logins', label: 'Logins', icon: LogIn, color: 'text-slate-600', bg: 'bg-slate-100', desc: 'Login sessions' },
];

const ROLE_COLORS = {
  admin: 'bg-red-100 text-red-700',
  recruiter: 'bg-blue-100 text-blue-700',
  employer: 'bg-emerald-100 text-emerald-700',
  accounts: 'bg-amber-100 text-amber-700',
};

function StatCard({ icon: Icon, label, value, sub, color, bg, testId }) {
  return (
    <Card className="border-slate-200/80 hover:shadow-sm transition-shadow" data-testid={testId}>
      <CardContent className="p-3.5">
        <div className="flex items-center gap-2 mb-1.5">
          <div className={`w-7 h-7 rounded-lg ${bg} flex items-center justify-center`}>
            <Icon className={`w-3.5 h-3.5 ${color}`} />
          </div>
          <span className="text-[11px] text-slate-500 font-medium leading-tight">{label}</span>
        </div>
        <p className="text-xl font-bold text-slate-900">{typeof value === 'number' ? value.toLocaleString() : value}</p>
        {sub && <p className="text-[10px] text-slate-400 mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function UserActivityRow({ user, rank, expanded, onToggle }) {
  const isInactive = user.total_actions === 0;
  const daysSinceActive = user.last_active
    ? Math.floor((Date.now() - new Date(user.last_active).getTime()) / 86400000)
    : null;

  const qualityColor =
    user.capture_quality >= 80 ? 'text-emerald-600'
    : user.capture_quality >= 50 ? 'text-amber-600'
    : 'text-rose-600';
  const efficiencyColor =
    user.mandate_efficiency >= 25 ? 'text-emerald-600'
    : user.mandate_efficiency >= 10 ? 'text-amber-600'
    : 'text-rose-600';

  return (
    <>
      <tr
        className={`border-b border-slate-100 cursor-pointer transition-colors ${isInactive ? 'bg-red-50/40' : 'hover:bg-slate-50/80'}`}
        onClick={onToggle}
        data-testid={`user-row-${user.user_id}`}
      >
        <td className="py-2.5 px-3 text-center">
          <span className={`inline-flex w-6 h-6 items-center justify-center rounded-full text-xs font-bold
            ${rank <= 3 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>
            {rank}
          </span>
        </td>
        <td className="py-2.5 px-3">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center text-[11px] font-semibold text-slate-600">
              {user.name?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800 leading-tight">{user.name}</p>
              <p className="text-[10px] text-slate-400">{user.email}</p>
              {(user.profiles_viewed || 0) > 0 && (
                <span
                  className="inline-flex items-center gap-1 mt-0.5 px-1.5 py-0.5 rounded text-[9px] font-medium bg-blue-50 text-blue-600"
                  title="Profile views (engagement, not scored)"
                  data-testid={`views-badge-${user.user_id}`}
                >
                  <Eye className="w-2.5 h-2.5" />
                  {user.profiles_viewed.toLocaleString()} views
                </span>
              )}
            </div>
          </div>
        </td>
        <td className="py-2.5 px-3">
          <Badge variant="secondary" className={`text-[10px] ${ROLE_COLORS[user.role] || 'bg-slate-100 text-slate-600'}`}>
            {user.role}
          </Badge>
        </td>
        <td className="py-2.5 px-3 text-center" data-testid={`composite-${user.user_id}`}>
          <span className={`text-sm font-bold ${isInactive ? 'text-red-500' : 'text-slate-800'}`}>
            {(user.composite_score || 0).toFixed(1)}
          </span>
        </td>
        <td className="py-2.5 px-3 text-center text-sm text-slate-700 font-semibold" data-testid={`activity-${user.user_id}`}>
          {(user.activity_score || 0).toLocaleString()}
        </td>
        <td className="py-2.5 px-3 text-center text-sm text-emerald-600 font-medium">{user.profiles_captured}</td>
        <td className="py-2.5 px-3 text-center text-sm text-purple-600 font-medium">{(user.pipeline_points || 0).toFixed(0)}</td>
        <td className={`py-2.5 px-3 text-center text-sm font-medium ${qualityColor}`}>{(user.capture_quality || 0).toFixed(0)}%</td>
        <td className={`py-2.5 px-3 text-center text-sm font-medium ${efficiencyColor}`}>{(user.mandate_efficiency || 0).toFixed(0)}%</td>
        <td className="py-2.5 px-3 text-center">
          {isInactive ? (
            <Badge variant="destructive" className="text-[10px]">Inactive</Badge>
          ) : daysSinceActive !== null ? (
            <span className={`text-[11px] ${daysSinceActive === 0 ? 'text-emerald-600 font-medium' : daysSinceActive <= 3 ? 'text-slate-600' : 'text-amber-600'}`}>
              {daysSinceActive === 0 ? 'Today' : `${daysSinceActive}d ago`}
            </span>
          ) : (
            <span className="text-[11px] text-slate-400">-</span>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-slate-50/60">
          <td colSpan={10} className="px-4 py-3">
            <div className="grid grid-cols-6 gap-2">
              {METRIC_DEFS.map(m => (
                <div key={m.key} className="flex items-center gap-1.5 text-[11px]">
                  <m.icon className={`w-3 h-3 ${m.color}`} />
                  <span className="text-slate-500">{m.label}:</span>
                  <span className="font-semibold text-slate-700">{user[m.key]}</span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function ActivityMonitorPage({ embedded = false }) {
  const [period, setPeriod] = useState('month');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [summaryData, setSummaryData] = useState(null);
  const [trendData, setTrendData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedUser, setExpandedUser] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      let params = `period=${period}`;
      if (period === 'custom' && customStart && customEnd) {
        params += `&start_date=${new Date(customStart).toISOString()}&end_date=${new Date(customEnd + 'T23:59:59').toISOString()}`;
      }
      const [summary, trend] = await Promise.all([
        fetchJSON(`/admin/activity-monitor/summary?${params}`),
        fetchJSON(`/admin/activity-monitor/trend?${params}`),
      ]);
      setSummaryData(summary);
      setTrendData(trend);
    } catch (err) {
      toast.error('Failed to load activity data');
    } finally {
      setLoading(false);
    }
  }, [period, customStart, customEnd]);

  useEffect(() => {
    if (period !== 'custom' || (customStart && customEnd)) {
      fetchData();
    }
  }, [fetchData, period, customStart, customEnd]);

  const filteredUsers = summaryData?.users?.filter(u => {
    if (roleFilter !== 'all' && u.role !== roleFilter) return false;
    if (searchQuery && !u.name?.toLowerCase().includes(searchQuery.toLowerCase()) && !u.email?.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  }) || [];

  const pt = summaryData?.platform_totals || {};
  const periodLabel = {
    today: 'Today',
    week: 'Last 7 Days',
    month: 'Last 30 Days',
    quarter: 'Last 90 Days',
    year: 'Last 365 Days',
    all: 'All Time',
    custom: 'Custom Range',
  }[period];

  if (loading && !summaryData) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="activity-monitor-loading">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-5 p-1" data-testid="activity-monitor-page">
      {/* Header — title hidden when embedded inside Analytics tabs (the
          parent page already provides its own header). The filter row is
          always visible so the user can change period from inside the tab. */}
      <div className="flex items-center justify-between">
        {!embedded && (
          <div>
            <h1 className="text-xl font-bold text-slate-900">Activity Monitor</h1>
            <p className="text-sm text-slate-500 mt-0.5">Track platform adoption and user engagement</p>
          </div>
        )}
        {embedded && <div />}
        <div className="flex items-center gap-2">
          <Select value={period} onValueChange={setPeriod} data-testid="period-filter">
            <SelectTrigger className="w-36 h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="today">Today</SelectItem>
              <SelectItem value="week">Last 7 Days</SelectItem>
              <SelectItem value="month">Last 30 Days</SelectItem>
              <SelectItem value="quarter">Last 90 Days</SelectItem>
              <SelectItem value="year">Last Year</SelectItem>
              <SelectItem value="all">All Time</SelectItem>
              <SelectItem value="custom">Custom Range</SelectItem>
            </SelectContent>
          </Select>
          {period === 'custom' && (
            <>
              <Input type="date" value={customStart} onChange={e => setCustomStart(e.target.value)}
                className="w-32 h-8 text-xs" data-testid="custom-start-date" />
              <span className="text-xs text-slate-400">to</span>
              <Input type="date" value={customEnd} onChange={e => setCustomEnd(e.target.value)}
                className="w-32 h-8 text-xs" data-testid="custom-end-date" />
            </>
          )}
          <Button variant="outline" size="sm" onClick={fetchData} className="h-8" data-testid="refresh-btn">
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Adoption Summary Cards */}
      <div className="grid grid-cols-4 gap-3" data-testid="adoption-summary">
        <StatCard icon={Users} label="Active Users" value={pt.active_users || 0}
          sub={`${pt.inactive_users || 0} inactive of ${pt.total_users || 0}`}
          color="text-blue-600" bg="bg-blue-50" testId="stat-active-users" />
        <StatCard icon={Activity} label="Total Actions" value={pt.total_actions || 0}
          sub={periodLabel} color="text-emerald-600" bg="bg-emerald-50" testId="stat-total-actions" />
        <StatCard icon={UserPlus} label="Profiles Captured" value={pt.profiles_captured || 0}
          sub="Via extension + manual" color="text-violet-600" bg="bg-violet-50" testId="stat-captures" />
        <StatCard icon={LogIn} label="Total Logins" value={pt.logins || 0}
          sub="Session count" color="text-slate-600" bg="bg-slate-100" testId="stat-logins" />
      </div>

      {/* Second Row - Engagement Metrics */}
      <div className="grid grid-cols-6 gap-2.5">
        <StatCard icon={Eye} label="Profile Views" value={pt.profiles_viewed || 0} color="text-blue-600" bg="bg-blue-50" testId="stat-views" />
        <StatCard icon={GitBranch} label="Pipeline Adds" value={pt.applications_created || 0} color="text-purple-600" bg="bg-purple-50" testId="stat-pipeline" />
        <StatCard icon={ClipboardList} label="Stage Changes" value={pt.stage_changes || 0} color="text-amber-600" bg="bg-amber-50" testId="stat-stages" />
        <StatCard icon={Briefcase} label="Mandates" value={pt.mandates_created || 0} color="text-cyan-600" bg="bg-cyan-50" testId="stat-mandates" />
        <StatCard icon={Upload} label="CV Uploads" value={pt.cv_uploads || 0} color="text-orange-600" bg="bg-orange-50" testId="stat-cv" />
        <StatCard icon={FileText} label="Trackers" value={pt.trackers_created || 0} color="text-teal-600" bg="bg-teal-50" testId="stat-trackers" />
      </div>

      {/* Activity Trend Chart */}
      {trendData?.trend?.length > 0 && (
        <Card className="border-slate-200/80" data-testid="trend-chart">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-blue-600" /> Activity Trend
            </CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-3">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trendData.trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }}
                  tickFormatter={d => { const p = d.split('-'); return `${p[1]}/${p[2]}`; }} />
                <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                <Tooltip
                  contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e2e8f0' }}
                  labelFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short', month: 'short', day: 'numeric' })}
                />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Line type="monotone" dataKey="total" stroke="#2563eb" strokeWidth={2} dot={false} name="Total" />
                <Line type="monotone" dataKey="captured" stroke="#059669" strokeWidth={1.5} dot={false} name="Captured" />
                <Line type="monotone" dataKey="updated" stroke="#7c3aed" strokeWidth={1.5} dot={false} name="Updated" />
                <Line type="monotone" dataKey="viewed" stroke="#0891b2" strokeWidth={1.5} dot={false} name="Viewed" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* User Leaderboard */}
      <Card className="border-slate-200/80" data-testid="user-leaderboard">
        <CardHeader className="pb-2 pt-4 px-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Users className="w-4 h-4 text-blue-600" /> User Leaderboard
              <Badge variant="secondary" className="text-[10px] ml-1">{filteredUsers.length} users</Badge>
            </CardTitle>
            <div className="flex items-center gap-2 flex-wrap">
              <Select value={period} onValueChange={setPeriod}>
                <SelectTrigger className="w-32 h-7 text-xs" data-testid="leaderboard-period-filter">
                  <Calendar className="w-3 h-3 mr-1 text-slate-400" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="today">Today</SelectItem>
                  <SelectItem value="week">Last 7 Days</SelectItem>
                  <SelectItem value="month">Last 30 Days</SelectItem>
                  <SelectItem value="quarter">Last 90 Days</SelectItem>
                  <SelectItem value="year">Last Year</SelectItem>
                  <SelectItem value="all">All Time</SelectItem>
                </SelectContent>
              </Select>
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                <Input
                  placeholder="Search users..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="pl-7 h-7 w-44 text-xs"
                  data-testid="user-search"
                />
              </div>
              <Select value={roleFilter} onValueChange={setRoleFilter}>
                <SelectTrigger className="w-28 h-7 text-xs" data-testid="role-filter">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Roles</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="recruiter">Recruiter</SelectItem>
                  <SelectItem value="employer">Employer</SelectItem>
                  <SelectItem value="accounts">Accounts</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-0 pb-2">
          <div className="overflow-x-auto">
            <table className="w-full text-left" data-testid="leaderboard-table">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/50">
                  <th className="py-2 px-3 text-[10px] font-semibold text-slate-500 text-center w-12">#</th>
                  <th className="py-2 px-3 text-[10px] font-semibold text-slate-500">User</th>
                  <th className="py-2 px-3 text-[10px] font-semibold text-slate-500">Role</th>
                  <th className="py-2 px-3 text-[10px] font-semibold text-slate-700 text-center" title="Blended composite: 0.6× activity (normalised) + 0.2× quality + 0.2× efficiency">Score</th>
                  <th className="py-2 px-3 text-[10px] font-semibold text-slate-500 text-center" title="Pipeline points + 0.5× captures + 1.0× CV uploads">Activity</th>
                  <th className="py-2 px-3 text-[10px] font-semibold text-emerald-600 text-center">Captures</th>
                  <th className="py-2 px-3 text-[10px] font-semibold text-purple-600 text-center" title="Weighted: joined×10, hired×7, offered×5, interview×3, shortlisted×2, submitted×1, sourced×0.5, rejected×−1">Pipeline Pts</th>
                  <th className="py-2 px-3 text-[10px] font-semibold text-slate-500 text-center" title="Avg fill-rate of required fields, penalised for recaptures">Quality %</th>
                  <th className="py-2 px-3 text-[10px] font-semibold text-slate-500 text-center" title="Submissions ÷ captures across mandates touched">Mandate Eff %</th>
                  <th className="py-2 px-3 text-[10px] font-semibold text-slate-500 text-center">Last Active</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u, i) => (
                  <UserActivityRow
                    key={u.user_id}
                    user={u}
                    rank={i + 1}
                    expanded={expandedUser === u.user_id}
                    onToggle={() => setExpandedUser(expandedUser === u.user_id ? null : u.user_id)}
                  />
                ))}
                {filteredUsers.length === 0 && (
                  <tr><td colSpan={10} className="text-center py-8 text-sm text-slate-400">No users found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Inactive Users Alert */}
      {(pt.inactive_users || 0) > 0 && (
        <Card className="border-amber-200 bg-amber-50/30" data-testid="inactive-alert">
          <CardContent className="p-3.5 flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-amber-800">{pt.inactive_users} user{pt.inactive_users > 1 ? 's' : ''} with zero activity in {periodLabel?.toLowerCase()}</p>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {summaryData?.users?.filter(u => u.total_actions === 0).map(u => (
                  <Badge key={u.user_id} variant="outline" className="text-[10px] border-amber-300 text-amber-700">
                    {u.name} ({u.role})
                  </Badge>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
