import { useState, useEffect, useCallback } from 'react';
import { revenueAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import {
  IndianRupee, TrendingUp, Building2, Briefcase, Users,
  Calendar, Loader2, BarChart3, Lock, Clock, FileCheck
} from 'lucide-react';

const fmt = (n) => n != null ? `₹${Math.round(n).toLocaleString('en-IN')}` : '—';
const fmtLakh = (n) => n != null ? `₹${(n / 100000).toFixed(1)}L` : '—';

function getDefaultDates() {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth() - 2, 1).toISOString().split('T')[0];
  const to = now.toISOString().split('T')[0];
  return { from, to };
}

export default function RevenueDashboardPage() {
  const defaults = getDefaultDates();
  const [fromDate, setFromDate] = useState(defaults.from);
  const [toDate, setToDate] = useState(defaults.to);
  const [records, setRecords] = useState([]);
  const [byCompany, setByCompany] = useState([]);
  const [byJob, setByJob] = useState([]);
  const [byRecruiter, setByRecruiter] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, coRes, jobRes, recrtRes] = await Promise.all([
        revenueAPI.records({ status: statusFilter !== 'all' ? statusFilter : undefined }),
        revenueAPI.aggregateByCompany(fromDate, toDate),
        revenueAPI.aggregateByJob(fromDate, toDate),
        revenueAPI.aggregateByRecruiter(fromDate, toDate),
      ]);
      setRecords(recRes.data.records || []);
      setByCompany(coRes.data.data || []);
      setByJob(jobRes.data.data || []);
      setByRecruiter(recrtRes.data.data || []);
    } catch {
      toast.error('Failed to load revenue data');
    } finally {
      setLoading(false);
    }
  }, [fromDate, toDate, statusFilter]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const totalRevenue = byCompany.reduce((s, c) => s + (c.total_revenue || 0), 0);
  const totalJoined = byCompany.reduce((s, c) => s + (c.count || 0), 0);
  const offeredCount = records.filter(r => r.revenue_status === 'offered').length;
  const joinedCount = records.filter(r => r.revenue_status === 'joined').length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="revenue-loading">
        <Loader2 className="w-6 h-6 animate-spin text-teal-600" />
        <span className="ml-2 text-gray-500">Loading revenue data...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="revenue-dashboard-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Revenue Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Financial overview — joined revenue by date range</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5">
            <Calendar className="w-4 h-4 text-gray-400" />
            <Input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36 h-9 text-sm" data-testid="revenue-from-date" />
            <span className="text-gray-400 text-sm">to</span>
            <Input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-36 h-9 text-sm" data-testid="revenue-to-date" />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-32 h-9" data-testid="revenue-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="offered">Offered</SelectItem>
              <SelectItem value="joined">Joined</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card data-testid="kpi-total-revenue">
          <CardContent className="pt-5 pb-4 px-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Joined Revenue</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{fmt(totalRevenue)}</p>
                <p className="text-xs text-gray-400 mt-1">{fromDate} — {toDate}</p>
              </div>
              <div className="p-2 rounded-lg bg-teal-50 text-teal-700"><IndianRupee className="w-5 h-5" /></div>
            </div>
          </CardContent>
        </Card>
        <Card data-testid="kpi-joined-count">
          <CardContent className="pt-5 pb-4 px-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Joined</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{totalJoined}</p>
                <p className="text-xs text-gray-400 mt-1">candidates in range</p>
              </div>
              <div className="p-2 rounded-lg bg-green-50 text-green-700"><Lock className="w-5 h-5" /></div>
            </div>
          </CardContent>
        </Card>
        <Card data-testid="kpi-offered-count">
          <CardContent className="pt-5 pb-4 px-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Offered</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{offeredCount}</p>
                <p className="text-xs text-gray-400 mt-1">pending join</p>
              </div>
              <div className="p-2 rounded-lg bg-amber-50 text-amber-700"><Clock className="w-5 h-5" /></div>
            </div>
          </CardContent>
        </Card>
        <Card data-testid="kpi-total-records">
          <CardContent className="pt-5 pb-4 px-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Total Records</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{records.length}</p>
                <p className="text-xs text-gray-400 mt-1">all revenue entries</p>
              </div>
              <div className="p-2 rounded-lg bg-gray-50 text-gray-500"><FileCheck className="w-5 h-5" /></div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Aggregation Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* By Company */}
        <Card data-testid="revenue-by-company">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Building2 className="w-4 h-4 text-teal-600" /> By Company</CardTitle>
          </CardHeader>
          <CardContent>
            {byCompany.length === 0 ? <p className="text-sm text-gray-400 py-4 text-center">No data in range</p> : (
              <div className="space-y-2">
                {byCompany.map((c, i) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                    <div>
                      <p className="text-sm font-medium text-gray-800">{c.company_name || 'Unknown'}</p>
                      <p className="text-xs text-gray-400">{c.count} joined · Avg CTC {fmtLakh(c.avg_ctc)}</p>
                    </div>
                    <p className="text-sm font-semibold text-teal-700">{fmt(c.total_revenue)}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* By Job */}
        <Card data-testid="revenue-by-job">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Briefcase className="w-4 h-4 text-teal-600" /> By Job</CardTitle>
          </CardHeader>
          <CardContent>
            {byJob.length === 0 ? <p className="text-sm text-gray-400 py-4 text-center">No data in range</p> : (
              <div className="space-y-2">
                {byJob.map((j, i) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                    <div>
                      <p className="text-sm font-medium text-gray-800 truncate max-w-[180px]">{j.job_title || 'Unknown'}</p>
                      <p className="text-xs text-gray-400">{j.company_name} · {j.count} joined</p>
                    </div>
                    <p className="text-sm font-semibold text-teal-700">{fmt(j.total_revenue)}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* By Recruiter */}
        <Card data-testid="revenue-by-recruiter">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Users className="w-4 h-4 text-teal-600" /> By Recruiter</CardTitle>
          </CardHeader>
          <CardContent>
            {byRecruiter.length === 0 ? <p className="text-sm text-gray-400 py-4 text-center">No data in range</p> : (
              <div className="space-y-2">
                {byRecruiter.map((r, i) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                    <div>
                      <p className="text-sm font-medium text-gray-800">{r.recruiter_name}</p>
                      <p className="text-xs text-gray-400">{r.count} joined · Avg CTC {fmtLakh(r.avg_ctc)}</p>
                    </div>
                    <p className="text-sm font-semibold text-teal-700">{fmt(r.total_revenue)}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Revenue Records Table */}
      <Card data-testid="revenue-records-table">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2"><BarChart3 className="w-4 h-4 text-teal-600" /> Revenue Records</CardTitle>
        </CardHeader>
        <CardContent>
          {records.length === 0 ? (
            <p className="text-sm text-gray-400 py-8 text-center">No revenue records yet. Process candidates through offered → joined stages.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500 text-xs uppercase tracking-wider">
                    <th className="py-2 pr-3">Candidate</th>
                    <th className="py-2 pr-3">Company</th>
                    <th className="py-2 pr-3">Offered CTC</th>
                    <th className="py-2 pr-3">Revenue</th>
                    <th className="py-2 pr-3">Type</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2">Dates</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {records.map((r, i) => (
                    <tr key={i} className="hover:bg-gray-50" data-testid={`revenue-row-${i}`}>
                      <td className="py-2.5 pr-3">
                        <p className="font-medium text-gray-800 truncate max-w-[140px]">{r.candidate_name || '—'}</p>
                        <p className="text-xs text-gray-400 truncate max-w-[140px]">{r.job_title || ''}</p>
                      </td>
                      <td className="py-2.5 pr-3 text-gray-600 truncate max-w-[120px]">{r.company_name || '—'}</td>
                      <td className="py-2.5 pr-3 text-gray-800 font-medium">{fmtLakh(r.offered_ctc)}</td>
                      <td className="py-2.5 pr-3 font-semibold text-teal-700">{fmt(r.final_revenue)}</td>
                      <td className="py-2.5 pr-3">
                        <Badge variant="outline" className="text-xs capitalize">
                          {r.commercial_snapshot?.type || '—'}
                          {r.percentage_used ? ` ${r.percentage_used}%` : ''}
                        </Badge>
                      </td>
                      <td className="py-2.5 pr-3">
                        <Badge className={r.revenue_status === 'joined'
                          ? 'bg-green-50 text-green-700 border-green-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200'}>
                          {r.revenue_status === 'joined' && <Lock className="w-3 h-3 mr-1" />}
                          {r.revenue_status}
                        </Badge>
                      </td>
                      <td className="py-2.5 text-xs text-gray-400">
                        {r.offer_date && <div>Offer: {r.offer_date}</div>}
                        {r.join_date && <div>Join: {r.join_date}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
