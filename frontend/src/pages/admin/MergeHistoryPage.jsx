import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Loader2, Search, Undo2, History, ChevronLeft, ChevronRight, Users } from 'lucide-react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const authHeaders = () => {
  const t = localStorage.getItem('vhc_token');
  return t ? { Authorization: `Bearer ${t}` } : {};
};

const PAGE = 25;

export default function MergeHistoryPage() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState('');
  const [actor, setActor] = useState('');
  const [loading, setLoading] = useState(true);
  const [undoing, setUndoing] = useState(null); // backup_id being undone
  const [confirmUndo, setConfirmUndo] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
      if (q.trim()) params.append('q', q.trim());
      if (actor.trim()) params.append('actor', actor.trim());
      const r = await axios.get(`${API_URL}/api/admin/candidate-hygiene/merge-history?${params}`,
                                { headers: authHeaders() });
      setRows(r.data.rows || []);
      setTotal(r.data.total || 0);
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to load merge history');
    } finally { setLoading(false); }
  }, [offset, q, actor]);

  useEffect(() => { load(); }, [load]);

  const doUndo = async (backupId) => {
    setUndoing(backupId);
    try {
      const r = await axios.post(`${API_URL}/api/admin/candidate-hygiene/undo-split/${backupId}`, {},
                                 { headers: authHeaders() });
      alert(`Undone. Restored candidate ${r.data.restored_candidate_id.slice(0, 8)}…, deleted ${r.data.deleted_new_candidates} split-created records.`);
      setConfirmUndo(null);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || 'Undo failed');
    } finally { setUndoing(null); }
  };

  const page = Math.floor(offset / PAGE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div className="space-y-4" data-testid="merge-history-page">
      <div className="flex items-center gap-2">
        <History className="h-5 w-5 text-slate-700" />
        <h1 className="text-xl font-semibold">Merge History</h1>
        <Badge variant="outline" className="ml-2" data-testid="mh-total">
          {total.toLocaleString()} splits recorded
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">
        Audit trail of every candidate-split ever performed. Every split is fully reversible.
        Undo is restricted to <code>admin@vhc.in</code>.
      </p>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4 flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[220px]">
            <label className="text-xs font-medium text-muted-foreground">Search by candidate name</label>
            <div className="relative">
              <Search className="h-3.5 w-3.5 absolute left-2 top-2.5 text-muted-foreground" />
              <Input
                data-testid="mh-search"
                className="pl-7 h-8 text-sm"
                placeholder="e.g. Amit Kumar"
                value={q}
                onChange={e => { setQ(e.target.value); setOffset(0); }}
              />
            </div>
          </div>
          <div className="min-w-[200px]">
            <label className="text-xs font-medium text-muted-foreground">Split by (admin email)</label>
            <Input
              data-testid="mh-actor"
              className="h-8 text-sm"
              placeholder="admin@vhc.in"
              value={actor}
              onChange={e => { setActor(e.target.value); setOffset(0); }}
            />
          </div>
          <Button size="sm" variant="ghost" onClick={() => { setQ(''); setActor(''); setOffset(0); }}
                  data-testid="mh-clear">Clear</Button>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="pt-4">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-6 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading merge history…
            </div>
          ) : rows.length === 0 ? (
            <div className="text-sm text-muted-foreground py-6 text-center">No splits found for these filters.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-left text-muted-foreground border-b">
                  <tr>
                    <th className="py-2 pr-3">When</th>
                    <th className="py-2 pr-3">Candidate</th>
                    <th className="py-2 pr-3">Split by</th>
                    <th className="py-2 pr-3">Kept email</th>
                    <th className="py-2 pr-3">Split into</th>
                    <th className="py-2 pr-3">Captures moved</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2 pr-3">Actions</th>
                  </tr>
                </thead>
                <tbody data-testid="mh-tbody">
                  {rows.map(r => (
                    <tr key={r.backup_id} className="border-b hover:bg-slate-50">
                      <td className="py-2 pr-3 whitespace-nowrap">
                        {r.created_at ? new Date(r.created_at).toLocaleString('en-IN', {
                          day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
                        }) : '—'}
                      </td>
                      <td className="py-2 pr-3">
                        <div className="font-medium">{r.candidate_name || '(no name)'}</div>
                        <div className="text-[10px] text-muted-foreground">
                          {r.original_phone || '—'} · {r.candidate_id?.slice(0, 8)}…
                        </div>
                      </td>
                      <td className="py-2 pr-3">{r.created_by || '—'}</td>
                      <td className="py-2 pr-3 font-mono text-[11px]">{r.winner_bucket || '—'}</td>
                      <td className="py-2 pr-3">
                        <div className="flex items-center gap-1">
                          <Users className="h-3 w-3 text-slate-500" />
                          <b>{r.new_candidates_created}</b> new
                        </div>
                        {r.new_buckets && r.new_buckets.length > 0 && (
                          <div className="text-[10px] text-muted-foreground truncate max-w-[200px]"
                               title={r.new_buckets.join(', ')}>
                            {r.new_buckets.slice(0, 2).join(', ')}
                            {r.new_buckets.length > 2 ? ` +${r.new_buckets.length - 2}` : ''}
                          </div>
                        )}
                      </td>
                      <td className="py-2 pr-3">{r.captures_moved}</td>
                      <td className="py-2 pr-3">
                        {r.is_undone ? (
                          <Badge variant="outline" className="text-slate-500">Undone</Badge>
                        ) : (
                          <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">Active</Badge>
                        )}
                      </td>
                      <td className="py-2 pr-3">
                        {!r.is_undone && (
                          <Button
                            size="sm" variant="ghost"
                            className="h-7 text-red-600 hover:text-red-700 hover:bg-red-50"
                            onClick={() => setConfirmUndo(r)}
                            disabled={undoing === r.backup_id}
                            data-testid={`mh-undo-${r.backup_id}`}
                          >
                            {undoing === r.backup_id
                              ? <Loader2 className="h-3 w-3 animate-spin" />
                              : <><Undo2 className="h-3 w-3 mr-1" />Undo</>}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > PAGE && (
            <div className="flex items-center justify-between mt-3 text-xs">
              <span className="text-muted-foreground">
                Showing {offset + 1}–{Math.min(offset + PAGE, total)} of {total.toLocaleString()}
              </span>
              <div className="flex gap-1">
                <Button size="sm" variant="outline"
                        onClick={() => setOffset(Math.max(0, offset - PAGE))}
                        disabled={offset === 0} data-testid="mh-prev">
                  <ChevronLeft className="h-3 w-3" />
                </Button>
                <span className="px-2 py-1 text-muted-foreground">
                  Page {page} / {totalPages}
                </span>
                <Button size="sm" variant="outline"
                        onClick={() => setOffset(offset + PAGE)}
                        disabled={offset + PAGE >= total} data-testid="mh-next">
                  <ChevronRight className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Undo confirmation modal */}
      {confirmUndo && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
             onClick={() => setConfirmUndo(null)}>
          <div className="bg-white rounded-lg max-w-md w-full p-5"
               onClick={e => e.stopPropagation()} data-testid="mh-undo-modal">
            <h3 className="font-semibold flex items-center gap-2 mb-2">
              <Undo2 className="h-5 w-5 text-red-600" />
              Undo this split?
            </h3>
            <div className="text-sm space-y-1 mb-3">
              <div><b>Candidate:</b> {confirmUndo.candidate_name}</div>
              <div><b>Split on:</b> {new Date(confirmUndo.created_at).toLocaleString('en-IN')}</div>
              <div><b>By:</b> {confirmUndo.created_by}</div>
              <div><b>Will delete:</b> {confirmUndo.new_candidates_created} candidate record(s)</div>
              <div><b>Will re-point:</b> {confirmUndo.captures_moved} capture log(s)</div>
            </div>
            <div className="text-xs bg-amber-50 border border-amber-200 rounded p-2 mb-3">
              This restores the original merged record. If more captures came in after the split,
              they stay pointed at whichever candidate they were captured into.
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setConfirmUndo(null)}
                      data-testid="mh-undo-cancel">Cancel</Button>
              <Button size="sm" className="bg-red-600 hover:bg-red-700 text-white"
                      onClick={() => doUndo(confirmUndo.backup_id)}
                      disabled={undoing === confirmUndo.backup_id}
                      data-testid="mh-undo-confirm">
                {undoing === confirmUndo.backup_id
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                  : <Undo2 className="h-3.5 w-3.5 mr-1" />}
                Undo split
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
