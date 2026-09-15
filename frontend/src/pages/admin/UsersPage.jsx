import { useState, useEffect } from 'react';
import { userAPI, companyAPI, accountManagerAPI, teamLeadAPI } from '../../lib/api';
import api from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { Search, Edit2, Trash2, Users, UserCircle, Plus, Key, UserCheck, Building2, Shield, AtSign, Crown } from 'lucide-react';

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [employers, setEmployers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [teamFilter, setTeamFilter] = useState('all');
  const [teamsList, setTeamsList] = useState([]);
  
  // Dialog states
  const [editingUser, setEditingUser] = useState(null);
  const [editForm, setEditForm] = useState({ name: '', phone: '', is_active: true, role: '' });
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [createForm, setCreateForm] = useState({ email: '', password: '', name: '', role: 'candidate', phone: '', company_id: '' });
  const [showResetPasswordDialog, setShowResetPasswordDialog] = useState(null);
  const [newPassword, setNewPassword] = useState('');
  const [showAMDialog, setShowAMDialog] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [selectedCompanies, setSelectedCompanies] = useState([]);
  // Team Lead promotion dialog — pick an employer from a dropdown
  const [tlDialog, setTlDialog] = useState(null);   // { recruiter } | null
  const [tlEmployerId, setTlEmployerId] = useState('');
  const [tlBusy, setTlBusy] = useState(false);

  // Phase 55.4 — migrate email dialog
  const [showMigrateDialog, setShowMigrateDialog] = useState(null);
  const [migrateNewEmail, setMigrateNewEmail] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [usersRes, employersRes, companiesRes, teamsRes] = await Promise.all([
        userAPI.getAll(),
        userAPI.getEmployers().catch(() => ({ data: [] })),
        companyAPI.getAll().catch(() => ({ data: [] })),
        api.get('/teams').catch(() => ({ data: [] })),
      ]);
      setUsers(usersRes.data);
      setEmployers(employersRes.data || []);
      setCompanies(companiesRes.data || []);
      setTeamsList((teamsRes.data || []).filter(t => t.status !== 'deleted'));
    } catch (error) {
      toast.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (user) => {
    setEditingUser(user);
    setEditForm({
      name: user.name,
      phone: user.phone || '',
      is_active: user.is_active,
      role: user.role,
    });
  };

  const handleUpdate = async () => {
    try {
      await userAPI.update(editingUser.id, editForm);
      toast.success('User updated successfully');
      setEditingUser(null);
      loadData();
    } catch (error) {
      toast.error('Failed to update user');
    }
  };

  const handleToggleTeamLead = async (u) => {
    if (u.is_team_lead) {
      if (!window.confirm(`Revoke Team Lead access for ${u.name}?`)) return;
      try {
        await teamLeadAPI.revoke(u.id);
        toast.success(`${u.name} is no longer a Team Lead`);
        loadData();
      } catch (e) {
        toast.error(e?.response?.data?.detail || 'Team Lead update failed');
      }
      return;
    }
    // Open dropdown dialog to pick employer
    setTlEmployerId('');
    setTlDialog({ recruiter: u });
  };

  const confirmTeamLeadGrant = async () => {
    if (!tlDialog?.recruiter || !tlEmployerId) return;
    setTlBusy(true);
    try {
      await teamLeadAPI.grant(tlDialog.recruiter.id, tlEmployerId);
      toast.success(`${tlDialog.recruiter.name} is now a Team Lead`);
      setTlDialog(null);
      setTlEmployerId('');
      loadData();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Team Lead promotion failed');
    } finally {
      setTlBusy(false);
    }
  };

  const handleCreate = async () => {
    // Validation
    if (!createForm.email || !createForm.password || !createForm.name) {
      toast.error('Please fill in all required fields');
      return;
    }
    
    try {
      await userAPI.create(createForm);
      toast.success('User created successfully');
      setShowCreateDialog(false);
      setCreateForm({ email: '', password: '', name: '', role: 'candidate', phone: '', company_id: '' });
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create user');
    }
  };

  const handleDelete = async (userId) => {
    if (!window.confirm('Are you sure you want to deactivate this user?')) return;
    
    try {
      await userAPI.delete(userId);
      toast.success('User deactivated successfully');
      loadData();
    } catch (error) {
      toast.error('Failed to deactivate user');
    }
  };

  const handleToggleStatus = async (userId) => {
    try {
      const result = await userAPI.toggleStatus(userId);
      toast.success(result.data.message);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to toggle user status');
    }
  };

  const handleResetPassword = async () => {
    if (!newPassword || newPassword.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    
    try {
      await userAPI.resetPassword(showResetPasswordDialog.id, newPassword);
      toast.success('Password reset successfully');
      setShowResetPasswordDialog(null);
      setNewPassword('');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to reset password');
    }
  };

  const handleMigrateEmail = async () => {
    const trimmed = (migrateNewEmail || '').trim().toLowerCase();
    if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      toast.error('Enter a valid new email');
      return;
    }
    if (trimmed === (showMigrateDialog?.email || '').toLowerCase()) {
      toast.error('New email is identical to current email');
      return;
    }
    try {
      const res = await userAPI.migrateEmail(showMigrateDialog.id, trimmed);
      toast.success(res.data?.message || 'Email migrated');
      setShowMigrateDialog(null);
      setMigrateNewEmail('');
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to migrate email');
    }
  };

  const handleOpenAMDialog = (user) => {
    const existing = (user.assigned_companies || []).map(c => typeof c === 'string' ? c : c.id);
    setSelectedCompanies(existing);
    setShowAMDialog(user);
  };

  const handleSaveAM = async () => {
    try {
      if (selectedCompanies.length === 0) {
        // Remove AM status
        await accountManagerAPI.assign(showAMDialog.id, []);
        toast.success('Account manager access removed');
      } else {
        await accountManagerAPI.assign(showAMDialog.id, selectedCompanies);
        toast.success('Account manager companies updated');
      }
      setShowAMDialog(null);
      setSelectedCompanies([]);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update account manager');
    }
  };

  const toggleCompanySelection = (companyId) => {
    setSelectedCompanies(prev =>
      prev.includes(companyId) ? prev.filter(id => id !== companyId) : [...prev, companyId]
    );
  };

  // Filter users
  const filteredUsers = users.filter((user) => {
    const matchesSearch =
      user.name.toLowerCase().includes(search.toLowerCase()) ||
      user.email.toLowerCase().includes(search.toLowerCase());
    const matchesRole = roleFilter === 'all' || user.role === roleFilter;
    let matchesTeam = true;
    if (teamFilter !== 'all') {
      const team = teamsList.find(t => t.id === teamFilter);
      const rids = (team && team.recruiter_ids) || [];
      matchesTeam = rids.includes(user.id);
    }
    return matchesSearch && matchesRole && matchesTeam;
  });

  // Group by role for counts
  const roleCounts = users.reduce((acc, user) => {
    acc[user.role] = (acc[user.role] || 0) + 1;
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="users-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">User Management</h1>
          <p className="text-slate-500 mt-1">Create, manage, and control user access</p>
        </div>
        <div className="flex gap-3">
          <Button 
            onClick={() => setShowCreateDialog(true)}
            className="bg-[#7CB342] hover:bg-[#689F38]"
            data-testid="create-user-btn"
          >
            <Plus className="w-4 h-4 mr-2" /> Create User
          </Button>
        </div>
      </div>

      {/* Phase 55.5 — direct admins to the Teams page for recruiter assignment */}
      <div
        className="border border-purple-200 bg-purple-50 rounded-lg p-3 text-sm text-purple-900 flex items-center gap-3"
        data-testid="recruiter-assignment-hint"
      >
        <Users className="w-4 h-4 shrink-0" />
        <div>
          <b>Assigning a recruiter to an employer / team?</b>
          {' '}Head over to the <a href="/admin/teams" className="underline font-medium">Teams</a> page —
          open the team and edit its members. (Account-manager access for recruiters
          stays on this page via the shield icon.)
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-slate-900">{users.length}</div>
            <div className="text-sm text-slate-500">Total Users</div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-blue-600">{roleCounts.admin || 0}</div>
            <div className="text-sm text-slate-500">Admins</div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-purple-600">{roleCounts.employer || 0}</div>
            <div className="text-sm text-slate-500">Employers</div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-amber-600">{roleCounts.recruiter || 0}</div>
            <div className="text-sm text-slate-500">Recruiters</div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-green-600">{roleCounts.candidate || 0}</div>
            <div className="text-sm text-slate-500">Candidates</div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search by name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
            data-testid="users-search-input"
          />
        </div>
        <Select value={roleFilter} onValueChange={setRoleFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Filter by role" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Roles</SelectItem>
            <SelectItem value="admin">Admin</SelectItem>
            <SelectItem value="employer">Employer</SelectItem>
            <SelectItem value="recruiter">Recruiter</SelectItem>
            <SelectItem value="candidate">Candidate</SelectItem>
          </SelectContent>
        </Select>
        <Select value={teamFilter} onValueChange={setTeamFilter}>
          <SelectTrigger className="w-48" data-testid="users-team-filter">
            <SelectValue placeholder="Filter by team" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Teams</SelectItem>
            {teamsList.map(t => (
              <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Users Table */}
      <Card className="border-slate-200">
        <CardHeader className="border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Users className="w-5 h-5 text-[#7CB342]" />
            Users ({filteredUsers.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead className="bg-slate-50 border-b border-slate-100">
                <tr>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">User</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Email</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Role</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Status</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Joined</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-slate-50">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                          <span className="text-[#7CB342] font-semibold">
                            {user.name.charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <span className="font-medium text-slate-900">{user.name}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-slate-600">{user.email}</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1">
                        <span className={`capitalize px-2 py-1 rounded-full text-xs font-medium ${
                          user.role === 'admin' ? 'bg-blue-100 text-blue-700' :
                          user.role === 'employer' ? 'bg-purple-100 text-purple-700' :
                          user.role === 'recruiter' ? 'bg-amber-100 text-amber-700' :
                          'bg-green-100 text-green-700'
                        }`}>
                          {user.role}
                        </span>
                        {user.is_account_manager && (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                            AM
                          </span>
                        )}
                        {user.is_team_lead && (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700 flex items-center gap-1" data-testid={`tl-badge-${user.id}`}>
                            <Crown className="w-3 h-3" /> Team Lead
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                        user.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                      }`}>
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-500 text-sm">
                      {new Date(user.created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleEdit(user)}
                          title="Edit user"
                          data-testid={`edit-user-${user.id}`}
                        >
                          <Edit2 className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setShowResetPasswordDialog(user)}
                          title="Reset password"
                          data-testid={`reset-pwd-${user.id}`}
                        >
                          <Key className="w-4 h-4 text-amber-600" />
                        </Button>
                        {user.is_active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => { setShowMigrateDialog(user); setMigrateNewEmail(''); }}
                            title="Migrate email (rename, keeps all records)"
                            data-testid={`migrate-email-${user.id}`}
                          >
                            <AtSign className="w-4 h-4 text-cyan-600" />
                          </Button>
                        )}
                        {user.role === 'recruiter' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenAMDialog(user)}
                            title="Account Manager settings"
                            data-testid={`am-settings-${user.id}`}
                          >
                            <Shield className={`w-4 h-4 ${user.is_account_manager ? 'text-indigo-600' : 'text-slate-400'}`} />
                          </Button>
                        )}
                        {user.role === 'recruiter' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleToggleTeamLead(user)}
                            title={user.is_team_lead ? 'Revoke Team Lead access' : 'Grant Team Lead access'}
                            data-testid={`tl-toggle-${user.id}`}
                          >
                            <Crown className={`w-4 h-4 ${user.is_team_lead ? 'text-amber-600' : 'text-slate-400'}`} />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleToggleStatus(user.id)}
                          title={user.is_active ? 'Deactivate' : 'Activate'}
                          data-testid={`toggle-${user.id}`}
                        >
                          <UserCheck className={`w-4 h-4 ${user.is_active ? 'text-green-600' : 'text-slate-400'}`} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-600 hover:text-red-700 hover:bg-red-50"
                          onClick={() => handleDelete(user.id)}
                          title="Delete user"
                          data-testid={`delete-user-${user.id}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filteredUsers.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-8">
                      <UserCircle className="w-12 h-12 text-slate-300 mx-auto mb-2" />
                      <p className="text-slate-500">No users found</p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Edit User Dialog */}
      <Dialog open={!!editingUser} onOpenChange={() => setEditingUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Edit User</DialogTitle>
            <DialogDescription>Update user information</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                data-testid="edit-user-name"
              />
            </div>
            <div className="space-y-2">
              <Label>Phone</Label>
              <Input
                value={editForm.phone}
                onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                placeholder="Optional"
                data-testid="edit-user-phone"
              />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select
                value={editForm.role}
                onValueChange={(value) => setEditForm({ ...editForm, role: value })}
                data-testid="edit-user-role"
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="employer">Employer</SelectItem>
                  <SelectItem value="recruiter">Recruiter</SelectItem>
                  <SelectItem value="candidate">Candidate</SelectItem>
                </SelectContent>
              </Select>
              {editingUser && editForm.role !== editingUser.role && (
                <p className="text-xs text-amber-600 flex items-center gap-1 mt-1">
                  <Shield className="w-3 h-3" />
                  Role will change from <span className="font-semibold">{editingUser.role}</span> to <span className="font-semibold">{editForm.role}</span>
                </p>
              )}
            </div>
            <div className="flex items-center justify-between">
              <Label>Active Status</Label>
              <Switch
                checked={editForm.is_active}
                onCheckedChange={(checked) => setEditForm({ ...editForm, is_active: checked })}
                data-testid="edit-user-status"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingUser(null)}>Cancel</Button>
            <Button onClick={handleUpdate} className="bg-[#7CB342] hover:bg-[#689F38]">Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create User Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Create New User</DialogTitle>
            <DialogDescription>Add a new user to the system</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Role *</Label>
              <Select 
                value={createForm.role} 
                onValueChange={(value) => setCreateForm({ ...createForm, role: value })}
              >
                <SelectTrigger data-testid="create-user-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="employer">Employer</SelectItem>
                  <SelectItem value="recruiter">Recruiter</SelectItem>
                  <SelectItem value="candidate">Candidate</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Name *</Label>
              <Input
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                placeholder="Full name"
                data-testid="create-user-name"
              />
            </div>
            <div className="space-y-2">
              <Label>Email *</Label>
              <Input
                type="email"
                value={createForm.email}
                onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                placeholder="user@example.com"
                data-testid="create-user-email"
              />
            </div>
            <div className="space-y-2">
              <Label>Password *</Label>
              <Input
                type="password"
                value={createForm.password}
                onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                placeholder="Minimum 8 characters"
                data-testid="create-user-password"
              />
            </div>
            <div className="space-y-2">
              <Label>Phone</Label>
              <Input
                value={createForm.phone}
                onChange={(e) => setCreateForm({ ...createForm, phone: e.target.value })}
                placeholder="Optional"
                data-testid="create-user-phone"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>Cancel</Button>
            <Button onClick={handleCreate} className="bg-[#7CB342] hover:bg-[#689F38]">Create User</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset Password Dialog */}
      <Dialog open={!!showResetPasswordDialog} onOpenChange={() => setShowResetPasswordDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Reset Password</DialogTitle>
            <DialogDescription>
              Set a new password for {showResetPasswordDialog?.name}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>New Password</Label>
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                data-testid="reset-password-input"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowResetPasswordDialog(null)}>Cancel</Button>
            <Button onClick={handleResetPassword} className="bg-amber-600 hover:bg-amber-700">Reset Password</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Migrate Email Dialog (Phase 55.4) */}
      <Dialog open={!!showMigrateDialog} onOpenChange={() => setShowMigrateDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Migrate Email</DialogTitle>
            <DialogDescription>
              Rename <b>{showMigrateDialog?.name}</b>'s login email. All records
              (mandates, captures, applications, attendance) stay attached — only
              the email changes.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Current email</Label>
              <Input value={showMigrateDialog?.email || ''} disabled data-testid="migrate-email-current" />
            </div>
            <div className="space-y-2">
              <Label>New email</Label>
              <Input
                type="email"
                value={migrateNewEmail}
                onChange={(e) => setMigrateNewEmail(e.target.value)}
                placeholder="e.g. hr20@vhc.in"
                data-testid="migrate-email-new"
                autoFocus
              />
              <p className="text-xs text-slate-500">
                The destination email must not be in use by an active account. If
                it was previously used by a deactivated user, it has already been
                archived and is free to take.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowMigrateDialog(null)} data-testid="migrate-email-cancel">Cancel</Button>
            <Button onClick={handleMigrateEmail} className="bg-cyan-600 hover:bg-cyan-700" data-testid="migrate-email-submit">Migrate Email</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Account Manager Dialog */}
      <Dialog open={!!showAMDialog} onOpenChange={() => setShowAMDialog(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">Account Manager Settings</DialogTitle>
            <DialogDescription>
              Assign companies to {showAMDialog?.name} as Account Manager.
              They'll get employer-level access (minus revenue/team data).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <Label>Select Companies</Label>
            <div className="max-h-60 overflow-y-auto space-y-2 border rounded-lg p-3">
              {companies.length === 0 ? (
                <p className="text-sm text-slate-500 text-center py-4">No companies found</p>
              ) : (
                companies.map((company) => (
                  <label
                    key={company.id}
                    className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer hover:bg-slate-50 ${
                      selectedCompanies.includes(company.id) ? 'bg-indigo-50 border border-indigo-200' : 'border border-transparent'
                    }`}
                    data-testid={`am-company-${company.id}`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedCompanies.includes(company.id)}
                      onChange={() => toggleCompanySelection(company.id)}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm text-slate-900 truncate">{company.name}</p>
                      {company.industry && <p className="text-xs text-slate-500">{company.industry}</p>}
                    </div>
                  </label>
                ))
              )}
            </div>
            <p className="text-xs text-slate-500">
              {selectedCompanies.length} company(ies) selected.
              {selectedCompanies.length === 0 && ' Saving with none will remove Account Manager access.'}
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAMDialog(null)}>Cancel</Button>
            <Button onClick={handleSaveAM} className="bg-indigo-600 hover:bg-indigo-700" data-testid="save-am-btn">
              Save Account Manager
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Team Lead promotion dialog — pick an employer from a searchable dropdown */}
      <Dialog open={!!tlDialog} onOpenChange={(open) => !open && setTlDialog(null)}>
        <DialogContent data-testid="team-lead-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Crown className="w-5 h-5 text-amber-600" /> Promote to Team Lead
            </DialogTitle>
            <DialogDescription>
              <b>{tlDialog?.recruiter?.name}</b> will act as an employer: view team, assign
              mandates, and edit jobs. Financial data (billing, commissions, margins) stays hidden.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <label className="text-sm font-medium text-slate-700">Which employer's team?</label>
            <Select value={tlEmployerId} onValueChange={setTlEmployerId}>
              <SelectTrigger data-testid="tl-employer-select">
                <SelectValue placeholder="Select an employer…" />
              </SelectTrigger>
              <SelectContent>
                {employers.length === 0 ? (
                  <div className="px-3 py-2 text-sm text-muted-foreground">No employers found</div>
                ) : (
                  employers.map((emp) => (
                    <SelectItem key={emp.id} value={emp.id} data-testid={`tl-employer-opt-${emp.id}`}>
                      <span className="font-medium">{emp.name}</span>
                      <span className="text-slate-500 ml-2 text-xs">{emp.email}</span>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
            <p className="text-xs text-slate-500">
              The recruiter must already be a member of this employer's team. Only the employer
              or an admin can revoke this later.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTlDialog(null)} disabled={tlBusy}>
              Cancel
            </Button>
            <Button
              onClick={confirmTeamLeadGrant}
              disabled={!tlEmployerId || tlBusy}
              className="bg-amber-600 hover:bg-amber-700"
              data-testid="tl-confirm-btn"
            >
              {tlBusy ? 'Promoting…' : 'Promote to Team Lead'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
