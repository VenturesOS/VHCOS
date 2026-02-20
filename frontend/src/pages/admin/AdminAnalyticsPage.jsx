import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { toast } from 'sonner';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, FunnelChart, Funnel, LabelList,
} from 'recharts';
import {
  TrendingUp, Users, Database, Zap, Clock, Activity,
  RotateCcw, Filter, Layers, FileDown, IndianRupee, ArrowRight,
  Briefcase, Target, ArrowDown,
} from 'lucide-react';

const API_BASE = '/api';

function getToken() {
  return localStorage.getItem('vhc_token');
}

async function fetchJSON(url) {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

// ── Overview Tab (existing analytics) ──

const COLORS = ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2'];
const SOURCE_LABELS = {
  naukri_extension: 'Naukri Extension', bulk_import: 'Bulk Import',
  public_application: 'Public Application', admin: 'Admin',
  recruiter: 'Recruiter', employer: 'Employer',
};
const STAGE_COLORS = {
  applied: '#64748b', shortlisted: '#2563eb', submitted_to_client: '#7c3aed',
  interview: '#8b5cf6', offered: '#d97706', hired: '#059669',
  joined: '#10b981', rejected: '#dc2626', removed: '#94a3b8', on_hold: '#f59e0b',
};
const STAGE_LABELS = {
  applied: 'Applied', shortlisted: 'Shortlisted', submitted_to_client: 'Submitted',
  interview: 'Interview', offered: 'Offered', hired: 'Hired', joined: 'Joined',
  rejected: 'Rejected', on_hold: 'On Hold', removed: 'Removed',
};

function OverviewTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ employer_id: '', team_id: '', recruiter_id: '', date_from: '', date_to: '' });

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) params.append(k, v); });
      setData(await fetchJSON(`/analytics/admin?${params}`));
    } catch { toast.error('Failed to load analytics'); }
    finally { setLoading(false); }
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
      const a = document.createElement('a'); a.href = url;
      a.download = res.headers.get('content-disposition')?.split('filename=')[1]?.replace(/"/g, '') || 'VHC_Analytics.pdf';
      a.click(); URL.revokeObjectURL(url);
      toast.success('PDF exported');
    } catch { toast.error('Failed to export PDF'); }
    finally { setExporting(false); }
  };

  if (loading && !data) return <LoadingSpinner />;

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
    <div className="space-y-6" data-testid="overview-tab">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">Capture metrics, source effectiveness & team performance</p>
        <Button onClick={exportPdf} disabled={exporting || loading} variant="outline" size="sm" data-testid="export-pdf-btn" className="gap-1.5">
          <FileDown className="w-4 h-4" /> {exporting ? 'Exporting...' : 'Export PDF'}
        </Button>
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
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            <Select value={filters.employer_id || "all"} onValueChange={(v) => setFilters(f => ({ ...f, employer_id: v === 'all' ? '' : v, team_id: '', recruiter_id: '' }))}>
              <SelectTrigger data-testid="filter-employer"><SelectValue placeholder="All Employers" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Employers</SelectItem>
                {(filterOpts.employers || []).map(e => <SelectItem key={e.id} value={e.id}>{e.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={filters.team_id || "all"} onValueChange={(v) => setFilters(f => ({ ...f, team_id: v === 'all' ? '' : v }))}>
              <SelectTrigger data-testid="filter-team"><SelectValue placeholder="All Teams" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Teams</SelectItem>
                {(filterOpts.teams || []).filter(t => !filters.employer_id || t.employer_id === filters.employer_id).map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={filters.recruiter_id || "all"} onValueChange={(v) => setFilters(f => ({ ...f, recruiter_id: v === 'all' ? '' : v }))}>
              <SelectTrigger data-testid="filter-recruiter"><SelectValue placeholder="All Recruiters" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Recruiters</SelectItem>
                {(filterOpts.recruiters || []).map(r => <SelectItem key={r.id} value={r.id}>{r.name} ({r.role})</SelectItem>)}
              </SelectContent>
            </Select>
            <Input type="date" value={filters.date_from} onChange={(e) => setFilters(f => ({ ...f, date_from: e.target.value }))} className="bg-white" data-testid="filter-date-from" />
            <Input type="date" value={filters.date_to} onChange={(e) => setFilters(f => ({ ...f, date_to: e.target.value }))} className="bg-white" data-testid="filter-date-to" />
          </div>
        </CardContent>
      </Card>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="kpi-scorecards">
        <KpiCard icon={Database} label="Total Captures" value={kpis.total_captures || 0} color="text-blue-600" bg="bg-blue-50" testId="kpi-total-captures" />
        <KpiCard icon={TrendingUp} label="Today" value={kpis.captures_today || 0} sub={`Week: ${kpis.captures_this_week || 0} | Month: ${kpis.captures_this_month || 0}`} color="text-emerald-600" bg="bg-emerald-50" testId="kpi-captures-today" />
        <KpiCard icon={Zap} label="Avg Daily (30d)" value={kpis.avg_daily_rate || 0} color="text-amber-600" bg="bg-amber-50" testId="kpi-avg-daily" />
        <KpiCard icon={Activity} label="Active Sources" value={kpis.active_sources || 0} sub={`${kpis.total_applications || 0} applications`} color="text-violet-600" bg="bg-violet-50" testId="kpi-active-sources" />
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border-slate-200" data-testid="capture-trends-chart">
          <CardHeader className="pb-2"><CardTitle className="text-base font-semibold flex items-center gap-2"><TrendingUp className="w-4 h-4 text-blue-600" /> Capture Trends (Last 30 Days)</CardTitle></CardHeader>
          <CardContent className="pt-0">
            {trends.length === 0 ? <EmptyState msg="No capture data" /> : (
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
        <Card className="border-slate-200" data-testid="source-distribution-chart">
          <CardHeader className="pb-2"><CardTitle className="text-base font-semibold flex items-center gap-2"><Layers className="w-4 h-4 text-emerald-600" /> Source Effectiveness</CardTitle></CardHeader>
          <CardContent className="pt-0">
            {pieData.length === 0 ? <EmptyState msg="No source data" /> : (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart><Pie data={pieData} cx="50%" cy="50%" innerRadius={45} outerRadius={80} paddingAngle={2} dataKey="value">
                    {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie><Tooltip formatter={(val) => [val, 'Captures']} /></PieChart>
                </ResponsiveContainer>
                <div className="space-y-1.5 mt-2">{pieData.map((s, i) => (
                  <div key={s.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS[i % COLORS.length] }} /><span className="text-slate-600">{s.name}</span></div>
                    <span className="font-medium text-slate-900">{s.value}</span>
                  </div>
                ))}</div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border-slate-200" data-testid="recruiter-performance-chart">
          <CardHeader className="pb-2"><CardTitle className="text-base font-semibold flex items-center gap-2"><Users className="w-4 h-4 text-violet-600" /> Recruiter Performance</CardTitle></CardHeader>
          <CardContent className="pt-0">
            {recruiters.length === 0 ? <EmptyState msg="No recruiter data" /> : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={recruiters.slice(0, 10)} layout="vertical" margin={{ left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} />
                  <Tooltip content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload;
                    return (<div className="bg-white border rounded-lg p-3 shadow-lg text-xs">
                      <p className="font-semibold">{d.name}</p>{d.team && <p className="text-slate-500">Team: {d.team}</p>}
                      <p className="text-blue-600 mt-1">Captures: {d.captures}</p></div>);
                  }} />
                  <Bar dataKey="captures" fill="#2563eb" radius={[0, 4, 4, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
        <div className="space-y-6">
          <Card className="border-slate-200" data-testid="funnel-velocity-card">
            <CardHeader className="pb-2"><CardTitle className="text-base font-semibold flex items-center gap-2"><Clock className="w-4 h-4 text-amber-600" /> Funnel Velocity (Avg Days)</CardTitle></CardHeader>
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
          <Card className="border-slate-200" data-testid="stage-distribution-card">
            <CardHeader className="pb-2"><CardTitle className="text-base font-semibold flex items-center gap-2"><Activity className="w-4 h-4 text-emerald-600" /> Application Stages</CardTitle></CardHeader>
            <CardContent className="pt-0">
              {stageData.length === 0 ? <EmptyState msg="No data" /> : (
                <div className="space-y-2">{stageData.sort((a, b) => b.value - a.value).map(s => {
                  const max = stageData[0]?.value || 1;
                  const pct = Math.round((s.value / max) * 100);
                  return (<div key={s.name} className="flex items-center gap-3" data-testid={`stage-${s.name}`}>
                    <span className="text-xs text-slate-600 capitalize w-20 text-right">{s.name}</span>
                    <div className="flex-1 h-5 bg-slate-100 rounded overflow-hidden">
                      <div className="h-full rounded transition-all duration-500" style={{ width: `${Math.max(pct, 4)}%`, background: STAGE_COLORS[s.name] || '#64748b' }} />
                    </div>
                    <Badge variant="secondary" className="min-w-[36px] justify-center text-xs">{s.value}</Badge>
                  </div>);
                })}</div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── Date Range Filter Component ──

function DateRangeFilter({ fromDate, toDate, onFromChange, onToChange, onPreset }) {
  const presets = [
    { label: '7d', days: 7 },
    { label: '30d', days: 30 },
    { label: '90d', days: 90 },
    { label: 'YTD', days: 'ytd' },
  ];
  return (
    <Card className="border-slate-200 bg-slate-50/50" data-testid="date-range-filter">
      <CardContent className="p-3">
        <div className="flex flex-wrap items-center gap-3">
          <Filter className="w-4 h-4 text-slate-500" />
          <div className="flex gap-1.5">
            {presets.map(p => (
              <Button key={p.label} variant="outline" size="sm" className="h-7 text-xs px-2.5" data-testid={`preset-${p.label}`}
                onClick={() => onPreset(p.days)}>
                {p.label}
              </Button>
            ))}
            {(fromDate || toDate) && (
              <Button variant="ghost" size="sm" className="h-7 text-xs px-2" data-testid="preset-clear" onClick={() => onPreset('clear')}>
                <RotateCcw className="w-3 h-3 mr-1" /> Clear
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <Input type="date" value={fromDate} onChange={e => onFromChange(e.target.value)} className="h-7 text-xs w-36 bg-white" data-testid="date-from" />
            <span className="text-xs text-slate-400">to</span>
            <Input type="date" value={toDate} onChange={e => onToChange(e.target.value)} className="h-7 text-xs w-36 bg-white" data-testid="date-to" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function useDateRange() {
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const handlePreset = (days) => {
    if (days === 'clear') { setFromDate(''); setToDate(''); return; }
    const now = new Date();
    const to = now.toISOString().split('T')[0];
    let from;
    if (days === 'ytd') {
      from = `${now.getFullYear()}-01-01`;
    } else {
      const d = new Date(now); d.setDate(d.getDate() - days);
      from = d.toISOString().split('T')[0];
    }
    setFromDate(from); setToDate(to);
  };
  const queryStr = () => {
    const p = new URLSearchParams();
    if (fromDate) p.append('from_date', fromDate);
    if (toDate) p.append('to_date', toDate);
    return p.toString() ? `?${p}` : '';
  };
  return { fromDate, toDate, setFromDate, setToDate, handlePreset, queryStr };
}

// ── Pipeline Funnel Tab ──

function PipelineFunnelTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const dr = useDateRange();

  const fetchData = useCallback(() => {
    setLoading(true);
    fetchJSON(`/analytics/pipeline-conversion${dr.queryStr()}`)
      .then(setData)
      .catch(() => toast.error('Failed to load pipeline data'))
      .finally(() => setLoading(false));
  }, [dr.fromDate, dr.toDate]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <LoadingSpinner />;
  if (!data) return <EmptyState msg="No pipeline data available" />;

  const conversions = data.conversions || {};
  const stageCounts = data.stage_counts || {};
  const total = data.total_applications || 0;

  const funnelStages = ['applied', 'shortlisted', 'submitted_to_client', 'interview', 'offered', 'hired', 'joined'];
  const funnelData = funnelStages.map(stage => {
    const count = stageCounts[stage] || 0;
    return { name: STAGE_LABELS[stage] || stage, value: count, fill: STAGE_COLORS[stage] || '#64748b' };
  });

  // Build cumulative funnel values (each stage = that stage + all after it)
  const cumulativeFunnel = funnelStages.map((stage, idx) => {
    const cumCount = funnelStages.slice(idx).reduce((sum, s) => sum + (stageCounts[s] || 0), 0);
    return { name: STAGE_LABELS[stage], count: cumCount, fill: STAGE_COLORS[stage], stage };
  });

  const conversionEntries = [
    { key: 'applied_to_shortlisted', from: 'Applied', to: 'Shortlisted' },
    { key: 'shortlisted_to_submitted', from: 'Shortlisted', to: 'Submitted' },
    { key: 'submitted_to_interview', from: 'Submitted', to: 'Interview' },
    { key: 'interview_to_offered', from: 'Interview', to: 'Offered' },
    { key: 'offered_to_hired', from: 'Offered', to: 'Hired' },
    { key: 'hired_to_joined', from: 'Hired', to: 'Joined' },
  ];

  return (
    <div className="space-y-6" data-testid="pipeline-funnel-tab">
      <DateRangeFilter fromDate={dr.fromDate} toDate={dr.toDate} onFromChange={dr.setFromDate} onToChange={dr.setToDate} onPreset={dr.handlePreset} />
      {loading && <LoadingSpinner />}
      {!loading && !data && <EmptyState msg="No pipeline data available" />}
      {!loading && data && <><p className="text-sm text-slate-500">Stage-by-stage conversion rates across your recruitment pipeline</p>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard icon={Users} label="Total Applications" value={total} color="text-blue-600" bg="bg-blue-50" testId="kpi-total-apps" />
        <KpiCard icon={Target} label="Shortlisted" value={conversions.applied_to_shortlisted?.count || 0} sub={`${conversions.applied_to_shortlisted?.rate || 0}% of applied`} color="text-indigo-600" bg="bg-indigo-50" testId="kpi-shortlisted" />
        <KpiCard icon={Briefcase} label="Offered" value={conversions.interview_to_offered?.count || 0} sub={`${conversions.interview_to_offered?.rate || 0}% of interviewed`} color="text-amber-600" bg="bg-amber-50" testId="kpi-offered" />
        <KpiCard icon={TrendingUp} label="Joined" value={conversions.hired_to_joined?.count || 0} sub={`End-to-end: ${total > 0 ? ((conversions.hired_to_joined?.count || 0) / total * 100).toFixed(1) : 0}%`} color="text-emerald-600" bg="bg-emerald-50" testId="kpi-joined" />
      </div>

      {/* Visual Funnel */}
      <Card className="border-slate-200" data-testid="pipeline-funnel-visual">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <ArrowDown className="w-4 h-4 text-blue-600" /> Pipeline Funnel
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {cumulativeFunnel.map((stage, i) => {
              const maxCount = cumulativeFunnel[0]?.count || 1;
              const widthPct = Math.max((stage.count / maxCount) * 100, 8);
              return (
                <div key={stage.stage} className="flex items-center gap-4" data-testid={`funnel-stage-${stage.stage}`}>
                  <span className="text-xs font-medium text-slate-600 w-24 text-right">{stage.name}</span>
                  <div className="flex-1 relative">
                    <div
                      className="h-10 rounded-lg flex items-center justify-between px-4 transition-all duration-700"
                      style={{ width: `${widthPct}%`, background: stage.fill, opacity: 0.85 + (i * 0.02) }}
                    >
                      <span className="text-white text-sm font-bold">{stage.count}</span>
                      {i > 0 && (
                        <span className="text-white/80 text-xs">
                          {cumulativeFunnel[i - 1]?.count > 0
                            ? `${((stage.count / cumulativeFunnel[i - 1].count) * 100).toFixed(0)}%`
                            : '0%'}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Conversion Rate Cards */}
      <Card className="border-slate-200" data-testid="conversion-rates">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <ArrowRight className="w-4 h-4 text-emerald-600" /> Stage Conversion Rates
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {conversionEntries.map(({ key, from, to }) => {
              const conv = conversions[key] || {};
              const rate = conv.rate || 0;
              const rateColor = rate >= 60 ? 'text-emerald-600' : rate >= 30 ? 'text-amber-600' : 'text-red-500';
              return (
                <div key={key} className="p-4 bg-slate-50 rounded-xl border border-slate-100" data-testid={`conversion-${key}`}>
                  <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
                    <span>{from}</span>
                    <ArrowRight className="w-3 h-3" />
                    <span>{to}</span>
                  </div>
                  <div className="flex items-end justify-between">
                    <span className={`text-2xl font-bold ${rateColor}`}>{rate}%</span>
                    <span className="text-xs text-slate-400">{conv.count || 0} candidates</span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-200 rounded-full mt-3">
                    <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(rate, 100)}%`, background: rate >= 60 ? '#059669' : rate >= 30 ? '#d97706' : '#dc2626' }} />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Stage Distribution Bar */}
      <Card className="border-slate-200" data-testid="stage-bar-chart">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Activity className="w-4 h-4 text-violet-600" /> Current Stage Distribution
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={funnelData} margin={{ bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip formatter={(val) => [val, 'Candidates']} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} barSize={40}>
                {funnelData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      </>}
    </div>
  );
}

// ── Revenue Tab ──

function RevenueTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const dr = useDateRange();

  const fetchData = useCallback(() => {
    setLoading(true);
    fetchJSON(`/analytics/revenue-forecast${dr.queryStr()}`)
      .then(setData)
      .catch(() => toast.error('Failed to load revenue data'))
      .finally(() => setLoading(false));
  }, [dr.fromDate, dr.toDate]);

  useEffect(() => { fetchData(); }, [fetchData]);
      .catch(() => toast.error('Failed to load revenue data'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner />;
  if (!data) return <EmptyState msg="No revenue data available" />;

  const byStage = data.by_stage || {};
  const probMap = data.probability_map || {};
  const forecast = data.total_forecast_pipeline || 0;
  const realized = data.total_realized_revenue || 0;
  const totalCandidates = data.total_candidates_with_offer || 0;

  const stageOrder = ['applied', 'shortlisted', 'submitted_to_client', 'interview', 'offered', 'hired', 'joined'];
  const stageRevData = stageOrder
    .filter(s => byStage[s])
    .map(s => ({
      name: STAGE_LABELS[s] || s,
      total: Math.round(byStage[s].total_revenue),
      weighted: Math.round(byStage[s].weighted_revenue),
      count: byStage[s].count,
      probability: byStage[s].probability,
      fill: STAGE_COLORS[s],
    }));

  const formatCurrency = (v) => {
    if (v >= 100000) return `${(v / 100000).toFixed(1)}L`;
    if (v >= 1000) return `${(v / 1000).toFixed(0)}K`;
    return v.toLocaleString();
  };

  return (
    <div className="space-y-6" data-testid="revenue-tab">
      <p className="text-sm text-slate-500">Revenue forecast weighted by stage probability and realized revenue</p>

      {/* Revenue KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="border-slate-200 bg-gradient-to-br from-emerald-50 to-white" data-testid="kpi-forecast-pipeline">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center">
                <TrendingUp className="w-4 h-4 text-emerald-600" />
              </div>
              <span className="text-xs text-slate-500 font-medium">Weighted Forecast</span>
            </div>
            <p className="text-3xl font-bold text-slate-900">{formatCurrency(forecast)}</p>
            <p className="text-xs text-slate-400 mt-1">Probability-weighted pipeline value</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200 bg-gradient-to-br from-blue-50 to-white" data-testid="kpi-realized-revenue">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
                <IndianRupee className="w-4 h-4 text-blue-600" />
              </div>
              <span className="text-xs text-slate-500 font-medium">Realized Revenue</span>
            </div>
            <p className="text-3xl font-bold text-slate-900">{formatCurrency(realized)}</p>
            <p className="text-xs text-slate-400 mt-1">From joined candidates</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200 bg-gradient-to-br from-violet-50 to-white" data-testid="kpi-candidates-offer">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-lg bg-violet-100 flex items-center justify-center">
                <Users className="w-4 h-4 text-violet-600" />
              </div>
              <span className="text-xs text-slate-500 font-medium">In Revenue Pipeline</span>
            </div>
            <p className="text-3xl font-bold text-slate-900">{totalCandidates}</p>
            <p className="text-xs text-slate-400 mt-1">Candidates with forecast revenue</p>
          </CardContent>
        </Card>
      </div>

      {/* Revenue by Stage Chart */}
      {stageRevData.length > 0 && (
        <Card className="border-slate-200" data-testid="revenue-by-stage-chart">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <IndianRupee className="w-4 h-4 text-emerald-600" /> Revenue by Stage
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={stageRevData} margin={{ bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={formatCurrency} />
                <Tooltip
                  formatter={(val, name) => [formatCurrency(val), name === 'total' ? 'Total Revenue' : 'Weighted Revenue']}
                  labelFormatter={(label) => `Stage: ${label}`}
                />
                <Bar dataKey="total" name="Total Revenue" fill="#93c5fd" radius={[4, 4, 0, 0]} barSize={30} />
                <Bar dataKey="weighted" name="Weighted Revenue" fill="#2563eb" radius={[4, 4, 0, 0]} barSize={30} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Probability Map */}
      <Card className="border-slate-200" data-testid="probability-map">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Target className="w-4 h-4 text-amber-600" /> Revenue Probability by Stage
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            {stageOrder.map(stage => {
              const prob = probMap[stage] || 0;
              const stageInfo = byStage[stage];
              return (
                <div key={stage} className="text-center p-3 rounded-xl border border-slate-100 bg-slate-50" data-testid={`prob-${stage}`}>
                  <p className="text-xs text-slate-500 mb-1">{STAGE_LABELS[stage]}</p>
                  <p className="text-xl font-bold" style={{ color: STAGE_COLORS[stage] }}>{prob}%</p>
                  {stageInfo && <p className="text-[10px] text-slate-400 mt-1">{stageInfo.count} candidates</p>}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Forecast vs Realized */}
      {(forecast > 0 || realized > 0) && (
        <Card className="border-slate-200" data-testid="forecast-vs-realized">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-blue-600" /> Forecast vs Realized
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-slate-600">Realized Revenue</span>
                  <span className="font-semibold text-emerald-600">{formatCurrency(realized)}</span>
                </div>
                <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-emerald-500 rounded-full transition-all duration-700" style={{ width: `${forecast > 0 ? Math.min((realized / forecast) * 100, 100) : 0}%` }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-slate-600">Weighted Forecast</span>
                  <span className="font-semibold text-blue-600">{formatCurrency(forecast)}</span>
                </div>
                <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full" style={{ width: '100%' }} />
                </div>
              </div>
              <p className="text-xs text-slate-400">
                Realization rate: {forecast > 0 ? ((realized / forecast) * 100).toFixed(1) : 0}%
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Performance Tab ──

function PerformanceTab() {
  const [recruiterData, setRecruiterData] = useState(null);
  const [mandateData, setMandateData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchJSON('/analytics/recruiter-performance'),
      fetchJSON('/analytics/mandate-performance'),
    ]).then(([r, m]) => {
      setRecruiterData(r);
      setMandateData(m);
    }).catch(() => toast.error('Failed to load performance data'))
    .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner />;

  const recruiters = recruiterData?.recruiters || [];
  const mandates = mandateData?.mandates || [];

  const formatCurrency = (v) => {
    if (v >= 100000) return `${(v / 100000).toFixed(1)}L`;
    if (v >= 1000) return `${(v / 1000).toFixed(0)}K`;
    return v.toLocaleString();
  };

  return (
    <div className="space-y-6" data-testid="performance-tab">
      <p className="text-sm text-slate-500">Recruiter and mandate-level performance metrics</p>

      {/* Recruiter Performance Table */}
      <Card className="border-slate-200" data-testid="recruiter-perf-table">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-600" /> Recruiter Performance
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Recruiter</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Total</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Submitted</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Offered</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Joined</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Rejected</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Revenue</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Conv. Rate</th>
                </tr>
              </thead>
              <tbody>
                {recruiters.length === 0 ? (
                  <tr><td colSpan={8} className="text-center py-8 text-slate-400">No recruiter data</td></tr>
                ) : recruiters.map((r, i) => (
                  <tr key={r.recruiter_id || i} className="border-b border-slate-100 hover:bg-slate-50/50" data-testid={`recruiter-row-${i}`}>
                    <td className="py-3 px-4 font-medium text-slate-900">{r.recruiter_name}</td>
                    <td className="py-3 px-4 text-right">{r.total_candidates}</td>
                    <td className="py-3 px-4 text-right text-blue-600">{r.submitted}</td>
                    <td className="py-3 px-4 text-right text-amber-600">{r.offered}</td>
                    <td className="py-3 px-4 text-right text-emerald-600 font-semibold">{r.joined}</td>
                    <td className="py-3 px-4 text-right text-red-500">{r.rejected}</td>
                    <td className="py-3 px-4 text-right font-semibold">{formatCurrency(r.total_revenue)}</td>
                    <td className="py-3 px-4 text-right">
                      <Badge variant={r.conversion_rate >= 10 ? 'default' : 'secondary'} className="text-xs">
                        {r.conversion_rate}%
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Recruiter Chart */}
      {recruiters.length > 0 && (
        <Card className="border-slate-200" data-testid="recruiter-perf-chart">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Activity className="w-4 h-4 text-violet-600" /> Recruiter Comparison
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={recruiters.slice(0, 8)} margin={{ bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="recruiter_name" tick={{ fontSize: 10 }} angle={-25} textAnchor="end" />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="total_candidates" name="Total" fill="#94a3b8" radius={[4, 4, 0, 0]} barSize={16} />
                <Bar dataKey="submitted" name="Submitted" fill="#2563eb" radius={[4, 4, 0, 0]} barSize={16} />
                <Bar dataKey="joined" name="Joined" fill="#059669" radius={[4, 4, 0, 0]} barSize={16} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Mandate Performance Table */}
      <Card className="border-slate-200" data-testid="mandate-perf-table">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Briefcase className="w-4 h-4 text-amber-600" /> Mandate Performance
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Mandate</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Company</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Total</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Submitted</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Offered</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Joined</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Revenue</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Submit %</th>
                </tr>
              </thead>
              <tbody>
                {mandates.length === 0 ? (
                  <tr><td colSpan={8} className="text-center py-8 text-slate-400">No mandate data</td></tr>
                ) : mandates.map((m, i) => (
                  <tr key={m.mandate_id || i} className="border-b border-slate-100 hover:bg-slate-50/50" data-testid={`mandate-row-${i}`}>
                    <td className="py-3 px-4 font-medium text-slate-900 max-w-[200px] truncate">{m.mandate_name}</td>
                    <td className="py-3 px-4 text-slate-600">{m.company || '—'}</td>
                    <td className="py-3 px-4 text-right">{m.total_candidates}</td>
                    <td className="py-3 px-4 text-right text-blue-600">{m.submitted}</td>
                    <td className="py-3 px-4 text-right text-amber-600">{m.offered}</td>
                    <td className="py-3 px-4 text-right text-emerald-600 font-semibold">{m.joined}</td>
                    <td className="py-3 px-4 text-right font-semibold">{formatCurrency(m.total_revenue)}</td>
                    <td className="py-3 px-4 text-right">
                      <Badge variant={m.submission_rate >= 50 ? 'default' : 'secondary'} className="text-xs">
                        {m.submission_rate}%
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Shared Components ──

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

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-64" data-testid="analytics-loading">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#2563eb]" />
    </div>
  );
}

function EmptyState({ msg }) {
  return <div className="flex items-center justify-center h-32 text-sm text-slate-400">{msg}</div>;
}

// ── Main Page ──

export default function AdminAnalyticsPage() {
  return (
    <div className="space-y-6" data-testid="admin-analytics-page">
      <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Analytics</h1>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="w-full sm:w-auto bg-slate-100 p-1">
          <TabsTrigger value="overview" data-testid="tab-overview" className="text-xs sm:text-sm">
            Overview
          </TabsTrigger>
          <TabsTrigger value="pipeline" data-testid="tab-pipeline" className="text-xs sm:text-sm">
            Pipeline Funnel
          </TabsTrigger>
          <TabsTrigger value="revenue" data-testid="tab-revenue" className="text-xs sm:text-sm">
            Revenue
          </TabsTrigger>
          <TabsTrigger value="performance" data-testid="tab-performance" className="text-xs sm:text-sm">
            Performance
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview"><OverviewTab /></TabsContent>
        <TabsContent value="pipeline"><PipelineFunnelTab /></TabsContent>
        <TabsContent value="revenue"><RevenueTab /></TabsContent>
        <TabsContent value="performance"><PerformanceTab /></TabsContent>
      </Tabs>
    </div>
  );
}
