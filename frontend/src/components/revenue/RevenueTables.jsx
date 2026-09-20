/**
 * Tables for the Branch & Recruiter Revenue tracker — column-for-column
 * with the client's sheet. Money is shown in full rupees (no rounding to
 * lakhs) because these numbers get reconciled against invoices.
 */
import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { Badge } from '../ui/badge';

export const inr = (n) => (n || n === 0)
  ? `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
  : '—';

export const compactINR = (n) => {
  const v = Number(n || 0);
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  return inr(v);
};

export const downloadCSV = (filename, columns, rows) => {
  const esc = (v) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const body = [
    columns.map((c) => esc(c.label)).join(','),
    ...rows.map((r) => columns.map((c) => esc(c.value(r))).join(',')),
  ].join('\n');
  const url = URL.createObjectURL(new Blob([body], { type: 'text/csv;charset=utf-8;' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

const STATUS_STYLE = {
  'Payment Received': 'bg-[#7CB342]/10 text-[#33691E] border-[#7CB342]/30',
  PP: 'bg-amber-50 text-amber-700 border-amber-200',
  IP: 'bg-sky-50 text-sky-700 border-sky-200',
  Backout: 'bg-rose-50 text-rose-700 border-rose-200',
  'Credit Note': 'bg-rose-50 text-rose-700 border-rose-200',
  'Other / Review': 'bg-slate-100 text-slate-600 border-slate-200',
};

export function StatusChip({ status }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[status] || STATUS_STYLE['Other / Review']}`}>
      {status || '—'}
    </span>
  );
}

/** Shared sortable table. `cols` = [{ key, label, align, render, csv }] */
export function DataTable({ cols, rows, initialSort, footer, onRowClick, testId, empty = 'Nothing in this period.' }) {
  const [sort, setSort] = useState(initialSort || { key: cols[0].key, dir: 'desc' });

  const sorted = useMemo(() => {
    const out = [...rows];
    out.sort((a, b) => {
      const x = a[sort.key], y = b[sort.key];
      const cmp = typeof x === 'number' && typeof y === 'number'
        ? x - y
        : String(x ?? '').localeCompare(String(y ?? ''));
      return sort.dir === 'asc' ? cmp : -cmp;
    });
    return out;
  }, [rows, sort]);

  const toggle = (key) => setSort((s) => (
    s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }
  ));

  if (!rows.length) return <p className="py-10 text-center text-sm text-slate-500">{empty}</p>;

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200" data-testid={testId}>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 sticky top-0 z-10">
          <tr>
            {cols.map((c) => (
              <th
                key={c.key}
                onClick={() => toggle(c.key)}
                className={`px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500 whitespace-nowrap cursor-pointer select-none hover:text-slate-800 ${c.align === 'right' ? 'text-right' : 'text-left'}`}
              >
                <span className="inline-flex items-center gap-1">
                  {c.label}
                  {sort.key === c.key && (sort.dir === 'asc'
                    ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr
              key={r._key || r.id || i}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={`border-t border-slate-100 ${onRowClick ? 'cursor-pointer hover:bg-[#7CB342]/5' : 'hover:bg-slate-50/70'}`}
            >
              {cols.map((c) => (
                <td key={c.key}
                    className={`px-3 py-2 whitespace-nowrap ${c.align === 'right' ? 'text-right tabular-nums' : ''}`}>
                  {c.render ? c.render(r) : (r[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {footer && (
          <tfoot className="bg-slate-50 font-semibold">
            <tr>
              {cols.map((c) => (
                <td key={c.key}
                    className={`px-3 py-2 whitespace-nowrap border-t-2 border-slate-200 ${c.align === 'right' ? 'text-right tabular-nums' : ''}`}>
                  {footer[c.key] ?? ''}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

export function Achievement({ pct, target }) {
  if (!target) return <span className="text-slate-400">no target</span>;
  const tone = pct >= 100 ? 'bg-[#7CB342]/10 text-[#33691E] border-[#7CB342]/30'
    : pct >= 60 ? 'bg-amber-50 text-amber-700 border-amber-200'
      : 'bg-rose-50 text-rose-700 border-rose-200';
  return <Badge variant="outline" className={tone}>{pct}%</Badge>;
}
