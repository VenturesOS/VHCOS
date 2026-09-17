// Employee Performance & KPI Analytics
// Spec Section 4 (2026-09-08) — replaces the previous system/generic
// analytics overview with a recruitment-performance workspace.
// Data source: GET /api/analytics/employee-performance & /leaderboard.
// KPI point rules match Daily Digest exactly (PIPELINE_POINTS).
import { useEffect, useMemo, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Loader2, TrendingUp, Users, CheckCircle2, Award, Target, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import api, { blogAPI, userAPI } from '../../lib/api';

const KPI_TILES = [
  { key: 'sourced',              label: 'Sourced',             icon: Users,        color: 'text-slate-600' },
  { key: 'submitted',            label: 'Profiles Submitted',  icon: TrendingUp,   color: 'text-blue-600' },
  { key: 'interview_scheduled',  label: 'Interview Scheduled', icon: Target,       color: 'text-cyan-600' },
  { key: 'interview_completed',  label: 'Interview Completed', icon: Target,       color: 'text-teal-600' },
  { key: 'offered',              label: 'Offers',              icon: Award,        color: 'text-amber-600' },
  { key: 'hired',                label: 'Hired',               icon: CheckCircle2, color: 'text-emerald-600' },
  { key: 'joined',               label: 'Joined',              icon: CheckCircle2, color: 'text-green-700' },
  { key: 'active_pipeline',      label: 'Active Pipeline',     icon: Users,        color: 'text-purple-600' },
];

function todayISO() { return new Date().toISOString().slice(0, 10); }
function monthStartISO() {
  const d = new Date(); d.setDate(1);
  return d.toISOString().slice(0, 10);
}

export default function AdminAnalyticsPage() {
  const [dateFrom, setDateFrom] = useState(monthStartISO());
  const [dateTo, setDateTo] = useState(todayISO());
  const [teamId, setTeamId] = useState('_all');
  const [employeeId, setEmployeeId] = useState('_all');
  const [teams, setTeams] = useState([]);
  const [people, setPeople] = useState([]);
  const [data, setData] = useState(null);
  const [annualData, setAnnualData] = useState(null);
  const [loading, setLoading] = useState(false);
  // Bumped on every Apply so the Joinings list re-reads with the same
  // date / team / employee scope as the KPI cards (fix.docx: "when we
  // filter out people the joining list should be filtered accordingly").
  const [appliedScope, setAppliedScope] = useState({
    dateFrom: monthStartISO(), dateTo: todayISO(), teamId: '_all', employeeId: '_all',
  });

  useEffect(() => {
    api.get('/teams').then(r => setTeams(r.data || [])).catch(() => {});
    userAPI.getAll().then(r => setPeople(r.data || [])).catch(() => {});
  }, []);

  const load = async () => {
    setLoading(true);
    setAppliedScope({ dateFrom, dateTo, teamId, employeeId });
    try {
      const params = { date_from: `${dateFrom}T00:00:00+00:00`, date_to: `${dateTo}T23:59:59+00:00` };
      if (teamId !== '_all') params.team_id = teamId;
      if (employeeId !== '_all') params.employee_id = employeeId;
      const [pRes, lRes] = await Promise.all([
        api.get('/analytics/employee-performance', { params }),
        api.get('/analytics/leaderboard', { params: teamId !== '_all' ? { team_id: teamId } : {} }),
      ]);
      setData(pRes.data);
      setAnnualData(lRes.data);
    } catch (e) {
      toast.error(e?.response?.data?.error || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const kpi = data?.kpi_summary || {};
  const conv = data?.conversion_summary || {};
  const employees = data?.employees || [];
  const annualTop = (annualData?.employees || []).slice(0, 20);

  const teamsForFilter = useMemo(() => teams.filter(t => t.status !== 'deleted'), [teams]);
  const peopleForFilter = useMemo(() => {
    const roster = (people || []).filter(u => u.is_active !== false);
    const scoped = appliedScope.teamId !== '_all' || teamId !== '_all'
      ? roster.filter(u => {
          const t = teamsForFilter.find(x => x.id === teamId);
          if (!t) return true;
          return (t.recruiter_ids || []).includes(u.id) || t.team_lead_id === u.id;
        })
      : roster;
    return scoped.sort((a, b) => (a.name || a.email || '').localeCompare(b.name || b.email || ''));
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [people, teamId, teamsForFilter]);

  return (
    <div className="space-y-6 p-4 sm:p-6" data-testid="admin-analytics-page">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Employee Performance</h1>
        <p className="text-sm text-slate-500 mt-1">
          Recruitment KPIs, conversion, and annual leaderboard. Points use the Daily Digest table.
        </p>
      </div>

      {/* Filter bar */}
      <Card className="border-slate-200">
        <CardContent className="p-4 grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">From</Label>
            <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} data-testid="filter-from" />
          </div>
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">To</Label>
            <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} data-testid="filter-to" />
          </div>
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Team</Label>
            <Select value={teamId} onValueChange={setTeamId}>
              <SelectTrigger data-testid="filter-team"><SelectValue placeholder="All teams" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_all">All teams</SelectItem>
                {teamsForFilter.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Employee</Label>
            <Select value={employeeId} onValueChange={setEmployeeId}>
              <SelectTrigger data-testid="filter-employee"><SelectValue placeholder="All employees" /></SelectTrigger>
              <SelectContent className="max-h-72">
                <SelectItem value="_all">All employees</SelectItem>
                {peopleForFilter.map(u => (
                  <SelectItem key={u.id} value={u.id}>{u.name || u.email}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={load} disabled={loading} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="apply-btn">
            {loading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1.5" />} Apply
          </Button>
        </CardContent>
      </Card>

      {/* KPI Summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="kpi-summary">
        {KPI_TILES.map(({ key, label, icon: Icon, color }) => (
          <Card key={key} className="border-slate-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs text-slate-500">{label}</div>
                  <div className={`text-2xl font-bold ${color} mt-1`}>{(kpi[key] ?? 0).toLocaleString()}</div>
                </div>
                <Icon className={`w-5 h-5 ${color} opacity-60`} />
              </div>
            </CardContent>
          </Card>
        ))}
        <Card className="border-emerald-300 bg-emerald-50 col-span-2 md:col-span-4">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <div className="text-xs text-emerald-800">Total KPI Points (Daily Digest scoring)</div>
              <div className="text-3xl font-bold text-emerald-700 mt-1">
                {(kpi.total_points ?? 0).toLocaleString()}
              </div>
            </div>
            <Award className="w-8 h-8 text-emerald-600" />
          </CardContent>
        </Card>
      </div>

      {/* Conversion funnel */}
      <Card className="border-slate-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Conversion — Submitted → Interview → Offer → Joining</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            ['Submitted → Interview',  conv.submitted_to_interview_pct],
            ['Interview → Offer',      conv.interview_to_offer_pct],
            ['Offer → Joining',        conv.offer_to_joining_pct],
            ['Submitted → Joining',    conv.submitted_to_joining_pct],
          ].map(([label, pct]) => (
            <div key={label} className="p-3 rounded-lg bg-slate-50">
              <div className="text-xs text-slate-500">{label}</div>
              <div className="text-2xl font-bold text-slate-900 mt-1">{(pct ?? 0)}%</div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Team Comparison / Employees table */}
      <Card className="border-slate-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Team Comparison ({employees.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0 overflow-auto">
          <table className="w-full text-sm" data-testid="team-comparison-table">
            <thead className="bg-slate-50 text-slate-600 text-xs">
              <tr>
                <th className="text-left px-3 py-2">#</th>
                <th className="text-left px-3 py-2">Employee</th>
                <th className="text-left px-3 py-2">Team</th>
                <th className="text-right px-3 py-2">Points</th>
                <th className="text-right px-3 py-2">Submitted</th>
                <th className="text-right px-3 py-2">Int. Sched.</th>
                <th className="text-right px-3 py-2">Int. Done</th>
                <th className="text-right px-3 py-2">Offered</th>
                <th className="text-right px-3 py-2">Joined</th>
                <th className="text-right px-3 py-2">Sub→Join %</th>
              </tr>
            </thead>
            <tbody>
              {employees.map(e => (
                <tr key={e.recruiter_id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-500">{e.rank}</td>
                  <td className="px-3 py-2 font-medium text-slate-900">{e.recruiter_name}</td>
                  <td className="px-3 py-2 text-slate-600">{e.team_name || '—'}</td>
                  <td className="px-3 py-2 text-right font-semibold text-emerald-700">{e.points.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right">{e.submitted}</td>
                  <td className="px-3 py-2 text-right">{e.interview_scheduled}</td>
                  <td className="px-3 py-2 text-right">{e.interview_completed}</td>
                  <td className="px-3 py-2 text-right">{e.offered}</td>
                  <td className="px-3 py-2 text-right font-semibold">{e.joined}</td>
                  <td className="px-3 py-2 text-right">{e.sub_to_joining_pct}%</td>
                </tr>
              ))}
              {employees.length === 0 && !loading && (
                <tr><td colSpan="10" className="px-3 py-8 text-center text-slate-400">No activity in this window.</td></tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Annual Leaderboard */}
      <Card className="border-slate-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Annual Leaderboard — {new Date().getFullYear()}</CardTitle>
        </CardHeader>
        <CardContent className="p-0 overflow-auto">
          <table className="w-full text-sm" data-testid="annual-leaderboard">
            <thead className="bg-slate-50 text-slate-600 text-xs">
              <tr>
                <th className="text-left px-3 py-2">Rank</th>
                <th className="text-left px-3 py-2">Employee</th>
                <th className="text-left px-3 py-2">Team</th>
                <th className="text-right px-3 py-2">Annual Points</th>
                <th className="text-right px-3 py-2">Submitted</th>
                <th className="text-right px-3 py-2">Offered</th>
                <th className="text-right px-3 py-2">Joined</th>
              </tr>
            </thead>
            <tbody>
              {annualTop.map(e => (
                <tr key={e.recruiter_id} className="border-t border-slate-100">
                  <td className="px-3 py-2 text-slate-500">#{e.rank}</td>
                  <td className="px-3 py-2 font-medium text-slate-900">{e.recruiter_name}</td>
                  <td className="px-3 py-2 text-slate-600">{e.team_name || '—'}</td>
                  <td className="px-3 py-2 text-right font-semibold text-emerald-700">{e.points.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right">{e.submitted}</td>
                  <td className="px-3 py-2 text-right">{e.offered}</td>
                  <td className="px-3 py-2 text-right font-semibold">{e.joined}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
      {/* Recent Joinings (fix.docx 2026-09-16) — moved from Blog Engine.
          Team leaders fill CTC + revenue here so the Employee
          Performance workspace becomes the single place they track
          actual joinings & the money each one made. */}
      <JoiningsSection scope={appliedScope} />
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Joinings section (was: Blog Engine → Joinings tab).
// Reads /api/blog/joinings; filters by date range, position, location.
// Team leaders inline-edit joined CTC + revenue.
// ─────────────────────────────────────────────────────────────
function JoiningsSection({ scope }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ position_q: '', location_q: '' });
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        date_from: scope.dateFrom || undefined,
        date_to: scope.dateTo || undefined,
      };
      if (scope.teamId && scope.teamId !== '_all') params.team_id = scope.teamId;
      if (scope.employeeId && scope.employeeId !== '_all') params.employee_id = scope.employeeId;
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
      const res = await blogAPI.listJoinings(params);
      setItems(res.data?.items || []);
    } catch {
      toast.error('Failed to load joinings');
    } finally { setLoading(false); }
  }, [filters, scope]);

  useEffect(() => { load(); }, [load]);

  const saveEdit = async (row) => {
    const patch = draft[row.application_id];
    if (!patch) return;
    setSaving(s => ({ ...s, [row.application_id]: true }));
    try {
      const body = {};
      if (patch.joined_ctc !== undefined && patch.joined_ctc !== '') body.joined_ctc = parseFloat(patch.joined_ctc);
      if (patch.revenue !== undefined && patch.revenue !== '') body.revenue = parseFloat(patch.revenue);
      await blogAPI.updateJoining(row.application_id, body);
      toast.success('Saved');
      setDraft(d => { const c = { ...d }; delete c[row.application_id]; return c; });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(s => ({ ...s, [row.application_id]: false }));
    }
  };

  return (
    <Card className="border-slate-200" data-testid="recent-joinings">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Recent Joinings ({items.length})</CardTitle>
        <p className="text-xs text-slate-500">
          Follows the date range, team and employee filters above ({scope.dateFrom} → {scope.dateTo}).
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Position contains</Label>
            <Input value={filters.position_q} onChange={e => setFilters({ ...filters, position_q: e.target.value })} placeholder="e.g. Manager" data-testid="joinings-position" />
          </div>
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Location contains</Label>
            <Input value={filters.location_q} onChange={e => setFilters({ ...filters, location_q: e.target.value })} placeholder="e.g. Delhi" data-testid="joinings-location" />
          </div>
        </div>

        {loading ? (
          <div className="p-6 text-center text-slate-500"><Loader2 className="w-5 h-5 inline animate-spin mr-2" /> Loading joinings…</div>
        ) : items.length === 0 ? (
          <div className="p-6 text-center text-slate-400">No joinings match these filters.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="joinings-table">
              <thead className="bg-slate-50 text-slate-600 text-xs">
                <tr>
                  <th className="text-left px-3 py-2">DOJ</th>
                  <th className="text-left px-3 py-2">Client company</th>
                  <th className="text-left px-3 py-2">Candidate</th>
                  <th className="text-left px-3 py-2">Recruiter</th>
                  <th className="text-left px-3 py-2">Position</th>
                  <th className="text-left px-3 py-2">Location</th>
                  <th className="text-right px-3 py-2">CTC (₹)</th>
                  <th className="text-right px-3 py-2">Revenue (₹)</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {items.map(row => {
                  const patch = draft[row.application_id] || {};
                  const dirty = ('joined_ctc' in patch) || ('revenue' in patch);
                  const ctcVal = patch.joined_ctc !== undefined ? patch.joined_ctc : (row.joined_ctc || '');
                  const revVal = patch.revenue !== undefined ? patch.revenue : (row.revenue ?? '');
                  return (
                    <tr key={row.application_id} className="border-t border-slate-100" data-testid={`joining-row-${row.application_id}`}>
                      <td className="px-3 py-2 font-mono">{row.join_date}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          {row.client_logo_url && <img src={row.client_logo_url} alt="" className="w-5 h-5 rounded object-contain bg-slate-50" />}
                          <span>{row.client_name}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2">{row.candidate_name}</td>
                      <td className="px-3 py-2 text-slate-500">{row.recruiter_name || '—'}</td>
                      <td className="px-3 py-2">{row.position}</td>
                      <td className="px-3 py-2">{row.location}</td>
                      <td className="px-3 py-2 text-right">
                        <Input
                          type="number" min="0" step="1000"
                          className="text-right h-8 w-32 ml-auto"
                          value={ctcVal}
                          onChange={e => setDraft(d => ({ ...d, [row.application_id]: { ...(d[row.application_id] || {}), joined_ctc: e.target.value } }))}
                          data-testid={`joining-ctc-${row.application_id}`}
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Input
                          type="number" min="0" step="100"
                          className="text-right h-8 w-32 ml-auto"
                          value={revVal}
                          onChange={e => setDraft(d => ({ ...d, [row.application_id]: { ...(d[row.application_id] || {}), revenue: e.target.value } }))}
                          placeholder="—"
                          data-testid={`joining-revenue-${row.application_id}`}
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button size="sm" disabled={!dirty || saving[row.application_id]} onClick={() => saveEdit(row)} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid={`joining-save-${row.application_id}`}>
                          {saving[row.application_id] ? '…' : 'Save'}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
