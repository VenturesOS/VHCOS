/**
 * AnalyticsHubPage — Phase 56 (Feb 2026)
 *
 * Unified admin analytics hub combining first-party page-view tracking
 * with in-app recruiter activity. Data comes from a single endpoint:
 *   GET /api/analytics/hub/dashboard?days=N
 *
 * Sections:
 *   1. KPI strip (total page views, DAU avg, top route)
 *   2. Daily uniques chart
 *   3. Top pages table
 *   4. Top recruiters by activity
 *   5. Capture funnel (action counts)
 *   6. Auth split (logged-in vs anonymous)
 *   7. Top referrers
 */
import { useState, useEffect, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { Badge } from "../../components/ui/badge";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area, PieChart, Pie, Cell,
} from "recharts";
import { Eye, Users, MousePointerClick, Globe, TrendingUp, Activity, Loader2, Brain, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

const envUrl = process.env.REACT_APP_BACKEND_URL;
const API_BASE = envUrl ? `${envUrl.replace(/\/+$/, "")}/api` : "/api";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("vhc_token");
}

async function fetchJSON(url) {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

const COLORS = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0891b2"];

function KpiCard({ icon: Icon, label, value, sub, color = "text-blue-600", bg = "bg-blue-50", testId }) {
  return (
    <Card className="border-slate-200" data-testid={testId}>
      <CardContent className="p-4">
        <div className="flex items-center gap-2.5 mb-2">
          <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
            <Icon className={`w-4 h-4 ${color}`} />
          </div>
          <span className="text-xs text-slate-500 font-medium">{label}</span>
        </div>
        <p className="text-2xl font-bold text-slate-900">
          {typeof value === "number" ? value.toLocaleString() : value || "—"}
        </p>
        {sub && <p className="text-[10px] text-slate-400 mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

export default function AnalyticsHubPage() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    fetchJSON(`/analytics/hub/dashboard?days=${days}`)
      .then((d) => { if (!cancel) setData(d); })
      .catch((e) => toast.error(`Failed to load: ${e.message}`))
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [days]);

  // LTR Phase 1 telemetry — separate endpoint, separate state so it
  // doesn't gate the main dashboard on this auxiliary call.
  const [ltr, setLtr] = useState(null);
  useEffect(() => {
    let cancel = false;
    fetchJSON(`/admin/ltr/stats?days=${days}`)
      .then((d) => { if (!cancel) setLtr(d); })
      .catch(() => {});  // soft fail — flywheel is nice-to-have
    return () => { cancel = true; };
  }, [days]);

  const avgDau = useMemo(() => {
    if (!data?.dau?.length) return 0;
    return Math.round(data.dau.reduce((a, d) => a + (d.uniques || 0), 0) / data.dau.length);
  }, [data]);

  const topRoute = data?.top_pages?.[0]?.route || "—";
  const authPct = useMemo(() => {
    if (!data?.auth_split?.length) return null;
    const auth = data.auth_split.find((s) => s.type === "auth")?.count || 0;
    const anon = data.auth_split.find((s) => s.type === "anon")?.count || 0;
    const total = auth + anon;
    if (!total) return null;
    return { auth, anon, authPct: Math.round((auth / total) * 100) };
  }, [data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96" data-testid="analytics-hub-loading">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto" data-testid="analytics-hub-page">
      {/* Header + range toggle */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Analytics Hub</h1>
          <p className="text-sm text-slate-500 mt-1">
            First-party page views + in-app activity. Privacy-first, no Google.
          </p>
        </div>
        <Tabs value={String(days)} onValueChange={(v) => setDays(parseInt(v))}>
          <TabsList data-testid="analytics-range-tabs">
            <TabsTrigger value="1" data-testid="range-1d">1d</TabsTrigger>
            <TabsTrigger value="7" data-testid="range-7d">7d</TabsTrigger>
            <TabsTrigger value="30" data-testid="range-30d">30d</TabsTrigger>
            <TabsTrigger value="90" data-testid="range-90d">90d</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KpiCard
          icon={Eye}
          label="Total Page Views"
          value={data?.total_pageviews || 0}
          sub={`Last ${days} day${days > 1 ? "s" : ""}`}
          testId="kpi-pageviews"
        />
        <KpiCard
          icon={Users}
          label="Avg Daily Uniques"
          value={avgDau}
          color="text-emerald-600"
          bg="bg-emerald-50"
          testId="kpi-dau"
        />
        <KpiCard
          icon={MousePointerClick}
          label="Top Route"
          value={topRoute === "—" ? "—" : topRoute.slice(0, 22)}
          sub={data?.top_pages?.[0] ? `${data.top_pages[0].views} views` : ""}
          color="text-amber-600"
          bg="bg-amber-50"
          testId="kpi-top-route"
        />
        <KpiCard
          icon={Activity}
          label="Logged-in Share"
          value={authPct ? `${authPct.authPct}%` : "—"}
          sub={authPct ? `${authPct.auth} auth · ${authPct.anon} anon` : ""}
          color="text-violet-600"
          bg="bg-violet-50"
          testId="kpi-auth"
        />
      </div>

      {/* Daily uniques chart */}
      <Card className="border-slate-200">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-blue-600" /> Daily Unique Visitors
          </CardTitle>
        </CardHeader>
        <CardContent>
          {data?.dau?.length ? (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={data.dau} margin={{ top: 10, right: 12, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="day" tick={{ fontSize: 11 }} stroke="#64748b" />
                <YAxis tick={{ fontSize: 11 }} stroke="#64748b" />
                <Tooltip
                  contentStyle={{ borderRadius: 8, fontSize: 12, border: "1px solid #e2e8f0" }}
                  labelStyle={{ fontWeight: 600 }}
                />
                <Area
                  type="monotone"
                  dataKey="uniques"
                  stroke="#2563eb"
                  fill="#2563eb"
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-sm text-slate-400 py-8 text-center">No page-view data yet</div>
          )}
        </CardContent>
      </Card>

      {/* Two-column row: top pages + top recruiters */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Globe className="w-4 h-4 text-blue-600" /> Top Pages
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data?.top_pages?.length ? (
              <div className="space-y-2" data-testid="top-pages-list">
                {data.top_pages.map((p, i) => (
                  <div key={p.route || i} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-100 last:border-0">
                    <span className="text-slate-700 truncate max-w-[70%] font-mono text-xs">
                      {p.route || "/"}
                    </span>
                    <Badge variant="secondary" className="text-xs">{p.views.toLocaleString()}</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-400 py-8 text-center">No page-view data yet</div>
            )}
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Users className="w-4 h-4 text-emerald-600" /> Top Recruiters by Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data?.top_recruiters?.length ? (
              <div className="space-y-2" data-testid="top-recruiters-list">
                {data.top_recruiters.map((r, i) => (
                  <div key={r.user_id || i} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-100 last:border-0">
                    <div className="flex flex-col">
                      <span className="text-slate-700 font-medium">{r.user_name || r.user_email || "Unknown"}</span>
                      {r.user_email && r.user_name && (
                        <span className="text-[10px] text-slate-400">{r.user_email}</span>
                      )}
                    </div>
                    <Badge className="text-xs bg-emerald-100 text-emerald-700 hover:bg-emerald-100">
                      {r.actions.toLocaleString()} actions
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-400 py-8 text-center">No activity logs yet</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Funnel + Referrers */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Activity className="w-4 h-4 text-violet-600" /> Activity Funnel
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data?.funnel?.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.funnel} margin={{ top: 10, right: 12, left: -16, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="action" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" interval={0} stroke="#64748b" />
                  <YAxis tick={{ fontSize: 11 }} stroke="#64748b" />
                  <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12, border: "1px solid #e2e8f0" }} />
                  <Bar dataKey="count" fill="#7c3aed" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-sm text-slate-400 py-8 text-center">No activity yet</div>
            )}
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Globe className="w-4 h-4 text-amber-600" /> Top Referrers
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data?.top_referrers?.length ? (
              <div className="space-y-2" data-testid="top-referrers-list">
                {data.top_referrers.map((r, i) => (
                  <div key={r.referrer || i} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-100 last:border-0">
                    <span className="text-slate-700 truncate max-w-[75%] font-mono text-xs" title={r.referrer}>
                      {(r.referrer || "").replace(/^https?:\/\//, "").slice(0, 50) || "—"}
                    </span>
                    <Badge variant="secondary" className="text-xs">{r.hits.toLocaleString()}</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-400 py-8 text-center">No referrer data</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── LTR Data Flywheel (Phase 56.5) ───────────────────────────── */}
      {/* Visualises progress toward the 5,000 labeled-triplet threshold
          needed before XGBoost LTR Phase 2 training can begin.
          Data: GET /api/admin/ltr/stats?days=N
          Soft-fails — section just doesn't render if endpoint errors. */}
      {ltr && (
        <Card className="border-slate-200" data-testid="ltr-flywheel-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple-600" /> Data Flywheel — LTR Training Readiness
              {ltr.ready_for_training && (
                <Badge className="bg-green-100 text-green-700 text-[10px] ml-2">
                  <CheckCircle2 className="w-3 h-3 mr-0.5" /> Ready to train
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className="bg-slate-50 rounded-lg p-3" data-testid="ltr-stat-sessions">
                <div className="text-xs text-slate-500">Search sessions</div>
                <div className="text-2xl font-semibold text-slate-900">{ltr.n_sessions.toLocaleString()}</div>
                <div className="text-[11px] text-slate-400 mt-0.5">{ltr.n_impressions.toLocaleString()} impressions</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-3" data-testid="ltr-stat-actions">
                <div className="text-xs text-slate-500">User actions</div>
                <div className="text-2xl font-semibold text-slate-900">{ltr.n_actions.toLocaleString()}</div>
                <div className="text-[11px] text-slate-400 mt-0.5">{ltr.sessions_with_actions} sessions with action</div>
              </div>
              <div className="bg-purple-50 rounded-lg p-3" data-testid="ltr-stat-progress">
                <div className="text-xs text-purple-700">Triplet progress</div>
                <div className="text-2xl font-semibold text-purple-900">
                  {ltr.triplet_estimate.toLocaleString()} / {ltr.target_triplets.toLocaleString()}
                </div>
                <div className="w-full bg-purple-100 rounded-full h-1.5 mt-2">
                  <div
                    className="bg-purple-600 h-1.5 rounded-full transition-all"
                    style={{ width: `${Math.min(100, ltr.progress_pct)}%` }}
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1.5">By source</div>
                {ltr.by_source?.length ? (
                  <div className="space-y-1.5">
                    {ltr.by_source.map((s) => (
                      <div key={s._id} className="flex items-center justify-between text-sm py-1 border-b border-slate-100 last:border-0">
                        <span className="text-slate-700 font-mono text-xs">{s._id}</span>
                        <Badge variant="secondary" className="text-xs">{s.n.toLocaleString()}</Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-slate-400 py-3 text-center">No sessions yet — run a Talent Graph search to seed</div>
                )}
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1.5">By action</div>
                {ltr.by_action?.length ? (
                  <div className="space-y-1.5">
                    {ltr.by_action.map((s) => (
                      <div key={s._id} className="flex items-center justify-between text-sm py-1 border-b border-slate-100 last:border-0">
                        <span className="text-slate-700 capitalize">{s._id.replace(/_/g, " ")}</span>
                        <Badge variant="secondary" className="text-xs">{s.n.toLocaleString()}</Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-slate-400 py-3 text-center">No actions logged yet</div>
                )}
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100 text-xs text-slate-500">
              Each user click / shortlist / contact / add-to-pipeline becomes a labeled triplet.
              When the bar fills, the XGBoost ranker can be trained. Data accumulates automatically — no manual labeling.
            </div>

            {/* Leaderboard — top contributors to LTR training data */}
            {ltr.by_user?.length > 0 && (
              <div className="mt-4 pt-3 border-t border-slate-100" data-testid="ltr-leaderboard">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3 h-3" /> Top contributors ({ltr.by_user.length})
                </div>
                <div className="space-y-1">
                  {ltr.by_user.map((u, i) => {
                    const pct = ltr.n_actions ? Math.round((u.n_actions / ltr.n_actions) * 100) : 0;
                    const initials = (u.email || "?").split("@")[0].slice(0, 2).toUpperCase();
                    const medal = i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : null;
                    return (
                      <div
                        key={u.email}
                        className="flex items-center gap-3 py-1.5 border-b border-slate-50 last:border-0"
                        data-testid={`ltr-leader-${i}`}
                      >
                        <div className="w-6 text-center text-xs text-slate-500">
                          {medal || `#${i + 1}`}
                        </div>
                        <div className="w-7 h-7 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center text-xs font-semibold">
                          {initials}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-slate-800 truncate">{u.email || "(unknown)"}</div>
                          <div className="text-[10px] text-slate-400">
                            {u.role || "—"} · {pct}% of actions
                          </div>
                        </div>
                        <Badge variant="outline" className="text-xs">{u.n_actions.toLocaleString()}</Badge>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
