import { useState, useEffect, useCallback } from 'react';
import { attendanceAPI } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { Clock, LogIn, LogOut, Calendar, MapPin, Wifi, ChevronLeft, ChevronRight, Loader2, Coffee, Home, Briefcase } from 'lucide-react';

const STATUS_STYLES = {
  present: 'bg-green-100 text-green-700',
  absent: 'bg-red-100 text-red-700',
  half_day: 'bg-amber-100 text-amber-700',
  leave: 'bg-blue-100 text-blue-700',
  wfh: 'bg-purple-100 text-purple-700',
  holiday: 'bg-cyan-100 text-cyan-700',
};

const STATUS_LABELS = {
  present: 'Present', absent: 'Absent', half_day: 'Half Day',
  leave: 'On Leave', wfh: 'WFH', holiday: 'Holiday',
};

const WORK_MODES = [
  { value: 'office', label: 'Office', icon: Briefcase },
  { value: 'wfh', label: 'Work from Home', icon: Home },
  { value: 'field', label: 'Field Visit', icon: MapPin },
];

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

export default function AttendancePage() {
  const { user } = useAuth();
  const [todayRecord, setTodayRecord] = useState(null);
  const [records, setRecords] = useState([]);
  const [holidays, setHolidays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [workMode, setWorkMode] = useState('office');
  const [isPaused, setIsPaused] = useState(false);
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());

  const loadData = useCallback(async () => {
    try {
      const [att, today, hol, status] = await Promise.all([
        attendanceAPI.getMyAttendance({ month, year }),
        attendanceAPI.getTodayStatus(),
        attendanceAPI.getHolidays({ year }),
        attendanceAPI.getStatus(),
      ]);
      setRecords(att.data.records || []);
      setTodayRecord(today.data.today);
      setHolidays(hol.data.holidays || []);
      setIsPaused(status.data.is_paused || false);
    } catch { toast.error('Failed to load attendance'); }
    finally { setLoading(false); }
  }, [month, year]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCheckIn = async () => {
    setChecking(true);
    try {
      const res = await attendanceAPI.checkIn({ work_mode: workMode });
      setTodayRecord(res.data);
      toast.success('Checked in successfully!');
      loadData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Check-in failed'); }
    finally { setChecking(false); }
  };

  const handleCheckOut = async () => {
    setChecking(true);
    try {
      const res = await attendanceAPI.checkOut({});
      setTodayRecord(res.data);
      toast.success('Checked out successfully!');
      loadData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Check-out failed'); }
    finally { setChecking(false); }
  };

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1); } else setMonth(m => m - 1); };
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1); } else setMonth(m => m + 1); };

  // Build calendar grid
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDay = new Date(year, month - 1, 1).getDay();
  const recordMap = Object.fromEntries(records.map(r => [r.date, r]));
  const holidayMap = Object.fromEntries(holidays.map(h => [h.date, h]));

  const todayStr = new Date().toISOString().split('T')[0];
  const hasCheckedIn = todayRecord?.check_in;
  const hasCheckedOut = todayRecord?.check_out;

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-6" data-testid="attendance-page">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-green-50 border border-green-200"><Clock className="h-5 w-5 text-green-700" /></div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight" data-testid="attendance-title">My Attendance</h1>
          <p className="text-sm text-muted-foreground">Track your daily attendance and work hours</p>
        </div>
      </div>

      {/* Today's Check-in/out Card */}
      <Card className="border-green-200 bg-gradient-to-r from-green-50/50 to-white" data-testid="today-card">
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Today — {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</p>
              <div className="flex items-center gap-4 mt-2">
                {hasCheckedIn && (
                  <div className="flex items-center gap-1.5 text-sm">
                    <LogIn className="h-4 w-4 text-green-600" />
                    <span className="font-medium">{todayRecord.check_in}</span>
                  </div>
                )}
                {hasCheckedOut && (
                  <div className="flex items-center gap-1.5 text-sm">
                    <LogOut className="h-4 w-4 text-red-500" />
                    <span className="font-medium">{todayRecord.check_out}</span>
                  </div>
                )}
                {hasCheckedIn && todayRecord.hours_worked > 0 && (
                  <Badge variant="secondary">{todayRecord.hours_worked}h worked</Badge>
                )}
                {todayRecord?.is_late && <Badge className="bg-amber-100 text-amber-700">Late ({todayRecord.late_minutes}m)</Badge>}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {!hasCheckedIn && (
                <>
                  <Select value={workMode} onValueChange={setWorkMode}>
                    <SelectTrigger className="w-[160px]" data-testid="work-mode-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {WORK_MODES.map(m => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Button onClick={handleCheckIn} disabled={checking} className="bg-green-600 hover:bg-green-700" data-testid="check-in-btn">
                    {checking ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <LogIn className="h-4 w-4 mr-1" />}
                    Check In
                  </Button>
                </>
              )}
              {hasCheckedIn && !hasCheckedOut && (
                <Button onClick={handleCheckOut} disabled={checking} variant="destructive" data-testid="check-out-btn">
                  {checking ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <LogOut className="h-4 w-4 mr-1" />}
                  Check Out
                </Button>
              )}
              {hasCheckedOut && <Badge className="bg-green-100 text-green-700 text-sm px-3 py-1">Day Complete</Badge>}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Calendar */}
      <Card data-testid="attendance-calendar">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Attendance Calendar</CardTitle>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon" onClick={prevMonth}><ChevronLeft className="h-4 w-4" /></Button>
              <span className="text-sm font-medium min-w-[140px] text-center">{MONTHS[month - 1]} {year}</span>
              <Button variant="ghost" size="icon" onClick={nextMonth}><ChevronRight className="h-4 w-4" /></Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-7 gap-1">
            {['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d => (
              <div key={d} className="text-center text-xs font-semibold text-muted-foreground py-2">{d}</div>
            ))}
            {Array.from({ length: firstDay }).map((_, i) => <div key={`e-${i}`} />)}
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const day = i + 1;
              const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
              const rec = recordMap[dateStr];
              const hol = holidayMap[dateStr];
              const isToday = dateStr === todayStr;
              const isWeekend = new Date(year, month - 1, day).getDay() === 0 || new Date(year, month - 1, day).getDay() === 6;

              let bg = '';
              let label = '';
              if (hol) { bg = 'bg-cyan-50 border-cyan-200'; label = hol.name; }
              else if (rec) { bg = rec.status === 'present' ? 'bg-green-50 border-green-200' : rec.status === 'leave' ? 'bg-blue-50 border-blue-200' : rec.status === 'half_day' ? 'bg-amber-50 border-amber-200' : rec.status === 'absent' ? 'bg-red-50 border-red-200' : 'bg-purple-50 border-purple-200'; }
              else if (isWeekend) { bg = 'bg-slate-50'; }

              return (
                <div key={day} className={`border rounded-lg p-1.5 min-h-[60px] text-xs ${bg} ${isToday ? 'ring-2 ring-green-400' : ''}`} data-testid={`cal-day-${day}`}>
                  <div className={`font-medium ${isWeekend ? 'text-red-400' : 'text-slate-700'}`}>{day}</div>
                  {hol && <div className="text-[10px] text-cyan-600 truncate mt-0.5" title={hol.name}>{hol.name}</div>}
                  {rec && !hol && (
                    <div className="mt-0.5">
                      <span className={`text-[10px] px-1 py-0.5 rounded ${STATUS_STYLES[rec.status] || ''}`}>
                        {STATUS_LABELS[rec.status] || rec.status}
                      </span>
                      {rec.check_in && <div className="text-[10px] text-muted-foreground mt-0.5">{rec.check_in}–{rec.check_out || '...'}</div>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t">
            {Object.entries(STATUS_LABELS).map(([k, v]) => (
              <div key={k} className="flex items-center gap-1.5">
                <span className={`w-3 h-3 rounded-sm ${STATUS_STYLES[k]}`} />
                <span className="text-xs text-muted-foreground">{v}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Records List */}
      <Card data-testid="attendance-records-list">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Attendance Log — {MONTHS[month - 1]} {year}</CardTitle>
        </CardHeader>
        <CardContent>
          {records.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No attendance records for this month.</p>
          ) : (
            <div className="overflow-auto">
              <table className="w-full text-sm" data-testid="attendance-table">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Date</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Status</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Check In</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Check Out</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Hours</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Mode</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map(r => (
                    <tr key={r.id} className="border-b hover:bg-slate-50/50">
                      <td className="px-3 py-2 font-medium">{new Date(r.date + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}</td>
                      <td className="px-3 py-2"><span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLES[r.status] || ''}`}>{STATUS_LABELS[r.status] || r.status}</span></td>
                      <td className="px-3 py-2">{r.check_in || '—'}</td>
                      <td className="px-3 py-2">{r.check_out || '—'}</td>
                      <td className="px-3 py-2">{r.hours_worked ? `${r.hours_worked}h` : '—'}{r.is_late ? <span className="text-amber-600 ml-1 text-xs">(Late)</span> : ''}</td>
                      <td className="px-3 py-2 capitalize">{r.work_mode || '—'}</td>
                      <td className="px-3 py-2 text-muted-foreground max-w-[200px] truncate">{r.notes || '—'}</td>
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
