import { Cpu, RefreshCw } from 'lucide-react';
import { Button } from '../ui/button';

export const LLMProviderStatus = ({ providers = [], refreshing, onRefresh }) => (
  <section className="border border-slate-200 rounded-lg p-5" data-testid="llm-provider-status">
    <div className="flex items-center justify-between gap-3 mb-5">
      <h2 className="text-sm font-semibold flex items-center gap-2"><Cpu className="w-4 h-4" />Provider chain</h2>
      <Button size="sm" variant="outline" onClick={onRefresh} disabled={refreshing} data-testid="refresh-provider-status">
        <RefreshCw className={`h-3.5 w-3.5 mr-1 ${refreshing ? 'animate-spin' : ''}`} />Refresh
      </Button>
    </div>
    <ol className="space-y-4">
      {providers.map((provider, index) => <li key={provider.id} className="flex items-center justify-between gap-3 text-sm flex-wrap" data-testid={`provider-${provider.id}`}>
        <span>{index + 1}. {provider.name}</span>
        <span className={provider.configured ? 'text-green-700' : 'text-red-700'} data-testid={`provider-${provider.id}-configuration`}>
          {provider.configured ? 'Configured' : 'Not configured'}
        </span>
      </li>)}
    </ol>
  </section>
);