import { useState } from 'react';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Badge } from '../../ui/badge';
import { Switch } from '../../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { toast } from 'sonner';
import { Plus, GripVertical, Trash2 } from 'lucide-react';

const FIELD_TYPE_LABELS = { text: 'Text', number: 'Number', currency: 'Currency', date: 'Date', dropdown: 'Dropdown' };

export default function CustomColumnsStep({ customColumns, setCustomColumns, existingKeys }) {
  const [showAdd, setShowAdd] = useState(false);
  const [newLabel, setNewLabel] = useState('');
  const [newType, setNewType] = useState('text');
  const [newRequired, setNewRequired] = useState(false);
  const [newDropdownOpts, setNewDropdownOpts] = useState('');

  const addColumn = () => {
    if (!newLabel.trim()) return toast.error('Column name required');
    const key = `custom_${newLabel.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_')}`;
    if (existingKeys.has(key)) return toast.error('Column already exists');

    setCustomColumns(prev => [...prev, {
      key, label: newLabel.trim(), field_type: newType, required: newRequired,
      dropdown_options: newType === 'dropdown' ? newDropdownOpts.split(',').map(o => o.trim()).filter(Boolean) : [],
    }]);
    setNewLabel(''); setNewType('text'); setNewRequired(false); setNewDropdownOpts('');
    setShowAdd(false);
  };

  const removeColumn = (key) => setCustomColumns(prev => prev.filter(c => c.key !== key));

  return (
    <div className="space-y-4" data-testid="step-custom-columns">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">Add custom fields that aren't in the master column library</p>
        <Button size="sm" variant="outline" onClick={() => setShowAdd(true)} data-testid="add-custom-col-btn">
          <Plus className="w-3.5 h-3.5 mr-1" /> Add Column
        </Button>
      </div>

      {showAdd && (
        <div className="p-4 rounded-xl border border-blue-200 bg-blue-50/40 space-y-3" data-testid="add-custom-form">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Column Name *</Label>
              <Input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="e.g. Interview Feedback" className="mt-1 text-sm" data-testid="custom-col-name" />
            </div>
            <div>
              <Label className="text-xs">Field Type</Label>
              <Select value={newType} onValueChange={setNewType}>
                <SelectTrigger className="mt-1" data-testid="custom-col-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(FIELD_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          {newType === 'dropdown' && (
            <div>
              <Label className="text-xs">Dropdown Options (comma-separated)</Label>
              <Input value={newDropdownOpts} onChange={e => setNewDropdownOpts(e.target.value)} placeholder="Option 1, Option 2, Option 3" className="mt-1 text-sm" data-testid="custom-col-options" />
            </div>
          )}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Switch checked={newRequired} onCheckedChange={setNewRequired} data-testid="custom-col-required" />
              <Label className="text-xs">Required field</Label>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button size="sm" onClick={addColumn} data-testid="confirm-add-custom">Add</Button>
            </div>
          </div>
        </div>
      )}

      {customColumns.length === 0 && !showAdd && (
        <div className="text-center py-8 text-sm text-slate-400 border border-dashed rounded-xl">
          No custom columns added yet. This step is optional.
        </div>
      )}

      {customColumns.length > 0 && (
        <div className="space-y-2">
          {customColumns.map(c => (
            <div key={c.key} className="flex items-center gap-3 p-3 bg-white rounded-lg border border-slate-200" data-testid={`custom-col-${c.key}`}>
              <GripVertical className="w-4 h-4 text-slate-300 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-800 truncate">{c.label}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <Badge variant="outline" className="text-[9px]">{FIELD_TYPE_LABELS[c.field_type]}</Badge>
                  {c.required && <Badge className="text-[9px] bg-red-50 text-red-600 border-red-200">Required</Badge>}
                  {c.dropdown_options?.length > 0 && <span className="text-[9px] text-slate-400">{c.dropdown_options.length} options</span>}
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => removeColumn(c.key)} className="text-slate-400 hover:text-red-500 shrink-0" data-testid={`remove-custom-${c.key}`}>
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

