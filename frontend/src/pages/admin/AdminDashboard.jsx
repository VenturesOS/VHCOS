import { useState, useEffect, useMemo } from 'react';
import { statsAPI, adminAPI, targetsAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import {
  Users, Briefcase, FileText, Building2, Database, UserPlus,
  Eye, GitBranch, Trophy, AlertTriangle, Clock, TrendingUp,
  ArrowRight, Zap, Key, Cpu, CheckCircle2, BarChart3, Target,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import DailyDigestWidget from '../../components/admin/dashboard/DailyDigestWidget';

const envUrl = process.env.REACT_APP_BACKEND_URL;
const API_BASE = envUrl ? `${envUrl.replace(/\/+$/, '')}/api` : '/api';
function getToken() { return localStorage.getItem('vhc_token'); }

const STAGE_LABELS = { sourced: 'Sourced', submitted_to_client: 'Submitted', shortlisted: 'Shortlisted', interview: 'Interviewed', offered: 'Offered', hired: 'Hired', joined: 'Joined', rejected: 'Rejected', on_hold: 'On Hold' };
const STAGE_COLORS = { sourced: '#94a3b8', submitted_to_client: '#06b6d4', shortlisted: '#d97706', interview: '#8b5cf6', offered: '#059669', hired: '#10b981', joined: '#14b8a6', rejected: '#dc2626', on_hold: '#6b7280' };
const FUNNEL_ORDER = ['sourced', 'submitted_to_client', 'shortlisted', 'interview', 'offered', 'hired', 'joined'];

const fmtINRShort = (n) => {
  if (n === undefined || n === null) return '—';
  const v = Number(n);
  if (v >= 10000000) return `₹${(v / 10000000).toFixed(2)}Cr`;
  if (v >= 100000) return `₹${(v / 100000).toFixed(1)}L`;
  return `₹${v.toLocaleString('en-IN')}`;
};

function StatCard({ icon: Icon, label, value, sub, color, bg, onClick, testId }) {
  return (
    <Card className={`border-slate-200/80 hover:shadow-md transition-all ${onClick ? 'cursor-pointer' : ''}`}
      onClick={onClick} data-testid={testId}>
      <CardContent className="p-4">
        <div className="flex items-center gap-2.5 mb-2">
          <div className={`w-9 h-9 rounded-xl ${bg} flex items-center justify-center`}>
            <Icon className={`w-4.5 h-4.5 ${color}`} />
          </div>
          <span className="text-xs text-slate-500 font-medium">{label}</span>
        </div>
        <p className="text-2xl font-bold text-slate-900">{typeof value === 'number' ? value.toLocaleString() : value}</p>
        {sub && <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function ExtractionQualityCard() {
  // Moved to Data Quality page — retained here as a no-op for backwards
  // compatibility in case any other file still imports this component.
  return null;
}

const FUNNEL_STAGE_COLORS = {
  sourced: 'bg-slate-400', applied: 'bg-blue-400', shortlisted: 'bg-cyan-400',
  submitted_to_client: 'bg-indigo-400', interview: 'bg-violet-400',
  offered: 'bg-amber-400', hired: 'bg-emerald-400', joined: 'bg-green-500',
};
const FUNNEL_STAGE_LABELS = {
  sourced: 'Sourced', applied: 'Applied', shortlisted: 'Shortlisted',
  submitted_to_client: 'Submitted', interview: 'Interview',
  offered: 'Offered', hired: 'Hired', joined: 'Joined',
};

function HiringFunnelWidget() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState('30');
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    adminAPI.getHiringFunnel({ days: parseInt(days, 10) })
      .then((r) => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [days]);

  if (loading) {
    return (
      <Card className="border-slate-200/80" data-testid="hiring-funnel-widget">
        <CardContent className="py-8 text-center text-slate-400 text-sm">Loading hiring funnel…</CardContent>
      </Card>
    );
  }
  if (!data || !data.funnel?.length) return null;
  const maxCount = Math.max(...data.funnel.map((s) => s.count), 1);

  return (
    <Card className="border-slate-200/80" data-testid="hiring-funnel-widget">
      <CardHeader className="pb-2 pt-4 px-4 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
          <BarChart3 className="w-4 h-4 text-violet-600" /> Hiring Funnel
        </CardTitle>
        <div className="flex items-center gap-2">
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger className="w-28 h-7 text-xs" data-testid="hiring-funnel-period">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
              <SelectItem value="180">180 days</SelectItem>
            </SelectContent>
          </Select>
          <button
            onClick={() => navigate('/admin/hiring-funnel')}
            className="text-[11px] text-violet-600 hover:underline"
            data-testid="hiring-funnel-deep-dive"
          >
            Full view →
          </button>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-2">
        {data.funnel.map((s) => {
          const w = (s.count / maxCount) * 100;
          return (
            <div key={s.stage} className="flex items-center gap-2">
              <span className="text-[11px] text-slate-500 w-24 truncate">
                {FUNNEL_STAGE_LABELS[s.stage] || s.stage}
              </span>
              <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${FUNNEL_STAGE_COLORS[s.stage] || 'bg-slate-400'}`}
                  style={{ width: `${w}%` }}
                />
              </div>
              <span className="text-[11px] font-semibold text-slate-700 w-12 text-right">
                {s.count.toLocaleString()}
              </span>
              {typeof s.conversion_pct === 'number' && (
                <span className="text-[10px] text-slate-400 w-10 text-right">{s.conversion_pct}%</span>
              )}
            </div>
          );
        })}
        {data.summary && (
          <div className="pt-2 mt-2 border-t border-slate-100 grid grid-cols-3 gap-2 text-center">
            <div>
              <p className="text-[10px] text-slate-400 uppercase tracking-wider">Avg time to hire</p>
              <p className="text-sm font-bold text-slate-800">{data.summary.avg_time_to_hire_days || '—'}d</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-400 uppercase tracking-wider">Conv. sourced→hired</p>
              <p className="text-sm font-bold text-slate-800">{data.summary.overall_conversion_pct || 0}%</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-400 uppercase tracking-wider">Active jobs</p>
              <p className="text-sm font-bold text-slate-800">{data.summary.active_jobs || 0}</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [company, setCompany] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    targetsAPI.companySummary().then(({ data }) => setCompany(data)).catch(() => {});
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const statsRes = await statsAPI.admin();
        setStats(statsRes.data);
      } catch {
        toast.error('Failed to load dashboard stats');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Memoize expensive computations (must be before any early returns)
  const funnelData = useMemo(() => {
    const funnel = stats?.hiring_funnel || {};
    return FUNNEL_ORDER
      .filter(s => funnel[s] > 0)
      .map(s => ({ stage: STAGE_LABELS[s] || s, count: funnel[s] || 0, fill: STAGE_COLORS[s] || '#94a3b8' }));
  }, [stats?.hiring_funnel]);

  const sortedPipelineStages = useMemo(() => {
    const stages = stats?.pipeline_stages || {};
    return Object.entries(stages).sort((a, b) => b[1] - a[1]).slice(0, 7);
  }, [stats?.pipeline_stages]);

  const pipelineMax = useMemo(() => {
    return sortedPipelineStages.length > 0 ? Math.max(...sortedPipelineStages.map(([, c]) => c)) : 0;
  }, [sortedPipelineStages]);

  if (loading) {
    return <div className="flex items-center justify-center h-64" data-testid="dashboard-loading"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>;
  }

  const today = stats?.today || {};
  const velocity = stats?.capture_velocity || [];
  const topRecruiters = stats?.top_recruiters_week || [];

  return (
    <div className="space-y-5 p-1" data-testid="admin-dashboard">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-0.5">Platform overview at a glance</p>
      </div>

      {/* Today's Snapshot */}
      <Card className="border-blue-100 bg-gradient-to-r from-blue-50/50 to-transparent" data-testid="today-snapshot">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-blue-900 flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-blue-600" /> Today's Pulse
            </h2>
            <span className="text-[10px] text-blue-400">{new Date().toLocaleDateString('en-IN', { weekday: 'long', month: 'short', day: 'numeric' })}</span>
          </div>
          <div className="grid grid-cols-4 gap-3">
            <div className="text-center">
              <p className="text-2xl font-bold text-blue-700">{today.active_users || 0}</p>
              <p className="text-[10px] text-slate-500">Active Users</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-600">{today.captures || 0}</p>
              <p className="text-[10px] text-slate-500">Profiles Captured</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-violet-600">{today.views || 0}</p>
              <p className="text-[10px] text-slate-500">Profiles Viewed</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-amber-600">{today.stage_changes || 0}</p>
              <p className="text-[10px] text-slate-500">Stage Changes</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Company revenue target roll-up (2026-09-17) */}
      <div className="grid grid-cols-3 gap-3" data-testid="admin-target-boxes">
        <StatCard icon={Target} label={`Company target ${company?.year || ''}`}
                  value={fmtINRShort(company?.total_target)}
                  sub="Jan–Dec · all teams"
                  color="text-[#7CB342]" bg="bg-[#DCFCE7]" testId="stat-company-target"
                  onClick={() => navigate('/admin/teams')} />
        <StatCard icon={TrendingUp} label="Revenue achieved"
                  value={fmtINRShort(company?.total_achieved)}
                  sub={`${company?.total_joinings ?? 0} joinings booked`}
                  color="text-emerald-600" bg="bg-emerald-50" testId="stat-company-achieved"
                  onClick={() => navigate('/admin/performance-records')} />
        <StatCard icon={Trophy} label="Achievement"
                  value={`${company?.achievement_pct ?? 0}%`}
                  sub={`${company?.teams?.length ?? 0} teams`}
                  color="text-amber-600" bg="bg-amber-50" testId="stat-company-pct"
                  onClick={() => navigate('/admin/performance-records')} />
      </div>

      {/* Core Stats */}
      <div className="grid grid-cols-5 gap-3" data-testid="core-stats">
        <StatCard icon={Users} label="Users" value={stats?.total_users || 0} color="text-blue-600" bg="bg-blue-50" testId="stat-users" onClick={() => navigate('/admin/users')} />
        <StatCard icon={Briefcase} label="Active Jobs" value={stats?.total_jobs || 0} color="text-emerald-600" bg="bg-emerald-50" testId="stat-jobs" onClick={() => navigate('/admin/jobs')} />
        <StatCard icon={FileText} label="Applications" value={stats?.total_applications || 0} color="text-amber-600" bg="bg-amber-50" testId="stat-apps" onClick={() => navigate('/admin/pipeline')} />
        <StatCard icon={Database} label="Candidate Bank" value={stats?.total_candidates || 0} color="text-violet-600" bg="bg-violet-50" testId="stat-candidates" onClick={() => navigate('/admin/candidate-bank')} />
        <StatCard icon={Building2} label="Companies" value={stats?.total_companies || 0} color="text-cyan-600" bg="bg-cyan-50" testId="stat-companies" onClick={() => navigate('/admin/companies')} />
      </div>

      {/* Middle Row: Top Recruiters + Capture Velocity + Alerts */}
      <div className="grid grid-cols-3 gap-4">
        {/* Top Recruiters */}
        <Card className="border-slate-200/80" data-testid="top-recruiters">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
              <Trophy className="w-4 h-4 text-amber-500" /> Top Recruiters
              <span className="text-[10px] text-slate-400 font-normal ml-1">this week</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 space-y-2">
            {topRecruiters.map((r, i) => (
              <div key={`recruiter-${r.name}`} className="flex items-center gap-2.5">
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold
                  ${i === 0 ? 'bg-amber-100 text-amber-700' : i === 1 ? 'bg-slate-200 text-slate-600' : i === 2 ? 'bg-orange-100 text-orange-700' : 'bg-slate-100 text-slate-500'}`}>
                  {i + 1}
                </span>
                <span className="text-sm text-slate-700 flex-1 truncate">{r.name}</span>
                <span className="text-xs font-semibold text-emerald-600">{r.captures}</span>
              </div>
            ))}
            {topRecruiters.length === 0 && <p className="text-xs text-slate-400">No captures this week</p>}
          </CardContent>
        </Card>

        {/* Capture Velocity */}
        <Card className="border-slate-200/80" data-testid="capture-velocity">
          <CardHeader className="pb-1 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4 text-blue-600" /> Capture Velocity
              <span className="text-[10px] text-slate-400 font-normal ml-1">last 7 days</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-1 pb-2">
            {velocity.length > 0 ? (
              <ResponsiveContainer width="100%" height={130}>
                <BarChart data={velocity}>
                  <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#94a3b8' }} tickFormatter={d => d.slice(5)} />
                  <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} width={30} />
                  <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} labelFormatter={d => new Date(d).toLocaleDateString('en-IN', { weekday: 'short', month: 'short', day: 'numeric' })} />
                  <Bar dataKey="count" fill="#2563eb" radius={[3, 3, 0, 0]} name="Captures" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-slate-400 text-center py-8">No data</p>
            )}
          </CardContent>
        </Card>

        {/* Alerts & Pending Actions */}
        <Card className="border-slate-200/80" data-testid="pending-actions">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4 text-amber-500" /> Attention Needed
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 space-y-2.5">
            <div className="flex items-center justify-between p-2.5 bg-amber-50 rounded-lg cursor-pointer hover:bg-amber-100 transition-colors"
              onClick={() => navigate('/admin/pipeline')} data-testid="alert-stale">
              <div className="flex items-center gap-2">
                <Clock className="w-3.5 h-3.5 text-amber-600" />
                <span className="text-xs text-amber-800">Stale candidates ({'>'}7d)</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-sm font-bold text-amber-700">{stats?.stale_candidates || 0}</span>
                <ArrowRight className="w-3 h-3 text-amber-500" />
              </div>
            </div>
            <div className="flex items-center justify-between p-2.5 bg-red-50 rounded-lg cursor-pointer hover:bg-red-100 transition-colors"
              onClick={() => navigate('/admin/jobs')} data-testid="alert-no-apps">
              <div className="flex items-center gap-2">
                <Briefcase className="w-3.5 h-3.5 text-red-600" />
                <span className="text-xs text-red-800">Jobs with 0 applicants</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-sm font-bold text-red-700">{stats?.jobs_no_applicants || 0}</span>
                <ArrowRight className="w-3 h-3 text-red-500" />
              </div>
            </div>
            <div className="text-center pt-1">
              <span className="text-[10px] text-slate-400 cursor-pointer hover:text-blue-600" onClick={() => navigate('/admin/activity-monitor')}>
                View Activity Monitor →
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Hiring Funnel + Pipeline + Users by Role */}
      <div className="grid grid-cols-3 gap-4">
        {/* Hiring Funnel */}
        <Card className="border-slate-200/80" data-testid="hiring-funnel">
          <CardHeader className="pb-1 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
              <GitBranch className="w-4 h-4 text-purple-600" /> Hiring Funnel
              <span className="text-[10px] text-slate-400 font-normal ml-1">30 days</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-1 pb-2">
            {funnelData.length > 0 ? (
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={funnelData} layout="vertical">
                  <XAxis type="number" tick={{ fontSize: 9, fill: '#94a3b8' }} />
                  <YAxis type="category" dataKey="stage" tick={{ fontSize: 9, fill: '#64748b' }} width={75} />
                  <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                  <Bar dataKey="count" radius={[0, 3, 3, 0]} name="Count">
                    {funnelData.map((entry, i) => (
                      <rect key={entry.stage} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-slate-400 text-center py-8">No funnel data</p>
            )}
          </CardContent>
        </Card>

        {/* Pipeline Overview */}
        <Card className="border-slate-200/80" data-testid="pipeline-overview">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
              <FileText className="w-4 h-4 text-indigo-600" /> Pipeline Overview
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 space-y-1.5">
            {sortedPipelineStages.map(([stage, count]) => {
                const pct = pipelineMax > 0 ? (count / pipelineMax) * 100 : 0;
                return (
                  <div key={stage} className="flex items-center gap-2">
                    <span className="text-[11px] text-slate-500 w-20 truncate capitalize">{STAGE_LABELS[stage] || stage}</span>
                    <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: STAGE_COLORS[stage] || '#94a3b8' }} />
                    </div>
                    <span className="text-[11px] font-semibold text-slate-700 w-10 text-right">{count.toLocaleString()}</span>
                  </div>
                );
              })}
          </CardContent>
        </Card>

        {/* Users by Role */}
        <Card className="border-slate-200/80" data-testid="users-by-role">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
              <Users className="w-4 h-4 text-blue-600" /> Users by Role
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 space-y-2">
            {Object.entries(stats?.users_by_role || {}).map(([role, count]) => (
              <div key={role} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${
                    role === 'admin' ? 'bg-red-400' : role === 'recruiter' ? 'bg-blue-400' :
                    role === 'employer' ? 'bg-emerald-400' : role === 'accounts' ? 'bg-amber-400' : 'bg-slate-400'
                  }`} />
                  <span className="text-sm text-slate-700 capitalize">{role}</span>
                </div>
                <span className="text-sm font-semibold text-slate-900">{count}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Recent Applications, Anthropic API Keys moved out of Admin Dashboard.
          Regex Parser Quality relocated to the Data Quality page. */}

      {/* Hiring Funnel widget — moved here from standalone sidebar item on
          2026-05-01. Full deep-dive view still available at /admin/hiring-funnel */}
      <HiringFunnelWidget />

      {/* Phase 54.15 — Daily Team Performance Digest. WhatsApp-ready message
          for daily team standup. Auto-generates at 18:00 IST. */}
      <DailyDigestWidget />
    </div>
  );
}
