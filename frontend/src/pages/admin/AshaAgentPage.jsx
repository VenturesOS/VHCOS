import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Bot, RefreshCw, MessageSquare, CheckCircle2, XCircle, Clock, Headset } from 'lucide-react';
import { toast } from 'sonner';
import { ashaAPI } from '../../lib/api';
import AgentScreeningPanel from '../../components/agent/AgentScreeningPanel';

/**
 * Asha Agent — admin overview page.
 * Tabs:
 *   Overview  → live counts (qualified / not-qualified / in-progress / callback) + config chips
 *   Sessions  → full transcript board (reuses AgentScreeningPanel across all mandates)
 *   Analytics → drop-off funnel (via AgentScreeningPanel's built-in analytics)
 */
export default function AshaAgentPage() {
  const [config, setConfig] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overview');

  const load = async () => {
    setLoading(true);
    try {
      const [cfg, sess] = await Promise.all([
        ashaAPI.getConfig().catch(() => ({ data: {} })),
        ashaAPI.listSessions({ limit: 200 }),
      ]);
      setConfig(cfg.data || {});
      setSessions(sess.data?.sessions || []);
    } catch (e) {
      toast.error('Could not load Asha data', { description: e?.response?.data?.detail });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);

  const counts = sessions.reduce(
    (acc, s) => {
      if (s.verdict === 'QUALIFIED') acc.qualified += 1;
      else if (s.verdict === 'NOT_QUALIFIED') acc.notQualified += 1;
      if (['consent', 'active', 'human_live'].includes(s.state)) acc.inProgress += 1;
      if (['callback', 'stalled', 'human_handoff'].includes(s.state)) acc.waiting += 1;
      if (s.state === 'human_live') acc.live += 1;
      return acc;
    },
    { qualified: 0, notQualified: 0, inProgress: 0, waiting: 0, live: 0 }
  );

  return (
    <div className="space-y-6" data-testid="asha-agent-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Bot className="h-6 w-6 text-emerald-600" /> Asha — Virtual Recruiter
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            End-to-end WhatsApp screening. Live conversations, slot booking, transcripts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ConfigBadges config={config} />
          <Button size="sm" variant="outline" onClick={load} data-testid="asha-refresh-btn">
            <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard icon={CheckCircle2} label="Qualified" value={counts.qualified} color="text-emerald-600" testid="stat-qualified" />
        <StatCard icon={XCircle} label="Not qualified" value={counts.notQualified} color="text-red-600" testid="stat-not-qualified" />
        <StatCard icon={MessageSquare} label="In progress" value={counts.inProgress} color="text-blue-600" testid="stat-in-progress" />
        <StatCard icon={Clock} label="Waiting / callback" value={counts.waiting} color="text-amber-600" testid="stat-waiting" />
        <StatCard icon={Headset} label="Live takeover" value={counts.live} color="text-indigo-600" testid="stat-live" />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList data-testid="asha-tabs">
          <TabsTrigger value="overview" data-testid="asha-tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="sessions" data-testid="asha-tab-sessions">Sessions ({sessions.length})</TabsTrigger>
          <TabsTrigger value="how" data-testid="asha-tab-how">How it works</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent conversations</CardTitle>
            </CardHeader>
            <CardContent>
              {sessions.length === 0 ? (
                <div className="text-center py-10 text-muted-foreground text-sm">
                  <Bot className="h-10 w-10 mx-auto mb-2 opacity-40" />
                  No Asha conversations yet. Push a candidate to Asha from any mandate to start.
                </div>
              ) : (
                <div className="divide-y">
                  {sessions.slice(0, 15).map((s) => (
                    <div key={s.id} className="flex items-center justify-between py-2.5 text-sm">
                      <div className="flex items-center gap-3 min-w-0">
                        <MessageSquare className="h-4 w-4 text-slate-400 flex-none" />
                        <span className="font-medium truncate">{s.candidate_name || s.candidate_id}</span>
                        {s.state === 'human_live' && <Badge className="bg-blue-600">LIVE</Badge>}
                      </div>
                      <div className="flex items-center gap-3 text-xs">
                        {s.score != null && (
                          <span className={s.score >= 70 ? 'text-emerald-600' : s.score >= 40 ? 'text-amber-600' : 'text-red-600'}>
                            {s.score}%
                          </span>
                        )}
                        <Badge variant={s.verdict === 'QUALIFIED' ? 'default' : 'secondary'} className="capitalize">
                          {s.verdict?.toLowerCase().replace('_', ' ') || s.state}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sessions" className="mt-4">
          {/* Reuse the full-featured board component. Without a mandateId it lists all sessions. */}
          <AgentScreeningPanel mandateId={undefined} />
        </TabsContent>

        <TabsContent value="how" className="mt-4">
          <Card>
            <CardContent className="prose prose-sm dark:prose-invert max-w-none pt-6">
              <h3 className="text-base font-semibold">Asha v2 — how she works</h3>
              <ol className="list-decimal ml-5 space-y-1.5">
                <li>Recruiter or Admin pushes a candidate to Asha from a mandate (or Bulk-Screen).</li>
                <li>Asha WhatsApps the candidate a consent message and starts a scripted screening.</li>
                <li>She verifies notice, CTC, location, and role-specific requirements.</li>
                <li>Qualified candidates are offered interview slots. Recruiter is notified.</li>
                <li>Recruiter can Take Over any live conversation from the Sessions tab.</li>
                <li>On completion Asha auto-generates a submission-note DOCX.</li>
              </ol>
              <h4 className="text-sm font-semibold mt-4">Wire Asha to a mandate</h4>
              <p className="text-sm text-muted-foreground">
                In any mandate/job-detail page, drop <code>&lt;AgentScreeningPanel mandateId=&#123;job.id&#125; /&gt;</code>{' '}
                and <code>&lt;InterviewSlotsCard mandateId=&#123;job.id&#125; /&gt;</code>. The Sessions tab above shows
                <em> all </em> mandates in one place.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color, testid }) {
  return (
    <Card data-testid={testid}>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">{label}</span>
          <Icon className={`h-4 w-4 ${color}`} />
        </div>
        <div className={`text-2xl font-bold mt-1 ${color}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

function ConfigBadges({ config }) {
  if (!config) return null;
  return (
    <div className="hidden md:flex gap-1.5">
      <Badge variant={config.enabled ? 'default' : 'secondary'} className={config.enabled ? 'bg-emerald-600' : ''}>
        {config.enabled ? 'Enabled' : 'Disabled'}
      </Badge>
      {config.dry_run && <Badge variant="outline">Dry-run</Badge>}
      <Badge variant="outline">
        {config.in_window ? 'In-window' : 'Out-of-window'}
      </Badge>
      {config.caps && (
        <Badge variant="outline">
          {config.caps.active}/{config.caps.daily} today
        </Badge>
      )}
    </div>
  );
}
