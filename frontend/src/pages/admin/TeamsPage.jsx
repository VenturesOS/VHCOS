import { useState, useEffect } from 'react';
import { teamAPI, userAPI, companyAPI } from '../../lib/api';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { 
  Search, Users, Building2, Plus, Edit2, Trash2, 
  UserCircle, Briefcase, ChevronRight, AlertCircle, CheckCircle2, Info
} from 'lucide-react';

export default function TeamsPage() {
  const [teams, setTeams] = useState([]);
  const [employers, setEmployers] = useState([]);
  const [recruiters, setRecruiters] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  
  // Dialog states
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState(null);
  
  // Auto-attach companies state
  const [autoAttachedCompanies, setAutoAttachedCompanies] = useState([]);
  const [loadingEmployerCompanies, setLoadingEmployerCompanies] = useState(false);
  
  // Form state
  const [createForm, setCreateForm] = useState({
    name: '',
    employer_id: '',
    recruiter_ids: [],
    company_ids: [],
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [teamsRes, employersRes, usersRes, companiesRes] = await Promise.all([
        teamAPI.getAll(),
        userAPI.getEmployers(),
        userAPI.getAll(),
        companyAPI.getAll(),
      ]);
      setTeams(teamsRes.data);
      setEmployers(employersRes.data);
      setRecruiters(usersRes.data.filter(u => u.role === 'recruiter'));
      setCompanies(companiesRes.data);
    } catch (error) {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  // Fetch companies assigned to selected employer (for auto-attach)
  const fetchEmployerCompanies = async (employerId) => {
    if (!employerId) {
      setAutoAttachedCompanies([]);
      return;
    }
    
    setLoadingEmployerCompanies(true);
    try {
      const res = await userAPI.getEmployerCompanies(employerId);
      const empCompanies = res.data.companies || [];
      setAutoAttachedCompanies(empCompanies);
      
      // Auto-select these companies in the form
      const autoCompanyIds = empCompanies.map(c => c.id);
      setCreateForm(prev => ({
        ...prev,
        company_ids: autoCompanyIds
      }));
      
      if (empCompanies.length > 0) {
        toast.success(`${empCompanies.length} company(ies) auto-attached from employer`);
      }
    } catch (error) {
      console.error('Failed to fetch employer companies:', error);
      setAutoAttachedCompanies([]);
    } finally {
      setLoadingEmployerCompanies(false);
    }
  };

  // Handle employer selection - auto-fetch companies
  const handleEmployerChange = (employerId) => {
    setCreateForm(prev => ({ ...prev, employer_id: employerId, company_ids: [] }));
    fetchEmployerCompanies(employerId);
  };

  const handleCreate = async () => {
    if (!createForm.name || !createForm.employer_id) {
      toast.error('Team name and employer are required');
      return;
    }
    try {
      await teamAPI.create(createForm);
      toast.success('Team created successfully');
      setShowCreate(false);
      resetForm();
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create team');
    }
  };

  const handleUpdate = async () => {
    if (!selectedTeam || !createForm.name) {
      toast.error('Team name is required');
      return;
    }
    try {
      await teamAPI.update(selectedTeam.id, {
        name: createForm.name,
        recruiter_ids: createForm.recruiter_ids,
        company_ids: createForm.company_ids,
      });
      toast.success('Team updated successfully');
      setShowEdit(false);
      setSelectedTeam(null);
      resetForm();
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update team');
    }
  };

  const handleDelete = async () => {
    if (!selectedTeam) return;
    try {
      await teamAPI.delete(selectedTeam.id);
      toast.success('Team disabled successfully');
      setShowDelete(false);
      setSelectedTeam(null);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to disable team');
    }
  };

  const openEdit = (team) => {
    setSelectedTeam(team);
    setCreateForm({
      name: team.name,
      employer_id: team.employer_id,
      recruiter_ids: team.recruiter_ids || [],
      company_ids: team.company_ids || [],
    });
    setAutoAttachedCompanies([]); // Clear auto-attached for edit mode
    setShowEdit(true);
  };

  const openDelete = (team) => {
    setSelectedTeam(team);
    setShowDelete(true);
  };

  const resetForm = () => {
    setCreateForm({
      name: '',
      employer_id: '',
      recruiter_ids: [],
      company_ids: [],
    });
    setAutoAttachedCompanies([]);
  };

  const toggleRecruiter = (recruiterId) => {
    setCreateForm(prev => ({
      ...prev,
      recruiter_ids: prev.recruiter_ids.includes(recruiterId)
        ? prev.recruiter_ids.filter(id => id !== recruiterId)
        : [...prev.recruiter_ids, recruiterId]
    }));
  };

  const toggleCompany = (companyId) => {
    setCreateForm(prev => ({
      ...prev,
      company_ids: prev.company_ids.includes(companyId)
        ? prev.company_ids.filter(id => id !== companyId)
        : [...prev.company_ids, companyId]
    }));
  };

  const filteredTeams = teams.filter((t) =>
    t.name.toLowerCase().includes(search.toLowerCase()) ||
    t.employer_name?.toLowerCase().includes(search.toLowerCase())
  );

  const activeTeams = filteredTeams.filter(t => t.status === 'active');
  const disabledTeams = filteredTeams.filter(t => t.status === 'disabled');

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="teams-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Teams & Hierarchy</h1>
          <p className="text-slate-500 mt-1">Manage teams, assign recruiters and companies</p>
        </div>
        <div className="flex gap-3">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              placeholder="Search teams..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
              data-testid="search-teams-input"
            />
          </div>
          <Button
            onClick={() => { resetForm(); setShowCreate(true); }}
            className="bg-[#7CB342] hover:bg-[#689F38]"
            data-testid="create-team-btn"
          >
            <Plus className="w-4 h-4 mr-2" /> Create Team
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#DCFCE7] flex items-center justify-center">
              <Users className="w-5 h-5 text-[#7CB342]" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{activeTeams.length}</p>
              <p className="text-xs text-slate-500">Active Teams</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
              <UserCircle className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{employers.length}</p>
              <p className="text-xs text-slate-500">Employers</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-50 flex items-center justify-center">
              <Briefcase className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{recruiters.length}</p>
              <p className="text-xs text-slate-500">Recruiters</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
              <Building2 className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{companies.length}</p>
              <p className="text-xs text-slate-500">Companies</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Teams List */}
      <div className="space-y-4">
        <h2 className="font-heading font-semibold text-lg text-slate-900">Active Teams</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {activeTeams.map((team) => (
            <TeamCard 
              key={team.id} 
              team={team} 
              onEdit={() => openEdit(team)}
              onDelete={() => openDelete(team)}
            />
          ))}
          {activeTeams.length === 0 && (
            <div className="col-span-full text-center py-12 bg-slate-50 rounded-lg">
              <Users className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500">No active teams found</p>
              <p className="text-sm text-slate-400 mt-1">Create a team to organize your recruiters and companies</p>
            </div>
          )}
        </div>

        {disabledTeams.length > 0 && (
          <>
            <h2 className="font-heading font-semibold text-lg text-slate-500 mt-8">Disabled Teams</h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 opacity-60">
              {disabledTeams.map((team) => (
                <TeamCard key={team.id} team={team} disabled />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Create Team Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">Create New Team</DialogTitle>
            <DialogDescription>
              Organize recruiters and companies under a team managed by an employer.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-6 py-4">
            {/* Team Name */}
            <div className="space-y-2">
              <Label>Team Name *</Label>
              <Input
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                placeholder="e.g., Tech Hiring Team"
                data-testid="team-name-input"
              />
            </div>

            {/* Employer Selection */}
            <div className="space-y-2">
              <Label>Team Owner (Employer) *</Label>
              <Select
                value={createForm.employer_id}
                onValueChange={handleEmployerChange}
              >
                <SelectTrigger data-testid="employer-select">
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

            {/* Auto-Attached Companies Info */}
            {createForm.employer_id && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-3" data-testid="auto-attach-info">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="w-5 h-5 text-green-600 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-green-800">
                      {loadingEmployerCompanies ? 'Loading...' : 
                        autoAttachedCompanies.length > 0 
                          ? `${autoAttachedCompanies.length} company(ies) auto-attached`
                          : 'No companies assigned to this employer yet'}
                    </p>
                    {autoAttachedCompanies.length > 0 && (
                      <p className="text-xs text-green-600 mt-1">
                        Companies assigned to this employer are automatically included. You can add more below.
                      </p>
                    )}
                  </div>
                </div>
                {autoAttachedCompanies.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {autoAttachedCompanies.map(comp => (
                      <Badge key={comp.id} variant="secondary" className="bg-green-100 text-green-700 text-xs">
                        {comp.name}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Recruiters Selection */}
            <div className="space-y-2">
              <Label>Assign Recruiters</Label>
              <div className="border rounded-lg p-3 max-h-40 overflow-y-auto space-y-2">
                {recruiters.length === 0 ? (
                  <p className="text-sm text-slate-400">No recruiters available</p>
                ) : (
                  recruiters.map((rec) => (
                    <label 
                      key={rec.id} 
                      className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={createForm.recruiter_ids.includes(rec.id)}
                        onChange={() => toggleRecruiter(rec.id)}
                        className="rounded border-slate-300 text-[#7CB342] focus:ring-[#7CB342]"
                      />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-slate-700">{rec.name}</p>
                        <p className="text-xs text-slate-400">{rec.email}</p>
                      </div>
                    </label>
                  ))
                )}
              </div>
              {createForm.recruiter_ids.length > 0 && (
                <p className="text-xs text-slate-500">{createForm.recruiter_ids.length} recruiter(s) selected</p>
              )}
            </div>

            {/* Additional Companies Selection (optional - for adding more companies) */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Label>Additional Companies</Label>
                <span className="text-xs text-slate-400">(optional)</span>
              </div>
              <p className="text-xs text-slate-500 -mt-1">
                Add more companies to this team beyond the auto-attached ones.
              </p>
              <div className="border rounded-lg p-3 max-h-40 overflow-y-auto space-y-2">
                {companies.filter(c => !autoAttachedCompanies.find(ac => ac.id === c.id)).length === 0 ? (
                  <p className="text-sm text-slate-400">
                    {autoAttachedCompanies.length > 0 
                      ? 'All available companies are already attached'
                      : 'No companies available'}
                  </p>
                ) : (
                  companies
                    .filter(c => !autoAttachedCompanies.find(ac => ac.id === c.id))
                    .map((comp) => (
                    <label 
                      key={comp.id} 
                      className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={createForm.company_ids.includes(comp.id)}
                        onChange={() => toggleCompany(comp.id)}
                        className="rounded border-slate-300 text-[#7CB342] focus:ring-[#7CB342]"
                      />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-slate-700">{comp.name}</p>
                        <p className="text-xs text-slate-400">{comp.industry || 'No industry'}</p>
                      </div>
                    </label>
                  ))
                )}
              </div>
              {createForm.company_ids.length > autoAttachedCompanies.length && (
                <p className="text-xs text-slate-500">
                  {createForm.company_ids.length - autoAttachedCompanies.length} additional company(ies) selected
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="save-team-btn"
            >
              Create Team
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Team Dialog */}
      <Dialog open={showEdit} onOpenChange={setShowEdit}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">Edit Team</DialogTitle>
            <DialogDescription>
              Update team details. Note: Team owner cannot be changed after creation.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-6 py-4">
            <div className="space-y-2">
              <Label>Team Name *</Label>
              <Input
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                placeholder="e.g., Tech Hiring Team"
              />
            </div>

            <div className="space-y-2">
              <Label>Team Owner (Employer)</Label>
              <div className="p-3 bg-slate-50 rounded-lg text-sm text-slate-600">
                {selectedTeam?.employer_name || 'Unknown'} 
                <span className="text-xs text-slate-400 ml-2">(Cannot be changed)</span>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Assign Recruiters</Label>
              <div className="border rounded-lg p-3 max-h-40 overflow-y-auto space-y-2">
                {recruiters.map((rec) => (
                  <label 
                    key={rec.id} 
                    className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={createForm.recruiter_ids.includes(rec.id)}
                      onChange={() => toggleRecruiter(rec.id)}
                      className="rounded border-slate-300 text-[#7CB342] focus:ring-[#7CB342]"
                    />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-slate-700">{rec.name}</p>
                      <p className="text-xs text-slate-400">{rec.email}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label>Assign Companies</Label>
              <div className="border rounded-lg p-3 max-h-40 overflow-y-auto space-y-2">
                {companies.map((comp) => (
                  <label 
                    key={comp.id} 
                    className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={createForm.company_ids.includes(comp.id)}
                      onChange={() => toggleCompany(comp.id)}
                      className="rounded border-slate-300 text-[#7CB342] focus:ring-[#7CB342]"
                    />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-slate-700">{comp.name}</p>
                      <p className="text-xs text-slate-400">{comp.industry || 'No industry'}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEdit(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleUpdate}
              className="bg-[#7CB342] hover:bg-[#689F38]"
            >
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDelete} onOpenChange={setShowDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading text-red-600 flex items-center gap-2">
              <AlertCircle className="w-5 h-5" /> Disable Team
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to disable <strong>{selectedTeam?.name}</strong>? 
              This will remove the team from active listings but will not delete any data.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDelete(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              data-testid="confirm-delete-btn"
            >
              Disable Team
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Team Card Component
function TeamCard({ team, onEdit, onDelete, disabled }) {
  return (
    <Card className={`border-slate-200 ${disabled ? 'bg-slate-50' : 'hover:shadow-md'} transition-shadow`}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center">
              <Users className="w-6 h-6 text-[#7CB342]" />
            </div>
            <div>
              <h3 className="font-heading font-semibold text-lg text-slate-900">{team.name}</h3>
              <p className="text-sm text-slate-500">Managed by {team.employer_name || 'Unknown'}</p>
            </div>
          </div>
          {!disabled && (
            <div className="flex gap-1">
              <Button variant="ghost" size="sm" onClick={onEdit} data-testid={`edit-team-${team.id}`}>
                <Edit2 className="w-4 h-4" />
              </Button>
              <Button variant="ghost" size="sm" onClick={onDelete} className="text-red-500 hover:text-red-600" data-testid={`delete-team-${team.id}`}>
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-3 gap-4 text-center border-t border-slate-100 pt-4">
          <div>
            <p className="text-lg font-semibold text-slate-900">{team.recruiter_ids?.length || 0}</p>
            <p className="text-xs text-slate-500">Recruiters</p>
          </div>
          <div>
            <p className="text-lg font-semibold text-slate-900">{team.company_ids?.length || 0}</p>
            <p className="text-xs text-slate-500">Companies</p>
          </div>
          <div>
            <p className="text-lg font-semibold text-[#7CB342]">{team.active_jobs_count || 0}</p>
            <p className="text-xs text-slate-500">Active Jobs</p>
          </div>
        </div>

        {/* Members Preview */}
        {(team.recruiter_names?.length > 0 || team.company_names?.length > 0) && (
          <div className="mt-4 pt-4 border-t border-slate-100">
            {team.recruiter_names?.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2">
                {team.recruiter_names.slice(0, 3).map((name, i) => (
                  <Badge key={i} variant="secondary" className="text-xs">
                    <UserCircle className="w-3 h-3 mr-1" />
                    {name}
                  </Badge>
                ))}
                {team.recruiter_names.length > 3 && (
                  <Badge variant="outline" className="text-xs">
                    +{team.recruiter_names.length - 3} more
                  </Badge>
                )}
              </div>
            )}
            {team.company_names?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {team.company_names.slice(0, 3).map((name, i) => (
                  <Badge key={i} variant="outline" className="text-xs">
                    <Building2 className="w-3 h-3 mr-1" />
                    {name}
                  </Badge>
                ))}
                {team.company_names.length > 3 && (
                  <Badge variant="outline" className="text-xs">
                    +{team.company_names.length - 3} more
                  </Badge>
                )}
              </div>
            )}
          </div>
        )}

        {disabled && (
          <Badge variant="secondary" className="mt-3 text-xs text-slate-400">
            Disabled
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}
