/**
 * Possible duplicate hires — pairs a human has to judge. Two people can
 * genuinely share a name here, so nothing is merged automatically.
 */
import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Loader2, Copy, Link2, Trash2, Users } from 'lucide-react';
import { toast } from 'sonner';
import api from '../../lib/api';
import { inr } from './RevenueTables';

const KIND_LABEL = {
  cross_system: 'Pipeline + tracker',
  same_client: 'Twice in the tracker',
  same_amount: 'Same amount',
};

function Side({ row, tone }) {
  return (
    <div className={`flex-1 rounded-md border px-3 py-2 ${tone}`}>
      <p className="text-sm font-medium text-slate-900">{row.candidate_name || '—'}</p>
      <p className="text-xs text-slate-500">
        {row.client_name || 'client not recorded'} · {row.date || 'no date'}
        {row.branch ? ` · ${row.branch}` : ''} · {row.recruiter_name || 'no recruiter'}
      </p>
      <p className="text-xs mt-0.5">
        <span className="font-medium">{inr(row.amount)}</span>
        <span className="text-slate-500"> · {row.payment_status || '—'}
          {row.invoice_no ? ` · ${row.invoice_no}` : ''}</span>
      </p>
      <Badge variant="outline" className="mt-1 text-[10px] border-slate-300 text-slate-500">
        {row.source === 'pipeline' ? 'Pipeline' : 'Tracker'}
      </Badge>
    </div>
  );
}

export function DuplicatePanel({ year, onResolved }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get('/branch-revenue/duplicates', { params: { year } });
      setData(res);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not check for duplicates');
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const resolve = async (pair, action) => {
    const key = `${pair.left.candidate_name}-${action}`;
    setBusy(key);
    try {
      const body = {
        action,
        placement_id: pair.right.id,
        ...(pair.left.source === 'pipeline'
          ? { application_id: pair.left.application_id, alias: pair.left.candidate_name }
          : { other_placement_id: pair.left.id, alias: pair.left.candidate_name }),
      };
      const { data: res } = await api.post('/branch-revenue/duplicates/resolve', body);
      toast.success(res.message);
      await load();
      onResolved?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white" data-testid="duplicate-panel">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-slate-100">
        <div className="flex items-start gap-2">
          <Copy className="w-4 h-4 mt-0.5 text-amber-500" />
          <div>
            <p className="text-sm font-medium text-slate-900">
              Possible duplicates{data ? ` (${data.count})` : ''}
            </p>
            <p className="text-xs text-slate-500">
              Hires that look like the same person recorded twice — transposed letters, initials or an
              added surname. Two people can share a name, so you decide.
              {data?.at_risk_amount ? ` ${inr(data.at_risk_amount)} would be counted twice if confirmed.` : ''}
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="duplicate-refresh">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Re-check'}
        </Button>
      </div>

      {loading && !data ? (
        <div className="py-10 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-slate-400" /></div>
      ) : !data?.pairs?.length ? (
        <p className="py-8 text-center text-sm text-slate-500" data-testid="duplicate-empty">
          Nothing looks duplicated.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100" data-testid="duplicate-list">
          {data.pairs.map((p, i) => (
            <li key={`${p.left.candidate_name}-${p.right.id}-${i}`} className="px-4 py-3 space-y-2">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px] border-amber-200 bg-amber-50 text-amber-700">
                  {KIND_LABEL[p.kind]} · {Math.round(p.confidence * 100)}% alike
                </Badge>
                <span className="text-xs text-slate-500">{p.reason}</span>
              </div>
              <div className="flex flex-col sm:flex-row gap-2 items-stretch">
                <Side row={p.left} tone="border-sky-200 bg-sky-50/40" />
                <Side row={p.right} tone="border-slate-200 bg-slate-50/60" />
              </div>
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" disabled={!!busy}
                        onClick={() => resolve(p, 'different_people')}
                        data-testid={`dup-different-${i}`}>
                  <Users className="w-3 h-3 mr-1" /> Different people
                </Button>
                {p.kind === 'cross_system' ? (
                  <Button size="sm" variant="outline" disabled={!!busy}
                          onClick={() => resolve(p, 'same_hire')} data-testid={`dup-merge-${i}`}>
                    <Link2 className="w-3 h-3 mr-1" /> Same hire — merge
                  </Button>
                ) : (
                  <Button size="sm" variant="outline" disabled={!!busy}
                          className="text-rose-700 border-rose-200 hover:bg-rose-50"
                          onClick={() => resolve(p, 'void_duplicate')} data-testid={`dup-void-${i}`}>
                    <Trash2 className="w-3 h-3 mr-1" /> Entered twice — void the copy
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
