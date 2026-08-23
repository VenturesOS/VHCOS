import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Loader2, RefreshCw, Search, Wrench, X, AlertTriangle } from 'lucide-react';
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
    </div>
  );
}
