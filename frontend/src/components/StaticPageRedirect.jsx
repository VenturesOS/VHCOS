import { useEffect, useState } from 'react';
import { Helmet } from 'react-helmet-async';

export default function StaticPageRedirect({ page }) {
  const [showLink, setShowLink] = useState(false);
  const target = '/website/' + page + window.location.hash;

  useEffect(() => {
    window.location.replace('/website/' + page + window.location.hash);
    const timer = setTimeout(() => setShowLink(true), 2000);
    return () => clearTimeout(timer);
  }, [page]);

  return (
    <>
      <Helmet>
        <meta httpEquiv="refresh" content={'0;url=' + target} />
      </Helmet>
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342] mx-auto mb-4"></div>
          <p className="text-slate-600">Loading...</p>
          {showLink && (
            <a href={target} className="mt-4 inline-block text-[#7CB342] underline">
              Click here if not redirected
            </a>
          )}
        </div>
      </div>
    </>
  );
}
