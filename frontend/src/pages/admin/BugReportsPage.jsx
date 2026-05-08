import { useState, useEffect, useCallback } from 'react';
import { bugReportsAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { toast } from 'sonner';
import { Bug, AlertTriangle, CheckCircle, Clock, ArrowRight, ExternalLink } from 'lucide-react';

const SEVERITY_STYLES = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-orange-100 text-orange-700 border-orange-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
};

const STATUS_STYLES = {
  open: 'bg-red-50 text-red-600',
  in_progress: 'bg-blue-50 text-blue-600',
  resolved: 'bg-green-50 text-green-600',
  closed: 'bg-slate-100 text-slate-500',
};

export default function BugReportsPage() {
  const [reports, setReports] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState(null);
  const [adminNotes, setAdminNotes] = useState('');
  const [newStatus, setNewStatus] = useState('');

  const load = useCallback(async () => {
    try {
      const [reportsRes, statsRes] = await Promise.all([
        bugReportsAPI.getAll(filter === 'all' ? undefined : filter),
        bugReportsAPI.getStats(),
      ]);
      setReports(reportsRes.data);
      setStats(statsRes.data);
    } catch {
      toast.error('Failed to load bug reports');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const handleUpdate = async () => {
    if (!selected) return;
    try {
      const params = {};
      if (newStatus) params.status = newStatus;
      if (adminNotes) params.admin_notes = adminNotes;
      await bugReportsAPI.update(selected.id, params);
      toast.success('Report updated');
      setSelected(null);
      load();
    } catch {
      toast.error('Update failed');
    }
  };

  const formatDate = (ts) => {
    if (!ts) return '—';
    return new Date(ts).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' });
  };

  return (
    <div className="space-y-6" data-testid="bug-reports-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Bug Reports</h1>
        <p className="text-slate-500 mt-1">Review and manage user-reported issues</p>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-slate-700">{stats.total}</p>
            <p className="text-xs text-slate-500">Total</p>
          </CardContent></Card>
          <Card className="border-red-200"><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-red-600">{stats.open}</p>
            <p className="text-xs text-slate-500">Open</p>
          </CardContent></Card>
          <Card className="border-blue-200"><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-blue-600">{stats.in_progress}</p>
            <p className="text-xs text-slate-500">In Progress</p>
          </CardContent></Card>
          <Card className="border-green-200"><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-green-600">{stats.resolved}</p>
            <p className="text-xs text-slate-500">Resolved</p>
          </CardContent></Card>
          <Card><CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-amber-600">{stats.critical_open + stats.high_open}</p>
            <p className="text-xs text-slate-500">Critical/High Open</p>
          </CardContent></Card>
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-3">
        <Label className="text-sm text-slate-600">Filter:</Label>
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-40" data-testid="bug-filter-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="closed">Closed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Reports list */}
      {loading ? (
        <div className="text-center py-16 text-slate-400">Loading...</div>
      ) : reports.length === 0 ? (
        <Card><CardContent className="py-16 text-center">
          <CheckCircle className="w-12 h-12 text-green-300 mx-auto mb-3" />
          <p className="text-slate-500">No bug reports found</p>
        </CardContent></Card>
      ) : (
        <div className="space-y-3" data-testid="bug-reports-list">
          {reports.map((r) => (
            <Card key={r.id} className="hover:shadow-sm transition-shadow cursor-pointer"
              onClick={() => { setSelected(r); setAdminNotes(r.admin_notes || ''); setNewStatus(r.status); }}
              data-testid={`bug-report-${r.id}`}>
              <CardContent className="py-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="mt-1">
                      {r.severity === 'critical' || r.severity === 'high'
                        ? <AlertTriangle className="w-5 h-5 text-red-500" />
                        : <Bug className="w-5 h-5 text-slate-400" />}
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium text-slate-900">{r.title}</p>
                      <p className="text-sm text-slate-500 line-clamp-1 mt-0.5">{r.description}</p>
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium border ${SEVERITY_STYLES[r.severity]}`}>{r.severity}</span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[r.status]}`}>{r.status.replace('_', ' ')}</span>
                        <span className="text-xs text-slate-400">{r.category}</span>
                        <span className="text-xs text-slate-400">by {r.reported_by_name} ({r.reported_by_role})</span>
                        <span className="text-xs text-slate-400">{formatDate(r.created_at)}</span>
                      </div>
                    </div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-300 shrink-0 mt-2" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Detail/Update Dialog */}
      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-w-lg" data-testid="bug-detail-dialog">
          <DialogHeader><DialogTitle className="font-heading">Bug Report Detail</DialogTitle></DialogHeader>
          {selected && (
            <div className="space-y-4">
              <div>
                <h3 className="font-semibold text-lg">{selected.title}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium border ${SEVERITY_STYLES[selected.severity]}`}>{selected.severity}</span>
                  <span className="text-xs text-slate-500">{selected.category} | {selected.reported_by_name} ({selected.reported_by_role})</span>
                </div>
              </div>
              <div className="bg-slate-50 p-3 rounded-lg text-sm text-slate-700">{selected.description}</div>
              {selected.page_url && (
                <p className="text-xs text-slate-400 flex items-center gap-1">
                  <ExternalLink className="w-3 h-3" /> {selected.page_url}
                </p>
              )}
              <div className="space-y-2">
                <Label>Status</Label>
                <Select value={newStatus} onValueChange={setNewStatus}>
                  <SelectTrigger data-testid="update-status-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Admin Notes</Label>
                <Textarea value={adminNotes} onChange={(e) => setAdminNotes(e.target.value)}
                  placeholder="Add investigation notes, fix details..." rows={3} data-testid="admin-notes-input" />
              </div>
              <div className="flex gap-3 pt-2">
                <Button variant="outline" className="flex-1" onClick={() => setSelected(null)}>Cancel</Button>
                <Button className="flex-1 bg-[#7CB342] hover:bg-[#689F38]" onClick={handleUpdate}
                  data-testid="update-report-btn">Update Report</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
