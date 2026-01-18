import { useState, useEffect } from 'react';
import { statsAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Link } from 'react-router-dom';
import { Briefcase, Users, TrendingUp, Plus, Clock } from 'lucide-react';
import { toast } from 'sonner';

export default function EmployerDashboard() {
  const [stats, setStats] = useState(null);
  const [recentJobs, setRecentJobs] = useState([]);
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

  return (
    <div className="space-y-8" data-testid="employer-dashboard">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Employer Dashboard</h1>
          <p className="text-slate-500 mt-1">Manage your job postings and applicants</p>
        </div>
        <Link to="/employer/jobs/new">
          <Button className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="post-job-btn">
            <Plus className="w-4 h-4 mr-2" /> Post New Job
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 stagger-children">
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <div className="w-12 h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center mb-4">
              <Briefcase className="w-6 h-6 text-[#7CB342]" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">{stats?.my_jobs || 0}</p>
            <p className="text-sm text-slate-500 mt-1">Active Jobs</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center mb-4">
              <Users className="w-6 h-6 text-blue-600" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">{stats?.total_applicants || 0}</p>
            <p className="text-sm text-slate-500 mt-1">Total Applicants</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <div className="w-12 h-12 rounded-xl bg-amber-50 flex items-center justify-center mb-4">
              <TrendingUp className="w-6 h-6 text-amber-600" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">
              {stats?.stage_stats?.shortlisted || 0}
            </p>
            <p className="text-sm text-slate-500 mt-1">Shortlisted</p>
          </CardContent>
        </Card>
      </div>

      {/* Application Stages */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-[#7CB342]" />
            Application Stages
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {['applied', 'shortlisted', 'interview', 'offered', 'hired'].map((stage) => (
              <div
                key={stage}
                className={`p-4 rounded-lg bg-slate-50 border-l-4 stage-${stage}`}
              >
                <p className="text-2xl font-bold text-slate-900">
                  {stats?.stage_stats?.[stage] || 0}
                </p>
                <p className="text-sm text-slate-500 capitalize">{stage}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Recent Jobs */}
      <Card className="border-slate-200">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Clock className="w-5 h-5 text-[#7CB342]" />
            Your Recent Jobs
          </CardTitle>
          <Link to="/employer/jobs" className="text-sm text-[#7CB342] hover:underline">
            View all
          </Link>
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
              <div className="text-center py-8">
                <Briefcase className="w-12 h-12 text-slate-300 mx-auto mb-2" />
                <p className="text-slate-500">No jobs posted yet</p>
                <Link to="/employer/jobs/new">
                  <Button className="mt-4 bg-[#7CB342] hover:bg-[#689F38]" size="sm">
                    Post Your First Job
                  </Button>
                </Link>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
