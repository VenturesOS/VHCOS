import { useEffect } from 'react';

/**
 * PublicWebsiteRedirect Component
 * 
 * Performs a hard redirect to the static website
 * This bypasses React Router to serve static HTML files from /public/website/
 */
export default function PublicWebsiteRedirect() {
  useEffect(() => {
    // Check if we're already on a static HTML page (prevent redirect loop)
    if (!window.location.pathname.endsWith('.html')) {
      // Redirect to the static Index.html
      window.location.replace('/website/Index.html');
    }
  }, []);

  // Show a brief loading state while redirecting
  return (
    <div className="min-h-screen bg-white flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342] mx-auto mb-4"></div>
        <p className="text-slate-600">Loading Ventures HRD...</p>
      </div>
    </div>
  );
}
