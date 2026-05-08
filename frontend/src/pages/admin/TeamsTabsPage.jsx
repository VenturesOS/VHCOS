import { Suspense, lazy, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { UsersRound, Network } from 'lucide-react';

const TeamsContent = lazy(() => import('./TeamsPage'));
const HierarchyContent = lazy(() => import('./HierarchyPage'));

const Loader = () => <div className="flex items-center justify-center h-32"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>;

export default function TeamsTabsPage() {
  const [tab, setTab] = useState('teams');
  return (
    <div data-testid="teams-tabs-page">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="teams" className="gap-1.5 text-xs" data-testid="tab-teams">
            <UsersRound className="w-3.5 h-3.5" /> Teams
          </TabsTrigger>
          <TabsTrigger value="hierarchy" className="gap-1.5 text-xs" data-testid="tab-hierarchy">
            <Network className="w-3.5 h-3.5" /> Hierarchy
          </TabsTrigger>
        </TabsList>
        <TabsContent value="teams"><Suspense fallback={<Loader />}><TeamsContent /></Suspense></TabsContent>
        <TabsContent value="hierarchy"><Suspense fallback={<Loader />}><HierarchyContent /></Suspense></TabsContent>
      </Tabs>
    </div>
  );
}
