import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from 'recharts';
import {
  TrendingUp, Users, Database, Zap, Clock, Activity,
  RotateCcw, Filter, Layers, FileDown,
} from 'lucide-react';

const API_BASE = '/api';

const COLORS = ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2'];

const SOURCE_LABELS = {
  naukri_extension: 'Naukri Extension',
  bulk_import: 'Bulk Import',
  public_application: 'Public Application',
  admin: 'Admin',
  recruiter: 'Recruiter',
  employer: 'Employer',
};

const STAGE_COLORS = {
  applied: '#64748b',
  shortlisted: '#2563eb',
  interview: '#7c3aed',
  offered: '#d97706',
  hired: '#059669',
  rejected: '#dc2626',
  removed: '#94a3b8',
  on_hold: '#f59e0b',
};

function getToken() {
  return localStorage.getItem('vhc_token');
}

export default function AdminAnalyticsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    employer_id: '',
    team_id: '',
    recruiter_id: '',
    date_from: '',
    date_to: '',
  });

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) params.append(k, v); });
      const res = await fetch(`${API_BASE}/analytics/admin?${params}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error('Failed to load');
      setData(await res.json());
    } catch {
      toast.error('Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { fetchAnalytics(); }, [fetchAnalytics]);

  const resetFilters = () => setFilters({ employer_id: '', team_id: '', recruiter_id: '', date_from: '', date_to: '' });

  const [exporting, setExporting] = useState(false);

  const exportPdf = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) params.append(k, v); });
      const res = await fetch(`${API_BASE}/analytics/admin/export-pdf?${params}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = res.headers.get('content-disposition')?.split('filename=')[1]?.replace(/"/g, '') || 'VHC_Analytics.pdf';
      a.click();
      URL.revokeObjectURL(url);
      toast.success('PDF exported successfully');
    } catch {
      toast.error('Failed to export PDF');
    } finally {
      setExporting(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="analytics-loading">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#2563eb]" />
      </div>
    );
  }

  const kpis = data?.kpis || {};
  const sourceDist = data?.source_distribution || [];
  const trends = data?.capture_trends || [];
  const recruiters = data?.recruiter_performance || [];
  const stageDist = data?.stage_distribution || {};
  const funnel = data?.funnel_velocity || {};
  const filterOpts = data?.filters || {};

  const stageData = Object.entries(stageDist).map(([name, value]) => ({ name, value }));
  const pieData = sourceDist.map(s => ({ name: SOURCE_LABELS[s.source] || s.source, value: s.count }));

  const hasActiveFilter = Object.values(filters).some(v => v);

  return (
    <div className="space-y-6" data-testid="admin-analytics-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Advanced Analytics</h1>
          <p className="text-slate-500 mt-1 text-sm">Capture metrics, source effectiveness, team performance & funnel velocity</p>
        </div>
        <div className="flex items-center gap-3">
          {loading && <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-[#2563eb]" />}
          <Button onClick={exportPdf} disabled={exporting || loading} variant="outline" size="sm" data-testid="export-pdf-btn" className="gap-1.5">
            <FileDown className="w-4 h-4" />
            {exporting ? 'Exporting...' : 'Export PDF'}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="border-slate-200 bg-slate-50/50" data-testid="analytics-filters">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <Filter className="w-4 h-4 text-slate-500" />
            <span className="text-sm font-medium text-slate-700">Filters</span>
            {hasActiveFilter && (
              <Button variant="ghost" size="sm" onClick={resetFilters} className="ml-auto text-xs h-7" data-testid="reset-filters-btn">
                <RotateCcw className="w-3 h-3 mr-1" /> Reset
              </Button>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Select value={filters.employer_id || "all"} onValueChange={(v) => setFilters(f => ({ ...f, employer_id: v === 'all' ? '' : v, team_id: '', recruiter_id: '' }))}>
              <SelectTrigger data-testid="filter-employer">
                <SelectValue placeholder="All Employers" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Employers</SelectItem>
                {(filterOpts.employers || []).map(e => (
                  <SelectItem key={e.id} value={e.id}>{e.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={filters.team_id || "all"} onValueChange={(v) => setFilters(f => ({ ...f, team_id: v === 'all' ? '' : v }))}>
              <SelectTrigger data-testid="filter-team">
                <SelectValue placeholder="All Teams" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Teams</SelectItem>
                {(filterOpts.teams || [])
                  .filter(t => !filters.employer_id || t.employer_id === filters.employer_id)
                  .map(t => (
                    <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                  ))}
              </SelectContent>
            </Select>

            <Select value={filters.recruiter_id || "all"} onValueChange={(v) => setFilters(f => ({ ...f, recruiter_id: v === 'all' ? '' : v }))}>
              <SelectTrigger data-testid="filter-recruiter">
                <SelectValue placeholder="All Recruiters" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Recruiters</SelectItem>
                {(filterOpts.recruiters || []).map(r => (
                  <SelectItem key={r.id} value={r.id}>{r.name} ({r.role})</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Input
              type="date"
              value={filters.date_from}
              onChange={(e) => setFilters(f => ({ ...f, date_from: e.target.value }))}
              className="bg-white"
              data-testid="filter-date-from"
            />
            <Input
              type="date"
              value={filters.date_to}
              onChange={(e) => setFilters(f => ({ ...f, date_to: e.target.value }))}
              className="bg-white"
              data-testid="filter-date-to"
            />
          </div>
        </CardContent>
      </Card>

      {/* KPI Scorecards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="kpi-scorecards">
        <KpiCard icon={Database} label="Total Captures" value={kpis.total_captures || 0} color="text-blue-600" bg="bg-blue-50" testId="kpi-total-captures" />
        <KpiCard icon={TrendingUp} label="Today" value={kpis.captures_today || 0} sub={`Week: ${kpis.captures_this_week || 0} | Month: ${kpis.captures_this_month || 0}`} color="text-emerald-600" bg="bg-emerald-50" testId="kpi-captures-today" />
        <KpiCard icon={Zap} label="Avg Daily (30d)" value={kpis.avg_daily_rate || 0} color="text-amber-600" bg="bg-amber-50" testId="kpi-avg-daily" />
        <KpiCard icon={Activity} label="Active Sources" value={kpis.active_sources || 0} sub={`${kpis.total_applications || 0} applications`} color="text-violet-600" bg="bg-violet-50" testId="kpi-active-sources" />
      </div>

      {/* Charts Row 1: Line + Pie */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Capture Trends — Line Chart */}
        <Card className="lg:col-span-2 border-slate-200" data-testid="capture-trends-chart">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-blue-600" />
              Capture Trends (Last 30 Days)
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {trends.length === 0 ? (
              <EmptyState msg="No capture data for selected period" />
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trends}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={d => d.slice(5)} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip labelFormatter={d => `Date: ${d}`} />
                  <Line type="monotone" dataKey="count" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} name="Captures" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Source Distribution — Pie Chart */}
        <Card className="border-slate-200" data-testid="source-distribution-chart">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Layers className="w-4 h-4 text-emerald-600" />
              Source Effectiveness
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {pieData.length === 0 ? (
              <EmptyState msg="No source data" />
            ) : (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={45}
                      outerRadius={80}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {pieData.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(val) => [val, 'Captures']} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-1.5 mt-2">
                  {pieData.map((s, i) => (
                    <div key={s.name} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                        <span className="text-slate-600">{s.name}</span>
                      </div>
                      <span className="font-medium text-slate-900">{s.value}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts Row 2: Bar + Funnel */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Team/Recruiter Performance — Bar Chart */}
        <Card className="border-slate-200" data-testid="recruiter-performance-chart">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Users className="w-4 h-4 text-violet-600" />
              Recruiter Performance
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {recruiters.length === 0 ? (
              <EmptyState msg="No recruiter data" />
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={recruiters.slice(0, 10)} layout="vertical" margin={{ left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0].payload;
                      return (
                        <div className="bg-white border border-slate-200 rounded-lg p-3 shadow-lg text-xs">
                          <p className="font-semibold text-slate-900">{d.name}</p>
                          {d.team && <p className="text-slate-500">Team: {d.team}</p>}
                          <p className="text-blue-600 mt-1">Captures: {d.captures}</p>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="captures" fill="#2563eb" radius={[0, 4, 4, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Funnel Velocity + Stage Distribution */}
        <div className="space-y-6">
          {/* Funnel Velocity */}
          <Card className="border-slate-200" data-testid="funnel-velocity-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Clock className="w-4 h-4 text-amber-600" />
                Funnel Velocity (Avg Days)
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="grid grid-cols-4 gap-3">
                {['shortlisted', 'interview', 'offered', 'hired'].map(stage => (
                  <div key={stage} className="text-center p-3 bg-slate-50 rounded-lg" data-testid={`funnel-${stage}`}>
                    <p className="text-2xl font-bold text-slate-900">{funnel[stage] || 0}</p>
                    <p className="text-[10px] text-slate-500 capitalize mt-1">{stage}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Stage Distribution */}
          <Card className="border-slate-200" data-testid="stage-distribution-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Activity className="w-4 h-4 text-emerald-600" />
                Application Stages
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {stageData.length === 0 ? (
                <EmptyState msg="No application data" />
              ) : (
                <div className="space-y-2">
                  {stageData.sort((a, b) => b.value - a.value).map(s => {
                    const max = stageData[0]?.value || 1;
                    const pct = Math.round((s.value / max) * 100);
                    return (
                      <div key={s.name} className="flex items-center gap-3" data-testid={`stage-${s.name}`}>
                        <span className="text-xs text-slate-600 capitalize w-20 text-right">{s.name}</span>
                        <div className="flex-1 h-5 bg-slate-100 rounded overflow-hidden">
                          <div
                            className="h-full rounded transition-all duration-500"
                            style={{ width: `${Math.max(pct, 4)}%`, background: STAGE_COLORS[s.name] || '#64748b' }}
                          />
                        </div>
                        <Badge variant="secondary" className="min-w-[36px] justify-center text-xs">{s.value}</Badge>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Recruiter Details Table */}
      <Card className="border-slate-200" data-testid="recruiter-details-table">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-600" />
            Recruiter Details
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Name</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Role</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Team</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Captures</th>
                </tr>
              </thead>
              <tbody>
                {recruiters.length === 0 ? (
                  <tr><td colSpan={4} className="text-center py-8 text-slate-400">No data</td></tr>
                ) : (
                  recruiters.map((r, i) => (
                    <tr key={r.user_id || i} className="border-b border-slate-100 hover:bg-slate-50/50">
                      <td className="py-3 px-4 font-medium text-slate-900">{r.name}</td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className="text-xs capitalize">{r.role}</Badge>
                      </td>
                      <td className="py-3 px-4 text-slate-600">{r.team || '—'}</td>
                      <td className="py-3 px-4 text-right font-semibold text-blue-600">{r.captures}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* AI Search Analytics */}
      {data?.ai_search?.total_searches > 0 && (
        <Card className="col-span-full border-slate-200" data-testid="ai-search-analytics">
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-slate-800 flex items-center gap-2">
              <Zap className="w-5 h-5 text-[#7CB342]" /> AI Search Analytics
              <Badge variant="outline" className="text-xs ml-2">{data.ai_search.total_searches} searches</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Top Searched Skills */}
              <div>
                <h4 className="text-sm font-medium text-slate-600 mb-3">Top Searched Skills</h4>
                {data.ai_search.top_searched_skills?.length > 0 ? (
                  <div className="space-y-2">
                    {data.ai_search.top_searched_skills.map((s, i) => (
                      <div key={s.skill} className="flex items-center gap-3">
                        <span className="text-xs text-slate-400 w-5">{i + 1}.</span>
                        <div className="flex-1">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm text-slate-700 capitalize">{s.skill}</span>
                            <span className="text-xs text-slate-500">{s.count}x</span>
                          </div>
                          <div className="w-full bg-slate-100 rounded-full h-1.5">
                            <div className="bg-[#7CB342] h-1.5 rounded-full" style={{
                              width: `${(s.count / (data.ai_search.top_searched_skills[0]?.count || 1)) * 100}%`
                            }} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-sm text-slate-400">No skill data yet</p>}
              </div>

              {/* Demand Gaps */}
              <div>
                <h4 className="text-sm font-medium text-slate-600 mb-3">Demand Gaps (Zero-Result Searches)</h4>
                {data.ai_search.zero_result_prompts?.length > 0 ? (
                  <div className="space-y-2">
                    {data.ai_search.zero_result_prompts.map((z, i) => (
                      <div key={i} className="p-2.5 bg-amber-50 border border-amber-100 rounded-lg">
                        <p className="text-xs text-amber-800 line-clamp-2">"{z.raw_prompt}"</p>
                        {z.extracted_filters?.skills?.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {z.extracted_filters.skills.slice(0, 4).map(sk => (
                              <span key={sk} className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[10px] rounded">{sk}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : <p className="text-sm text-slate-400">No demand gaps detected yet</p>}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function KpiCard({ icon: Icon, label, value, sub, color, bg, testId }) {
  return (
    <Card className="border-slate-200 hover:shadow-sm transition-shadow" data-testid={testId}>
      <CardContent className="p-4">
        <div className="flex items-center gap-2.5 mb-2">
          <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
            <Icon className={`w-4 h-4 ${color}`} />
          </div>
          <span className="text-xs text-slate-500 font-medium">{label}</span>
        </div>
        <p className="text-2xl font-bold text-slate-900">{typeof value === 'number' ? value.toLocaleString() : value}</p>
        {sub && <p className="text-[10px] text-slate-400 mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function EmptyState({ msg }) {
  return (
    <div className="flex items-center justify-center h-32 text-sm text-slate-400">{msg}</div>
  );
}
