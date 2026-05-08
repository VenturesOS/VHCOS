import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { Plus, Upload, FileSpreadsheet } from 'lucide-react';

export default function BasicSetupStep({ name, setName, mandateId, setMandateId, templateMode, setTemplateMode, existingTemplateId, setExistingTemplateId, jobs, templates }) {
  return (
    <div className="space-y-5" data-testid="step-basic-setup">
      <div>
        <Label className="text-sm font-medium">Tracker Name *</Label>
        <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Senior Python Dev — ABC Corp" className="mt-1.5" data-testid="wizard-tracker-name" />
      </div>
      <div>
        <Label className="text-sm font-medium">Mandate / Job *</Label>
        <Select value={mandateId} onValueChange={setMandateId}>
          <SelectTrigger className="mt-1.5" data-testid="wizard-mandate-select"><SelectValue placeholder="Select a mandate" /></SelectTrigger>
          <SelectContent>
            {jobs.map(j => <SelectItem key={j.id} value={j.id}>{j.title}{j.company_name ? ` — ${j.company_name}` : ''}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="text-sm font-medium">Template</Label>
        <div className="grid grid-cols-3 gap-3 mt-2">
          {[
            { key: 'existing', label: 'Use Existing', icon: FileSpreadsheet, desc: 'Pick a saved template' },
            { key: 'new', label: 'Create New', icon: Plus, desc: 'Build from column library' },
            { key: 'upload', label: 'Upload File', icon: Upload, desc: 'Import from Excel/CSV' },
          ].map(opt => (
            <button key={opt.key} onClick={() => setTemplateMode(opt.key)}
              className={`p-3 rounded-xl border-2 text-left transition-all ${templateMode === opt.key ? 'border-blue-500 bg-blue-50/80 ring-1 ring-blue-200' : 'border-slate-200 hover:border-slate-300 bg-white'}`}
              data-testid={`template-mode-${opt.key}`}>
              <opt.icon className={`w-5 h-5 mb-1.5 ${templateMode === opt.key ? 'text-blue-600' : 'text-slate-400'}`} />
              <p className="text-sm font-medium">{opt.label}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">{opt.desc}</p>
            </button>
          ))}
        </div>
      </div>
      {templateMode === 'existing' && (
        <div>
          <Label className="text-sm font-medium">Select Template *</Label>
          <Select value={existingTemplateId} onValueChange={setExistingTemplateId}>
            <SelectTrigger className="mt-1.5" data-testid="wizard-existing-template"><SelectValue placeholder="Choose template" /></SelectTrigger>
            <SelectContent>
              {templates.map(t => (
                <SelectItem key={t.id} value={t.id}>{t.name} <span className="text-muted-foreground ml-1">({t.columns?.length || 0} cols)</span></SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  );
}
