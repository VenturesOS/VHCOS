import { useState, useEffect, useRef, useCallback } from 'react';
import { systemErrorsAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { toast } from 'sonner';
import {
  Activity, AlertTriangle, Monitor, Server, Clock, Trash2, RefreshCw,
  Download, Loader2, Shield, Database, Cpu, Zap, Radio, Brain,
  ArrowUpDown, CircleDot, CheckCircle2, XCircle, AlertCircle,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';
function getToken() { return localStorage.getItem('vhc_token'); }

const SERVICE_META = {
  mongodb:             { icon: Database,    label: 'MongoDB',        metricKey: 'latency_ms',     metricLabel: 'Latency' },
  api_server:          { icon: Server,      label: 'API Server',     metricKey: 'latency_ms',     metricLabel: 'Latency' },
  background_workers:  { icon: Cpu,         label: 'Workers',        metricKey: 'stuck_jobs',     metricLabel: 'Stuck Jobs' },
  queue_system:        { icon: ArrowUpDown, label: 'Queue',          metricKey: 'pending',        metricLabel: 'Pending' },
  system_resources:    { icon: Zap,         label: 'Resources',      metricKey: 'memory_percent', metricLabel: 'Memory' },
  automation_pipeline: { icon: Radio,       label: 'Automation',     metricKey: 'success_rate',   metricLabel: 'Success' },
  ai_services:         { icon: Brain,       label: 'AI Services',    metricKey: 'ai_errors_1h',   metricLabel: 'Errors/1h' },
  data_sync:           { icon: CircleDot,   label: 'Data Sync',      metricKey: 'sync_errors_24h',metricLabel: 'Errors/24h' },
};

const STATUS_STYLES = {
  healthy:  { dot: 'bg-emerald-500', ring: 'ring-emerald-500/20', bg: 'bg-emerald-50', text: 'text-emerald-700' },
  warning:  { dot: 'bg-amber-500',   ring: 'ring-amber-500/20',   bg: 'bg-amber-50',   text: 'text-amber-700' },
  critical: { dot: 'bg-red-500',     ring: 'ring-red-500/20',     bg: 'bg-red-50',     text: 'text-red-700' },
  offline:  { dot: 'bg-slate-400',   ring: 'ring-slate-400/20',   bg: 'bg-slate-50',   text: 'text-slate-500' },
};

export default function SystemHealthPage() {
  const [stats, setStats] = useState(null);
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [live, setLive] = useState(null);
  const intervalRef = useRef(null);

  const fetchLive = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/system-health/live-status`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) setLive(await res.json());
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

  // Auto-refresh every 30s
  useEffect(() => {
    intervalRef.current = setInterval(fetchLive, 30000);
    return () => clearInterval(intervalRef.current);
  }, [fetchLive]);

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

  const fmtDate = (ts) => {
    if (!ts) return '-';
    return new Date(ts).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  };

  const fmtTime = (ts) => {
    if (!ts) return '';
    return new Date(ts).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  };

  const maxHourly = stats?.hourly_trend?.reduce((m, h) => Math.max(m, h.count), 0) || 1;
  const currentScore = live?.current_score ?? null;
  const services = live?.services || [];
  const scoreHistory = (live?.score_history || []).map(p => ({
    ...p,
    time: fmtTime(p.timestamp),
  }));
  const incidents = live?.incidents || [];

  return (
    <div className="space-y-6" data-testid="system-health-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">System Health</h1>
          <p className="text-sm text-slate-500 mt-1">Real-time monitoring &middot; Auto-refresh 30s</p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          {currentScore !== null && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200" data-testid="health-score-badge">
              <Shield className={`w-4 h-4 ${currentScore >= 70 ? 'text-emerald-500' : currentScore >= 40 ? 'text-amber-500' : 'text-red-500'}`} />
              <span className="text-sm font-semibold text-slate-700">{currentScore}</span>
              <span className="text-[10px] text-slate-400">/100</span>
            </div>
          )}
          <Button variant="outline" size="sm" onClick={handleDownloadReport} disabled={downloading}
            data-testid="download-maintenance-report-btn" className="gap-1.5">
            {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            <span className="hidden sm:inline">{downloading ? 'Generating...' : 'Maintenance Report'}</span>
          </Button>
          <Button variant="outline" size="sm" onClick={load} data-testid="refresh-health-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button variant="outline" size="sm" className="text-red-600 hover:bg-red-50" onClick={handleClear}
            data-testid="clear-errors-btn">
            <Trash2 className="w-4 h-4 mr-1" /> Clear Old
          </Button>
        </div>
      </div>

      {/* ═══ LIVE SERVICE MONITOR GRID ═══ */}
      {services.length > 0 && (
        <div data-testid="live-service-grid">
          <h2 className="font-heading text-base font-semibold text-slate-800 mb-3">Live Service Monitor</h2>
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
                      <div className={`p-1.5 rounded-md ${st.bg}`}>
                        <Icon className={`w-4 h-4 ${st.text}`} />
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className={`w-2 h-2 rounded-full ${st.dot} ring-4 ${st.ring}`} />
                      </div>
                    </div>
                    <p className="text-xs font-semibold text-slate-800 truncate">{meta.label}</p>
                    <div className="flex items-end justify-between mt-1">
                      <span className="text-lg font-bold text-slate-900">
                        {metricVal !== undefined && metricVal !== null ? `${metricVal}${suffix}` : '-'}
                      </span>
                      <span className="text-[10px] text-slate-400">{meta.metricLabel}</span>
                    </div>
                    <div className="flex items-center justify-between mt-1.5 text-[10px] text-slate-400">
                      <span>{fmtTime(svc.timestamp)}</span>
                      {svc.failure_count_24h > 0 && (
                        <span className="text-red-500 font-medium">{svc.failure_count_24h} failures</span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* ═══ HEALTH SCORE TREND + INCIDENTS (2-col) ═══ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Score Trend Chart */}
        {scoreHistory.length > 1 && (
          <Card className="lg:col-span-2" data-testid="health-score-chart">
            <CardHeader className="pb-2">
              <CardTitle className="font-heading text-base flex items-center gap-2">
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
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0', boxShadow: '0 2px 8px rgba(0,0,0,.06)' }}
                    formatter={(v) => [`${v}/100`, 'Score']}
                  />
                  <Area type="monotone" dataKey="score" stroke="#059669" strokeWidth={2} fill="url(#scoreGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* Active Incidents Panel */}
        <Card data-testid="active-incidents-panel">
          <CardHeader className="pb-2">
            <CardTitle className="font-heading text-base flex items-center gap-2">
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
                            <span className="text-xs font-semibold text-slate-800">
                              {SERVICE_META[inc.service_name]?.label || inc.service_name}
                            </span>
                            <Badge variant="outline" className={`text-[9px] py-0 px-1 ${st.text} border-current`}>{inc.status}</Badge>
                          </div>
                          <p className="text-[10px] text-slate-400 truncate mt-0.5">
                            {inc.error_details || `${inc.status} — see metrics`}
                          </p>
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

      {/* ═══ EXISTING: Error Stats ═══ */}
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

      {/* ═══ EXISTING: Hourly trend ═══ */}
      {stats?.hourly_trend?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="font-heading text-base flex items-center gap-2">
            <Activity className="w-4 h-4 text-slate-500" /> Error Trend (Last 24h)
          </CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-end gap-1 h-24">
              {stats.hourly_trend.map((h, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1" title={`${h.hour}: ${h.count} errors`}>
                  <div className="w-full bg-red-400 rounded-t transition-all"
                    style={{ height: `${Math.max((h.count / maxHourly) * 80, 2)}px` }} />
                  {i % 4 === 0 && <span className="text-[9px] text-slate-400">{h.hour?.slice(11, 13)}h</span>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ═══ EXISTING: Most frequent errors ═══ */}
      {stats?.top_errors?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="font-heading text-base flex items-center gap-2">
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
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          e.source === 'frontend' ? 'bg-blue-50 text-blue-600' : 'bg-indigo-50 text-indigo-600'
                        }`}>{e.source}</span>
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

      {/* ═══ EXISTING: Error log ═══ */}
      <div className="flex items-center gap-3">
        <h2 className="font-heading text-lg font-semibold">Error Log</h2>
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
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                        err.source === 'frontend' ? 'bg-blue-50 text-blue-600' : 'bg-indigo-50 text-indigo-600'
                      }`}>{err.source}</span>
                      <span className="text-xs text-slate-400">{err.error_type}</span>
                      {err.endpoint && <span className="text-xs text-slate-400">{err.endpoint}</span>}
                      {err.user_role && <span className="text-xs text-slate-400">{err.user_role}</span>}
                      <span className="text-xs text-slate-400 flex items-center gap-0.5">
                        <Clock className="w-3 h-3" />{fmtDate(err.created_at)}
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ═══ EXISTING: Error detail dialog ═══ */}
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
                  <pre className="bg-slate-900 text-green-400 p-3 rounded text-xs overflow-x-auto max-h-48 whitespace-pre-wrap">
                    {selected.stack_trace}
                  </pre>
                </div>
              )}
              {selected.page_url && (
                <div><span className="text-xs text-slate-500">Page: </span><span className="text-xs text-slate-600">{selected.page_url}</span></div>
              )}
              {selected.browser_info && (
                <div><span className="text-xs text-slate-500">Browser: </span><span className="text-xs text-slate-600 break-all">{selected.browser_info}</span></div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
