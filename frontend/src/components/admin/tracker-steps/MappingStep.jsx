import { Badge } from '../../ui/badge';
import { Switch } from '../../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { ArrowRight } from 'lucide-react';

export default function MappingStep({ uploadMapping, setUploadMapping, masterCols }) {
  if (!uploadMapping) return null;

  const updateMapping = (idx, masterKey) => {
    setUploadMapping(prev => {
      const newMapping = prev.mapping.map(m => {
        if (m.index === idx) {
          if (masterKey === '_skip') return { ...m, matched: false, master_column: null, custom: false };
          if (masterKey === '_custom') return { ...m, matched: false, master_column: null, custom: true, customKey: `upload_${m.header.toLowerCase().replace(/[^a-z0-9]+/g, '_')}` };
          const mc = masterCols.find(c => c.key === masterKey);
          return { ...m, matched: true, master_column: mc, custom: false };
        }
        return m;
      });
      return { ...prev, mapping: newMapping, matched_count: newMapping.filter(m => m.matched).length };
    });
  };

  const toggleRequired = (idx) => {
    setUploadMapping(prev => ({
      ...prev,
      mapping: prev.mapping.map(m => m.index === idx ? { ...m, required: !m.required } : m),
    }));
  };

  return (
    <div className="space-y-4" data-testid="step-mapping">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">Map file columns to master fields</p>
        <Badge variant="outline" className="text-xs">{uploadMapping.matched_count}/{uploadMapping.total_headers} matched</Badge>
      </div>
      <div className="space-y-2 max-h-[340px] overflow-y-auto pr-1">
        {uploadMapping.mapping.map(m => (
          <div key={m.index} className={`flex items-center gap-3 p-2.5 rounded-lg border ${
            m.matched ? 'border-emerald-200 bg-emerald-50/40' :
            m.custom ? 'border-blue-200 bg-blue-50/40' :
            'border-slate-200'
          }`} data-testid={`map-row-${m.index}`}>
            <div className="w-32 shrink-0">
              <p className="text-xs font-medium text-slate-700 truncate">{m.header}</p>
            </div>
            <ArrowRight className="w-3 h-3 text-slate-300 shrink-0" />
            <Select value={m.matched ? m.master_column?.key : m.custom ? '_custom' : '_skip'} onValueChange={v => updateMapping(m.index, v)}>
              <SelectTrigger className="h-8 text-xs flex-1"><SelectValue placeholder="Map to..." /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_skip"><span className="text-slate-400">Skip column</span></SelectItem>
                <SelectItem value="_custom"><span className="text-blue-600">Keep as custom</span></SelectItem>
                {masterCols.map(c => <SelectItem key={c.key} value={c.key}>{c.label} ({c.category})</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-1.5 shrink-0">
              <Switch checked={m.required || false} onCheckedChange={() => toggleRequired(m.index)} />
              <span className="text-[9px] text-slate-400 w-8">{m.required ? 'Req' : 'Opt'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
