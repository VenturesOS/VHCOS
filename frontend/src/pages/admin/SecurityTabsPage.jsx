import { Suspense, lazy, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { ShieldCheck, Shield } from 'lucide-react';

const SecurityAuditContent = lazy(() => import('./SecurityAuditDashboard'));
const ComplianceContent = lazy(() => import('./ComplianceDashboardPage'));

const Loader = () => <div className="flex items-center justify-center h-32"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>;

export default function SecurityTabsPage() {
  const [tab, setTab] = useState('audit');
  return (
    <div data-testid="security-tabs-page">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="audit" className="gap-1.5 text-xs" data-testid="tab-security-audit">
            <ShieldCheck className="w-3.5 h-3.5" /> Security Audit
          </TabsTrigger>
          <TabsTrigger value="compliance" className="gap-1.5 text-xs" data-testid="tab-compliance">
            <Shield className="w-3.5 h-3.5" /> Compliance
          </TabsTrigger>
        </TabsList>
        <TabsContent value="audit"><Suspense fallback={<Loader />}><SecurityAuditContent /></Suspense></TabsContent>
        <TabsContent value="compliance"><Suspense fallback={<Loader />}><ComplianceContent /></Suspense></TabsContent>
      </Tabs>
    </div>
  );
}
