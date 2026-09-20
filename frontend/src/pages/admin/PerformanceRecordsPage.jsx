import { useState, useEffect, useCallback, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Label } from '../../components/ui/label';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../components/ui/select';
import {
  Loader2, Archive, Save, Download, AlertTriangle, ChevronRight, X, RotateCcw,
} from 'lucide-react';
import { toast } from 'sonner';
import { performanceRecordsAPI, branchRevenueAPI } from '../../lib/api';
import {
  DataTable, StatusChip, Achievement, inr, compactINR, downloadCSV,
} from '../../components/revenue/RevenueTables';
import { ReconcilePanel } from '../../components/revenue/ReconcilePanel';

const KPI = [
  ['placements', 'Placements', (v) => v],
  ['recruiter_groups', 'Recruiters', (v) => v],
  ['gross', 'Gross Billing', compactINR],
  ['received', 'Payment Received', compactINR],
  ['pending', 'Pending (PP + IP)', compactINR],
  ['active', 'Active Revenue', compactINR],
  ['realization_pct', 'Realization %', (v) => `${v}%`],
  ['records_needing_review', 'Records to review', (v) => v],
];

function KpiCard({ label, value, hint, testId }) {
  return (
    <div data-testid={testId}
         className="rounded-lg border border-slate-200 bg-white px-4 py-3 transition-colors hover:border-[#7CB342]/50">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-900 tabular-nums">{value}</p>
      {hint && <p className="text-[11px] text-slate-400 mt-0.5">{hint}</p>}
    </div>
  );
}

const MONEY_COLS = [
  ['gross', 'Gross Billing'], ['received', 'Payment Received'], ['pp', 'PP'], ['ip', 'IP'],
  ['backout', 'Backout'], ['credit_note', 'Credit Note'], ['other', 'Other / Review'],
  ['active', 'Active Revenue'],
];

const moneyCols = MONEY_COLS.map(([key, label]) => ({
  key, label, align: 'right', render: (r) => inr(r[key]), csv: (r) => r[key],
}));

export default function PerformanceRecordsPage() {
  const [periodType, setPeriodType] = useState('year');
  const [period, setPeriod] = useState('');
  const [periods, setPeriods] = useState({ months: [], quarters: [], years: [] });
  const [branch, setBranch] = useState('all');
  const [branches, setBranches] = useState([]);
  const [sheet, setSheet] = useState(null);
  const [report, setReport] = useState(null);
  const [archive, setArchive] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingSnap, setSavingSnap] = useState(false);
  const [openTeam, setOpenTeam] = useState(null);
  const [tab, setTab] = useState('dashboard');

  // Placement list (the sheet's row-level view)
  const [rows, setRows] = useState({ items: [], count: 0, totals: null });
  const [rowsLoading, setRowsLoading] = useState(false);
  const [q, setQ] = useState('');
  const [qInput, setQInput] = useState('');
  const [status, setStatus] = useState('all');
  const [recruiterFilter, setRecruiterFilter] = useState(null);

  // Debounce the search so a query isn't fired on every keystroke
  useEffect(() => {
    const t = setTimeout(() => setQ(qInput), 350);
    return () => clearTimeout(t);
  }, [qInput]);

  useEffect(() => {
    performanceRecordsAPI.periods().then(({ data }) => {
      setPeriods(data);
      setPeriod(data.years?.[0] || '');
    }).catch(() => {});
    branchRevenueAPI.branches().then(({ data }) => setBranches(data.branches || [])).catch(() => {});
  }, []);

  const optionsFor = (type) => (
    type === 'month' ? periods.months : type === 'quarter' ? periods.quarters : periods.years
  ) || [];

  const params = useMemo(() => ({
    period_type: periodType, period, ...(branch !== 'all' ? { branch } : {}),
  }), [periodType, period, branch]);

  const load = useCallback(async () => {
    if (!period) return;
    setLoading(true);
    try {
      const [s, a] = await Promise.all([
        branchRevenueAPI.dashboard(params),
        performanceRecordsAPI.archive().catch(() => ({ data: { items: [] } })),
      ]);
      setSheet(s.data);
      setArchive(a.data?.items || []);
      setReport(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load the record');
    } finally {
      setLoading(false);
    }
  }, [params, period]);

  useEffect(() => { load(); }, [load]);

  // The team/target roll-up is a heavier query — only fetch it when asked for.
  const [reportLoading, setReportLoading] = useState(false);
  const loadReport = useCallback(async () => {
    if (!period) return;
    setReportLoading(true);
    try {
      const { data } = await performanceRecordsAPI.report({ period_type: periodType, period });
      setReport(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not load the team roll-up');
    } finally {
      setReportLoading(false);
    }
  }, [periodType, period]);

  useEffect(() => { if (tab === 'teams' && !report) loadReport(); }, [tab, report, loadReport]);

  const loadRows = useCallback(async () => {
    if (!period) return;
    setRowsLoading(true);
    try {
      const { data } = await branchRevenueAPI.placements({
        ...params, limit: 500,
        ...(q ? { q } : {}),
        ...(status !== 'all' ? { payment_status: status } : {}),
        ...(recruiterFilter?.recruiter_id ? { recruiter_id: recruiterFilter.recruiter_id } : {}),
      });
      setRows(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not load the placements');
    } finally {
      setRowsLoading(false);
    }
  }, [params, period, q, status, recruiterFilter]);

  useEffect(() => { if (tab === 'placements') loadRows(); }, [tab, loadRows]);

  const changeType = (t) => {
    setPeriodType(t);
    setPeriod(optionsFor(t)[0] || '');
  };

  const openRecruiter = (r) => {
    setRecruiterFilter(r);
    setTab('placements');
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

  const kpis = sheet?.kpis;
  const branchRows = sheet?.branches || [];
  const recruiterRows = (sheet?.recruiters || []).map((r) => ({ ...r, _key: `${r.branch}-${r.recruiter_id || r.recruiter}` }));
  const review = sheet?.data_quality || [];

  const branchFooter = useMemo(() => (kpis ? {
    branch: 'TOTAL', recruiter_groups: kpis.recruiter_groups, placements: kpis.placements,
    ...Object.fromEntries(MONEY_COLS.map(([k]) => [k, inr(kpis[k])])),
    realization_pct: `${kpis.realization_pct}%`,
    avg_per_placement: inr(kpis.avg_per_placement),
  } : null), [kpis]);

  const branchCols = [
    { key: 'branch', label: 'Branch', render: (r) => <span className="font-medium text-slate-900">{r.branch}</span> },
    { key: 'recruiter_groups', label: 'Recruiters', align: 'right' },
    { key: 'placements', label: 'Placements', align: 'right' },
    ...moneyCols,
    { key: 'realization_pct', label: 'Realization %', align: 'right', render: (r) => `${r.realization_pct}%` },
    { key: 'avg_per_placement', label: 'Avg / Placement', align: 'right', render: (r) => inr(r.avg_per_placement) },
    { key: 'achievement_pct', label: 'Target', align: 'right', render: (r) => <Achievement pct={r.achievement_pct} target={r.period_target} /> },
  ];

  const recruiterCols = [
    { key: 'branch', label: 'Branch' },
    { key: 'account_manager', label: 'Account Manager' },
    {
      key: 'recruiter',
      label: 'Recruiter',
      render: (r) => (
        <span className="font-medium text-slate-900">
          {r.recruiter}
          {r.unassigned && <Badge variant="outline" className="ml-2 text-[10px] border-slate-300 text-slate-500">no login</Badge>}
          {r.is_ex_employee && <Badge variant="outline" className="ml-2 text-[10px] border-amber-200 bg-amber-50 text-amber-700">left</Badge>}
        </span>
      ),
    },
    { key: 'placements', label: 'Placements', align: 'right' },
    ...moneyCols,
    { key: 'realization_pct', label: 'Realization %', align: 'right', render: (r) => `${r.realization_pct}%` },
    { key: 'avg_per_placement', label: 'Avg / Placement', align: 'right', render: (r) => inr(r.avg_per_placement) },
    { key: 'period_target', label: 'Target', align: 'right', render: (r) => inr(r.period_target) },
    { key: 'achievement_pct', label: 'Achieved', align: 'right', render: (r) => <Achievement pct={r.achievement_pct} target={r.period_target} /> },
  ];

  const placementCols = [
    { key: 'doj', label: 'DOJ' },
    { key: 'branch', label: 'Branch' },
    { key: 'recruiter_name', label: 'Recruiter' },
    { key: 'organization', label: 'Client' },
    { key: 'candidate_name', label: 'Candidate', render: (r) => <span className="font-medium text-slate-900">{r.candidate_name || '—'}</span> },
    { key: 'designation', label: 'Designation' },
    { key: 'location', label: 'Location' },
    { key: 'offered_ctc', label: 'Offered CTC', align: 'right', render: (r) => inr(r.offered_ctc) },
    { key: 'invoice_no', label: 'Invoice No.' },
    {
      key: 'revenue',
      label: 'Billing Amount',
      align: 'right',
      render: (r) => (
        <span>
          {inr(r.revenue)}
          {r.shared_credit && (
            <span className="ml-1 text-[10px] text-slate-400">50% shared</span>
          )}
        </span>
      ),
      csv: (r) => r.revenue,
    },
    { key: 'payment_status', label: 'Payment Status', render: (r) => <StatusChip status={r.payment_status} /> },
  ];

  const exportCSV = () => {
    const map = {
      dashboard: ['branch-summary', branchCols, branchRows],
      branches: ['branch-summary', branchCols, branchRows],
      recruiters: ['recruiter-revenue', recruiterCols, recruiterRows],
      placements: ['placements', placementCols, rows.items],
      review: ['data-quality', [
        { key: 's_no', label: 'S.No' }, { key: 'branch', label: 'Branch' },
        { key: 'recruiter', label: 'Recruiter' }, { key: 'organization', label: 'Client' },
        { key: 'candidate_name', label: 'Candidate' }, { key: 'revenue', label: 'Billing Amount' },
        { key: 'payment_status', label: 'Payment Status' },
        { key: 'reasons', label: 'Review note', csv: (r) => (r.reasons || []).join(' · ') },
      ], review],
    };
    const [name, cols, data] = map[tab] || map.dashboard;
    downloadCSV(
      `vhc-${name}-${period}.csv`,
      cols.map((c) => ({ label: c.label, value: c.csv || ((r) => r[c.key]) })),
      data,
    );
  };

  return (
    <div className="space-y-6" data-testid="performance-records-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Branch &amp; Recruiter Revenue</h1>
          <p className="text-sm text-slate-500 max-w-3xl">
            Performance records for every branch and recruiter — placements, billing, collections and
            target achievement. Revenue is taken from the branch tracker plus joinings booked in the
            platform. Closed periods archive automatically.
          </p>
        </div>
        <div className="flex items-end gap-2 flex-wrap">
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Basis</Label>
            <Select value={periodType} onValueChange={changeType}>
              <SelectTrigger className="w-28" data-testid="record-basis"><SelectValue /></SelectTrigger>
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
              <SelectTrigger className="w-32" data-testid="record-period"><SelectValue /></SelectTrigger>
              <SelectContent className="max-h-72">
                {optionsFor(periodType).map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-slate-500 mb-1 block">Branch</Label>
            <Select value={branch} onValueChange={setBranch}>
              <SelectTrigger className="w-36" data-testid="record-branch"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All branches</SelectItem>
                {branches.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button variant="outline" onClick={exportCSV} data-testid="record-export-btn">
            <Download className="w-4 h-4 mr-1" /> Export
          </Button>
          <Button variant="outline" onClick={saveSnapshot} disabled={savingSnap || !period}
                  data-testid="record-snapshot-btn">
            {savingSnap ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
            Store record
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : !kpis ? (
        <p className="text-sm text-slate-500">Pick a period to see the record.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3" data-testid="record-kpis">
            {KPI.map(([key, label, fmt]) => (
              <KpiCard key={key} testId={`record-kpi-${key}`} label={label} value={fmt(kpis[key])}
                       hint={key === 'active' ? 'gross − backout / credit note'
                         : key === 'realization_pct' ? 'received ÷ active'
                           : key === 'placements' ? `${sheet.range?.from} → ${sheet.range?.to}` : null} />
            ))}
          </div>

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="flex-wrap h-auto">
              <TabsTrigger value="dashboard" data-testid="tab-dashboard">Branch Summary</TabsTrigger>
              <TabsTrigger value="recruiters" data-testid="tab-recruiters">Recruiter Revenue</TabsTrigger>
              <TabsTrigger value="placements" data-testid="tab-placements">Placements</TabsTrigger>
              <TabsTrigger value="teams" data-testid="tab-teams">Teams &amp; Targets</TabsTrigger>
              <TabsTrigger value="review" data-testid="tab-review">
                Review {kpis.records_needing_review ? `(${kpis.records_needing_review})` : ''}
              </TabsTrigger>
              <TabsTrigger value="archive" data-testid="tab-archive">Archive ({archive.length})</TabsTrigger>
            </TabsList>

            <TabsContent value="dashboard" className="mt-4">
              <DataTable testId="branch-summary-table" cols={branchCols} rows={branchRows}
                         footer={branchFooter} initialSort={{ key: 'gross', dir: 'desc' }} />
            </TabsContent>

            <TabsContent value="recruiters" className="mt-4 space-y-2">
              <p className="text-xs text-slate-500">
                Click a recruiter to see their placements. Spelling variants from the tracker are
                merged into one person; anyone who has left keeps their revenue inside their branch.
              </p>
              <DataTable testId="recruiter-revenue-table" cols={recruiterCols} rows={recruiterRows}
                         initialSort={{ key: 'gross', dir: 'desc' }} onRowClick={openRecruiter} />
            </TabsContent>

            <TabsContent value="placements" className="mt-4 space-y-3">
              <div className="flex items-end gap-2 flex-wrap">
                <div className="flex-1 min-w-[220px]">
                  <Label className="text-xs text-slate-500 mb-1 block">
                    Search {qInput !== q && <span className="text-slate-400">· searching…</span>}
                  </Label>
                  <Input value={qInput} onChange={(e) => setQInput(e.target.value)}
                         placeholder="Candidate, client, designation, invoice no."
                         data-testid="placements-search" />
                </div>
                <div>
                  <Label className="text-xs text-slate-500 mb-1 block">Payment status</Label>
                  <Select value={status} onValueChange={setStatus}>
                    <SelectTrigger className="w-44" data-testid="placements-status"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All statuses</SelectItem>
                      {['Payment Received', 'PP', 'IP', 'Backout', 'Credit Note', 'Other / Review']
                        .map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                {recruiterFilter && (
                  <Button variant="outline" size="sm" onClick={() => setRecruiterFilter(null)}
                          data-testid="placements-clear-recruiter">
                    <X className="w-3 h-3 mr-1" /> {recruiterFilter.recruiter}
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={loadRows} data-testid="placements-refresh">
                  <RotateCcw className="w-3 h-3 mr-1" /> Refresh
                </Button>
              </div>
              {rowsLoading ? (
                <div className="py-12 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-slate-400" /></div>
              ) : (
                <>
                  <p className="text-xs text-slate-500" data-testid="placements-count">
                    {rows.totals?.placements ?? 0} placements · gross {inr(rows.totals?.gross)} · received {inr(rows.totals?.received)}
                    {rows.count > rows.items.length ? ` · showing first ${rows.items.length}` : ''}
                  </p>
                  <DataTable testId="placements-table" cols={placementCols} rows={rows.items}
                             initialSort={{ key: 'doj', dir: 'desc' }} />
                </>
              )}
            </TabsContent>

            <TabsContent value="teams" className="mt-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Teams &amp; contributors</CardTitle>
                </CardHeader>
                <CardContent>
                  {reportLoading ? (
                    <div className="py-12 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-slate-400" /></div>
                  ) : (report?.teams || []).length === 0 ? (
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
                                Account manager: {t.employer_name || '—'} · {t.members.length} members
                                {t.ex_member_revenue ? ` · ${inr(t.ex_member_revenue)} from people who left / unassigned` : ''}
                              </p>
                            </div>
                            <div className="flex items-center gap-4">
                              <div className="text-right">
                                <p className="text-sm font-semibold tabular-nums">{inr(t.revenue)}</p>
                                <p className="text-xs text-slate-500">{t.joinings} placements</p>
                              </div>
                              <Achievement pct={t.period_achievement_pct} target={t.period_target} />
                              <ChevronRight className={`w-4 h-4 text-slate-400 transition-transform ${openTeam === t.team_id ? 'rotate-90' : ''}`} />
                            </div>
                          </button>
                          {openTeam === t.team_id && (
                            <div className="border-t bg-slate-50/60 px-4 py-3 space-y-3">
                              <DataTable
                                testId={`team-members-${t.team_id}`}
                                initialSort={{ key: 'revenue', dir: 'desc' }}
                                rows={t.members.map((m) => ({ ...m, _key: m.user_id }))}
                                empty="No members on this team."
                                cols={[
                                  { key: 'name', label: 'Recruiter', render: (m) => <span className="font-medium text-slate-900">{m.name}</span> },
                                  { key: 'joinings', label: 'Placements', align: 'right' },
                                  { key: 'revenue', label: 'Revenue', align: 'right', render: (m) => inr(m.revenue) },
                                  { key: 'period_target', label: periodType === 'year' ? 'Target' : 'Period target', align: 'right', render: (m) => inr(m.period_target) },
                                  { key: 'period_achievement_pct', label: 'Achieved', align: 'right', render: (m) => <Achievement pct={m.period_achievement_pct} target={m.period_target} /> },
                                ]}
                              />
                              {(t.ex_members || []).length > 0 && (
                                <div>
                                  <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
                                    Left the company / unassigned — counted in this team
                                  </p>
                                  <ul className="text-xs text-slate-600 space-y-0.5">
                                    {t.ex_members.map((p) => (
                                      <li key={p.name}>{p.name} · {p.placements} placements · {inr(p.active)}</li>
                                    ))}
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
            </TabsContent>

            <TabsContent value="review" className="mt-4 space-y-4">
              <ReconcilePanel year={Number(period.slice(0, 4)) || new Date().getFullYear()} />
              <div className="flex items-center gap-2 text-sm text-slate-600">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                {kpis.records_needing_review} records need a decision ·{' '}
                {kpis.rows_without_login} placements belong to people with no login
              </div>
              <DataTable
                testId="review-table"
                initialSort={{ key: 'branch', dir: 'asc' }}
                empty="Nothing to review in this period."
                rows={review.map((r, i) => ({ ...r, _key: `${r.s_no}-${i}` }))}
                cols={[
                  { key: 's_no', label: 'S.No' },
                  { key: 'branch', label: 'Branch' },
                  { key: 'recruiter', label: 'Recruiter' },
                  { key: 'organization', label: 'Client' },
                  { key: 'candidate_name', label: 'Candidate' },
                  { key: 'revenue', label: 'Billing Amount', align: 'right', render: (r) => inr(r.revenue) },
                  { key: 'payment_status', label: 'Status', render: (r) => <StatusChip status={r.payment_status} /> },
                  {
                    key: 'reasons',
                    label: 'Needs',
                    render: (r) => (
                      <span className={r.blocking ? 'text-rose-700' : 'text-slate-500'}>
                        {(r.reasons || []).join(' · ')}
                      </span>
                    ),
                  },
                ]}
              />
            </TabsContent>

            <TabsContent value="archive" className="mt-4">
              {archive.length === 0 ? (
                <p className="py-10 text-center text-sm text-slate-500" data-testid="record-archive-empty">
                  Nothing archived yet — records are stored automatically once a period ends,
                  or hit “Store record” to freeze this one now.
                </p>
              ) : (
                <DataTable
                  testId="record-archive-table"
                  initialSort={{ key: 'period', dir: 'desc' }}
                  rows={archive}
                  cols={[
                    { key: 'period', label: 'Period', render: (a) => <span className="font-medium">{a.period}</span> },
                    { key: 'period_type', label: 'Basis', render: (a) => <span className="capitalize">{a.period_type}</span> },
                    { key: 'total_revenue', label: 'Revenue', align: 'right', render: (a) => inr(a.total_revenue) },
                    { key: 'total_joinings', label: 'Placements', align: 'right' },
                    { key: 'archived_at', label: 'Stored', render: (a) => `${(a.archived_at || '').slice(0, 10)} · ${a.archived_by}` },
                    {
                      key: 'id',
                      label: '',
                      render: (a) => (
                        <Button size="sm" variant="ghost"
                                onClick={() => { setPeriodType(a.period_type); setPeriod(a.period); setTab('dashboard'); }}
                                data-testid={`record-open-${a.id}`}>
                          <Archive className="w-3 h-3 mr-1" /> Open
                        </Button>
                      ),
                    },
                  ]}
                />
              )}
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
