import { useState, useEffect, useCallback } from 'react';
import { attendanceAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import {
  BarChart3, TrendingUp, Clock, Users, AlertTriangle, Activity,
  Loader2, Download, Play, FileText, Zap, ShieldAlert, Info,
  ChevronRight, Heart
} from 'lucide-react';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const PERIOD_OPTIONS = [
  { value: '7', label: 'Last 7 Days' },
  { value: '14', label: 'Last 14 Days' },
  { value: '30', label: 'Last 30 Days' },
  { value: '60', label: 'Last 60 Days' },
  { value: '90', label: 'Last 90 Days' },
];

const PIE_COLORS = ['#3b82f6', '#8b5cf6', '#f97316'];
const SEVERITY_STYLES = {
  critical: { bg: 'bg-red-50 border-red-200', icon: ShieldAlert, color: 'text-red-600' },
  warning: { bg: 'bg-amber-50 border-amber-200', icon: AlertTriangle, color: 'text-amber-600' },
  info: { bg: 'bg-blue-50 border-blue-200', icon: Info, color: 'text-blue-600' },
};

export default function AttendanceInsightsPage() {
  const [analytics, setAnalytics] = useState(null);
  const [healthScores, setHealthScores] = useState(null);
  const [cronLogs, setCronLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState('30');
  const [activeTab, setActiveTab] = useState('overview');
  const [triggeringReminder, setTriggeringReminder] = useState(false);
  const [triggeringAbsent, setTriggeringAbsent] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [a, h, c] = await Promise.all([
        attendanceAPI.getAnalytics({ days: parseInt(days) }),
        attendanceAPI.getHealthScores({ days: parseInt(days) }),
        attendanceAPI.getCronLogs({ limit: 10 }).catch(() => ({ data: { logs: [] } })),
      ]);
      setAnalytics(a.data);
      setHealthScores(h.data);
      setCronLogs(c.data.logs || []);
    } catch { toast.error('Failed to load analytics'); }
    finally { setLoading(false); }
  }, [days]);

  useEffect(() => { loadData(); }, [loadData]);

  const triggerReminders = async () => {
    setTriggeringReminder(true);
    try {
      await attendanceAPI.triggerReminders();
      toast.success('Reminders triggered!');
      loadData();
    } catch { toast.error('Failed'); }
    finally { setTriggeringReminder(false); }
  };

  const triggerAutoAbsent = async () => {
    setTriggeringAbsent(true);
    try {
      await attendanceAPI.triggerAutoAbsent();
      toast.success('Auto-absent marking triggered!');
      loadData();
    } catch { toast.error('Failed'); }
    finally { setTriggeringAbsent(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  const m = analytics?.metrics || {};
  const charts = analytics?.charts || {};
  const insights = analytics?.insights || [];
  const scores = healthScores?.scores || [];

  return (
    <div className="space-y-6" data-testid="attendance-insights-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-50 border border-indigo-200"><BarChart3 className="h-5 w-5 text-indigo-700" /></div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight" data-testid="insights-title">Attendance Insights</h1>
            <p className="text-sm text-muted-foreground">Analytics, patterns & automation controls</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger className="w-[150px]" data-testid="period-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              {PERIOD_OPTIONS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3" data-testid="metric-cards">
        <MetricCard label="Headcount" value={m.headcount} icon={Users} color="indigo" />
        <MetricCard label="Attendance Rate" value={`${m.attendance_rate}%`} icon={TrendingUp} color="green" />
        <MetricCard label="Absent Rate" value={`${m.absentee_rate}%`} icon={AlertTriangle} color="red" />
        <MetricCard label="Late Rate" value={`${m.late_rate}%`} icon={Clock} color="amber" />
        <MetricCard label="Avg Hours/Day" value={m.avg_hours_per_day} icon={Activity} color="blue" />
        <MetricCard label="Avg Health" value={healthScores?.average_score || 0} icon={Heart} color="rose" suffix="/100" />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList data-testid="insights-tabs">
          <TabsTrigger value="overview"><TrendingUp className="h-3.5 w-3.5 mr-1" /> Trends</TabsTrigger>
          <TabsTrigger value="team"><Users className="h-3.5 w-3.5 mr-1" /> Team</TabsTrigger>
          <TabsTrigger value="patterns"><Zap className="h-3.5 w-3.5 mr-1" /> Patterns {insights.length > 0 && <Badge className="ml-1 bg-red-100 text-red-700 h-5 text-[10px]">{insights.length}</Badge>}</TabsTrigger>
          <TabsTrigger value="health"><Heart className="h-3.5 w-3.5 mr-1" /> Health Scores</TabsTrigger>
          <TabsTrigger value="automation"><Play className="h-3.5 w-3.5 mr-1" /> Automation</TabsTrigger>
        </TabsList>

        {/* TRENDS TAB */}
        <TabsContent value="overview" className="space-y-4 mt-4">
          {/* Daily Attendance Trend */}
          <Card data-testid="daily-trend-chart">
            <CardHeader className="pb-2"><CardTitle className="text-base">Daily Attendance Trend</CardTitle></CardHeader>
            <CardContent>
              {charts.daily_trend?.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={charts.daily_trend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={v => v.slice(5)} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip contentStyle={{ fontSize: 12 }} />
                    <Legend />
                    <Line type="monotone" dataKey="present" stroke="#22c55e" strokeWidth={2} name="Present" dot={false} />
                    <Line type="monotone" dataKey="absent" stroke="#ef4444" strokeWidth={2} name="Absent" dot={false} />
                    <Line type="monotone" dataKey="late" stroke="#f59e0b" strokeWidth={2} name="Late" dot={false} />
                    <Line type="monotone" dataKey="wfh" stroke="#8b5cf6" strokeWidth={2} name="WFH" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : <p className="text-sm text-muted-foreground text-center py-8">No trend data available.</p>}
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Weekly Late */}
            <Card data-testid="weekly-late-chart">
              <CardHeader className="pb-2"><CardTitle className="text-base">Weekly Late Arrivals</CardTitle></CardHeader>
              <CardContent>
                {charts.weekly_late?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={charts.weekly_late}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="week" tick={{ fontSize: 10 }} tickFormatter={v => v.slice(5)} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip contentStyle={{ fontSize: 12 }} />
                      <Bar dataKey="late_count" fill="#f59e0b" radius={[4, 4, 0, 0]} name="Late Count" />
                    </BarChart>
                  </ResponsiveContainer>
                ) : <p className="text-sm text-muted-foreground text-center py-8">No data.</p>}
              </CardContent>
            </Card>

            {/* Work Mode Pie */}
            <Card data-testid="work-mode-chart">
              <CardHeader className="pb-2"><CardTitle className="text-base">Work Mode Distribution</CardTitle></CardHeader>
              <CardContent>
                {charts.work_mode_distribution?.some(d => d.value > 0) ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={charts.work_mode_distribution.filter(d => d.value > 0)} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                        {charts.work_mode_distribution.filter(d => d.value > 0).map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                ) : <p className="text-sm text-muted-foreground text-center py-8">No data.</p>}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* TEAM TAB */}
        <TabsContent value="team" className="mt-4">
          <Card data-testid="team-comparison-chart">
            <CardHeader className="pb-2"><CardTitle className="text-base">Team Attendance Comparison</CardTitle></CardHeader>
            <CardContent>
              {charts.team_comparison?.length > 0 ? (
                <ResponsiveContainer width="100%" height={Math.max(300, charts.team_comparison.length * 35)}>
                  <BarChart data={charts.team_comparison} layout="vertical" margin={{ left: 80 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={80} />
                    <Tooltip contentStyle={{ fontSize: 12 }} />
                    <Legend />
                    <Bar dataKey="present" fill="#22c55e" name="Present" stackId="a" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="absent" fill="#ef4444" name="Absent" stackId="a" />
                    <Bar dataKey="late" fill="#f59e0b" name="Late" stackId="a" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <p className="text-sm text-muted-foreground text-center py-8">No data.</p>}
            </CardContent>
          </Card>
        </TabsContent>

        {/* PATTERNS TAB */}
        <TabsContent value="patterns" className="mt-4">
          <div className="space-y-3" data-testid="patterns-list">
            {insights.length === 0 ? (
              <Card><CardContent className="py-8 text-center"><p className="text-sm text-muted-foreground">No patterns detected. All good!</p></CardContent></Card>
            ) : (
              insights.map((ins, i) => {
                const style = SEVERITY_STYLES[ins.severity] || SEVERITY_STYLES.info;
                const Icon = style.icon;
                return (
                  <Card key={i} className={`${style.bg} border`} data-testid={`insight-${i}`}>
                    <CardContent className="py-4 px-5 flex items-start gap-3">
                      <Icon className={`h-5 w-5 mt-0.5 ${style.color} shrink-0`} />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold">{ins.title}</p>
                          <Badge variant="outline" className={`text-[10px] capitalize ${style.color}`}>{ins.severity}</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{ins.description}</p>
                      </div>
                    </CardContent>
                  </Card>
                );
              })
            )}
          </div>
        </TabsContent>

        {/* HEALTH SCORES TAB */}
        <TabsContent value="health" className="mt-4">
          <Card data-testid="health-scores-card">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Attendance Health Scores</CardTitle>
                <Badge variant="secondary">Average: {healthScores?.average_score || 0}/100</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {scores.map(s => (
                  <div key={s.user_id} className="flex items-center gap-3 border rounded-lg px-4 py-3" data-testid={`health-${s.user_id}`}>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{s.name}</p>
                        <Badge variant="outline" className="text-[10px] capitalize">{s.role}</Badge>
                      </div>
                      <div className="flex gap-3 mt-1 text-[11px] text-muted-foreground">
                        <span>P:{s.stats?.present || 0}</span>
                        <span>A:{s.stats?.absent || 0}</span>
                        <span>L:{s.stats?.late || 0}</span>
                        <span>Avg:{s.stats?.avg_hours || 0}h</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="w-24 bg-slate-100 rounded-full h-2">
                        <div className={`h-2 rounded-full ${s.score >= 75 ? 'bg-green-500' : s.score >= 50 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${s.score}%` }} />
                      </div>
                      <span className={`text-sm font-bold min-w-[32px] text-right ${s.score >= 75 ? 'text-green-600' : s.score >= 50 ? 'text-amber-600' : 'text-red-600'}`}>{s.score}</span>
                      <span className="text-[10px] text-muted-foreground min-w-[56px]">{s.label}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* AUTOMATION TAB */}
        <TabsContent value="automation" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card data-testid="reminder-control">
              <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Clock className="h-4 w-4 text-blue-500" /> Attendance Reminders</CardTitle></CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-3">Send check-in reminders to employees who haven't clocked in. Respects holidays, weekends & approved leaves.</p>
                <Button onClick={triggerReminders} disabled={triggeringReminder} data-testid="trigger-reminders-btn">
                  {triggeringReminder ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Play className="h-4 w-4 mr-1" />}
                  Trigger Now
                </Button>
              </CardContent>
            </Card>

            <Card data-testid="auto-absent-control">
              <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-red-500" /> Auto Absent Marking</CardTitle></CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-3">Mark remaining no-shows as absent. Skips employees with check-ins, approved leave, or holidays.</p>
                <Button variant="destructive" onClick={triggerAutoAbsent} disabled={triggeringAbsent} data-testid="trigger-absent-btn">
                  {triggeringAbsent ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Play className="h-4 w-4 mr-1" />}
                  Trigger Now
                </Button>
              </CardContent>
            </Card>
          </div>

          {/* Cron Logs */}
          <Card data-testid="cron-logs-card">
            <CardHeader className="pb-3"><CardTitle className="text-base">Cron Job Execution Log</CardTitle></CardHeader>
            <CardContent>
              {cronLogs.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">No cron jobs executed yet.</p>
              ) : (
                <div className="overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Job</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Status</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Details</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500">Executed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cronLogs.map(l => (
                        <tr key={l.id} className="border-b hover:bg-slate-50/50">
                          <td className="px-3 py-2 font-medium capitalize">{l.job_name?.replace('_', ' ')}</td>
                          <td className="px-3 py-2">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${l.status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{l.status}</span>
                          </td>
                          <td className="px-3 py-2 text-xs text-muted-foreground max-w-[300px] truncate">
                            {l.details ? `Reminded: ${l.details.reminded || 0}, Skipped: ${l.details.skipped || 0}` : '—'}
                          </td>
                          <td className="px-3 py-2 text-xs">{l.executed_at ? new Date(l.executed_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function MetricCard({ label, value, icon: Icon, color, suffix = '' }) {
  const colors = {
    indigo: 'bg-indigo-50 text-indigo-700 border-indigo-100',
    green: 'bg-green-50 text-green-700 border-green-100',
    red: 'bg-red-50 text-red-700 border-red-100',
    amber: 'bg-amber-50 text-amber-700 border-amber-100',
    blue: 'bg-blue-50 text-blue-700 border-blue-100',
    rose: 'bg-rose-50 text-rose-700 border-rose-100',
  };
  return (
    <Card className={`border ${colors[color] || ''}`}>
      <CardContent className="py-3 px-4">
        <div className="flex items-center gap-2 mb-1">
          <Icon className="h-3.5 w-3.5 opacity-70" />
          <span className="text-[11px] font-medium opacity-80">{label}</span>
        </div>
        <p className="text-xl font-bold">{value}{suffix}</p>
      </CardContent>
    </Card>
  );
}
