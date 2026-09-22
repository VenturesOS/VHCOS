/**
 * Bill several candidates of one client on a single invoice.
 *
 * Six people joining the same client in a month meant six invoices and six
 * payments to chase. Here they go on one document, and marking it paid clears
 * all six at once.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../ui/select';
import { Loader2, Receipt } from 'lucide-react';
import { toast } from 'sonner';
import { billsAPI } from '../../lib/api';
import { inr } from './RevenueTables';

const SENDERS = [
  ['Ventures HRD Pvt Ltd', 'Ventures HRD Pvt Ltd · 07AACCV6268J1ZW'],
  ['VENTURE HRD CENTER', 'VENTURE HRD CENTER · 07AAMPY9883D2ZT'],
];

export function ConsolidatedInvoiceDialog({ rows, onClose, onDone }) {
  const [lines, setLines] = useState([]);
  const [sender, setSender] = useState(SENDERS[0][0]);
  const [bankId, setBankId] = useState('');
  const [banks, setBanks] = useState([]);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLines((rows || []).map((r) => ({
      key: r.key,
      application_id: r.application_id || '',
      placement_id: r.placement_id || '',
      candidate_name: r.candidate_name,
      designation: r.designation || '',
      // A tracker row already carries its billing amount; a pipeline joining
      // needs the CTC and the rate typed in, same as the single-invoice flow.
      annual_ctc: '',
      commercial_rate_pct: r.application_id ? '8.33' : '',
      line_amount: r.amount || '',
      fromTracker: !r.application_id,
    })));
  }, [rows]);

  useEffect(() => {
    billsAPI.listBankAccounts().then(({ data }) => {
      const list = data.items || data || [];
      setBanks(list);
      const preferred = list.find((b) => b.is_default) || list[0];
      if (preferred) setBankId(preferred.id);
    }).catch(() => {});
  }, []);

  const set = (key, field, value) => setLines((ls) => ls.map(
    (l) => (l.key === key ? { ...l, [field]: value } : l)));

  const amountOf = (l) => (l.fromTracker
    ? Number(l.line_amount || 0)
    : Number(l.annual_ctc || 0) * Number(l.commercial_rate_pct || 0) / 100);

  const subtotal = useMemo(() => lines.reduce((s, l) => s + amountOf(l), 0), [lines]);
  const client = rows?.[0]?.client_name || '';

  const submit = async () => {
    const missing = lines.filter((l) => !amountOf(l));
    if (missing.length) {
      toast.error(`Enter the CTC and rate for ${missing.map((m) => m.candidate_name).join(', ')}`);
      return;
    }
    setSaving(true);
    try {
      const { data } = await billsAPI.consolidatedInvoice({
        sender_variant: sender,
        bank_account_id: bankId || undefined,
        notes: notes || undefined,
        items: lines.map((l) => ({
          ...(l.application_id ? { application_id: l.application_id } : { placement_id: l.placement_id }),
          designation: l.designation || undefined,
          annual_ctc: Number(l.annual_ctc || 0),
          commercial_rate_pct: Number(l.commercial_rate_pct || 0),
          ...(l.fromTracker ? { line_amount: Number(l.line_amount || 0) } : {}),
        })),
      });
      toast.success(data.message);
      onDone?.();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not raise the invoice');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={!!rows?.length} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl" data-testid="consolidated-invoice-dialog">
        <DialogHeader>
          <DialogTitle>One invoice · {lines.length} candidates</DialogTitle>
          <DialogDescription className="text-xs">
            Billing <span className="font-medium">{client}</span>. When this invoice is paid, all{' '}
            {lines.length} candidates are marked received together.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-72 overflow-y-auto rounded-md border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 sticky top-0">
              <tr className="text-[11px] uppercase tracking-wide text-slate-500">
                <th className="text-left px-3 py-2">Candidate</th>
                <th className="text-left px-3 py-2">Designation</th>
                <th className="text-right px-3 py-2">Annual CTC</th>
                <th className="text-right px-3 py-2">Rate %</th>
                <th className="text-right px-3 py-2">Amount</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.key} className="border-t border-slate-100" data-testid={`ci-line-${l.key}`}>
                  <td className="px-3 py-2 font-medium text-slate-900">{l.candidate_name}</td>
                  <td className="px-3 py-2">
                    <Input className="h-8" value={l.designation}
                           onChange={(e) => set(l.key, 'designation', e.target.value)}
                           placeholder="Designation" data-testid={`ci-designation-${l.key}`} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    {l.fromTracker ? <span className="text-slate-400">—</span> : (
                      <Input className="h-8 w-28 text-right" type="number" value={l.annual_ctc}
                             onChange={(e) => set(l.key, 'annual_ctc', e.target.value)}
                             data-testid={`ci-ctc-${l.key}`} />
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {l.fromTracker ? <span className="text-slate-400">—</span> : (
                      <Input className="h-8 w-20 text-right" type="number" step="0.01"
                             value={l.commercial_rate_pct}
                             onChange={(e) => set(l.key, 'commercial_rate_pct', e.target.value)}
                             data-testid={`ci-rate-${l.key}`} />
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums" data-testid={`ci-amount-${l.key}`}>
                    {l.fromTracker ? (
                      <Input className="h-8 w-28 text-right" type="number" value={l.line_amount}
                             onChange={(e) => set(l.key, 'line_amount', e.target.value)} />
                    ) : inr(amountOf(l))}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-slate-50">
              <tr>
                <td colSpan={4} className="px-3 py-2 text-right font-medium">Subtotal (before GST)</td>
                <td className="px-3 py-2 text-right font-semibold tabular-nums" data-testid="ci-subtotal">
                  {inr(subtotal)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Raise from</Label>
            <Select value={sender} onValueChange={setSender}>
              <SelectTrigger data-testid="ci-sender"><SelectValue /></SelectTrigger>
              <SelectContent>
                {SENDERS.map(([value, label]) => (
                  <SelectItem key={value} value={value}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Receive into</Label>
            <Select value={bankId} onValueChange={setBankId}>
              <SelectTrigger data-testid="ci-bank"><SelectValue placeholder="Bank account" /></SelectTrigger>
              <SelectContent>
                {banks.map((b) => <SelectItem key={b.id} value={b.id}>{b.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div>
          <Label className="text-xs text-slate-500 mb-1 block">Notes on the invoice (optional)</Label>
          <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)}
                    data-testid="ci-notes" />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={saving} className="bg-[#7CB342] hover:bg-[#6aa037]"
                  data-testid="ci-submit">
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Receipt className="w-4 h-4 mr-1" />}
            Raise one invoice · {inr(subtotal)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
