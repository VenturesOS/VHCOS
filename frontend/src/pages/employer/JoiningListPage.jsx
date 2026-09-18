import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../components/ui/dialog';
import { Loader2, RefreshCw, Receipt, IndianRupee, UserCheck, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';
import { joiningsAPI, targetsAPI } from '../../lib/api';

const fmtINR = (n) => (n || n === 0)
  ? `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
  : '—';

const yearStart = () => `${new Date().getFullYear()}-01-01`;
const today = () => new Date().toISOString().slice(0, 10);

function StatBox({ label, value, hint, icon: Icon, testId }) {
  return (
    <Card data-testid={testId} className="border-slate-200">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
            <p className="text-2xl font-semibold text-slate-900 mt-1">{value}</p>
            {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
          </div>
          {Icon && <Icon className="w-5 h-5 text-[#7CB342]" />}
        </div>
      </CardContent>
    </Card>
  );
}

export default function JoiningListPage() {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: yearStart(), date_to: today() });
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState({});
  const [invoiceFor, setInvoiceFor] = useState(null);
  const [invoiceForm, setInvoiceForm] = useState({ joined_ctc: '', commercial_rate_pct: '', designation: '' });
  const [raising, setRaising] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [j, t] = await Promise.all([
        joiningsAPI.list({ ...filters, limit: 500 }),
        targetsAPI.teamSummary().catch(() => ({ data: null })),
      ]);
      setRows(j.data?.items || []);
      setSummary({ joinings: j.data, targets: t.data });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load joinings');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const saveRow = async (row) => {
    const d = draft[row.application_id] || {};
    setSaving((s) => ({ ...s, [row.application_id]: true }));
    try {
      await joiningsAPI.update(row.application_id, {
        joined_ctc: d.joined_ctc !== undefined && d.joined_ctc !== '' ? Number(d.joined_ctc) : undefined,
        revenue: d.revenue !== undefined && d.revenue !== '' ? Number(d.revenue) : undefined,
      });
      toast.success('Saved');
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save');
    } finally {
      setSaving((s) => ({ ...s, [row.application_id]: false }));
    }
  };

  const openInvoice = (row) => {
    setInvoiceFor(row);
    setInvoiceForm({
      joined_ctc: row.joined_ctc || '',
      commercial_rate_pct: row.commercial_rate_pct || '',
      designation: row.position || '',
    });
  };

  const submitInvoice = async () => {
    if (!invoiceForm.joined_ctc || !invoiceForm.commercial_rate_pct) {
      toast.error('Enter both the joining CTC and the commercial rate');
      return;
    }
    setRaising(true);
    try {
      const { data } = await joiningsAPI.raiseInvoice(invoiceFor.application_id, {
        joined_ctc: Number(invoiceForm.joined_ctc),
        commercial_rate_pct: Number(invoiceForm.commercial_rate_pct),
        designation: invoiceForm.designation || undefined,
      });
      toast.success(`Invoice ${data.bill_number} sent to Accounts`);
      setInvoiceFor(null);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not raise the invoice');
    } finally {
      setRaising(false);
    }
  };

  const teamTotals = summary?.targets || {};

  return (
    <div className="space-y-6" data-testid="joining-list-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Joining List</h1>
          <p className="text-sm text-slate-500">
            Every candidate your team moved to <span className="font-medium">Joined</span>. Fill the joining
            CTC and revenue, then raise the invoice — Accounts receives it pre-filled.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} data-testid="joinings-refresh">
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatBox testId="stat-joinings" label="Joinings in range" value={rows.length}
                 icon={UserCheck} hint={`${summary?.joinings?.pending_revenue_count ?? 0} awaiting revenue`} />
        <StatBox testId="stat-revenue" label="Revenue booked" value={fmtINR(summary?.joinings?.total_revenue)}
                 icon={IndianRupee} hint="From the joinings listed below" />
        <StatBox testId="stat-team-target" label="Team target (year)" value={fmtINR(teamTotals.total_target)}
                 icon={TrendingUp} hint={`${teamTotals.year || new Date().getFullYear()} · Jan–Dec`} />
        <StatBox testId="stat-team-achievement" label="Team achievement"
                 value={`${teamTotals.achievement_pct ?? 0}%`} icon={TrendingUp}
                 hint={`${fmtINR(teamTotals.total_achieved)} achieved`} />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Joinings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">From</Label>
              <Input type="date" value={filters.date_from}
                     onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
                     data-testid="joinings-from" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">To</Label>
              <Input type="date" value={filters.date_to}
                     onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
                     data-testid="joinings-to" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Position contains</Label>
              <Input value={filters.position_q || ''}
                     onChange={(e) => setFilters({ ...filters, position_q: e.target.value })}
                     placeholder="e.g. Manager" data-testid="joinings-position" />
            </div>
          </div>

          {loading ? (
            <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
          ) : rows.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-500" data-testid="joinings-empty">
              No joinings in this window yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="joinings-table">
                <thead>
                  <tr className="border-b text-xs uppercase tracking-wide text-slate-500">
                    <th className="text-left px-3 py-2">DOJ</th>
                    <th className="text-left px-3 py-2">Candidate</th>
                    <th className="text-left px-3 py-2">Recruiter</th>
                    <th className="text-left px-3 py-2">Client</th>
                    <th className="text-left px-3 py-2">Position</th>
                    <th className="text-left px-3 py-2">Joining CTC</th>
                    <th className="text-left px-3 py-2">Revenue</th>
                    <th className="text-left px-3 py-2">Invoice</th>
                    <th className="text-right px-3 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const d = draft[row.application_id] || {};
                    return (
                      <tr key={row.application_id} className="border-b last:border-0 hover:bg-slate-50"
                          data-testid={`joining-row-${row.application_id}`}>
                        <td className="px-3 py-2 whitespace-nowrap">{row.join_date || '—'}</td>
                        <td className="px-3 py-2">{row.candidate_name}</td>
                        <td className="px-3 py-2 text-slate-500">{row.recruiter_name || '—'}</td>
                        <td className="px-3 py-2">{row.client_name || '—'}</td>
                        <td className="px-3 py-2">{row.position || '—'}</td>
                        <td className="px-3 py-2">
                          <Input className="h-8 w-28" type="number" placeholder="CTC"
                                 value={d.joined_ctc ?? (row.joined_ctc || '')}
                                 onChange={(e) => setDraft({ ...draft, [row.application_id]: { ...d, joined_ctc: e.target.value } })}
                                 data-testid={`joining-ctc-${row.application_id}`} />
                        </td>
                        <td className="px-3 py-2">
                          <Input className="h-8 w-28" type="number" placeholder="Revenue"
                                 value={d.revenue ?? (row.revenue ?? '')}
                                 onChange={(e) => setDraft({ ...draft, [row.application_id]: { ...d, revenue: e.target.value } })}
                                 data-testid={`joining-revenue-${row.application_id}`} />
                        </td>
                        <td className="px-3 py-2">
                          {row.bill_number
                            ? <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100">{row.bill_number}</Badge>
                            : <span className="text-xs text-slate-400">Not raised</span>}
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          <Button size="sm" variant="outline" className="h-8 mr-2"
                                  disabled={saving[row.application_id]}
                                  onClick={() => saveRow(row)}
                                  data-testid={`joining-save-${row.application_id}`}>
                            {saving[row.application_id] ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Save'}
                          </Button>
                          <Button size="sm" className="h-8 bg-[#7CB342] hover:bg-[#6aa037]"
                                  disabled={!!row.bill_number}
                                  onClick={() => openInvoice(row)}
                                  data-testid={`joining-raise-invoice-${row.application_id}`}>
                            <Receipt className="w-3 h-3 mr-1" /> Raise Invoice
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!invoiceFor} onOpenChange={(o) => !o && setInvoiceFor(null)}>
        <DialogContent data-testid="raise-invoice-dialog">
          <DialogHeader>
            <DialogTitle>Raise invoice — {invoiceFor?.candidate_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-xs text-slate-500">
              {invoiceFor?.client_name} · joined {invoiceFor?.join_date}. Both figures are entered manually.
              The invoice line amount <span className="font-medium">replaces</span> the revenue booked for{' '}
              {invoiceFor?.recruiter_name || 'the recruiter'}
              {invoiceFor?.revenue ? ` (currently ${fmtINR(invoiceFor.revenue)})` : ''}.
            </p>
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Designation on invoice</Label>
              <Input value={invoiceForm.designation}
                     onChange={(e) => setInvoiceForm({ ...invoiceForm, designation: e.target.value })}
                     data-testid="invoice-designation" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Annual CTC (₹)</Label>
                <Input type="number" value={invoiceForm.joined_ctc}
                       onChange={(e) => setInvoiceForm({ ...invoiceForm, joined_ctc: e.target.value })}
                       data-testid="invoice-ctc" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Commercial rate (%)</Label>
                <Input type="number" step="0.01" value={invoiceForm.commercial_rate_pct}
                       onChange={(e) => setInvoiceForm({ ...invoiceForm, commercial_rate_pct: e.target.value })}
                       data-testid="invoice-rate" />
              </div>
            </div>
            {invoiceForm.joined_ctc && invoiceForm.commercial_rate_pct && (
              <p className="text-sm text-slate-700" data-testid="invoice-preview-amount">
                Invoice amount:&nbsp;
                <span className="font-semibold">
                  {fmtINR(Number(invoiceForm.joined_ctc) * Number(invoiceForm.commercial_rate_pct) / 100)}
                </span>
                <span className="text-slate-400"> (before GST)</span>
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInvoiceFor(null)}>Cancel</Button>
            <Button onClick={submitInvoice} disabled={raising}
                    className="bg-[#7CB342] hover:bg-[#6aa037]" data-testid="invoice-submit">
              {raising ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Receipt className="w-4 h-4 mr-1" />}
              Send to Accounts
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
