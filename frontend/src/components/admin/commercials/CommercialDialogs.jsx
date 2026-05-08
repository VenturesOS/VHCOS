import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../../ui/dialog';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { AlertCircle } from 'lucide-react';

export function CommercialFormDialog({ open, onClose, isCreate, form, setForm, companies, onSubmit, submitting }) {
  return (
    <Dialog open={open} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-heading">{isCreate ? 'Create Commercial' : 'Edit Commercial'}</DialogTitle>
          <DialogDescription>Define fee structure for client engagements</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          {isCreate && (
            <div className="space-y-2">
              <Label>Company *</Label>
              <Select value={form.company_id} onValueChange={v => setForm({ ...form, company_id: v })}>
                <SelectTrigger><SelectValue placeholder="Select company" /></SelectTrigger>
                <SelectContent>{companies.map(c => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-2">
            <Label>Commercial Name *</Label>
            <Input value={form.commercial_name} onChange={e => setForm({ ...form, commercial_name: e.target.value })} placeholder="e.g., Standard IT Hiring" />
          </div>
          <div className="space-y-2">
            <Label>Type *</Label>
            <Select value={form.type} onValueChange={v => setForm({ ...form, type: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="percentage">Percentage of Salary</SelectItem>
                <SelectItem value="fixed">Fixed Fee</SelectItem>
                <SelectItem value="level_based">Level-Based</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {form.type === 'percentage' && (
            <div className="space-y-2">
              <Label>Fee Percentage *</Label>
              <div className="relative">
                <Input type="number" step="0.01" value={form.fee_percentage} onChange={e => setForm({ ...form, fee_percentage: e.target.value })} placeholder="8.33" className="pr-8" />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">%</span>
              </div>
            </div>
          )}
          {form.type === 'fixed' && (
            <div className="space-y-2">
              <Label>Fixed Amount (INR) *</Label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">&#8377;</span>
                <Input type="number" value={form.fixed_amount} onChange={e => setForm({ ...form, fixed_amount: e.target.value })} placeholder="100000" className="pl-8" />
              </div>
            </div>
          )}
          {form.type === 'level_based' && (
            <div className="space-y-3 p-3 bg-slate-50 rounded-lg">
              <Label>Level-wise Percentages *</Label>
              <div className="grid grid-cols-2 gap-3">
                {['junior', 'mid', 'senior', 'leadership'].map(level => (
                  <div key={level}>
                    <Label className="text-xs text-slate-500 capitalize">{level}</Label>
                    <Input type="number" step="0.01" value={form.level_config[level]}
                      onChange={e => setForm({ ...form, level_config: { ...form.level_config, [level]: e.target.value } })}
                      placeholder={level === 'junior' ? '8' : level === 'mid' ? '10' : level === 'senior' ? '12' : '15'} />
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Effective From *</Label>
              <Input type="date" value={form.effective_from} onChange={e => setForm({ ...form, effective_from: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label>Effective To (Optional)</Label>
              <Input type="date" value={form.effective_to} onChange={e => setForm({ ...form, effective_to: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Salary Min (Optional)</Label>
              <Input type="number" value={form.salary_min} onChange={e => setForm({ ...form, salary_min: e.target.value })} placeholder="300000" />
            </div>
            <div className="space-y-2">
              <Label>Salary Max (Optional)</Label>
              <Input type="number" value={form.salary_max} onChange={e => setForm({ ...form, salary_max: e.target.value })} placeholder="1500000" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button onClick={onSubmit} disabled={submitting} className="bg-[#7CB342] hover:bg-[#689F38]">
            {submitting ? 'Saving...' : isCreate ? 'Create' : 'Save Changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function DeleteCommercialDialog({ open, onClose, commercial, onDelete }) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-red-600 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" /> Deactivate Commercial
          </DialogTitle>
          <DialogDescription>
            Are you sure you want to deactivate <strong>{commercial?.commercial_name}</strong>? This will prevent it from being used in new revenue calculations.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)}>Cancel</Button>
          <Button variant="destructive" onClick={onDelete}>Deactivate</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
