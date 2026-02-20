import { useState, useEffect, useCallback } from 'react';
import { trackerAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import { ClipboardList, Download, CheckCircle2, AlertTriangle, Loader2, ArrowLeft } from 'lucide-react';

const STATUS_LABELS = {
  submitted: { label: 'Submitted', color: 'bg-cyan-100 text-cyan-700' },
  interview_scheduled: { label: 'Interview Scheduled', color: 'bg-purple-100 text-purple-700' },
  interviewed: { label: 'Interviewed', color: 'bg-indigo-100 text-indigo-700' },
  offer_issued: { label: 'Offer Issued', color: 'bg-green-100 text-green-700' },
  offer_accepted: { label: 'Offer Accepted', color: 'bg-emerald-100 text-emerald-700' },
  joining_confirmed: { label: 'Joining Confirmed', color: 'bg-teal-100 text-teal-700' },
  rejected: { label: 'Rejected', color: 'bg-red-100 text-red-700' },
  on_hold: { label: 'On Hold', color: 'bg-gray-100 text-gray-700' },
};

// Columns hidden from employer (internal recruiter fields)
const HIDDEN_KEYS = new Set([
  'recruiter_notes', 'why_shortlisted', 'risks_concerns', 'recruiter_rating',
  'ai_resume_score', 'fitment_score', 'recruiter_name', 'technical_rating',
  'communication_rating', 'key_strengths',
]);

export default function EmployerTrackerPage() {
  const [trackers, setTrackers] = useState([]);
  const [selectedTracker, setSelectedTracker] = useState(null);
  const [tracker, setTracker] = useState(null);
  const [validation, setValidation] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadTrackers = useCallback(async () => {
    try {
      const res = await trackerAPI.getTrackers();
      setTrackers(res.data.trackers || []);
    } catch { toast.error('Failed to load trackers'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadTrackers(); }, [loadTrackers]);

  const loadTracker = useCallback(async (id) => {
    setLoading(true);
    try {
      const [tr, val] = await Promise.all([
        trackerAPI.getTracker(id),
        trackerAPI.validate(id),
      ]);
      setTracker(tr.data);
      setValidation(val.data);
    } catch { toast.error('Failed to load tracker'); }
    finally { setLoading(false); }
  }, []);

  const handleSelect = (id) => {
    setSelectedTracker(id);
    loadTracker(id);
  };

  const handleDownload = async () => {
    if (!selectedTracker) return;
    try {
      const res = await trackerAPI.exportExcel(selectedTracker);
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${tracker?.name || 'tracker'}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Download failed'); }
  };

  if (loading && !selectedTracker) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;
  }

  // Tracker Detail View (read-only)
  if (selectedTracker && tracker) {
    const columns = (tracker.columns || []).filter(c => !HIDDEN_KEYS.has(c.key));
    const rows = tracker.rows || [];
    const downloadColor = validation?.status === 'green'
      ? 'bg-green-600 hover:bg-green-700 text-white'
      : 'bg-amber-500 hover:bg-amber-600 text-white';

    return (
      <div className="space-y-4" data-testid="employer-tracker-detail">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => { setSelectedTracker(null); setTracker(null); }} data-testid="employer-back-btn">
              <ArrowLeft className="h-4 w-4 mr-1" /> Back
            </Button>
            <div>
              <h2 className="text-xl font-bold" data-testid="employer-tracker-name">{tracker.name}</h2>
              <p className="text-xs text-muted-foreground">{tracker.mandate_name} &middot; {rows.length} candidates</p>
            </div>
          </div>
          <Button size="sm" className={downloadColor} onClick={handleDownload} data-testid="employer-download-btn">
            {validation?.status === 'green' ? <CheckCircle2 className="h-4 w-4 mr-1" /> : <AlertTriangle className="h-4 w-4 mr-1" />}
            Download Excel
          </Button>
        </div>

        <div className="border rounded-lg overflow-auto bg-white" style={{ maxHeight: '65vh' }}>
          <table className="w-full text-sm" data-testid="employer-tracker-table">
            <thead className="bg-slate-50 sticky top-0 z-10">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 border-b w-8">#</th>
                {columns.map(col => (
                  <th key={col.key} className="px-3 py-2 text-left text-xs font-semibold text-slate-500 border-b whitespace-nowrap min-w-[120px]">
                    {col.label}
                  </th>
                ))}
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 border-b min-w-[140px]">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={columns.length + 2} className="text-center py-10 text-muted-foreground">No candidates submitted yet.</td></tr>
              ) : rows.map((row, idx) => (
                <tr key={row.id} className="border-b hover:bg-slate-50/50" data-testid={`employer-row-${idx}`}>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{idx + 1}</td>
                  {columns.map(col => (
                    <td key={col.key} className="px-3 py-2 text-sm">
                      {row.data?.[col.key] || <span className="text-slate-300">&mdash;</span>}
                    </td>
                  ))}
                  <td className="px-3 py-2">
                    <span className={`text-xs rounded-full px-2.5 py-1 font-medium ${STATUS_LABELS[row.submission_status]?.color || 'bg-gray-100 text-gray-600'}`}>
                      {STATUS_LABELS[row.submission_status]?.label || row.submission_status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Tracker List
  return (
    <div className="space-y-6" data-testid="employer-tracker-list">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-cyan-50 border border-cyan-200"><ClipboardList className="h-5 w-5 text-cyan-700" /></div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight" data-testid="employer-tracker-title">Submission Trackers</h1>
          <p className="text-sm text-muted-foreground">Track candidate submissions for your mandates</p>
        </div>
      </div>

      {trackers.length === 0 ? (
        <Card className="border-dashed"><CardContent className="py-12 text-center">
          <ClipboardList className="h-12 w-12 mx-auto text-muted-foreground/40 mb-3" />
          <p className="text-muted-foreground">No submission trackers available yet.</p>
        </CardContent></Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {trackers.map(t => (
            <Card key={t.id} className="cursor-pointer hover:border-cyan-300 transition-colors" onClick={() => handleSelect(t.id)} data-testid={`employer-tracker-card-${t.id}`}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center justify-between">
                  <span className="truncate">{t.name}</span>
                  <Badge variant="secondary" className="text-xs ml-2 shrink-0">{t.row_count || 0}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">{t.mandate_name}</p>
                <p className="text-xs text-muted-foreground mt-1">Updated {new Date(t.updated_at || t.created_at).toLocaleDateString('en-IN')}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
