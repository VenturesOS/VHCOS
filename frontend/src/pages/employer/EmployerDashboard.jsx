import { useState, useEffect } from 'react';
import { statsAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Link } from 'react-router-dom';
import { Briefcase, Users, TrendingUp, Plus, Clock, ArrowRight, Sparkles, Search, CheckCircle } from 'lucide-react';
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

  const hasJobs = recentJobs.length > 0;

  return (
    <div className="space-y-8" data-testid="employer-dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Employer Dashboard</h1>
          <p className="text-slate-500 mt-1">Manage your hiring pipeline</p>
        </div>
        <Link to="/employer/jobs/new">
          <Button className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="post-job-btn">
            <Plus className="w-4 h-4 mr-2" /> Post New Job
          </Button>
        </Link>
      </div>

      {/* Quick Start Flow - Only show when no jobs */}
      {!hasJobs && (
        <Card className="border-[#7CB342] bg-gradient-to-r from-[#DCFCE7] to-white">
          <CardContent className="p-6">
            <h2 className="font-heading text-xl font-bold text-slate-900 mb-4">
              Get Started in 3 Simple Steps
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex items-start gap-3 p-4 bg-white rounded-lg border border-slate-200">
                <div className="w-8 h-8 rounded-full bg-[#7CB342] text-white flex items-center justify-center font-bold shrink-0">1</div>
                <div>
                  <p className="font-semibold text-slate-900">Post a Job</p>
                  <p className="text-sm text-slate-500">Define your role requirements</p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-4 bg-white rounded-lg border border-slate-200">
                <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center font-bold shrink-0">2</div>
                <div>
                  <p className="font-semibold text-slate-700">Find Candidates</p>
                  <p className="text-sm text-slate-500">AI matches candidates to your job</p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-4 bg-white rounded-lg border border-slate-200">
                <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center font-bold shrink-0">3</div>
                <div>
                  <p className="font-semibold text-slate-700">Review & Decide</p>
                  <p className="text-sm text-slate-500">Shortlist or reject candidates</p>
                </div>
              </div>
            </div>
            <div className="mt-4">
              <Link to="/employer/jobs/new">
                <Button className="bg-[#7CB342] hover:bg-[#689F38]">
                  <Plus className="w-4 h-4 mr-2" /> Post Your First Job
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 stagger-children">
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
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <div className="w-12 h-12 rounded-xl bg-green-50 flex items-center justify-center mb-4">
              <CheckCircle className="w-6 h-6 text-green-600" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">
              {stats?.stage_stats?.hired || 0}
            </p>
            <p className="text-sm text-slate-500 mt-1">Hired</p>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      {hasJobs && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="border-slate-200 hover:border-[#7CB342] transition-colors">
            <CardContent className="p-6">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-xl bg-purple-50 flex items-center justify-center">
                  <Sparkles className="w-7 h-7 text-purple-600" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-slate-900">Find Matching Candidates</h3>
                  <p className="text-sm text-slate-500">Use AI to discover candidates that match your job requirements</p>
                </div>
                <Link to="/employer/find-candidates">
                  <Button variant="outline" size="sm">
                    <Search className="w-4 h-4 mr-2" /> Find Candidates
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200 hover:border-[#7CB342] transition-colors">
            <CardContent className="p-6">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-xl bg-blue-50 flex items-center justify-center">
                  <Users className="w-7 h-7 text-blue-600" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-slate-900">Review Applicants</h3>
                  <p className="text-sm text-slate-500">View and manage candidates who applied to your jobs</p>
                </div>
                <Link to="/employer/applicants">
                  <Button variant="outline" size="sm">
                    <ArrowRight className="w-4 h-4 mr-2" /> View Applicants
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Hiring Pipeline */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-[#7CB342]" />
            Hiring Pipeline
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { id: 'applied', label: 'Applied', desc: 'New applications' },
              { id: 'shortlisted', label: 'Shortlisted', desc: 'Ready for interview' },
              { id: 'interview', label: 'Interview', desc: 'In interview process' },
              { id: 'offered', label: 'Offered', desc: 'Offer extended' },
              { id: 'hired', label: 'Hired', desc: 'Successfully hired' },
            ].map((stage) => (
              <div
                key={stage.id}
                className={`p-4 rounded-lg bg-slate-50 border-l-4 stage-${stage.id} hover:bg-slate-100 transition-colors`}
              >
                <p className="text-2xl font-bold text-slate-900">
                  {stats?.stage_stats?.[stage.id] || 0}
                </p>
                <p className="text-sm font-medium text-slate-700">{stage.label}</p>
                <p className="text-xs text-slate-400 mt-1">{stage.desc}</p>
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
            Your Active Jobs
          </CardTitle>
          <Link to="/employer/jobs" className="text-sm text-[#7CB342] hover:underline">
            View all jobs
          </Link>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {recentJobs.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <div className="flex-1">
                  <p className="font-medium text-slate-900">{job.title}</p>
                  <p className="text-sm text-slate-500">{job.location} • {job.job_type}</p>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="font-semibold text-[#7CB342]">{job.applicant_count}</p>
                    <p className="text-xs text-slate-500">applicants</p>
                  </div>
                  <Link to={`/employer/find-candidates?job=${job.id}`}>
                    <Button variant="outline" size="sm" className="text-[#7CB342] border-[#7CB342]">
                      <Sparkles className="w-4 h-4 mr-1" /> Find Matches
                    </Button>
                  </Link>
                </div>
              </div>
            ))}
            {recentJobs.length === 0 && (
              <div className="text-center py-8">
                <Briefcase className="w-12 h-12 text-slate-300 mx-auto mb-2" />
                <p className="text-slate-500 mb-2">No jobs posted yet</p>
                <p className="text-sm text-slate-400 mb-4">Post your first job to start receiving applications</p>
                <Link to="/employer/jobs/new">
                  <Button className="bg-[#7CB342] hover:bg-[#689F38]" size="sm">
                    <Plus className="w-4 h-4 mr-2" /> Post Your First Job
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
