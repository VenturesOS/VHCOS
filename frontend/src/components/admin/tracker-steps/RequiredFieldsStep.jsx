import { useMemo } from 'react';
import { Badge } from '../../ui/badge';
import { Switch } from '../../ui/switch';

export default function RequiredFieldsStep({ masterCols, selectedColumns, setSelectedColumns, customColumns, setCustomColumns }) {
  const allCols = useMemo(() => {
    const master = selectedColumns.map(key => {
      const mc = masterCols.find(c => c.key === key);
      return { key, label: mc?.label || key, type: 'master', required: mc?._required ?? mc?.default_required ?? false };
    });
    const custom = customColumns.map(c => ({ key: c.key, label: c.label, type: 'custom', required: c.required }));
    return [...master, ...custom];
  }, [masterCols, selectedColumns, customColumns]);

  const toggleRequired = (key, type) => {
    if (type === 'master') {
      const mc = masterCols.find(c => c.key === key);
      if (mc) mc._required = !mc._required;
      setSelectedColumns([...selectedColumns]); // force re-render
    } else {
      setCustomColumns(prev => prev.map(c => c.key === key ? { ...c, required: !c.required } : c));
    }
  };

  const requiredCount = allCols.filter(c => c.required).length;

  return (
    <div className="space-y-4" data-testid="step-required-fields">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">Mark fields as required for download validation</p>
        <Badge variant="outline" className="text-xs">{requiredCount} required / {allCols.length} total</Badge>
      </div>
      <div className="space-y-1.5 max-h-[360px] overflow-y-auto pr-1">
        {allCols.map(c => (
          <div key={c.key} className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 transition-colors" data-testid={`req-${c.key}`}>
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm text-slate-700 truncate">{c.label}</span>
              {c.type === 'custom' && <Badge variant="outline" className="text-[9px] shrink-0">Custom</Badge>}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-[10px] ${c.required ? 'text-red-500 font-medium' : 'text-slate-400'}`}>
                {c.required ? 'Required' : 'Optional'}
              </span>
              <Switch checked={c.required} onCheckedChange={() => toggleRequired(c.key, c.type)} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
