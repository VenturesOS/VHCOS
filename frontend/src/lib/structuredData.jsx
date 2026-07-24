/**
 * structuredData.js — schema.org JSON-LD builders for SEOHead.
 *
 * The highest-value one for a recruitment firm is jobPostingLD():
 * valid JobPosting markup makes every shareable-link job eligible for
 * the Google for Jobs panel — a free, high-intent distribution channel
 * that currently receives none of VHC's listings because PublicJobPage
 * ships no structured data at all.
 *
 * All builders return plain objects; pass them to <SEOHead jsonLd={...} />.
 */

const SITE_URL = 'https://ventureshrd.com';

export const organizationLD = () => ({
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'Ventures HRD Centre Pvt Ltd',
  alternateName: 'VHC Talent Advisory',
  url: SITE_URL,
  logo: `${SITE_URL}/website/images/logo.png`,
  foundingDate: '1999',
  address: {
    '@type': 'PostalAddress',
    streetAddress: 'D-12/79,80 Second Floor, Sector-8, Rohini',
    addressLocality: 'New Delhi',
    postalCode: '110085',
    addressCountry: 'IN',
  },
  email: 'admin@vhc.in',
  areaServed: ['IN', 'US', 'GB', 'AE'],
});

/**
 * Google for Jobs — required fields: title, description (HTML ok),
 * datePosted, hiringOrganization, jobLocation. validThrough and
 * baseSalary strongly improve eligibility and ranking.
 *
 * @param {object} job — the job document from /api/public/jobs/{id}
 */
export const jobPostingLD = (job) => {
  if (!job) return null;

  const ld = {
    '@context': 'https://schema.org',
    '@type': 'JobPosting',
    title: job.title,
    description: job.description_html || job.description || job.title,
    datePosted: (job.created_at || '').slice(0, 10),
    employmentType: mapEmploymentType(job.employment_type),
    hiringOrganization: {
      '@type': 'Organization',
      name: job.company_confidential
        ? 'Confidential — via Ventures HRD Centre'
        : job.company_name || 'Ventures HRD Centre Pvt Ltd',
      sameAs: SITE_URL,
    },
    jobLocation: {
      '@type': 'Place',
      address: {
        '@type': 'PostalAddress',
        addressLocality: job.location || job.city || 'India',
        addressCountry: 'IN',
      },
    },
    directApply: true,
    url: `${SITE_URL}/jobs/${job.id}`,
  };

  // Expiry — Google strongly prefers validThrough; fall back to 60 days.
  if (job.expires_at) {
    ld.validThrough = job.expires_at;
  } else if (job.created_at) {
    const d = new Date(job.created_at);
    d.setDate(d.getDate() + 60);
    ld.validThrough = d.toISOString();
  }

  // Salary — only emit when real numbers exist (fake ranges hurt trust).
  const min = job.salary_min ?? job.ctc_min;
  const max = job.salary_max ?? job.ctc_max;
  if (min || max) {
    ld.baseSalary = {
      '@type': 'MonetaryAmount',
      currency: 'INR',
      value: {
        '@type': 'QuantitativeValue',
        minValue: min || undefined,
        maxValue: max || undefined,
        unitText: 'YEAR',
      },
    };
  }

  if (job.remote === true || /remote/i.test(job.location || '')) {
    ld.jobLocationType = 'TELECOMMUTE';
    ld.applicantLocationRequirements = { '@type': 'Country', name: 'India' };
  }

  return ld;
};

/** Blog articles on /career-insights and /industrial-hiring-insights. */
export const articleLD = (post, pathPrefix) => ({
  '@context': 'https://schema.org',
  '@type': 'Article',
  headline: post.title,
  description: post.excerpt || post.meta_description || '',
  image: post.cover_image || `${SITE_URL}/og-default.png`,
  datePublished: post.published_at,
  dateModified: post.updated_at || post.published_at,
  author: {
    '@type': 'Organization',
    name: 'Ventures HRD Centre Pvt Ltd',
    url: SITE_URL,
  },
  publisher: {
    '@type': 'Organization',
    name: 'Ventures HRD Centre Pvt Ltd',
    logo: { '@type': 'ImageObject', url: `${SITE_URL}/website/images/logo.png` },
  },
  mainEntityOfPage: `${SITE_URL}/${pathPrefix}/${post.slug}`,
});

/** Breadcrumbs — items: [{ name, path }] */
export const breadcrumbLD = (items) => ({
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: items.map((item, i) => ({
    '@type': 'ListItem',
    position: i + 1,
    name: item.name,
    item: `${SITE_URL}${item.path}`,
  })),
});

/** FAQ rich results — faqs: [{ q, a }] (plain text answers). */
export const faqLD = (faqs) => ({
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: faqs.map(({ q, a }) => ({
    '@type': 'Question',
    name: q,
    acceptedAnswer: { '@type': 'Answer', text: a },
  })),
});

function mapEmploymentType(t) {
  const m = {
    'full-time': 'FULL_TIME', full_time: 'FULL_TIME', fulltime: 'FULL_TIME',
    'part-time': 'PART_TIME', part_time: 'PART_TIME',
    contract: 'CONTRACTOR', contractor: 'CONTRACTOR',
    temporary: 'TEMPORARY', internship: 'INTERN', intern: 'INTERN',
  };
  return m[(t || '').toLowerCase()] || 'FULL_TIME';
}
