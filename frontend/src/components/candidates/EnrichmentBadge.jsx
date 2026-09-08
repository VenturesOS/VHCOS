import { Clock3, CircleAlert } from 'lucide-react';

const SOURCES = {
  nvidia_nemotron_550b: { label: 'N', title: 'NVIDIA Nemotron 550B', style: 'bg-slate-900 text-emerald-400 border-emerald-500' },
  openai_gpt_oss_120b: { label: 'GO', title: 'GPT-OSS 120B via NVIDIA', style: 'bg-amber-100 text-amber-800 border-amber-300' },
  nvidia_nemotron_super_120b: { label: 'NS', title: 'NVIDIA Nemotron Super 120B', style: 'bg-cyan-50 text-cyan-800 border-cyan-300' },
  nvidia_mistral_nemotron: { label: 'MN', title: 'NVIDIA Mistral Nemotron', style: 'bg-indigo-50 text-indigo-800 border-indigo-300' },
  emergent_haiku_4_5: { label: 'EC', title: 'Emergent Claude Haiku 4.5', style: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  claude_haiku_4_5_emergent: { label: 'EC', title: 'Emergent Claude Haiku 4.5', style: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  regex_zero_cost: { label: 'RX', title: 'Rule-based extraction, not AI', style: 'bg-slate-100 text-slate-600 border-slate-300' },
  regex_hybrid: { label: 'RX', title: 'Rule-based extraction', style: 'bg-slate-100 text-slate-600 border-slate-300' },
};

export const EnrichmentBadge = ({ candidate, isAdmin = false }) => {
  if (!isAdmin) return null;
  const status = candidate.enrichment_status;
  const source = candidate.ai_enrichment_source;
  const failed = status === 'failed' || (!status && ['all_failed', 'exception'].includes(source));
  const pending = ['pending', 'processing', 'queued'].includes(status);
  const badge = failed
    ? { label: 'Failed', title: 'AI enrichment failed; captured profile is saved', style: 'bg-red-50 text-red-700 border-red-200', Icon: CircleAlert }
    : pending
      ? { label: 'Pending', title: 'AI enrichment is pending', style: 'bg-amber-50 text-amber-800 border-amber-200', Icon: Clock3 }
      : SOURCES[source] || (status === 'enriched' || source
        ? { label: 'AI', title: `Previously enriched (${source || 'legacy provider'})`, style: 'bg-slate-100 text-slate-700 border-slate-300' }
        : { label: 'Not enriched', title: 'No completed AI enrichment recorded', style: 'bg-slate-50 text-slate-600 border-slate-200' });
  const Icon = badge.Icon;
  return <span className={`inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-bold ${badge.style}`}
    title={badge.title} aria-label={badge.title} data-testid={`ai-source-badge-${candidate.id}`}>
    {Icon && <Icon className="h-3 w-3" aria-hidden="true" />}{badge.label}
  </span>;
};