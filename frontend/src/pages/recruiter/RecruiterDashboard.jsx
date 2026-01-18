import { useState, useEffect } from 'react';
import { statsAPI, jobAPI, applicationAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Link } from 'react-router-dom';
import { Briefcase, Users, TrendingUp, Clock, ArrowRight, ClipboardList, Search, FileText, CheckCircle, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';

export default function RecruiterDashboard() {
  const [stats, setStats] = useState(null);
  const [recentJobs, setRecentJobs] = useState([]);
  const [recentApplications, setRecentApplications] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, jobsRes, appsRes] = await Promise.all([
        statsAPI.recruiter(),
        jobAPI.getAll(),
        applicationAPI.getAll(),
      ]);
      setStats(statsRes.data);
      setRecentJobs(jobsRes.data.slice(0, 5));
      setRecentApplications(appsRes.data.slice(0, 5));
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

  // Pipeline stages aligned with SOP terminology
  const pipelineStages = [
    { id: 'applied', label: 'New CVs', desc: 'Awaiting screening', color: 'bg-blue-500' },
    { id: 'shortlisted', label: 'Shortlisted', desc: 'Ready for interview', color: 'bg-amber-500' },
    { id: 'interview', label: 'Interview', desc: 'In process', color: 'bg-purple-500' },
    { id: 'offered', label: 'Offered', desc: 'Offer extended', color: 'bg-green-500' },
    { id: 'hired', label: 'Hired', desc: 'Joined', color: 'bg-emerald-500' },
  ];

  return (
    <div className="space-y-8" data-testid="recruiter-dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Recruiter Dashboard</h1>
          <p className="text-slate-500 mt-1">Manage mandates and candidate pipeline</p>
        </div>
        <div className="flex gap-2">
          <Link to="/recruiter/pipeline">
            <Button variant="outline">
              <ClipboardList className="w-4 h-4 mr-2" /> View Pipeline
            </Button>
          </Link>
          <Link to="/recruiter/find-candidates">
            <Button className="bg-[#7CB342] hover:bg-[#689F38]">
              <Search className="w-4 h-4 mr-2" /> AI Screening
            </Button>
          </Link>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 stagger-children">
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <div className="w-12 h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center mb-4">
              <Briefcase className="w-6 h-6 text-[#7CB342]" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">{stats?.total_jobs || 0}</p>
            <p className="text-sm text-slate-500 mt-1">Active Mandates</p>
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
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <div className="w-12 h-12 rounded-xl bg-amber-50 flex items-center justify-center mb-4">
              <AlertCircle className="w-6 h-6 text-amber-600" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">
              {stats?.pipeline_stats?.applied || 0}
            </p>
            <p className="text-sm text-slate-500 mt-1">Pending Review</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-6">
            <div className="w-12 h-12 rounded-xl bg-green-50 flex items-center justify-center mb-4">
              <CheckCircle className="w-6 h-6 text-green-600" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">
              {stats?.pipeline_stats?.hired || 0}
            </p>
            <p className="text-sm text-slate-500 mt-1">Hired This Month</p>
          </CardContent>
        </Card>
      </div>

      {/* Recruiter Workflow - SOP Aligned */}
      <Card className="border-slate-200 border-l-4 border-l-[#7CB342]">
        <CardHeader>
          <CardTitle className="font-heading text-lg">Daily Workflow</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Link to="/recruiter/jobs" className="block">
              <div className="p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors text-center">
                <FileText className="w-8 h-8 text-[#7CB342] mx-auto mb-2" />
                <p className="font-medium text-slate-900">1. View Mandates</p>
                <p className="text-xs text-slate-500 mt-1">Check assigned jobs</p>
              </div>
            </Link>
            <Link to="/recruiter/pipeline" className="block">
              <div className="p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors text-center">
                <Search className="w-8 h-8 text-blue-600 mx-auto mb-2" />
                <p className="font-medium text-slate-900">2. Screen CVs</p>
                <p className="text-xs text-slate-500 mt-1">Review with AI advisory</p>
              </div>
            </Link>
            <Link to="/recruiter/pipeline" className="block">
              <div className="p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors text-center">
                <ClipboardList className="w-8 h-8 text-purple-600 mx-auto mb-2" />
                <p className="font-medium text-slate-900">3. Move Pipeline</p>
                <p className="text-xs text-slate-500 mt-1">Shortlist or reject</p>
              </div>
            </Link>
            <Link to="/recruiter/pipeline" className="block">
              <div className="p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors text-center">
                <CheckCircle className="w-8 h-8 text-green-600 mx-auto mb-2" />
                <p className="font-medium text-slate-900">4. Track Progress</p>
                <p className="text-xs text-slate-500 mt-1">Monitor outcomes</p>
              </div>
            </Link>
          </div>
        </CardContent>
      </Card>

      {/* Pipeline Overview */}
      <Card className="border-slate-200">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-[#7CB342]" />
            Pipeline Status
          </CardTitle>
          <Link to="/recruiter/pipeline" className="text-sm text-[#7CB342] hover:underline">
            Open Pipeline Board
          </Link>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {pipelineStages.map((stage) => (
              <div
                key={stage.id}
                className={`p-4 rounded-lg bg-slate-50 border-l-4 border-l-${stage.color.replace('bg-', '')} hover:bg-slate-100 transition-colors cursor-pointer`}
                style={{ borderLeftColor: stage.color === 'bg-blue-500' ? '#3B82F6' : 
                         stage.color === 'bg-amber-500' ? '#F59E0B' :
                         stage.color === 'bg-purple-500' ? '#8B5CF6' :
                         stage.color === 'bg-green-500' ? '#22C55E' : '#10B981' }}
              >
                <p className="text-2xl font-bold text-slate-900">
                  {stats?.pipeline_stats?.[stage.id] || 0}
                </p>
                <p className="text-sm font-medium text-slate-700">{stage.label}</p>
                <p className="text-xs text-slate-400 mt-1">{stage.desc}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Mandates */}
        <Card className="border-slate-200">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="font-heading text-lg flex items-center gap-2">
              <Briefcase className="w-5 h-5 text-[#7CB342]" />
              Active Mandates
            </CardTitle>
            <Link to="/recruiter/jobs" className="text-sm text-[#7CB342] hover:underline">
              View all
            </Link>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {recentJobs.map((job) => (
                <div
                  key={job.id}
                  className="flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-slate-900 truncate">{job.title}</p>
                    <p className="text-sm text-slate-500">{job.location}</p>
                  </div>
                  <div className="text-right ml-4">
                    <p className="font-semibold text-[#7CB342]">{job.applicant_count}</p>
                    <p className="text-xs text-slate-500">candidates</p>
                  </div>
                </div>
              ))}
              {recentJobs.length === 0 && (
                <div className="text-center py-6">
                  <Briefcase className="w-10 h-10 text-slate-300 mx-auto mb-2" />
                  <p className="text-slate-500 text-sm">No active mandates assigned</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Recent Pipeline Activity */}
        <Card className="border-slate-200">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="font-heading text-lg flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#7CB342]" />
              Recent Pipeline Activity
            </CardTitle>
            <Link to="/recruiter/pipeline" className="text-sm text-[#7CB342] hover:underline">
              View pipeline
            </Link>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {recentApplications.map((app) => (
                <div
                  key={app.id}
                  className="flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                      <span className="text-[#7CB342] font-semibold text-sm">
                        {app.candidate_name?.charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium text-slate-900 truncate">{app.candidate_name}</p>
                      <p className="text-sm text-slate-500 truncate">{app.job_title}</p>
                    </div>
                  </div>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium capitalize ${
                    app.stage === 'applied' ? 'bg-blue-50 text-blue-600' :
                    app.stage === 'shortlisted' ? 'bg-amber-50 text-amber-600' :
                    app.stage === 'interview' ? 'bg-purple-50 text-purple-600' :
                    app.stage === 'offered' ? 'bg-green-50 text-green-600' :
                    'bg-emerald-50 text-emerald-600'
                  }`}>
                    {app.stage}
                  </span>
                </div>
              ))}
              {recentApplications.length === 0 && (
                <div className="text-center py-6">
                  <ClipboardList className="w-10 h-10 text-slate-300 mx-auto mb-2" />
                  <p className="text-slate-500 text-sm">No pipeline activity yet</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
