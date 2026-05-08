import { Suspense, lazy, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { Database, UserCircle } from 'lucide-react';

const CandidateDataBankContent = lazy(() => import('./CandidateDataBankPage'));
const CandidatesContent = lazy(() => import('./CandidatesPage'));

const Loader = () => <div className="flex items-center justify-center h-32"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>;

export default function CandidateBankTabsPage() {
  const [tab, setTab] = useState('bank');
  return (
    <div data-testid="candidate-bank-tabs-page">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="bank" className="gap-1.5 text-xs" data-testid="tab-candidate-bank">
            <Database className="w-3.5 h-3.5" /> Candidate Bank
          </TabsTrigger>
          <TabsTrigger value="candidates" className="gap-1.5 text-xs" data-testid="tab-candidates">
            <UserCircle className="w-3.5 h-3.5" /> Candidates
          </TabsTrigger>
        </TabsList>
        <TabsContent value="bank"><Suspense fallback={<Loader />}><CandidateDataBankContent /></Suspense></TabsContent>
        <TabsContent value="candidates"><Suspense fallback={<Loader />}><CandidatesContent /></Suspense></TabsContent>
      </Tabs>
    </div>
  );
}
