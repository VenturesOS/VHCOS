import { useState, useEffect } from 'react';
import { statsAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Briefcase, Users, TrendingUp, Clock } from 'lucide-react';
import { toast } from 'sonner';

export default function RecruiterDashboard() {
  const [stats, setStats] = useState(null);
  const [recentJobs, setRecentJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, jobsRes] = await Promise.all([
        statsAPI.recruiter(),
        jobAPI.getAll(),
      ]);
      setStats(statsRes.data);
      setRecentJobs(jobsRes.data.slice(0, 5));
    } catch (error) {
      toast.error('Failed to load dashboard');
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

  const pipelineStages = ['applied', 'shortlisted', 'interview', 'offered', 'hired'];

  return (
    <div className="space-y-8" data-testid="recruiter-dashboard">
      <div>
        <h1 className="font-heading text-3xl font-bold text-slate-900">Recruiter Dashboard</h1>
        <p className="text-slate-500 mt-1">Manage candidates and recruitment pipeline</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 stagger-children">
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <div className="w-12 h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center mb-4">
              <Briefcase className="w-6 h-6 text-[#7CB342]" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">{stats?.total_jobs || 0}</p>
            <p className="text-sm text-slate-500 mt-1">Active Jobs</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center mb-4">
              <Users className="w-6 h-6 text-blue-600" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">{stats?.total_candidates || 0}</p>
            <p className="text-sm text-slate-500 mt-1">Total Candidates</p>
          </CardContent>
        </Card>
      </div>

      {/* Pipeline Overview */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-[#7CB342]" />
            Pipeline Overview
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {pipelineStages.map((stage) => (
              <div
                key={stage}
                className={`p-4 rounded-lg bg-slate-50 border-l-4 stage-${stage}`}
              >
                <p className="text-2xl font-bold text-slate-900">
                  {stats?.pipeline_stats?.[stage] || 0}
                </p>
                <p className="text-sm text-slate-500 capitalize">{stage}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Recent Jobs */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Clock className="w-5 h-5 text-[#7CB342]" />
            Recent Jobs
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {recentJobs.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <div>
                  <p className="font-medium text-slate-900">{job.title}</p>
                  <p className="text-sm text-slate-500">{job.location} • {job.job_type}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-[#7CB342]">{job.applicant_count}</p>
                  <p className="text-xs text-slate-500">applicants</p>
                </div>
              </div>
            ))}
            {recentJobs.length === 0 && (
              <p className="text-slate-500 text-sm text-center py-4">No jobs available</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
