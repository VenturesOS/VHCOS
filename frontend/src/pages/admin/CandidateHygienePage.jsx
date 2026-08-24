import { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Loader2, RefreshCw, Search, Wrench, X, AlertTriangle, Zap, CheckCircle2 } from 'lucide-react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const authHeaders = () => {
  const t = localStorage.getItem('vhc_token');
  return t ? { Authorization: `Bearer ${t}` } : {};
};

export default function CandidateHygienePage() {
  const [severity, setSeverity] = useState('all');
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [splitting, setSplitting] = useState(false);
  const [splitResult, setSplitResult] = useState(null);

  // Bulk auto-split
  const [bulkJob, setBulkJob] = useState(null);
  const [bulkStarting, setBulkStarting] = useState(false);
  const [bulkConfirmOpen, setBulkConfirmOpen] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API_URL}/api/admin/candidate-hygiene/conflicts?severity=${severity}&limit=200`,
                                { headers: authHeaders() });
      setRows(r.data.rows || []);
      setTotal(r.data.total || 0);
    } finally { setLoading(false); }
  }, [severity]);

  useEffect(() => { load(); }, [load]);

  // ── Bulk auto-split status polling ──
  const fetchBulkStatus = useCallback(async () => {
    try {
      const r = await axios.get(`${API_URL}/api/admin/candidate-hygiene/bulk-split/status`,
                                { headers: authHeaders() });
      setBulkJob(r.data && r.data.status !== 'none' ? r.data : null);
      return r.data;
    } catch { return null; }
  }, []);

  useEffect(() => { fetchBulkStatus(); }, [fetchBulkStatus]);

  useEffect(() => {
    if (bulkJob && (bulkJob.status === 'running' || bulkJob.status === 'queued')) {
      pollRef.current = setInterval(async () => {
        const j = await fetchBulkStatus();
        if (j && (j.status === 'done' || j.status === 'crashed')) {
          clearInterval(pollRef.current);
          load(); // refresh conflict list after job finishes
        }
      }, 3000);
      return () => clearInterval(pollRef.current);
    }
  }, [bulkJob?.status, fetchBulkStatus, load]);

  const startBulkSplit = async () => {
    setBulkStarting(true);
    try {
      await axios.post(`${API_URL}/api/admin/candidate-hygiene/bulk-split/start`, {},
                       { headers: authHeaders() });
      setBulkConfirmOpen(false);
      await fetchBulkStatus();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to start bulk split');
    } finally { setBulkStarting(false); }
  };

  const openDetail = async (cid) => {
    setDetailLoading(true);
    setSplitResult(null);
    try {
      const r = await axios.get(`${API_URL}/api/admin/candidate-hygiene/detail/${cid}`,
                                { headers: authHeaders() });
      setDetail(r.data);
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed');
    } finally { setDetailLoading(false); }
  };

  const runSplit = async (dryRun) => {
    if (!detail) return;
    setSplitting(true);
    try {
      const cid = detail.candidate_bank_state.id;
      const r = await axios.post(
        `${API_URL}/api/admin/candidate-hygiene/split/${cid}?dry_run=${dryRun}`,
        {}, { headers: authHeaders() }
      );
      setSplitResult(r.data);
      if (!dryRun) {
        await load();  // refresh conflict list
      }
    } catch (e) {
      alert(e.response?.data?.detail || 'Split failed');
    } finally { setSplitting(false); }
  };

  return (
    <div className="space-y-4" data-testid="candidate-hygiene">
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            Candidate Hygiene — cross-contaminated records
          </h2>
          <p className="text-xs text-muted-foreground">
            Records where 2+ distinct real humans were merged into one candidate_id (caused by pre-Feb-2026 same-name dedupe bug). Click any row to inspect and split.
          </p>
        </div>
        <select value={severity} onChange={e => setSeverity(e.target.value)} className="h-8 rounded border px-2 text-xs" data-testid="ch-severity">
          <option value="all">All conflicts</option>
          <option value="email">Email conflicts only</option>
          <option value="phone">Phone conflicts only</option>
        </select>
        <Button size="sm" variant="outline" onClick={load} data-testid="ch-refresh"><RefreshCw className="h-3.5 w-3.5" /></Button>
      </div>

      <Card>
        <CardContent className="pt-4">
          <div className="text-2xl font-bold text-red-600" data-testid="ch-total">{total.toLocaleString()}</div>
          <div className="text-xs text-muted-foreground">contaminated candidate_bank records detected</div>
        </CardContent>
      </Card>

      {/* Bulk auto-split panel */}
      <Card className="border-amber-200 bg-amber-50/40" data-testid="ch-bulk-panel">
        <CardContent className="pt-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 font-semibold text-sm">
                <Zap className="h-4 w-4 text-amber-600" />
                Auto-Bulk Split (Safe Mode)
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Splits every contaminated record that has <b>≥2 distinct email addresses</b> using the same
                email-bucket logic as the manual button. Runs in the background — you can close this tab.
                Ambiguous records (only phone/employer mismatch, no clear emails) are skipped and stay
                visible above for manual review. Every split is logged to <code>merged_conflicts_backup</code> and can be undone.
              </p>

              {bulkJob && (
                <div className="mt-3 text-xs">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant={
                      bulkJob.status === 'done' ? 'default' :
                      bulkJob.status === 'crashed' ? 'destructive' :
                      bulkJob.status === 'running' ? 'secondary' : 'outline'
                    } data-testid="ch-bulk-status">
                      {bulkJob.status === 'running' && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
                      {bulkJob.status === 'done' && <CheckCircle2 className="h-3 w-3 mr-1" />}
                      {bulkJob.status.toUpperCase()}
                    </Badge>
                    <span>Progress: <b>{bulkJob.processed || 0}</b> / {bulkJob.total || 0}</span>
                    <span>· Split: <b className="text-green-700">{bulkJob.succeeded || 0}</b></span>
                    <span>· Skipped: <b>{bulkJob.skipped || 0}</b></span>
                    {(bulkJob.failed || 0) > 0 && <span>· Failed: <b className="text-red-600">{bulkJob.failed}</b></span>}
                    <span className="text-muted-foreground">
                      · Started {bulkJob.started_at ? new Date(bulkJob.started_at).toLocaleString('en-IN') : '—'}
                      {bulkJob.started_by ? ` by ${bulkJob.started_by}` : ''}
                    </span>
                  </div>
                  {bulkJob.total > 0 && (
                    <div className="mt-1.5 h-1.5 bg-slate-200 rounded overflow-hidden max-w-md">
                      <div
                        className={`h-full ${bulkJob.status === 'crashed' ? 'bg-red-500' : 'bg-emerald-500'} transition-all`}
                        style={{ width: `${Math.min(100, Math.round(((bulkJob.processed || 0) / bulkJob.total) * 100))}%` }}
                      />
                    </div>
                  )}
                  {bulkJob.status === 'done' && (
                    <div className="mt-2 text-green-800 bg-green-50 border border-green-200 rounded px-2 py-1.5">
                      ✓ Finished at {new Date(bulkJob.finished_at).toLocaleString('en-IN')} — {bulkJob.succeeded} record{bulkJob.succeeded === 1 ? '' : 's'} split, {bulkJob.skipped} skipped.
                    </div>
                  )}
                  {bulkJob.status === 'crashed' && (
                    <div className="mt-2 text-red-800 bg-red-50 border border-red-200 rounded px-2 py-1.5">
                      ✗ Job crashed: {bulkJob.crash_reason || 'unknown'}
                    </div>
                  )}
                  {bulkJob.errors && bulkJob.errors.length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-muted-foreground">
                        Errors / skipped ({bulkJob.errors.length}{bulkJob.errors.length >= 50 ? '+' : ''})
                      </summary>
                      <pre className="text-[10px] bg-white border rounded p-2 mt-1 max-h-40 overflow-auto">
                        {bulkJob.errors.map(e => `${e.candidate_id.slice(0, 8)}… — ${e.reason}`).join('\n')}
                      </pre>
                    </details>
                  )}
                </div>
              )}
            </div>
            <div className="flex flex-col gap-2 shrink-0">
              <Button
                size="sm"
                onClick={() => setBulkConfirmOpen(true)}
                disabled={bulkStarting || (bulkJob && (bulkJob.status === 'running' || bulkJob.status === 'queued'))}
                className="bg-amber-600 hover:bg-amber-700 text-white"
                data-testid="ch-bulk-start"
              >
                <Zap className="h-3.5 w-3.5 mr-1" />
                {bulkJob && (bulkJob.status === 'running' || bulkJob.status === 'queued') ? 'Running…' : 'Start Bulk Split'}
              </Button>
              <Button size="sm" variant="ghost" onClick={fetchBulkStatus} data-testid="ch-bulk-refresh">
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {loading ? <div className="flex justify-center py-6"><Loader2 className="animate-spin" /></div> : (
        <Card>
          <CardContent className="pt-4">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground border-b">
                <tr>
                  <th className="text-left py-1">Candidate</th>
                  <th className="text-right"># emails</th>
                  <th className="text-right"># captures</th>
                  <th className="text-left pl-3">Sample emails</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.candidate_id} className="border-b hover:bg-muted/40">
                    <td className="py-1.5">{r.candidate_name}</td>
                    <td className="text-right"><Badge variant={r.n_distinct_emails >= 5 ? 'destructive' : 'secondary'}>{r.n_distinct_emails}</Badge></td>
                    <td className="text-right">{r.n_captures}</td>
                    <td className="pl-3 text-xs text-muted-foreground max-w-[380px] truncate">{r.sample_emails.join(', ')}</td>
                    <td><Button size="sm" variant="ghost" onClick={() => openDetail(r.candidate_id)} data-testid={`ch-inspect-${r.candidate_id.slice(0,8)}`}><Search className="h-3.5 w-3.5" /></Button></td>
                  </tr>
                ))}
                {!rows.length && <tr><td colSpan={5} className="py-4 text-center text-muted-foreground">No conflicts.</td></tr>}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* detail modal */}
      {detail && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => { setDetail(null); setSplitResult(null); }}>
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[85vh] overflow-auto p-5" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold">
                {detail.candidate_bank_state.name} — {detail.identity_buckets.length} identity buckets, {detail.total_captures} captures
              </h3>
              <Button size="sm" variant="ghost" onClick={() => { setDetail(null); setSplitResult(null); }}><X className="h-4 w-4" /></Button>
            </div>

            {detailLoading ? <Loader2 className="animate-spin" /> : (
              <>
                <div className="text-xs bg-slate-50 rounded p-3 mb-3">
                  <div><b>Current bank state:</b> {detail.candidate_bank_state.name} — {detail.candidate_bank_state.email || '(no email)'} — {detail.candidate_bank_state.current_employer || '(no employer)'}</div>
                </div>

                <table className="w-full text-xs mb-4">
                  <thead className="text-muted-foreground border-b">
                    <tr><th className="text-left py-1">Identity (email)</th><th className="text-right">Captures</th><th className="text-left pl-3">Employers seen</th><th className="text-right">Latest</th></tr>
                  </thead>
                  <tbody>
                    {detail.identity_buckets.map((b, i) => (
                      <tr key={i} className="border-b">
                        <td className="py-1.5 font-mono">{b.identity_key}</td>
                        <td className="text-right">{b.capture_count}</td>
                        <td className="pl-3 text-muted-foreground">{b.sample_employers.join(' / ') || '-'}</td>
                        <td className="text-right whitespace-nowrap">{b.latest_capture ? new Date(b.latest_capture).toLocaleDateString('en-IN') : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => runSplit(true)} disabled={splitting} data-testid="ch-dryrun">
                    {splitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wrench className="h-3.5 w-3.5 mr-1" />} Dry-run split
                  </Button>
                  <Button size="sm" onClick={() => runSplit(false)} disabled={splitting || !splitResult} className="bg-red-600 hover:bg-red-700" data-testid="ch-execsplit">
                    Execute split
                  </Button>
                  <span className="text-xs text-muted-foreground">Backup created; can be undone via admin@vhc.in.</span>
                </div>

                {splitResult && (
                  <pre className="mt-3 text-xs bg-green-50 border border-green-200 rounded p-3 overflow-auto max-h-64">{JSON.stringify(splitResult, null, 2)}</pre>
                )}
              </>
            )}
          </div>
        </div>
      )}
      {/* Bulk-split confirmation modal */}
      {bulkConfirmOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setBulkConfirmOpen(false)}>
          <div className="bg-white rounded-lg max-w-md w-full p-5" onClick={e => e.stopPropagation()} data-testid="ch-bulk-confirm">
            <h3 className="font-semibold flex items-center gap-2 mb-2">
              <AlertTriangle className="h-5 w-5 text-amber-600" />
              Confirm bulk auto-split
            </h3>
            <p className="text-sm text-muted-foreground mb-3">
              This will iterate all {total.toLocaleString()} contaminated records and split every one that has
              ≥2 distinct email identities. Ambiguous records (no clear emails) are skipped.
              Every split is backed up and reversible.
            </p>
            <div className="text-xs bg-amber-50 border border-amber-200 rounded p-2 mb-3">
              Mode: <b>safe_min2_emails</b> — no destructive merges, no data loss.
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setBulkConfirmOpen(false)} data-testid="ch-bulk-cancel">Cancel</Button>
              <Button size="sm" onClick={startBulkSplit} disabled={bulkStarting}
                      className="bg-amber-600 hover:bg-amber-700 text-white" data-testid="ch-bulk-confirm-start">
                {bulkStarting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5 mr-1" />}
                Start job
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
