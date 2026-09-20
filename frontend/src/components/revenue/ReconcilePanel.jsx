/**
 * Reconciliation panel — re-derives every revenue figure from a different
 * direction and shows whether they agree. Lives in the Review tab so the
 * client can check the books themselves instead of taking our word for it.
 */
import { useState } from 'react';
import { Button } from '../ui/button';
import { Loader2, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { branchRevenueAPI } from '../../lib/api';
import { inr } from './RevenueTables';

export function ReconcilePanel({ year }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const res = await branchRevenueAPI.reconcile({ year });
      setData(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not run the reconciliation');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white" data-testid="reconcile-panel">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-slate-100">
        <div className="flex items-start gap-2">
          <ShieldCheck className="w-4 h-4 mt-0.5 text-[#7CB342]" />
          <div>
            <p className="text-sm font-medium text-slate-900">Number check ({year})</p>
            <p className="text-xs text-slate-500">
              Adds the same revenue up nine different ways — by branch, by recruiter, by team, by month,
              and against the Joining List — and flags anything that disagrees or is counted twice.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={run} disabled={loading} data-testid="reconcile-run">
          {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
          {data ? 'Run again' : 'Run check'}
        </Button>
      </div>

      {data && (
        <div className="px-4 py-3 space-y-3">
          <div className="flex items-center gap-2 text-sm" data-testid="reconcile-verdict">
            {data.ok
              ? <><CheckCircle2 className="w-4 h-4 text-[#7CB342]" /><span className="font-medium text-[#33691E]">All {data.checks.length} checks agree</span></>
              : <><XCircle className="w-4 h-4 text-rose-600" /><span className="font-medium text-rose-700">{data.checks.filter((c) => !c.ok).length} of {data.checks.length} checks disagree</span></>}
            <span className="text-slate-400">·</span>
            <span className="text-slate-600">
              tracker {inr(data.totals.tracker_active)} + platform {inr(data.totals.platform_revenue)} ={' '}
              <span className="font-medium">{inr(data.totals.company_achieved)}</span> across {data.totals.placements} placements
            </span>
          </div>
          <ul className="divide-y divide-slate-100" data-testid="reconcile-checks">
            {data.checks.map((c) => (
              <li key={c.check} className="flex items-start justify-between gap-4 py-2">
                <div className="flex items-start gap-2">
                  {c.ok
                    ? <CheckCircle2 className="w-4 h-4 mt-0.5 text-[#7CB342] shrink-0" />
                    : <XCircle className="w-4 h-4 mt-0.5 text-rose-600 shrink-0" />}
                  <div>
                    <p className="text-sm text-slate-800">{c.check}</p>
                    {c.note && <p className="text-xs text-slate-500">{c.note}</p>}
                  </div>
                </div>
                <p className={`text-xs tabular-nums shrink-0 ${c.ok ? 'text-slate-400' : 'text-rose-700 font-medium'}`}>
                  {c.ok ? 'matches' : `off by ${inr(c.difference)}`}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
