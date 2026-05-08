import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import { FileSearch, RefreshCw, Eye, X } from 'lucide-react';
import { toast } from 'sonner';
import api from '../../lib/api';

const fmtTime = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

function DiffCell({ value }) {
  if (value === null || value === undefined || value === '') {
    return <span className="text-slate-400 italic">null</span>;
  }
  if (Array.isArray(value)) {
    return <span className="text-slate-700">[{value.length} items]</span>;
  }
  if (typeof value === 'object') {
    return <span className="text-slate-700 font-mono text-xs">{JSON.stringify(value).slice(0, 80)}...</span>;
  }
  return <span className="text-slate-900">{String(value)}</span>;
}

function TraceDetailModal({ trace, onClose }) {
  if (!trace) return null;
  const rx = trace.regex_output || {};
  const llm = trace.llm_output || {};
  const merged = trace.merged_output || {};
  const allKeys = Array.from(new Set([
    ...Object.keys(rx), ...Object.keys(llm), ...Object.keys(merged),
  ])).sort();

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg max-w-6xl w-full max-h-[90vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b p-4 flex items-center justify-between z-10">
          <div>
            <div className="font-semibold">{trace.candidate_name || '—'}</div>
            <div className="text-xs text-slate-500 flex gap-3">
              <span>source: <Badge variant="outline" className="text-[10px]">{trace.llm_source}</Badge></span>
              <span>endpoint: {trace.endpoint}</span>
              <span>{fmtTime(trace.created_at)}</span>
              <span>{trace.raw_text_length?.toLocaleString()} chars</span>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="w-4 h-4" /></Button>
        </div>

        <div className="p-4 space-y-4">
          {/* Side-by-side diff */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-slate-100 sticky top-0">
                <tr>
                  <th className="text-left p-2 font-semibold">Field</th>
                  <th className="text-left p-2 font-semibold text-indigo-700">Regex</th>
                  <th className="text-left p-2 font-semibold text-teal-700">LLM</th>
                  <th className="text-left p-2 font-semibold text-green-700">Final (Merged)</th>
                </tr>
              </thead>
              <tbody>
                {allKeys.map((k) => {
                  const r = rx[k]; const l = llm[k]; const m = merged[k];
                  const hasConflict = (r !== undefined && l !== undefined && JSON.stringify(r) !== JSON.stringify(l));
                  return (
                    <tr key={k} className={`border-b ${hasConflict ? 'bg-amber-50' : ''}`}>
                      <td className="p-2 font-mono text-slate-600">{k}</td>
                      <td className="p-2"><DiffCell value={r} /></td>
                      <td className="p-2"><DiffCell value={l} /></td>
                      <td className="p-2 font-semibold"><DiffCell value={m} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Raw text preview */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-semibold">Raw Text (first 4KB)</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="text-xs bg-slate-50 p-3 rounded max-h-64 overflow-auto whitespace-pre-wrap">
                {trace.raw_text_head || '—'}
              </pre>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default function ExtractionAuditPage() {
  const [traces, setTraces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = filter ? `?candidate_name=${encodeURIComponent(filter)}&limit=50` : '?limit=50';
      const r = await api.get(`/debug/extraction-trace${params}`);
      setTraces(r.data.traces || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load traces');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = async (id) => {
    try {
      const r = await api.get(`/debug/extraction-trace/${id}`);
      setSelected(r.data);
    } catch (e) {
      toast.error('Failed to load trace');
    }
  };

  return (
    <div className="space-y-4" data-testid="extraction-audit-page">
      <Card>
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <FileSearch className="w-4 h-4 text-indigo-600" />
            Extraction Audit — Side-by-Side Diff
          </CardTitle>
          <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="audit-refresh-btn">
            <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 mb-3">
            <Input
              placeholder="Filter by candidate name…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && load()}
              className="h-9 text-sm max-w-xs"
              data-testid="audit-filter-input"
            />
            <Button size="sm" onClick={load} data-testid="audit-apply-filter-btn">Apply</Button>
            <span className="text-xs text-slate-500 ml-auto">{traces.length} traces (auto-expire in 72h)</span>
          </div>

          <div className="overflow-x-auto border rounded">
            <table className="w-full text-xs">
              <thead className="bg-slate-100 border-b">
                <tr>
                  <th className="text-left p-2">Time</th>
                  <th className="text-left p-2">Candidate</th>
                  <th className="text-left p-2">Endpoint</th>
                  <th className="text-left p-2">LLM Source</th>
                  <th className="text-left p-2">Exp</th>
                  <th className="text-left p-2">CTC</th>
                  <th className="text-left p-2">Notice</th>
                  <th className="text-left p-2"></th>
                </tr>
              </thead>
              <tbody>
                {traces.length === 0 && (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-slate-400">
                      {loading ? 'Loading…' : 'No traces yet. They accumulate as candidates are captured.'}
                    </td>
                  </tr>
                )}
                {traces.map((t) => {
                  const m = t.merged_output || {};
                  return (
                    <tr key={t.id} className="border-b hover:bg-slate-50" data-testid={`trace-row-${t.id}`}>
                      <td className="p-2 text-slate-500">{fmtTime(t.created_at)}</td>
                      <td className="p-2 font-medium">{t.candidate_name || '—'}</td>
                      <td className="p-2">
                        <Badge variant="outline" className="text-[10px]">{t.endpoint}</Badge>
                      </td>
                      <td className="p-2">
                        <Badge
                          className={`text-[10px] ${
                            t.llm_source?.includes('anthropic') ? 'bg-red-100 text-red-800 border-red-300' :
                            t.llm_source?.includes('runpod') ? 'bg-green-100 text-green-800 border-green-300' :
                            'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {t.llm_source || 'unknown'}
                        </Badge>
                      </td>
                      <td className="p-2">{m.experience_years || m.total_experience_years || '—'}</td>
                      <td className="p-2">{m.current_ctc || m.current_salary ? `₹${((m.current_ctc || m.current_salary) / 100000).toFixed(1)}L` : '—'}</td>
                      <td className="p-2">{m.notice_period || '—'}</td>
                      <td className="p-2">
                        <Button size="sm" variant="ghost" onClick={() => openDetail(t.id)} data-testid={`view-trace-${t.id}`}>
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <TraceDetailModal trace={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
