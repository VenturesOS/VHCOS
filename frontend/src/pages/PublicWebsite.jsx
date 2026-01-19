import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * PublicWebsite Component
 * 
 * Serves static HTML files from /public/website/ directory
 * This is a workaround for React SPA routing to serve static HTML content
 */
export default function PublicWebsite() {
  const location = useLocation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Determine which file to load based on pathname
    let filename = 'Index.html';
    const path = location.pathname.replace('/website/', '').replace('/website', '');
    
    if (path && path !== '/') {
      filename = path.endsWith('.html') ? path : `${path}.html`;
    }

    // For the root path, redirect to Index.html
    const targetUrl = `/website/${filename}`;
    
    // Perform a full page navigation to the static HTML
    window.location.href = targetUrl;
  }, [location.pathname]);

  // Show a brief loading state while redirecting
  return (
    <div className="min-h-screen bg-white flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342] mx-auto mb-4"></div>
        <p className="text-slate-600">Loading...</p>
      </div>
    </div>
  );
}
