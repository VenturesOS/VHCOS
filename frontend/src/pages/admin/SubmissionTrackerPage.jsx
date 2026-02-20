import { useState, useEffect, useCallback, useRef } from 'react';
import { trackerAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import {
  Table, Plus, FileSpreadsheet, Download, AlertTriangle, CheckCircle2,
  Trash2, Search, Settings2, Loader2, ChevronDown, X, ClipboardList, Eye, Upload
} from 'lucide-react';
import CreateTrackerWizard from '../../components/admin/CreateTrackerWizard';

const STATUS_OPTIONS = [
  { value: 'submitted', label: 'Submitted', color: 'bg-cyan-100 text-cyan-700' },
  { value: 'interview_scheduled', label: 'Interview Scheduled', color: 'bg-purple-100 text-purple-700' },
  { value: 'interviewed', label: 'Interviewed', color: 'bg-indigo-100 text-indigo-700' },
  { value: 'offer_issued', label: 'Offer Issued', color: 'bg-green-100 text-green-700' },
  { value: 'offer_accepted', label: 'Offer Accepted', color: 'bg-emerald-100 text-emerald-700' },
  { value: 'joining_confirmed', label: 'Joining Confirmed', color: 'bg-teal-100 text-teal-700' },
  { value: 'rejected', label: 'Rejected', color: 'bg-red-100 text-red-700' },
  { value: 'on_hold', label: 'On Hold', color: 'bg-gray-100 text-gray-700' },
];

const STATUS_MAP = Object.fromEntries(STATUS_OPTIONS.map(s => [s.value, s]));

// ── Tracker List View ──
function TrackerListView({ onSelectTracker }) {
  const [trackers, setTrackers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const tr = await trackerAPI.getTrackers();
      setTrackers(tr.data.trackers || []);
    } catch { toast.error('Failed to load trackers'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-6" data-testid="tracker-list-view">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-50 border border-cyan-200"><ClipboardList className="h-5 w-5 text-cyan-700" /></div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight" data-testid="tracker-page-title">Client Submission Trackers</h1>
            <p className="text-sm text-muted-foreground">Manage candidate submissions per mandate</p>
          </div>
        </div>
        <Button onClick={() => setShowWizard(true)} data-testid="create-tracker-btn"><Plus className="h-4 w-4 mr-1" /> New Tracker</Button>
      </div>

      {trackers.length === 0 ? (
        <Card className="border-dashed"><CardContent className="py-12 text-center">
          <FileSpreadsheet className="h-12 w-12 mx-auto text-muted-foreground/40 mb-3" />
          <p className="text-muted-foreground">No trackers yet. Create one to start tracking submissions.</p>
        </CardContent></Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {trackers.map(t => (
            <Card key={t.id} className="cursor-pointer hover:border-cyan-300 transition-colors" onClick={() => onSelectTracker(t.id)} data-testid={`tracker-card-${t.id}`}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center justify-between">
                  <span className="truncate">{t.name}</span>
                  <Badge variant="secondary" className="text-xs ml-2 shrink-0">{t.row_count || 0} candidates</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">{t.mandate_name || 'No mandate'}</p>
                <p className="text-xs text-muted-foreground mt-1">Created {new Date(t.created_at).toLocaleDateString('en-IN')}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <CreateTrackerWizard
        open={showWizard}
        onClose={() => setShowWizard(false)}
        onCreated={(id) => { loadData(); onSelectTracker(id); }}
      />
    </div>
  );
}


// ── Tracker Spreadsheet View ──
function TrackerSpreadsheetView({ trackerId, onBack }) {
  const [tracker, setTracker] = useState(null);
  const [loading, setLoading] = useState(true);
  const [validation, setValidation] = useState(null);
  const [editCell, setEditCell] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [showAddCandidate, setShowAddCandidate] = useState(false);
  const [saving, setSaving] = useState(false);
  const editRef = useRef(null);

  const loadTracker = useCallback(async () => {
    try {
      const [tr, val] = await Promise.all([
        trackerAPI.getTracker(trackerId),
        trackerAPI.validate(trackerId),
      ]);
      setTracker(tr.data);
      setValidation(val.data);
    } catch { toast.error('Failed to load tracker'); }
    finally { setLoading(false); }
  }, [trackerId]);

  useEffect(() => { loadTracker(); }, [loadTracker]);

  const handleCellSave = async (rowId, key) => {
    if (editCell?.rowId === rowId && editCell?.key === key) {
      setSaving(true);
      try {
        await trackerAPI.updateRow(trackerId, rowId, { data: { [key]: editValue } });
        setTracker(prev => ({
          ...prev,
          rows: prev.rows.map(r => r.id === rowId ? { ...r, data: { ...r.data, [key]: editValue } } : r)
        }));
        // Refresh validation
        trackerAPI.validate(trackerId).then(v => setValidation(v.data));
      } catch { toast.error('Save failed'); }
      finally { setSaving(false); setEditCell(null); }
    }
  };

  const handleStatusChange = async (rowId, newStatus) => {
    try {
      await trackerAPI.updateRowStatus(trackerId, rowId, newStatus);
      setTracker(prev => ({
        ...prev,
        rows: prev.rows.map(r => r.id === rowId ? { ...r, submission_status: newStatus } : r)
      }));
      toast.success('Status updated');
    } catch (e) { toast.error(e.response?.data?.detail || 'Status update failed'); }
  };

  const handleDeleteRow = async (rowId) => {
    try {
      await trackerAPI.deleteRow(trackerId, rowId);
      setTracker(prev => ({ ...prev, rows: prev.rows.filter(r => r.id !== rowId) }));
      toast.success('Row removed');
    } catch { toast.error('Failed to remove'); }
  };

  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);

  const handleDownload = async () => {
    try {
      const res = await trackerAPI.exportExcel(trackerId);
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${tracker?.name || 'tracker'}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Download failed'); }
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await trackerAPI.uploadFile(trackerId, file);
      const d = res.data;
      toast.success(`Imported ${d.imported} rows. ${d.unmapped_headers?.length || 0} unmapped columns.`);
      loadTracker();
      setShowUpload(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally { setUploading(false); e.target.value = ''; }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;
  if (!tracker) return <div className="text-center py-12 text-muted-foreground">Tracker not found</div>;

  const columns = tracker.columns || [];
  const rows = tracker.rows || [];
  const requiredKeys = new Set(columns.filter(c => c.required).map(c => c.key));
  const issueMap = new Set((validation?.issues || []).map(i => `${i.row_id}:${i.field}`));

  const downloadColor = validation?.status === 'green' ? 'bg-green-600 hover:bg-green-700 text-white'
    : validation?.status === 'yellow' ? 'bg-amber-500 hover:bg-amber-600 text-white'
    : 'bg-red-500 hover:bg-red-600 text-white';

  return (
    <div className="space-y-4" data-testid="tracker-spreadsheet-view">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} data-testid="back-to-list">&larr; Back</Button>
          <div>
            <h2 className="text-xl font-bold" data-testid="tracker-name">{tracker.name}</h2>
            <p className="text-xs text-muted-foreground">{tracker.mandate_name} &middot; {rows.length} candidates</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setShowAddCandidate(true)} data-testid="add-candidate-btn"><Plus className="h-4 w-4 mr-1" /> Add Candidate</Button>
          <label className="cursor-pointer">
            <input type="file" accept=".xlsx,.csv" className="hidden" onChange={handleUpload} data-testid="upload-input" />
            <Button size="sm" variant="outline" asChild disabled={uploading} data-testid="upload-btn">
              <span>{uploading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Upload className="h-4 w-4 mr-1" />} Upload</span>
            </Button>
          </label>
          <Button size="sm" className={downloadColor} onClick={handleDownload} data-testid="download-tracker-btn"
            title={validation?.message || ''}>
            {validation?.status === 'green' ? <CheckCircle2 className="h-4 w-4 mr-1" /> : <AlertTriangle className="h-4 w-4 mr-1" />}
            Download
          </Button>
        </div>
      </div>

      {/* Validation Banner */}
      {validation?.status === 'yellow' && (
        <div className="flex items-center gap-2 text-sm bg-amber-50 border border-amber-200 rounded-lg px-4 py-2" data-testid="validation-banner">
          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
          <span className="text-amber-700">{validation.message}</span>
        </div>
      )}

      {/* Spreadsheet Table */}
      <div className="border rounded-lg overflow-auto bg-white" style={{ maxHeight: '65vh' }}>
        <table className="w-full text-sm" data-testid="tracker-table">
          <thead className="bg-slate-50 sticky top-0 z-10">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 border-b w-8">#</th>
              {columns.map(col => (
                <th key={col.key} className="px-3 py-2 text-left text-xs font-semibold text-slate-500 border-b whitespace-nowrap min-w-[120px]">
                  {col.label}
                  {col.required && <span className="text-red-400 ml-0.5">*</span>}
                </th>
              ))}
              <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 border-b min-w-[150px]">Status</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500 border-b w-12"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={columns.length + 3} className="text-center py-10 text-muted-foreground">No candidates yet. Click "Add Candidate" to start.</td></tr>
            ) : rows.map((row, idx) => (
              <tr key={row.id} className="border-b hover:bg-slate-50/50 group" data-testid={`tracker-row-${idx}`}>
                <td className="px-3 py-1.5 text-xs text-muted-foreground">{idx + 1}</td>
                {columns.map(col => {
                  const val = row.data?.[col.key] || '';
                  const isEditing = editCell?.rowId === row.id && editCell?.key === col.key;
                  const hasMissing = issueMap.has(`${row.id}:${col.key}`);
                  return (
                    <td key={col.key}
                      className={`px-1 py-0.5 border-r cursor-text ${hasMissing ? 'bg-red-50' : ''}`}
                      onClick={() => { if (!isEditing) { setEditCell({ rowId: row.id, key: col.key }); setEditValue(String(val)); setTimeout(() => editRef.current?.focus(), 50); } }}
                      title={hasMissing ? `Required: ${col.label}` : ''}
                      data-testid={`cell-${idx}-${col.key}`}
                    >
                      {isEditing ? (
                        <input ref={editRef} className="w-full h-full px-2 py-1 text-sm border-2 border-cyan-400 rounded outline-none bg-white"
                          value={editValue} onChange={e => setEditValue(e.target.value)}
                          onBlur={() => handleCellSave(row.id, col.key)}
                          onKeyDown={e => { if (e.key === 'Enter') handleCellSave(row.id, col.key); if (e.key === 'Escape') setEditCell(null); }}
                        />
                      ) : (
                        <div className="px-2 py-1 text-sm min-h-[28px] truncate max-w-[200px]">
                          {val || (hasMissing ? <span className="text-red-400 text-xs italic">Required</span> : <span className="text-slate-300">&mdash;</span>)}
                        </div>
                      )}
                    </td>
                  );
                })}
                <td className="px-2 py-1">
                  <select className={`text-xs rounded px-2 py-1 border-0 cursor-pointer ${STATUS_MAP[row.submission_status]?.color || 'bg-gray-100'}`}
                    value={row.submission_status} onChange={e => handleStatusChange(row.id, e.target.value)} data-testid={`status-select-${idx}`}>
                    {STATUS_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </td>
                <td className="px-2 py-1 text-center">
                  <button onClick={() => handleDeleteRow(row.id)} className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 transition-opacity" data-testid={`delete-row-${idx}`}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Add Candidate Dialog */}
      <AddCandidateDialog
        open={showAddCandidate}
        onClose={() => setShowAddCandidate(false)}
        trackerId={trackerId}
        mandateId={tracker.mandate_id}
        onAdded={loadTracker}
      />
    </div>
  );
}


// ── Add Candidate Dialog ──
function AddCandidateDialog({ open, onClose, trackerId, mandateId, onAdded }) {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [adding, setAdding] = useState(null);

  useEffect(() => {
    if (!open || !mandateId) return;
    setLoading(true);
    import('../../lib/api').then(({ applicationAPI }) => {
      applicationAPI.getAll({ job_id: mandateId }).then(res => {
        const apps = res.data.applications || res.data || [];
        setApplications(Array.isArray(apps) ? apps : []);
      }).finally(() => setLoading(false));
    });
  }, [open, mandateId]);

  const handleAdd = async (app) => {
    setAdding(app.id);
    try {
      await trackerAPI.addRow(trackerId, {
        candidate_id: app.candidate_id || app.id,
        application_id: app.id,
      });
      toast.success(`${app.candidate_name || 'Candidate'} added to tracker`);
      onAdded();
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to add');
    } finally { setAdding(null); }
  };

  const filtered = applications.filter(a =>
    !search || (a.candidate_name || '').toLowerCase().includes(search.toLowerCase()) ||
    (a.candidate_email || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Plus className="h-5 w-5" /> Add Candidate to Tracker</DialogTitle>
          <DialogDescription>Select from candidates in this mandate's pipeline</DialogDescription>
        </DialogHeader>
        <div className="relative mb-3">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search candidates..." value={search} onChange={e => setSearch(e.target.value)} data-testid="search-candidates" />
        </div>
        <div className="max-h-[300px] overflow-auto space-y-2">
          {loading ? <div className="text-center py-6"><Loader2 className="h-6 w-6 animate-spin mx-auto" /></div> :
            filtered.length === 0 ? <p className="text-sm text-muted-foreground text-center py-6">No candidates found</p> :
            filtered.map(app => (
              <div key={app.id} className="flex items-center justify-between border rounded-lg px-3 py-2 hover:bg-slate-50" data-testid={`candidate-option-${app.id}`}>
                <div className="min-w-0">
                  <p className="font-medium text-sm truncate">{app.candidate_name || 'Unknown'}</p>
                  <p className="text-xs text-muted-foreground">{app.candidate_email || ''} &middot; Stage: {app.stage}</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => handleAdd(app)} disabled={adding === app.id} data-testid={`add-btn-${app.id}`}>
                  {adding === app.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
                </Button>
              </div>
            ))
          }
        </div>
      </DialogContent>
    </Dialog>
  );
}


// ── Main Page ──
export default function SubmissionTrackerPage() {
  const [selectedTracker, setSelectedTracker] = useState(null);

  if (selectedTracker) {
    return <TrackerSpreadsheetView trackerId={selectedTracker} onBack={() => setSelectedTracker(null)} />;
  }
  return <TrackerListView onSelectTracker={setSelectedTracker} />;
}
