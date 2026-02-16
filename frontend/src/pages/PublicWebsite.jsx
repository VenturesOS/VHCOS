import { useEffect } from 'react';

/**
 * PublicWebsiteRedirect Component
 * 
 * In development: craco devServer middleware serves the static homepage at /
 * directly, so this component never renders.
 * 
 * In production: Falls back to redirecting to the static HTML file.
 */
export default function PublicWebsiteRedirect() {
  useEffect(() => {
    window.location.replace('/website/Index.html');
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
