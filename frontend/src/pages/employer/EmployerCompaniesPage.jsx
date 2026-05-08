import { useState, useEffect } from 'react';
import { employerPortalAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { toast } from 'sonner';
import {
  Building2, Briefcase, TrendingUp, DollarSign, MapPin, Users,
  ChevronRight, Banknote, Target, BarChart3, Lock, Plus, Trash2,
  Percent, Hash, Layers, User, Phone, Mail
} from 'lucide-react';

const EMPTY_HR = { name: '', email: '', phone: '', designation: '' };
const EMPTY_LEVEL = { min_salary: '', max_salary: '', percentage: '' };
const EMPTY_FIXED_LEVEL = { level_name: '', min_salary: '', max_salary: '', fixed_fee: '' };

function buildFormState() {
  return {
    name: '', description: '', industry: '', website: '', location: '',
    hr_contacts: [{ ...EMPTY_HR }],
    commercial: { type: 'percentage', percentage_value: '', fixed_fee_amount: '', level_config: [{ ...EMPTY_LEVEL }], fixed_fee_levels: [{ ...EMPTY_FIXED_LEVEL }] },
  };
}

function buildPayload(form) {
  const comm = { type: form.commercial.type };
  if (comm.type === 'percentage') comm.percentage_value = parseFloat(form.commercial.percentage_value) || 0;
  else if (comm.type === 'fixed') comm.fixed_fee_amount = parseFloat(form.commercial.fixed_fee_amount) || 0;
  else if (comm.type === 'level_based') {
    comm.level_config = form.commercial.level_config
      .filter(l => l.min_salary !== '' && l.max_salary !== '' && l.percentage !== '')
      .map(l => ({ min_salary: parseFloat(l.min_salary), max_salary: parseFloat(l.max_salary), percentage: parseFloat(l.percentage) }));
  } else if (comm.type === 'fixed_level_based') {
    comm.fixed_fee_levels = (form.commercial.fixed_fee_levels || [])
      .filter(l => l.min_salary !== '' && l.max_salary !== '' && l.fixed_fee !== '')
      .map(l => ({ level_name: l.level_name || null, min_salary: parseFloat(l.min_salary), max_salary: parseFloat(l.max_salary), fixed_fee: parseFloat(l.fixed_fee) }));
  }
  return {
    name: form.name, description: form.description || null, industry: form.industry || null,
    website: form.website || null, location: form.location || null,
    hr_contacts: form.hr_contacts.filter(h => h.name || h.email || h.phone),
    commercial: comm,
  };
}

function CreateCompanyDialog({ open, onOpenChange, onCreated }) {
  const [form, setForm] = useState(buildFormState());
  const [submitting, setSubmitting] = useState(false);
  const updateField = (field, val) => setForm(prev => ({ ...prev, [field]: val }));

  const handleSubmit = async () => {
    if (!form.name) return toast.error('Company name is required');
    if (!form.commercial.type) return toast.error('Commercial model is required');
    setSubmitting(true);
    try {
      await employerPortalAPI.createCompany(buildPayload(form));
      toast.success('Company created and assigned to you!');
      setForm(buildFormState());
      onOpenChange(false);
      onCreated();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to create company');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="employer-create-company-dialog">
        <DialogHeader>
          <DialogTitle>Add New Company</DialogTitle>
          <DialogDescription>Create a company - it will be automatically assigned to you.</DialogDescription>
        </DialogHeader>
        <div className="space-y-5 py-2">
          {/* Basic Info */}
          <div className="space-y-3">
            <Label className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
              <Building2 className="w-4 h-4" /> Company Info
            </Label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-gray-500">Company Name *</Label>
                <Input value={form.name} onChange={e => updateField('name', e.target.value)} placeholder="Company name" data-testid="emp-company-name" />
              </div>
              <div>
                <Label className="text-xs text-gray-500">Industry</Label>
                <Input value={form.industry} onChange={e => updateField('industry', e.target.value)} placeholder="e.g. Manufacturing" data-testid="emp-company-industry" />
              </div>
              <div>
                <Label className="text-xs text-gray-500">Location</Label>
                <Input value={form.location} onChange={e => updateField('location', e.target.value)} placeholder="City, State" data-testid="emp-company-location" />
              </div>
              <div>
                <Label className="text-xs text-gray-500">Website</Label>
                <Input value={form.website} onChange={e => updateField('website', e.target.value)} placeholder="https://..." data-testid="emp-company-website" />
              </div>
            </div>
            <div>
              <Label className="text-xs text-gray-500">Description</Label>
              <Textarea value={form.description} onChange={e => updateField('description', e.target.value)} placeholder="Brief description" rows={2} data-testid="emp-company-desc" />
            </div>
          </div>

          <hr className="border-gray-100" />

          {/* HR Contacts */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
                <User className="w-4 h-4" /> HR Contacts
              </Label>
              <Button type="button" variant="ghost" size="sm" onClick={() => setForm(prev => ({ ...prev, hr_contacts: [...prev.hr_contacts, { ...EMPTY_HR }] }))} data-testid="emp-add-hr">
                <Plus className="w-3.5 h-3.5 mr-1" /> Add
              </Button>
            </div>
            {form.hr_contacts.map((c, i) => (
              <div key={`level-${i}`} className="grid grid-cols-1 sm:grid-cols-4 gap-2 p-3 bg-gray-50 rounded-lg">
                <Input placeholder="Name" value={c.name} onChange={e => { const next = [...form.hr_contacts]; next[i] = { ...next[i], name: e.target.value }; setForm(prev => ({ ...prev, hr_contacts: next })); }} />
                <Input placeholder="Email" value={c.email} onChange={e => { const next = [...form.hr_contacts]; next[i] = { ...next[i], email: e.target.value }; setForm(prev => ({ ...prev, hr_contacts: next })); }} />
                <Input placeholder="Phone" value={c.phone} onChange={e => { const next = [...form.hr_contacts]; next[i] = { ...next[i], phone: e.target.value }; setForm(prev => ({ ...prev, hr_contacts: next })); }} />
                <div className="flex gap-2">
                  <Input placeholder="Designation" value={c.designation || ''} onChange={e => { const next = [...form.hr_contacts]; next[i] = { ...next[i], designation: e.target.value }; setForm(prev => ({ ...prev, hr_contacts: next })); }} className="flex-1" />
                  {form.hr_contacts.length > 1 && (
                    <Button type="button" variant="ghost" size="icon" className="shrink-0 text-red-400 hover:text-red-600"
                      onClick={() => setForm(prev => ({ ...prev, hr_contacts: prev.hr_contacts.filter((_, idx) => idx !== i) }))}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>

          <hr className="border-gray-100" />

          {/* Commercial */}
          <div className="space-y-3">
            <Label className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
              <DollarSign className="w-4 h-4" /> Commercial Model <span className="text-red-500">*</span>
            </Label>
            <div className="flex gap-2 flex-wrap">
              {[{ key: 'percentage', label: 'Flat %', icon: Percent }, { key: 'fixed', label: 'Fixed Fee', icon: Hash }, { key: 'level_based', label: 'Level % Based', icon: Layers }, { key: 'fixed_level_based', label: 'Level Fixed Fee', icon: Layers }].map(({ key, label, icon: Icon }) => (
                <button key={key} type="button" onClick={() => setForm(prev => ({ ...prev, commercial: { ...prev.commercial, type: key } }))}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${form.commercial.type === key ? 'bg-teal-600 text-white border-teal-600' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'}`}
                  data-testid={`emp-comm-type-${key}`}>
                  <Icon className="w-4 h-4" /> {label}
                </button>
              ))}
            </div>
            {form.commercial.type === 'percentage' && (
              <div className="max-w-xs">
                <Label className="text-xs text-gray-500 mb-1 block">Fee Percentage (%)</Label>
                <Input type="number" step="0.01" min="0" placeholder="e.g. 8.33" value={form.commercial.percentage_value}
                  onChange={e => setForm(prev => ({ ...prev, commercial: { ...prev.commercial, percentage_value: e.target.value } }))} data-testid="emp-comm-pct" />
              </div>
            )}
            {form.commercial.type === 'fixed' && (
              <div className="max-w-xs">
                <Label className="text-xs text-gray-500 mb-1 block">Fixed Fee Amount (INR)</Label>
                <Input type="number" step="1" min="0" placeholder="e.g. 50000" value={form.commercial.fixed_fee_amount}
                  onChange={e => setForm(prev => ({ ...prev, commercial: { ...prev.commercial, fixed_fee_amount: e.target.value } }))} data-testid="emp-comm-fixed" />
              </div>
            )}
            {form.commercial.type === 'level_based' && (
              <div className="space-y-2">
                <div className="grid grid-cols-4 gap-2 text-xs text-gray-500 font-medium px-1">
                  <span>Min Salary</span><span>Max Salary</span><span>Percentage (%)</span><span></span>
                </div>
                {form.commercial.level_config.map((lv, i) => (
                  <div key={`fixed-${i}`} className="grid grid-cols-4 gap-2 items-center">
                    <Input type="number" min="0" placeholder="100000" value={lv.min_salary}
                      onChange={e => { const next = [...form.commercial.level_config]; next[i] = { ...next[i], min_salary: e.target.value }; setForm(prev => ({ ...prev, commercial: { ...prev.commercial, level_config: next } })); }} />
                    <Input type="number" min="0" placeholder="1200000" value={lv.max_salary}
                      onChange={e => { const next = [...form.commercial.level_config]; next[i] = { ...next[i], max_salary: e.target.value }; setForm(prev => ({ ...prev, commercial: { ...prev.commercial, level_config: next } })); }} />
                    <Input type="number" step="0.01" min="0" placeholder="8.33" value={lv.percentage}
                      onChange={e => { const next = [...form.commercial.level_config]; next[i] = { ...next[i], percentage: e.target.value }; setForm(prev => ({ ...prev, commercial: { ...prev.commercial, level_config: next } })); }} />
                    {form.commercial.level_config.length > 1 && (
                      <Button type="button" variant="ghost" size="icon" className="text-red-400 hover:text-red-600"
                        onClick={() => setForm(prev => ({ ...prev, commercial: { ...prev.commercial, level_config: prev.commercial.level_config.filter((_, idx) => idx !== i) } }))}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm"
                  onClick={() => setForm(prev => ({ ...prev, commercial: { ...prev.commercial, level_config: [...prev.commercial.level_config, { ...EMPTY_LEVEL }] } }))}>
                  <Plus className="w-3.5 h-3.5 mr-1" /> Add Level
                </Button>
              </div>
            )}
            {form.commercial.type === 'fixed_level_based' && (
              <div className="space-y-2">
                <div className="grid grid-cols-5 gap-2 text-xs text-gray-500 font-medium px-1">
                  <span>Level Name</span><span>Min Salary</span><span>Max Salary</span><span>Fixed Fee (INR)</span><span></span>
                </div>
                {(form.commercial.fixed_fee_levels || [{ ...EMPTY_FIXED_LEVEL }]).map((lv, i) => (
                  <div key={`range-${i}`} className="grid grid-cols-5 gap-2 items-center">
                    <Input type="text" placeholder="e.g. Junior" value={lv.level_name || ''}
                      onChange={e => { const next = [...(form.commercial.fixed_fee_levels || [])]; next[i] = { ...next[i], level_name: e.target.value }; setForm(prev => ({ ...prev, commercial: { ...prev.commercial, fixed_fee_levels: next } })); }} />
                    <Input type="number" min="0" placeholder="100000" value={lv.min_salary}
                      onChange={e => { const next = [...(form.commercial.fixed_fee_levels || [])]; next[i] = { ...next[i], min_salary: e.target.value }; setForm(prev => ({ ...prev, commercial: { ...prev.commercial, fixed_fee_levels: next } })); }} />
                    <Input type="number" min="0" placeholder="1200000" value={lv.max_salary}
                      onChange={e => { const next = [...(form.commercial.fixed_fee_levels || [])]; next[i] = { ...next[i], max_salary: e.target.value }; setForm(prev => ({ ...prev, commercial: { ...prev.commercial, fixed_fee_levels: next } })); }} />
                    <Input type="number" step="1" min="0" placeholder="50000" value={lv.fixed_fee}
                      onChange={e => { const next = [...(form.commercial.fixed_fee_levels || [])]; next[i] = { ...next[i], fixed_fee: e.target.value }; setForm(prev => ({ ...prev, commercial: { ...prev.commercial, fixed_fee_levels: next } })); }} />
                    {(form.commercial.fixed_fee_levels || []).length > 1 && (
                      <Button type="button" variant="ghost" size="icon" className="text-red-400 hover:text-red-600"
                        onClick={() => setForm(prev => ({ ...prev, commercial: { ...prev.commercial, fixed_fee_levels: prev.commercial.fixed_fee_levels.filter((_, idx) => idx !== i) } }))}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm"
                  onClick={() => setForm(prev => ({ ...prev, commercial: { ...prev.commercial, fixed_fee_levels: [...(prev.commercial.fixed_fee_levels || []), { ...EMPTY_FIXED_LEVEL }] } }))}>
                  <Plus className="w-3.5 h-3.5 mr-1" /> Add Level
                </Button>
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="emp-create-cancel">Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting || !form.name} data-testid="emp-create-submit">
            {submitting ? 'Creating...' : 'Create Company'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function EmployerCompaniesPage() {
  const [companiesData, setCompaniesData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    loadCompanies();
  }, []);

  const loadCompanies = async () => {
    try {
      const res = await employerPortalAPI.getMyCompanies();
      setCompaniesData(res.data);
    } catch (error) {
      toast.error('Failed to load companies');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  const companies = companiesData?.companies || [];

  if (companies.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-heading font-bold text-slate-900">Companies</h1>
            <p className="text-sm text-slate-500 mt-1">Manage your companies and their details</p>
          </div>
          <Button size="sm" onClick={() => setShowCreate(true)} data-testid="add-company-btn">
            <Plus className="w-4 h-4 mr-1" /> Add Company
          </Button>
        </div>
        <Card className="border-slate-200">
          <CardContent className="p-12 text-center">
            <Building2 className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-600 mb-2">No Companies Yet</h3>
            <p className="text-slate-500 mb-4">Add your first company to get started.</p>
            <Button onClick={() => setShowCreate(true)} data-testid="add-company-empty-btn">
              <Plus className="w-4 h-4 mr-1" /> Add Company
            </Button>
          </CardContent>
        </Card>
        <CreateCompanyDialog open={showCreate} onOpenChange={setShowCreate} onCreated={loadCompanies} />
      </div>
    );
  }

  const totalMandates = companies.reduce((sum, c) => sum + (c.mandates?.length || 0), 0);
  const totalPipeline = companies.reduce((sum, c) => sum + (c.total_pipeline || 0), 0);
  const totalRevenue = companies.reduce((sum, c) => sum + (c.total_revenue_closed || 0), 0);

  return (
    <div className="space-y-6" data-testid="employer-companies">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-heading font-bold text-slate-900">Companies</h1>
          <p className="text-sm text-slate-500 mt-1">{companies.length} companies</p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(true)} data-testid="add-company-btn">
          <Plus className="w-4 h-4 mr-1" /> Add Company
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <Building2 className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{companies.length}</p>
                <p className="text-xs text-slate-500">Companies</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
                <Briefcase className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{totalMandates}</p>
                <p className="text-xs text-slate-500">Total Mandates</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <Target className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{totalPipeline}</p>
                <p className="text-xs text-slate-500">Total Pipeline</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200 bg-gradient-to-r from-green-50 to-white">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-green-600">{formatSalaryINR(totalRevenue)}</p>
                <p className="text-xs text-slate-500">Closed Revenue</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Companies List */}
      <Card className="border-slate-200">
        <CardHeader className="border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Building2 className="w-5 h-5 text-[#7CB342]" />
            My Companies
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-slate-100">
            {companies.map((company) => (
              <div
                key={company.id}
                className="p-4 hover:bg-slate-50 transition-colors cursor-pointer flex items-center justify-between"
                onClick={() => setSelectedCompany(company)}
                data-testid={`company-row-${company.id}`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center overflow-hidden">
                    {company.logo_url ? (
                      <img src={company.logo_url} alt={company.name} className="w-full h-full object-contain" />
                    ) : (
                      <Building2 className="w-6 h-6 text-slate-400" />
                    )}
                  </div>
                  <div>
                    <p className="font-medium text-slate-900">{company.name}</p>
                    <div className="flex items-center gap-3 text-sm text-slate-500">
                      {company.industry && <span>{company.industry}</span>}
                      {company.location && (
                        <span className="flex items-center gap-1">
                          <MapPin className="w-3 h-3" /> {company.location}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-8">
                  <div className="text-center">
                    <p className="text-lg font-semibold text-slate-900">{company.active_mandates_count || 0}</p>
                    <p className="text-xs text-slate-500">Active Mandates</p>
                  </div>
                  <div className="text-center">
                    <p className="text-lg font-semibold text-slate-900">{company.total_pipeline || 0}</p>
                    <p className="text-xs text-slate-500">Pipeline</p>
                  </div>
                  <div className="text-center hidden md:block">
                    <p className="text-lg font-semibold text-purple-600">
                      {company.commercial?.fee_percentage || company.commercial?.percentage_value || '-'}%
                    </p>
                    <p className="text-xs text-slate-500">Fee %</p>
                  </div>
                  <div className="text-center hidden md:block">
                    <p className="text-lg font-semibold text-green-600">{formatSalaryINR(company.total_revenue_closed || 0)}</p>
                    <p className="text-xs text-slate-500">Closed</p>
                  </div>
                  <ChevronRight className="w-5 h-5 text-slate-400" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Company Detail Dialog */}
      <Dialog open={!!selectedCompany} onOpenChange={() => setSelectedCompany(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <Building2 className="w-6 h-6 text-slate-400" />
              {selectedCompany?.name}
            </DialogTitle>
          </DialogHeader>
          {selectedCompany && (
            <Tabs defaultValue="commercial" className="w-full">
              <TabsList className="mb-4">
                <TabsTrigger value="commercial"><DollarSign className="w-4 h-4 mr-1" /> Commercial</TabsTrigger>
                <TabsTrigger value="mandates"><Briefcase className="w-4 h-4 mr-1" /> Mandates</TabsTrigger>
                <TabsTrigger value="pipeline"><BarChart3 className="w-4 h-4 mr-1" /> Pipelines</TabsTrigger>
              </TabsList>

              <TabsContent value="commercial">
                <div className="space-y-4">
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-start gap-2">
                    <Lock className="w-4 h-4 text-blue-500 mt-0.5" />
                    <p className="text-sm text-blue-700">Commercial details are managed by Admin. Contact your administrator to make changes.</p>
                  </div>
                  {selectedCompany.commercial ? (
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Fee Percentage</p>
                        <p className="text-2xl font-bold text-purple-600">{selectedCompany.commercial.fee_percentage || selectedCompany.commercial.percentage_value || '-'}%</p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Currency</p>
                        <p className="text-2xl font-bold text-slate-800">{selectedCompany.commercial.currency || 'INR'}</p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Fee Structure</p>
                        <p className="font-medium text-slate-800 capitalize">{selectedCompany.commercial.fee_structure || selectedCompany.commercial.type || '-'}</p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Payment Terms</p>
                        <p className="font-medium text-slate-800">{selectedCompany.commercial.payment_terms || '-'}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <Banknote className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                      <p className="text-slate-500">No commercial terms defined</p>
                    </div>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="mandates">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="font-medium">Active Mandates</h4>
                    <span className="text-sm text-slate-500">{selectedCompany.active_mandates_count || 0} active</span>
                  </div>
                  <div className="space-y-2 max-h-80 overflow-y-auto">
                    {selectedCompany.mandates?.filter(m => m.status === 'active').map((mandate) => (
                      <div key={mandate.id} className="p-4 bg-slate-50 rounded-lg border-l-4 border-[#7CB342]">
                        <div className="flex items-center justify-between mb-2">
                          <p className="font-medium text-slate-800">{mandate.title}</p>
                          <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full capitalize">{mandate.status}</span>
                        </div>
                        <div className="flex items-center gap-4 text-sm text-slate-500">
                          {mandate.location && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {mandate.location}</span>}
                          <span>Pipeline: {mandate.pipeline_count}</span>
                          <span className="text-green-600">Closed: {formatSalaryINR(mandate.total_revenue_closed)}</span>
                        </div>
                      </div>
                    ))}
                    {(!selectedCompany.mandates || selectedCompany.mandates.length === 0) && (
                      <p className="text-slate-400 text-sm text-center py-4">No mandates found</p>
                    )}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="pipeline">
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3 mb-4">
                    <div className="p-3 bg-amber-50 rounded-lg text-center">
                      <p className="text-2xl font-bold text-amber-600">{selectedCompany.total_pipeline || 0}</p>
                      <p className="text-xs text-amber-600">Total Pipeline</p>
                    </div>
                    <div className="p-3 bg-green-50 rounded-lg text-center">
                      <p className="text-2xl font-bold text-green-600">{formatSalaryINR(selectedCompany.total_revenue_closed || 0)}</p>
                      <p className="text-xs text-green-600">Closed Revenue</p>
                    </div>
                  </div>
                  <h4 className="font-medium">Pipeline by Mandate</h4>
                  <div className="space-y-3 max-h-64 overflow-y-auto">
                    {selectedCompany.mandates?.map((mandate) => (
                      <div key={mandate.id} className="p-3 bg-slate-50 rounded-lg">
                        <div className="flex items-center justify-between mb-2">
                          <p className="font-medium text-slate-800 text-sm">{mandate.title}</p>
                          <span className="text-xs text-green-600">{formatSalaryINR(mandate.total_revenue_closed)} closed</span>
                        </div>
                        <div className="flex gap-2 flex-wrap">
                          {Object.entries(mandate.stages || {}).map(([stage, count]) => (
                            <span key={stage} className={`px-2 py-0.5 text-xs rounded ${
                              stage === 'hired' ? 'bg-green-100 text-green-700' :
                              stage === 'rejected' ? 'bg-red-100 text-red-700' :
                              stage === 'offered' ? 'bg-purple-100 text-purple-700' :
                              stage === 'interview' ? 'bg-blue-100 text-blue-700' :
                              stage === 'shortlisted' ? 'bg-amber-100 text-amber-700' :
                              'bg-slate-100 text-slate-600'
                            }`}>{stage}: {count}</span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>

      {/* Create Company Dialog */}
      <CreateCompanyDialog open={showCreate} onOpenChange={setShowCreate} onCreated={loadCompanies} />
    </div>
  );
}
