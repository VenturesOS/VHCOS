import { useState, useMemo } from 'react';
import { Input } from '../../ui/input';
import { Badge } from '../../ui/badge';
import { Search, Check } from 'lucide-react';

export default function ColumnSelectionStep({ masterCols, categories, selectedColumns, setSelectedColumns }) {
  const [search, setSearch] = useState('');

  const grouped = useMemo(() => {
    const g = {};
    for (const cat of categories) g[cat] = [];
    masterCols.forEach(c => {
      if (search && !c.label.toLowerCase().includes(search.toLowerCase()) && !c.key.toLowerCase().includes(search.toLowerCase())) return;
      (g[c.category] = g[c.category] || []).push(c);
    });
    return g;
  }, [masterCols, categories, search]);

  const toggle = (key) => {
    setSelectedColumns(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  };

  const selectAll = (cat) => {
    const keys = (grouped[cat] || []).map(c => c.key);
    const allSelected = keys.every(k => selectedColumns.includes(k));
    if (allSelected) setSelectedColumns(prev => prev.filter(k => !keys.includes(k)));
    else setSelectedColumns(prev => [...new Set([...prev, ...keys])]);
  };

  return (
    <div className="space-y-4" data-testid="step-column-selection">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">{selectedColumns.length} columns selected</p>
      </div>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search columns..." className="pl-9" data-testid="column-search" />
      </div>
      <div className="space-y-3 max-h-[340px] overflow-y-auto pr-1">
        {Object.entries(grouped).map(([cat, cols]) => {
          if (cols.length === 0) return null;
          const allSel = cols.every(c => selectedColumns.includes(c.key));
          return (
            <div key={cat} data-testid={`category-${cat}`}>
              <button onClick={() => selectAll(cat)}
                className="flex items-center gap-2 w-full text-left mb-1.5 group">
                <span className={`w-4 h-4 rounded border flex items-center justify-center text-[10px] transition-colors ${
                  allSel ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-300 group-hover:border-slate-400'
                }`}>{allSel && <Check className="w-3 h-3" />}</span>
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{cat}</span>
                <span className="text-[10px] text-slate-400 ml-auto">{cols.filter(c => selectedColumns.includes(c.key)).length}/{cols.length}</span>
              </button>
              <div className="grid grid-cols-2 gap-1 ml-6">
                {cols.sort((a, b) => a.label.localeCompare(b.label)).map(c => {
                  const sel = selectedColumns.includes(c.key);
                  return (
                    <button key={c.key} onClick={() => toggle(c.key)}
                      className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left text-xs transition-all ${
                        sel ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200' : 'hover:bg-slate-50 text-slate-600'
                      }`}
                      data-testid={`col-${c.key}`}
                    >
                      <span className={`w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 ${
                        sel ? 'bg-blue-600 border-blue-600' : 'border-slate-300'
                      }`}>{sel && <Check className="w-2.5 h-2.5 text-white" />}</span>
                      <span className="truncate">{c.label}</span>
                      <Badge variant="outline" className="ml-auto text-[9px] px-1 py-0 shrink-0">{c.field_type}</Badge>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
