import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { CalendarPlus, Trash2, Loader2, Clock } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import api from '@/lib/api';

/**
 * InterviewSlotsCard — slot pool manager for a mandate. Mount next to
 * AgentScreeningPanel: <InterviewSlotsCard mandateId={job.id} />
 * Asha offers open slots automatically to QUALIFIED candidates.
 */
export default function InterviewSlotsCard({ mandateId }) {
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ start: '', capacity: 1, mode: 'phone', details: '' });
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/agent/slots', { params: { mandate_id: mandateId } });
      setSlots(res.data.slots || []);
    } catch {
      toast({ title: 'Could not load slots', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [mandateId, toast]);

  useEffect(() => { load(); }, [load]);

  const addSlot = async () => {
    if (!form.start) return;
    setBusy(true);
    try {
      await api.post('/agent/slots', {
        mandate_id: mandateId,
        start: new Date(form.start).toISOString(),
        capacity: Number(form.capacity) || 1,
        mode: form.mode,
        details: form.details || null,
      });
      setForm({ start: '', capacity: 1, mode: 'phone', details: '' });
      toast({ title: 'Slot added', description: 'Asha will offer it to qualified candidates.' });
      load();
    } catch (e) {
      toast({ title: 'Could not add slot', description: e?.response?.data?.detail, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const removeSlot = async (id) => {
    try {
      await api.delete(`/agent/slots/${id}`);
      load();
    } catch (e) {
      toast({ title: 'Could not delete', description: e?.response?.data?.detail, variant: 'destructive' });
    }
  };

  const fmt = (iso) =>
    new Date(iso).toLocaleString('en-IN', {
      weekday: 'short', day: '2-digit', month: 'short',
      hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata',
    }) + ' IST';

  return (
    <Card>
      <CardHeader className="py-3">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Clock className="h-4 w-4 text-emerald-600" /> Interview slots
          <Badge variant="secondary">{slots.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="datetime-local"
            value={form.start}
            onChange={(e) => setForm({ ...form, start: e.target.value })}
            className="col-span-2 text-sm"
          />
          <Input
            type="number" min="1" placeholder="Capacity"
            value={form.capacity}
            onChange={(e) => setForm({ ...form, capacity: e.target.value })}
            className="text-sm"
          />
          <select
            value={form.mode}
            onChange={(e) => setForm({ ...form, mode: e.target.value })}
            className="h-9 rounded-md border bg-background px-2 text-sm"
          >
            <option value="phone">Phone</option>
            <option value="video">Video</option>
            <option value="office">In person</option>
          </select>
          <Input
            placeholder="Details (link / address) — optional"
            value={form.details}
            onChange={(e) => setForm({ ...form, details: e.target.value })}
            className="col-span-2 text-sm"
          />
          <Button onClick={addSlot} disabled={busy || !form.start} size="sm" className="col-span-2 gap-1.5">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CalendarPlus className="h-3.5 w-3.5" />}
            Add slot
          </Button>
        </div>

        <div className="space-y-1.5">
          {loading && <p className="text-xs text-muted-foreground text-center py-2">Loading…</p>}
          {!loading && slots.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-2">
              No slots — Asha will close qualified chats with "recruiter will call".
            </p>
          )}
          {slots.map((s) => (
            <div key={s.id} className="flex items-center justify-between rounded-lg border px-3 py-1.5 text-sm">
              <div>
                <span className="font-medium">{fmt(s.start)}</span>
                <span className="text-xs text-muted-foreground ml-2">
                  {s.mode} · {s.booked_count || 0}/{s.capacity} booked
                </span>
              </div>
              <Button variant="ghost" size="icon" className="h-7 w-7"
                      onClick={() => removeSlot(s.id)} disabled={(s.booked_count || 0) > 0}>
                <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
