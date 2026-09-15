// SearchableMultiSelect
// Spec 5.11 (2026-09-08). Debounced type-ahead against a facet endpoint
// (e.g. /candidate-bank/facets). Selected values render as removable
// chips. Value is a comma-separated string so the existing hook keeps
// working without a shape change.
import { useEffect, useRef, useState } from 'react';
import { X, Search } from 'lucide-react';
import api from '../../lib/api';

export function SearchableMultiSelect({
  field,          // 'location' | 'company' | 'skills'
  value = '',     // comma-separated string
  onChange,       // (nextCsv: string) => void
  placeholder = 'Search…',
  testid,
}) {
  const [q, setQ] = useState('');
  const [options, setOptions] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef(null);
  const selected = value ? value.split(',').map(s => s.trim()).filter(Boolean) : [];

  useEffect(() => {
    if (!open || q.length < 2) { setOptions([]); return; }
    if (abortRef.current) abortRef.current.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await api.get('/candidate-bank/facets', {
          params: { field, q, limit: 20 },
          signal: ctl.signal,
        });
        setOptions(r.data?.values || []);
      } catch (_e) { /* aborted or endpoint error — silent */ }
      finally { setLoading(false); }
    }, 300);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [q, open, field]);

  const toggle = (v) => {
    const set = new Set(selected);
    if (set.has(v)) set.delete(v); else set.add(v);
    onChange(Array.from(set).join(','));
  };
  const remove = (v) => onChange(selected.filter(s => s !== v).join(','));

  return (
    <div className="relative" data-testid={testid}>
      <div className="flex flex-wrap gap-1 mb-1">
        {selected.map(v => (
          <span key={v} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#DCFCE7] text-[#4A7C2C] text-xs font-medium">
            {v}
            <button onClick={() => remove(v)} className="hover:text-red-600"><X className="w-3 h-3" /></button>
          </span>
        ))}
      </div>
      <div className="relative">
        <Search className="w-3.5 h-3.5 absolute left-2 top-2.5 text-slate-400" />
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={placeholder}
          className="w-full pl-7 pr-2 py-1.5 text-sm rounded border border-slate-200 focus:border-[#7CB342] focus:ring-1 focus:ring-[#7CB342] outline-none"
          data-testid={`${testid}-input`}
        />
      </div>
      {open && (q.length >= 2) && (
        <div className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {loading && <div className="px-3 py-2 text-xs text-slate-400">Searching…</div>}
          {!loading && options.length === 0 && (
            <div className="px-3 py-2 text-xs text-slate-400">No matches. Press Enter to add "{q}" as-is.</div>
          )}
          {options.map(o => (
            <button
              key={o.value}
              type="button"
              onClick={() => toggle(o.value)}
              className={`w-full flex items-center justify-between px-3 py-1.5 text-sm hover:bg-slate-50 ${selected.includes(o.value) ? 'bg-emerald-50' : ''}`}
            >
              <span className="text-slate-800">{o.value}</span>
              <span className="text-[10px] text-slate-400">{o.count?.toLocaleString?.() || o.count}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
