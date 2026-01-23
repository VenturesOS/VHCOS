import { useState, useEffect } from 'react';
import { analyticsAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import { toast } from 'sonner';
import { 
  TrendingUp, DollarSign, Clock, Users, Briefcase, 
  Target, Building2, Percent, UserCircle
} from 'lucide-react';

export default function EmployerAnalyticsPage() {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    loadAnalytics();
  }, [dateFrom, dateTo]);

  const loadAnalytics = async () => {
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      
      const res = await analyticsAPI.getEmployer(params);
      setAnalytics(res.data);
    } catch (error) {
      toast.error('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value) => {
    if (!value) return '₹0';
    if (value >= 10000000) return `₹${(value / 10000000).toFixed(2)}Cr`;
    if (value >= 100000) return `₹${(value / 100000).toFixed(2)}L`;
    return `₹${value.toLocaleString('en-IN')}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  const kpis = analytics?.kpis || {};
  const teamPerformance = analytics?.team_performance || [];
  const companyRevenue = analytics?.company_revenue || [];
  const recruiterContribution = analytics?.recruiter_contribution || [];

  return (
    <div className="space-y-6" data-testid="employer-analytics-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">My Analytics</h1>
          <p className="text-slate-500 mt-1">Performance insights for your companies and teams</p>
        </div>
        
        {/* Date Filters */}
        <div className="flex gap-3">
          <div className="w-40">
            <Input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              placeholder="From"
            />
          </div>
          <div className="w-40">
            <Input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              placeholder="To"
            />
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Briefcase className="w-4 h-4 text-[#7CB342]" />
              <span className="text-xs text-slate-500">Active Mandates</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{kpis.active_mandates || 0}</p>
          </CardContent>
        </Card>
        
        <Card className="border-amber-200 bg-amber-50/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-4 h-4 text-amber-600" />
              <span className="text-xs text-amber-700">Pipeline Revenue</span>
            </div>
            <p className="text-2xl font-bold text-amber-700">{formatCurrency(kpis.pipeline_revenue)}</p>
          </CardContent>
        </Card>
        
        <Card className="border-green-200 bg-green-50/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <DollarSign className="w-4 h-4 text-green-600" />
              <span className="text-xs text-green-700">Closed Revenue</span>
            </div>
            <p className="text-2xl font-bold text-green-700">{formatCurrency(kpis.closed_revenue)}</p>
          </CardContent>
        </Card>
        
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-4 h-4 text-blue-600" />
              <span className="text-xs text-slate-500">Offers Pending</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{kpis.offers_pending || 0}</p>
          </CardContent>
        </Card>
        
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Percent className="w-4 h-4 text-purple-600" />
              <span className="text-xs text-slate-500">Avg Fee %</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{kpis.avg_fee_percentage || 0}%</p>
          </CardContent>
        </Card>
      </div>

      {/* Data Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Team Performance */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <Users className="w-5 h-5 text-[#7CB342]" />
              Team Performance
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <th className="text-left py-3 px-4 font-medium text-slate-600">Team</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Mandates</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Hired</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  {teamPerformance.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="text-center py-8 text-slate-400">No team data</td>
                    </tr>
                  ) : (
                    teamPerformance.map((team, idx) => (
                      <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-3 px-4 font-medium text-slate-900">{team.team_name}</td>
                        <td className="py-3 px-4 text-right text-slate-600">{team.mandates}</td>
                        <td className="py-3 px-4 text-right text-green-600">{team.hired}</td>
                        <td className="py-3 px-4 text-right text-[#7CB342]">{formatCurrency(team.pipeline_revenue + team.closed_revenue)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Company Revenue */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <Building2 className="w-5 h-5 text-[#7CB342]" />
              Company-wise Revenue
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <th className="text-left py-3 px-4 font-medium text-slate-600">Company</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Mandates</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Pipeline</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Closed</th>
                  </tr>
                </thead>
                <tbody>
                  {companyRevenue.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="text-center py-8 text-slate-400">No company data</td>
                    </tr>
                  ) : (
                    companyRevenue.map((company, idx) => (
                      <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-3 px-4 font-medium text-slate-900">{company.company_name}</td>
                        <td className="py-3 px-4 text-right text-slate-600">{company.mandates}</td>
                        <td className="py-3 px-4 text-right text-amber-600">{formatCurrency(company.pipeline)}</td>
                        <td className="py-3 px-4 text-right text-green-600">{formatCurrency(company.closed)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recruiter Contribution */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading flex items-center gap-2">
            <UserCircle className="w-5 h-5 text-[#7CB342]" />
            Recruiter Contribution
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Recruiter</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Mandates</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Applications</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Hired</th>
                  <th className="text-right py-3 px-4 font-medium text-slate-600">Revenue</th>
                </tr>
              </thead>
              <tbody>
                {recruiterContribution.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-slate-400">No recruiter data</td>
                  </tr>
                ) : (
                  recruiterContribution.map((rec, idx) => (
                    <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="py-3 px-4 font-medium text-slate-900">{rec.recruiter_name}</td>
                      <td className="py-3 px-4 text-right text-slate-600">{rec.mandates}</td>
                      <td className="py-3 px-4 text-right text-slate-600">{rec.applications}</td>
                      <td className="py-3 px-4 text-right text-green-600">{rec.hired}</td>
                      <td className="py-3 px-4 text-right text-[#7CB342]">{formatCurrency(rec.revenue)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
