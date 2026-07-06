import { useEffect, useState } from 'react';
import { candidateBankAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { Loader2, Merge, Mail, Phone, RefreshCw, ChevronRight } from 'lucide-react';
import SEOHead from '../../components/shared/SEOHead';

/**
 * DedupeMergePage — admin surface for reviewing + merging duplicate
 * candidate records. Reads from GET /candidate-bank/find-all-duplicates
 * (groups on lowercased email and normalized phone, top 50 each) and
 * calls POST /candidate-bank/merge-duplicates with the selected IDs.
 *
 * The backend merge helper handles field-level survivorship (newer wins,
 * non-empty wins over empty) so this UI stays intentionally lean —
 * the recruiter picks which records go into a group and clicks Merge.
 */

const FIELDS = [
  { key: 'name',                label: 'Name' },
  { key: 'email',               label: 'Email' },
  { key: 'phone',               label: 'Phone' },
  { key: 'current_designation', label: 'Designation' },
  { key: 'current_employer',    label: 'Employer' },
  { key: 'current_location',    label: 'Location' },
  { key: 'source',              label: 'Source' },
  { key: 'created_at',          label: 'Captured' },
];

const fmtDate = (v) => {
  if (!v) return '—';
  try { return new Date(v).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return String(v).slice(0, 10); }
};

const displayValue = (c, k) => {
  const v = c?.[k];
  if (v == null || v === '') return '—';
  if (k === 'created_at') return fmtDate(v);
  return String(v);
};

function DuplicateGroup({ group, kind, onMerged }) {
  const [selected, setSelected] = useState(new Set((group.candidates || []).map(c => c.id)));
  const [merging, setMerging] = useState(false);

  const toggle = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const merge = async () => {
    const ids = Array.from(selected);
    if (ids.length < 2) {
      toast.error('Select at least 2 candidates to merge.');
      return;
    }
    setMerging(true);
    try {
      const res = await candidateBankAPI.mergeDuplicates(ids);
      toast.success(res?.data?.message || 'Merge complete.');
      onMerged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Merge failed.');
    } finally {
      setMerging(false);
    }
  };

  const KindIcon = kind === 'email' ? Mail : Phone;

  return (
    <Card className="mb-4" data-testid={`dedupe-group-${group._id}`}>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <div className="flex items-center gap-2 min-w-0">
          <KindIcon className="w-4 h-4 text-slate-500 dark:text-slate-400 shrink-0" />
          <CardTitle className="text-base truncate">{group._id}</CardTitle>
          <Badge variant="secondary" className="ml-2">{group.count} records</Badge>
        </div>
        <Button
          onClick={merge}
          disabled={merging || selected.size < 2}
          size="sm"
          className="bg-[#7CB342] hover:bg-[#689F38] text-white"
          data-testid={`dedupe-merge-btn-${group._id}`}
        >
          {merging ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Merge className="w-4 h-4 mr-2" />}
          Merge selected ({selected.size})
        </Button>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="p-2 w-8"></th>
                {FIELDS.map(f => <th key={f.key} className="p-2 whitespace-nowrap">{f.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {(group.candidates || []).map(c => (
                <tr
                  key={c.id}
                  className={`border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40 ${selected.has(c.id) ? 'bg-emerald-50/60 dark:bg-emerald-950/20' : ''}`}
                  data-testid={`dedupe-row-${c.id}`}
                >
                  <td className="p-2 text-center">
                    <input
                      type="checkbox"
                      checked={selected.has(c.id)}
                      onChange={() => toggle(c.id)}
                      className="accent-[#7CB342]"
                      data-testid={`dedupe-checkbox-${c.id}`}
                    />
                  </td>
                  {FIELDS.map(f => (
                    <td key={f.key} className="p-2 whitespace-nowrap text-slate-700 dark:text-slate-200">
                      {displayValue(c, f.key)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
          <ChevronRight className="w-3 h-3" />
          Backend picks field-level survivorship (newer wins, non-empty wins over empty).
          Uncheck any row you do not want folded into the group.
        </p>
      </CardContent>
    </Card>
  );
}

export default function DedupeMergePage() {
  const [loading, setLoading] = useState(true);
  const [emailGroups, setEmailGroups] = useState([]);
  const [phoneGroups, setPhoneGroups] = useState([]);
  const [merging, setMerging] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await candidateBankAPI.findAllDuplicates();
      setEmailGroups(res?.data?.email_duplicates || []);
      setPhoneGroups(res?.data?.phone_duplicates || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load duplicates.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const mergeAll = async () => {
    if (!window.confirm('Bulk-merge every group shown here? This cannot be undone.')) return;
    setMerging(true);
    try {
      const res = await candidateBankAPI.mergeAllDuplicates();
      toast.success(res?.data?.message || 'Bulk merge complete.');
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Bulk merge failed.');
    } finally {
      setMerging(false);
    }
  };

  const totalGroups = emailGroups.length + phoneGroups.length;

  return (
    <div className="max-w-7xl mx-auto" data-testid="dedupe-merge-page">
      <SEOHead title="Candidate Dedupe" noindex />

      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Candidate Dedupe</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Review email and phone-normalized duplicate groups. Merge preserves the richest record and folds the rest into it.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} disabled={loading} data-testid="dedupe-refresh-btn">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button
            onClick={mergeAll}
            disabled={merging || loading || totalGroups === 0}
            className="bg-[#7CB342] hover:bg-[#689F38] text-white"
            data-testid="dedupe-merge-all-btn"
          >
            {merging ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Merge className="w-4 h-4 mr-2" />}
            Merge all groups
          </Button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 py-16 justify-center">
          <Loader2 className="w-5 h-5 animate-spin" /> Scanning candidate bank for duplicates…
        </div>
      )}

      {!loading && totalGroups === 0 && (
        <Card>
          <CardContent className="py-16 text-center text-slate-500 dark:text-slate-400">
            No duplicate groups found. The bank is clean. 🎉
          </CardContent>
        </Card>
      )}

      {!loading && emailGroups.length > 0 && (
        <div className="mb-8">
          <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
            <Mail className="w-4 h-4" /> Email duplicates
            <Badge variant="secondary">{emailGroups.length}</Badge>
          </h2>
          {emailGroups.map(g => (
            <DuplicateGroup key={`e-${g._id}`} group={g} kind="email" onMerged={load} />
          ))}
        </div>
      )}

      {!loading && phoneGroups.length > 0 && (
        <div>
          <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
            <Phone className="w-4 h-4" /> Phone duplicates
            <Badge variant="secondary">{phoneGroups.length}</Badge>
          </h2>
          {phoneGroups.map(g => (
            <DuplicateGroup key={`p-${g._id}`} group={g} kind="phone" onMerged={load} />
          ))}
        </div>
      )}
    </div>
  );
}
