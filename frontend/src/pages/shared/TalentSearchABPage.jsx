/**
 * LLM Extraction A/B Testing — Nemotron vs RunPod Qwen quality comparison.
 *
 * Repurposed from the old Hybrid-vs-Lexical search page. Powers the
 * `/(admin|recruiter|employer)/talent-search` route (kept the same URL to
 * avoid breaking sidebar links, but the sidebar label is now "LLM A/B Testing").
 *
 * Flow:
 *   1. Admin clicks "Start comparison" — POST /api/admin/llm-ab/run
 *   2. Backend spawns background task that runs first 100 extension-captured
 *      candidates through Nemotron + Qwen in parallel
 *   3. Frontend polls /status/{id} every 3s, shows progress
 *   4. When done, renders extensive quality report + per-candidate diff table
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { Play, RefreshCw, Loader2, XCircle, Award, GitCompare, Clock, CheckCircle2, AlertTriangle } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const api = axios.create({ baseURL: API });
api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem('token');
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

// ── Report renderers ────────────────────────────────────────────────────

function MetricCard({ label, nemotron, qwen, better = 'higher', unit = '', testid }) {
  const nemNum = Number(nemotron);
  const qwNum = Number(qwen);
  let nemWins = false, qwWins = false;
  if (Number.isFinite(nemNum) && Number.isFinite(qwNum) && nemNum !== qwNum) {
    if (better === 'higher') { nemWins = nemNum > qwNum; qwWins = qwNum > nemNum; }
    else                     { nemWins = nemNum < qwNum; qwWins = qwNum < nemNum; }
  }
  return (
    <div className="p-3 rounded-md border bg-white" data-testid={testid}>
      <div className="text-xs text-slate-500 mb-2 uppercase tracking-wide">{label}</div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className={`flex flex-col p-2 rounded ${nemWins ? 'bg-emerald-50 border border-emerald-200' : ''}`}>
          <span className="text-[10px] text-slate-500">Nemotron</span>
          <span className="font-mono font-semibold text-slate-900">{nemotron}{unit}</span>
        </div>
        <div className={`flex flex-col p-2 rounded ${qwWins ? 'bg-emerald-50 border border-emerald-200' : ''}`}>
          <span className="text-[10px] text-slate-500">Qwen</span>
          <span className="font-mono font-semibold text-slate-900">{qwen}{unit}</span>
        </div>
      </div>
    </div>
  );
}

function FieldFillTable({ data }) {
  const rows = Object.entries(data);
  return (
    <div className="border rounded-md overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-100">
          <tr>
            <th className="text-left px-3 py-2">Field</th>
            <th className="text-right px-3 py-2">Nemotron %</th>
            <th className="text-right px-3 py-2">Qwen %</th>
            <th className="text-right px-3 py-2 w-24">Δ</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([field, r]) => {
            const delta = r.nemotron_pct - r.qwen_pct;
            const winner = Math.abs(delta) < 0.5 ? '=' : delta > 0 ? 'N' : 'Q';
            return (
              <tr key={field} className="border-t hover:bg-slate-50" data-testid={`fill-row-${field}`}>
                <td className="px-3 py-1.5 font-mono text-xs">{field}</td>
                <td className={`text-right px-3 py-1.5 font-mono ${delta > 0.5 ? 'text-emerald-700 font-semibold' : ''}`}>{r.nemotron_pct}%</td>
                <td className={`text-right px-3 py-1.5 font-mono ${delta < -0.5 ? 'text-emerald-700 font-semibold' : ''}`}>{r.qwen_pct}%</td>
                <td className={`text-right px-3 py-1.5 font-mono ${winner === 'N' ? 'text-emerald-600' : winner === 'Q' ? 'text-sky-600' : 'text-slate-400'}`}>
                  {winner === '=' ? '–' : `${winner} +${Math.abs(delta).toFixed(1)}`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ArrayRichnessTable({ data }) {
  return (
    <div className="border rounded-md overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-100">
          <tr>
            <th className="text-left px-3 py-2">Array field</th>
            <th className="text-right px-3 py-2">N avg</th>
            <th className="text-right px-3 py-2">Q avg</th>
            <th className="text-right px-3 py-2">N zero%</th>
            <th className="text-right px-3 py-2">Q zero%</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data).map(([field, r]) => (
            <tr key={field} className="border-t hover:bg-slate-50" data-testid={`richness-row-${field}`}>
              <td className="px-3 py-1.5 font-mono text-xs">{field}</td>
              <td className="text-right px-3 py-1.5 font-mono">{r.nemotron_avg}</td>
              <td className="text-right px-3 py-1.5 font-mono">{r.qwen_avg}</td>
              <td className="text-right px-3 py-1.5 font-mono text-xs text-slate-500">{r.nemotron_zero_pct}%</td>
              <td className="text-right px-3 py-1.5 font-mono text-xs text-slate-500">{r.qwen_zero_pct}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AgreementTable({ data }) {
  return (
    <div className="border rounded-md overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-100">
          <tr>
            <th className="text-left px-3 py-2">Field</th>
            <th className="text-right px-3 py-2">Agree %</th>
            <th className="text-right px-3 py-2 text-xs text-slate-500">Compared</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data).map(([field, r]) => (
            <tr key={field} className="border-t hover:bg-slate-50" data-testid={`agreement-row-${field}`}>
              <td className="px-3 py-1.5 font-mono text-xs">{field}</td>
              <td className={`text-right px-3 py-1.5 font-mono ${r.agree_pct >= 90 ? 'text-emerald-700' : r.agree_pct >= 70 ? 'text-amber-600' : 'text-red-600'} font-semibold`}>
                {r.agree_pct}%
              </td>
              <td className="text-right px-3 py-1.5 text-xs text-slate-500">{r.agreed}/{r.compared}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Report({ report }) {
  if (!report || report.error) {
    return <p className="text-sm text-slate-500">{report?.error || 'No report'}</p>;
  }
  const { success, latency, response_size, field_fill_rate, array_richness,
          agreement, winner_per_candidate, critical_missing, sample_size, verdict } = report;

  return (
    <div className="space-y-6">
      {/* Verdict banner */}
      <div className="p-4 rounded-md bg-gradient-to-r from-slate-900 to-slate-800 text-white flex items-center gap-3" data-testid="ab-verdict-banner">
        <Award className="h-6 w-6 text-emerald-400 shrink-0" />
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400 mb-0.5">Overall verdict — {sample_size} candidates</div>
          <div className="font-semibold text-base">{verdict}</div>
        </div>
      </div>

      {/* Top-line metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="Success rate" nemotron={`${success.nemotron_success_pct}%`} qwen={`${success.qwen_success_pct}%`} testid="metric-success" />
        <MetricCard label="Avg latency" nemotron={latency.nemotron.avg_ms} qwen={latency.qwen.avg_ms} unit="ms" better="lower" testid="metric-latency" />
        <MetricCard label="p95 latency" nemotron={latency.nemotron.p95_ms} qwen={latency.qwen.p95_ms} unit="ms" better="lower" testid="metric-p95" />
        <MetricCard label="JSON-repair fallback" nemotron={success.nemotron_json_repaired} qwen={success.qwen_json_repaired} better="lower" testid="metric-json-repair" />
        <MetricCard label="Avg response chars" nemotron={response_size.nemotron.avg} qwen={response_size.qwen.avg} testid="metric-size" />
        <MetricCard label="Critical-field missing" nemotron={`${critical_missing.nemotron_pct}%`} qwen={`${critical_missing.qwen_pct}%`} better="lower" testid="metric-missing" />
        <MetricCard label="Winner: Nemotron" nemotron={winner_per_candidate.nemotron} qwen={winner_per_candidate.qwen} testid="metric-winner-nemo" />
        <MetricCard label="Ties / Both-failed" nemotron={winner_per_candidate.tie} qwen={winner_per_candidate.both_failed} better="lower" testid="metric-ties" />
      </div>

      {/* Field-fill rate */}
      <div>
        <h3 className="font-semibold text-slate-900 mb-2 text-sm">Field coverage — % of successful extractions that populated each field</h3>
        <FieldFillTable data={field_fill_rate} />
      </div>

      {/* Array richness */}
      <div>
        <h3 className="font-semibold text-slate-900 mb-2 text-sm">Array richness — avg count + % of records with zero items</h3>
        <ArrayRichnessTable data={array_richness} />
      </div>

      {/* Agreement */}
      <div>
        <h3 className="font-semibold text-slate-900 mb-2 text-sm">Value agreement — % of candidates where both models returned the same value</h3>
        <AgreementTable data={agreement} />
      </div>
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────────

export default function TalentSearchABPage() {
  const [sampleSize, setSampleSize] = useState(100);
  const [sourceFilter, setSourceFilter] = useState('extension');
  const [starting, setStarting] = useState(false);
  const [run, setRun] = useState(null);           // full run doc from server
  const [history, setHistory] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const pollRef = useRef(null);

  const loadHistory = useCallback(async () => {
    try {
      const r = await api.get('/api/admin/llm-ab/runs');
      setHistory(r.data || []);
    } catch (e) { /* silent */ }
  }, []);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const pollStatus = useCallback((runId) => {
    stopPoll();
    const tick = async () => {
      try {
        const r = await api.get(`/api/admin/llm-ab/status/${runId}`);
        setRun(r.data);
        if (['completed', 'failed', 'cancelled'].includes(r.data?.status)) {
          stopPoll();
          loadHistory();
          if (r.data.status === 'completed') toast.success('A/B run complete');
          if (r.data.status === 'failed') toast.error(`A/B run failed: ${r.data.error || 'unknown'}`);
        }
      } catch (e) { /* keep trying */ }
    };
    tick();
    pollRef.current = setInterval(tick, 3000);
  }, [loadHistory]);

  useEffect(() => () => stopPoll(), []);

  const handleStart = useCallback(async () => {
    if (sampleSize < 1 || sampleSize > 500) { toast.error('Sample size must be 1-500'); return; }
    setStarting(true);
    try {
      const r = await api.post('/api/admin/llm-ab/run', null, {
        params: { sample_size: sampleSize, source_filter: sourceFilter },
      });
      toast.success(`Run started — ${r.data.run_id.slice(0, 8)}`);
      setSelectedRunId(r.data.run_id);
      pollStatus(r.data.run_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to start run');
    } finally { setStarting(false); }
  }, [sampleSize, sourceFilter, pollStatus]);

  const handleCancel = useCallback(async () => {
    if (!selectedRunId) return;
    try {
      await api.post(`/api/admin/llm-ab/cancel/${selectedRunId}`);
      toast.success('Cancellation requested');
    } catch (e) { toast.error('Cancel failed'); }
  }, [selectedRunId]);

  const handleView = useCallback((runId) => {
    setSelectedRunId(runId);
    pollStatus(runId);
  }, [pollStatus]);

  const isRunning = run?.status === 'running' || run?.status === 'pending';
  const progressPct = run?.progress?.total ? Math.round(100 * (run.progress.done || 0) / run.progress.total) : 0;

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6" data-testid="llm-ab-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 text-slate-900">
            <GitCompare className="h-6 w-6 text-emerald-600" />
            LLM Extraction A/B
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Runs the first N extension-captured candidates through <b>Nemotron 550B</b> and <b>RunPod Qwen 14B</b> and generates a detailed quality report.
          </p>
        </div>
      </div>

      {/* Controls */}
      <Card>
        <CardHeader><CardTitle className="text-base">Start a new run</CardTitle></CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="text-xs text-slate-500 block mb-1">Sample size</label>
              <Input type="number" min={1} max={500} value={sampleSize}
                     onChange={(e) => setSampleSize(parseInt(e.target.value || '0'))}
                     className="w-32" data-testid="ab-sample-size" />
            </div>
            <div>
              <label className="text-xs text-slate-500 block mb-1">Source filter (regex)</label>
              <Input value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}
                     placeholder="extension" className="w-64" data-testid="ab-source-filter" />
            </div>
            <Button onClick={handleStart} disabled={starting || isRunning}
                    className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="ab-start-btn">
              {starting ? <Loader2 className="animate-spin h-4 w-4 mr-1" /> : <Play className="h-4 w-4 mr-1" />}
              Start comparison
            </Button>
            {isRunning && (
              <Button variant="outline" onClick={handleCancel} data-testid="ab-cancel-btn">
                <XCircle className="h-4 w-4 mr-1" /> Cancel
              </Button>
            )}
            <Button variant="ghost" onClick={loadHistory} data-testid="ab-refresh-btn">
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
          <p className="text-xs text-slate-400 mt-3">
            The run processes 5 candidates in parallel to stay under Nemotron's 40 rpm free tier.
            Expect ~3–6 min for 100 candidates depending on Qwen pod cold-start.
          </p>
        </CardContent>
      </Card>

      {/* Active run / selected run */}
      {run && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center justify-between">
              <span>Run <span className="font-mono text-xs text-slate-500">{run.id?.slice(0, 8)}</span></span>
              <Badge variant={
                run.status === 'completed' ? 'default' :
                run.status === 'failed' ? 'destructive' :
                run.status === 'cancelled' ? 'secondary' : 'outline'
              } data-testid="ab-status-badge">{run.status}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {isRunning && (
              <div>
                <div className="flex justify-between text-xs text-slate-500 mb-1">
                  <span>Progress</span>
                  <span data-testid="ab-progress-text">{run.progress?.done || 0} / {run.progress?.total || 0}</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                  <div className="bg-emerald-500 h-full transition-all" style={{ width: `${progressPct}%` }} data-testid="ab-progress-bar" />
                </div>
              </div>
            )}
            {run.status === 'failed' && (
              <div className="p-3 rounded-md bg-red-50 border border-red-200 text-sm text-red-800 flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <div>
                  <div className="font-semibold mb-0.5">Run failed</div>
                  <div className="font-mono text-xs">{run.error}</div>
                </div>
              </div>
            )}
            {run.status === 'completed' && run.report && (
              <Report report={run.report} />
            )}
          </CardContent>
        </Card>
      )}

      {/* History */}
      <Card>
        <CardHeader><CardTitle className="text-base">Recent runs</CardTitle></CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-sm text-slate-500">No runs yet.</p>
          ) : (
            <div className="border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-100">
                  <tr>
                    <th className="text-left px-3 py-2">Started</th>
                    <th className="text-left px-3 py-2">By</th>
                    <th className="text-left px-3 py-2">Status</th>
                    <th className="text-right px-3 py-2">Sample</th>
                    <th className="text-right px-3 py-2">Progress</th>
                    <th className="text-left px-3 py-2">Verdict</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.id} className="border-t hover:bg-slate-50" data-testid={`ab-history-row-${h.id}`}>
                      <td className="px-3 py-2 text-xs text-slate-500">{h.created_at?.slice(0, 19)?.replace('T', ' ')}</td>
                      <td className="px-3 py-2 text-xs">{h.started_by_name || '—'}</td>
                      <td className="px-3 py-2"><Badge variant="outline" className="text-xs">{h.status}</Badge></td>
                      <td className="px-3 py-2 text-right font-mono text-xs">{h.sample_size}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs">{h.progress?.done ?? 0}/{h.progress?.total ?? 0}</td>
                      <td className="px-3 py-2 text-xs">{h.report?.verdict?.slice(0, 60) || (h.error ? <span className="text-red-600">{h.error.slice(0, 60)}</span> : '—')}</td>
                      <td className="px-3 py-2 text-right">
                        <Button variant="ghost" size="sm" onClick={() => handleView(h.id)} data-testid={`ab-history-view-${h.id}`}>View</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
