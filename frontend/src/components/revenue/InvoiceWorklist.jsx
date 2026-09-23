/**
 * Invoices & Payments — the Accounts worklist. Everything that owes an
 * invoice, owes a payment, or is already collected, drawn from the branch
 * tracker, the pipeline and the bills raised in the platform.
 */
import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Tabs, TabsList, TabsTrigger } from '../ui/tabs';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';
import { Loader2, Download, RotateCcw, Receipt, IndianRupee } from 'lucide-react';
import { toast } from 'sonner';
import api, { billsAPI } from '../../lib/api';
import { inr, compactINR, downloadCSV, DataTable } from './RevenueTables';
import { Checkbox } from '../ui/checkbox';
import { ConsolidatedInvoiceDialog } from './ConsolidatedInvoiceDialog';

const TABS = [
  ['to_raise', 'Invoice to be raised'],
  ['pending', 'Payment pending'],
  ['received', 'Payment received'],
  ['written_off', 'Backout / Credit note'],
  ['all', 'Everything'],
];

const KIND = {
  tracker: ['Tracker', 'bg-slate-100 text-slate-600 border-slate-200'],
  pipeline: ['Pipeline', 'bg-sky-50 text-sky-700 border-sky-200'],
  bill: ['Platform invoice', 'bg-[#7CB342]/10 text-[#33691E] border-[#7CB342]/30'],
};

const today = () => new Date().toISOString().slice(0, 10);

export function InvoiceWorklist() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [state, setState] = useState('to_raise');
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [acting, setActing] = useState(null);   // row being edited
  const [form, setForm] = useState({ invoice_no: '', payment_date: today(), mode: 'invoice' });
  const [saving, setSaving] = useState(false);
  const [picked, setPicked] = useState({});        // key -> row, for one-invoice-many-candidates
  const [billing, setBilling] = useState(null);

  useEffect(() => {
    const t = setTimeout(() => setQ(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await billsAPI.worklist({
        ...(state !== 'all' ? { state } : {}),
        ...(q ? { q } : {}),
      });
      setData(res);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not load the worklist');
    } finally {
      setLoading(false);
    }
  }, [state, q]);

  useEffect(() => { load(); }, [load]);

  const open = (row, mode) => {
    setForm({ invoice_no: row.reference || '', payment_date: today(), mode });
    setActing(row);
  };

  const submit = async () => {
    setSaving(true);
    try {
      if (acting.kind === 'bill') {
        await billsAPI.markPaid(acting.bill_id, { paid_on: form.payment_date });
      } else if (form.mode === 'invoice') {
        if (!form.invoice_no.trim()) throw new Error('Enter the invoice number');
        await api.patch(`/branch-revenue/placements/${acting.placement_id}`, {
          invoice_no: form.invoice_no.trim(),
          payment_status: 'PP',
          note: 'Invoice raised',
        });
      } else {
        await api.patch(`/branch-revenue/placements/${acting.placement_id}`, {
          payment_status: 'Payment Received',
          payment_date: form.payment_date,
          ...(form.invoice_no.trim() ? { invoice_no: form.invoice_no.trim() } : {}),
          note: 'Payment received',
        });
      }
      toast.success(form.mode === 'invoice' ? 'Moved to payment pending' : 'Marked as received');
      setActing(null);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || 'Could not save');
    } finally {
      setSaving(false);
    }
  };

  const rows = (data?.items || []).map((r) => ({ ...r, _key: r.key }));
  const chosen = Object.values(picked);
  const anchorClient = chosen[0]?.client_name || null;
  const clients = [...new Set(chosen.map((r) => r.client_name || '—'))];
  const canBillTogether = chosen.length > 1 && clients.length === 1;
  const rowLocked = (row) => {
    // Once one row is picked, only rows of the same client are selectable.
    // An invoice can only bill one client, so this hard-guards against
    // accidentally putting another client's candidate on the wrong invoice.
    if (!anchorClient) return false;
    if (picked[row.key]) return false;
    return (row.client_name || '—') !== anchorClient;
  };
  const toggle = (row) => setPicked((p) => {
    const next = { ...p };
    if (next[row.key]) delete next[row.key];
    else if (rowLocked(row)) return p; // silently ignore, checkbox is also disabled
    else next[row.key] = row;
    return next;
  });
  const states = data?.states || {};

  const cols = [
    ...(state === 'to_raise' ? [{
      key: 'pick',
      label: '',
      render: (r) => {
        const locked = rowLocked(r);
        return (
          <Checkbox
            checked={!!picked[r.key]}
            disabled={locked}
            onCheckedChange={() => toggle(r)}
            aria-label={locked
              ? `Locked — invoice is for ${anchorClient}`
              : `Select ${r.candidate_name}`}
            title={locked ? `Locked to ${anchorClient} — clear the selection to pick another client` : undefined}
            data-testid={`wl-pick-${r.key}`}
          />
        );
      },
    }] : []),
    { key: 'date', label: 'Date' },
    {
      key: 'candidate_name',
      label: 'Candidate',
      render: (r) => <span className="font-medium text-slate-900">{r.candidate_name || '—'}</span>,
    },
    { key: 'client_name', label: 'Client' },
    { key: 'recruiter_name', label: 'Recruiter' },
    { key: 'branch', label: 'Branch', render: (r) => r.branch || '—' },
    { key: 'reference', label: 'Invoice no.', render: (r) => r.reference || <span className="text-slate-400">not raised</span> },
    { key: 'amount', label: 'Amount', align: 'right', render: (r) => inr(r.amount) },
    { key: 'payment_status', label: 'Status', render: (r) => r.payment_status || '—' },
    { key: 'payment_date', label: 'Paid on', render: (r) => r.payment_date || '—' },
    {
      key: 'kind',
      label: 'From',
      render: (r) => {
        const [label, tone] = KIND[r.kind] || KIND.tracker;
        return <Badge variant="outline" className={`text-[10px] ${tone}`}>{label}</Badge>;
      },
    },
    {
      key: 'key',
      label: '',
      align: 'right',
      render: (r) => (
        <div className="flex justify-end gap-2 whitespace-nowrap">
          {r.can_raise_invoice && (
            <Button size="sm" variant="outline" className="h-8" asChild data-testid={`wl-raise-${r.key}`}>
              <a href="/admin/analytics#joinings">Raise invoice</a>
            </Button>
          )}
          {r.can_record_invoice && r.state === 'to_raise' && (
            <Button size="sm" variant="outline" className="h-8" onClick={() => open(r, 'invoice')}
                    data-testid={`wl-record-${r.key}`}>
              <Receipt className="w-3 h-3 mr-1" /> Record invoice
            </Button>
          )}
          {r.can_mark_received && r.state !== 'received' && (
            <Button size="sm" className="h-8 bg-[#7CB342] hover:bg-[#6aa037]"
                    onClick={() => open(r, 'payment')} data-testid={`wl-received-${r.key}`}>
              <IndianRupee className="w-3 h-3 mr-1" /> Mark received
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4" data-testid="invoice-worklist">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {TABS.slice(0, 4).map(([key, label]) => (
          <button key={key} onClick={() => setState(key)}
                  data-testid={`wl-stat-${key}`}
                  className={`text-left rounded-lg border px-4 py-3 transition-colors ${
                    state === key ? 'border-[#7CB342] bg-[#7CB342]/5' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
            <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-900 tabular-nums">
              {states[key]?.count ?? 0}
            </p>
            <p className="text-[11px] text-slate-400">{compactINR(states[key]?.amount)}</p>
          </button>
        ))}
      </div>

      <div className="flex items-end gap-2 flex-wrap">
        <Tabs value={state} onValueChange={setState}>
          <TabsList className="flex-wrap h-auto">
            {TABS.map(([key, label]) => (
              <TabsTrigger key={key} value={key} data-testid={`wl-tab-${key}`}>{label}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="flex-1 min-w-[220px]">
          <Label className="text-xs text-slate-500 mb-1 block">
            Search {search !== q && <span className="text-slate-400">· searching…</span>}
          </Label>
          <Input value={search} onChange={(e) => setSearch(e.target.value)}
                 placeholder="Candidate, client, recruiter, invoice no." data-testid="wl-search" />
        </div>
        <Button variant="outline" size="sm" onClick={load} data-testid="wl-refresh">
          <RotateCcw className="w-3 h-3 mr-1" /> Refresh
        </Button>
        <Button variant="outline" size="sm" data-testid="wl-export"
                onClick={() => downloadCSV(`invoices-${state}.csv`,
                  cols.filter((c) => c.key !== 'key').map((c) => ({ label: c.label, value: (r) => r[c.key] })),
                  rows)}>
          <Download className="w-3 h-3 mr-1" /> Export
        </Button>
      </div>

      {chosen.length > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-[#7CB342]/40 bg-[#7CB342]/5 px-4 py-3"
             data-testid="wl-selection-bar">
          <p className="text-sm text-slate-700">
            <span className="font-medium">{chosen.length} selected</span>
            {' · '}
            <span className="font-medium">{anchorClient || '—'}</span>
            {' · '}
            {inr(chosen.reduce((s, r) => s + (r.amount || 0), 0))}
            <span className="ml-2 text-xs text-slate-500">
              (locked to this client — clear to pick another)
            </span>
          </p>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => setPicked({})} data-testid="wl-clear-selection">
              Clear
            </Button>
            <Button size="sm" disabled={!canBillTogether} onClick={() => setBilling(chosen)}
                    className="bg-[#7CB342] hover:bg-[#6aa037]" data-testid="wl-bill-together">
              <Receipt className="w-3 h-3 mr-1" /> Bill {chosen.length} on one invoice
            </Button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : (
        <>
          <p className="text-xs text-slate-500" data-testid="wl-count">
            {data?.count ?? 0} records · {inr(data?.totals?.amount)}
          </p>
          <DataTable testId="wl-table" cols={cols} rows={rows}
                     initialSort={{ key: 'date', dir: 'desc' }}
                     empty="Nothing in this bucket." />
        </>
      )}

      <ConsolidatedInvoiceDialog rows={billing} onClose={() => setBilling(null)}
                                 onDone={() => { setPicked({}); load(); }} />

      <Dialog open={!!acting} onOpenChange={(o) => !o && setActing(null)}>
        <DialogContent data-testid="wl-dialog">
          <DialogHeader>
            <DialogTitle>
              {form.mode === 'invoice' ? 'Record the invoice' : 'Mark payment received'}
            </DialogTitle>
            <DialogDescription className="text-xs">
              {acting?.candidate_name} · {acting?.client_name || 'client not recorded'} · {inr(acting?.amount)}
              {form.mode === 'invoice' ? ' — this moves the row to Payment pending.' : ''}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {acting?.kind !== 'bill' && (
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">
                  Invoice no.{form.mode === 'payment' ? ' (optional)' : ''}
                </Label>
                <Input value={form.invoice_no} onChange={(e) => setForm({ ...form, invoice_no: e.target.value })}
                       placeholder="VHC/26-27/…" data-testid="wl-invoice-no" />
              </div>
            )}
            {form.mode === 'payment' && (
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Payment date</Label>
                <Input type="date" value={form.payment_date}
                       onChange={(e) => setForm({ ...form, payment_date: e.target.value })}
                       data-testid="wl-payment-date" />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActing(null)}>Cancel</Button>
            <Button onClick={submit} disabled={saving} className="bg-[#7CB342] hover:bg-[#6aa037]"
                    data-testid="wl-submit">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
              {form.mode === 'invoice' ? 'Save invoice no.' : 'Mark received'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
