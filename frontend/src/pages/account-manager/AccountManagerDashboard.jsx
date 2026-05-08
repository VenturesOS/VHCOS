import { useState, useEffect } from 'react';
import { accountManagerAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Link } from 'react-router-dom';
import { Building2, Briefcase, Users, TrendingUp, ArrowRight, LayoutDashboard } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../../lib/auth';

export default function AccountManagerDashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, companiesRes] = await Promise.all([
        accountManagerAPI.getDashboardStats(),
        accountManagerAPI.getMyCompanies(),
      ]);
      setStats(statsRes.data);
      setCompanies(companiesRes.data.companies || []);
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

  const stageStats = stats?.stage_stats || {};
  const totalPipeline = Object.values(stageStats).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-8" data-testid="am-dashboard">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">
          Account Manager Dashboard
        </h1>
        <p className="text-slate-500 mt-1">Welcome back, {user?.name}</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card data-testid="stat-companies">
          <CardContent className="p-4 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <Building2 className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{stats?.total_companies || 0}</p>
                <p className="text-xs text-slate-500">My Accounts</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card data-testid="stat-jobs">
          <CardContent className="p-4 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <Briefcase className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{stats?.active_jobs || 0}</p>
                <p className="text-xs text-slate-500">Active Jobs</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card data-testid="stat-applications">
          <CardContent className="p-4 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
                <Users className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{stats?.total_applications || 0}</p>
                <p className="text-xs text-slate-500">Applications</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card data-testid="stat-pipeline">
          <CardContent className="p-4 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{totalPipeline}</p>
                <p className="text-xs text-slate-500">In Pipeline</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* My Companies */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-lg font-semibold text-slate-900">My Accounts</h2>
        </div>
        {companies.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-slate-500">
              No companies assigned yet. Contact your admin to get started.
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {companies.map((company) => (
              <Link key={company.id} to={`/${user?.role === 'employer' ? 'employer' : 'recruiter'}/account-manager/company/${company.id}`}>
                <Card className="hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-[#7CB342]" data-testid={`company-card-${company.id}`}>
                  <CardContent className="p-4 sm:p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center">
                          <Building2 className="w-6 h-6 text-slate-600" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-slate-900">{company.name}</h3>
                          <p className="text-sm text-slate-500">{company.industry || 'N/A'}</p>
                          {company.location && (
                            <p className="text-xs text-slate-400 mt-1">{company.location}</p>
                          )}
                        </div>
                      </div>
                      <ArrowRight className="w-5 h-5 text-slate-400" />
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Pipeline Summary */}
      {Object.keys(stageStats).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Pipeline Overview (All Accounts)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {Object.entries(stageStats).map(([stage, count]) => (
                <div key={stage} className="text-center p-3 bg-slate-50 rounded-lg">
                  <p className="text-xl font-bold text-slate-900">{count}</p>
                  <p className="text-xs text-slate-500 capitalize">{stage.replace(/_/g, ' ')}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
