import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { Mail, Phone, Building2, Clock, Trash2, Eye, Filter } from 'lucide-react';
import { contactAPI } from '../../lib/api';

const STATUS_COLORS = {
  new: 'bg-blue-100 text-blue-700',
  reviewed: 'bg-amber-100 text-amber-700',
  contacted: 'bg-green-100 text-green-700',
  closed: 'bg-slate-100 text-slate-500',
};

export default function ContactSubmissionsPage() {
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('all');
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const params = filterStatus !== 'all' ? filterStatus : undefined;
      const res = await contactAPI.getAll(params);
      setSubmissions(res.data.submissions || []);
    } catch {
      toast.error('Failed to load submissions');
    } finally {
      setLoading(false);
    }
  }, [filterStatus]);

  useEffect(() => { load(); }, [load]);

  const updateStatus = async (id, status) => {
    try {
      await contactAPI.updateStatus(id, status);
      toast.success(`Status updated to ${status}`);
      load();
      if (selected?.id === id) setSelected(prev => ({ ...prev, status }));
    } catch {
      toast.error('Failed to update status');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this submission?')) return;
    try {
      await contactAPI.delete(id);
      toast.success('Submission deleted');
      load();
      if (selected?.id === id) setSelected(null);
    } catch {
      toast.error('Failed to delete');
    }
  };

  const formatDate = (d) => d ? new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }) : '-';

  const serviceLabels = {
    'executive-search': 'Executive Search',
    'specialist-hiring': 'Specialist Hiring',
    'people-advisory': 'People Advisory',
    'diversity-hiring': 'Diversity Hiring',
    'global-hiring': 'Global Hiring',
    'other': 'Other Inquiry',
  };

  const newCount = submissions.filter(s => s.status === 'new').length;

  return (
    <div className="space-y-6" data-testid="contact-submissions-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Contact Submissions</h1>
          <p className="text-slate-500 mt-1">Inquiries from the public website contact form{newCount > 0 && <span className="ml-2 text-blue-600 font-medium">({newCount} new)</span>}</p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400" />
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-40" data-testid="status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="new">New</SelectItem>
              <SelectItem value="reviewed">Reviewed</SelectItem>
              <SelectItem value="contacted">Contacted</SelectItem>
              <SelectItem value="closed">Closed</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 text-slate-400">Loading submissions...</div>
      ) : submissions.length === 0 ? (
        <Card><CardContent className="py-16 text-center text-slate-400">No contact submissions yet.</CardContent></Card>
      ) : (
        <div className="grid gap-4">
          {submissions.map((s) => (
            <Card key={s.id} className="border-slate-200 hover:shadow-md transition-shadow" data-testid={`submission-${s.id}`}>
              <CardContent className="p-4 sm:p-5">
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h3 className="font-semibold text-slate-900">{s.full_name}</h3>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[s.status] || STATUS_COLORS.new}`} data-testid={`status-badge-${s.id}`}>
                        {s.status}
                      </span>
                      <span className="text-xs text-slate-400 bg-slate-50 px-2 py-0.5 rounded">
                        {serviceLabels[s.service_interest] || s.service_interest}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 mt-2 text-sm text-slate-500 flex-wrap">
                      <span className="flex items-center gap-1"><Mail className="w-3.5 h-3.5" />{s.email}</span>
                      {s.phone && <span className="flex items-center gap-1"><Phone className="w-3.5 h-3.5" />{s.phone}</span>}
                      {s.company_name && <span className="flex items-center gap-1"><Building2 className="w-3.5 h-3.5" />{s.company_name}</span>}
                    </div>
                    <p className="mt-2 text-sm text-slate-600 line-clamp-2">{s.message}</p>
                    <p className="mt-2 text-xs text-slate-400 flex items-center gap-1"><Clock className="w-3 h-3" />{formatDate(s.submitted_at)}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button variant="outline" size="sm" onClick={() => setSelected(s)} data-testid={`view-btn-${s.id}`}>
                      <Eye className="w-3.5 h-3.5 mr-1" />View
                    </Button>
                    <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-700 hover:bg-red-50"
                      onClick={() => handleDelete(s.id)} data-testid={`delete-btn-${s.id}`}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading">Submission Details</DialogTitle></DialogHeader>
          {selected && (
            <div className="space-y-4" data-testid="submission-detail-dialog">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div><p className="text-slate-400 text-xs">Name</p><p className="font-medium">{selected.full_name}</p></div>
                <div><p className="text-slate-400 text-xs">Email</p><p className="font-medium">{selected.email}</p></div>
                <div><p className="text-slate-400 text-xs">Phone</p><p className="font-medium">{selected.phone || '-'}</p></div>
                <div><p className="text-slate-400 text-xs">Company</p><p className="font-medium">{selected.company_name || '-'}</p></div>
                <div><p className="text-slate-400 text-xs">Service</p><p className="font-medium">{serviceLabels[selected.service_interest] || selected.service_interest}</p></div>
                <div><p className="text-slate-400 text-xs">Submitted</p><p className="font-medium">{formatDate(selected.submitted_at)}</p></div>
              </div>
              <div>
                <p className="text-slate-400 text-xs mb-1">Message</p>
                <div className="bg-slate-50 p-3 rounded-lg text-sm text-slate-700 whitespace-pre-wrap">{selected.message}</div>
              </div>
              <div>
                <p className="text-slate-400 text-xs mb-2">Update Status</p>
                <div className="flex gap-2 flex-wrap">
                  {['new', 'reviewed', 'contacted', 'closed'].map(st => (
                    <Button key={st} size="sm" variant={selected.status === st ? 'default' : 'outline'}
                      className={selected.status === st ? 'bg-[#7CB342] hover:bg-[#689F38]' : ''}
                      onClick={() => updateStatus(selected.id, st)} data-testid={`set-status-${st}`}>
                      {st.charAt(0).toUpperCase() + st.slice(1)}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
