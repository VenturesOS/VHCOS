import { Helmet } from 'react-helmet-async';

/**
 * SEOHead — single source of truth for per-route <head> tags.
 *
 * Usage (public page):
 *   <SEOHead
 *     title="Plant Head Jobs in Pune | VHC Careers"
 *     description="Live plant head and manufacturing leadership openings..."
 *     path="/jobs/abc-123"
 *     jsonLd={jobPostingLD(job)}
 *   />
 *
 * Usage (private page — dashboards, login, admin):
 *   <SEOHead title="Candidate Bank" noindex />
 *
 * Rules baked in:
 *  - Title is auto-suffixed with the brand unless it already contains it.
 *  - Canonical is always absolute (SITE_URL + path).
 *  - `noindex` flips robots to noindex,nofollow for that route only —
 *    the base index.html now defaults to index,follow (2026-07 fix).
 *  - `jsonLd` accepts one object or an array of objects; each is emitted
 *    as its own <script type="application/ld+json"> block.
 */

const SITE_URL = 'https://ventureshrd.com';
const SITE_NAME = 'Ventures HRD Centre Pvt Ltd';
const DEFAULT_DESCRIPTION =
  "India's industrial recruitment and executive search specialists since 1999. " +
  'Manufacturing, automotive, aerospace and OEM hiring.';
const DEFAULT_OG_IMAGE = `${SITE_URL}/og-default.png`;

export default function SEOHead({
  title,
  description = DEFAULT_DESCRIPTION,
  path = '',
  image = DEFAULT_OG_IMAGE,
  type = 'website',
  noindex = false,
  jsonLd = null,
  publishedTime = null,
  modifiedTime = null,
}) {
  const fullTitle = !title
    ? `${SITE_NAME} | Industrial Recruitment Experts, India`
    : title.includes('Ventures HRD') || title.includes('VHC')
      ? title
      : `${title} | Ventures HRD Centre`;

  const canonical = `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`;
  const ldBlocks = jsonLd ? (Array.isArray(jsonLd) ? jsonLd : [jsonLd]) : [];

  return (
    <Helmet>
      <title>{fullTitle}</title>
      <meta name="description" content={description} />
      <link rel="canonical" href={canonical} />

      <meta
        name="robots"
        content={noindex ? 'noindex, nofollow' : 'index, follow, max-snippet:-1, max-image-preview:large'}
      />

      {/* Open Graph */}
      <meta property="og:type" content={type} />
      <meta property="og:site_name" content={SITE_NAME} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={canonical} />
      <meta property="og:image" content={image} />
      <meta property="og:locale" content="en_IN" />
      {type === 'article' && publishedTime && (
        <meta property="article:published_time" content={publishedTime} />
      )}
      {type === 'article' && modifiedTime && (
        <meta property="article:modified_time" content={modifiedTime} />
      )}

      {/* Twitter / X */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={image} />

      {/* Structured data */}
      {ldBlocks.map((block, i) => (
        <script key={i} type="application/ld+json">
          {JSON.stringify(block)}
        </script>
      ))}
    </Helmet>
  );
}
