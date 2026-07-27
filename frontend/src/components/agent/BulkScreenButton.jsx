import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Bot, Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import api from '@/lib/api';

/**
 * BulkScreenButton — push a whole result set to Asha.
 * <BulkScreenButton candidateIds={selectedIds} mandateId={activeMandateId} />
 */
export default function BulkScreenButton({ candidateIds = [], mandateId, size = 'sm' }) {
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();

  const push = async () => {
    if (!mandateId || candidateIds.length === 0) return;
    setBusy(true);
    try {
      const res = await api.post('/agent/push-bulk', {
        candidate_ids: candidateIds, mandate_id: mandateId,
      });
      const { started, queued, skipped } = res.data;
      toast({
        title: `Asha: ${started} started, ${queued} queued`,
        description: skipped?.length
          ? `${skipped.length} skipped (${[...new Set(skipped.map((s) => s.reason))].join(', ')})`
          : 'All candidates accepted.',
      });
    } catch (e) {
      toast({ title: 'Bulk push failed', description: e?.response?.data?.detail, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button variant="outline" size={size} onClick={push}
            disabled={busy || !mandateId || candidateIds.length === 0}
            title={mandateId ? `Screen ${candidateIds.length} via Asha` : 'Select a mandate first'}
            className="gap-1.5">
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bot className="h-3.5 w-3.5" />}
      Screen {candidateIds.length} via Asha
    </Button>
  );
}
