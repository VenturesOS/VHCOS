import { useState, useEffect } from 'react';
import { commercialAPI, companyAPI } from '../../lib/api';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { 
  Search, Plus, Edit2, Trash2, DollarSign, Percent, 
  Building2, Calendar, AlertCircle, Layers
} from 'lucide-react';

export default function CommercialsPage() {
  const [commercials, setCommercials] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [companyFilter, setCompanyFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [selectedCommercial, setSelectedCommercial] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  
  const [form, setForm] = useState({
    company_id: '',
    commercial_name: '',
    type: 'percentage',
    fee_percentage: '',
    fixed_amount: '',
    level_config: { junior: '8', mid: '10', senior: '12', leadership: '15' },
    salary_min: '',
    salary_max: '',
    effective_from: new Date().toISOString().split('T')[0],
    effective_to: '',
    is_active: true,
  });

  useEffect(() => {
    loadData();
  }, [companyFilter]);

  const loadData = async () => {
    try {
      const [commercialsRes, companiesRes] = await Promise.all([
        commercialAPI.getAll({ company_id: companyFilter !== 'all' ? companyFilter : undefined }),
        companyAPI.getAll(),
      ]);
      setCommercials(commercialsRes.data);
      setCompanies(companiesRes.data);
    } catch (error) {
      toast.error('Failed to load commercials');
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setForm({
      company_id: '',
      commercial_name: '',
      type: 'percentage',
      fee_percentage: '',
      fixed_amount: '',
      level_config: { junior: '8', mid: '10', senior: '12', leadership: '15' },
      salary_min: '',
      salary_max: '',
      effective_from: new Date().toISOString().split('T')[0],
      effective_to: '',
      is_active: true,
    });
  };

  const handleCreate = async () => {
    if (!form.company_id || !form.commercial_name) {
      toast.error('Company and commercial name are required');
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        company_id: form.company_id,
        commercial_name: form.commercial_name,
        type: form.type,
        effective_from: form.effective_from,
        effective_to: form.effective_to || null,
        is_active: form.is_active,
      };

      if (form.type === 'percentage') {
        payload.fee_percentage = parseFloat(form.fee_percentage);
      } else if (form.type === 'fixed') {
        payload.fixed_amount = parseFloat(form.fixed_amount);
      } else if (form.type === 'level_based') {
        payload.level_config = {
          junior: parseFloat(form.level_config.junior),
          mid: parseFloat(form.level_config.mid),
          senior: parseFloat(form.level_config.senior),
          leadership: parseFloat(form.level_config.leadership),
        };
      }

      if (form.salary_min) payload.salary_min = parseInt(form.salary_min);
      if (form.salary_max) payload.salary_max = parseInt(form.salary_max);

      await commercialAPI.create(payload);
      toast.success('Commercial created successfully');
      setShowCreate(false);
      resetForm();
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create commercial');
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = async () => {
    if (!selectedCommercial) return;

    setSubmitting(true);
    try {
      const payload = {
        commercial_name: form.commercial_name,
        type: form.type,
        effective_from: form.effective_from,
        effective_to: form.effective_to || null,
        is_active: form.is_active,
      };

      if (form.type === 'percentage') {
        payload.fee_percentage = parseFloat(form.fee_percentage);
      } else if (form.type === 'fixed') {
        payload.fixed_amount = parseFloat(form.fixed_amount);
      } else if (form.type === 'level_based') {
        payload.level_config = {
          junior: parseFloat(form.level_config.junior),
          mid: parseFloat(form.level_config.mid),
          senior: parseFloat(form.level_config.senior),
          leadership: parseFloat(form.level_config.leadership),
        };
      }

      if (form.salary_min) payload.salary_min = parseInt(form.salary_min);
      if (form.salary_max) payload.salary_max = parseInt(form.salary_max);

      await commercialAPI.update(selectedCommercial.id, payload);
      toast.success('Commercial updated successfully');
      setShowEdit(false);
      setSelectedCommercial(null);
      resetForm();
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update commercial');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedCommercial) return;

    try {
      await commercialAPI.delete(selectedCommercial.id);
      toast.success('Commercial deactivated successfully');
      setShowDelete(false);
      setSelectedCommercial(null);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to deactivate commercial');
    }
  };

  const openEdit = (commercial) => {
    setSelectedCommercial(commercial);
    setForm({
      company_id: commercial.company_id,
      commercial_name: commercial.commercial_name,
      type: commercial.type,
      fee_percentage: commercial.fee_percentage?.toString() || '',
      fixed_amount: commercial.fixed_amount?.toString() || '',
      level_config: commercial.level_config || { junior: '8', mid: '10', senior: '12', leadership: '15' },
      salary_min: commercial.salary_min?.toString() || '',
      salary_max: commercial.salary_max?.toString() || '',
      effective_from: commercial.effective_from?.split('T')[0] || '',
      effective_to: commercial.effective_to?.split('T')[0] || '',
      is_active: commercial.is_active,
    });
    setShowEdit(true);
  };

  const filteredCommercials = commercials.filter((c) =>
    c.commercial_name?.toLowerCase().includes(search.toLowerCase()) ||
    c.company_name?.toLowerCase().includes(search.toLowerCase())
  );

  const getTypeBadge = (type) => {
    const styles = {
      percentage: 'bg-blue-100 text-blue-700',
      fixed: 'bg-green-100 text-green-700',
      level_based: 'bg-purple-100 text-purple-700',
    };
    return styles[type] || 'bg-slate-100 text-slate-600';
  };

  const formatFee = (commercial) => {
    if (commercial.type === 'percentage') {
      return `${commercial.fee_percentage}%`;
    } else if (commercial.type === 'fixed') {
      return `₹${commercial.fixed_amount?.toLocaleString('en-IN')}`;
    } else if (commercial.type === 'level_based') {
      const config = commercial.level_config || {};
      return `Jr: ${config.junior || 0}% | Mid: ${config.mid || 0}% | Sr: ${config.senior || 0}% | Lead: ${config.leadership || 0}%`;
    }
    return '-';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="commercials-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Commercials</h1>
          <p className="text-slate-500 mt-1">Manage fee structures and commercial agreements</p>
        </div>
        <div className="flex flex-wrap gap-2 sm:gap-3">
          <div className="relative w-full sm:w-48">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={companyFilter} onValueChange={setCompanyFilter}>
            <SelectTrigger className="w-full sm:w-40">
              <SelectValue placeholder="All Companies" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Companies</SelectItem>
              {companies.map((c) => (
                <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={() => { resetForm(); setShowCreate(true); }}
            className="bg-[#7CB342] hover:bg-[#689F38] w-full sm:w-auto"
            data-testid="create-commercial-btn"
          >
            <Plus className="w-4 h-4 mr-2" /> Add Commercial
          </Button>
        </div>
      </div>

      {/* Commercials Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {filteredCommercials.map((commercial) => (
          <Card key={commercial.id} className={`border-slate-200 ${!commercial.is_active && 'opacity-60'}`}>
            <CardContent className="p-5">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center">
                    {commercial.type === 'percentage' && <Percent className="w-6 h-6 text-[#7CB342]" />}
                    {commercial.type === 'fixed' && <DollarSign className="w-6 h-6 text-[#7CB342]" />}
                    {commercial.type === 'level_based' && <Layers className="w-6 h-6 text-[#7CB342]" />}
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900">{commercial.commercial_name}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      <Building2 className="w-3 h-3 text-slate-400" />
                      <span className="text-sm text-slate-500">{commercial.company_name}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={getTypeBadge(commercial.type)}>
                    {commercial.type.replace('_', ' ')}
                  </Badge>
                  {!commercial.is_active && (
                    <Badge variant="secondary" className="text-slate-400">Inactive</Badge>
                  )}
                </div>
              </div>

              <div className="bg-slate-50 rounded-lg p-3 mb-4">
                <p className="text-lg font-semibold text-[#7CB342]">{formatFee(commercial)}</p>
              </div>

              <div className="flex items-center justify-between text-sm text-slate-500">
                <div className="flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  <span>From: {commercial.effective_from?.split('T')[0]}</span>
                </div>
                {commercial.effective_to && (
                  <span>To: {commercial.effective_to.split('T')[0]}</span>
                )}
              </div>

              <div className="flex gap-2 mt-4 pt-4 border-t border-slate-100">
                <Button variant="outline" size="sm" onClick={() => openEdit(commercial)}>
                  <Edit2 className="w-4 h-4 mr-1" /> Edit
                </Button>
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="text-red-500 border-red-200 hover:bg-red-50"
                  onClick={() => { setSelectedCommercial(commercial); setShowDelete(true); }}
                >
                  <Trash2 className="w-4 h-4 mr-1" /> Deactivate
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {filteredCommercials.length === 0 && (
          <div className="col-span-full text-center py-12 bg-slate-50 rounded-lg">
            <DollarSign className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500">No commercials found</p>
            <p className="text-sm text-slate-400 mt-1">Create a commercial agreement to get started</p>
          </div>
        )}
      </div>

      {/* Create/Edit Dialog */}
      <Dialog open={showCreate || showEdit} onOpenChange={() => { setShowCreate(false); setShowEdit(false); }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {showCreate ? 'Create Commercial' : 'Edit Commercial'}
            </DialogTitle>
            <DialogDescription>
              Define fee structure for client engagements
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {showCreate && (
              <div className="space-y-2">
                <Label>Company *</Label>
                <Select value={form.company_id} onValueChange={(v) => setForm({ ...form, company_id: v })}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select company" />
                  </SelectTrigger>
                  <SelectContent>
                    {companies.map((c) => (
                      <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-2">
              <Label>Commercial Name *</Label>
              <Input
                value={form.commercial_name}
                onChange={(e) => setForm({ ...form, commercial_name: e.target.value })}
                placeholder="e.g., Standard IT Hiring"
              />
            </div>

            <div className="space-y-2">
              <Label>Type *</Label>
              <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="percentage">Percentage of Salary</SelectItem>
                  <SelectItem value="fixed">Fixed Fee</SelectItem>
                  <SelectItem value="level_based">Level-Based</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {form.type === 'percentage' && (
              <div className="space-y-2">
                <Label>Fee Percentage *</Label>
                <div className="relative">
                  <Input
                    type="number"
                    step="0.01"
                    value={form.fee_percentage}
                    onChange={(e) => setForm({ ...form, fee_percentage: e.target.value })}
                    placeholder="8.33"
                    className="pr-8"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">%</span>
                </div>
              </div>
            )}

            {form.type === 'fixed' && (
              <div className="space-y-2">
                <Label>Fixed Amount (INR) *</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">₹</span>
                  <Input
                    type="number"
                    value={form.fixed_amount}
                    onChange={(e) => setForm({ ...form, fixed_amount: e.target.value })}
                    placeholder="100000"
                    className="pl-8"
                  />
                </div>
              </div>
            )}

            {form.type === 'level_based' && (
              <div className="space-y-3 p-3 bg-slate-50 rounded-lg">
                <Label>Level-wise Percentages *</Label>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs text-slate-500">Junior</Label>
                    <Input
                      type="number"
                      step="0.01"
                      value={form.level_config.junior}
                      onChange={(e) => setForm({ ...form, level_config: { ...form.level_config, junior: e.target.value } })}
                      placeholder="8"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500">Mid</Label>
                    <Input
                      type="number"
                      step="0.01"
                      value={form.level_config.mid}
                      onChange={(e) => setForm({ ...form, level_config: { ...form.level_config, mid: e.target.value } })}
                      placeholder="10"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500">Senior</Label>
                    <Input
                      type="number"
                      step="0.01"
                      value={form.level_config.senior}
                      onChange={(e) => setForm({ ...form, level_config: { ...form.level_config, senior: e.target.value } })}
                      placeholder="12"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-500">Leadership</Label>
                    <Input
                      type="number"
                      step="0.01"
                      value={form.level_config.leadership}
                      onChange={(e) => setForm({ ...form, level_config: { ...form.level_config, leadership: e.target.value } })}
                      placeholder="15"
                    />
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Effective From *</Label>
                <Input
                  type="date"
                  value={form.effective_from}
                  onChange={(e) => setForm({ ...form, effective_from: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>Effective To (Optional)</Label>
                <Input
                  type="date"
                  value={form.effective_to}
                  onChange={(e) => setForm({ ...form, effective_to: e.target.value })}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Salary Min (Optional)</Label>
                <Input
                  type="number"
                  value={form.salary_min}
                  onChange={(e) => setForm({ ...form, salary_min: e.target.value })}
                  placeholder="300000"
                />
              </div>
              <div className="space-y-2">
                <Label>Salary Max (Optional)</Label>
                <Input
                  type="number"
                  value={form.salary_max}
                  onChange={(e) => setForm({ ...form, salary_max: e.target.value })}
                  placeholder="1500000"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreate(false); setShowEdit(false); }} disabled={submitting}>
              Cancel
            </Button>
            <Button
              onClick={showCreate ? handleCreate : handleEdit}
              disabled={submitting}
              className="bg-[#7CB342] hover:bg-[#689F38]"
            >
              {submitting ? 'Saving...' : showCreate ? 'Create' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={showDelete} onOpenChange={setShowDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading text-red-600 flex items-center gap-2">
              <AlertCircle className="w-5 h-5" /> Deactivate Commercial
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to deactivate <strong>{selectedCommercial?.commercial_name}</strong>?
              This will prevent it from being used in new revenue calculations.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDelete(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Deactivate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
