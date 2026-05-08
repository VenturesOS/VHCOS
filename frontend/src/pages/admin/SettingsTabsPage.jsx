import { Suspense, lazy, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { Settings, Download } from 'lucide-react';

const SettingsContent = lazy(() => import('./SettingsPage'));
const ResourcesContent = lazy(() => import('./AdminResourcesPage'));

const Loader = () => <div className="flex items-center justify-center h-32"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>;

export default function SettingsTabsPage() {
  const [tab, setTab] = useState('settings');
  return (
    <div data-testid="settings-tabs-page">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="settings" className="gap-1.5 text-xs" data-testid="tab-settings">
            <Settings className="w-3.5 h-3.5" /> Settings
          </TabsTrigger>
          <TabsTrigger value="resources" className="gap-1.5 text-xs" data-testid="tab-resources">
            <Download className="w-3.5 h-3.5" /> Resources
          </TabsTrigger>
        </TabsList>
        <TabsContent value="settings"><Suspense fallback={<Loader />}><SettingsContent /></Suspense></TabsContent>
        <TabsContent value="resources"><Suspense fallback={<Loader />}><ResourcesContent /></Suspense></TabsContent>
      </Tabs>
    </div>
  );
}
