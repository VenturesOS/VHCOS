import { useState, useEffect } from 'react';
import { userAPI, companyAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import { Search, Edit2, Trash2, Users, UserCircle, Plus, Key, UserCheck, Building2, Link } from 'lucide-react';

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [employers, setEmployers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  
  // Dialog states
  const [editingUser, setEditingUser] = useState(null);
  const [editForm, setEditForm] = useState({ name: '', phone: '', is_active: true });
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [createForm, setCreateForm] = useState({ email: '', password: '', name: '', role: 'candidate', phone: '', company_id: '' });
  const [showResetPasswordDialog, setShowResetPasswordDialog] = useState(null);
  const [newPassword, setNewPassword] = useState('');
  const [showAssignDialog, setShowAssignDialog] = useState(null);
  const [selectedEmployer, setSelectedEmployer] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [usersRes, employersRes] = await Promise.all([
        userAPI.getAll(),
        userAPI.getEmployers().catch(() => ({ data: [] }))
      ]);
      setUsers(usersRes.data);
      setEmployers(employersRes.data || []);
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

  const handleAssignRecruiter = async () => {
    if (!selectedEmployer) {
      toast.error('Please select an employer');
      return;
    }
    
    try {
      await userAPI.assignRecruiter(showAssignDialog.id, selectedEmployer);
      toast.success('Recruiter assigned to employer');
      setShowAssignDialog(null);
      setSelectedEmployer('');
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to assign recruiter');
    }
  };

  // Filter users
  const filteredUsers = users.filter((user) => {
    const matchesSearch = 
      user.name.toLowerCase().includes(search.toLowerCase()) ||
      user.email.toLowerCase().includes(search.toLowerCase());
    const matchesRole = roleFilter === 'all' || user.role === roleFilter;
    return matchesSearch && matchesRole;
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
          <h1 className="font-heading text-3xl font-bold text-slate-900">User Management</h1>
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
            <table className="w-full">
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
                      <span className={`capitalize px-2 py-1 rounded-full text-xs font-medium ${
                        user.role === 'admin' ? 'bg-blue-100 text-blue-700' :
                        user.role === 'employer' ? 'bg-purple-100 text-purple-700' :
                        user.role === 'recruiter' ? 'bg-amber-100 text-amber-700' :
                        'bg-green-100 text-green-700'
                      }`}>
                        {user.role}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                        user.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                      }`}>
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-500 text-sm">
                      {new Date(user.created_at).toLocaleDateString()}
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
                        {user.role === 'recruiter' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setShowAssignDialog(user)}
                            title="Assign to employer"
                            data-testid={`assign-${user.id}`}
                          >
                            <Link className="w-4 h-4 text-purple-600" />
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

      {/* Assign Recruiter Dialog */}
      <Dialog open={!!showAssignDialog} onOpenChange={() => setShowAssignDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">Assign Recruiter to Employer</DialogTitle>
            <DialogDescription>
              Link {showAssignDialog?.name} to an employer account
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Select Employer</Label>
              <Select value={selectedEmployer} onValueChange={setSelectedEmployer}>
                <SelectTrigger data-testid="assign-employer-select">
                  <SelectValue placeholder="Choose an employer..." />
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
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAssignDialog(null)}>Cancel</Button>
            <Button onClick={handleAssignRecruiter} className="bg-purple-600 hover:bg-purple-700">Assign</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
