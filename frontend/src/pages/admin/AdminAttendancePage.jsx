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
import { Users, Download, ChevronLeft, ChevronRight, Loader2, Clock, Calendar, UserCheck, UserX, AlertTriangle, Building2 } from 'lucide-react';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

const STATUS_STYLES = {
  present: 'bg-green-100 text-green-700',
  absent: 'bg-red-100 text-red-700',
  half_day: 'bg-amber-100 text-amber-700',
  leave: 'bg-blue-100 text-blue-700',
  wfh: 'bg-purple-100 text-purple-700',
  holiday: 'bg-cyan-100 text-cyan-700',
};

export default function AdminAttendancePage() {
  const [report, setReport] = useState(null);
  const [records, setRecords] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [showMarkDialog, setShowMarkDialog] = useState(false);
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [rep, all] = await Promise.all([
        attendanceAPI.getMonthlyReport({ month, year }),
        attendanceAPI.getAllAttendance({ month, year }),
      ]);
      setReport(rep.data);
      setRecords(all.data.records || []);
      setUsers(all.data.users || []);
    } catch { toast.error('Failed to load attendance'); }
    finally { setLoading(false); }
  }, [month, year]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await attendanceAPI.exportExcel({ month, year });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a'); a.href = url;
      a.download = `attendance_${year}_${String(month).padStart(2, '0')}.xlsx`;
      a.click(); URL.revokeObjectURL(url);
      toast.success('Report downloaded!');
    } catch { toast.error('Export failed'); }
    finally { setExporting(false); }
  };

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1); } else setMonth(m => m - 1); };
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1); } else setMonth(m => m + 1); };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  const summaries = report?.summaries || [];
  const holidays = report?.holidays || [];

  // Summary stats
  const totalPresent = summaries.reduce((s, u) => s + u.present, 0);
  const totalAbsent = summaries.reduce((s, u) => s + u.absent, 0);
  const totalLeaves = summaries.reduce((s, u) => s + u.leaves, 0);
  const totalLate = summaries.reduce((s, u) => s + u.late_count, 0);

  return (
    <div className="space-y-6" data-testid="admin-attendance-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-50 border border-indigo-200"><Users className="h-5 w-5 text-indigo-700" /></div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight" data-testid="admin-attendance-title">Attendance Dashboard</h1>
            <p className="text-sm text-muted-foreground">Monitor team attendance, manage overrides & export reports</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setShowMarkDialog(true)} data-testid="admin-mark-btn"><Calendar className="h-4 w-4 mr-1" /> Mark Attendance</Button>
          <Button onClick={handleExport} disabled={exporting} data-testid="export-btn">
            {exporting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Download className="h-4 w-4 mr-1" />}
            Export Excel
          </Button>
        </div>
      </div>

      {/* Month Selector + Stats */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={prevMonth}><ChevronLeft className="h-4 w-4" /></Button>
          <span className="text-sm font-semibold min-w-[140px] text-center">{MONTHS[month - 1]} {year}</span>
          <Button variant="ghost" size="icon" onClick={nextMonth}><ChevronRight className="h-4 w-4" /></Button>
        </div>
        <div className="flex gap-3 flex-wrap">
          <StatBadge icon={UserCheck} label="Present" value={totalPresent} color="green" />
          <StatBadge icon={UserX} label="Absent" value={totalAbsent} color="red" />
          <StatBadge icon={Calendar} label="Leaves" value={totalLeaves} color="blue" />
          <StatBadge icon={AlertTriangle} label="Late" value={totalLate} color="amber" />
          <StatBadge icon={Building2} label="Holidays" value={report?.holiday_count || 0} color="cyan" />
        </div>
      </div>

      {/* User Summary Table */}
      <Card data-testid="attendance-summary-table">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Monthly Summary — {summaries.length} employees</CardTitle>
        </CardHeader>
        <CardContent>
          {summaries.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No attendance data for this month.</p>
          ) : (
            <div className="overflow-auto">
              <table className="w-full text-sm" data-testid="summary-table">
                <thead className="bg-slate-50 sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">#</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Name</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Role</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">Present</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">Absent</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">Half Day</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">Leaves</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">WFH</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">Late</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">Hours</th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-slate-500">OT (min)</th>
                  </tr>
                </thead>
                <tbody>
                  {summaries.map((s, i) => (
                    <tr key={s.user_id} className="border-b hover:bg-slate-50/50">
                      <td className="px-3 py-2 text-muted-foreground">{i + 1}</td>
                      <td className="px-3 py-2">
                        <p className="font-medium">{s.name}</p>
                        <p className="text-xs text-muted-foreground">{s.email}</p>
                      </td>
                      <td className="px-3 py-2 capitalize">{s.role}</td>
                      <td className="px-3 py-2 text-center"><span className="bg-green-100 text-green-700 text-xs px-2 py-0.5 rounded-full">{s.present}</span></td>
                      <td className="px-3 py-2 text-center"><span className="bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded-full">{s.absent}</span></td>
                      <td className="px-3 py-2 text-center">{s.half_days}</td>
                      <td className="px-3 py-2 text-center"><span className="bg-blue-100 text-blue-700 text-xs px-2 py-0.5 rounded-full">{s.leaves}</span></td>
                      <td className="px-3 py-2 text-center">{s.wfh}</td>
                      <td className="px-3 py-2 text-center">{s.late_count > 0 ? <span className="bg-amber-100 text-amber-700 text-xs px-2 py-0.5 rounded-full">{s.late_count}</span> : 0}</td>
                      <td className="px-3 py-2 text-center font-medium">{s.total_hours}</td>
                      <td className="px-3 py-2 text-center">{s.total_overtime_minutes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <AdminMarkDialog open={showMarkDialog} onClose={() => setShowMarkDialog(false)} users={users} onMarked={loadData} />
    </div>
  );
}

function StatBadge({ icon: Icon, label, value, color }) {
  const colors = {
    green: 'bg-green-50 text-green-700 border-green-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    cyan: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  };
  return (
    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium ${colors[color]}`}>
      <Icon className="h-3.5 w-3.5" />
      <span>{label}: {value}</span>
    </div>
  );
}

function AdminMarkDialog({ open, onClose, users, onMarked }) {
  const [userId, setUserId] = useState('');
  const [dateVal, setDateVal] = useState('');
  const [status, setStatus] = useState('present');
  const [checkIn, setCheckIn] = useState('');
  const [checkOut, setCheckOut] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!userId || !dateVal) return toast.error('Select user and date');
    setSubmitting(true);
    try {
      await attendanceAPI.adminMark({
        user_id: userId,
        date: dateVal,
        status,
        check_in: checkIn || null,
        check_out: checkOut || null,
        notes: notes || null,
      });
      toast.success('Attendance marked!');
      onClose(); onMarked();
      setUserId(''); setDateVal(''); setCheckIn(''); setCheckOut(''); setNotes('');
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setSubmitting(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md" data-testid="admin-mark-dialog">
        <DialogHeader>
          <DialogTitle>Mark Attendance</DialogTitle>
          <DialogDescription>Override or manually mark attendance for a team member</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label>Employee</Label>
            <Select value={userId} onValueChange={setUserId}>
              <SelectTrigger className="mt-1.5" data-testid="mark-user-select"><SelectValue placeholder="Select employee" /></SelectTrigger>
              <SelectContent>
                {users.map(u => <SelectItem key={u.id} value={u.id}>{u.name} ({u.role})</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Date</Label><Input type="date" value={dateVal} onChange={e => setDateVal(e.target.value)} className="mt-1.5" data-testid="mark-date" /></div>
            <div>
              <Label>Status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="mt-1.5" data-testid="mark-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['present','absent','half_day','leave','wfh','holiday'].map(s => <SelectItem key={s} value={s} className="capitalize">{s.replace('_',' ')}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Check In</Label><Input type="time" value={checkIn} onChange={e => setCheckIn(e.target.value)} className="mt-1.5" data-testid="mark-checkin" /></div>
            <div><Label>Check Out</Label><Input type="time" value={checkOut} onChange={e => setCheckOut(e.target.value)} className="mt-1.5" data-testid="mark-checkout" /></div>
          </div>
          <div><Label>Notes</Label><Input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Optional notes..." className="mt-1.5" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting} data-testid="mark-submit-btn">
            {submitting && <Loader2 className="h-4 w-4 animate-spin mr-1" />} Mark Attendance
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
