import { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Loader2, ExternalLink, RefreshCw, Search, X } from 'lucide-react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const authHeaders = () => {
  const t = localStorage.getItem('vhc_token');
  return t ? { Authorization: `Bearer ${t}` } : {};
};

const CAUSE_COLORS = {
  timeout: 'bg-red-100 text-red-800',
  selector_not_found: 'bg-orange-100 text-orange-800',
  auth_or_login_wall: 'bg-yellow-100 text-yellow-800',
  contact_section_collapsed: 'bg-amber-100 text-amber-800',
  page_not_fully_loaded: 'bg-blue-100 text-blue-800',
  search_result_variant_dom: 'bg-purple-100 text-purple-800',
  network_error: 'bg-red-100 text-red-800',
  parse_error: 'bg-red-100 text-red-800',
  field_absent_on_profile: 'bg-gray-100 text-gray-700',
  success: 'bg-green-100 text-green-800',
};

export default function CaptureDiagnosticsPage() {
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ field: null, cause: null });
  const [rows, setRows] = useState([]);
  const [drillLoading, setDrillLoading] = useState(false);
  const [rawLog, setRawLog] = useState(null);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API_URL}/api/admin/capture-diagnostics/summary?days=${days}`,
                                { headers: authHeaders() });
      setSummary(r.data);
    } finally { setLoading(false); }
  }, [days]);

  const loadFailures = useCallback(async () => {
    if (!filter.field && !filter.cause) { setRows([]); return; }
    setDrillLoading(true);
    try {
      const p = new URLSearchParams({ days });
      if (filter.field) p.set('field', filter.field);
      if (filter.cause) p.set('cause', filter.cause);
      const r = await axios.get(`${API_URL}/api/admin/capture-diagnostics/failures?${p}`,
                                { headers: authHeaders() });
      setRows(r.data.rows || []);
    } finally { setDrillLoading(false); }
  }, [filter, days]);

  useEffect(() => { loadSummary(); }, [loadSummary]);
  useEffect(() => { loadFailures(); }, [loadFailures]);

  const openRaw = async (logId) => {
    try {
      const r = await axios.get(`${API_URL}/api/admin/capture-diagnostics/capture/${logId}`,
                                { headers: authHeaders() });
      setRawLog(r.data);
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to fetch raw log');
    }
  };

  if (loading) return <div className="flex items-center justify-center h-40"><Loader2 className="animate-spin" /></div>;
  if (!summary) return <div className="text-sm text-muted-foreground">No data.</div>;

  const successRate = summary.success_rate_pct;

  return (
    <div className="space-y-4" data-testid="capture-diagnostics">
      {/* header */}
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <h2 className="text-lg font-semibold">Capture Diagnostics</h2>
          <p className="text-xs text-muted-foreground">Root-cause analysis of extension captures — actionable data for the next update.</p>
        </div>
        <select value={days} onChange={e => setDays(+e.target.value)} className="h-8 rounded border px-2 text-xs" data-testid="cd-days">
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
        <Button size="sm" variant="outline" onClick={loadSummary} data-testid="cd-refresh"><RefreshCw className="h-3.5 w-3.5" /></Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card><CardContent className="pt-4">
          <div className="text-2xl font-bold" data-testid="cd-total">{summary.total_captures.toLocaleString()}</div>
          <div className="text-xs text-muted-foreground">Total captures</div>
        </CardContent></Card>
        <Card><CardContent className="pt-4">
          <div className={`text-2xl font-bold ${successRate >= 90 ? 'text-green-600' : successRate >= 70 ? 'text-amber-600' : 'text-red-600'}`} data-testid="cd-success-rate">{successRate}%</div>
          <div className="text-xs text-muted-foreground">Clean-capture rate</div>
        </CardContent></Card>
        <Card><CardContent className="pt-4">
          <div className="text-2xl font-bold" data-testid="cd-clean">{summary.clean_captures.toLocaleString()}</div>
          <div className="text-xs text-muted-foreground">Captures with 0 missing fields</div>
        </CardContent></Card>
        <Card><CardContent className="pt-4">
          <div className="text-2xl font-bold text-red-600">{(summary.total_captures - summary.clean_captures).toLocaleString()}</div>
          <div className="text-xs text-muted-foreground">Captures missing ≥1 field</div>
        </CardContent></Card>
      </div>

      {/* top causes with fix hints */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Root causes (ranked)</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {summary.top_causes.slice(0, 8).map((c) => (
            <div key={c.cause} className="flex items-start gap-3 text-sm border-l-2 pl-3 py-1"
                 style={{ borderColor: c.cause === 'success' ? '#16a34a' : '#dc2626' }}>
              <button className="shrink-0" onClick={() => setFilter({ field: null, cause: c.cause })} data-testid={`cd-cause-${c.cause}`}>
                <Badge className={CAUSE_COLORS[c.cause] || 'bg-gray-100 text-gray-700'}>{c.cause}</Badge>
              </button>
              <div className="flex-1">
                <div className="font-medium">{c.count.toLocaleString()} captures ({c.pct}%)</div>
                <div className="text-xs text-muted-foreground">{c.action}</div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* field miss table */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Field miss ranking</CardTitle></CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground border-b">
              <tr><th className="text-left py-1">Field</th><th className="text-right">Missed</th><th className="text-right">Miss %</th><th className="text-left pl-4">Top cause</th><th className="text-left pl-4">Also missing with</th><th></th></tr>
            </thead>
            <tbody>
              {summary.field_stats.filter(f => f.missed > 0).map(f => (
                <tr key={f.field} className="border-b hover:bg-muted/40">
                  <td className="py-1.5 font-mono">{f.field}</td>
                  <td className="text-right">{f.missed.toLocaleString()}</td>
                  <td className="text-right"><span className={f.miss_rate_pct > 20 ? 'text-red-600 font-semibold' : ''}>{f.miss_rate_pct}%</span></td>
                  <td className="pl-4"><Badge variant="outline" className={`text-xs ${CAUSE_COLORS[f.top_cause] || ''}`}>{f.top_cause || '-'}</Badge></td>
                  <td className="pl-4 text-xs text-muted-foreground">{f.top_cofailures.map(x => `${x.field}(${x.count})`).join(', ') || '-'}</td>
                  <td><Button size="sm" variant="ghost" onClick={() => setFilter({ field: f.field, cause: null })} data-testid={`cd-field-${f.field}`}><Search className="h-3.5 w-3.5" /></Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* drilldown */}
      {(filter.field || filter.cause) && (
        <Card>
          <CardHeader className="pb-2 flex-row items-center justify-between">
            <CardTitle className="text-base">Drilldown — {filter.field ? `missing "${filter.field}"` : `cause: ${filter.cause}`}</CardTitle>
            <Button size="sm" variant="ghost" onClick={() => setFilter({ field: null, cause: null })}><X className="h-3.5 w-3.5" /></Button>
          </CardHeader>
          <CardContent>
            {drillLoading ? <Loader2 className="animate-spin" /> : (
              <table className="w-full text-xs">
                <thead className="text-muted-foreground border-b">
                  <tr><th className="text-left py-1">When</th><th className="text-left">Candidate</th><th className="text-left">Missing</th><th className="text-left">Cause / step</th><th className="text-right">Dur</th><th></th></tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={r.id} className="border-b hover:bg-muted/40">
                      <td className="py-1 whitespace-nowrap">{new Date(r.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'short', timeStyle: 'short' })}</td>
                      <td className="max-w-[140px] truncate">{r.candidate_name || '-'}</td>
                      <td className="max-w-[220px] truncate text-red-700">{r.missing_fields.join(', ')}</td>
                      <td><Badge className={`text-xs ${CAUSE_COLORS[r.cause] || ''}`}>{r.cause}</Badge>{r.failed_step && <span className="ml-1 text-muted-foreground">/{r.failed_step}</span>}</td>
                      <td className="text-right">{r.capture_duration_ms || '-'}ms</td>
                      <td className="whitespace-nowrap">
                        {r.profile_url && <a href={r.profile_url} target="_blank" rel="noreferrer" className="text-blue-600 inline-flex items-center gap-0.5"><ExternalLink className="h-3 w-3" /></a>}
                        <Button size="sm" variant="ghost" className="h-6 px-1 ml-1" onClick={() => openRaw(r.id)}>raw</Button>
                      </td>
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={6} className="text-center py-4 text-muted-foreground">No matches.</td></tr>}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}

      {/* raw modal */}
      {rawLog && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setRawLog(null)}>
          <div className="bg-white rounded-lg max-w-3xl w-full max-h-[80vh] overflow-auto p-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold">Raw capture log</h3>
              <Button size="sm" variant="ghost" onClick={() => setRawLog(null)}><X className="h-4 w-4" /></Button>
            </div>
            <pre className="text-xs bg-slate-50 p-3 rounded overflow-auto">{JSON.stringify(rawLog, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
