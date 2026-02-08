import { useState, useEffect } from 'react';
import { systemErrorsAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { Activity, AlertTriangle, Monitor, Server, Clock, Trash2, RefreshCw } from 'lucide-react';

export default function SystemHealthPage() {
  const [stats, setStats] = useState(null);
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState(null);

  useEffect(() => { load(); }, [filter]);

  const load = async () => {
    try {
      const params = {};
      if (filter !== 'all') params.source = filter;
      const [statsRes, errorsRes] = await Promise.all([
        systemErrorsAPI.getStats(),
        systemErrorsAPI.getAll(params),
      ]);
      setStats(statsRes.data);
      setErrors(errorsRes.data);
    } catch {
      toast.error('Failed to load system health data');
    } finally {
      setLoading(false);
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

  const formatDate = (ts) => {
    if (!ts) return '—';
    return new Date(ts).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  };

  // Simple bar chart for hourly trend
  const maxHourly = stats?.hourly_trend?.reduce((m, h) => Math.max(m, h.count), 0) || 1;

  return (
    <div className="space-y-6" data-testid="system-health-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">System Health</h1>
          <p className="text-slate-500 mt-1">Auto-captured errors from frontend and backend</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="refresh-health-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button variant="outline" size="sm" className="text-red-600 hover:bg-red-50" onClick={handleClear}
            data-testid="clear-errors-btn">
            <Trash2 className="w-4 h-4 mr-1" /> Clear Old
          </Button>
        </div>
      </div>

      {/* Stats */}
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

      {/* Hourly trend */}
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

      {/* Most frequent errors */}
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
                        <span className="text-xs text-slate-400">{formatDate(e.latest)}</span>
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

      {/* Error log */}
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
                        <Clock className="w-3 h-3" />{formatDate(err.created_at)}
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Error detail dialog */}
      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-w-xl" data-testid="error-detail-dialog">
          <DialogHeader><DialogTitle className="font-heading">Error Detail</DialogTitle></DialogHeader>
          {selected && (
            <div className="space-y-3 max-h-[60vh] overflow-y-auto">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-slate-500">Source:</span> <span className="font-medium">{selected.source}</span></div>
                <div><span className="text-slate-500">Type:</span> <span className="font-medium">{selected.error_type}</span></div>
                <div><span className="text-slate-500">Endpoint:</span> <span className="font-medium">{selected.endpoint || '—'}</span></div>
                <div><span className="text-slate-500">Status:</span> <span className="font-medium">{selected.status_code || '—'}</span></div>
                <div><span className="text-slate-500">User:</span> <span className="font-medium">{selected.user_role || 'anonymous'}</span></div>
                <div><span className="text-slate-500">Time:</span> <span className="font-medium">{formatDate(selected.created_at)}</span></div>
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
