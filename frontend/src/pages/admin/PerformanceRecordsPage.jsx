import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../components/ui/select';
import { Loader2, Archive, Save, Trophy, IndianRupee, UserCheck, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import { performanceRecordsAPI } from '../../lib/api';

const fmtINR = (n) => (n || n === 0)
  ? `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
  : '—';

function StatBox({ label, value, hint, icon: Icon, testId }) {
  return (
    <Card data-testid={testId} className="border-slate-200">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
            <p className="text-2xl font-semibold text-slate-900 mt-1">{value}</p>
            {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
          </div>
          {Icon && <Icon className="w-5 h-5 text-[#7CB342]" />}
        </div>
      </CardContent>
    </Card>
  );
}

export default function PerformanceRecordsPage() {
  const [periodType, setPeriodType] = useState('month');
  const [period, setPeriod] = useState('');
  const [periods, setPeriods] = useState({ months: [], quarters: [], years: [] });
  const [report, setReport] = useState(null);
  const [archive, setArchive] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingSnap, setSavingSnap] = useState(false);
  const [openTeam, setOpenTeam] = useState(null);

  useEffect(() => {
    performanceRecordsAPI.periods().then(({ data }) => {
      setPeriods(data);
      setPeriod(data.months?.[0] || '');
    }).catch(() => {});
  }, []);

  const optionsFor = (type) => (
    type === 'month' ? periods.months : type === 'quarter' ? periods.quarters : periods.years
  ) || [];

  const load = useCallback(async () => {
    if (!period) return;
    setLoading(true);
    try {
      const [r, a] = await Promise.all([
        performanceRecordsAPI.report({ period_type: periodType, period }),
        performanceRecordsAPI.archive().catch(() => ({ data: { items: [] } })),
      ]);
      setReport(r.data);
      setArchive(a.data?.items || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load the record');
    } finally {
      setLoading(false);
    }
  }, [periodType, period]);

  useEffect(() => { load(); }, [load]);

  const changeType = (t) => {
    setPeriodType(t);
    setPeriod(optionsFor(t)[0] || '');
  };

  const saveSnapshot = async () => {
    setSavingSnap(true);
    try {
      await performanceRecordsAPI.snapshot({ period_type: periodType, period });
      toast.success(`${period} stored in the archive`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not store the snapshot');
    } finally {
      setSavingSnap(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="performance-records-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Performance Records</h1>
          <p className="text-sm text-slate-500">
            Monthly, quarterly and annual record of every recruiter and employer — joinings, revenue and
            target achievement. Closed periods are archived automatically.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Basis</Label>
            <Select value={periodType} onValueChange={changeType}>
              <SelectTrigger className="w-32" data-testid="record-basis"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="month">Monthly</SelectItem>
                <SelectItem value="quarter">Quarterly</SelectItem>
                <SelectItem value="year">Annual</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Period</Label>
            <Select value={period} onValueChange={setPeriod}>
              <SelectTrigger className="w-36" data-testid="record-period"><SelectValue /></SelectTrigger>
              <SelectContent className="max-h-72">
                {optionsFor(periodType).map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button variant="outline" onClick={saveSnapshot} disabled={savingSnap || !period}
                  data-testid="record-snapshot-btn">
            {savingSnap ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
            Store record
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : !report ? (
        <p className="text-sm text-slate-500">Pick a period to see the record.</p>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatBox testId="record-stat-revenue" label="Revenue in period" value={fmtINR(report.total_revenue)}
                     icon={IndianRupee} hint={`${report.range?.from} → ${report.range?.to}`} />
            <StatBox testId="record-stat-joinings" label="Joinings" value={report.total_joinings}
                     icon={UserCheck} hint={`${report.teams?.length || 0} teams`} />
            <StatBox testId="record-stat-target" label="Annual target (all teams)"
                     value={fmtINR(report.total_annual_target)} icon={Trophy}
                     hint="Context for the period share" />
            <StatBox testId="record-stat-status" label="Status"
                     value={report.source === 'archive' ? 'Archived' : 'Live'}
                     icon={Archive}
                     hint={report.closed ? 'Period closed' : 'Period still running'} />
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Teams &amp; contributors</CardTitle>
            </CardHeader>
            <CardContent>
              {(report.teams || []).length === 0 ? (
                <p className="py-8 text-center text-sm text-slate-500">No teams recorded.</p>
              ) : (
                <div className="space-y-2" data-testid="record-teams">
                  {report.teams.map((t) => (
                    <div key={t.team_id} className="border rounded-lg">
                      <button
                        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
                        onClick={() => setOpenTeam(openTeam === t.team_id ? null : t.team_id)}
                        data-testid={`record-team-${t.team_id}`}
                      >
                        <div>
                          <p className="font-medium text-slate-900">{t.team_name}</p>
                          <p className="text-xs text-slate-500">
                            Employer: {t.employer_name || '—'} · {t.members.length} members
                          </p>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="text-right">
                            <p className="text-sm font-semibold">{fmtINR(t.revenue)}</p>
                            <p className="text-xs text-slate-500">{t.joinings} joinings</p>
                          </div>
                          <ChevronRight className={`w-4 h-4 text-slate-400 transition-transform ${openTeam === t.team_id ? 'rotate-90' : ''}`} />
                        </div>
                      </button>
                      {openTeam === t.team_id && (
                        <div className="border-t bg-slate-50/60 px-4 py-3 overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="text-xs uppercase tracking-wide text-slate-500">
                                <th className="text-left py-1">Recruiter</th>
                                <th className="text-left py-1">Joinings</th>
                                <th className="text-left py-1">Revenue</th>
                                <th className="text-left py-1">Annual target</th>
                                <th className="text-left py-1">Share of target</th>
                              </tr>
                            </thead>
                            <tbody>
                              {t.members.map((m) => (
                                <tr key={m.user_id} className="border-t border-slate-200">
                                  <td className="py-1.5">{m.name || m.user_id}</td>
                                  <td className="py-1.5">{m.joinings}</td>
                                  <td className="py-1.5">{fmtINR(m.revenue)}</td>
                                  <td className="py-1.5">{fmtINR(m.annual_target)}</td>
                                  <td className="py-1.5">
                                    <Badge variant="outline">{m.share_of_annual_target_pct}%</Badge>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {t.members.some((m) => (m.candidates || []).length > 0) && (
                            <div className="mt-3">
                              <p className="text-xs uppercase tracking-wide text-slate-500 mb-1">Joinings</p>
                              <ul className="text-xs text-slate-600 space-y-1">
                                {t.members.flatMap((m) => (m.candidates || []).map((c, i) => (
                                  <li key={`${m.user_id}-${i}`}>
                                    {c.join_date} · {c.candidate_name} → {c.client_name} ({c.position})
                                    {c.revenue ? ` · ${fmtINR(c.revenue)}` : ' · revenue pending'}
                                    {c.bill_number ? ` · ${c.bill_number}` : ''}
                                  </li>
                                )))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Archive ({archive.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {archive.length === 0 ? (
                <p className="py-6 text-center text-sm text-slate-500" data-testid="record-archive-empty">
                  Nothing archived yet — records are stored automatically once a period ends.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="record-archive-table">
                    <thead>
                      <tr className="border-b text-xs uppercase tracking-wide text-slate-500">
                        <th className="text-left px-3 py-2">Period</th>
                        <th className="text-left px-3 py-2">Basis</th>
                        <th className="text-left px-3 py-2">Revenue</th>
                        <th className="text-left px-3 py-2">Joinings</th>
                        <th className="text-left px-3 py-2">Stored</th>
                        <th className="text-right px-3 py-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {archive.map((a) => (
                        <tr key={a.id} className="border-b last:border-0">
                          <td className="px-3 py-2 font-medium">{a.period}</td>
                          <td className="px-3 py-2 capitalize">{a.period_type}</td>
                          <td className="px-3 py-2">{fmtINR(a.total_revenue)}</td>
                          <td className="px-3 py-2">{a.total_joinings}</td>
                          <td className="px-3 py-2 text-slate-500">
                            {(a.archived_at || '').slice(0, 10)} · {a.archived_by}
                          </td>
                          <td className="px-3 py-2 text-right">
                            <Button size="sm" variant="ghost"
                                    onClick={() => { setPeriodType(a.period_type); setPeriod(a.period); }}
                                    data-testid={`record-open-${a.id}`}>
                              Open
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
