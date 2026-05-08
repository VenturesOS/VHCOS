import { Badge } from '../../ui/badge';

export default function ReviewStep({ name, mandateId, jobs, templateMode, existingTemplateId, templates, masterCols, selectedColumns, customColumns, uploadMapping }) {
  const mandate = jobs.find(j => j.id === mandateId);

  let columnSummary = [];
  if (templateMode === 'existing') {
    const tpl = templates.find(t => t.id === existingTemplateId);
    columnSummary = tpl?.columns?.map(c => ({ label: c.label, required: c.required, type: c.is_custom ? 'Custom' : c.category })) || [];
  } else if (templateMode === 'upload' && uploadMapping) {
    columnSummary = uploadMapping.mapping
      .filter(m => m.matched || m.custom)
      .map(m => ({
        label: m.master_column?.label || m.header,
        required: m.required || false,
        type: m.matched ? (m.master_column?.category || 'Master') : 'Custom',
      }));
  } else {
    const mc = selectedColumns.map(key => {
      const c = masterCols.find(col => col.key === key);
      return { label: c?.label || key, required: c?._required ?? c?.default_required ?? false, type: c?.category || 'Master' };
    });
    const cc = customColumns.map(c => ({ label: c.label, required: c.required, type: 'Custom' }));
    columnSummary = [...mc, ...cc];
  }

  const requiredCount = columnSummary.filter(c => c.required).length;

  return (
    <div className="space-y-4" data-testid="step-review">
      <p className="text-sm text-slate-600">Review your tracker configuration before creating</p>

      <div className="grid grid-cols-2 gap-4">
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Tracker</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">{name}</p>
        </div>
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Mandate</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">{mandate?.title || 'Unknown'}</p>
        </div>
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Template</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">
            {templateMode === 'existing' ? templates.find(t => t.id === existingTemplateId)?.name : 'New (auto-created)'}
          </p>
        </div>
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Columns</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">{columnSummary.length} total, {requiredCount} required</p>
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-slate-500 mb-2">Column List</p>
        <div className="max-h-[200px] overflow-y-auto space-y-1 pr-1">
          {columnSummary.map((c, i) => (
            <div key={i} className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-white border border-slate-100 text-xs">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-slate-700 truncate">{c.label}</span>
                <Badge variant="outline" className="text-[8px] px-1 shrink-0">{c.type}</Badge>
              </div>
              {c.required && <Badge className="text-[8px] bg-red-50 text-red-600 border-red-200 shrink-0">Required</Badge>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
