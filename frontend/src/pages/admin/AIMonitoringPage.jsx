import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Progress } from '../../components/ui/progress';
import { Activity, Cpu, AlertTriangle, CheckCircle2, RefreshCw, PlayCircle, TrendingUp, Zap } from 'lucide-react';
import { toast } from 'sonner';
import api from '../../lib/api';

const fmtTime = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

const StateBadge = ({ state }) => {
  const map = {
    healthy: { cls: 'bg-green-100 text-green-800 border-green-300', icon: CheckCircle2 },
    ok: { cls: 'bg-green-100 text-green-800 border-green-300', icon: CheckCircle2 },
    warning: { cls: 'bg-amber-100 text-amber-800 border-amber-300', icon: AlertTriangle },
    critical: { cls: 'bg-red-100 text-red-800 border-red-300', icon: AlertTriangle },
    unknown: { cls: 'bg-slate-100 text-slate-700 border-slate-300', icon: Activity },
  };
  const { cls, icon: Icon } = map[state] || map.unknown;
  return (
    <Badge className={`${cls} gap-1.5`} data-testid={`state-badge-${state}`}>
      <Icon className="w-3.5 h-3.5" />{state?.toUpperCase() || 'UNKNOWN'}
    </Badge>
  );
};

export default function AIMonitoringPage() {
  const [banner, setBanner] = useState(null);
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [starting, setStarting] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [b, h, s, j] = await Promise.all([
        api.get('/admin/llm/live-banner'),
        api.get('/admin/runpod/health'),
        api.get('/admin/llm/failure-stats?hours=24'),
        api.get('/candidate-bank/data-quality/bulk-re-enrich/status'),
      ]);
      setBanner(b.data);
      setHealth(h.data);
      setStats(s.data);
      setJobs(j.data?.jobs || []);
      const running = (j.data?.jobs || []).find((jj) => jj.status === 'running');
      if (running) setActiveJob(running);
    } catch (e) {
      console.error('[AIMonitoring] load failed', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    const t = setInterval(loadAll, 15000); // refresh every 15s
    return () => clearInterval(t);
  }, [loadAll]);

  // More aggressive poll if a bulk re-enrich job is running
  useEffect(() => {
    if (!activeJob || activeJob.status !== 'running') return;
    const t = setInterval(async () => {
      try {
        const r = await api.get(`/candidate-bank/data-quality/bulk-re-enrich/status/${activeJob.id}`);
        setActiveJob(r.data);
        if (r.data.status !== 'running') {
          toast.success(`Bulk re-enrich complete: ${r.data.succeeded} succeeded, ${r.data.failed} failed`);
          loadAll();
        }
      } catch {}
    }, 3000);
    return () => clearInterval(t);
  }, [activeJob?.id, activeJob?.status, loadAll]);

  const forceSync = async () => {
    setSyncing(true);
    try {
      const r = await api.post('/admin/runpod/sync-now');
      setHealth(r.data);
      toast.success(`RunPod synced: ${r.data.vllm_reachable ? 'vLLM reachable' : 'unreachable'}`);
    } catch (e) {
      toast.error('Sync failed — check backend logs');
    }
    setSyncing(false);
  };

  const startBulkReenrich = async (limit = 500) => {
    setStarting(true);
    try {
      const r = await api.post(`/candidate-bank/data-quality/bulk-re-enrich?gaps_only=true&since_hours=720&limit=${limit}&concurrency=4`);
      toast.success(`Started: ${r.data.scheduled} candidates queued of ${r.data.total_matched} matched`);
      setActiveJob({ id: r.data.job_id, total: r.data.scheduled, status: 'running', processed: 0, succeeded: 0, failed: 0, skipped_no_text: 0, progress_pct: 0 });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to start');
    }
    setStarting(false);
  };

  const dryRun = async () => {
    try {
      const r = await api.post('/candidate-bank/data-quality/bulk-re-enrich?dry_run=true&gaps_only=true&since_hours=720');
      toast.info(r.data.message);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Dry-run failed');
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64"><RefreshCw className="w-6 h-6 animate-spin text-slate-500" /></div>;
  }

  return (
    <div className="space-y-5" data-testid="ai-monitoring-page">
      {/* Live banner — shown at top if warning/critical */}
      {banner && banner.state !== 'healthy' && (
        <div
          className={`rounded-lg px-4 py-3 border-l-4 flex items-start gap-3 ${
            banner.state === 'critical' ? 'bg-red-50 border-red-500 text-red-900' : 'bg-amber-50 border-amber-500 text-amber-900'
          }`}
          data-testid="llm-live-banner"
        >
          <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="font-semibold text-sm">{banner.message}</div>
            <div className="text-xs opacity-75 mt-0.5">
              Pod: {banner.details?.pod_name || '—'} | Last sync: {fmtTime(banner.details?.last_sync_at)}
            </div>
          </div>
        </div>
      )}

      {/* Top row — RunPod health + Qwen stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* RunPod Health */}
        <Card data-testid="runpod-health-card">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-600" /> RunPod vLLM
            </CardTitle>
            <Button size="sm" variant="outline" onClick={forceSync} disabled={syncing} data-testid="force-sync-btn">
              <RefreshCw className={`w-3.5 h-3.5 mr-1 ${syncing ? 'animate-spin' : ''}`} />
              Sync Now
            </Button>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Reachable</span>
              {health?.vllm_reachable ? (
                <Badge className="bg-green-100 text-green-800 border-green-300 gap-1">
                  <CheckCircle2 className="w-3 h-3" /> YES
                </Badge>
              ) : (
                <Badge className="bg-red-100 text-red-800 border-red-300 gap-1">
                  <AlertTriangle className="w-3 h-3" /> NO
                </Badge>
              )}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Pod</span>
              <span className="font-mono text-xs truncate max-w-[200px]" title={health?.pod_id}>{health?.pod_id || '—'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">GPU</span>
              <span className="font-medium">{health?.pod_machine_gpu || '—'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Status</span>
              <Badge variant="outline" className="text-xs">{health?.pod_status || '—'}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Model</span>
              <span className="font-mono text-xs truncate max-w-[220px]">{health?.vllm_model || '—'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Auto-sync daemon</span>
              <Badge variant={health?.auto_sync_enabled ? 'default' : 'secondary'}>
                {health?.auto_sync_enabled ? 'ENABLED' : 'DISABLED (no API key)'}
              </Badge>
            </div>
            <div className="flex items-center justify-between text-xs text-slate-500 pt-2 border-t">
              <span>Last sync</span>
              <span>{fmtTime(health?.last_sync_at)}</span>
            </div>
            {health?.last_error && (
              <div className="text-xs bg-red-50 text-red-700 rounded px-2 py-1.5" data-testid="runpod-error">
                {health.last_error}
              </div>
            )}
          </CardContent>
        </Card>

        {/* LLM routing stats */}
        <Card data-testid="llm-stats-card">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-teal-600" /> LLM Routing (24h)
            </CardTitle>
            <StateBadge state={stats?.health_grade} />
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Total extractions</span>
              <span className="font-semibold">{stats?.total_extractions?.toLocaleString() || 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Qwen 14B (primary)</span>
              <span className="font-semibold text-green-700">{stats?.summary?.runpod_qwen14b_pct || 0}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Regex-only (cache)</span>
              <span className="font-semibold text-slate-700">{stats?.summary?.regex_only_pct || 0}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Anthropic (paid fallback)</span>
              <span className={`font-semibold ${stats?.summary?.anthropic_fallback_pct > 10 ? 'text-red-600' : 'text-slate-700'}`}>
                {stats?.summary?.anthropic_fallback_pct || 0}% ({stats?.summary?.anthropic_fallback_count || 0})
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Qwen retry rescues</span>
              <span className="font-semibold">{stats?.summary?.qwen_retry_rescues || 0}</span>
            </div>
            <div className="pt-2 border-t">
              <div className="text-xs text-slate-500 mb-1.5">Full breakdown</div>
              <div className="space-y-1 max-h-40 overflow-auto">
                {(stats?.by_source || []).map((s) => (
                  <div key={s.source} className="flex items-center justify-between text-xs">
                    <span className="font-mono truncate">{s.source}</span>
                    <span className="font-semibold">{s.count.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bulk Re-Enrich */}
      <Card data-testid="bulk-reenrich-card">
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-600" /> Bulk Re-Enrich
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={dryRun} data-testid="bulk-reenrich-dryrun-btn">
              Dry Run
            </Button>
            <Button
              size="sm"
              className="bg-amber-600 hover:bg-amber-700"
              onClick={() => startBulkReenrich(500)}
              disabled={starting || (activeJob?.status === 'running')}
              data-testid="bulk-reenrich-start-btn"
            >
              <PlayCircle className="w-3.5 h-3.5 mr-1" />
              Start 500-batch
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-slate-500 mb-3">
            Re-runs the Qwen 14B pipeline on candidates with missing top-card fields (experience_years=0, CTC=null, notice_period=null). Dry-run first to see how many match.
          </p>

          {activeJob && (
            <div className="space-y-2" data-testid="active-job-progress">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">
                  {activeJob.status === 'running' ? 'Running' : activeJob.status === 'completed' ? 'Completed' : 'Failed'}
                  {activeJob.last_candidate && <span className="text-xs text-slate-500 ml-2">— {activeJob.last_candidate}</span>}
                </span>
                <span className="font-semibold">{activeJob.processed || 0}/{activeJob.total || 0} ({activeJob.progress_pct || 0}%)</span>
              </div>
              <Progress value={activeJob.progress_pct || 0} className="h-2" />
              <div className="grid grid-cols-4 gap-2 text-xs pt-1">
                <div className="bg-green-50 text-green-900 rounded px-2 py-1">
                  <div className="font-semibold">{activeJob.succeeded || 0}</div>
                  <div className="opacity-75">Succeeded</div>
                </div>
                <div className="bg-red-50 text-red-900 rounded px-2 py-1">
                  <div className="font-semibold">{activeJob.failed || 0}</div>
                  <div className="opacity-75">Failed</div>
                </div>
                <div className="bg-slate-50 text-slate-900 rounded px-2 py-1">
                  <div className="font-semibold">{activeJob.skipped_no_text || 0}</div>
                  <div className="opacity-75">Skipped</div>
                </div>
                <div className="bg-indigo-50 text-indigo-900 rounded px-2 py-1">
                  <div className="font-semibold truncate">{Object.keys(activeJob.by_source || {})[0] || '—'}</div>
                  <div className="opacity-75">Top source</div>
                </div>
              </div>
            </div>
          )}

          {jobs.length > 0 && (
            <div className="mt-4 pt-3 border-t">
              <div className="text-xs font-semibold text-slate-600 mb-2">Recent Jobs</div>
              <div className="space-y-1.5">
                {jobs.slice(0, 5).map((j) => (
                  <div key={j.id} className="flex items-center justify-between text-xs bg-slate-50 rounded px-2 py-1.5">
                    <span className="font-mono text-slate-500 truncate max-w-[140px]">{j.id.slice(0, 10)}</span>
                    <span className="text-slate-600 truncate max-w-[200px]">{fmtTime(j.started_at)}</span>
                    <span className="font-semibold">{j.succeeded || 0}/{j.total || 0}</span>
                    <Badge variant="outline" className={`text-[10px] ${j.status === 'completed' ? 'border-green-300 text-green-700' : j.status === 'failed' ? 'border-red-300 text-red-700' : 'border-amber-300 text-amber-700'}`}>
                      {j.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
