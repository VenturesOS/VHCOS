import { useState, useEffect, useCallback } from 'react';
import { teamDigestAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import {
  MessageCircle, Copy, RefreshCw, Trophy, TrendingUp, TrendingDown,
  Users, Calendar, Sparkles, AlertTriangle, Award, Loader2, Send,
} from 'lucide-react';

const ISTToday = () => {
  // Compute today's IST date string YYYY-MM-DD
  const now = new Date();
  const istMs = now.getTime() + (now.getTimezoneOffset() + 330) * 60 * 1000;
  const ist = new Date(istMs);
  return ist.toISOString().slice(0, 10);
};

function StatTile({ icon: Icon, label, value, sub, color = 'gray', testId }) {
  const colors = {
    teal: 'bg-teal-50 text-teal-700 border-teal-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    gray: 'bg-gray-50 text-gray-700 border-gray-200',
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
  };
  return (
    <Card data-testid={testId} className={`border ${colors[color]}`}>
      <CardContent className="pt-4 pb-4 px-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider opacity-70">{label}</p>
            <p className="text-2xl font-bold mt-1">{value ?? '—'}</p>
            {sub && <p className="text-[11px] opacity-60 mt-0.5">{sub}</p>}
          </div>
          <Icon className="w-6 h-6 opacity-60" />
        </div>
      </CardContent>
    </Card>
  );
}

export default function DailyDigestPage() {
  const [digest, setDigest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [selectedDate, setSelectedDate] = useState(ISTToday());

  const loadToday = useCallback(async () => {
    setLoading(true);
    try {
      const res = await teamDigestAPI.today();
      setDigest(res.data);
      setSelectedDate(res.data.date);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load digest');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadByDate = useCallback(async (date) => {
    setLoading(true);
    try {
      const res = await teamDigestAPI.byDate(date);
      setDigest(res.data);
      setSelectedDate(res.data.date);
    } catch (e) {
      if (e?.response?.status === 404) {
        toast.warning('No digest stored for that date. Click "Regenerate" to compute it.');
      } else {
        toast.error(e?.response?.data?.detail || 'Failed to load digest');
      }
      setDigest(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadToday(); }, [loadToday]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const isToday = selectedDate === ISTToday();
      const res = isToday
        ? await teamDigestAPI.regenerate()
        : await teamDigestAPI.regenForDate(selectedDate);
      setDigest(res.data);
      toast.success('Digest regenerated');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to regenerate');
    } finally {
      setRegenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!digest?.whatsapp_text) return;
    try {
      await navigator.clipboard.writeText(digest.whatsapp_text);
      toast.success('Copied to clipboard — paste into WhatsApp');
    } catch (e) {
      toast.error('Clipboard access blocked by browser');
    }
  };

  const handleSendWhatsApp = () => {
    if (!digest?.whatsapp_text) return;
    const encoded = encodeURIComponent(digest.whatsapp_text);
    window.open(`https://web.whatsapp.com/send?text=${encoded}`, '_blank', 'noopener');
  };

  return (
    <div className="space-y-6 p-1" data-testid="daily-digest-page">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <MessageCircle className="w-7 h-7 text-emerald-600" />
            Daily Team Digest
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Auto-generated 18:00 IST. One-click copy for your WhatsApp group.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5">
            <Calendar className="w-4 h-4 text-gray-400" />
            <Input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              onBlur={() => selectedDate && loadByDate(selectedDate)}
              max={ISTToday()}
              className="w-40"
              data-testid="digest-date-picker"
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRegenerate}
            disabled={regenerating}
            data-testid="digest-regenerate-btn"
          >
            {regenerating
              ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
              : <RefreshCw className="w-4 h-4 mr-1.5" />}
            Regenerate
          </Button>
        </div>
      </div>

      {loading && !digest ? (
        <Card><CardContent className="py-16 text-center text-gray-400">
          <Loader2 className="w-6 h-6 mx-auto animate-spin mb-2" />
          Loading digest…
        </CardContent></Card>
      ) : !digest ? (
        <Card><CardContent className="py-16 text-center text-gray-400">
          No digest available for this date.
        </CardContent></Card>
      ) : (
        <>
          {/* Top stat tiles */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile
              icon={Users}
              color="blue"
              label="Recruiters"
              value={digest.recruiter_count}
              sub={`${digest.employer_count} team leads`}
              testId="stat-recruiters"
            />
            <StatTile
              icon={Trophy}
              color="amber"
              label="Top Score"
              value={digest.top_overall?.[0]?.activity_score ?? 0}
              sub={digest.top_overall?.[0]?.name || '—'}
              testId="stat-top-score"
            />
            <StatTile
              icon={AlertTriangle}
              color={digest.inactive_recruiters?.length > 0 ? 'red' : 'green'}
              label="Inactive"
              value={digest.inactive_recruiters?.length || 0}
              sub="recruiters with no activity"
              testId="stat-inactive"
            />
            <StatTile
              icon={Award}
              color="teal"
              label="Best Quality"
              value={digest.best_quality ? `${digest.best_quality.capture_quality}%` : '—'}
              sub={digest.best_quality?.name || 'no captures today'}
              testId="stat-best-quality"
            />
          </div>

          {/* WhatsApp preview card */}
          <Card className="border-emerald-200 bg-gradient-to-br from-emerald-50/40 to-white shadow-sm" data-testid="whatsapp-preview-card">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <MessageCircle className="w-5 h-5 text-emerald-600" />
                WhatsApp Message Preview
              </CardTitle>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCopy}
                  data-testid="copy-whatsapp-btn"
                >
                  <Copy className="w-4 h-4 mr-1.5" />
                  Copy
                </Button>
                <Button
                  size="sm"
                  className="bg-emerald-600 hover:bg-emerald-700"
                  onClick={handleSendWhatsApp}
                  data-testid="open-whatsapp-btn"
                >
                  <Send className="w-4 h-4 mr-1.5" />
                  Open WhatsApp Web
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <pre
                className="whitespace-pre-wrap font-mono text-[13px] leading-relaxed bg-white border border-gray-200 rounded-md p-4 max-h-[500px] overflow-auto text-gray-800"
                data-testid="whatsapp-text"
              >
                {digest.whatsapp_text}
              </pre>
            </CardContent>
          </Card>

          {/* Detail panels: Top 3, Top per team, Improving, Falling */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <DetailCard
              title="Top 3 Overall"
              icon={Trophy}
              color="amber"
              testId="card-top-overall"
              items={digest.top_overall?.map((t, i) => ({
                rank: i + 1,
                primary: t.name,
                secondary: `${t.activity_score} pts · ${t.captures_count} captures`,
                team: t.team_name,
              })) || []}
              empty="No activity today"
            />
            <DetailCard
              title="Top per Team"
              icon={Users}
              color="blue"
              testId="card-top-per-team"
              items={digest.top_per_team?.map((t) => ({
                primary: `${t.top_recruiter} — ${t.top_score} pts`,
                secondary: `${t.team_name} · Lead: ${t.leader_name}`,
              })) || []}
              empty="No team activity"
            />
            <DetailCard
              title="Improving (vs last active day)"
              icon={TrendingUp}
              color="green"
              testId="card-improving-dod"
              items={digest.improving_dod?.map((x) => ({
                primary: x.name,
                secondary: `+${x.delta} pts (vs ${x.previous_date})`,
              })) || []}
              empty="No improvers"
            />
            <DetailCard
              title="Falling (vs last active day)"
              icon={TrendingDown}
              color="red"
              testId="card-falling-dod"
              items={digest.falling_dod?.map((x) => ({
                primary: x.name,
                secondary: `${x.delta} pts (vs ${x.previous_date})`,
              })) || []}
              empty="No decliners"
            />
            <DetailCard
              title="Week-over-Week Gains"
              icon={Sparkles}
              color="teal"
              testId="card-wow-gain"
              items={digest.improving_wow?.map((x) => ({
                primary: x.name,
                secondary: `+${x.pct_change}% (${x.this_week_avg} vs ${x.last_week_avg} avg/day)`,
              })) || []}
              empty="Stable across the week"
            />
            <DetailCard
              title="Week-over-Week Drops"
              icon={TrendingDown}
              color="red"
              testId="card-wow-drop"
              items={digest.falling_wow?.map((x) => ({
                primary: x.name,
                secondary: `${x.pct_change}% (${x.this_week_avg} vs ${x.last_week_avg} avg/day)`,
              })) || []}
              empty="No major drops"
            />
          </div>

          {/* Inactive callout */}
          {(digest.inactive_recruiters?.length > 0 || digest.inactive_employers?.length > 0) && (
            <Card className="border-red-200 bg-red-50/40" data-testid="card-inactive">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2 text-red-700">
                  <AlertTriangle className="w-5 h-5" />
                  Inactive Today
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {digest.inactive_recruiters?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-red-600 mb-1.5">
                      {digest.inactive_recruiters.length} Recruiters
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {digest.inactive_recruiters.map((n) => (
                        <Badge key={n} variant="outline" className="bg-white border-red-200 text-red-700">{n}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {digest.inactive_employers?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-red-600 mb-1.5">
                      {digest.inactive_employers.length} Team Leads (low team output)
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {digest.inactive_employers.map((n) => (
                        <Badge key={n} variant="outline" className="bg-white border-red-200 text-red-700">{n}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Footer metadata */}
          <p className="text-xs text-gray-400 text-center">
            Generated {digest.generated_at ? new Date(digest.generated_at).toLocaleString() : '—'} ·
            <span className="ml-1">Date: {digest.pretty_date} ({digest.weekday})</span>
          </p>
        </>
      )}
    </div>
  );
}

function DetailCard({ title, icon: Icon, color, items, empty, testId }) {
  const ring = {
    amber: 'text-amber-600',
    blue: 'text-blue-600',
    green: 'text-emerald-600',
    red: 'text-red-600',
    teal: 'text-teal-600',
  };
  return (
    <Card data-testid={testId}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2 text-gray-700">
          <Icon className={`w-4 h-4 ${ring[color] || 'text-gray-500'}`} />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {items.length === 0 ? (
          <p className="text-sm text-gray-400 py-2">{empty}</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {items.map((it, i) => (
              <li key={i} className="py-2 flex items-center gap-3">
                {it.rank && (
                  <span className={`w-6 h-6 inline-flex items-center justify-center rounded-full text-xs font-bold ${
                    it.rank === 1 ? 'bg-amber-100 text-amber-700' :
                    it.rank === 2 ? 'bg-gray-100 text-gray-700' :
                    'bg-orange-100 text-orange-700'
                  }`}>{it.rank}</span>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{it.primary}</p>
                  <p className="text-xs text-gray-500 truncate">{it.secondary}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
