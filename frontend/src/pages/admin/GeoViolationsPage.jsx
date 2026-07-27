import { useState, useEffect, useCallback } from 'react';
import { attendanceAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { ShieldAlert, MapPin, RefreshCw, Users, AlertTriangle, Loader2, Clock } from 'lucide-react';

const RANGE_OPTIONS = [
  { value: 1,  label: 'Today' },
  { value: 7,  label: 'Last 7d' },
  { value: 30, label: 'Last 30d' },
];

const REASON_STYLES = {
  outside_fence: 'bg-red-100 text-red-700',
  gps_missing:   'bg-amber-100 text-amber-700',
};

const REASON_LABELS = {
  outside_fence: 'Outside fence',
  gps_missing:   'GPS missing',
};

function fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit', month: 'short',
      hour: '2-digit', minute: '2-digit',
      hour12: true,
    });
  } catch { return iso.slice(0, 19); }
}

export default function GeoViolationsPage() {
  const [days, setDays] = useState(1);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ total: 0, violations: [], by_user: [] });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await attendanceAPI.getGeoViolations({ days, limit: 500 });
      setData(res.data || { total: 0, violations: [], by_user: [] });
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to load violations');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  const worstOffenders = data.by_user || [];
  const checkinCount  = data.violations.filter(v => v.action === 'check-in').length;
  const checkoutCount = data.violations.filter(v => v.action === 'check-out').length;
  const gpsMissing    = data.violations.filter(v => v.reason === 'gps_missing').length;

  return (
    <div className="space-y-6" data-testid="geo-violations-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-red-50 border border-red-200">
            <ShieldAlert className="h-5 w-5 text-red-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight" data-testid="page-title">
              Geo-Fence Violations
            </h1>
            <p className="text-sm text-muted-foreground">
              Blocked check-in / check-out attempts from outside allowed offices
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {RANGE_OPTIONS.map(r => (
            <Button
              key={r.value}
              size="sm"
              variant={days === r.value ? 'default' : 'outline'}
              onClick={() => setDays(r.value)}
              data-testid={`range-${r.value}`}
              className={days === r.value ? 'bg-red-600 hover:bg-red-700' : ''}
            >
              {r.label}
            </Button>
          ))}
          <Button
            size="sm"
            variant="ghost"
            onClick={load}
            disabled={loading}
            data-testid="refresh-btn"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total blocked"      value={data.total}      icon={AlertTriangle} tint="red"    testId="stat-total" />
        <StatCard label="Check-in attempts"  value={checkinCount}    icon={Clock}         tint="orange" testId="stat-checkin" />
        <StatCard label="Check-out attempts" value={checkoutCount}   icon={Clock}         tint="orange" testId="stat-checkout" />
        <StatCard label="GPS missing"        value={gpsMissing}      icon={MapPin}        tint="amber"  testId="stat-gps" />
      </div>

      {/* Worst offenders leaderboard — the key panel per the user's ask */}
      <Card data-testid="offenders-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="h-4 w-4 text-slate-600" />
            Worst offenders — ranked by count
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8 text-slate-400">
              <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading…
            </div>
          ) : worstOffenders.length === 0 ? (
            <div className="text-center py-8 text-sm text-slate-500">
              🎉 No geo-fence violations in the selected range.
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {worstOffenders.map((u, i) => (
                <div
                  key={u.user_id}
                  className="flex items-center justify-between py-2.5"
                  data-testid={`offender-row-${i}`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-semibold shrink-0 ${
                        i === 0 ? 'bg-red-100 text-red-700' :
                        i === 1 ? 'bg-orange-100 text-orange-700' :
                        i === 2 ? 'bg-amber-100 text-amber-700' :
                                  'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {i + 1}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-800 truncate">
                        {u.user_name || 'Unknown user'}
                      </div>
                      <div className="text-[11px] text-slate-500 truncate">{u.user_email}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {Object.entries(u.reasons || {}).map(([r, c]) => (
                      <Badge key={r} className={`text-[10px] ${REASON_STYLES[r] || 'bg-slate-100 text-slate-700'}`}>
                        {REASON_LABELS[r] || r} · {c}
                      </Badge>
                    ))}
                    <span className="text-sm font-semibold text-slate-800 tabular-nums w-8 text-right">
                      {u.count}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Raw event log */}
      <Card data-testid="events-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4 text-slate-600" />
            Recent events
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-slate-400">
              <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading…
            </div>
          ) : data.violations.length === 0 ? (
            <div className="text-center py-8 text-sm text-slate-500">No events in this range.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-slate-600">When</th>
                    <th className="px-4 py-2 text-left font-medium text-slate-600">User</th>
                    <th className="px-4 py-2 text-left font-medium text-slate-600">Action</th>
                    <th className="px-4 py-2 text-left font-medium text-slate-600">Reason</th>
                    <th className="px-4 py-2 text-right font-medium text-slate-600">Distance</th>
                    <th className="px-4 py-2 text-left font-medium text-slate-600">Office</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.violations.map(v => (
                    <tr key={v.id} data-testid={`event-row-${v.id}`}>
                      <td className="px-4 py-2 whitespace-nowrap text-slate-600">{fmtTime(v.created_at)}</td>
                      <td className="px-4 py-2">
                        <div className="text-slate-800 font-medium">{v.user_name || '—'}</div>
                        <div className="text-[11px] text-slate-500">{v.user_email}</div>
                      </td>
                      <td className="px-4 py-2">
                        <Badge className={v.action === 'check-in' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'}>
                          {v.action}
                        </Badge>
                      </td>
                      <td className="px-4 py-2">
                        <Badge className={REASON_STYLES[v.reason] || 'bg-slate-100 text-slate-700'}>
                          {REASON_LABELS[v.reason] || v.reason}
                        </Badge>
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums text-slate-700">
                        {v.distance_m != null ? `${v.distance_m.toLocaleString()} m` : '—'}
                      </td>
                      <td className="px-4 py-2 text-slate-600">{v.office || '—'}</td>
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

function StatCard({ label, value, icon: Icon, tint, testId }) {
  const tints = {
    red:    { bg: 'bg-red-50',    border: 'border-red-200',    icon: 'text-red-600',    text: 'text-red-700' },
    orange: { bg: 'bg-orange-50', border: 'border-orange-200', icon: 'text-orange-600', text: 'text-orange-700' },
    amber:  { bg: 'bg-amber-50',  border: 'border-amber-200',  icon: 'text-amber-600',  text: 'text-amber-700' },
  };
  const t = tints[tint] || tints.red;
  return (
    <Card className={`${t.bg} ${t.border}`} data-testid={testId}>
      <CardContent className="pt-4 pb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg bg-white/60 ${t.icon}`}>
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
            <div className={`text-2xl font-bold tabular-nums ${t.text}`}>{value.toLocaleString()}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
