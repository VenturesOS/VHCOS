import { Suspense, lazy, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { FileText, BarChart3, Radar } from 'lucide-react';

const BlogEngineContent = lazy(() => import('./BlogEnginePage'));
const BlogAnalyticsContent = lazy(() => import('./BlogAnalyticsPage'));
const SEOMonitoringContent = lazy(() => import('./SEOMonitoringPage'));

const Loader = () => <div className="flex items-center justify-center h-32"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>;

export default function BlogTabsPage() {
  const [tab, setTab] = useState('engine');
  return (
    <div data-testid="blog-tabs-page">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="engine" className="gap-1.5 text-xs" data-testid="tab-blog-engine">
            <FileText className="w-3.5 h-3.5" /> Blog Engine
          </TabsTrigger>
          <TabsTrigger value="analytics" className="gap-1.5 text-xs" data-testid="tab-blog-analytics">
            <BarChart3 className="w-3.5 h-3.5" /> Analytics
          </TabsTrigger>
          <TabsTrigger value="seo" className="gap-1.5 text-xs" data-testid="tab-seo-monitoring">
            <Radar className="w-3.5 h-3.5" /> SEO
          </TabsTrigger>
        </TabsList>
        <TabsContent value="engine"><Suspense fallback={<Loader />}><BlogEngineContent /></Suspense></TabsContent>
        <TabsContent value="analytics"><Suspense fallback={<Loader />}><BlogAnalyticsContent /></Suspense></TabsContent>
        <TabsContent value="seo"><Suspense fallback={<Loader />}><SEOMonitoringContent /></Suspense></TabsContent>
      </Tabs>
    </div>
  );
}
