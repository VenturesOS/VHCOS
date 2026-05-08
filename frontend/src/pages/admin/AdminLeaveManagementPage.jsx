import { useState, useEffect, useCallback } from 'react';
import { attendanceAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import { Shield, CheckCircle2, XCircle, Clock, Loader2, Plus, Pencil, Trash2, Calendar, Users, Settings } from 'lucide-react';

const LEAVE_TYPES = ['casual', 'sick', 'earned', 'comp_off'];
const LEAVE_LABELS = { casual: 'Casual', sick: 'Sick', earned: 'Earned', comp_off: 'Comp-Off' };

export default function AdminLeaveManagementPage() {
  const [activeTab, setActiveTab] = useState('approvals');

  return (
    <div className="space-y-6" data-testid="admin-leave-page">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-violet-50 border border-violet-200"><Shield className="h-5 w-5 text-violet-700" /></div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight" data-testid="admin-leave-title">Leave Management</h1>
          <p className="text-sm text-muted-foreground">Approve leave requests, manage balances & holidays</p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList data-testid="admin-leave-tabs">
          <TabsTrigger value="approvals"><Clock className="h-3.5 w-3.5 mr-1" /> Approvals</TabsTrigger>
          <TabsTrigger value="balances"><Users className="h-3.5 w-3.5 mr-1" /> Leave Banks</TabsTrigger>
          <TabsTrigger value="holidays"><Calendar className="h-3.5 w-3.5 mr-1" /> Holidays</TabsTrigger>
        </TabsList>

        <TabsContent value="approvals"><LeaveApprovals /></TabsContent>
        <TabsContent value="balances"><LeaveBalances /></TabsContent>
        <TabsContent value="holidays"><HolidayManager /></TabsContent>
      </Tabs>
    </div>
  );
}

// ── Leave Approvals Tab ──

function LeaveApprovals() {
  const [pending, setPending] = useState([]);
  const [allRequests, setAllRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(null);

  const loadData = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([
        attendanceAPI.getPendingLeaves(),
        attendanceAPI.getAllLeaveRequests({}),
      ]);
      setPending(p.data.requests || []);
      setAllRequests(a.data.requests || []);
    } catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleAction = async (id, action) => {
    setActing(id);
    try {
      if (action === 'approve') await attendanceAPI.approveLeave(id, {});
      else await attendanceAPI.rejectLeave(id, {});
      toast.success(`Leave ${action}d!`);
      loadData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setActing(null); }
  };

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-6 mt-4">
      {/* Pending */}
      <Card data-testid="pending-approvals-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-500" /> Pending Approvals
            {pending.length > 0 && <Badge className="bg-amber-100 text-amber-700">{pending.length}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {pending.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">No pending requests.</p>
          ) : (
            <div className="space-y-3">
              {pending.map(r => (
                <div key={r.id} className="flex items-center justify-between border rounded-lg px-4 py-3" data-testid={`pending-${r.id}`}>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium">{r.user_name}</p>
                      <Badge variant="outline" className="text-[10px] capitalize">{r.user_role}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 capitalize">
                      {r.leave_type} Leave · {r.days} day{r.days !== 1 ? 's' : ''}
                      {r.half_day && ' (Half Day)'}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(r.start_date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' })}
                      {r.start_date !== r.end_date && ` — ${new Date(r.end_date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' })}`}
                    </p>
                    <p className="text-xs text-slate-600 mt-0.5">{r.reason}</p>
                  </div>
                  <div className="flex gap-2 shrink-0 ml-3">
                    <Button size="sm" onClick={() => handleAction(r.id, 'approve')} disabled={!!acting} className="bg-green-600 hover:bg-green-700 h-8" data-testid={`approve-${r.id}`}>
                      {acting === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5 mr-1" />} Approve
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => handleAction(r.id, 'reject')} disabled={!!acting} className="h-8" data-testid={`reject-${r.id}`}>
                      <XCircle className="h-3.5 w-3.5 mr-1" /> Reject
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* All requests */}
      <Card data-testid="all-requests-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">All Leave Requests — {new Date().getFullYear()}</CardTitle>
        </CardHeader>
        <CardContent>
          {allRequests.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">No requests found.</p>
          ) : (
            <div className="overflow-auto max-h-[400px]">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Employee</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Type</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Dates</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">Days</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {allRequests.map(r => (
                    <tr key={r.id} className="border-b hover:bg-slate-50/50">
                      <td className="px-3 py-2"><p className="font-medium text-xs">{r.user_name}</p><p className="text-[10px] text-muted-foreground">{r.user_email}</p></td>
                      <td className="px-3 py-2 capitalize text-xs">{r.leave_type}</td>
                      <td className="px-3 py-2 text-xs">{r.start_date}{r.start_date !== r.end_date && ` — ${r.end_date}`}</td>
                      <td className="px-3 py-2 text-center text-xs">{r.days}</td>
                      <td className="px-3 py-2 text-center">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full capitalize ${r.status === 'approved' ? 'bg-green-100 text-green-700' : r.status === 'rejected' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>{r.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Leave Balances Tab ──

function LeaveBalances() {
  const [balances, setBalances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editUser, setEditUser] = useState(null);

  const loadData = useCallback(async () => {
    try {
      const res = await attendanceAPI.getAllLeaveBalances({});
      setBalances(res.data.balances || []);
    } catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="mt-4">
      <Card data-testid="leave-balances-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Leave Banks — {new Date().getFullYear()}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto">
            <table className="w-full text-sm" data-testid="balances-table">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Employee</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Role</th>
                  {LEAVE_TYPES.map(t => (
                    <th key={t} className="px-3 py-2 text-center text-xs font-semibold text-slate-500">{LEAVE_LABELS[t]}<br /><span className="font-normal text-[10px]">(Used/Total)</span></th>
                  ))}
                  <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">Action</th>
                </tr>
              </thead>
              <tbody>
                {balances.map(b => (
                  <tr key={b.user_id} className="border-b hover:bg-slate-50/50">
                    <td className="px-3 py-2"><p className="font-medium text-xs">{b.name}</p><p className="text-[10px] text-muted-foreground">{b.email}</p></td>
                    <td className="px-3 py-2 capitalize text-xs">{b.role}</td>
                    {LEAVE_TYPES.map(t => (
                      <td key={t} className="px-3 py-2 text-center text-xs">
                        <span className="font-medium">{b[`${t}_leave_used`]}</span>
                        <span className="text-muted-foreground">/{b[`${t}_leave_total`]}</span>
                      </td>
                    ))}
                    <td className="px-3 py-2 text-center">
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditUser(b)} data-testid={`edit-balance-${b.user_id}`}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      {editUser && <EditBalanceDialog user={editUser} onClose={() => setEditUser(null)} onSaved={loadData} />}
    </div>
  );
}

function EditBalanceDialog({ user, onClose, onSaved }) {
  const [casual, setCasual] = useState(user.casual_leave_total || 0);
  const [sick, setSick] = useState(user.sick_leave_total || 0);
  const [earned, setEarned] = useState(user.earned_leave_total || 0);
  const [compOff, setCompOff] = useState(user.comp_off_total || 0);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await attendanceAPI.setUserLeaveBalance(user.user_id, {
        casual_leave: casual, sick_leave: sick, earned_leave: earned, comp_off: compOff,
      });
      toast.success(`Leave balance updated for ${user.name}`);
      onClose(); onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-sm" data-testid="edit-balance-dialog">
        <DialogHeader>
          <DialogTitle>Set Leave Balance</DialogTitle>
          <DialogDescription>{user.name} ({user.role})</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {[['Casual Leave', casual, setCasual], ['Sick Leave', sick, setSick], ['Earned Leave', earned, setEarned], ['Comp-Off', compOff, setCompOff]].map(([label, val, setter]) => (
            <div key={label} className="flex items-center justify-between gap-3">
              <Label className="text-sm min-w-[100px]">{label}</Label>
              <Input type="number" value={val} onChange={e => setter(parseInt(e.target.value) || 0)} className="w-20 text-center" min={0} />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving} data-testid="save-balance-btn">
            {saving && <Loader2 className="h-4 w-4 animate-spin mr-1" />} Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Holiday Manager Tab ──

function HolidayManager() {
  const [holidays, setHolidays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editHoliday, setEditHoliday] = useState(null);

  const loadData = useCallback(async () => {
    try {
      const res = await attendanceAPI.getHolidays({});
      setHolidays(res.data.holidays || []);
    } catch { toast.error('Failed to load'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this holiday?')) return;
    try {
      await attendanceAPI.deleteHoliday(id);
      toast.success('Holiday deleted');
      loadData();
    } catch { toast.error('Failed to delete'); }
  };

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="mt-4 space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-sm text-muted-foreground">{holidays.length} holidays configured for {new Date().getFullYear()}</p>
        <Button size="sm" onClick={() => setShowCreate(true)} data-testid="add-holiday-btn"><Plus className="h-4 w-4 mr-1" /> Add Holiday</Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="holidays-grid">
        {holidays.map(h => {
          const d = new Date(h.date + 'T00:00:00');
          return (
            <Card key={h.id} className={`${h.is_optional ? 'border-dashed' : ''}`} data-testid={`holiday-${h.id}`}>
              <CardContent className="py-3 px-4 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="text-center min-w-[44px] py-1 rounded-lg bg-cyan-50">
                    <div className="text-lg font-bold text-cyan-700">{d.getDate()}</div>
                    <div className="text-[10px] text-cyan-600 uppercase">{d.toLocaleDateString('en-IN', { month: 'short', timeZone: 'Asia/Kolkata' })}</div>
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{h.name}</p>
                    <p className="text-[10px] text-muted-foreground capitalize">{h.holiday_type}{h.is_optional ? ' · Optional' : ''}</p>
                  </div>
                </div>
                <div className="flex gap-1 shrink-0 ml-2">
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditHoliday(h)}><Pencil className="h-3 w-3" /></Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-red-500 hover:text-red-600" onClick={() => handleDelete(h.id)}><Trash2 className="h-3 w-3" /></Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {(showCreate || editHoliday) && (
        <HolidayDialog
          holiday={editHoliday}
          onClose={() => { setShowCreate(false); setEditHoliday(null); }}
          onSaved={loadData}
        />
      )}
    </div>
  );
}

function HolidayDialog({ holiday, onClose, onSaved }) {
  const isEdit = !!holiday;
  const [name, setName] = useState(holiday?.name || '');
  const [dateVal, setDateVal] = useState(holiday?.date || '');
  const [hType, setHType] = useState(holiday?.holiday_type || 'national');
  const [optional, setOptional] = useState(holiday?.is_optional || false);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!name.trim() || !dateVal) return toast.error('Fill name and date');
    setSaving(true);
    try {
      if (isEdit) {
        await attendanceAPI.updateHoliday(holiday.id, { name: name.trim(), date: dateVal, holiday_type: hType, is_optional: optional });
        toast.success('Holiday updated');
      } else {
        await attendanceAPI.createHoliday({ name: name.trim(), date: dateVal, holiday_type: hType, is_optional: optional });
        toast.success('Holiday added');
      }
      onClose(); onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-sm" data-testid="holiday-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit' : 'Add'} Holiday</DialogTitle>
          <DialogDescription>Configure a holiday for the calendar</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div><Label>Name</Label><Input value={name} onChange={e => setName(e.target.value)} className="mt-1.5" placeholder="e.g. Republic Day" data-testid="holiday-name" /></div>
          <div><Label>Date</Label><Input type="date" value={dateVal} onChange={e => setDateVal(e.target.value)} className="mt-1.5" data-testid="holiday-date" /></div>
          <div>
            <Label>Type</Label>
            <Select value={hType} onValueChange={setHType}>
              <SelectTrigger className="mt-1.5" data-testid="holiday-type"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="national">National Holiday</SelectItem>
                <SelectItem value="festival">Festival</SelectItem>
                <SelectItem value="company">Company Holiday</SelectItem>
                <SelectItem value="optional">Optional</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="optional" checked={optional} onChange={e => setOptional(e.target.checked)} className="rounded" />
            <Label htmlFor="optional" className="text-sm">Optional holiday</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving} data-testid="save-holiday-btn">
            {saving && <Loader2 className="h-4 w-4 animate-spin mr-1" />} {isEdit ? 'Update' : 'Add'} Holiday
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
