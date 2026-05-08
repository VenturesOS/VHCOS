import { useState, useEffect, useCallback } from 'react';
import { candidateBankAPI } from '../../lib/api';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Label } from '../ui/label';
import { toast } from 'sonner';
import { AlertTriangle, RotateCcw, Trash2, Loader2, User, Mail, Phone, MapPin, Briefcase, Building2, ChevronLeft, ChevronRight, ExternalLink, Save, Sparkles, Eye } from 'lucide-react';

export function FailedCapturesTab() {
  const [captures, setCaptures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [unrecovered, setUnrecovered] = useState(0);
  const [showFilter, setShowFilter] = useState('unrecovered');
  const [selectedIds, setSelectedIds] = useState([]);
  const [editCapture, setEditCapture] = useState(null);
  const [editData, setEditData] = useState({});
  const [saving, setSaving] = useState(false);
  const [classifying, setClassifying] = useState(false);
  const [detailCapture, setDetailCapture] = useState(null);

  const loadCaptures = useCallback(async () => {
    setLoading(true);
    try {
      const res = await candidateBankAPI.getFailedCaptures({ page, limit: 20, show: showFilter });
      setCaptures(res.data.logs || []);
      setTotal(res.data.total || 0);
      setTotalPages(res.data.pages || 1);
      setUnrecovered(res.data.unrecovered || 0);
    } catch (err) {
      toast.error('Failed to load captures');
    } finally {
      setLoading(false);
    }
  }, [page, showFilter]);

  useEffect(() => { loadCaptures(); }, [loadCaptures]);

  const handleSaveToBank = async () => {
    if (!editCapture) return;
    setSaving(true);
    try {
      const res = await candidateBankAPI.saveFailedCapture(editCapture.id, editData);
      toast.success(res.data.message || 'Saved to candidate bank');
      setEditCapture(null);
      loadCaptures();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleBulkDismiss = async () => {
    if (!selectedIds.length) return;
    try {
      const res = await candidateBankAPI.bulkDismissCaptures(selectedIds);
      toast.success(`Dismissed ${res.data.dismissed} captures`);
      setSelectedIds([]);
      loadCaptures();
    } catch {
      toast.error('Failed to dismiss');
    }
  };

  const handleAutoClassify = async () => {
    setClassifying(true);
    try {
      const res = await candidateBankAPI.autoClassifyCaptures(true);
      toast.success(`Classified: ${res.data.classified}, Auto-dismissed: ${res.data.auto_dismissed}`);
      loadCaptures();
    } catch {
      toast.error('Classification failed');
    } finally {
      setClassifying(false);
    }
  };

  const openEdit = (capture) => {
    const raw = capture.raw_data || capture.data || {};
    setEditData({
      name: raw.name || capture.candidate_name || '',
      email: raw.email || capture.email || '',
      phone: raw.phone || '',
      designation: raw.designation || raw.title || '',
      current_employer: raw.current_employer || raw.company || '',
      location: raw.location || '',
      skills: Array.isArray(raw.skills) ? raw.skills.join(', ') : (raw.skills || ''),
      experience_years: raw.experience_years || '',
      industry: raw.industry || '',
      profile_url: raw.profile_url || capture.profile_url || '',
    });
    setEditCapture(capture);
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const toggleAll = () => {
    if (selectedIds.length === captures.length) setSelectedIds([]);
    else setSelectedIds(captures.map(c => c.id));
  };

  return (
    <div className="space-y-4" data-testid="failed-captures-tab">
      {/* Header stats */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="text-amber-600 border-amber-200 bg-amber-50 px-3 py-1" data-testid="unrecovered-count">
            <AlertTriangle className="w-3.5 h-3.5 mr-1.5" />
            {unrecovered} unrecovered
          </Badge>
          <div className="flex gap-1 bg-slate-100 rounded-md p-0.5">
            {['unrecovered', 'recovered', 'all'].map(f => (
              <button key={f} onClick={() => { setShowFilter(f); setPage(1); }}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${showFilter === f ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}
                data-testid={`filter-${f}`}>
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          {selectedIds.length > 0 && (
            <Button variant="outline" size="sm" onClick={handleBulkDismiss} className="text-red-600 border-red-200 hover:bg-red-50" data-testid="bulk-dismiss-btn">
              <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Dismiss ({selectedIds.length})
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleAutoClassify} disabled={classifying} data-testid="auto-classify-btn">
            {classifying ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5 mr-1.5" />}
            Auto-Classify
          </Button>
        </div>
      </div>

      {/* Captures list */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : captures.length === 0 ? (
        <Card className="border-slate-200">
          <CardContent className="py-12 text-center text-slate-500">
            <AlertTriangle className="w-10 h-10 mx-auto mb-3 text-slate-300" />
            <p>No {showFilter === 'all' ? '' : showFilter} failed captures found.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="border-slate-200">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="captures-table">
                <thead>
                  <tr className="border-b bg-slate-50">
                    <th className="p-3 text-left w-8">
                      <input type="checkbox" checked={selectedIds.length === captures.length && captures.length > 0}
                        onChange={toggleAll} className="rounded" />
                    </th>
                    <th className="p-3 text-left font-medium text-slate-600">Candidate / Data</th>
                    <th className="p-3 text-left font-medium text-slate-600">Error Reason</th>
                    <th className="p-3 text-left font-medium text-slate-600">Timestamp</th>
                    <th className="p-3 text-left font-medium text-slate-600">Status</th>
                    <th className="p-3 text-right font-medium text-slate-600">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {captures.map(cap => {
                    const raw = cap.raw_data || cap.data || {};
                    const name = raw.name || cap.candidate_name || 'Unknown';
                    const email = raw.email || cap.email || '';
                    return (
                      <tr key={cap.id} className={`border-b hover:bg-slate-50 transition-colors ${selectedIds.includes(cap.id) ? 'bg-blue-50/50' : ''}`}
                        data-testid={`capture-row-${cap.id}`}>
                        <td className="p-3">
                          <input type="checkbox" checked={selectedIds.includes(cap.id)} onChange={() => toggleSelect(cap.id)} className="rounded" />
                        </td>
                        <td className="p-3">
                          <div className="font-medium text-slate-800">{name}</div>
                          {email && <div className="text-xs text-slate-500">{email}</div>}
                          {raw.designation && <div className="text-xs text-slate-400">{raw.designation}</div>}
                        </td>
                        <td className="p-3">
                          <span className="text-xs text-red-600 bg-red-50 px-2 py-0.5 rounded">{cap.error || cap.failure_reason || 'Unknown error'}</span>
                        </td>
                        <td className="p-3 text-xs text-slate-500">
                          {cap.timestamp ? new Date(cap.timestamp).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }) : '-'}
                        </td>
                        <td className="p-3">
                          {cap.is_recovered ? (
                            <Badge variant="secondary" className="text-xs bg-green-50 text-green-700">Recovered</Badge>
                          ) : (
                            <Badge variant="secondary" className="text-xs bg-amber-50 text-amber-700">Pending</Badge>
                          )}
                        </td>
                        <td className="p-3 text-right">
                          <div className="flex gap-1.5 justify-end">
                            <Button variant="ghost" size="sm" onClick={() => setDetailCapture(cap)} data-testid={`view-capture-${cap.id}`}>
                              <Eye className="w-3.5 h-3.5" />
                            </Button>
                            {!cap.is_recovered && (
                              <Button variant="outline" size="sm" onClick={() => openEdit(cap)} data-testid={`recover-capture-${cap.id}`}>
                                <RotateCcw className="w-3.5 h-3.5 mr-1" /> Recover
                              </Button>
                            )}
                            {(raw.profile_url || cap.profile_url) && (
                              <Button variant="ghost" size="sm" asChild>
                                <a href={raw.profile_url || cap.profile_url} target="_blank" rel="noopener noreferrer">
                                  <ExternalLink className="w-3.5 h-3.5" />
                                </a>
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-500">Showing {((page - 1) * 20) + 1}-{Math.min(page * 20, total)} of {total}</span>
            <div className="flex gap-1">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)} data-testid="prev-page-btn">
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="px-3 py-1 text-sm text-slate-600">Page {page}/{totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} data-testid="next-page-btn">
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </>
      )}

      {/* Detail View Dialog */}
      <Dialog open={!!detailCapture} onOpenChange={() => setDetailCapture(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Capture Details</DialogTitle>
          </DialogHeader>
          {detailCapture && (
            <div className="space-y-3 text-sm">
              <div className="bg-slate-50 rounded-lg p-4">
                <h4 className="font-medium text-slate-700 mb-2">Raw Captured Data</h4>
                <pre className="text-xs text-slate-600 whitespace-pre-wrap break-all max-h-60 overflow-y-auto bg-white p-3 rounded border">
                  {JSON.stringify(detailCapture.raw_data || detailCapture.data || detailCapture, null, 2)}
                </pre>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><span className="text-slate-500">Error:</span> <span className="text-red-600">{detailCapture.error || detailCapture.failure_reason || '-'}</span></div>
                <div><span className="text-slate-500">Timestamp:</span> {detailCapture.timestamp || '-'}</div>
                <div><span className="text-slate-500">Source URL:</span> {detailCapture.source_url || detailCapture.profile_url || '-'}</div>
                <div><span className="text-slate-500">Status:</span> {detailCapture.is_recovered ? 'Recovered' : 'Pending'}</div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit & Save Dialog */}
      <Dialog open={!!editCapture} onOpenChange={() => setEditCapture(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Recover Failed Capture</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs flex items-center gap-1"><User className="w-3 h-3" /> Name *</Label>
              <Input value={editData.name || ''} onChange={(e) => setEditData(d => ({ ...d, name: e.target.value }))}
                placeholder="Full Name" data-testid="edit-name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs flex items-center gap-1"><Mail className="w-3 h-3" /> Email</Label>
                <Input value={editData.email || ''} onChange={(e) => setEditData(d => ({ ...d, email: e.target.value }))}
                  placeholder="email@example.com" data-testid="edit-email" />
              </div>
              <div>
                <Label className="text-xs flex items-center gap-1"><Phone className="w-3 h-3" /> Phone</Label>
                <Input value={editData.phone || ''} onChange={(e) => setEditData(d => ({ ...d, phone: e.target.value }))}
                  placeholder="+91 9876543210" data-testid="edit-phone" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs flex items-center gap-1"><Briefcase className="w-3 h-3" /> Designation</Label>
                <Input value={editData.designation || ''} onChange={(e) => setEditData(d => ({ ...d, designation: e.target.value }))}
                  placeholder="Software Engineer" data-testid="edit-designation" />
              </div>
              <div>
                <Label className="text-xs flex items-center gap-1"><Building2 className="w-3 h-3" /> Company</Label>
                <Input value={editData.current_employer || ''} onChange={(e) => setEditData(d => ({ ...d, current_employer: e.target.value }))}
                  placeholder="Company name" data-testid="edit-company" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs flex items-center gap-1"><MapPin className="w-3 h-3" /> Location</Label>
                <Input value={editData.location || ''} onChange={(e) => setEditData(d => ({ ...d, location: e.target.value }))}
                  placeholder="City" data-testid="edit-location" />
              </div>
              <div>
                <Label className="text-xs">Experience (years)</Label>
                <Input type="number" value={editData.experience_years || ''} onChange={(e) => setEditData(d => ({ ...d, experience_years: e.target.value }))}
                  placeholder="5" data-testid="edit-experience" />
              </div>
            </div>
            <div>
              <Label className="text-xs">Skills (comma-separated)</Label>
              <Input value={editData.skills || ''} onChange={(e) => setEditData(d => ({ ...d, skills: e.target.value }))}
                placeholder="Python, Java, React" data-testid="edit-skills" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditCapture(null)}>Cancel</Button>
            <Button onClick={handleSaveToBank} disabled={saving} className="bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="save-to-bank-btn">
              {saving ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Save className="w-4 h-4 mr-1.5" />}
              Save to Bank
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
