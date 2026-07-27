import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Bot, Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import api from '@/lib/api';

/**
 * "Screen via Asha" — drop next to existing candidate row/detail actions.
 * <ScreenWithAshaButton candidateId={c.id} mandateId={activeMandateId} />
 * Disabled (with tooltip-style title) until a mandate is selected.
 */
export default function ScreenWithAshaButton({ candidateId, mandateId, size = 'sm' }) {
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();

  const push = async () => {
    if (!mandateId) return;
    setBusy(true);
    try {
      const res = await api.post('/agent/push', { candidate_id: candidateId, mandate_id: mandateId });
      toast({
        title: res.data.mode === 'started' ? 'Asha is on it 🤖' : 'Queued for Asha',
        description:
          res.data.mode === 'started'
            ? 'Screening conversation started on WhatsApp.'
            : res.data.note,
      });
    } catch (e) {
      toast({
        title: 'Could not start screening',
        description: e?.response?.data?.detail || 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button
      variant="outline"
      size={size}
      onClick={push}
      disabled={busy || !mandateId}
      title={mandateId ? 'Send to Asha for WhatsApp screening' : 'Select a mandate first'}
      className="gap-1.5"
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bot className="h-3.5 w-3.5" />}
      Screen via Asha
    </Button>
  );
}
