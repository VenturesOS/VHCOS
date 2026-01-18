import { useState, useEffect } from 'react';
import { statsAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { BarChart3, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';

const COLORS = ['#3B82F6', '#F59E0B', '#8B5CF6', '#7CB342', '#22C55E', '#EF4444'];

export default function AnalyticsPage() {
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, jobsRes] = await Promise.all([
        statsAPI.employer(),
        jobAPI.getAll(),
      ]);
      setStats(statsRes.data);
      setJobs(jobsRes.data);
    } catch (error) {
      toast.error('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  const stageData = Object.entries(stats?.stage_stats || {}).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value,
  }));

  const jobData = jobs.slice(0, 5).map((job) => ({
    name: job.title.length > 15 ? job.title.substring(0, 15) + '...' : job.title,
    applicants: job.applicant_count,
  }));

  return (
    <div className="space-y-6" data-testid="analytics-page">
      <div>
        <h1 className="font-heading text-3xl font-bold text-slate-900">Analytics</h1>
        <p className="text-slate-500 mt-1">Track your recruitment performance</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <p className="text-sm text-slate-500">Total Jobs</p>
            <p className="font-heading text-3xl font-bold text-slate-900 mt-1">
              {stats?.my_jobs || 0}
            </p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <p className="text-sm text-slate-500">Total Applicants</p>
            <p className="font-heading text-3xl font-bold text-slate-900 mt-1">
              {stats?.total_applicants || 0}
            </p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <p className="text-sm text-slate-500">Hired Candidates</p>
            <p className="font-heading text-3xl font-bold text-[#7CB342] mt-1">
              {stats?.stage_stats?.hired || 0}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Applications by Stage */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading text-lg flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-[#7CB342]" />
              Applications by Stage
            </CardTitle>
          </CardHeader>
          <CardContent>
            {stageData.length > 0 ? (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={stageData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={5}
                      dataKey="value"
                      label={({ name, value }) => `${name}: ${value}`}
                    >
                      {stageData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">
                No data available
              </div>
            )}
          </CardContent>
        </Card>

        {/* Applicants by Job */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading text-lg flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-[#7CB342]" />
              Applicants by Job
            </CardTitle>
          </CardHeader>
          <CardContent>
            {jobData.length > 0 ? (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={jobData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="applicants" fill="#7CB342" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">
                No jobs posted yet
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
