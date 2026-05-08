import { Suspense, lazy, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { Activity, Rss } from 'lucide-react';

const ActivityMonitorContent = lazy(() => import('./ActivityMonitorPage'));
const ActivityFeedContent = lazy(() => import('../shared/ActivityFeedPage'));

const Loader = () => <div className="flex items-center justify-center h-32"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>;

export default function ActivityTabsPage() {
  const [tab, setTab] = useState('monitor');
  return (
    <div data-testid="activity-tabs-page">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="monitor" className="gap-1.5 text-xs" data-testid="tab-activity-monitor">
            <Activity className="w-3.5 h-3.5" /> Activity Monitor
          </TabsTrigger>
          <TabsTrigger value="feed" className="gap-1.5 text-xs" data-testid="tab-activity-feed">
            <Rss className="w-3.5 h-3.5" /> Activity Feed
          </TabsTrigger>
        </TabsList>
        <TabsContent value="monitor"><Suspense fallback={<Loader />}><ActivityMonitorContent /></Suspense></TabsContent>
        <TabsContent value="feed"><Suspense fallback={<Loader />}><ActivityFeedContent /></Suspense></TabsContent>
      </Tabs>
    </div>
  );
}
