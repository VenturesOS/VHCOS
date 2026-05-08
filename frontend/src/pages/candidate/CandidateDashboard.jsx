import { useState, useEffect } from 'react';
import { statsAPI, applicationAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Link } from 'react-router-dom';
import { FileText, Briefcase, Mail, Search, Clock, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';

export default function CandidateDashboard() {
  const [stats, setStats] = useState(null);
  const [recentApplications, setRecentApplications] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, appsRes] = await Promise.all([
        statsAPI.candidate(),
        applicationAPI.getAll(),
      ]);
      setStats(statsRes.data);
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

  return (
    <div className="space-y-8" data-testid="candidate-dashboard">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Welcome back!</h1>
          <p className="text-slate-500 mt-1">Find your dream job today</p>
        </div>
        <Link to="/candidate/jobs">
          <Button className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="browse-jobs-btn">
            <Search className="w-4 h-4 mr-2" /> Browse Jobs
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6 stagger-children">
        <Card className="border-slate-200">
          <CardContent className="p-4 sm:p-6">
            <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center mb-4">
              <FileText className="w-6 h-6 text-[#7CB342]" />
            </div>
            <p className="font-heading text-2xl sm:text-3xl font-bold text-slate-900">{stats?.my_applications || 0}</p>
            <p className="text-sm text-slate-500 mt-1">My Applications</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 sm:p-6">
            <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl bg-blue-50 flex items-center justify-center mb-4">
              <Briefcase className="w-6 h-6 text-blue-600" />
            </div>
            <p className="font-heading text-2xl sm:text-3xl font-bold text-slate-900">{stats?.active_jobs || 0}</p>
            <p className="text-sm text-slate-500 mt-1">Active Jobs</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 sm:p-6">
            <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl bg-amber-50 flex items-center justify-center mb-4">
              <Clock className="w-6 h-6 text-amber-600" />
            </div>
            <p className="font-heading text-3xl font-bold text-slate-900">
              {stats?.application_stages?.interview || 0}
            </p>
            <p className="text-sm text-slate-500 mt-1">Interviews</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 sm:p-6">
            <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl bg-purple-50 flex items-center justify-center mb-4">
              <Mail className="w-6 h-6 text-purple-600" />
            </div>
            <p className="font-heading text-2xl sm:text-3xl font-bold text-slate-900">{stats?.unread_messages || 0}</p>
            <p className="text-sm text-slate-500 mt-1">Unread Messages</p>
          </CardContent>
        </Card>
      </div>

      {/* Application Status */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg">Application Status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {['sourced', 'submitted_to_client', 'shortlisted', 'interview', 'offered', 'hired'].map((stage) => (
              <div
                key={stage}
                className={`p-4 rounded-lg bg-slate-50 border-l-4 stage-${stage}`}
              >
                <p className="text-2xl font-bold text-slate-900">
                  {stats?.application_stages?.[stage] || 0}
                </p>
                <p className="text-sm text-slate-500 capitalize">{stage}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Recent Applications */}
      <Card className="border-slate-200">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="font-heading text-lg">Recent Applications</CardTitle>
          <Link to="/candidate/applications" className="text-sm text-[#7CB342] hover:underline flex items-center gap-1">
            View all <ArrowRight className="w-4 h-4" />
          </Link>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {recentApplications.map((app) => (
              <div
                key={app.id}
                className="flex items-center justify-between p-4 bg-slate-50 rounded-lg"
              >
                <div>
                  <p className="font-medium text-slate-900">{app.job_title}</p>
                  <p className="text-sm text-slate-500">{app.company_name || 'Company'}</p>
                </div>
                <span className={`badge badge-${app.stage}`}>{app.stage}</span>
              </div>
            ))}
            {recentApplications.length === 0 && (
              <div className="text-center py-8">
                <FileText className="w-12 h-12 text-slate-300 mx-auto mb-2" />
                <p className="text-slate-500">No applications yet</p>
                <Link to="/candidate/jobs">
                  <Button className="mt-4 bg-[#7CB342] hover:bg-[#689F38]" size="sm">
                    Start Applying
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
