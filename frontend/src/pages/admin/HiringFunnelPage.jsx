import { useState, useEffect } from 'react';
import { adminAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { BarChart3, Clock, TrendingUp, Users, Briefcase, ArrowRight } from 'lucide-react';

const STAGE_LABELS = {
  sourced: 'Sourced', applied: 'Applied', shortlisted: 'Shortlisted',
  submitted_to_client: 'Submitted', interview: 'Interview',
  offered: 'Offered', hired: 'Hired', joined: 'Joined',
};

const STAGE_COLORS = {
  sourced: 'bg-slate-400', applied: 'bg-blue-400', shortlisted: 'bg-cyan-400',
  submitted_to_client: 'bg-indigo-400', interview: 'bg-violet-400',
  offered: 'bg-amber-400', hired: 'bg-emerald-400', joined: 'bg-green-500',
};

export default function HiringFunnelPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState('30');

  useEffect(() => {
    setLoading(true);
    adminAPI.getHiringFunnel({ days: parseInt(days) })
      .then(res => setData(res.data))
      .catch(() => toast.error('Failed to load funnel data'))
      .finally(() => setLoading(false));
  }, [days]);

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="spinner" /></div>;
  }

  if (!data) return <p className="text-slate-400 text-center py-12">No data available</p>;

  const maxCount = Math.max(...data.funnel.map(s => s.count), 1);

  return (
    <div className="space-y-6" data-testid="hiring-funnel-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Hiring Funnel</h1>
          <p className="text-slate-500 mt-1">Pipeline velocity, conversion rates & time-to-hire</p>
        </div>
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger className="w-40" data-testid="period-select">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Last 7 days</SelectItem>
            <SelectItem value="30">Last 30 days</SelectItem>
            <SelectItem value="90">Last 90 days</SelectItem>
            <SelectItem value="180">Last 6 months</SelectItem>
            <SelectItem value="365">Last year</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                <Users className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{data.total_applications}</p>
                <p className="text-xs text-slate-500">Total Applications</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-50 flex items-center justify-center">
                <Briefcase className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{data.active_jobs}</p>
                <p className="text-xs text-slate-500">Active Jobs</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
                <Clock className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{data.avg_time_to_hire_days ?? '—'}</p>
                <p className="text-xs text-slate-500">Avg Days to Hire</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-emerald-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">
                  {data.funnel.find(s => s.stage === 'hired')?.count || 0}
                </p>
                <p className="text-xs text-slate-500">Total Hired</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Funnel Visualization */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-[#7CB342]" /> Pipeline Funnel
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {data.funnel.map((stage, i) => (
              <div key={stage.stage} className="flex items-center gap-3" data-testid={`funnel-stage-${stage.stage}`}>
                <span className="text-sm text-slate-600 w-28 text-right shrink-0">
                  {STAGE_LABELS[stage.stage] || stage.stage}
                </span>
                <div className="flex-1 bg-slate-100 rounded-full h-8 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${STAGE_COLORS[stage.stage] || 'bg-slate-400'} flex items-center px-3 transition-all duration-500`}
                    style={{ width: `${Math.max((stage.count / maxCount) * 100, stage.count > 0 ? 8 : 0)}%` }}
                  >
                    <span className="text-white text-xs font-bold">{stage.count}</span>
                  </div>
                </div>
                {data.conversions[i] && (
                  <span className="text-xs text-slate-400 w-16 shrink-0 flex items-center gap-1">
                    <ArrowRight className="w-3 h-3" /> {data.conversions[i].rate}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Conversion Rates */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading text-lg">Stage Conversions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {data.conversions.map((c) => (
                <div key={`${c.from}-${c.to}`} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                  <span className="text-sm text-slate-600">
                    {STAGE_LABELS[c.from] || c.from} <ArrowRight className="w-3 h-3 inline mx-1" /> {STAGE_LABELS[c.to] || c.to}
                  </span>
                  <span className={`text-sm font-bold ${c.rate > 50 ? 'text-green-600' : c.rate > 20 ? 'text-amber-600' : 'text-red-500'}`}>
                    {c.rate}%
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Source Effectiveness */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading text-lg">Source Effectiveness</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {data.source_effectiveness.map((s) => (
                <div key={s.source} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                  <div>
                    <span className="text-sm font-medium text-slate-700">{s.source}</span>
                    <span className="text-xs text-slate-400 ml-2">{s.total} candidates</span>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-bold text-green-600">{s.hired} hired</span>
                    <span className="text-xs text-slate-400 ml-2">({s.conversion_rate}%)</span>
                  </div>
                </div>
              ))}
              {data.source_effectiveness.length === 0 && (
                <p className="text-slate-400 text-sm text-center py-4">No source data</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Rejections */}
      {Object.keys(data.rejections).length > 0 && (
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="font-heading text-lg">Rejections & Drops</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {Object.entries(data.rejections).map(([stage, count]) => (
                <div key={stage} className="px-4 py-2 bg-red-50 rounded-lg border border-red-100">
                  <p className="text-lg font-bold text-red-600">{count}</p>
                  <p className="text-xs text-red-400">{STAGE_LABELS[stage] || stage}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
