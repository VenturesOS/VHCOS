import { useState, useEffect, useCallback } from 'react';
import { attendanceAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { CalendarDays, Plus, Clock, CheckCircle2, XCircle, Loader2, FileText, AlertTriangle } from 'lucide-react';

const LEAVE_TYPES = [
  { value: 'casual', label: 'Casual Leave' },
  { value: 'sick', label: 'Sick Leave' },
  { value: 'earned', label: 'Earned/Privilege Leave' },
  { value: 'comp_off', label: 'Comp-Off' },
];

const STATUS_STYLES = {
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
};

export default function LeaveManagementPage() {
  const [requests, setRequests] = useState([]);
  const [balance, setBalance] = useState(null);
  const [holidays, setHolidays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showRequest, setShowRequest] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [req, bal, hol] = await Promise.all([
        attendanceAPI.getMyLeaveRequests({}),
        attendanceAPI.getMyLeaveBalance({}),
        attendanceAPI.getHolidays({}),
      ]);
      setRequests(req.data.requests || []);
      setBalance(bal.data);
      setHolidays(hol.data.holidays || []);
    } catch { toast.error('Failed to load leave data'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  const leaveTypes = [
    { key: 'casual', label: 'Casual', total: balance?.casual_leave_total || 0, used: balance?.casual_leave_used || 0 },
    { key: 'sick', label: 'Sick', total: balance?.sick_leave_total || 0, used: balance?.sick_leave_used || 0 },
    { key: 'earned', label: 'Earned', total: balance?.earned_leave_total || 0, used: balance?.earned_leave_used || 0 },
    { key: 'comp_off', label: 'Comp-Off', total: balance?.comp_off_total || 0, used: balance?.comp_off_used || 0 },
  ];

  return (
    <div className="space-y-6" data-testid="leave-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-blue-50 border border-blue-200"><CalendarDays className="h-5 w-5 text-blue-700" /></div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight" data-testid="leave-title">Leave Management</h1>
            <p className="text-sm text-muted-foreground">Request leaves and track your leave balance</p>
          </div>
        </div>
        <Button onClick={() => setShowRequest(true)} data-testid="request-leave-btn"><Plus className="h-4 w-4 mr-1" /> Request Leave</Button>
      </div>

      {/* Leave Balance Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="leave-balance-cards">
        {leaveTypes.map(lt => (
          <Card key={lt.key} className="text-center">
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground font-medium mb-1">{lt.label} Leave</p>
              <div className="text-2xl font-bold text-slate-900">{lt.total - lt.used}</div>
              <p className="text-[11px] text-muted-foreground mt-0.5">{lt.used} used of {lt.total}</p>
              <div className="w-full bg-slate-100 rounded-full h-1.5 mt-2">
                <div className={`h-1.5 rounded-full ${lt.used > lt.total * 0.8 ? 'bg-red-400' : 'bg-green-400'}`} style={{ width: `${lt.total > 0 ? Math.min(100, (lt.used / lt.total) * 100) : 0}%` }} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Holidays */}
      {holidays.length > 0 && (
        <Card data-testid="holidays-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2"><CalendarDays className="h-4 w-4 text-cyan-600" /> Holidays — {new Date().getFullYear()}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
              {holidays.map(h => {
                const d = new Date(h.date + 'T00:00:00');
                const isPast = d < new Date(new Date().toDateString());
                return (
                  <div key={h.id} className={`flex items-center gap-3 px-3 py-2 rounded-lg border ${isPast ? 'opacity-50' : ''} ${h.is_optional ? 'border-dashed' : ''}`}>
                    <div className="text-center min-w-[40px]">
                      <div className="text-lg font-bold text-cyan-700">{d.getDate()}</div>
                      <div className="text-[10px] text-muted-foreground uppercase">{d.toLocaleDateString('en-IN', { month: 'short', timeZone: 'Asia/Kolkata' })}</div>
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{h.name}</p>
                      <p className="text-[10px] text-muted-foreground capitalize">{h.holiday_type}{h.is_optional ? ' (Optional)' : ''}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Leave Requests History */}
      <Card data-testid="leave-requests-list">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">My Leave Requests</CardTitle>
        </CardHeader>
        <CardContent>
          {requests.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No leave requests yet.</p>
          ) : (
            <div className="space-y-3">
              {requests.map(r => (
                <div key={r.id} className="flex items-center justify-between border rounded-lg px-4 py-3" data-testid={`leave-request-${r.id}`}>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium capitalize">{r.leave_type} Leave</p>
                      <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${STATUS_STYLES[r.status] || ''}`}>{r.status}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {new Date(r.start_date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' })}
                      {r.start_date !== r.end_date && ` — ${new Date(r.end_date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' })}`}
                      {r.half_day && ' (Half Day)'}
                      {' '}· {r.days} day{r.days !== 1 ? 's' : ''}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">{r.reason}</p>
                    {r.admin_notes && <p className="text-xs text-blue-600 mt-0.5">Admin: {r.admin_notes}</p>}
                  </div>
                  <div className="text-right shrink-0 ml-3">
                    {r.status === 'approved' && <CheckCircle2 className="h-5 w-5 text-green-500" />}
                    {r.status === 'rejected' && <XCircle className="h-5 w-5 text-red-500" />}
                    {r.status === 'pending' && <Clock className="h-5 w-5 text-amber-500" />}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Request Leave Dialog */}
      <LeaveRequestDialog open={showRequest} onClose={() => setShowRequest(false)} onCreated={loadData} balance={balance} />
    </div>
  );
}

function LeaveRequestDialog({ open, onClose, onCreated, balance }) {
  const [leaveType, setLeaveType] = useState('casual');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reason, setReason] = useState('');
  const [halfDay, setHalfDay] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!startDate || !endDate || !reason.trim()) return toast.error('Please fill all fields');
    setSubmitting(true);
    try {
      await attendanceAPI.requestLeave({
        leave_type: leaveType,
        start_date: startDate,
        end_date: endDate,
        reason: reason.trim(),
        half_day: halfDay,
      });
      toast.success('Leave request submitted!');
      onClose();
      onCreated();
      setStartDate(''); setEndDate(''); setReason(''); setHalfDay(false);
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to submit'); }
    finally { setSubmitting(false); }
  };

  const totalKey = `${leaveType}_total`;
  const usedKey = `${leaveType}_used`;
  const available = (balance?.[totalKey] || 0) - (balance?.[usedKey] || 0);

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md" data-testid="leave-request-dialog">
        <DialogHeader>
          <DialogTitle>Request Leave</DialogTitle>
          <DialogDescription>Submit a new leave request for approval</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label className="text-sm font-medium">Leave Type</Label>
            <Select value={leaveType} onValueChange={setLeaveType}>
              <SelectTrigger className="mt-1.5" data-testid="leave-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {LEAVE_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground mt-1">Available: {available} days</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-sm font-medium">From</Label>
              <Input type="date" value={startDate} onChange={e => { setStartDate(e.target.value); if (!endDate) setEndDate(e.target.value); }} className="mt-1.5" data-testid="start-date" />
            </div>
            <div>
              <Label className="text-sm font-medium">To</Label>
              <Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="mt-1.5" data-testid="end-date" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="half-day" checked={halfDay} onChange={e => setHalfDay(e.target.checked)} className="rounded" />
            <Label htmlFor="half-day" className="text-sm">Half day only</Label>
          </div>
          <div>
            <Label className="text-sm font-medium">Reason</Label>
            <Input value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason for leave..." className="mt-1.5" data-testid="leave-reason" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting} data-testid="submit-leave-btn">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
            Submit Request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
