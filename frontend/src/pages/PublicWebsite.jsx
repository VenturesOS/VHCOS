import { useEffect, useState } from 'react';
import { Helmet } from 'react-helmet-async';

/**
 * PublicWebsiteRedirect Component
 * 
 * In development: craco devServer middleware serves the static homepage at /
 * directly, so this component never renders.
 * 
 * In production: Multiple fallback redirects to the static HTML homepage:
 *   1. Immediate JS redirect via window.location.replace
 *   2. <meta http-equiv="refresh"> as HTML-level fallback
 *   3. Visible clickable link after 2s timeout as last resort
 */
export default function PublicWebsiteRedirect() {
  const [showLink, setShowLink] = useState(false);

  useEffect(() => {
    window.location.replace('/website/Index.html');
    const timer = setTimeout(() => setShowLink(true), 2000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <>
      <Helmet>
        <meta httpEquiv="refresh" content="0;url=/website/Index.html" />
        <link rel="canonical" href="/website/Index.html" />
      </Helmet>
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342] mx-auto mb-4"></div>
          <p className="text-slate-600">Loading Ventures HRD...</p>
          {showLink && (
            <a
              href="/website/Index.html"
              className="mt-4 inline-block text-[#7CB342] underline"
              data-testid="homepage-fallback-link"
            >
              Click here if not redirected
            </a>
          )}
          <noscript>
            <meta httpEquiv="refresh" content="0;url=/website/Index.html" />
            <p>Redirecting... <a href="/website/Index.html">Click here</a></p>
          </noscript>
        </div>
      </div>
    </>
  );
}
