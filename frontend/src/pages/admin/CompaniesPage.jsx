import { useState, useEffect } from 'react';
import { companyAPI, userAPI } from '../../lib/api';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { Search, Building2, Globe, MapPin, Plus, Edit2, UserCircle } from 'lucide-react';

export default function CompaniesPage() {
  const [companies, setCompanies] = useState([]);
  const [employers, setEmployers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [selectedEmployer, setSelectedEmployer] = useState('');
  const [createForm, setCreateForm] = useState({
    name: '',
    description: '',
    industry: '',
    website: '',
    location: '',
  });
  const [editForm, setEditForm] = useState({
    name: '',
    description: '',
    industry: '',
    website: '',
    location: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [companiesRes, employersRes] = await Promise.all([
        companyAPI.getAll(),
        userAPI.getEmployers(),
      ]);
      setCompanies(companiesRes.data);
      setEmployers(employersRes.data);
    } catch (error) {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!createForm.name) {
      toast.error('Company name is required');
      return;
    }
    try {
      await companyAPI.create(createForm);
      toast.success('Company created successfully');
      setShowCreate(false);
      setCreateForm({ name: '', description: '', industry: '', website: '', location: '' });
      loadData();
    } catch (error) {
      toast.error('Failed to create company');
    }
  };

  const handleEdit = async () => {
    if (!selectedCompany || !editForm.name) {
      toast.error('Company name is required');
      return;
    }
    try {
      await companyAPI.update(selectedCompany.id, editForm);
      toast.success('Company updated successfully');
      setShowEdit(false);
      setSelectedCompany(null);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update company');
    }
  };

  const handleAssignEmployer = async () => {
    if (!selectedCompany || !selectedEmployer) {
      toast.error('Please select an employer');
      return;
    }
    try {
      await companyAPI.assignEmployer(selectedCompany.id, selectedEmployer);
      toast.success('Employer assigned successfully');
      setShowAssign(false);
      setSelectedCompany(null);
      setSelectedEmployer('');
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to assign employer');
    }
  };

  const openEdit = (company) => {
    setSelectedCompany(company);
    setEditForm({
      name: company.name,
      description: company.description || '',
      industry: company.industry || '',
      website: company.website || '',
      location: company.location || '',
    });
    setShowEdit(true);
  };

  const openAssign = (company) => {
    setSelectedCompany(company);
    setSelectedEmployer(company.assigned_employer_id || '');
    setShowAssign(true);
  };

  const filteredCompanies = companies.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.industry?.toLowerCase().includes(search.toLowerCase())
  );

  const getEmployerName = (employerId) => {
    const employer = employers.find(e => e.id === employerId);
    return employer?.name || 'Unknown';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="companies-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Companies</h1>
          <p className="text-slate-500 mt-1">Manage client companies and employer assignments</p>
        </div>
        <div className="flex gap-3">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              placeholder="Search companies..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
            />
          </div>
          <Button
            onClick={() => setShowCreate(true)}
            className="bg-[#7CB342] hover:bg-[#689F38]"
            data-testid="add-company-btn"
          >
            <Plus className="w-4 h-4 mr-2" /> Add
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredCompanies.map((company) => (
          <Card key={company.id} className="border-slate-200 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-xl bg-[#DCFCE7] flex items-center justify-center shrink-0">
                  <Building2 className="w-7 h-7 text-[#7CB342]" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-heading font-semibold text-lg text-slate-900 truncate">
                      {company.name}
                    </h3>
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      onClick={() => openEdit(company)}
                      className="shrink-0"
                    >
                      <Edit2 className="w-4 h-4" />
                    </Button>
                  </div>
                  <p className="text-sm text-slate-500">{company.industry || 'Industry not specified'}</p>
                  {company.location && (
                    <p className="text-sm text-slate-400 flex items-center gap-1 mt-1">
                      <MapPin className="w-3 h-3" /> {company.location}
                    </p>
                  )}
                  {company.website && (
                    <a
                      href={company.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-[#7CB342] hover:underline flex items-center gap-1 mt-2"
                    >
                      <Globe className="w-3 h-3" /> Website
                    </a>
                  )}
                </div>
              </div>

              {/* Employer Assignment Section */}
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <UserCircle className="w-4 h-4 text-slate-400" />
                    <span className="text-xs text-slate-500">Assigned Employer:</span>
                  </div>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={() => openAssign(company)}
                    className="text-xs h-7"
                    data-testid={`assign-employer-${company.id}`}
                  >
                    {company.assigned_employer_id ? 'Change' : 'Assign'}
                  </Button>
                </div>
                {company.assigned_employer_id ? (
                  <Badge variant="secondary" className="mt-2">
                    {company.assigned_employer_name || getEmployerName(company.assigned_employer_id)}
                  </Badge>
                ) : (
                  <p className="text-xs text-amber-600 mt-2">No employer assigned</p>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
        {filteredCompanies.length === 0 && (
          <div className="col-span-full text-center py-12 bg-slate-50 rounded-lg">
            <Building2 className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500">No companies found</p>
            <p className="text-sm text-slate-400 mt-1">Add your first company to get started</p>
          </div>
        )}
      </div>

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Add Company</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Company Name *</Label>
              <Input
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                placeholder="Enter company name"
                data-testid="company-name-input"
              />
            </div>
            <div className="space-y-2">
              <Label>Industry</Label>
              <Input
                value={createForm.industry}
                onChange={(e) => setCreateForm({ ...createForm, industry: e.target.value })}
                placeholder="e.g., Technology, Healthcare"
              />
            </div>
            <div className="space-y-2">
              <Label>Location</Label>
              <Input
                value={createForm.location}
                onChange={(e) => setCreateForm({ ...createForm, location: e.target.value })}
                placeholder="e.g., New York, NY"
              />
            </div>
            <div className="space-y-2">
              <Label>Website</Label>
              <Input
                value={createForm.website}
                onChange={(e) => setCreateForm({ ...createForm, website: e.target.value })}
                placeholder="https://example.com"
              />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea
                value={createForm.description}
                onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                placeholder="Brief company description"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="save-company-btn"
            >
              Create Company
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={showEdit} onOpenChange={setShowEdit}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Edit Company</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Company Name *</Label>
              <Input
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                placeholder="Enter company name"
              />
            </div>
            <div className="space-y-2">
              <Label>Industry</Label>
              <Input
                value={editForm.industry}
                onChange={(e) => setEditForm({ ...editForm, industry: e.target.value })}
                placeholder="e.g., Technology, Healthcare"
              />
            </div>
            <div className="space-y-2">
              <Label>Location</Label>
              <Input
                value={editForm.location}
                onChange={(e) => setEditForm({ ...editForm, location: e.target.value })}
                placeholder="e.g., New York, NY"
              />
            </div>
            <div className="space-y-2">
              <Label>Website</Label>
              <Input
                value={editForm.website}
                onChange={(e) => setEditForm({ ...editForm, website: e.target.value })}
                placeholder="https://example.com"
              />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                placeholder="Brief company description"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEdit(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleEdit}
              className="bg-[#7CB342] hover:bg-[#689F38]"
            >
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Assign Employer Dialog */}
      <Dialog open={showAssign} onOpenChange={setShowAssign}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Assign Employer</DialogTitle>
            <DialogDescription>
              Select an employer to manage {selectedCompany?.name}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label>Select Employer</Label>
            <Select
              value={selectedEmployer}
              onValueChange={setSelectedEmployer}
            >
              <SelectTrigger className="mt-2" data-testid="employer-select">
                <SelectValue placeholder="Select an employer" />
              </SelectTrigger>
              <SelectContent>
                {employers.map((emp) => (
                  <SelectItem key={emp.id} value={emp.id}>
                    {emp.name} ({emp.email})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAssign(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAssignEmployer}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="confirm-assign-btn"
            >
              Assign Employer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
