import { useState, useEffect, useCallback } from 'react';
import { financeAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { toast } from 'sonner';
import { Plus, FileText, Send, CheckCircle, Trash2, Loader2, Download, Eye, IndianRupee } from 'lucide-react';

const fmt = (n) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n || 0);

const STATUS_COLORS = {
  draft: 'bg-slate-100 text-slate-600',
  sent: 'bg-blue-50 text-blue-600',
  paid: 'bg-green-50 text-green-600',
  overdue: 'bg-red-50 text-red-600',
};

export default function InvoicePage() {
  const [invoices, setInvoices] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [viewInvoice, setViewInvoice] = useState(null);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    client_id: '', items: [{ description: '', quantity: 1, rate: 0, amount: 0 }],
    gst_percent: 18, due_date: '', notes: '',
  });

  const loadInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit: 20 };
      if (statusFilter) params.status = statusFilter;
      const res = await financeAPI.listInvoices(params);
      setInvoices(res.data.invoices || []);
      setTotal(res.data.total || 0);
      setPages(res.data.pages || 1);
    } catch { toast.error('Failed to load invoices'); }
    finally { setLoading(false); }
  }, [page, statusFilter]);

  const loadClients = useCallback(async () => {
    try {
      const res = await financeAPI.listClients({ limit: 100 });
      setClients(res.data.clients || []);
    } catch {}
  }, []);

  useEffect(() => { loadInvoices(); }, [loadInvoices]);
  useEffect(() => { loadClients(); }, [loadClients]);

  const updateItem = (idx, field, value) => {
    const items = [...form.items];
    items[idx] = { ...items[idx], [field]: value };
    if (field === 'quantity' || field === 'rate') {
      items[idx].amount = (parseFloat(items[idx].quantity) || 0) * (parseFloat(items[idx].rate) || 0);
    }
    setForm({ ...form, items });
  };

  const addItem = () => setForm({ ...form, items: [...form.items, { description: '', quantity: 1, rate: 0, amount: 0 }] });
  const removeItem = (idx) => setForm({ ...form, items: form.items.filter((_, i) => i !== idx) });

  const subtotal = form.items.reduce((sum, i) => sum + (i.amount || 0), 0);
  const gstAmount = subtotal * (form.gst_percent / 100);
  const invoiceTotal = subtotal + gstAmount;

  const handleCreate = async () => {
    if (!form.client_id) return toast.error('Select a client');
    if (!form.due_date) return toast.error('Set a due date');
    if (form.items.some(i => !i.description)) return toast.error('All items need descriptions');
    setSaving(true);
    try {
      await financeAPI.createInvoice({
        client_id: form.client_id, items: form.items,
        subtotal, gst_percent: form.gst_percent, gst_amount: gstAmount,
        total: invoiceTotal, due_date: form.due_date, notes: form.notes,
      });
      toast.success('Invoice created');
      setShowCreate(false);
      setForm({ client_id: '', items: [{ description: '', quantity: 1, rate: 0, amount: 0 }], gst_percent: 18, due_date: '', notes: '' });
      loadInvoices();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const handleAction = async (id, action) => {
    try {
      if (action === 'send') await financeAPI.sendInvoice(id);
      else if (action === 'paid') await financeAPI.markPaid(id);
      else if (action === 'delete') { await financeAPI.deleteInvoice(id); }
      toast.success(`Invoice ${action === 'delete' ? 'deleted' : action === 'send' ? 'sent' : 'marked paid'}`);
      loadInvoices();
    } catch { toast.error('Action failed'); }
  };

  const downloadCSV = async () => {
    try {
      const res = await financeAPI.exportInvoices({ status: statusFilter || undefined });
      const rows = res.data.rows;
      if (!rows?.length) return toast.info('No data to export');
      const headers = Object.keys(rows[0]);
      const csv = [headers.join(','), ...rows.map(r => headers.map(h => `"${r[h] || ''}"`).join(','))].join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = res.data.filename || 'invoices.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Export failed'); }
  };

  return (
    <div className="space-y-4 p-4 sm:p-6" data-testid="invoice-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Invoices</h1>
          <p className="text-sm text-slate-500">{total} total invoices</p>
        </div>
        <div className="flex gap-2">
          <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v === 'all' ? '' : v); setPage(1); }}>
            <SelectTrigger className="w-32 h-9" data-testid="status-filter"><SelectValue placeholder="All Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="sent">Sent</SelectItem>
              <SelectItem value="paid">Paid</SelectItem>
              <SelectItem value="overdue">Overdue</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={downloadCSV} data-testid="export-csv-btn"><Download className="w-4 h-4 mr-1" />Export</Button>
          <Button size="sm" onClick={() => setShowCreate(true)} className="bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="create-invoice-btn">
            <Plus className="w-4 h-4 mr-1" />New Invoice
          </Button>
        </div>
      </div>

      <Card className="border-slate-200">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="invoices-table">
            <thead>
              <tr className="border-b bg-slate-50">
                <th className="p-3 text-left font-medium text-slate-600">Invoice #</th>
                <th className="p-3 text-left font-medium text-slate-600">Client</th>
                <th className="p-3 text-right font-medium text-slate-600">Amount</th>
                <th className="p-3 text-left font-medium text-slate-600">Due Date</th>
                <th className="p-3 text-left font-medium text-slate-600">Status</th>
                <th className="p-3 text-right font-medium text-slate-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="p-8 text-center"><Loader2 className="w-5 h-5 animate-spin mx-auto text-slate-400" /></td></tr>
              ) : invoices.length === 0 ? (
                <tr><td colSpan={6} className="p-8 text-center text-slate-400">No invoices found. Create your first invoice.</td></tr>
              ) : invoices.map((inv) => (
                <tr key={inv.id} className="border-b hover:bg-slate-50" data-testid={`invoice-row-${inv.id}`}>
                  <td className="p-3 font-medium text-slate-800">{inv.invoice_number}</td>
                  <td className="p-3 text-slate-600">{inv.client_name}</td>
                  <td className="p-3 text-right font-medium text-slate-800"><IndianRupee className="w-3 h-3 inline" />{fmt(inv.total)}</td>
                  <td className="p-3 text-slate-500">{inv.due_date}</td>
                  <td className="p-3"><Badge className={`text-xs ${STATUS_COLORS[inv.status] || ''}`}>{inv.status}</Badge></td>
                  <td className="p-3 text-right">
                    <div className="flex gap-1 justify-end">
                      <Button variant="ghost" size="sm" onClick={() => setViewInvoice(inv)}><Eye className="w-3.5 h-3.5" /></Button>
                      {inv.status === 'draft' && <Button variant="ghost" size="sm" onClick={() => handleAction(inv.id, 'send')}><Send className="w-3.5 h-3.5 text-blue-600" /></Button>}
                      {(inv.status === 'sent' || inv.status === 'overdue') && <Button variant="ghost" size="sm" onClick={() => handleAction(inv.id, 'paid')}><CheckCircle className="w-3.5 h-3.5 text-green-600" /></Button>}
                      {inv.status === 'draft' && <Button variant="ghost" size="sm" onClick={() => handleAction(inv.id, 'delete')}><Trash2 className="w-3.5 h-3.5 text-red-500" /></Button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {pages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-500">Page {page} of {pages}</span>
          <div className="flex gap-1">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
            <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {/* View Invoice Dialog */}
      <Dialog open={!!viewInvoice} onOpenChange={() => setViewInvoice(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Invoice {viewInvoice?.invoice_number}</DialogTitle></DialogHeader>
          {viewInvoice && (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div><span className="text-slate-500">Client:</span> <span className="font-medium">{viewInvoice.client_name}</span></div>
                <div><span className="text-slate-500">Status:</span> <Badge className={`text-xs ${STATUS_COLORS[viewInvoice.status]}`}>{viewInvoice.status}</Badge></div>
                <div><span className="text-slate-500">Due:</span> {viewInvoice.due_date}</div>
                <div><span className="text-slate-500">Created:</span> {viewInvoice.created_at?.slice(0, 10)}</div>
              </div>
              <table className="w-full text-sm border">
                <thead><tr className="bg-slate-50"><th className="p-2 text-left">Item</th><th className="p-2 text-right">Qty</th><th className="p-2 text-right">Rate</th><th className="p-2 text-right">Amount</th></tr></thead>
                <tbody>
                  {(viewInvoice.items || []).map((item, i) => (
                    <tr key={i} className="border-t"><td className="p-2">{item.description}</td><td className="p-2 text-right">{item.quantity}</td><td className="p-2 text-right">{fmt(item.rate)}</td><td className="p-2 text-right">{fmt(item.amount)}</td></tr>
                  ))}
                </tbody>
              </table>
              <div className="text-right space-y-1">
                <p>Subtotal: <span className="font-medium">{fmt(viewInvoice.subtotal)}</span></p>
                <p>GST ({viewInvoice.gst_percent}%): <span className="font-medium">{fmt(viewInvoice.gst_amount)}</span></p>
                <p className="text-lg font-bold">Total: <IndianRupee className="w-4 h-4 inline" />{fmt(viewInvoice.total)}</p>
              </div>
              {viewInvoice.notes && <p className="text-slate-500 italic">{viewInvoice.notes}</p>}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Create Invoice Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Create Invoice</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Client *</Label>
                <Select value={form.client_id} onValueChange={(v) => setForm({ ...form, client_id: v })}>
                  <SelectTrigger data-testid="select-client"><SelectValue placeholder="Select client..." /></SelectTrigger>
                  <SelectContent>{clients.map(c => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>Due Date *</Label>
                <Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} data-testid="due-date" />
              </div>
            </div>

            <div>
              <Label>Line Items</Label>
              <div className="space-y-2 mt-1">
                {form.items.map((item, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                    <Input className="col-span-5" placeholder="Description" value={item.description} onChange={(e) => updateItem(idx, 'description', e.target.value)} data-testid={`item-desc-${idx}`} />
                    <Input className="col-span-2" type="number" placeholder="Qty" value={item.quantity} onChange={(e) => updateItem(idx, 'quantity', e.target.value)} />
                    <Input className="col-span-2" type="number" placeholder="Rate" value={item.rate} onChange={(e) => updateItem(idx, 'rate', e.target.value)} />
                    <span className="col-span-2 text-right text-sm font-medium">{fmt(item.amount)}</span>
                    {form.items.length > 1 && <Button variant="ghost" size="sm" className="col-span-1" onClick={() => removeItem(idx)}><Trash2 className="w-3 h-3 text-red-500" /></Button>}
                  </div>
                ))}
                <Button variant="outline" size="sm" onClick={addItem}><Plus className="w-3 h-3 mr-1" />Add Item</Button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div><Label>GST %</Label><Input type="number" value={form.gst_percent} onChange={(e) => setForm({ ...form, gst_percent: parseFloat(e.target.value) || 0 })} /></div>
              <div className="text-right space-y-1 pt-5">
                <p className="text-sm">Subtotal: {fmt(subtotal)}</p>
                <p className="text-sm">GST: {fmt(gstAmount)}</p>
                <p className="text-lg font-bold">Total: {fmt(invoiceTotal)}</p>
              </div>
            </div>

            <div><Label>Notes</Label><Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Payment terms, notes..." rows={2} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={saving} className="bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="save-invoice-btn">
              {saving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <FileText className="w-4 h-4 mr-1" />}Save Invoice
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
