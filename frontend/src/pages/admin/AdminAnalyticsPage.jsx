import { useState, useEffect } from 'react';
import { analyticsAPI, userAPI, companyAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { toast } from 'sonner';
import { 
  TrendingUp, DollarSign, Clock, Users, Briefcase, 
  Target, Building2, BarChart3, PieChart, UserCircle
} from 'lucide-react';

export default function AdminAnalyticsPage() {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [employers, setEmployers] = useState([]);
  const [companies, setCompanies] = useState([]);
  
  // Filters
  const [filters, setFilters] = useState({
    employer_id: 'all',
    company_id: 'all',
    date_from: '',
    date_to: '',
  });

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    loadAnalytics();
  }, [filters]);

  const loadInitialData = async () => {
    try {
      const [employersRes, companiesRes] = await Promise.all([
        userAPI.getEmployers(),
        companyAPI.getAll(),
      ]);
      setEmployers(employersRes.data);
      setCompanies(companiesRes.data);
    } catch (error) {
      console.error('Error loading initial data:', error);
    }
  };

  const loadAnalytics = async () => {
    try {
      const params = {};
      if (filters.employer_id && filters.employer_id !== 'all') params.employer_id = filters.employer_id;
      if (filters.company_id && filters.company_id !== 'all') params.company_id = filters.company_id;
      if (filters.date_from) params.date_from = filters.date_from;
      if (filters.date_to) params.date_to = filters.date_to;
      
      const res = await analyticsAPI.getAdmin(params);
      setAnalytics(res.data);
    } catch (error) {
      toast.error('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value) => {
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
  const stageDistribution = analytics?.stage_distribution || {};
  const revenueFunnel = analytics?.revenue_funnel || {};
  const companyRevenue = analytics?.company_revenue || [];
  const recruiterPerformance = analytics?.recruiter_performance || [];

  return (
    <div className="space-y-6" data-testid="admin-analytics-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Business Analytics</h1>
          <p className="text-slate-500 mt-1">Revenue pipeline and performance insights</p>
        </div>
        
        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <div className="w-40">
            <Select
              value={filters.company_id}
              onValueChange={(v) => setFilters({ ...filters, company_id: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder="All Companies" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Companies</SelectItem>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-40">
            <Input
              type="date"
              value={filters.date_from}
              onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
              placeholder="From"
            />
          </div>
          <div className="w-40">
            <Input
              type="date"
              value={filters.date_to}
              onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
              placeholder="To"
            />
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Briefcase className="w-4 h-4 text-[#7CB342]" />
              <span className="text-xs text-slate-500">Active Mandates</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{kpis.total_active_mandates || 0}</p>
          </CardContent>
        </Card>
        
        <Card className="border-amber-200 bg-amber-50/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-4 h-4 text-amber-600" />
              <span className="text-xs text-amber-700">Pipeline Revenue</span>
            </div>
            <p className="text-2xl font-bold text-amber-700">{formatCurrency(kpis.total_pipeline_revenue || 0)}</p>
          </CardContent>
        </Card>
        
        <Card className="border-green-200 bg-green-50/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <DollarSign className="w-4 h-4 text-green-600" />
              <span className="text-xs text-green-700">Closed Revenue</span>
            </div>
            <p className="text-2xl font-bold text-green-700">{formatCurrency(kpis.closed_revenue || 0)}</p>
          </CardContent>
        </Card>
        
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-4 h-4 text-blue-600" />
              <span className="text-xs text-slate-500">Avg Time to Close</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{kpis.avg_time_to_close_days || 0} days</p>
          </CardContent>
        </Card>
        
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Target className="w-4 h-4 text-purple-600" />
              <span className="text-xs text-slate-500">Offer-to-Join</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{kpis.offer_to_join_ratio || 0}%</p>
          </CardContent>
        </Card>
        
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <UserCircle className="w-4 h-4 text-blue-600" />
              <span className="text-xs text-slate-500">Employers</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{kpis.active_employers || 0}</p>
          </CardContent>
        </Card>
        
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Users className="w-4 h-4 text-purple-600" />
              <span className="text-xs text-slate-500">Recruiters</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{kpis.active_recruiters || 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue Funnel */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-[#7CB342]" />
              Revenue Funnel by Stage
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <FunnelBar label="Offered" value={revenueFunnel.offered || 0} maxValue={Math.max(revenueFunnel.offered || 0, revenueFunnel.hired || 0) || 1} color="bg-amber-500" />
              <FunnelBar label="Hired (Closed)" value={revenueFunnel.hired || 0} maxValue={Math.max(revenueFunnel.offered || 0, revenueFunnel.hired || 0) || 1} color="bg-green-500" />
            </div>
          </CardContent>
        </Card>

        {/* Stage Distribution */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <PieChart className="w-5 h-5 text-[#7CB342]" />
              Application Stage Distribution
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(stageDistribution).map(([stage, count]) => (
                <div key={stage} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <span className="text-sm text-slate-600 capitalize">{stage.replace('_', ' ')}</span>
                  <Badge variant="secondary">{count}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tables Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Pipeline</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Closed</th>
                  </tr>
                </thead>
                <tbody>
                  {companyRevenue.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="text-center py-8 text-slate-400">No revenue data</td>
                    </tr>
                  ) : (
                    companyRevenue.map((company, idx) => (
                      <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-3 px-4 font-medium text-slate-900">{company.name || 'Unknown'}</td>
                        <td className="py-3 px-4 text-right text-amber-600">{formatCurrency(company.pipeline || 0)}</td>
                        <td className="py-3 px-4 text-right text-green-600">{formatCurrency(company.closed || 0)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Recruiter Performance */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <Users className="w-5 h-5 text-[#7CB342]" />
              Recruiter Performance
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <th className="text-left py-3 px-4 font-medium text-slate-600">Recruiter</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Apps</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Shortlisted</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Hired</th>
                    <th className="text-right py-3 px-4 font-medium text-slate-600">Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  {recruiterPerformance.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="text-center py-8 text-slate-400">No recruiter data</td>
                    </tr>
                  ) : (
                    recruiterPerformance.map((rec, idx) => (
                      <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-3 px-4 font-medium text-slate-900">{rec.name || 'Unknown'}</td>
                        <td className="py-3 px-4 text-right text-slate-600">{rec.applications || 0}</td>
                        <td className="py-3 px-4 text-right text-slate-600">{rec.shortlisted || 0}</td>
                        <td className="py-3 px-4 text-right text-green-600">{rec.hired || 0}</td>
                        <td className="py-3 px-4 text-right text-[#7CB342]">{formatCurrency(rec.revenue || 0)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// Funnel Bar Component
function FunnelBar({ label, value, maxValue, color }) {
  const percentage = maxValue > 0 ? (value / maxValue) * 100 : 0;
  
  const formatCurrency = (val) => {
    if (val >= 10000000) return `₹${(val / 10000000).toFixed(2)}Cr`;
    if (val >= 100000) return `₹${(val / 100000).toFixed(2)}L`;
    return `₹${val.toLocaleString('en-IN')}`;
  };
  
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="font-medium text-slate-900">{formatCurrency(value)}</span>
      </div>
      <div className="h-8 bg-slate-100 rounded-lg overflow-hidden">
        <div 
          className={`h-full ${color} transition-all duration-500`}
          style={{ width: `${Math.max(percentage, 5)}%` }}
        />
      </div>
    </div>
  );
}
