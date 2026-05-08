import { useState, useEffect, useCallback } from 'react';
import { financeAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Badge } from '../../components/ui/badge';
import { TrendingUp, IndianRupee, Loader2, Clock } from 'lucide-react';

const fmt = (n) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n || 0);

export default function RevenueDashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('current_year');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await financeAPI.revenueDashboard(period);
      setData(res.data);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-slate-400" /></div>;

  const d = data || {};

  return (
    <div className="space-y-6 p-4 sm:p-6" data-testid="revenue-dashboard">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Revenue Dashboard</h1>
          <p className="text-sm text-slate-500">Track collections, outstanding, and revenue trends</p>
        </div>
        <Select value={period} onValueChange={setPeriod}>
          <SelectTrigger className="w-40 h-9" data-testid="period-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="current_month">This Month</SelectItem>
            <SelectItem value="last_3_months">Last 3 Months</SelectItem>
            <SelectItem value="last_6_months">Last 6 Months</SelectItem>
            <SelectItem value="current_year">This Year</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-green-200 bg-green-50/30" data-testid="kpi-collected">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-green-700 uppercase">Collected</p>
            <p className="text-2xl font-bold text-green-700 mt-1">{fmt(d.total_revenue)}</p>
            <p className="text-xs text-green-600 mt-1">{d.revenue_count || 0} invoices paid</p>
          </CardContent>
        </Card>
        <Card className="border-amber-200 bg-amber-50/30" data-testid="kpi-outstanding">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-amber-700 uppercase">Outstanding</p>
            <p className="text-2xl font-bold text-amber-700 mt-1">{fmt(d.outstanding)}</p>
            <p className="text-xs text-amber-600 mt-1">{d.outstanding_count || 0} pending</p>
          </CardContent>
        </Card>
        <Card className="border-red-200 bg-red-50/30" data-testid="kpi-overdue">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-red-700 uppercase">Overdue</p>
            <p className="text-2xl font-bold text-red-700 mt-1">{fmt(d.overdue)}</p>
            <p className="text-xs text-red-600 mt-1">{d.overdue_count || 0} invoices</p>
          </CardContent>
        </Card>
        <Card className="border-blue-200 bg-blue-50/30" data-testid="kpi-net">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-blue-700 uppercase">Net Profit</p>
            <p className={`text-2xl font-bold mt-1 ${(d.net_profit || 0) >= 0 ? 'text-blue-700' : 'text-red-700'}`}>{fmt(d.net_profit)}</p>
            <p className="text-xs text-blue-600 mt-1">After expenses</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Monthly Revenue Bars */}
        <Card className="border-slate-200">
          <CardHeader className="pb-2"><CardTitle className="text-base">Monthly Revenue</CardTitle></CardHeader>
          <CardContent>
            {(d.monthly_trend || []).length > 0 ? (
              <div className="space-y-3">
                {d.monthly_trend.map((m) => {
                  const max = Math.max(...d.monthly_trend.map(x => x.revenue), 1);
                  const pct = (m.revenue / max) * 100;
                  return (
                    <div key={m.month} className="flex items-center gap-3">
                      <span className="text-xs text-slate-500 w-20 shrink-0">{m.month}</span>
                      <div className="flex-1 h-8 bg-slate-100 rounded-lg overflow-hidden relative">
                        <div className="h-full bg-gradient-to-r from-green-500 to-green-400 rounded-lg transition-all" style={{ width: `${pct}%` }} />
                        <span className="absolute inset-y-0 right-2 flex items-center text-xs font-medium text-slate-600">{fmt(m.revenue)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : <p className="text-sm text-slate-400 py-8 text-center">No revenue data for this period</p>}
          </CardContent>
        </Card>

        {/* Top Clients */}
        <Card className="border-slate-200">
          <CardHeader className="pb-2"><CardTitle className="text-base">Top Clients</CardTitle></CardHeader>
          <CardContent>
            {(d.top_clients || []).length > 0 ? (
              <div className="space-y-4">
                {d.top_clients.map((c, i) => {
                  const max = d.top_clients[0]?.revenue || 1;
                  const pct = (c.revenue / max) * 100;
                  return (
                    <div key={i}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-slate-700">{c.name}</span>
                        <span className="text-sm text-slate-600">{fmt(c.revenue)}</span>
                      </div>
                      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : <p className="text-sm text-slate-400 py-8 text-center">No client data</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
