import { useState, useEffect, useCallback } from 'react';
import { attendanceAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { Users, ChevronLeft, ChevronRight, Loader2, Clock, Calendar, UserCheck, UserX, AlertTriangle } from 'lucide-react';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

const STATUS_STYLES = {
  present: 'bg-green-100 text-green-700',
  absent: 'bg-red-100 text-red-700',
  half_day: 'bg-amber-100 text-amber-700',
  leave: 'bg-blue-100 text-blue-700',
  wfh: 'bg-purple-100 text-purple-700',
  holiday: 'bg-cyan-100 text-cyan-700',
};

export default function EmployerTeamAttendancePage() {
  const [report, setReport] = useState(null);
  const [records, setRecords] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [rep, all] = await Promise.all([
        attendanceAPI.getEmployerTeamMonthlyReport({ month, year }),
        attendanceAPI.getEmployerTeamAttendance({ month, year }),
      ]);
      setReport(rep.data);
      setRecords(all.data.records || []);
      setUsers(all.data.users || []);
    } catch {
      toast.error('Failed to load team attendance');
    } finally {
      setLoading(false);
    }
  }, [month, year]);

  useEffect(() => { loadData(); }, [loadData]);

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1); } else setMonth(m => m - 1); };
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1); } else setMonth(m => m + 1); };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  const summaries = report?.summaries || [];
  const holidays = report?.holidays || [];

  const totalPresent = summaries.reduce((s, u) => s + u.present, 0);
  const totalAbsent = summaries.reduce((s, u) => s + u.absent, 0);
  const totalLeaves = summaries.reduce((s, u) => s + u.leaves, 0);
  const totalLate = summaries.reduce((s, u) => s + u.late_count, 0);

  return (
    <div className="space-y-6" data-testid="employer-team-attendance-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-50 border border-indigo-200"><Users className="h-5 w-5 text-indigo-700" /></div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight" data-testid="team-attendance-title">Team Attendance</h1>
            <p className="text-sm text-muted-foreground">View your team's attendance performance</p>
          </div>
        </div>
      </div>

      {/* Month Navigation */}
      <div className="flex items-center gap-4" data-testid="month-nav">
        <Button variant="outline" size="icon" onClick={prevMonth} data-testid="prev-month"><ChevronLeft className="h-4 w-4" /></Button>
        <span className="text-lg font-semibold min-w-[180px] text-center">{MONTHS[month - 1]} {year}</span>
        <Button variant="outline" size="icon" onClick={nextMonth} data-testid="next-month"><ChevronRight className="h-4 w-4" /></Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card data-testid="stat-present"><CardContent className="pt-6 text-center"><UserCheck className="h-8 w-8 mx-auto text-green-500 mb-2" /><div className="text-2xl font-bold text-green-700">{totalPresent}</div><div className="text-xs text-muted-foreground">Present Days</div></CardContent></Card>
        <Card data-testid="stat-absent"><CardContent className="pt-6 text-center"><UserX className="h-8 w-8 mx-auto text-red-500 mb-2" /><div className="text-2xl font-bold text-red-700">{totalAbsent}</div><div className="text-xs text-muted-foreground">Absent Days</div></CardContent></Card>
        <Card data-testid="stat-leaves"><CardContent className="pt-6 text-center"><Calendar className="h-8 w-8 mx-auto text-blue-500 mb-2" /><div className="text-2xl font-bold text-blue-700">{totalLeaves}</div><div className="text-xs text-muted-foreground">Leaves</div></CardContent></Card>
        <Card data-testid="stat-late"><CardContent className="pt-6 text-center"><AlertTriangle className="h-8 w-8 mx-auto text-amber-500 mb-2" /><div className="text-2xl font-bold text-amber-700">{totalLate}</div><div className="text-xs text-muted-foreground">Late Arrivals</div></CardContent></Card>
      </div>

      {/* Team Summary Table */}
      <Card data-testid="team-summary-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Users className="h-5 w-5" /> Team Summary — {MONTHS[month - 1]} {year}</CardTitle>
        </CardHeader>
        <CardContent>
          {summaries.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">No attendance data for this month</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3 font-medium">Name</th>
                    <th className="text-left py-2 px-3 font-medium">Role</th>
                    <th className="text-center py-2 px-3 font-medium">Present</th>
                    <th className="text-center py-2 px-3 font-medium">Absent</th>
                    <th className="text-center py-2 px-3 font-medium">Half Day</th>
                    <th className="text-center py-2 px-3 font-medium">Leaves</th>
                    <th className="text-center py-2 px-3 font-medium">WFH</th>
                    <th className="text-center py-2 px-3 font-medium">Late</th>
                    <th className="text-center py-2 px-3 font-medium">Hours</th>
                  </tr>
                </thead>
                <tbody>
                  {summaries.map(s => (
                    <tr key={s.user_id} className="border-b hover:bg-slate-50">
                      <td className="py-2 px-3 font-medium">{s.name}</td>
                      <td className="py-2 px-3"><Badge variant="outline" className="text-xs capitalize">{s.role}</Badge></td>
                      <td className="text-center py-2 px-3"><span className="text-green-600 font-semibold">{s.present}</span></td>
                      <td className="text-center py-2 px-3"><span className="text-red-600 font-semibold">{s.absent}</span></td>
                      <td className="text-center py-2 px-3">{s.half_days}</td>
                      <td className="text-center py-2 px-3">{s.leaves}</td>
                      <td className="text-center py-2 px-3">{s.wfh}</td>
                      <td className="text-center py-2 px-3">{s.late_count > 0 ? <span className="text-amber-600 font-semibold">{s.late_count}</span> : '0'}</td>
                      <td className="text-center py-2 px-3">{s.total_hours}h</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Holidays */}
      {holidays.length > 0 && (
        <Card data-testid="holidays-card">
          <CardHeader><CardTitle className="text-base">Holidays in {MONTHS[month - 1]}</CardTitle></CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {holidays.map(h => (
                <Badge key={h.id || h.date} variant="secondary" className="bg-cyan-50 text-cyan-700 border-cyan-200">{h.name} — {h.date}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Daily Records */}
      <Card data-testid="daily-records-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Clock className="h-5 w-5" /> Daily Records</CardTitle>
        </CardHeader>
        <CardContent>
          {records.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">No daily records for this month</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3 font-medium">Date</th>
                    <th className="text-left py-2 px-3 font-medium">Name</th>
                    <th className="text-center py-2 px-3 font-medium">Check In</th>
                    <th className="text-center py-2 px-3 font-medium">Check Out</th>
                    <th className="text-center py-2 px-3 font-medium">Hours</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map(r => (
                    <tr key={r.id} className="border-b hover:bg-slate-50">
                      <td className="py-2 px-3">{r.date}</td>
                      <td className="py-2 px-3 font-medium">{r.user_name || '—'}</td>
                      <td className="text-center py-2 px-3">{r.check_in || '—'}</td>
                      <td className="text-center py-2 px-3">{r.check_out || '—'}</td>
                      <td className="text-center py-2 px-3">{r.hours_worked || 0}h</td>
                      <td className="text-center py-2 px-3">
                        <Badge className={STATUS_STYLES[r.status] || 'bg-gray-100 text-gray-600'}>
                          {(r.status || 'unknown').replace('_', ' ')}
                        </Badge>
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
