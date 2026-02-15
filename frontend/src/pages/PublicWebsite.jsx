import { useEffect } from 'react';

/**
 * PublicWebsiteRedirect Component
 * Redirects to the static website homepage at the clean root URL.
 * The craco devServer middleware serves the static HTML at /.
 */
export default function PublicWebsiteRedirect() {
  useEffect(() => {
    if (window.location.pathname !== '/') {
      window.location.replace('/');
    }
  }, []);

  return (
    <div className="min-h-screen bg-white flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342] mx-auto mb-4"></div>
        <p className="text-slate-600">Loading Ventures HRD...</p>
      </div>
    </div>
  );
}
