import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../components/ui/dialog';
import { Loader2, RefreshCw, Receipt, Download } from 'lucide-react';
import { toast } from 'sonner';
import { joiningsAPI, targetsAPI } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { StatusChip, inr, compactINR, downloadCSV } from '../../components/revenue/RevenueTables';
import { ResolveRowDialog } from '../../components/revenue/ResolveRowDialog';

const yearStart = () => `${new Date().getFullYear()}-01-01`;
const today = () => new Date().toISOString().slice(0, 10);

const STATUSES = ['Payment Received', 'PP', 'IP', 'Backout', 'Credit Note', 'Other / Review', 'Revenue pending'];

const SOURCE_LABEL = {
  both: ['In pipeline + tracker', 'bg-[#7CB342]/10 text-[#33691E] border-[#7CB342]/30'],
  tracker: ['Tracker only', 'bg-slate-100 text-slate-600 border-slate-200'],
  pipeline: ['Pipeline only', 'bg-sky-50 text-sky-700 border-sky-200'],
};

function StatBox({ label, value, hint, testId }) {
  return (
    <div data-testid={testId} className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-900 tabular-nums">{value}</p>
      {hint && <p className="text-[11px] text-slate-400 mt-0.5">{hint}</p>}
    </div>
  );
}

export default function JoiningListPage() {
  const { user } = useAuth();
  const readOnly = user?.role === 'recruiter';
  const [data, setData] = useState(null);
  const [targets, setTargets] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: yearStart(), date_to: today() });
  const [status, setStatus] = useState('all');
  const [source, setSource] = useState('all');
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState({});
  const [invoiceFor, setInvoiceFor] = useState(null);
  const [updateRow, setUpdateRow] = useState(null);
  const [invoiceForm, setInvoiceForm] = useState({ joined_ctc: '', billing_amount: '', designation: '' });
  const [raising, setRaising] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setQ(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [j, t] = await Promise.all([
        joiningsAPI.list({
          ...filters,
          ...(status !== 'all' ? { payment_status: status } : {}),
          ...(source !== 'all' ? { source } : {}),
          ...(q ? { q } : {}),
          limit: 1000,
        }),
        readOnly ? Promise.resolve({ data: null }) : targetsAPI.teamSummary().catch(() => ({ data: null })),
      ]);
      setData(j.data);
      setTargets(t.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load joinings');
    } finally {
      setLoading(false);
    }
  }, [filters, status, source, q, readOnly]);

  useEffect(() => { load(); }, [load]);

  const saveRow = async (row, { silent = false, skipReload = false } = {}) => {
    const d = draft[row.key] || {};
    setSaving((s) => ({ ...s, [row.key]: true }));
    try {
      await joiningsAPI.update(row.application_id, {
        joined_ctc: d.joined_ctc !== undefined && d.joined_ctc !== '' ? Number(d.joined_ctc) : undefined,
        revenue: d.revenue !== undefined && d.revenue !== '' ? Number(d.revenue) : undefined,
        join_date: d.join_date || undefined,
      });
      if (!silent) toast.success('Saved');
      setDraft((prev) => { const n = { ...prev }; delete n[row.key]; return n; });
      if (!skipReload) await load();
    } catch (e) {
      toast.error(`${row.candidate_name || 'Row'}: ${e?.response?.data?.detail || 'could not save'}`);
    } finally {
      setSaving((s) => ({ ...s, [row.key]: false }));
    }
  };

  const raise = async (row, ctc, amount, designation) => {
    setRaising(true);
    try {
      const { data: res } = await joiningsAPI.raiseInvoice(row.application_id, {
        joined_ctc: Number(ctc),
        billing_amount: Number(amount),
        designation: designation || row.position || undefined,
      });
      toast.success(`Invoice ${res.bill_number} sent to Accounts`);
      setInvoiceFor(null);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not raise the invoice');
    } finally {
      setRaising(false);
    }
  };

  // Step 7 — if both figures are already on the row, the invoice goes straight
  // to Accounts; only a missing figure opens the box.
  const startInvoice = (row) => {
    const d = draft[row.key] || {};
    const ctc = d.joined_ctc ?? row.joined_ctc;
    const amount = d.revenue ?? row.revenue;
    if (Number(ctc) > 0 && Number(amount) > 0) {
      raise(row, ctc, amount, row.position);
      return;
    }
    setInvoiceFor(row);
    setInvoiceForm({
      joined_ctc: ctc || '',
      billing_amount: amount || '',
      designation: row.position || '',
    });
  };

  const submitInvoice = () => {
    if (!Number(invoiceForm.joined_ctc) || !Number(invoiceForm.billing_amount)) {
      toast.error('Enter both the joining CTC and the billing amount');
      return;
    }
    raise(invoiceFor, invoiceForm.joined_ctc, invoiceForm.billing_amount, invoiceForm.designation);
  };

  const rows = data?.items || [];
  const totals = data?.totals || {};
  const sources = data?.sources || {};

  // Any row the user has actually changed — drives the sticky save bar.
  const dirtyRows = rows.filter((r) => {
    const d = draft[r.key];
    if (!d) return false;
    return ['join_date', 'joined_ctc', 'revenue'].some(
      (f) => d[f] !== undefined && String(d[f]) !== String(r[f] ?? ''),
    );
  });
  const savingAny = Object.values(saving).some(Boolean);

  const saveAll = async () => {
    for (const row of dirtyRows) {
      // eslint-disable-next-line no-await-in-loop
      await saveRow(row, { silent: true, skipReload: true });
    }
    toast.success(`Saved ${dirtyRows.length} joining${dirtyRows.length > 1 ? 's' : ''}`);
    await load();
  };

  const exportCSV = () => downloadCSV(
    `joinings-${filters.date_from}-to-${filters.date_to}.csv`,
    [
      ['DOJ', 'join_date'], ['Candidate', 'candidate_name'], ['Recruiter', 'recruiter_name'],
      ['Client', 'client_name'], ['Position', 'position'], ['Branch', 'branch'],
      ['Joining CTC', 'joined_ctc'], ['Billing Amount', 'revenue'],
      ['Payment Status', 'payment_status'], ['Invoice', 'bill_number'], ['Source', 'source'],
    ].map(([label, key]) => ({ label, value: (r) => r[key] })),
    rows,
  );

  return (
    <div className="space-y-6" data-testid="joining-list-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Joining List</h1>
          <p className="text-sm text-slate-500 max-w-3xl">
            {readOnly
              ? 'Every candidate of yours who has joined the client.'
              : 'Every joining for your team. Fill in the joining CTC and the billing amount, then raise the invoice — it lands in Accounts’ Bills & Invoices tab.'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={exportCSV} data-testid="joinings-export">
            <Download className="w-4 h-4 mr-1" /> Export
          </Button>
          <Button variant="outline" size="sm" onClick={load} data-testid="joinings-refresh">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {readOnly ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">My joinings ({data?.count ?? 0})</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
            ) : rows.length === 0 ? (
              <p className="py-10 text-center text-sm text-slate-500" data-testid="joinings-empty">
                No joinings yet.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-sm" data-testid="joinings-table">
                  <thead className="bg-slate-50">
                    <tr className="text-[11px] uppercase tracking-wide text-slate-500">
                      <th className="text-left px-3 py-2">DOJ</th>
                      <th className="text-left px-3 py-2">Candidate</th>
                      <th className="text-left px-3 py-2">Client</th>
                      <th className="text-left px-3 py-2">Client Position</th>
                      <th className="text-right px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const d = draft[row.key] || {};
                      return (
                      <tr key={row.key} className="border-t border-slate-100 hover:bg-slate-50/70"
                          data-testid={`joining-row-${row.key}`}>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {row.editable ? (
                            <Input className="h-8 w-36" type="date"
                                   value={d.join_date ?? (row.join_date || '')}
                                   onChange={(e) => setDraft({ ...draft, [row.key]: { ...d, join_date: e.target.value } })}
                                   data-testid={`joining-doj-${row.key}`} />
                          ) : (row.join_date || '—')}
                        </td>
                        <td className="px-3 py-2 font-medium text-slate-900">{row.candidate_name || '—'}</td>
                        <td className="px-3 py-2">{row.client_name || '—'}</td>
                        <td className="px-3 py-2">{row.position || '—'}</td>
                        <td className="px-3 py-2 text-right">
                          {row.editable && (
                            <Button size="sm" variant="outline" className="h-8"
                                    disabled={saving[row.key] || !d.join_date || d.join_date === row.join_date}
                                    onClick={() => saveRow(row)} data-testid={`joining-save-${row.key}`}>
                              {saving[row.key] ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Save DOJ'}
                            </Button>
                          )}
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
      ) : (
      <>
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        <StatBox testId="stat-joinings" label="Joinings" value={data?.count ?? 0}
                 hint={`${sources.both ?? 0} in both · ${sources.tracker_only ?? 0} tracker · ${sources.pipeline_only ?? 0} pipeline`} />
        <StatBox testId="stat-gross" label="Gross Billing" value={compactINR(totals.gross)} />
        <StatBox testId="stat-received" label="Payment Received" value={compactINR(totals.received)} />
        <StatBox testId="stat-pending" label="Pending (PP + IP)" value={compactINR(totals.pending)} />
        <StatBox testId="stat-lost" label="Backout / Credit Note" value={compactINR(totals.lost)} />
        <StatBox testId="stat-team-achievement" label="Team achievement"
                 value={`${targets?.achievement_pct ?? 0}%`}
                 hint={targets ? `${compactINR(targets.total_achieved)} of ${compactINR(targets.total_target)}` : null} />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            Joinings {data?.revenue_pending_count ? (
              <span className="ml-2 text-xs font-normal text-amber-600">
                {data.revenue_pending_count} awaiting revenue
              </span>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
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
              <Label className="text-xs text-slate-500 mb-1 block">Payment status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger data-testid="joinings-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Source</Label>
              <Select value={source} onValueChange={setSource}>
                <SelectTrigger data-testid="joinings-source"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tracker + pipeline</SelectItem>
                  <SelectItem value="both">In both</SelectItem>
                  <SelectItem value="tracker">Tracker only</SelectItem>
                  <SelectItem value="pipeline">Pipeline only</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">
                Search {search !== q && <span className="text-slate-400">· searching…</span>}
              </Label>
              <Input value={search} onChange={(e) => setSearch(e.target.value)}
                     placeholder="Candidate, client, position" data-testid="joinings-search" />
            </div>
          </div>

          {loading ? (
            <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
          ) : rows.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-500" data-testid="joinings-empty">
              No joinings match these filters.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-sm" data-testid="joinings-table">
                <thead className="bg-slate-50">
                  <tr className="text-[11px] uppercase tracking-wide text-slate-500">
                    <th className="text-left px-3 py-2">DOJ</th>
                    <th className="text-left px-3 py-2">Candidate</th>
                    <th className="text-left px-3 py-2">Recruiter</th>
                    <th className="text-left px-3 py-2">Client</th>
                    <th className="text-left px-3 py-2">Position</th>
                    <th className="text-right px-3 py-2">Joining CTC</th>
                    <th className="text-right px-3 py-2">Billing Amount</th>
                    <th className="text-left px-3 py-2">Payment</th>
                    <th className="text-left px-3 py-2">Invoice</th>
                    <th className="text-left px-3 py-2">Source</th>
                    <th className="text-right px-3 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const d = draft[row.key] || {};
                    const [srcLabel, srcTone] = SOURCE_LABEL[row.source] || SOURCE_LABEL.tracker;
                    return (
                      <tr key={row.key} className="border-t border-slate-100 hover:bg-slate-50/70"
                          data-testid={`joining-row-${row.key}`}>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {row.editable ? (
                            <Input className="h-8 w-36" type="date"
                                   value={d.join_date ?? (row.join_date || '')}
                                   onChange={(e) => setDraft({ ...draft, [row.key]: { ...d, join_date: e.target.value } })}
                                   data-testid={`joining-doj-${row.key}`} />
                          ) : (row.join_date || '—')}
                        </td>
                        <td className="px-3 py-2 font-medium text-slate-900">{row.candidate_name || '—'}</td>
                        <td className="px-3 py-2 text-slate-500">{row.recruiter_name || '—'}</td>
                        <td className="px-3 py-2">{row.client_name || '—'}</td>
                        <td className="px-3 py-2">{row.position || '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {row.editable ? (
                            <Input className="h-8 w-28" type="number" placeholder="CTC"
                                   value={d.joined_ctc ?? (row.joined_ctc || '')}
                                   onChange={(e) => setDraft({ ...draft, [row.key]: { ...d, joined_ctc: e.target.value } })}
                                   data-testid={`joining-ctc-${row.key}`} />
                          ) : inr(row.joined_ctc)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {row.editable ? (
                            <Input className="h-8 w-28" type="number" placeholder="Revenue"
                                   value={d.revenue ?? (row.revenue || '')}
                                   onChange={(e) => setDraft({ ...draft, [row.key]: { ...d, revenue: e.target.value } })}
                                   data-testid={`joining-revenue-${row.key}`} />
                          ) : inr(row.revenue)}
                        </td>
                        <td className="px-3 py-2"><StatusChip status={row.payment_status} /></td>
                        <td className="px-3 py-2">
                          {row.bill_number
                            ? <span className="text-xs text-slate-600">{row.bill_number}</span>
                            : <span className="text-xs text-slate-400">Not raised</span>}
                        </td>
                        <td className="px-3 py-2">
                          <Badge variant="outline" className={`text-[10px] ${srcTone}`}>{srcLabel}</Badge>
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          {row.editable ? (
                            <>
                              <Button size="sm" variant="outline" className="h-8 mr-2"
                                      disabled={saving[row.key]} onClick={() => saveRow(row)}
                                      data-testid={`joining-save-${row.key}`}>
                                {saving[row.key] ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Save'}
                              </Button>
                              <Button size="sm" className="h-8 bg-[#7CB342] hover:bg-[#6aa037]"
                                      disabled={!!row.bill_number || raising} onClick={() => startInvoice(row)}
                                      data-testid={`joining-raise-invoice-${row.key}`}>
                                <Receipt className="w-3 h-3 mr-1" /> Raise Invoice
                              </Button>
                            </>
                          ) : row.placement_id ? (
                            <Button size="sm" variant="outline" className="h-8"
                                    onClick={() => setUpdateRow({
                                      id: row.placement_id,
                                      candidate_name: row.candidate_name,
                                      branch: row.branch,
                                      organization: row.client_name,
                                      revenue: row.revenue,
                                      payment_status: row.payment_status,
                                      invoice_no: row.bill_number,
                                      recruiter_id: row.recruiter_id,
                                      reasons: ['Recorded in the branch tracker — update the payment as it moves'],
                                    })}
                                    data-testid={`joining-update-${row.key}`}>
                              Update
                            </Button>
                          ) : (
                            <span className="text-xs text-slate-400">from tracker</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {data?.truncated && (
            <p className="text-xs text-slate-500">Showing the first {rows.length} of {data.count} — narrow the dates to see the rest.</p>
          )}
        </CardContent>
      </Card>
      </>
      )}

      {dirtyRows.length > 0 && (
        <div className="sticky bottom-4 z-30 flex justify-center" data-testid="joinings-save-bar">
          <div className="flex items-center gap-4 rounded-full border border-amber-300 bg-amber-50 px-5 py-2.5 shadow-lg">
            <span className="text-sm text-amber-900">
              {dirtyRows.length} unsaved change{dirtyRows.length > 1 ? 's' : ''}
            </span>
            <Button size="sm" variant="ghost" className="h-8 text-amber-900 hover:bg-amber-100"
                    onClick={() => setDraft({})} data-testid="joinings-discard-all">
              Discard
            </Button>
            <Button size="sm" className="h-8 bg-[#7CB342] hover:bg-[#6aa037]"
                    disabled={savingAny} onClick={saveAll} data-testid="joinings-save-all">
              {savingAny ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
              Save changes
            </Button>
          </div>
        </div>
      )}

      <ResolveRowDialog row={updateRow} onClose={() => setUpdateRow(null)} onSaved={load} />

      <Dialog open={!!invoiceFor} onOpenChange={(o) => !o && setInvoiceFor(null)}>
        <DialogContent data-testid="raise-invoice-dialog">
          <DialogHeader>
            <DialogTitle>Raise invoice — {invoiceFor?.candidate_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-xs text-slate-500">
              {invoiceFor?.client_name} · joined {invoiceFor?.join_date}. The joining CTC or the
              billing amount is missing — fill them in and the invoice goes to Accounts.
            </p>
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Designation on invoice</Label>
              <Input value={invoiceForm.designation}
                     onChange={(e) => setInvoiceForm({ ...invoiceForm, designation: e.target.value })}
                     data-testid="invoice-designation" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Joining CTC (₹)</Label>
                <Input type="number" value={invoiceForm.joined_ctc}
                       onChange={(e) => setInvoiceForm({ ...invoiceForm, joined_ctc: e.target.value })}
                       data-testid="invoice-ctc" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Billing amount (₹)</Label>
                <Input type="number" value={invoiceForm.billing_amount}
                       onChange={(e) => setInvoiceForm({ ...invoiceForm, billing_amount: e.target.value })}
                       data-testid="invoice-amount" />
              </div>
            </div>
            {Number(invoiceForm.billing_amount) > 0 && (
              <p className="text-sm text-slate-700" data-testid="invoice-preview-amount">
                Invoice amount:&nbsp;
                <span className="font-semibold">{inr(Number(invoiceForm.billing_amount))}</span>
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
