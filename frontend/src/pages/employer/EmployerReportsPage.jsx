import { useState, useEffect } from 'react';
import api from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { Calendar, Download, Mail, Users, Clock, FileSpreadsheet, RefreshCw } from 'lucide-react';

export default function EmployerReportsPage() {
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState({});
  const [triggering, setTriggering] = useState({});

  const loadData = async () => {
    try {
      setLoading(true);
      const teamsRes = await api.get('/teams');
      const teamsData = Array.isArray(teamsRes.data) ? teamsRes.data : teamsRes.data.teams || [];
      setTeams(teamsData);
    } catch (err) {
      toast.error('Failed to load reports data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const downloadPreview = async (teamId, teamName, type) => {
    const key = `${teamId}_${type}`;
    setDownloading(prev => ({ ...prev, [key]: true }));
    try {
      const res = await api.get(`/reports/${type}/preview/${teamId}`, { responseType: 'blob' });
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const today = new Date().toISOString().slice(0, 10);
      a.download = `${type === 'daily' ? 'Daily' : 'Weekly'}_Report_${teamName.replace(/\s+/g, '_')}_${today}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      toast.success(`${type === 'daily' ? 'Daily' : 'Weekly'} Excel downloaded`);
    } catch (err) {
      toast.error(`Failed to download ${type} preview`);
    } finally {
      setDownloading(prev => ({ ...prev, [key]: false }));
    }
  };

  const triggerRun = async (type) => {
    if (!confirm(`Send the ${type} report email to ALL team leaders right now?`)) return;
    setTriggering(prev => ({ ...prev, [type]: true }));
    try {
      const res = await api.post(`/api/reports/${type}/run-now`);
      toast.success(`${type === 'daily' ? 'Daily' : 'Weekly'} reports: sent=${res.data.sent}, failed=${res.data.failed}, skipped=${res.data.skipped}`);
      await loadData();
    } catch (err) {
      toast.error(`Failed to trigger ${type} run`);
    } finally {
      setTriggering(prev => ({ ...prev, [type]: false }));
    }
  };

  return (
    <div className="p-6 space-y-6" data-testid="employer-reports-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Automated Reports</h1>
          <p className="text-gray-500 text-sm mt-1">Daily + weekly recruiter performance delivered automatically to team leaders.</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadData} disabled={loading} data-testid="reports-refresh-btn">
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Schedule banner */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="border-l-4 border-l-blue-600">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-blue-600" />
              <CardTitle className="text-base">Daily Report</CardTitle>
              <Badge variant="secondary" className="ml-auto">6:30 PM IST</Badge>
            </div>
            <CardDescription>Sent every evening. Activity past 6:30 PM rolls to next day.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              size="sm"
              variant="default"
              onClick={() => triggerRun('daily')}
              disabled={triggering.daily}
              data-testid="trigger-daily-now-btn"
            >
              <Mail className="w-4 h-4 mr-2" />
              {triggering.daily ? 'Sending…' : 'Send Daily Report Now'}
            </Button>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-600">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-emerald-600" />
              <CardTitle className="text-base">Weekly Report</CardTitle>
              <Badge variant="secondary" className="ml-auto">Mon 9:00 AM IST</Badge>
            </div>
            <CardDescription>Previous Mon–Sun activity. Includes stage transitions for older mandates too.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              size="sm"
              variant="default"
              onClick={() => triggerRun('weekly')}
              disabled={triggering.weekly}
              data-testid="trigger-weekly-now-btn"
            >
              <Mail className="w-4 h-4 mr-2" />
              {triggering.weekly ? 'Sending…' : 'Send Weekly Report Now'}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Teams table with download buttons */}
      <Card data-testid="teams-downloads-card">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5" />
            <CardTitle>Preview Reports by Team</CardTitle>
          </div>
          <CardDescription>Download the Excel your team leaders will receive — no email sent.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-gray-400 text-sm py-8 text-center">Loading teams…</div>
          ) : teams.length === 0 ? (
            <div className="text-gray-500 text-sm py-8 text-center">No active teams yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500 uppercase text-xs tracking-wider">
                    <th className="px-3 py-2 font-medium">Team</th>
                    <th className="px-3 py-2 font-medium">Leader</th>
                    <th className="px-3 py-2 font-medium">Recruiters</th>
                    <th className="px-3 py-2 font-medium text-right">Daily Preview</th>
                    <th className="px-3 py-2 font-medium text-right">Weekly Preview</th>
                  </tr>
                </thead>
                <tbody>
                  {teams.map((team) => {
                    const dKey = `${team.id}_daily`;
                    const wKey = `${team.id}_weekly`;
                    return (
                      <tr key={team.id} className="border-b hover:bg-gray-50" data-testid={`team-row-${team.id}`}>
                        <td className="px-3 py-3 font-medium">{team.name || '(unnamed)'}</td>
                        <td className="px-3 py-3 text-gray-600">{team.employer_name || '—'}</td>
                        <td className="px-3 py-3 text-gray-600">{(team.recruiter_ids || []).length}</td>
                        <td className="px-3 py-3 text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => downloadPreview(team.id, team.name || 'Team', 'daily')}
                            disabled={downloading[dKey]}
                            data-testid={`download-daily-${team.id}`}
                          >
                            <Download className="w-3 h-3 mr-1" />
                            {downloading[dKey] ? '…' : 'Download'}
                          </Button>
                        </td>
                        <td className="px-3 py-3 text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => downloadPreview(team.id, team.name || 'Team', 'weekly')}
                            disabled={downloading[wKey]}
                            data-testid={`download-weekly-${team.id}`}
                          >
                            <Download className="w-3 h-3 mr-1" />
                            {downloading[wKey] ? '…' : 'Download'}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
