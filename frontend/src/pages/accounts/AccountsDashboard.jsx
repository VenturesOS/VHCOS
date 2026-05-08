import { useState, useEffect, useCallback } from 'react';
import { financeAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { IndianRupee, FileText, Users, TrendingUp, TrendingDown, AlertCircle, Clock, ArrowUpRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const fmt = (n) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n || 0);

export default function AccountsDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const res = await financeAPI.revenueDashboard('current_year');
      setData(res.data);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="animate-spin w-8 h-8 border-2 border-slate-300 border-t-blue-600 rounded-full" /></div>;

  const d = data || {};

  return (
    <div className="space-y-6 p-4 sm:p-6" data-testid="accounts-dashboard">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Accounts Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Financial overview and key metrics</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-slate-200 cursor-pointer hover:shadow-md transition-shadow" onClick={() => navigate('/accounts/revenue')} data-testid="kpi-revenue">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Total Revenue</p>
                <p className="text-2xl font-bold text-slate-900 mt-1">{fmt(d.total_revenue)}</p>
                <p className="text-xs text-slate-400 mt-1">{d.revenue_count || 0} paid invoices</p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-green-50 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200 cursor-pointer hover:shadow-md transition-shadow" onClick={() => navigate('/accounts/invoices')} data-testid="kpi-outstanding">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Outstanding</p>
                <p className="text-2xl font-bold text-amber-600 mt-1">{fmt(d.outstanding)}</p>
                <p className="text-xs text-slate-400 mt-1">{d.outstanding_count || 0} invoices pending</p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
                <Clock className="w-5 h-5 text-amber-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200 cursor-pointer hover:shadow-md transition-shadow" onClick={() => navigate('/accounts/expenses')} data-testid="kpi-expenses">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Expenses</p>
                <p className="text-2xl font-bold text-red-600 mt-1">{fmt(d.total_expenses)}</p>
                <p className="text-xs text-slate-400 mt-1">{d.expense_count || 0} entries</p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center">
                <TrendingDown className="w-5 h-5 text-red-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200" data-testid="kpi-profit">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Net Profit</p>
                <p className={`text-2xl font-bold mt-1 ${(d.net_profit || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>{fmt(d.net_profit)}</p>
                <p className="text-xs text-slate-400 mt-1">Current year</p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                <IndianRupee className="w-5 h-5 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Overdue Alert */}
      {d.overdue > 0 && (
        <Card className="border-red-200 bg-red-50/50" data-testid="overdue-alert">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 shrink-0" />
            <div>
              <p className="text-sm font-medium text-red-700">{d.overdue_count} overdue invoice(s) totaling {fmt(d.overdue)}</p>
              <p className="text-xs text-red-500 mt-0.5">Follow up with clients to collect payments</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Monthly Trend */}
        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold text-slate-700">Monthly Revenue Trend</CardTitle>
          </CardHeader>
          <CardContent>
            {(d.monthly_trend || []).length > 0 ? (
              <div className="space-y-2">
                {d.monthly_trend.map((m) => {
                  const max = Math.max(...d.monthly_trend.map(x => x.revenue));
                  const pct = max > 0 ? (m.revenue / max) * 100 : 0;
                  return (
                    <div key={m.month} className="flex items-center gap-3">
                      <span className="text-xs text-slate-500 w-16 shrink-0">{m.month}</span>
                      <div className="flex-1 h-6 bg-slate-100 rounded overflow-hidden">
                        <div className="h-full bg-green-500 rounded transition-all" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs font-medium text-slate-700 w-24 text-right">{fmt(m.revenue)}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-400 py-8 text-center">No revenue data yet</p>
            )}
          </CardContent>
        </Card>

        {/* Top Clients */}
        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold text-slate-700">Top Clients by Revenue</CardTitle>
          </CardHeader>
          <CardContent>
            {(d.top_clients || []).length > 0 ? (
              <div className="space-y-3">
                {d.top_clients.map((c, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center text-xs font-bold text-blue-600">{i + 1}</div>
                      <div>
                        <p className="text-sm font-medium text-slate-800">{c.name}</p>
                        <p className="text-xs text-slate-400">{c.invoices} invoices</p>
                      </div>
                    </div>
                    <span className="text-sm font-semibold text-slate-700">{fmt(c.revenue)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400 py-8 text-center">No client data yet</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card className="border-slate-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold text-slate-700">Quick Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'New Invoice', path: '/accounts/invoices', icon: FileText, color: 'bg-blue-50 text-blue-600' },
              { label: 'Add Client', path: '/accounts/clients', icon: Users, color: 'bg-green-50 text-green-600' },
              { label: 'Log Expense', path: '/accounts/expenses', icon: IndianRupee, color: 'bg-red-50 text-red-600' },
              { label: 'View Reports', path: '/accounts/reports', icon: ArrowUpRight, color: 'bg-purple-50 text-purple-600' },
            ].map((a) => (
              <button key={a.label} onClick={() => navigate(a.path)}
                className="flex items-center gap-2 p-3 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors text-left"
                data-testid={`quick-${a.label.toLowerCase().replace(/\s/g, '-')}`}>
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${a.color}`}>
                  <a.icon className="w-4 h-4" />
                </div>
                <span className="text-sm font-medium text-slate-700">{a.label}</span>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
