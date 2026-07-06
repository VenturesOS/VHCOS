import { Outlet, Navigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth';
import { Sidebar } from './Sidebar';
import { Toaster } from '../ui/sonner';
import EnvironmentBadge from '../shared/EnvironmentBadge';
import ExtensionUpdateBanner from '../shared/ExtensionUpdateBanner';
import CommandPalette from '../shared/CommandPalette';
import SEOHead from '../shared/SEOHead';

export const DashboardLayout = ({ allowedRoles }) => {
  const { user, loading, isAuthenticated } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC] dark:bg-slate-950">
        <div className="spinner" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user?.role)) {
    // Redirect to appropriate dashboard
    return <Navigate to={`/${user?.role}`} replace />;
  }

  const showBadge = ['admin', 'recruiter', 'employer', 'accounts'].includes(user?.role);

  return (
    <div className="min-h-screen bg-[#F8FAFC] dark:bg-slate-950">
      {/* All authenticated dashboards are private — noindex per SEO fix (2026-07). */}
      <SEOHead title="VHC Talent OS" noindex />
      {showBadge && <EnvironmentBadge />}
      <Sidebar />
      <main className={`lg:pl-64 min-h-screen ${showBadge ? 'pt-6' : ''}`}>
        <div className="px-4 pb-6 pt-16 lg:px-8 lg:pb-8 lg:pt-8" style={{ paddingBottom: 'calc(1.5rem + env(safe-area-inset-bottom, 0px))' }}>
          <ExtensionUpdateBanner />
          <Outlet />
        </div>
      </main>
      {/* Global ⌘K / Ctrl+K launcher — role-aware nav + live candidate lookup. */}
      <CommandPalette />
      <Toaster position="top-right" />
    </div>
  );
};

export default DashboardLayout;
