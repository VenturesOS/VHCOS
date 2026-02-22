import { Outlet, Navigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth';
import { Sidebar } from './Sidebar';
import { Toaster } from '../ui/sonner';
import EnvironmentBadge from '../shared/EnvironmentBadge';

export const DashboardLayout = ({ allowedRoles }) => {
  const { user, loading, isAuthenticated } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC]">
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

  const showBadge = ['admin', 'recruiter', 'employer'].includes(user?.role);

  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      {showBadge && <EnvironmentBadge />}
      <Sidebar />
      <main className={`lg:pl-64 min-h-screen ${showBadge ? 'pt-6' : ''}`}>
        <div className="px-4 pb-6 pt-16 lg:px-8 lg:pb-8 lg:pt-8">
          <Outlet />
        </div>
      </main>
      <Toaster position="top-right" />
    </div>
  );
};
};

export default DashboardLayout;
