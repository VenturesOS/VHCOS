/**
 * Resolve a flagged tracker row by hand: put it against the right recruiter,
 * correct the billing amount, move the payment along, or dismiss it as fine.
 * Every save is logged server-side and flows straight into the numbers.
 */
import { useEffect, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../ui/select';
import { Loader2, Check, X } from 'lucide-react';
import { toast } from 'sonner';
import api from '../../lib/api';
import { inr } from './RevenueTables';

const STATUSES = ['Payment Received', 'PP', 'IP', 'Backout', 'Credit Note', 'Other / Review'];
const UNASSIGNED = '__unassigned__';
const today = () => new Date().toISOString().slice(0, 10);

export function ResolveRowDialog({ row, onClose, onSaved }) {
  const [people, setPeople] = useState([]);
  const [form, setForm] = useState({
    recruiter_id: '', revenue: '', payment_status: '', invoice_no: '', payment_date: '', note: '',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!row) return;
    setForm({
      recruiter_id: row.recruiter_id || UNASSIGNED,
      revenue: row.revenue ?? '',
      payment_status: row.payment_status || '',
      invoice_no: row.invoice_no || '',
      payment_date: row.payment_status === 'Payment Received' ? (row.payment_date || today()) : '',
      note: '',
    });
  }, [row]);

  useEffect(() => {
    // Scoped list — an account manager can only credit their own team
    api.get('/branch-revenue/assignable-recruiters')
      .then(({ data }) => setPeople(data.items || []))
      .catch(() => {});
  }, []);

  const save = async (dismissOnly = false) => {
    setSaving(true);
    try {
      const body = dismissOnly ? { dismiss_review: true, note: form.note || 'Checked — no change needed' } : {
        ...(form.recruiter_id && form.recruiter_id !== (row.recruiter_id || UNASSIGNED)
          ? { recruiter_id: form.recruiter_id === UNASSIGNED ? '' : form.recruiter_id } : {}),
        ...(String(form.revenue) !== String(row.revenue ?? '') ? { revenue: Number(form.revenue || 0) } : {}),
        ...(form.payment_status && form.payment_status !== row.payment_status
          ? { payment_status: form.payment_status } : {}),
        ...(form.invoice_no !== (row.invoice_no || '') ? { invoice_no: form.invoice_no } : {}),
        ...(form.payment_date ? { payment_date: form.payment_date } : {}),
        ...(form.note ? { note: form.note } : {}),
      };
      if (!Object.keys(body).length) {
        toast.error('Nothing changed yet');
        setSaving(false);
        return;
      }
      await api.patch(`/branch-revenue/placements/${row.id}`, body);
      toast.success(dismissOnly ? 'Marked as checked' : 'Saved — every total has been updated');
      onSaved?.();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save');
    } finally {
      setSaving(false);
    }
  };

  if (!row) return null;

  return (
    <Dialog open={!!row} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="resolve-row-dialog">
        <DialogHeader>
          <DialogTitle>Resolve — {row.candidate_name || `row ${row.s_no}`}</DialogTitle>
          <DialogDescription className="text-xs">
            {row.branch} · {row.organization || 'client not recorded'} · currently {inr(row.revenue)}
            {' '}({row.payment_status || 'no status'})
          </DialogDescription>
        </DialogHeader>

        <ul className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800 space-y-0.5">
          {(row.reasons || []).map((r) => <li key={r}>• {r}</li>)}
        </ul>

        <div className="space-y-3">
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Credit this placement to</Label>
            <Select value={form.recruiter_id} onValueChange={(v) => setForm({ ...form, recruiter_id: v })}>
              <SelectTrigger data-testid="resolve-recruiter"><SelectValue placeholder="Pick a recruiter" /></SelectTrigger>
              <SelectContent className="max-h-72">
                <SelectItem value={UNASSIGNED}>Ex-employee / Unassigned (stays with the branch)</SelectItem>
                {people.map((u) => (
                  <SelectItem key={u.id} value={u.id}>{u.name} · {u.email}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Billing amount (₹)</Label>
              <Input type="number" value={form.revenue}
                     onChange={(e) => setForm({ ...form, revenue: e.target.value })}
                     data-testid="resolve-amount" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Invoice no.</Label>
              <Input value={form.invoice_no}
                     onChange={(e) => setForm({ ...form, invoice_no: e.target.value })}
                     data-testid="resolve-invoice-no" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Payment status</Label>
              <Select value={form.payment_status}
                      onValueChange={(v) => setForm({
                        ...form, payment_status: v,
                        payment_date: v === 'Payment Received' ? (form.payment_date || today()) : '',
                      })}>
                <SelectTrigger data-testid="resolve-status"><SelectValue placeholder="Pick a status" /></SelectTrigger>
                <SelectContent>
                  {STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {form.payment_status === 'Payment Received' && (
              <div>
                <Label className="text-xs text-slate-500 mb-1 block">Payment date</Label>
                <Input type="date" value={form.payment_date}
                       onChange={(e) => setForm({ ...form, payment_date: e.target.value })}
                       data-testid="resolve-payment-date" />
              </div>
            )}
          </div>
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Note (optional)</Label>
            <Textarea rows={2} value={form.note}
                      onChange={(e) => setForm({ ...form, note: e.target.value })}
                      placeholder="Why this was changed — kept in the audit log"
                      data-testid="resolve-note" />
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => save(true)} disabled={saving}
                  data-testid="resolve-dismiss">
            <X className="w-4 h-4 mr-1" /> Fine as-is
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => save(false)} disabled={saving}
                  className="bg-[#7CB342] hover:bg-[#6aa037]" data-testid="resolve-save">
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Check className="w-4 h-4 mr-1" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
