import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Bot, RefreshCw, RotateCcw, MessageSquare, Loader2,
  Headset, Play, FileDown, BarChart3, Send,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import api from '@/lib/api';

/**
 * AgentScreeningPanel v2 — mandate/job detail tab:
 *   <AgentScreeningPanel mandateId={job.id} />
 * Columns · transcript drawer · live human takeover (pause Asha, type as
 * the recruiter, resume) · submission-note DOCX download · drop-off
 * analytics funnel.
 */

const COLUMNS = [
  { key: 'qualified', title: '✅ Qualified', filter: (s) => s.verdict === 'QUALIFIED' },
  { key: 'not_qualified', title: '❌ Not qualified', filter: (s) => s.verdict === 'NOT_QUALIFIED' },
  { key: 'in_progress', title: '💬 In progress', filter: (s) => ['consent', 'active', 'human_live'].includes(s.state) },
  { key: 'waiting', title: '⏳ Callback / Stalled', filter: (s) => ['callback', 'stalled', 'human_handoff'].includes(s.state) },
];

const scoreColor = (n) => (n >= 70 ? 'text-emerald-600' : n >= 40 ? 'text-amber-600' : 'text-red-600');

export default function AgentScreeningPanel({ mandateId }) {
  const [sessions, setSessions] = useState([]);
  const [funnel, setFunnel] = useState(null);
  const [showFunnel, setShowFunnel] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [drawerBusy, setDrawerBusy] = useState(false);
  const [takeoverText, setTakeoverText] = useState('');
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/agent/sessions', { params: { mandate_id: mandateId, limit: 200 } });
      setSessions(res.data.sessions || []);
    } catch {
      toast({ title: 'Could not load Asha sessions', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [mandateId, toast]);

  useEffect(() => {
    load();
    const t = setInterval(load, 45000);
    return () => clearInterval(t);
  }, [load]);

  const loadFunnel = async () => {
    try {
      const res = await api.get('/agent/analytics', { params: { mandate_id: mandateId } });
      setFunnel(res.data.funnel);
      setShowFunnel(true);
    } catch {
      toast({ title: 'Could not load analytics', variant: 'destructive' });
    }
  };

  const refreshSelected = async (id) => {
    const res = await api.get(`/agent/sessions/${id}`);
    setSelected(res.data.session);
  };

  const openSession = async (id) => {
    setDrawerBusy(true);
    setSelected({ id });
    try {
      await refreshSelected(id);
    } catch {
      toast({ title: 'Could not load transcript', variant: 'destructive' });
      setSelected(null);
    } finally {
      setDrawerBusy(false);
    }
  };

  const act = async (fn, okMsg) => {
    try {
      await fn();
      if (okMsg) toast({ title: okMsg });
      if (selected?.id) await refreshSelected(selected.id);
      load();
    } catch (e) {
      toast({ title: 'Action failed', description: e?.response?.data?.detail, variant: 'destructive' });
    }
  };

  const requalify = (id) => act(() => api.post(`/agent/sessions/${id}/reverse`), 'Moved to Qualified');
  const takeover = (id) => act(() => api.post(`/agent/sessions/${id}/takeover`), 'You have the mic — Asha paused');
  const resume = (id) => act(() => api.post(`/agent/sessions/${id}/resume`), 'Asha resumed');

  const sendAsHuman = async () => {
    const text = takeoverText.trim();
    if (!text || !selected?.id) return;
    setTakeoverText('');
    await act(() => api.post(`/agent/sessions/${selected.id}/send`, { text }));
  };

  const downloadNote = (id) => {
    window.open(`${api.defaults.baseURL || '/api'}/agent/sessions/${id}/submission-note`, '_blank');
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Bot className="h-4 w-4 text-emerald-600" />
          Asha screening · {sessions.length} conversation{sessions.length === 1 ? '' : 's'}
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" onClick={loadFunnel} className="gap-1.5">
            <BarChart3 className="h-3.5 w-3.5" /> Drop-off
          </Button>
          <Button variant="ghost" size="sm" onClick={load} className="gap-1.5">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      {showFunnel && funnel && (
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              Drop-off funnel · {funnel.completion_rate}% completion
              <span className="text-xs font-normal text-muted-foreground">
                {Object.entries(funnel.by_language).map(([l, n]) => `${l}:${n}`).join(' · ')}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 pt-0">
            {funnel.blocks.map((b) => {
              const max = Math.max(1, ...funnel.blocks.map((x) => x.asked));
              return (
                <div key={b.id} className="flex items-center gap-2 text-xs">
                  <span className="w-28 truncate text-muted-foreground">{b.id}</span>
                  <div className="flex-1 h-4 rounded bg-muted overflow-hidden flex">
                    <div className="bg-emerald-500/80 h-full" style={{ width: `${(b.answered / max) * 100}%` }} />
                    <div className="bg-red-400/80 h-full" style={{ width: `${(b.dropped_here / max) * 100}%` }} />
                  </div>
                  <span className="w-24 text-right text-muted-foreground">
                    {b.answered}✓ {b.dropped_here > 0 ? `· ${b.dropped_here} drop` : ''}
                  </span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {COLUMNS.map((col) => {
          const items = sessions.filter(col.filter);
          return (
            <Card key={col.key} className="min-h-[180px]">
              <CardHeader className="py-3">
                <CardTitle className="text-sm font-semibold flex items-center justify-between">
                  {col.title}
                  <Badge variant="secondary">{items.length}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pt-0">
                {items.length === 0 && (
                  <p className="text-xs text-muted-foreground py-3 text-center">Nothing here yet</p>
                )}
                {items.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => openSession(s.id)}
                    className="w-full text-left rounded-lg border bg-card px-3 py-2 hover:border-emerald-500/60 hover:shadow-sm transition"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium truncate">{s.candidate_name || s.candidate_id}</span>
                      {s.state === 'human_live' && <Headset className="h-3.5 w-3.5 text-blue-600" />}
                      {s.score != null && (
                        <span className={`text-xs font-bold ${scoreColor(s.score)}`}>{s.score}%</span>
                      )}
                    </div>
                    {s.pending?.kind === 'slot_offer' && (
                      <p className="text-[11px] text-blue-600/90 mt-0.5">📅 choosing interview slot…</p>
                    )}
                    {s.disqualifier && (
                      <p className="text-[11px] text-red-600/90 truncate mt-0.5">{s.disqualifier}</p>
                    )}
                    {s.verified?.notice_days != null && (
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        Notice {s.verified.notice_days}d
                        {s.verified.expected_lpa ? ` · Exp ${s.verified.expected_lpa} LPA` : ''}
                      </p>
                    )}
                  </button>
                ))}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Sheet open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <SheetContent className="w-full sm:max-w-md flex flex-col">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2 flex-wrap">
              <MessageSquare className="h-4 w-4 text-emerald-600" />
              {selected?.candidate_name || 'Transcript'}
              {selected?.verdict && (
                <Badge variant={selected.verdict === 'QUALIFIED' ? 'default' : 'secondary'}>
                  {selected.verdict}{selected.score != null ? ` · ${selected.score}%` : ''}
                </Badge>
              )}
              {selected?.state === 'human_live' && (
                <Badge className="bg-blue-600">LIVE — you're typing</Badge>
              )}
            </SheetTitle>
          </SheetHeader>

          {drawerBusy ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              <ScrollArea className="flex-1 pr-3 my-3">
                <div className="space-y-2">
                  {(selected?.transcript || []).map((t, i) => (
                    <div key={i} className={`flex ${t.dir === 'out' ? 'justify-start' : 'justify-end'}`}>
                      <div
                        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${
                          t.dir === 'out'
                            ? t.agent?.startsWith('human')
                              ? 'bg-blue-100 text-blue-900 rounded-tl-sm'
                              : 'bg-muted text-foreground rounded-tl-sm'
                            : 'bg-emerald-600 text-white rounded-tr-sm'
                        }`}
                      >
                        {t.text}
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>

              {selected?.verified && Object.keys(selected.verified).length > 0 && (
                <div className="rounded-lg border bg-muted/40 p-3 text-xs space-y-1 mb-2">
                  <p className="font-semibold text-foreground">Verified by Asha</p>
                  {Object.entries(selected.verified).map(([k, v]) => (
                    <p key={k} className="text-muted-foreground">
                      {k.replace(/_/g, ' ')}: <span className="text-foreground">{Array.isArray(v) ? v.join(', ') : String(v)}</span>
                    </p>
                  ))}
                </div>
              )}

              {selected?.state === 'human_live' && (
                <div className="flex gap-2 mb-2">
                  <Input
                    value={takeoverText}
                    onChange={(e) => setTakeoverText(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && sendAsHuman()}
                    placeholder="Type as recruiter…"
                    className="text-sm"
                  />
                  <Button size="icon" onClick={sendAsHuman} disabled={!takeoverText.trim()}>
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                {['consent', 'active', 'callback'].includes(selected?.state) && (
                  <Button variant="outline" size="sm" onClick={() => takeover(selected.id)} className="gap-1.5">
                    <Headset className="h-4 w-4" /> Take over
                  </Button>
                )}
                {selected?.state === 'human_live' && (
                  <Button variant="outline" size="sm" onClick={() => resume(selected.id)} className="gap-1.5">
                    <Play className="h-4 w-4" /> Resume Asha
                  </Button>
                )}
                {selected?.state === 'completed' && (
                  <Button variant="outline" size="sm" onClick={() => downloadNote(selected.id)} className="gap-1.5">
                    <FileDown className="h-4 w-4" /> Submission note
                  </Button>
                )}
                {selected?.verdict === 'NOT_QUALIFIED' && (
                  <Button size="sm" onClick={() => requalify(selected.id)} className="gap-1.5">
                    <RotateCcw className="h-4 w-4" /> Requalify
                  </Button>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
