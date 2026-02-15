import { useState, useEffect } from 'react';
import { statsAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Users, Briefcase, FileText, Building2, TrendingUp, Clock } from 'lucide-react';
import { toast } from 'sonner';

export default function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const res = await statsAPI.admin();
      setStats(res.data);
    } catch (error) {
      toast.error('Failed to load dashboard stats');
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

  const statCards = [
    {
      label: 'Total Users',
      value: stats?.total_users || 0,
      icon: Users,
      color: 'bg-blue-50 text-blue-600',
    },
    {
      label: 'Active Jobs',
      value: stats?.total_jobs || 0,
      icon: Briefcase,
      color: 'bg-[#DCFCE7] text-[#7CB342]',
    },
    {
      label: 'Applications',
      value: stats?.total_applications || 0,
      icon: FileText,
      color: 'bg-amber-50 text-amber-600',
    },
    {
      label: 'Companies',
      value: stats?.total_companies || 0,
      icon: Building2,
      color: 'bg-purple-50 text-purple-600',
    },
  ];

  return (
    <div className="space-y-8" data-testid="admin-dashboard">
      {/* Header */}
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Admin Dashboard</h1>
        <p className="text-slate-500 mt-1">Overview of your recruitment platform</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 stagger-children">
        {statCards.map((stat) => (
          <Card key={stat.label} className="border-slate-200 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className={`w-12 h-12 rounded-xl ${stat.color} flex items-center justify-center mb-4`}>
                <stat.icon className="w-6 h-6" />
              </div>
              <p className="font-heading text-2xl sm:text-3xl font-bold text-slate-900">{stat.value}</p>
              <p className="text-sm text-slate-500 mt-1">{stat.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Users by Role */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading text-lg flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-[#7CB342]" />
              Users by Role
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {Object.entries(stats?.users_by_role || {}).map(([role, count]) => (
                <div key={role} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full bg-[#7CB342]" />
                    <span className="capitalize text-slate-700">{role}</span>
                  </div>
                  <span className="font-semibold text-slate-900">{count}</span>
                </div>
              ))}
              {Object.keys(stats?.users_by_role || {}).length === 0 && (
                <p className="text-slate-500 text-sm">No users yet</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Recent Applications */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading text-lg flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#7CB342]" />
              Recent Applications
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {stats?.recent_applications?.slice(0, 5).map((app) => (
                <div
                  key={app.id}
                  className="flex items-center justify-between p-3 bg-slate-50 rounded-lg"
                >
                  <div>
                    <p className="font-medium text-slate-900 text-sm">{app.candidate_name}</p>
                    <p className="text-xs text-slate-500">{app.job_title}</p>
                  </div>
                  <span className={`badge badge-${app.stage}`}>{app.stage}</span>
                </div>
              ))}
              {(!stats?.recent_applications || stats.recent_applications.length === 0) && (
                <p className="text-slate-500 text-sm">No recent applications</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
