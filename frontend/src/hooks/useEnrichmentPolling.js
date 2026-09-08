import { useEffect } from 'react';
import { candidateBankAPI } from '../lib/api';

export const useEnrichmentPolling = (candidates, setCandidates) => {
  const pendingIds = candidates.filter(c => ['pending', 'processing', 'queued'].includes(c.enrichment_status))
    .slice(0, 5).map(c => c.id).join(',');
  useEffect(() => {
    if (!pendingIds) return;
    let stopped = false;
    let busy = false;
    let attempts = 0;
    const timer = setInterval(async () => {
      if (busy || attempts >= 25) return;
      busy = true;
      attempts += 1;
      try {
        const results = await Promise.allSettled(pendingIds.split(',').map(id => candidateBankAPI.getById(id)));
        if (stopped) return;
        const updates = new Map(results.filter(r => r.status === 'fulfilled')
          .map(r => [r.value.data.id, r.value.data]));
        setCandidates(previous => previous.map(candidate => updates.has(candidate.id)
          ? { ...candidate, ...updates.get(candidate.id) } : candidate));
      } finally { busy = false; }
    }, 12000);
    return () => { stopped = true; clearInterval(timer); };
  }, [pendingIds, setCandidates]);
};