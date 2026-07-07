import { useEffect, useMemo, useState } from 'react';
import { candidateBankAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '../../components/ui/alert-dialog';
import { toast } from 'sonner';
import { Loader2, Merge, Mail, Phone, RefreshCw, Crown, Info } from 'lucide-react';
import SEOHead from '../../components/shared/SEOHead';

/**
 * DedupeMergePage — admin surface for reviewing + merging duplicate candidates.
 *
 * Reads GET /candidate-bank/find-all-duplicates (groups on lowercased email
 * and normalized phone, top 50 each) and POSTs to /merge-duplicates with the
 * selected IDs. Backend picks field-level survivorship: newest `updated_at`
 * wins, `completeness_score` as tiebreaker. Non-empty wins over empty.
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

// Mirrors backend `_merge_candidate_group`: newest updated_at wins, completeness_score
// tie-breaker. This is a display-only preview — the backend has the final say.
const completenessScore = (d) => {
  let s = 0;
  for (const [k, v] of Object.entries(d || {})) {
    if (k.startsWith('_') || k === 'id' || k === 'created_at' || k === 'updated_at') continue;
    if (v && v !== '' && !(Array.isArray(v) && v.length === 0)) s += 1;
  }
  return s;
};

const predictSurvivor = (candidates) => {
  if (!candidates?.length) return null;
  const sorted = [...candidates].sort((a, b) => {
    const ta = a.updated_at || a.created_at || '';
    const tb = b.updated_at || b.created_at || '';
    if (ta !== tb) return ta < tb ? 1 : -1;
    return completenessScore(b) - completenessScore(a);
  });
  return sorted[0]?.id;
};

function DuplicateGroup({ group, kind, onMerged }) {
  const [selected, setSelected] = useState(new Set((group.candidates || []).map(c => c.id)));
  const [merging, setMerging] = useState(false);

  const survivorId = useMemo(() => predictSurvivor(group.candidates), [group.candidates]);

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
      const skipped = res?.data?.skipped?.length || 0;
      toast.success(res?.data?.message || 'Merge complete.');
      if (skipped > 0) {
        toast.warning(`${skipped} donor(s) skipped due to low match score. See merge_history.`);
      }
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
                <th className="p-2 w-8"></th>
                {FIELDS.map(f => <th key={f.key} className="p-2 whitespace-nowrap">{f.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {(group.candidates || []).map(c => {
                const isSurvivor = c.id === survivorId;
                return (
                  <tr
                    key={c.id}
                    className={`border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40 ${
                      selected.has(c.id) ? 'bg-emerald-50/60 dark:bg-emerald-950/20' : ''
                    } ${isSurvivor ? 'font-medium' : ''}`}
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
                    <td className="p-2 text-center">
                      {isSurvivor && (
                        <Crown
                          className="w-4 h-4 text-amber-500 inline"
                          aria-label="Predicted survivor"
                          title="Predicted survivor (newest updated_at, richest data). Backend has final say."
                          data-testid={`dedupe-survivor-${c.id}`}
                        />
                      )}
                    </td>
                    {FIELDS.map(f => (
                      <td key={f.key} className="p-2 whitespace-nowrap text-slate-700 dark:text-slate-200">
                        {displayValue(c, f.key)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
          <Crown className="w-3 h-3 text-amber-500" />
          Row marked with a crown is the predicted survivor. Backend picks field-level
          survivorship (newer wins, non-empty wins over empty) and enforces a 2-of-3
          name/email/phone gate — donors that fail are flagged for manual review.
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
  const [bulkOpen, setBulkOpen] = useState(false);

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
    setBulkOpen(false);
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
  const totalDuplicateRecords = useMemo(
    () => [...emailGroups, ...phoneGroups].reduce((acc, g) => acc + (g.count || 0), 0),
    [emailGroups, phoneGroups],
  );
  const estimatedFolds = Math.max(0, totalDuplicateRecords - totalGroups);

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
          <AlertDialog open={bulkOpen} onOpenChange={setBulkOpen}>
            <AlertDialogTrigger asChild>
              <Button
                disabled={merging || loading || totalGroups === 0}
                className="bg-[#7CB342] hover:bg-[#689F38] text-white"
                data-testid="dedupe-merge-all-btn"
              >
                {merging ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Merge className="w-4 h-4 mr-2" />}
                Merge all groups
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent data-testid="dedupe-merge-all-dialog">
              <AlertDialogHeader>
                <AlertDialogTitle>Bulk-merge every duplicate group?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will fold <strong>{totalDuplicateRecords}</strong> records into{' '}
                  <strong>{totalGroups}</strong> groups — approximately{' '}
                  <strong>{estimatedFolds}</strong> donor records will be deleted after being
                  merged into their surviving master. Donors that fail the 2-of-3
                  name/email/phone match gate are flagged, not deleted. <strong>This cannot be undone.</strong>
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel data-testid="dedupe-merge-all-cancel">Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={mergeAll}
                  className="bg-[#7CB342] hover:bg-[#689F38]"
                  data-testid="dedupe-merge-all-confirm"
                >
                  Yes, merge all
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {!loading && totalGroups > 0 && (
        <div
          className="mb-6 flex items-center gap-3 rounded-md border border-emerald-200 dark:border-emerald-900 bg-emerald-50/60 dark:bg-emerald-950/20 px-4 py-3 text-sm text-emerald-900 dark:text-emerald-100"
          data-testid="dedupe-summary"
        >
          <Info className="w-4 h-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
          <span>
            <strong>{totalGroups}</strong> duplicate groups covering{' '}
            <strong>{totalDuplicateRecords}</strong> records. Merging all will remove
            approximately <strong>{estimatedFolds}</strong> donor records.
          </span>
        </div>
      )}

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
