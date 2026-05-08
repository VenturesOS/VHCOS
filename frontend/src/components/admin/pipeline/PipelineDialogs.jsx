import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../../ui/dialog';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { AlertCircle, Award, UserCheck, Lock } from 'lucide-react';

export function DeleteDialog({ open, onClose, app, onConfirm }) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-red-600 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" /> Remove from Pipeline
          </DialogTitle>
          <DialogDescription>
            Are you sure you want to remove <strong>{app?.candidate_name}</strong> from the pipeline?
          </DialogDescription>
        </DialogHeader>
        <div className="py-4 space-y-3">
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
            <p className="text-sm text-amber-700">
              <strong>Note:</strong> This will only remove the candidate from this job&apos;s pipeline.
            </p>
            <ul className="text-sm text-amber-600 mt-2 space-y-1 list-disc list-inside">
              <li>The candidate will NOT be deleted from the data bank</li>
              <li>Historical data will be preserved for audit</li>
              <li>This action can be undone by re-adding the candidate</li>
            </ul>
          </div>
          {app && (
            <div className="text-sm text-slate-600">
              <p><strong>Job:</strong> {app.job_title}</p>
              <p><strong>Current Stage:</strong> {app.stage}</p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)}>Cancel</Button>
          <Button variant="destructive" onClick={onConfirm} data-testid="confirm-delete-application-btn">Remove from Pipeline</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function OfferDialog({ open, onClose, app, form, setForm, onConfirm, loading }) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent data-testid="offer-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Award className="w-5 h-5 text-green-600" /> Process Offer</DialogTitle>
          <DialogDescription>{app?.candidate_name} — {app?.job_title}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label className="text-sm font-medium">Offered CTC (Annual, INR) *</Label>
            <Input type="number" min="0" step="1000" placeholder="e.g. 1800000" value={form.offered_ctc}
              onChange={e => setForm(p => ({ ...p, offered_ctc: e.target.value }))} data-testid="offer-ctc-input" />
            {form.offered_ctc > 0 && <p className="text-xs text-gray-500 mt-1">₹{(parseFloat(form.offered_ctc) / 100000).toFixed(1)} LPA</p>}
          </div>
          <div>
            <Label className="text-sm font-medium">Offer Date *</Label>
            <Input type="date" value={form.offer_date} onChange={e => setForm(p => ({ ...p, offer_date: e.target.value }))} data-testid="offer-date-input" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)}>Cancel</Button>
          <Button onClick={onConfirm} disabled={loading} className="bg-green-600 hover:bg-green-700" data-testid="confirm-offer-btn">{loading ? 'Processing...' : 'Confirm Offer'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function HiredDialog({ open, onClose, app, form, setForm, onConfirm, loading }) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent data-testid="hired-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><UserCheck className="w-5 h-5 text-emerald-600" /> Process Hired (Offer Accepted)</DialogTitle>
          <DialogDescription>{app?.candidate_name} — Offered CTC: ₹{app?.offered_ctc ? (app.offered_ctc / 100000).toFixed(1) + 'L' : '—'}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label className="text-sm font-medium">Date of Joining (DOJ) *</Label>
            <Input type="date" value={form.date_of_joining} onChange={e => setForm({ date_of_joining: e.target.value })} data-testid="hired-doj-input" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)}>Cancel</Button>
          <Button onClick={onConfirm} disabled={loading} className="bg-emerald-600 hover:bg-emerald-700" data-testid="confirm-hired-btn">{loading ? 'Processing...' : 'Confirm Hired'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function JoinDialog({ open, onClose, app, form, setForm, onConfirm, loading }) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent data-testid="join-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Lock className="w-5 h-5 text-teal-600" /> Process Joining</DialogTitle>
          <DialogDescription>
            {app?.candidate_name} — Offered CTC: ₹{app?.offered_ctc ? (app.offered_ctc / 100000).toFixed(1) + 'L' : '—'}
            <br /><span className="text-amber-600 text-xs font-medium">Revenue will be locked after this action.</span>
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label className="text-sm font-medium">Join Date *</Label>
            <Input type="date" value={form.join_date} onChange={e => setForm({ join_date: e.target.value })} data-testid="join-date-input" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)}>Cancel</Button>
          <Button onClick={onConfirm} disabled={loading} className="bg-teal-600 hover:bg-teal-700" data-testid="confirm-join-btn">{loading ? 'Processing...' : 'Confirm Joining'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
