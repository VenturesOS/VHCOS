import { Suspense, lazy, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { Activity, Bug, Cpu, FileSearch, Puzzle } from 'lucide-react';

const SystemHealthContent = lazy(() => import('./SystemHealthPage'));
const BugReportsContent = lazy(() => import('./BugReportsPage'));
const AIMonitoringContent = lazy(() => import('./AIMonitoringPage'));
const ExtractionAuditContent = lazy(() => import('./ExtractionAuditPage'));
const ExtensionVersionsContent = lazy(() => import('./ExtensionVersionsPage'));

const Loader = () => <div className="flex items-center justify-center h-32"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>;

export default function SystemHealthTabsPage() {
  const [tab, setTab] = useState('ai');
  return (
    <div data-testid="system-health-tabs-page">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-4 flex-wrap h-auto">
          <TabsTrigger value="ai" className="gap-1.5 text-xs" data-testid="tab-ai-monitoring">
            <Cpu className="w-3.5 h-3.5" /> AI Monitoring
          </TabsTrigger>
          <TabsTrigger value="audit" className="gap-1.5 text-xs" data-testid="tab-extraction-audit">
            <FileSearch className="w-3.5 h-3.5" /> Extraction Audit
          </TabsTrigger>
          <TabsTrigger value="extension" className="gap-1.5 text-xs" data-testid="tab-extension-versions">
            <Puzzle className="w-3.5 h-3.5" /> Extension Versions
          </TabsTrigger>
          <TabsTrigger value="health" className="gap-1.5 text-xs" data-testid="tab-system-health">
            <Activity className="w-3.5 h-3.5" /> System Health
          </TabsTrigger>
          <TabsTrigger value="bugs" className="gap-1.5 text-xs" data-testid="tab-bug-reports">
            <Bug className="w-3.5 h-3.5" /> Bug Reports
          </TabsTrigger>
        </TabsList>
        <TabsContent value="ai"><Suspense fallback={<Loader />}><AIMonitoringContent /></Suspense></TabsContent>
        <TabsContent value="audit"><Suspense fallback={<Loader />}><ExtractionAuditContent /></Suspense></TabsContent>
        <TabsContent value="extension"><Suspense fallback={<Loader />}><ExtensionVersionsContent /></Suspense></TabsContent>
        <TabsContent value="health"><Suspense fallback={<Loader />}><SystemHealthContent /></Suspense></TabsContent>
        <TabsContent value="bugs"><Suspense fallback={<Loader />}><BugReportsContent /></Suspense></TabsContent>
      </Tabs>
    </div>
  );
}
