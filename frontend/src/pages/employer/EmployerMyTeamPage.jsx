import { useState, useEffect } from 'react';
import { employerPortalAPI, attendanceAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import {
  Users, Briefcase, TrendingUp, DollarSign, Mail, Calendar,
  ChevronRight, Clock, Target, UserCheck, UserX, AlertTriangle,
  CircleDot, Home, Coffee
} from 'lucide-react';

const STATUS_CONFIG = {
  present: { label: 'Present', color: 'bg-green-100 text-green-700 border-green-200', dot: 'bg-green-500' },
  absent: { label: 'Absent', color: 'bg-red-100 text-red-700 border-red-200', dot: 'bg-red-500' },
  leave: { label: 'On Leave', color: 'bg-blue-100 text-blue-700 border-blue-200', dot: 'bg-blue-500' },
  wfh: { label: 'WFH', color: 'bg-purple-100 text-purple-700 border-purple-200', dot: 'bg-purple-500' },
  half_day: { label: 'Half Day', color: 'bg-amber-100 text-amber-700 border-amber-200', dot: 'bg-amber-500' },
  not_checked_in: { label: 'Not Checked In', color: 'bg-slate-100 text-slate-600 border-slate-200', dot: 'bg-slate-400' },
};

export default function EmployerMyTeamPage() {
  const [teamData, setTeamData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedMember, setSelectedMember] = useState(null);
  const [todayAttendance, setTodayAttendance] = useState(null);
  const [monthlyReport, setMonthlyReport] = useState(null);

  useEffect(() => {
    loadTeamData();
    loadTodayAttendance();
    loadMonthlyReport();
  }, []);

  const loadTeamData = async () => {
    try {
      const res = await employerPortalAPI.getMyTeam();
      setTeamData(res.data);
    } catch {
      toast.error('Failed to load team data');
    } finally {
      setLoading(false);
    }
  };

  const loadTodayAttendance = async () => {
    try {
      const res = await attendanceAPI.getEmployerTeamToday();
      setTodayAttendance(res.data);
    } catch {
      // non-critical
    }
  };

  const loadMonthlyReport = async () => {
    try {
      const now = new Date();
      const res = await attendanceAPI.getEmployerTeamMonthlyReport({
        month: now.getMonth() + 1,
        year: now.getFullYear(),
      });
      setMonthlyReport(res.data);
    } catch {
      // non-critical
    }
  };

  const getTodayStatus = (memberId) => {
    if (!todayAttendance?.members) return null;
    return todayAttendance.members.find(m => m.user_id === memberId);
  };

  const getMonthlyStats = (memberId) => {
    if (!monthlyReport?.summaries) return null;
    return monthlyReport.summaries.find(s => s.user_id === memberId);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  if (!teamData?.team) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-heading font-bold text-slate-900">My Team</h1>
          <p className="text-sm text-slate-500 mt-1">Manage your team and track performance</p>
        </div>
        <Card className="border-slate-200">
          <CardContent className="p-12 text-center">
            <Users className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-600 mb-2">No Team Assigned</h3>
            <p className="text-slate-500">Contact your administrator to set up your team.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { team, members, summary } = teamData;

  return (
    <div className="space-y-6" data-testid="employer-my-team">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-heading font-bold text-slate-900">My Team</h1>
        <p className="text-sm text-slate-500 mt-1">Team: {team.name} - {summary.total_members} members</p>
      </div>

      {/* Performance Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <Users className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{summary.total_members}</p>
                <p className="text-xs text-slate-500">Team Members</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
                <Briefcase className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{summary.total_mandates}</p>
                <p className="text-xs text-slate-500">Active Mandates</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <Target className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{summary.total_pipeline}</p>
                <p className="text-xs text-slate-500">Total Pipeline</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-orange-100 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-orange-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{formatSalaryINR(summary.total_revenue_pipeline)}</p>
                <p className="text-xs text-slate-500">Pipeline Revenue</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200 bg-gradient-to-r from-green-50 to-white">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-green-600">{formatSalaryINR(summary.total_revenue_closed)}</p>
                <p className="text-xs text-slate-500">Closed Revenue</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Today's Attendance Snapshot */}
      {todayAttendance && (
        <Card className="border-slate-200" data-testid="today-attendance-snapshot">
          <CardHeader className="border-b border-slate-100 bg-slate-50/50 py-3">
            <CardTitle className="font-heading text-base flex items-center gap-2">
              <Clock className="w-4 h-4 text-indigo-600" />
              Today's Attendance  -  {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata' })}
              {todayAttendance.is_holiday && (
                <Badge className="ml-2 bg-cyan-100 text-cyan-700 border-cyan-200">Holiday: {todayAttendance.holiday_name}</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            {/* Today's stat cards */}
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-4">
              <div className="flex items-center gap-2 p-3 rounded-lg bg-green-50 border border-green-100">
                <UserCheck className="w-5 h-5 text-green-600" />
                <div>
                  <p className="text-xl font-bold text-green-700">{todayAttendance.present}</p>
                  <p className="text-[11px] text-green-600">Present</p>
                </div>
              </div>
              <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-100">
                <UserX className="w-5 h-5 text-red-600" />
                <div>
                  <p className="text-xl font-bold text-red-700">{todayAttendance.absent}</p>
                  <p className="text-[11px] text-red-600">Absent</p>
                </div>
              </div>
              <div className="flex items-center gap-2 p-3 rounded-lg bg-blue-50 border border-blue-100">
                <Calendar className="w-5 h-5 text-blue-600" />
                <div>
                  <p className="text-xl font-bold text-blue-700">{todayAttendance.on_leave}</p>
                  <p className="text-[11px] text-blue-600">On Leave</p>
                </div>
              </div>
              <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-50 border border-amber-100">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
                <div>
                  <p className="text-xl font-bold text-amber-700">{todayAttendance.late}</p>
                  <p className="text-[11px] text-amber-600">Late</p>
                </div>
              </div>
              <div className="flex items-center gap-2 p-3 rounded-lg bg-purple-50 border border-purple-100">
                <Home className="w-5 h-5 text-purple-600" />
                <div>
                  <p className="text-xl font-bold text-purple-700">{todayAttendance.wfh}</p>
                  <p className="text-[11px] text-purple-600">WFH</p>
                </div>
              </div>
              <div className="flex items-center gap-2 p-3 rounded-lg bg-slate-50 border border-slate-200">
                <Coffee className="w-5 h-5 text-slate-500" />
                <div>
                  <p className="text-xl font-bold text-slate-600">{todayAttendance.not_checked_in}</p>
                  <p className="text-[11px] text-slate-500">Not In</p>
                </div>
              </div>
            </div>

            {/* Per-member today status */}
            <div className="flex flex-wrap gap-2">
              {todayAttendance.members.map(m => {
                const cfg = STATUS_CONFIG[m.status] || STATUS_CONFIG.not_checked_in;
                return (
                  <div key={m.user_id} className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium border ${cfg.color}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                    {m.name}
                    {m.check_in && <span className="text-[10px] opacity-70 ml-1">{m.check_in}</span>}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Monthly Attendance Summary */}
      {monthlyReport?.summaries?.length > 0 && (
        <Card className="border-slate-200" data-testid="monthly-attendance-summary">
          <CardHeader className="border-b border-slate-100 bg-slate-50/50 py-3">
            <CardTitle className="font-heading text-base flex items-center gap-2">
              <CircleDot className="w-4 h-4 text-indigo-600" />
              Attendance Summary - {new Date().toLocaleDateString('en-IN', { month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata' })}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-slate-500">
                    <th className="text-left py-2 px-2 font-medium">Member</th>
                    <th className="text-center py-2 px-2 font-medium">Present</th>
                    <th className="text-center py-2 px-2 font-medium">Absent</th>
                    <th className="text-center py-2 px-2 font-medium">Half Day</th>
                    <th className="text-center py-2 px-2 font-medium">Leave</th>
                    <th className="text-center py-2 px-2 font-medium">Late</th>
                    <th className="text-center py-2 px-2 font-medium">WFH</th>
                    <th className="text-center py-2 px-2 font-medium">Hours</th>
                  </tr>
                </thead>
                <tbody>
                  {monthlyReport.summaries.map(s => (
                    <tr key={s.user_id} className="border-b hover:bg-slate-50">
                      <td className="py-2 px-2 font-medium">{s.name}</td>
                      <td className="text-center py-2 px-2"><span className="text-green-600 font-semibold">{s.present}</span></td>
                      <td className="text-center py-2 px-2"><span className={s.absent > 0 ? 'text-red-600 font-semibold' : 'text-slate-400'}>{s.absent}</span></td>
                      <td className="text-center py-2 px-2">{s.half_days}</td>
                      <td className="text-center py-2 px-2">{s.leaves}</td>
                      <td className="text-center py-2 px-2"><span className={s.late_count > 0 ? 'text-amber-600 font-semibold' : 'text-slate-400'}>{s.late_count}</span></td>
                      <td className="text-center py-2 px-2">{s.wfh}</td>
                      <td className="text-center py-2 px-2">{s.total_hours}h</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Team Members List */}
      <Card className="border-slate-200">
        <CardHeader className="border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Users className="w-5 h-5 text-[#7CB342]" />
            Team Members
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-slate-100">
            {members.map((member) => {
              const todayStatus = getTodayStatus(member.id);
              const statusCfg = todayStatus ? (STATUS_CONFIG[todayStatus.status] || STATUS_CONFIG.not_checked_in) : null;
              return (
                <div
                  key={member.id}
                  className="p-4 hover:bg-slate-50 transition-colors cursor-pointer flex items-center justify-between"
                  onClick={() => setSelectedMember(member)}
                  data-testid={`team-member-${member.id}`}
                >
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center relative">
                      <span className="text-[#7CB342] font-semibold text-lg">
                        {member.name?.charAt(0).toUpperCase()}
                      </span>
                      {todayStatus && (
                        <span className={`absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-white ${statusCfg.dot}`} title={statusCfg.label} />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-slate-900">{member.name}</p>
                        {member.is_active ? (
                          <span className="w-2 h-2 bg-green-500 rounded-full" title="Active" />
                        ) : (
                          <span className="w-2 h-2 bg-slate-300 rounded-full" title="Inactive" />
                        )}
                        {statusCfg && (
                          <Badge className={`text-[10px] px-1.5 py-0 h-5 border ${statusCfg.color}`}>{statusCfg.label}</Badge>
                        )}
                      </div>
                      <p className="text-sm text-slate-500">{member.email}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-8">
                    <div className="text-center">
                      <p className="text-lg font-semibold text-slate-900">{member.mandates_assigned}</p>
                      <p className="text-xs text-slate-500">Mandates</p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-slate-900">{member.total_pipeline_count}</p>
                      <p className="text-xs text-slate-500">Pipeline</p>
                    </div>
                    <div className="text-center hidden md:block">
                      <p className="text-lg font-semibold text-amber-600">{formatSalaryINR(member.revenue_pipeline)}</p>
                      <p className="text-xs text-slate-500">In Pipeline</p>
                    </div>
                    <div className="text-center hidden md:block">
                      <p className="text-lg font-semibold text-green-600">{formatSalaryINR(member.revenue_closed)}</p>
                      <p className="text-xs text-slate-500">Closed</p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-slate-400" />
                  </div>
                </div>
              );
            })}

            {members.length === 0 && (
              <div className="p-12 text-center">
                <Users className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <p className="text-slate-500">No team members assigned yet</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Member Detail Dialog */}
      <MemberDetailDialog
        member={selectedMember}
        open={!!selectedMember}
        onClose={() => setSelectedMember(null)}
        getMonthlyStats={getMonthlyStats}
        getTodayStatus={getTodayStatus}
      />
    </div>
  );
}

function MemberDetailDialog({ member, open, onClose, getMonthlyStats, getTodayStatus }) {
  if (!member) return null;
  const monthStats = getMonthlyStats(member.id);
  const todayStatus = getTodayStatus(member.id);
  const statusCfg = todayStatus ? (STATUS_CONFIG[todayStatus.status] || STATUS_CONFIG.not_checked_in) : null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-heading">Team Member Details</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="mb-4">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="attendance">Attendance</TabsTrigger>
            <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
            <TabsTrigger value="mandates">Mandates</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <div className="space-y-4">
              <div className="flex items-center gap-4 p-4 bg-slate-50 rounded-lg">
                <div className="w-16 h-16 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                  <span className="text-[#7CB342] font-bold text-2xl">
                    {member.name?.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-xl">{member.name}</h3>
                    {member.is_active ? (
                      <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full">Active</span>
                    ) : (
                      <span className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full">Inactive</span>
                    )}
                    {statusCfg && (
                      <Badge className={`text-xs border ${statusCfg.color}`}>{statusCfg.label}</Badge>
                    )}
                  </div>
                  <p className="text-slate-500 flex items-center gap-1">
                    <Mail className="w-4 h-4" /> {member.email}
                  </p>
                  {member.joined_at && (
                    <p className="text-sm text-slate-400 flex items-center gap-1">
                      <Calendar className="w-3 h-3" /> Joined: {new Date(member.joined_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}
                    </p>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-3 bg-blue-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-blue-600">{member.mandates_assigned}</p>
                  <p className="text-xs text-blue-600">Mandates</p>
                </div>
                <div className="p-3 bg-purple-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-purple-600">{member.total_pipeline_count}</p>
                  <p className="text-xs text-purple-600">Total Pipeline</p>
                </div>
                <div className="p-3 bg-amber-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-amber-600">{formatSalaryINR(member.revenue_pipeline)}</p>
                  <p className="text-xs text-amber-600">Pipeline Value</p>
                </div>
                <div className="p-3 bg-green-50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-green-600">{formatSalaryINR(member.revenue_closed)}</p>
                  <p className="text-xs text-green-600">Closed Revenue</p>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="attendance">
            <div className="space-y-4">
              {/* Today's Status */}
              {todayStatus && (
                <div className="p-4 bg-slate-50 rounded-lg">
                  <h4 className="font-medium text-sm text-slate-500 mb-2">Today</h4>
                  <div className="flex items-center gap-4">
                    <Badge className={`border ${statusCfg.color}`}>{statusCfg.label}</Badge>
                    {todayStatus.check_in && <span className="text-sm text-slate-600">In: {todayStatus.check_in}</span>}
                    {todayStatus.check_out && <span className="text-sm text-slate-600">Out: {todayStatus.check_out}</span>}
                    {todayStatus.hours_worked > 0 && <span className="text-sm text-slate-600">{todayStatus.hours_worked}h</span>}
                    {todayStatus.is_late && <Badge className="bg-amber-100 text-amber-700 border-amber-200 text-xs">Late</Badge>}
                  </div>
                </div>
              )}

              {/* Monthly Summary */}
              {monthStats ? (
                <div>
                  <h4 className="font-medium text-sm text-slate-500 mb-3">
                    {new Date().toLocaleDateString('en-IN', { month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata' })} Summary
                  </h4>
                  <div className="grid grid-cols-3 md:grid-cols-4 gap-3">
                    <div className="p-3 rounded-lg bg-green-50 text-center">
                      <p className="text-2xl font-bold text-green-600">{monthStats.present}</p>
                      <p className="text-xs text-green-600">Present</p>
                    </div>
                    <div className="p-3 rounded-lg bg-red-50 text-center">
                      <p className="text-2xl font-bold text-red-600">{monthStats.absent}</p>
                      <p className="text-xs text-red-600">Absent</p>
                    </div>
                    <div className="p-3 rounded-lg bg-blue-50 text-center">
                      <p className="text-2xl font-bold text-blue-600">{monthStats.leaves}</p>
                      <p className="text-xs text-blue-600">Leave</p>
                    </div>
                    <div className="p-3 rounded-lg bg-amber-50 text-center">
                      <p className="text-2xl font-bold text-amber-600">{monthStats.late_count}</p>
                      <p className="text-xs text-amber-600">Late</p>
                    </div>
                    <div className="p-3 rounded-lg bg-purple-50 text-center">
                      <p className="text-2xl font-bold text-purple-600">{monthStats.wfh}</p>
                      <p className="text-xs text-purple-600">WFH</p>
                    </div>
                    <div className="p-3 rounded-lg bg-orange-50 text-center">
                      <p className="text-2xl font-bold text-orange-600">{monthStats.half_days}</p>
                      <p className="text-xs text-orange-600">Half Day</p>
                    </div>
                    <div className="p-3 rounded-lg bg-indigo-50 text-center">
                      <p className="text-2xl font-bold text-indigo-600">{monthStats.total_hours}h</p>
                      <p className="text-xs text-indigo-600">Total Hours</p>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-slate-400 text-sm">No attendance data this month</p>
              )}
            </div>
          </TabsContent>

          <TabsContent value="pipeline">
            <div className="space-y-4">
              <h4 className="font-medium">Pipeline Stages</h4>
              <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
                {Object.entries(member.pipeline).map(([stage, count]) => (
                  <div key={stage} className={`p-3 rounded-lg text-center ${
                    stage === 'hired' ? 'bg-green-50' :
                    stage === 'rejected' ? 'bg-red-50' :
                    stage === 'offered' ? 'bg-purple-50' :
                    stage === 'interview' ? 'bg-blue-50' :
                    stage === 'shortlisted' ? 'bg-amber-50' :
                    'bg-slate-50'
                  }`}>
                    <p className={`text-2xl font-bold ${
                      stage === 'hired' ? 'text-green-600' :
                      stage === 'rejected' ? 'text-red-600' :
                      stage === 'offered' ? 'text-purple-600' :
                      stage === 'interview' ? 'text-blue-600' :
                      stage === 'shortlisted' ? 'text-amber-600' :
                      'text-slate-600'
                    }`}>{count}</p>
                    <p className="text-xs text-slate-500 capitalize">{stage}</p>
                  </div>
                ))}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="mandates">
            <div className="space-y-3">
              <h4 className="font-medium">Assigned Mandates ({member.mandates_assigned})</h4>
              {member.mandates?.map((mandate) => (
                <div key={mandate.id} className="p-3 bg-slate-50 rounded-lg">
                  <p className="font-medium text-slate-800">{mandate.title}</p>
                  <p className="text-sm text-slate-500">{mandate.company_name}</p>
                </div>
              ))}
              {(!member.mandates || member.mandates.length === 0) && (
                <p className="text-slate-400 text-sm">No mandates assigned</p>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
