import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { systemErrorsAPI, apiMetricsAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import {
  Activity, AlertTriangle, Monitor, Server, Clock, Trash2, RefreshCw,
  Download, Loader2, Shield, ShieldCheck, Database, Cpu, Zap, Radio, Brain,
  ArrowUpDown, CircleDot, CheckCircle2, XCircle, AlertCircle,
  Gauge, TrendingUp, Timer, BarChart3, Wifi, WifiOff,
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Area, AreaChart, BarChart, Bar, CartesianGrid, Cell,
} from 'recharts';

const API_URL = '';
function getToken() { return localStorage.getItem('vhc_token'); }

// ─── Constants ───────────────────────────────────────────

const SERVICE_META = {
  mongodb:             { icon: Database,    label: 'MongoDB',        metricKey: 'latency_ms',     metricLabel: 'Latency' },
  api_server:          { icon: Server,      label: 'API Server',     metricKey: 'latency_ms',     metricLabel: 'Latency' },
  background_workers:  { icon: Cpu,         label: 'Workers',        metricKey: 'stuck_jobs',     metricLabel: 'Stuck Jobs' },
  queue_system:        { icon: ArrowUpDown, label: 'Queue',          metricKey: 'pending',        metricLabel: 'Pending' },
  system_resources:    { icon: Zap,         label: 'Resources',      metricKey: 'memory_percent', metricLabel: 'Memory' },
  automation_pipeline: { icon: Radio,       label: 'Automation',     metricKey: 'success_rate',   metricLabel: 'Success' },
  ai_services:         { icon: Brain,       label: 'AI Services',    metricKey: 'ai_errors_1h',   metricLabel: 'Errors/1h' },
  data_sync:           { icon: CircleDot,   label: 'Data Sync',      metricKey: 'sync_errors_24h',metricLabel: 'Errors/24h' },
  naukri_capture:      { icon: Download,    label: 'Naukri Capture',  metricKey: 'success_rate',   metricLabel: 'Success%' },
  security:            { icon: Shield,      label: 'Security',        metricKey: 'events_24h',     metricLabel: 'Events/24h' },
  virus_scanner:       { icon: Shield,      label: 'Virus Scanner',   metricKey: 'mode',           metricLabel: 'Mode' },
};

const STATUS_STYLES = {
  healthy:  { dot: 'bg-emerald-500', ring: 'ring-emerald-500/20', bg: 'bg-emerald-50', text: 'text-emerald-700' },
  warning:  { dot: 'bg-amber-500',   ring: 'ring-amber-500/20',   bg: 'bg-amber-50',   text: 'text-amber-700' },
  critical: { dot: 'bg-red-500',     ring: 'ring-red-500/20',     bg: 'bg-red-50',     text: 'text-red-700' },
  offline:  { dot: 'bg-slate-400',   ring: 'ring-slate-400/20',   bg: 'bg-slate-50',   text: 'text-slate-500' },
};

const TIME_RANGES = [
  { value: '1h', label: '1 Hour' },
  { value: '6h', label: '6 Hours' },
  { value: '24h', label: '24 Hours' },
  { value: '7d', label: '7 Days' },
];

// ─── Helpers ─────────────────────────────────────────────

const fmtDate = (ts) => {
  if (!ts) return '-';
  return new Date(ts).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' });
};
const fmtTime = (ts) => {
  if (!ts) return '';
  return new Date(ts).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' });
};

// ══════════════════════════════════════════════════════════
// API METRICS TAB
// ══════════════════════════════════════════════════════════

function APIMetricsTab() {
  const [range, setRange] = useState('1h');
  const [overview, setOverview] = useState(null);
  const [timeseries, setTimeseries] = useState([]);
  const [topErrors, setTopErrors] = useState([]);
  const [topSlow, setTopSlow] = useState([]);
  const [dbHealth, setDbHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [endpointSort, setEndpointSort] = useState('errors');
  const timerRef = useRef(null);

  const fetchAll = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    try {
      const [ov, ts, te, tslow, dbh] = await Promise.all([
        apiMetricsAPI.getOverview(range),
        apiMetricsAPI.getTimeseries(range),
        apiMetricsAPI.getTopEndpoints(range, 'errors'),
        apiMetricsAPI.getTopEndpoints(range, 'slow'),
        apiMetricsAPI.getDbHealth(),
      ]);
      setOverview(ov.data);
      setTimeseries(ts.data);
      setTopErrors(te.data);
      setTopSlow(tslow.data);
      setDbHealth(dbh.data);
    } catch {
      toast.error('Failed to load API metrics');
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => { fetchAll(true); }, [fetchAll]);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    timerRef.current = setInterval(() => fetchAll(false), 10000);
    return () => clearInterval(timerRef.current);
  }, [fetchAll]);

  const endpoints = endpointSort === 'errors' ? topErrors : topSlow;

  if (loading && !overview) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="api-metrics-tab">
      {/* Time Range Selector */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 bg-slate-100 rounded-lg p-0.5" data-testid="time-range-selector">
          {TIME_RANGES.map((tr) => (
            <button
              key={tr.value}
              onClick={() => setRange(tr.value)}
              data-testid={`range-${tr.value}`}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                range === tr.value
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {tr.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          Live · 10s refresh
        </div>
      </div>

      {/* ─── Overview Cards ─── */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="metrics-overview-cards">
          <MetricCard
            icon={<Gauge className="w-4 h-4" />}
            label="Total Requests"
            value={overview.total_requests.toLocaleString()}
            testId="card-total-requests"
            accent="text-blue-600"
            accentBg="bg-blue-50"
          />
          <MetricCard
            icon={<AlertTriangle className="w-4 h-4" />}
            label="Error Rate"
            value={`${overview.error_rate}%`}
            testId="card-error-rate"
            accent={overview.error_rate > 5 ? 'text-red-600' : overview.error_rate > 1 ? 'text-amber-600' : 'text-emerald-600'}
            accentBg={overview.error_rate > 5 ? 'bg-red-50' : overview.error_rate > 1 ? 'bg-amber-50' : 'bg-emerald-50'}
            sub={`${overview.error_count} errors`}
          />
          <MetricCard
            icon={<Timer className="w-4 h-4" />}
            label="Avg Response"
            value={`${overview.avg_response_ms}ms`}
            testId="card-avg-response"
            accent={overview.avg_response_ms > 2000 ? 'text-red-600' : overview.avg_response_ms > 500 ? 'text-amber-600' : 'text-emerald-600'}
            accentBg={overview.avg_response_ms > 2000 ? 'bg-red-50' : overview.avg_response_ms > 500 ? 'bg-amber-50' : 'bg-emerald-50'}
          />
          <MetricCard
            icon={<TrendingUp className="w-4 h-4" />}
            label="P95 Response"
            value={`${overview.p95_response_ms}ms`}
            testId="card-p95-response"
            accent="text-indigo-600"
            accentBg="bg-indigo-50"
          />
          <MetricCard
            icon={<Zap className="w-4 h-4" />}
            label="Max Response"
            value={`${overview.max_response_ms}ms`}
            testId="card-max-response"
            accent="text-slate-600"
            accentBg="bg-slate-50"
            sub={`${overview.server_error_count} 5xx`}
          />
        </div>
      )}

      {/* ─── Charts Row: Response Time + Error Rate ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Response Time Chart */}
        <Card data-testid="response-time-chart">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Timer className="w-4 h-4 text-indigo-500" /> Response Time
            </CardTitle>
          </CardHeader>
          <CardContent>
            {timeseries.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={timeseries} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="respGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} unit="ms" />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0', boxShadow: '0 2px 8px rgba(0,0,0,.06)' }}
                    formatter={(v) => [`${v}ms`, 'Avg Response']}
                  />
                  <Area type="monotone" dataKey="avg_ms" stroke="#6366f1" strokeWidth={2} fill="url(#respGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[200px] flex items-center justify-center text-sm text-slate-400">No data for selected range</div>
            )}
          </CardContent>
        </Card>

        {/* Error Rate Chart */}
        <Card data-testid="error-rate-chart">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-500" /> Error Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            {timeseries.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={timeseries} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} unit="%" />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0', boxShadow: '0 2px 8px rgba(0,0,0,.06)' }}
                    formatter={(v, name) => {
                      if (name === 'error_rate') return [`${v}%`, 'Error Rate'];
                      return [v, 'Requests'];
                    }}
                  />
                  <Bar dataKey="requests" fill="#e2e8f0" radius={[2, 2, 0, 0]} name="requests" />
                  <Bar dataKey="errors" radius={[2, 2, 0, 0]} name="error_rate">
                    {timeseries.map((entry, i) => (
                      <Cell key={i} fill={entry.errors > 0 ? '#ef4444' : '#d1d5db'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[200px] flex items-center justify-center text-sm text-slate-400">No data for selected range</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ─── DB Health + Throughput ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* DB Health Card */}
        {dbHealth && (
          <Card data-testid="db-health-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <Database className="w-4 h-4 text-emerald-500" /> MongoDB Status
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">Connection</span>
                <div className="flex items-center gap-1.5">
                  {dbHealth.status === 'connected' ? (
                    <><Wifi className="w-3.5 h-3.5 text-emerald-500" /><span className="text-xs font-medium text-emerald-600">Connected</span></>
                  ) : (
                    <><WifiOff className="w-3.5 h-3.5 text-red-500" /><span className="text-xs font-medium text-red-600">Error</span></>
                  )}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">Ping</span>
                <span className={`text-xs font-mono font-medium ${dbHealth.ping_ms > 500 ? 'text-red-600' : dbHealth.ping_ms > 100 ? 'text-amber-600' : 'text-emerald-600'}`}>
                  {dbHealth.ping_ms}ms
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">Active Connections</span>
                <span className="text-xs font-mono font-medium text-slate-700">{dbHealth.connections?.current || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">Available</span>
                <span className="text-xs font-mono font-medium text-slate-700">{dbHealth.connections?.available || 0}</span>
              </div>
              {/* Connection usage bar */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-slate-400">Pool Utilization</span>
                  <span className="text-[10px] font-medium text-slate-500">
                    {dbHealth.connections?.current || 0} / {(dbHealth.connections?.current || 0) + (dbHealth.connections?.available || 0)}
                  </span>
                </div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      ((dbHealth.connections?.current || 0) / ((dbHealth.connections?.current || 0) + (dbHealth.connections?.available || 1))) > 0.8
                        ? 'bg-red-500'
                        : ((dbHealth.connections?.current || 0) / ((dbHealth.connections?.current || 0) + (dbHealth.connections?.available || 1))) > 0.5
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                    }`}
                    style={{
                      width: `${Math.min(((dbHealth.connections?.current || 0) / ((dbHealth.connections?.current || 0) + (dbHealth.connections?.available || 1))) * 100, 100)}%`
                    }}
                  />
                </div>
              </div>
              <div className="flex items-center justify-between pt-1 border-t border-slate-100">
                <span className="text-xs text-slate-500">Collections</span>
                <span className="text-xs font-mono font-medium text-slate-700">{dbHealth.collections_count}</span>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Request Throughput Chart */}
        <Card className="lg:col-span-2" data-testid="throughput-chart">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-blue-500" /> Request Throughput
            </CardTitle>
          </CardHeader>
          <CardContent>
            {timeseries.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={timeseries} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="reqGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0', boxShadow: '0 2px 8px rgba(0,0,0,.06)' }}
                    formatter={(v) => [v, 'Requests']}
                  />
                  <Area type="monotone" dataKey="requests" stroke="#3b82f6" strokeWidth={2} fill="url(#reqGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[200px] flex items-center justify-center text-sm text-slate-400">No data for selected range</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ─── Top Endpoints Table ─── */}
      <Card data-testid="top-endpoints-table">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Server className="w-4 h-4 text-slate-500" /> Endpoint Analysis
            </CardTitle>
            <div className="flex gap-1 bg-slate-100 rounded-md p-0.5">
              <button
                onClick={() => setEndpointSort('errors')}
                data-testid="sort-by-errors"
                className={`px-2.5 py-1 rounded text-[11px] font-medium transition-all ${
                  endpointSort === 'errors' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'
                }`}
              >
                Most Errors
              </button>
              <button
                onClick={() => setEndpointSort('slow')}
                data-testid="sort-by-slow"
                className={`px-2.5 py-1 rounded text-[11px] font-medium transition-all ${
                  endpointSort === 'slow' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'
                }`}
              >
                Slowest
              </button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {endpoints.length > 0 ? (
            <div className="divide-y divide-slate-100">
              {endpoints.map((ep, i) => (
                <div key={i} className="px-4 py-2.5 hover:bg-slate-50 flex items-center gap-3" data-testid={`endpoint-row-${i}`}>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold shrink-0 ${
                    ep.method === 'GET' ? 'bg-emerald-50 text-emerald-700'
                    : ep.method === 'POST' ? 'bg-blue-50 text-blue-700'
                    : ep.method === 'PUT' ? 'bg-amber-50 text-amber-700'
                    : ep.method === 'DELETE' ? 'bg-red-50 text-red-700'
                    : 'bg-slate-50 text-slate-600'
                  }`}>{ep.method}</span>
                  <span className="text-xs font-mono text-slate-700 flex-1 truncate">{ep.endpoint}</span>
                  <div className="flex items-center gap-4 shrink-0 text-xs">
                    <span className="text-slate-500 w-16 text-right">{ep.count} reqs</span>
                    <span className={`w-16 text-right font-medium ${ep.errors > 0 ? 'text-red-600' : 'text-slate-400'}`}>
                      {ep.errors > 0 ? `${ep.errors} err` : '-'}
                    </span>
                    <span className={`w-16 text-right font-mono ${
                      ep.avg_ms > 2000 ? 'text-red-600' : ep.avg_ms > 500 ? 'text-amber-600' : 'text-slate-500'
                    }`}>{ep.avg_ms}ms</span>
                    <span className="text-slate-400 w-16 text-right font-mono">{ep.max_ms}ms max</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center text-sm text-slate-400">No endpoint data for selected range</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({ icon, label, value, testId, accent, accentBg, sub }) {
  return (
    <Card data-testid={testId}>
      <CardContent className="py-3.5 px-4">
        <div className="flex items-center gap-2 mb-1.5">
          <div className={`p-1 rounded ${accentBg}`}>
            <span className={accent}>{icon}</span>
          </div>
          <span className="text-[11px] text-slate-500 font-medium">{label}</span>
        </div>
        <p className={`text-xl font-bold ${accent}`}>{value}</p>
        {sub && <p className="text-[10px] text-slate-400 mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}


// ══════════════════════════════════════════════════════════
// SERVICES & ERRORS TAB (Existing functionality)
// ══════════════════════════════════════════════════════════

function ServicesErrorsTab() {
  const [stats, setStats] = useState(null);
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState(null);
  const [live, setLive] = useState(null);
  const [failedCaptures, setFailedCaptures] = useState(null);
  const [securityEvents, setSecurityEvents] = useState(null);
  const intervalRef = useRef(null);

  const fetchLive = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/system-health/live-status`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) setLive(await res.json());
    } catch (_) {}
    try {
      const res = await fetch(`${API_URL}/api/system-health/failed-captures?limit=10&recovered=false`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) setFailedCaptures(await res.json());
    } catch (_) {}
    try {
      const res = await fetch(`${API_URL}/api/system-health/security-events?limit=10`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) setSecurityEvents(await res.json());
    } catch (_) {}
  }, []);

  const load = useCallback(async () => {
    try {
      const params = {};
      if (filter !== 'all') params.source = filter;
      const [statsRes, errorsRes] = await Promise.all([
        systemErrorsAPI.getStats(),
        systemErrorsAPI.getAll(params),
      ]);
      setStats(statsRes.data);
      setErrors(errorsRes.data);
      await fetchLive();
    } catch {
      toast.error('Failed to load system health data');
    } finally {
      setLoading(false);
    }
  }, [filter, fetchLive]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    intervalRef.current = setInterval(fetchLive, 30000);
    return () => clearInterval(intervalRef.current);
  }, [fetchLive]);

  const handleClear = async () => {
    if (!window.confirm('Delete errors older than 30 days?')) return;
    try {
      const res = await systemErrorsAPI.clear(30);
      toast.success(`Cleared ${res.data.deleted} old errors`);
      load();
    } catch {
      toast.error('Failed to clear errors');
    }
  };

  const handleRecover = async (captureId) => {
    try {
      const res = await fetch(`${API_URL}/api/system-health/failed-captures/${captureId}/recover`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) {
        toast.success('Marked as recovered');
        fetchLive();
      } else {
        toast.error('Failed to mark as recovered');
      }
    } catch {
      toast.error('Recovery action failed');
    }
  };

  const maxHourly = stats?.hourly_trend?.reduce((m, h) => Math.max(m, h.count), 0) || 1;
  const services = live?.services || [];
  const scoreHistory = (live?.score_history || []).map(p => ({
    ...p,
    time: fmtTime(p.timestamp),
  }));
  const incidents = live?.incidents || [];

  return (
    <div className="space-y-5" data-testid="services-errors-tab">
      {/* Actions bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <Button variant="outline" size="sm" onClick={load} data-testid="refresh-services-btn">
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
        <Button variant="outline" size="sm" className="text-red-600 hover:bg-red-50" onClick={handleClear}
          data-testid="clear-errors-btn">
          <Trash2 className="w-4 h-4 mr-1" /> Clear Old
        </Button>
      </div>

      {/* Service Monitor Grid */}
      {services.length > 0 && (
        <div data-testid="live-service-grid">
          <h2 className="font-heading text-sm font-semibold text-slate-800 mb-3">Live Service Monitor</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {services.map((svc) => {
              const meta = SERVICE_META[svc.service_name] || { icon: Server, label: svc.service_name, metricKey: '', metricLabel: '' };
              const Icon = meta.icon;
              const st = STATUS_STYLES[svc.status] || STATUS_STYLES.offline;
              const metricVal = svc.metrics?.[meta.metricKey];
              const suffix = meta.metricKey?.includes('percent') ? '%' : meta.metricKey?.includes('ms') || meta.metricKey?.includes('latency') ? 'ms' : meta.metricKey?.includes('rate') ? '%' : '';
              return (
                <Card key={svc.service_name} className={`relative overflow-hidden border ${svc.status === 'critical' ? 'border-red-200' : svc.status === 'warning' ? 'border-amber-200' : 'border-slate-200'}`}
                  data-testid={`service-card-${svc.service_name}`}>
                  <CardContent className="p-3">
                    <div className="flex items-start justify-between mb-2">
                      <div className={`p-1.5 rounded-md ${st.bg}`}><Icon className={`w-4 h-4 ${st.text}`} /></div>
                      <div className="flex items-center gap-1.5"><div className={`w-2 h-2 rounded-full ${st.dot} ring-4 ${st.ring}`} /></div>
                    </div>
                    <p className="text-xs font-semibold text-slate-800 truncate">{meta.label}</p>
                    <div className="flex items-end justify-between mt-1">
                      <span className="text-lg font-bold text-slate-900">{metricVal !== undefined && metricVal !== null ? `${metricVal}${suffix}` : '-'}</span>
                      <span className="text-[10px] text-slate-400">{meta.metricLabel}</span>
                    </div>
                    <div className="flex items-center justify-between mt-1.5 text-[10px] text-slate-400">
                      <span>{fmtTime(svc.timestamp)}</span>
                      {svc.failure_count_24h > 0 && <span className="text-red-500 font-medium">{svc.failure_count_24h} failures</span>}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* Health Score Trend + Incidents */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {scoreHistory.length > 1 && (
          <Card className="lg:col-span-2" data-testid="health-score-chart">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Activity className="w-4 h-4 text-slate-500" /> Health Score Trend (24h)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={scoreHistory} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#059669" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#059669" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }} formatter={(v) => [`${v}/100`, 'Score']} />
                  <Area type="monotone" dataKey="score" stroke="#059669" strokeWidth={2} fill="url(#scoreGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
        <Card data-testid="active-incidents-panel">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" /> Active Incidents
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {incidents.length === 0 ? (
              <div className="py-8 text-center" data-testid="no-incidents">
                <CheckCircle2 className="w-8 h-8 text-emerald-300 mx-auto mb-1.5" />
                <p className="text-xs text-slate-400">No active incidents</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {incidents.map((inc, i) => {
                  const st = STATUS_STYLES[inc.status] || STATUS_STYLES.offline;
                  const Icon = inc.status === 'critical' ? XCircle : AlertCircle;
                  return (
                    <div key={i} className="px-3 py-2.5 hover:bg-slate-50" data-testid={`incident-${i}`}>
                      <div className="flex items-start gap-2">
                        <Icon className={`w-3.5 h-3.5 mt-0.5 ${st.text} shrink-0`} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs font-semibold text-slate-800">{SERVICE_META[inc.service_name]?.label || inc.service_name}</span>
                            <Badge variant="outline" className={`text-[9px] py-0 px-1 ${st.text} border-current`}>{inc.status}</Badge>
                          </div>
                          <p className="text-[10px] text-slate-400 truncate mt-0.5">{inc.error_details || `${inc.status} — see metrics`}</p>
                          <span className="text-[10px] text-slate-300">{fmtTime(inc.timestamp)}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Failed Naukri Captures */}
      {failedCaptures && (failedCaptures.stats?.unrecovered > 0 || failedCaptures.logs?.length > 0) && (
        <Card data-testid="failed-captures-panel">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                Failed Naukri Captures
                {failedCaptures.stats?.unrecovered > 0 && (
                  <Badge variant="outline" className="text-[10px] text-red-600 border-red-300 ml-1">{failedCaptures.stats.unrecovered} unrecovered</Badge>
                )}
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-slate-100">
              {failedCaptures.logs?.map((fc, i) => (
                <div key={fc.id || i} className="px-4 py-3 hover:bg-slate-50 flex items-start justify-between gap-3" data-testid={`failed-capture-${i}`}>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-slate-800">{fc.candidate_name || 'Unknown'}</span>
                      {fc.candidate_email && <span className="text-xs text-slate-400">{fc.candidate_email}</span>}
                    </div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <Badge variant="outline" className="text-[9px] text-red-600 border-red-200">{fc.failed_step || 'unknown'}</Badge>
                      <span className="text-[11px] text-slate-500 truncate max-w-xs">{fc.failure_reason}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-400">
                      <span>{fmtDate(fc.timestamp)}</span>
                      {fc.data_missing_fields?.length > 0 && <span className="text-amber-500">Missing: {fc.data_missing_fields.join(', ')}</span>}
                      {fc.profile_url && <a href={fc.profile_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline truncate max-w-[150px]">Profile Link</a>}
                    </div>
                  </div>
                  <Button size="sm" variant="outline" className="shrink-0 text-xs h-7 gap-1" onClick={() => handleRecover(fc.id)} data-testid={`recover-btn-${i}`}>
                    <CheckCircle2 className="w-3 h-3" /> Recover
                  </Button>
                </div>
              ))}
              {failedCaptures.logs?.length === 0 && (
                <div className="py-6 text-center text-xs text-slate-400">
                  <CheckCircle2 className="w-6 h-6 text-emerald-300 mx-auto mb-1" />
                  All captures recovered
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Security Events */}
      {securityEvents && securityEvents.total > 0 && (
        <Card data-testid="security-events-panel">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Shield className="w-4 h-4 text-red-500" />
                Security Events (24h)
                {securityEvents.summary?.critical > 0 && (
                  <Badge variant="outline" className="text-[10px] text-red-600 border-red-300 ml-1">{securityEvents.summary.critical} critical</Badge>
                )}
              </CardTitle>
              <span className="text-xs text-slate-400">{securityEvents.total} total</span>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-slate-100">
              {securityEvents.events?.slice(0, 8).map((ev, i) => {
                const sevColors = { CRITICAL: 'bg-red-50 text-red-700 border-red-200', HIGH: 'bg-orange-50 text-orange-700 border-orange-200', MEDIUM: 'bg-amber-50 text-amber-700 border-amber-200', LOW: 'bg-slate-50 text-slate-600 border-slate-200' };
                return (
                  <div key={ev.id || i} className="px-4 py-2.5 hover:bg-slate-50" data-testid={`security-event-${i}`}>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="outline" className={`text-[9px] py-0 px-1.5 ${sevColors[ev.severity] || sevColors.LOW}`}>{ev.severity}</Badge>
                      <span className="text-xs font-medium text-slate-800">{ev.event_type?.replace(/_/g, ' ')}</span>
                      <span className="text-[10px] text-slate-400 ml-auto">{ev.ip_address}</span>
                      <span className="text-[10px] text-slate-300">{fmtTime(ev.timestamp)}</span>
                    </div>
                    <p className="text-[11px] text-slate-500 truncate mt-0.5 pl-12">{ev.detail}</p>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-slate-700">{stats.total}</p>
            <p className="text-xs text-slate-500">Total Errors</p>
          </CardContent></Card>
          <Card className="border-red-200"><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-red-600">{stats.last_1h}</p>
            <p className="text-xs text-slate-500">Last 1 Hour</p>
          </CardContent></Card>
          <Card className="border-amber-200"><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-amber-600">{stats.last_24h}</p>
            <p className="text-xs text-slate-500">Last 24 Hours</p>
          </CardContent></Card>
          <Card><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-blue-600">{stats.frontend}</p>
            <p className="text-xs text-slate-500 flex items-center justify-center gap-1"><Monitor className="w-3 h-3" /> Frontend</p>
          </CardContent></Card>
          <Card><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-indigo-600">{stats.backend}</p>
            <p className="text-xs text-slate-500 flex items-center justify-center gap-1"><Server className="w-3 h-3" /> Backend</p>
          </CardContent></Card>
        </div>
      )}

      {/* Hourly Trend */}
      {stats?.hourly_trend?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Activity className="w-4 h-4 text-slate-500" /> Error Trend (Last 24h)
          </CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-end gap-1 h-24">
              {stats.hourly_trend.map((h, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1" title={`${h.hour}: ${h.count} errors`}>
                  <div className="w-full bg-red-400 rounded-t transition-all" style={{ height: `${Math.max((h.count / maxHourly) * 80, 2)}px` }} />
                  {i % 4 === 0 && <span className="text-[9px] text-slate-400">{h.hour?.slice(11, 13)}h</span>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Most Frequent Errors */}
      {stats?.top_errors?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" /> Most Frequent Errors
          </CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-slate-100">
              {stats.top_errors.map((e, i) => (
                <div key={i} className="p-3 hover:bg-slate-50" data-testid={`top-error-${i}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">{e.message}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${e.source === 'frontend' ? 'bg-blue-50 text-blue-600' : 'bg-indigo-50 text-indigo-600'}`}>{e.source}</span>
                        <span className="text-xs text-slate-400">{e.error_type}</span>
                        <span className="text-xs text-slate-400">{fmtDate(e.latest)}</span>
                      </div>
                    </div>
                    <span className="text-lg font-bold text-red-600 ml-3">{e.count}x</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error Log */}
      <div className="flex items-center gap-3">
        <h2 className="font-heading text-base font-semibold">Error Log</h2>
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-36" data-testid="error-source-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            <SelectItem value="frontend">Frontend</SelectItem>
            <SelectItem value="backend">Backend</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading...</div>
      ) : errors.length === 0 ? (
        <Card><CardContent className="py-12 text-center">
          <Activity className="w-10 h-10 text-green-300 mx-auto mb-2" />
          <p className="text-slate-500">No errors captured. System is healthy.</p>
        </CardContent></Card>
      ) : (
        <div className="space-y-2" data-testid="error-log-list">
          {errors.map((err) => (
            <Card key={err.id} className="cursor-pointer hover:shadow-sm transition-shadow"
              onClick={() => setSelected(err)} data-testid={`error-log-${err.id}`}>
              <CardContent className="py-3">
                <div className="flex items-start gap-3">
                  {err.source === 'frontend'
                    ? <Monitor className="w-4 h-4 text-blue-500 shrink-0 mt-1" />
                    : <Server className="w-4 h-4 text-indigo-500 shrink-0 mt-1" />}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">{err.message}</p>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${err.source === 'frontend' ? 'bg-blue-50 text-blue-600' : 'bg-indigo-50 text-indigo-600'}`}>{err.source}</span>
                      <span className="text-xs text-slate-400">{err.error_type}</span>
                      {err.endpoint && <span className="text-xs text-slate-400">{err.endpoint}</span>}
                      {err.user_role && <span className="text-xs text-slate-400">{err.user_role}</span>}
                      <span className="text-xs text-slate-400 flex items-center gap-0.5"><Clock className="w-3 h-3" />{fmtDate(err.created_at)}</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Error Detail Dialog */}
      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-w-xl" data-testid="error-detail-dialog">
          <DialogHeader><DialogTitle className="font-heading">Error Detail</DialogTitle></DialogHeader>
          {selected && (
            <div className="space-y-3 max-h-[60vh] overflow-y-auto">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-slate-500">Source:</span> <span className="font-medium">{selected.source}</span></div>
                <div><span className="text-slate-500">Type:</span> <span className="font-medium">{selected.error_type}</span></div>
                <div><span className="text-slate-500">Endpoint:</span> <span className="font-medium">{selected.endpoint || '-'}</span></div>
                <div><span className="text-slate-500">Status:</span> <span className="font-medium">{selected.status_code || '-'}</span></div>
                <div><span className="text-slate-500">User:</span> <span className="font-medium">{selected.user_role || 'anonymous'}</span></div>
                <div><span className="text-slate-500">Time:</span> <span className="font-medium">{fmtDate(selected.created_at)}</span></div>
              </div>
              <div>
                <p className="text-sm text-slate-500 mb-1">Message:</p>
                <div className="bg-red-50 p-3 rounded text-sm text-red-700 break-words">{selected.message}</div>
              </div>
              {selected.stack_trace && (
                <div>
                  <p className="text-sm text-slate-500 mb-1">Stack Trace:</p>
                  <pre className="bg-slate-900 text-green-400 p-3 rounded text-xs overflow-x-auto max-h-48 whitespace-pre-wrap">{selected.stack_trace}</pre>
                </div>
              )}
              {selected.page_url && <div><span className="text-xs text-slate-500">Page: </span><span className="text-xs text-slate-600">{selected.page_url}</span></div>}
              {selected.browser_info && <div><span className="text-xs text-slate-500">Browser: </span><span className="text-xs text-slate-600 break-all">{selected.browser_info}</span></div>}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ══════════════════════════════════════════════════════════
// MAIN PAGE
// ══════════════════════════════════════════════════════════

export default function SystemHealthPage() {
  const [downloading, setDownloading] = useState(false);

  const handleDownloadReport = async () => {
    setDownloading(true);
    try {
      const res = await fetch(`${API_URL}/api/system-health/maintenance-report/download`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error('Failed to generate report');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `VHC_Maintenance_Report_${new Date().toISOString().slice(0,10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success('Maintenance report downloaded');
    } catch (e) {
      toast.error(e.message || 'Failed to download report');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="system-health-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">System Health</h1>
          <p className="text-sm text-slate-500 mt-1">Real-time API monitoring, error tracking & diagnostics</p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <Link to="/admin/security-audit">
            <Button variant="outline" size="sm" className="gap-1.5" data-testid="security-audit-link">
              <ShieldCheck className="w-4 h-4" /> <span className="hidden sm:inline">Security Audit</span>
            </Button>
          </Link>
          <Button variant="outline" size="sm" onClick={handleDownloadReport} disabled={downloading}
            data-testid="download-maintenance-report-btn" className="gap-1.5">
            {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            <span className="hidden sm:inline">{downloading ? 'Generating...' : 'Maintenance Report'}</span>
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="api-metrics" className="w-full">
        <TabsList className="grid w-full grid-cols-2 max-w-md" data-testid="health-tabs">
          <TabsTrigger value="api-metrics" data-testid="tab-api-metrics" className="gap-1.5">
            <Gauge className="w-4 h-4" /> API Metrics
          </TabsTrigger>
          <TabsTrigger value="services" data-testid="tab-services" className="gap-1.5">
            <Server className="w-4 h-4" /> Services & Errors
          </TabsTrigger>
        </TabsList>
        <TabsContent value="api-metrics" className="mt-4">
          <APIMetricsTab />
        </TabsContent>
        <TabsContent value="services" className="mt-4">
          <ServicesErrorsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
