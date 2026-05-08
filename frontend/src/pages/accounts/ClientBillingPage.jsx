import { useState, useEffect, useCallback } from 'react';
import { financeAPI } from '../../lib/api';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { Plus, Search, Building2, Mail, Phone, MapPin, IndianRupee, Edit2, Trash2, Loader2 } from 'lucide-react';

const fmt = (n) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n || 0);

export default function ClientBillingPage() {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editClient, setEditClient] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: '', contact_person: '', email: '', phone: '', address: '', gst_number: '', payment_terms: 'Net 30', billing_cycle: 'Monthly' });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await financeAPI.listClients({ search: search || undefined, limit: 100 });
      setClients(res.data.clients || []);
    } catch { toast.error('Failed to load clients'); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [load]);

  const openEdit = (c) => {
    setForm({ name: c.name, contact_person: c.contact_person || '', email: c.email || '', phone: c.phone || '', address: c.address || '', gst_number: c.gst_number || '', payment_terms: c.payment_terms || 'Net 30', billing_cycle: c.billing_cycle || 'Monthly' });
    setEditClient(c);
    setShowForm(true);
  };

  const openCreate = () => {
    setForm({ name: '', contact_person: '', email: '', phone: '', address: '', gst_number: '', payment_terms: 'Net 30', billing_cycle: 'Monthly' });
    setEditClient(null);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.name) return toast.error('Client name is required');
    setSaving(true);
    try {
      if (editClient) {
        await financeAPI.updateClient(editClient.id, form);
        toast.success('Client updated');
      } else {
        await financeAPI.createClient(form);
        toast.success('Client created');
      }
      setShowForm(false);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this client?')) return;
    try {
      await financeAPI.deleteClient(id);
      toast.success('Client deleted');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Cannot delete — client has invoices'); }
  };

  return (
    <div className="space-y-4 p-4 sm:p-6" data-testid="client-billing-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Client Billing</h1>
          <p className="text-sm text-slate-500">Manage clients, payment terms & billing cycles</p>
        </div>
        <Button size="sm" onClick={openCreate} className="bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="add-client-btn">
          <Plus className="w-4 h-4 mr-1" />Add Client
        </Button>
      </div>

      <div className="relative w-full sm:w-72">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
        <Input placeholder="Search clients..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 h-9" data-testid="search-clients" />
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : clients.length === 0 ? (
        <Card className="border-slate-200"><CardContent className="py-12 text-center text-slate-400">
          <Building2 className="w-10 h-10 mx-auto mb-3 text-slate-300" /><p>No clients yet. Add your first client.</p>
        </CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((c) => (
            <Card key={c.id} className="border-slate-200 hover:shadow-md transition-shadow" data-testid={`client-card-${c.id}`}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                      <Building2 className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-slate-800">{c.name}</h3>
                      {c.contact_person && <p className="text-xs text-slate-500">{c.contact_person}</p>}
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" onClick={() => openEdit(c)} data-testid={`edit-client-${c.id}`}><Edit2 className="w-3.5 h-3.5" /></Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(c.id)}><Trash2 className="w-3.5 h-3.5 text-red-500" /></Button>
                  </div>
                </div>
                <div className="mt-3 space-y-1.5 text-sm">
                  {c.email && <p className="flex items-center gap-2 text-slate-500"><Mail className="w-3 h-3" />{c.email}</p>}
                  {c.phone && <p className="flex items-center gap-2 text-slate-500"><Phone className="w-3 h-3" />{c.phone}</p>}
                  {c.address && <p className="flex items-center gap-2 text-slate-500"><MapPin className="w-3 h-3" />{c.address}</p>}
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                  <Badge variant="secondary" className="text-xs">{c.payment_terms || 'Net 30'}</Badge>
                  <Badge variant="secondary" className="text-xs">{c.billing_cycle || 'Monthly'}</Badge>
                  {c.gst_number && <Badge variant="outline" className="text-xs">GST: {c.gst_number}</Badge>}
                </div>
                {c.outstanding_balance > 0 && (
                  <div className="mt-3 pt-3 border-t flex items-center justify-between">
                    <span className="text-xs text-slate-500">Outstanding</span>
                    <span className="text-sm font-bold text-amber-600"><IndianRupee className="w-3 h-3 inline" />{fmt(c.outstanding_balance)}</span>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Client Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editClient ? 'Edit' : 'Add'} Client</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Company Name *</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="client-name" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Contact Person</Label><Input value={form.contact_person} onChange={(e) => setForm({ ...form, contact_person: e.target.value })} /></div>
              <div><Label>Email</Label><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
              <div><Label>GST Number</Label><Input value={form.gst_number} onChange={(e) => setForm({ ...form, gst_number: e.target.value })} /></div>
            </div>
            <div><Label>Address</Label><Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Payment Terms</Label>
                <Select value={form.payment_terms} onValueChange={(v) => setForm({ ...form, payment_terms: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['Net 15', 'Net 30', 'Net 45', 'Net 60', 'Due on Receipt', 'Advance'].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Billing Cycle</Label>
                <Select value={form.billing_cycle} onValueChange={(v) => setForm({ ...form, billing_cycle: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['Monthly', 'Quarterly', 'Bi-Annual', 'Annual', 'On Demand'].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="save-client-btn">
              {saving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}{editClient ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
