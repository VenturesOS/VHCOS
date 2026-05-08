import { Suspense, lazy, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { Upload, History } from 'lucide-react';

const BulkImportContent = lazy(() => import('./BulkImportPage'));
const ImportHistoryContent = lazy(() => import('./ImportHistoryPage'));

const Loader = () => <div className="flex items-center justify-center h-32"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>;

export default function NaukriImportTabsPage() {
  const [tab, setTab] = useState('import');
  return (
    <div data-testid="naukri-import-tabs-page">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="import" className="gap-1.5 text-xs" data-testid="tab-naukri-import">
            <Upload className="w-3.5 h-3.5" /> Naukri Import
          </TabsTrigger>
          <TabsTrigger value="history" className="gap-1.5 text-xs" data-testid="tab-import-history">
            <History className="w-3.5 h-3.5" /> Import History
          </TabsTrigger>
        </TabsList>
        <TabsContent value="import"><Suspense fallback={<Loader />}><BulkImportContent /></Suspense></TabsContent>
        <TabsContent value="history"><Suspense fallback={<Loader />}><ImportHistoryContent /></Suspense></TabsContent>
      </Tabs>
    </div>
  );
}
