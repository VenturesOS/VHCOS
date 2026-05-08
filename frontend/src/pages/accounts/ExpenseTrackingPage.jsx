import { useState, useEffect, useCallback } from 'react';
import { financeAPI } from '../../lib/api';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { toast } from 'sonner';
import { Plus, Download, IndianRupee, Loader2, Edit2, Trash2, Filter } from 'lucide-react';

const fmt = (n) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n || 0);

const CATEGORIES = [
  'Office Supplies', 'Travel', 'Software & Subscriptions', 'Salary & Wages',
  'Marketing', 'Utilities', 'Rent', 'Professional Services', 'Equipment',
  'Recruitment', 'Training', 'Miscellaneous',
];

const CAT_COLORS = {
  'Salary & Wages': 'bg-blue-50 text-blue-700',
  'Rent': 'bg-purple-50 text-purple-700',
  'Software & Subscriptions': 'bg-indigo-50 text-indigo-700',
  'Travel': 'bg-green-50 text-green-700',
  'Marketing': 'bg-pink-50 text-pink-700',
  'default': 'bg-slate-100 text-slate-600',
};

export default function ExpenseTrackingPage() {
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [category, setCategory] = useState('');
  const [month, setMonth] = useState('');
  const [summary, setSummary] = useState({});
  const [showForm, setShowForm] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ category: '', amount: '', description: '', date: new Date().toISOString().slice(0, 10), vendor: '', payment_method: '' });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit: 30 };
      if (category) params.category = category;
      if (month) params.month = month;
      const res = await financeAPI.listExpenses(params);
      setExpenses(res.data.expenses || []);
      setTotal(res.data.total || 0);
      setPages(res.data.pages || 1);
      setSummary(res.data.summary_by_category || {});
    } catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  }, [page, category, month]);

  useEffect(() => { load(); }, [load]);

  const totalAmount = Object.values(summary).reduce((s, v) => s + (v?.total || 0), 0);

  const openCreate = () => {
    setForm({ category: '', amount: '', description: '', date: new Date().toISOString().slice(0, 10), vendor: '', payment_method: '' });
    setEditItem(null);
    setShowForm(true);
  };

  const openEdit = (exp) => {
    setForm({ category: exp.category, amount: exp.amount, description: exp.description || '', date: exp.date, vendor: exp.vendor || '', payment_method: exp.payment_method || '' });
    setEditItem(exp);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.category || !form.amount || !form.date) return toast.error('Category, amount and date are required');
    setSaving(true);
    try {
      const payload = { ...form, amount: parseFloat(form.amount) };
      if (editItem) {
        await financeAPI.updateExpense(editItem.id, payload);
        toast.success('Updated');
      } else {
        await financeAPI.createExpense(payload);
        toast.success('Expense added');
      }
      setShowForm(false);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this expense?')) return;
    try { await financeAPI.deleteExpense(id); toast.success('Deleted'); load(); }
    catch { toast.error('Failed'); }
  };

  const downloadCSV = async () => {
    try {
      const res = await financeAPI.exportExpenses({ month: month || undefined });
      const rows = res.data.rows;
      if (!rows?.length) return toast.info('No data');
      const headers = Object.keys(rows[0]);
      const csv = [headers.join(','), ...rows.map(r => headers.map(h => `"${r[h] || ''}"`).join(','))].join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = res.data.filename || 'expenses.csv'; a.click();
    } catch { toast.error('Export failed'); }
  };

  return (
    <div className="space-y-4 p-4 sm:p-6" data-testid="expense-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Expense Tracking</h1>
          <p className="text-sm text-slate-500">{total} expenses {totalAmount > 0 && `| Total: ${fmt(totalAmount)}`}</p>
        </div>
        <div className="flex gap-2">
          <Input type="month" value={month} onChange={(e) => { setMonth(e.target.value); setPage(1); }} className="h-9 w-36" data-testid="month-filter" />
          <Select value={category} onValueChange={(v) => { setCategory(v === 'all' ? '' : v); setPage(1); }}>
            <SelectTrigger className="w-40 h-9" data-testid="category-filter"><SelectValue placeholder="All Categories" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              {CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={downloadCSV}><Download className="w-4 h-4 mr-1" />Export</Button>
          <Button size="sm" onClick={openCreate} className="bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="add-expense-btn"><Plus className="w-4 h-4 mr-1" />Add Expense</Button>
        </div>
      </div>

      {/* Category Summary */}
      {Object.keys(summary).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(summary).sort((a, b) => b[1].total - a[1].total).map(([cat, v]) => (
            <Badge key={cat} className={`text-xs px-3 py-1 cursor-pointer ${CAT_COLORS[cat] || CAT_COLORS.default}`} onClick={() => { setCategory(cat); setPage(1); }}>
              {cat}: {fmt(v.total)} ({v.count})
            </Badge>
          ))}
        </div>
      )}

      <Card className="border-slate-200">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="expenses-table">
            <thead>
              <tr className="border-b bg-slate-50">
                <th className="p-3 text-left font-medium text-slate-600">Date</th>
                <th className="p-3 text-left font-medium text-slate-600">Category</th>
                <th className="p-3 text-left font-medium text-slate-600">Description</th>
                <th className="p-3 text-left font-medium text-slate-600">Vendor</th>
                <th className="p-3 text-right font-medium text-slate-600">Amount</th>
                <th className="p-3 text-right font-medium text-slate-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="p-8 text-center"><Loader2 className="w-5 h-5 animate-spin mx-auto text-slate-400" /></td></tr>
              ) : expenses.length === 0 ? (
                <tr><td colSpan={6} className="p-8 text-center text-slate-400">No expenses found</td></tr>
              ) : expenses.map((exp) => (
                <tr key={exp.id} className="border-b hover:bg-slate-50" data-testid={`expense-row-${exp.id}`}>
                  <td className="p-3 text-slate-600">{exp.date}</td>
                  <td className="p-3"><Badge className={`text-xs ${CAT_COLORS[exp.category] || CAT_COLORS.default}`}>{exp.category}</Badge></td>
                  <td className="p-3 text-slate-700">{exp.description || '-'}</td>
                  <td className="p-3 text-slate-500">{exp.vendor || '-'}</td>
                  <td className="p-3 text-right font-medium text-slate-800"><IndianRupee className="w-3 h-3 inline" />{fmt(exp.amount)}</td>
                  <td className="p-3 text-right">
                    <div className="flex gap-1 justify-end">
                      <Button variant="ghost" size="sm" onClick={() => openEdit(exp)}><Edit2 className="w-3.5 h-3.5" /></Button>
                      <Button variant="ghost" size="sm" onClick={() => handleDelete(exp.id)}><Trash2 className="w-3.5 h-3.5 text-red-500" /></Button>
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
          <span className="text-sm text-slate-500">Page {page}/{pages}</span>
          <div className="flex gap-1">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
            <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editItem ? 'Edit' : 'Add'} Expense</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Category *</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                <SelectTrigger data-testid="expense-category"><SelectValue placeholder="Select..." /></SelectTrigger>
                <SelectContent>{CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Amount *</Label><Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="expense-amount" /></div>
              <div><Label>Date *</Label><Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></div>
            </div>
            <div><Label>Description</Label><Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Vendor</Label><Input value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} /></div>
              <div>
                <Label>Payment Method</Label>
                <Select value={form.payment_method} onValueChange={(v) => setForm({ ...form, payment_method: v })}>
                  <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                  <SelectContent>
                    {['Bank Transfer', 'Credit Card', 'Cash', 'UPI', 'Cheque'].map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="save-expense-btn">
              {saving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}{editItem ? 'Update' : 'Add'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
