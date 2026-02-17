import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import DOMPurify from 'dompurify';
import { pillarPageAPI } from '../../lib/api';
import PillarHero from '../../components/PillarPage/PillarHero';
import PillarContent from '../../components/PillarPage/PillarContent';
import PillarSidebar from '../../components/PillarPage/PillarSidebar';
import { Loader2 } from 'lucide-react';

const VALID_SLUGS = new Set(['industrial-recruitment', 'hr-consulting-services', 'career-insights']);
const BASE_URL = 'https://ventureshrd.com';

function PillarNotFound() {
  return (
    <div className="min-h-screen bg-white flex items-center justify-center" data-testid="pillar-404">
      <div className="text-center px-6">
        <p className="text-6xl font-extrabold text-gray-200 mb-4">404</p>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Page Not Found</h1>
        <p className="text-gray-500 mb-8">The page you are looking for does not exist or has been moved.</p>
        <a href="/website/Index.html" className="inline-block bg-gray-900 text-white px-6 py-3 rounded-lg font-semibold text-sm hover:bg-gray-800 transition-colors" data-testid="pillar-404-home">Back to Home</a>
      </div>
    </div>
  );
}

export default function PillarPage() {
  const { slug } = useParams();
  const [page, setPage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!slug || !VALID_SLUGS.has(slug)) {
      setNotFound(true);
      setLoading(false);
      return;
    }
    setLoading(true);
    pillarPageAPI.getBySlug(slug)
      .then(r => setPage(r.data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center" data-testid="pillar-loading">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (notFound || !page) return <PillarNotFound />;

  const canonicalUrl = `${BASE_URL}/${page.slug}`;
  const sanitizedContent = DOMPurify.sanitize(page.content || '');

  return (
    <div className="min-h-screen bg-white" data-testid="pillar-page">
      <Helmet>
        <title>{page.meta_title}</title>
        <meta name="description" content={page.meta_description} />
        <link rel="canonical" href={canonicalUrl} />
        <meta property="og:title" content={page.meta_title} />
        <meta property="og:description" content={page.meta_description} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:type" content="article" />
      </Helmet>

      {/* Header */}
      <header style={{ background: '#111827', padding: '16px 24px' }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <a href="/website/Index.html" style={{ display: 'flex', alignItems: 'center', gap: '12px', textDecoration: 'none' }}>
            <img src="/website/assests/logo.svg" alt="VHC" style={{ height: '36px' }} onError={e => { e.target.style.display = 'none'; }} />
            <span style={{ color: 'white', fontWeight: 700, fontSize: '18px' }}>Ventures HRD Centre</span>
          </a>
          <a href="/website/contact.html" data-testid="pillar-header-cta" style={{ background: '#9acd32', color: '#111827', padding: '10px 24px', borderRadius: '8px', textDecoration: 'none', fontWeight: 600, fontSize: '14px' }}>Contact Us</a>
        </div>
      </header>

      <PillarHero hero={page.hero} />

      {/* Main Content + Sidebar */}
      <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '60px 24px', display: 'grid', gridTemplateColumns: '1fr', gap: '48px' }} className="lg:!grid-cols-[1fr_320px]" data-testid="pillar-body">
        <PillarContent html={sanitizedContent} faq={page.faq} />
        <PillarSidebar slug={page.slug} />
      </div>

      {/* Bottom CTA */}
      {page.hero?.cta_text && (
        <section style={{ background: '#111827', padding: '64px 24px', textAlign: 'center' }} data-testid="pillar-bottom-cta">
          <div style={{ maxWidth: '700px', margin: '0 auto' }}>
            <h2 style={{ color: 'white', fontSize: 'clamp(22px, 4vw, 32px)', fontWeight: 700, marginBottom: '16px', lineHeight: 1.3 }}>Ready to Transform Your Workforce Strategy?</h2>
            <p style={{ color: '#9ca3af', fontSize: '16px', lineHeight: 1.7, marginBottom: '32px' }}>Connect with our experts for a confidential consultation on your talent acquisition needs.</p>
            <a href={page.hero.cta_link || '/website/contact.html'} data-testid="pillar-bottom-cta-btn" style={{ display: 'inline-block', background: '#9acd32', color: '#111827', padding: '14px 36px', borderRadius: '8px', fontWeight: 700, fontSize: '15px', textDecoration: 'none', transition: 'opacity 0.2s' }}>
              {page.hero.cta_text}
            </a>
          </div>
        </section>
      )}

      {/* Footer */}
      <footer style={{ background: '#111827', borderTop: '1px solid #1f2937', color: 'white', padding: '40px 24px', textAlign: 'center' }}>
        <p style={{ opacity: 0.6, fontSize: '14px' }}>&copy; {new Date().getFullYear()} Ventures HRD Centre Pvt Ltd. All rights reserved.</p>
      </footer>
    </div>
  );
}
