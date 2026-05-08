import { CheckCircle } from 'lucide-react';

export default function TrustBadge({ variant = 'default' }) {
  const badges = [
    { label: 'DPDP 2023 Compliant', key: 'dpdp' },
    { label: 'Data Protected', key: 'data' },
    { label: 'Consent Verified', key: 'consent' },
  ];

  if (variant === 'inline') {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-slate-400" data-testid="trust-badge-inline">
        <CheckCircle className="w-3 h-3 text-emerald-500" />
        <span>DPDP 2023 Compliant</span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3" data-testid="trust-badges">
      {badges.map((b) => (
        <div key={b.key} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-50 border border-slate-100" data-testid={`trust-badge-${b.key}`}>
          <CheckCircle className="w-3 h-3 text-emerald-500" />
          <span className="text-[11px] font-medium text-slate-500">{b.label}</span>
        </div>
      ))}
    </div>
  );
}
