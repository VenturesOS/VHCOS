import { Suspense, lazy, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { Clock, CalendarDays, BarChart3, Settings } from 'lucide-react';

const AttendanceContent = lazy(() => import('./AdminAttendancePage'));
const LeaveContent = lazy(() => import('./AdminLeaveManagementPage'));
const InsightsContent = lazy(() => import('./AttendanceInsightsPage'));
const SettingsContent = lazy(() => import('./AttendanceSettingsPage'));

const Loader = () => <div className="flex items-center justify-center h-32"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>;

export default function AttendanceTabsPage() {
  const [tab, setTab] = useState('attendance');
  return (
    <div data-testid="attendance-tabs-page">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="attendance" className="gap-1.5 text-xs" data-testid="tab-attendance">
            <Clock className="w-3.5 h-3.5" /> Attendance
          </TabsTrigger>
          <TabsTrigger value="leaves" className="gap-1.5 text-xs" data-testid="tab-leaves">
            <CalendarDays className="w-3.5 h-3.5" /> Leave Management
          </TabsTrigger>
          <TabsTrigger value="insights" className="gap-1.5 text-xs" data-testid="tab-insights">
            <BarChart3 className="w-3.5 h-3.5" /> Insights
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-1.5 text-xs" data-testid="tab-att-settings">
            <Settings className="w-3.5 h-3.5" /> Settings
          </TabsTrigger>
        </TabsList>
        <TabsContent value="attendance"><Suspense fallback={<Loader />}><AttendanceContent /></Suspense></TabsContent>
        <TabsContent value="leaves"><Suspense fallback={<Loader />}><LeaveContent /></Suspense></TabsContent>
        <TabsContent value="insights"><Suspense fallback={<Loader />}><InsightsContent /></Suspense></TabsContent>
        <TabsContent value="settings"><Suspense fallback={<Loader />}><SettingsContent /></Suspense></TabsContent>
      </Tabs>
    </div>
  );
}
