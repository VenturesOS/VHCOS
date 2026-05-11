import { useState, useEffect, useCallback } from 'react';
import { teamDigestAPI } from '../../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Button } from '../../ui/button';
import { Badge } from '../../ui/badge';
import { toast } from 'sonner';
import {
  MessageCircle, Copy, RefreshCw, Send, Trophy,
  TrendingUp, TrendingDown, AlertTriangle, Loader2,
  ChevronDown, ChevronUp,
} from 'lucide-react';

/**
 * Compact Daily Digest widget for the Admin Dashboard.
 * - Shows quick stats + collapsed WhatsApp preview
 * - "Copy" + "Open WhatsApp Web" actions inline
 * - Expand button reveals the full message
 */
export default function DailyDigestWidget() {
  const [digest, setDigest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await teamDigestAPI.today();
      setDigest(res.data);
    } catch (e) {
      // Lazy build inside the GET handler can take a while or fail; show stub
      setDigest(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const res = await teamDigestAPI.regenerate();
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
      toast.success('Copied — paste into WhatsApp group');
    } catch (e) {
      toast.error('Clipboard access blocked by browser');
    }
  };

  const handleSendWhatsApp = () => {
    if (!digest?.whatsapp_text) return;
    const encoded = encodeURIComponent(digest.whatsapp_text);
    window.open(`https://web.whatsapp.com/send?text=${encoded}`, '_blank', 'noopener');
  };

  if (loading) {
    return (
      <Card className="border-slate-200/80" data-testid="daily-digest-widget">
        <CardContent className="py-8 text-center text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 mx-auto animate-spin mb-2" />
          Loading daily digest…
        </CardContent>
      </Card>
    );
  }

  if (!digest) {
    return (
      <Card className="border-emerald-200 bg-emerald-50/40" data-testid="daily-digest-widget">
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2 text-emerald-700">
            <MessageCircle className="w-4 h-4" /> Daily Team Digest
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-sm text-slate-500 mb-3">
            No digest available yet for today. Auto-generates at 18:00 IST, or click below to compute now.
          </p>
          <Button
            size="sm"
            onClick={handleRegenerate}
            disabled={regenerating}
            data-testid="digest-widget-generate-btn"
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            {regenerating
              ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
              : <RefreshCw className="w-4 h-4 mr-1.5" />}
            Generate Now
          </Button>
        </CardContent>
      </Card>
    );
  }

  const top1 = digest.top_overall?.[0];
  const top2 = digest.top_overall?.[1];
  const top3 = digest.top_overall?.[2];
  const improver = digest.improving_dod?.[0];
  const decliner = digest.falling_dod?.[0];

  return (
    <Card className="border-emerald-200/70 bg-gradient-to-br from-emerald-50/30 to-white" data-testid="daily-digest-widget">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between flex-wrap gap-2">
          <CardTitle className="text-base flex items-center gap-2 text-slate-900">
            <MessageCircle className="w-4 h-4 text-emerald-600" />
            Daily Team Digest
            <Badge variant="outline" className="ml-1 text-[10px] bg-white border-emerald-200 text-emerald-700">
              {digest.pretty_date}
            </Badge>
          </CardTitle>
          <div className="flex items-center gap-1.5 flex-wrap">
            <Button
              size="sm"
              variant="outline"
              onClick={handleRegenerate}
              disabled={regenerating}
              data-testid="digest-widget-refresh-btn"
              className="h-7 px-2 text-xs"
            >
              {regenerating
                ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                : <RefreshCw className="w-3.5 h-3.5 mr-1" />}
              Refresh
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleCopy}
              data-testid="digest-widget-copy-btn"
              className="h-7 px-2 text-xs"
            >
              <Copy className="w-3.5 h-3.5 mr-1" />
              Copy
            </Button>
            <Button
              size="sm"
              onClick={handleSendWhatsApp}
              data-testid="digest-widget-whatsapp-btn"
              className="h-7 px-2 text-xs bg-emerald-600 hover:bg-emerald-700"
            >
              <Send className="w-3.5 h-3.5 mr-1" />
              WhatsApp
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Quick stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <MiniStat
            icon={Trophy}
            label="Top Performer"
            value={top1?.name || '—'}
            sub={top1 ? `${top1.activity_score} pts` : 'no activity'}
            color="amber"
          />
          <MiniStat
            icon={TrendingUp}
            label="Biggest Gainer"
            value={improver?.name || '—'}
            sub={improver ? `+${improver.delta} pts` : 'no improvers'}
            color="green"
          />
          <MiniStat
            icon={TrendingDown}
            label="Biggest Drop"
            value={decliner?.name || '—'}
            sub={decliner ? `${decliner.delta} pts` : 'all steady'}
            color="red"
          />
          <MiniStat
            icon={AlertTriangle}
            label="Inactive Today"
            value={digest.inactive_recruiters?.length || 0}
            sub={`of ${digest.recruiter_count} recruiters`}
            color={(digest.inactive_recruiters?.length || 0) > 0 ? 'red' : 'green'}
          />
        </div>

        {/* Top 3 chips */}
        {digest.top_overall?.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] uppercase tracking-wider text-slate-500 font-medium">Top 3:</span>
            {[top1, top2, top3].filter(Boolean).map((t, i) => (
              <Badge
                key={`${t.user_id}-${i}`}
                variant="outline"
                className="bg-white border-slate-200 text-slate-700"
              >
                <span className="font-semibold mr-1">#{i + 1}</span>
                {t.name} · {t.activity_score} pts
              </Badge>
            ))}
          </div>
        )}

        {/* WhatsApp preview (collapsible) */}
        <div>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-emerald-700 hover:text-emerald-800 font-medium flex items-center gap-1"
            data-testid="digest-widget-toggle-preview"
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {expanded ? 'Hide WhatsApp preview' : 'Show WhatsApp preview'}
          </button>
          {expanded && (
            <pre
              className="mt-2 whitespace-pre-wrap font-mono text-[12px] leading-relaxed bg-white border border-emerald-100 rounded-md p-3 max-h-[400px] overflow-auto text-slate-800"
              data-testid="digest-widget-whatsapp-text"
            >
              {digest.whatsapp_text}
            </pre>
          )}
        </div>

        {/* Inactive recruiters preview */}
        {digest.inactive_recruiters?.length > 0 && !expanded && (
          <div className="text-[11px] text-slate-500">
            <span className="font-medium text-red-600">{digest.inactive_recruiters.length} inactive:</span>{' '}
            {digest.inactive_recruiters.slice(0, 5).join(', ')}
            {digest.inactive_recruiters.length > 5 && ` +${digest.inactive_recruiters.length - 5} more`}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MiniStat({ icon: Icon, label, value, sub, color }) {
  const colors = {
    amber: 'bg-amber-50 text-amber-700 border-amber-100',
    green: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    red: 'bg-red-50 text-red-700 border-red-100',
    gray: 'bg-slate-50 text-slate-700 border-slate-100',
  };
  return (
    <div className={`border rounded-md px-3 py-2 ${colors[color] || colors.gray}`}>
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className="w-3.5 h-3.5 opacity-70" />
        <span className="text-[10px] uppercase tracking-wider font-medium opacity-80">{label}</span>
      </div>
      <p className="text-sm font-semibold truncate">{value}</p>
      {sub && <p className="text-[11px] opacity-60 truncate">{sub}</p>}
    </div>
  );
}
