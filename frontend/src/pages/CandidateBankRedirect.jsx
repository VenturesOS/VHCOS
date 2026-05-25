import { useEffect } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';

/**
 * Role-aware redirector for /candidate-bank?candidateId=...
 *
 * Used by the VHC Naukri Chrome Extension's "Already in Database" badge so a
 * single deep-link URL works regardless of the user's role (admin / recruiter
 * / employer). Query params (e.g. ?candidateId=xyz) are preserved.
 */
export default function CandidateBankRedirect() {
  const { user, loading } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // If not logged in, send to login with full return URL (preserves query params)
  useEffect(() => {
    if (loading) return;
    if (!user) {
      const next = encodeURIComponent(location.pathname + location.search);
      navigate(`/login?next=${next}`, { replace: true });
    }
  }, [loading, user, location, navigate]);

  if (loading || !user) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <div className="spinner" />
      </div>
    );
  }

  const role = user.role;
  const target =
    role === 'admin'    ? '/admin/candidate-bank' :
    role === 'recruiter'? '/recruiter/candidate-bank' :
    role === 'employer' ? '/employer/candidate-bank' :
                          '/login';

  return <Navigate to={`${target}${location.search}`} replace />;
}
