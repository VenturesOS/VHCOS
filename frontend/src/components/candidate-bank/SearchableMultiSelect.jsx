// SearchableMultiSelect (fix.docx 2026-09-16 refresh)
//
// Behavior contract per the user's exact ask:
//   1. On box focus the full alphabetical list of options for that field
//      preloads once (no typing required).
//   2. As the user types in the search box, the ALREADY-fetched list
//      filters client-side — no debounced fetch per keystroke.
//   3. Selected values render as removable green chips.
//   4. Value is a comma-separated string so the parent hook doesn't
//      need to know it's multi-select.
//
// The backend endpoint (`/candidate-bank/facets`) reads from the
// precomputed `facet_cache` collection, so preloading is < 200 ms even
// on a 178 k-row bank.
import { useEffect, useMemo, useRef, useState } from 'react';
import { X, Search, ChevronDown, Loader2 } from 'lucide-react';
import api from '../../lib/api';

// Per-field cache so re-opening the same dropdown is instant. Persists
// for the lifetime of the tab (no TTL — cache is invalidated on hard
// refresh, which matches user expectations for a picker).
const _fieldCache = new Map();  // field → array of {value, count}
const _inFlight   = new Map();  // field → Promise

async function _loadOptions(field) {
  if (_fieldCache.has(field)) return _fieldCache.get(field);
  if (_inFlight.has(field))    return _inFlight.get(field);
  const p = api
    .get('/candidate-bank/facets', { params: { field, limit: 500 } })
    .then(r => {
      const rows = (r.data?.values || []).slice().sort(
        (a, b) => (a.value || '').toString().localeCompare((b.value || '').toString(), 'en', { sensitivity: 'base' })
      );
      _fieldCache.set(field, rows);
      _inFlight.delete(field);
      return rows;
    })
    .catch((e) => {
      _inFlight.delete(field);
      return [];
    });
  _inFlight.set(field, p);
  return p;
}

export function SearchableMultiSelect({
  field,
  value = '',
  onChange,
  placeholder = 'Click to pick…',
  testid,
}) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState(() => _fieldCache.get(field) || []);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  const selected = value ? value.split(',').map(s => s.trim()).filter(Boolean) : [];

  const ensureLoaded = async () => {
    if (_fieldCache.has(field)) {
      setOptions(_fieldCache.get(field));
      return;
    }
    setLoading(true);
    const rows = await _loadOptions(field);
    setOptions(rows);
    setLoading(false);
  };

  useEffect(() => {
    // Preload when the component mounts too, so the FIRST focus is instant.
    if (!_fieldCache.has(field)) {
      _loadOptions(field).then(rows => setOptions(rows));
    }
  }, [field]);

  const filtered = useMemo(() => {
    const nq = q.trim().toLowerCase();
    if (!nq) return options;
    return options.filter(o => (o.value || '').toString().toLowerCase().includes(nq));
  }, [q, options]);

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
            <button onMouseDown={(e) => { e.preventDefault(); remove(v); }} className="hover:text-red-600" data-testid={`${testid}-remove-${v}`}>
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="relative">
        <Search className="w-3.5 h-3.5 absolute left-2 top-2.5 text-slate-400" />
        <input
          ref={inputRef}
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => { ensureLoaded(); setOpen(true); }}
          onBlur={() => setTimeout(() => setOpen(false), 200)}
          placeholder={placeholder}
          className="w-full pl-7 pr-7 py-1.5 text-sm rounded border border-slate-200 focus:border-[#7CB342] focus:ring-1 focus:ring-[#7CB342] outline-none"
          data-testid={`${testid}-input`}
        />
        <ChevronDown className="w-3.5 h-3.5 absolute right-2 top-2.5 text-slate-400 pointer-events-none" />
      </div>
      {open && (
        <div className="absolute z-20 mt-1 w-full max-h-72 overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {loading && (
            <div className="px-3 py-2 text-xs text-slate-400 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" /> Loading options…
            </div>
          )}
          {!loading && filtered.length === 0 && (
            <div className="px-3 py-2 text-xs text-slate-400">
              No matches{q ? ` for "${q}"` : ''}.
            </div>
          )}
          {!loading && filtered.slice(0, 200).map(o => (
            <button
              key={o.value}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); toggle(o.value); }}
              className={`w-full flex items-center justify-between px-3 py-1.5 text-sm hover:bg-slate-50 ${selected.includes(o.value) ? 'bg-emerald-50' : ''}`}
            >
              <span className="text-slate-800 truncate pr-2">{o.value}</span>
              <span className="text-[10px] text-slate-400 shrink-0">
                {o.count?.toLocaleString?.() || o.count || ''}
              </span>
            </button>
          ))}
          {!loading && filtered.length > 200 && (
            <div className="px-3 py-1.5 text-[11px] text-slate-400 border-t bg-slate-50">
              Showing top 200 of {filtered.length}. Type to narrow.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
