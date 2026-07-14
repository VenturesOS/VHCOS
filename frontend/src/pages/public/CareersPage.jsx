import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import SEOHead from '../../components/shared/SEOHead';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Search, MapPin, Briefcase, Building2, Loader2, ArrowRight } from 'lucide-react';

/**
 * CareersPage — public /careers listing of live job mandates.
 *
 * Data source: GET /api/public/careers/jobs (no auth). Each card links to
 * /jobs/{id} which already ships JobPosting JSON-LD (see PublicJobPage.jsx).
 *
 * SEO strategy:
 *   - This page carries an ItemList JSON-LD so Google can crawl the full
 *     set of live roles from a single URL (helps discovery).
 *   - Each individual /jobs/{id} URL has the full JobPosting schema and is
 *     what appears in Google Jobs search results.
 */

const API = process.env.REACT_APP_BACKEND_URL || '';

const itemListJsonLd = (jobs) => ({
  '@context': 'https://schema.org',
  '@type': 'ItemList',
  itemListElement: jobs.slice(0, 30).map((j, i) => ({
    '@type': 'ListItem',
    position: i + 1,
    url: `https://ventureshrd.com/jobs/${j.id}`,
    name: j.title,
  })),
});

export default function CareersPage() {
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [filters, setFilters] = useState({ functions: [], locations: [], seniorities: [] });
  const [activeFn, setActiveFn] = useState('');
  const [activeLoc, setActiveLoc] = useState('');

  useEffect(() => {
    axios.get(`${API}/api/public/careers/filters`)
      .then(r => setFilters(r.data || {}))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (q)         params.set('q', q);
    if (activeFn)  params.set('function', activeFn);
    if (activeLoc) params.set('location', activeLoc);
    params.set('limit', '60');

    let cancelled = false;
    axios.get(`${API}/api/public/careers/jobs?${params.toString()}`)
      .then(r => {
        if (cancelled) return;
        setJobs(r.data?.jobs || []);
        setTotal(r.data?.total || 0);
      })
      .catch(() => { if (!cancelled) setJobs([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [q, activeFn, activeLoc]);

  const jsonLd = useMemo(() => JSON.stringify(itemListJsonLd(jobs)), [jobs]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="careers-page">
      <SEOHead
        title="Open Roles — Manufacturing & Industrial Careers | Ventures HRD Centre"
        description={`Explore ${total || 'live'} open roles in manufacturing, automotive, aerospace and OEM hiring across India. Plant Head, Operations, Quality, Design and Shopfloor engineering positions.`}
        canonical="https://ventureshrd.com/careers"
      />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd }} />

      {/* Hero */}
      <header className="bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-900 text-white">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">
            Open roles across India's<br className="hidden sm:block" /> industrial hiring landscape.
          </h1>
          <p className="mt-6 text-base sm:text-lg text-slate-300 max-w-2xl">
            {total > 0
              ? `${total} live mandates from manufacturing, automotive, aerospace, and OEM clients — refreshed as new roles open.`
              : 'Live mandates from manufacturing, automotive, aerospace, and OEM clients across India.'}
          </p>
        </div>
      </header>

      {/* Toolbar */}
      <section className="border-b border-slate-200 bg-white sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[240px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              type="text"
              placeholder="Search by title, function, or seniority…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="pl-9 h-10"
              data-testid="careers-search-input"
            />
          </div>

          <select
            className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
            value={activeFn}
            onChange={(e) => setActiveFn(e.target.value)}
            data-testid="careers-filter-function"
          >
            <option value="">All functions</option>
            {filters.functions.map(f => <option key={f} value={f}>{f}</option>)}
          </select>

          <select
            className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700"
            value={activeLoc}
            onChange={(e) => setActiveLoc(e.target.value)}
            data-testid="careers-filter-location"
          >
            <option value="">All locations</option>
            {filters.locations.map(l => <option key={l} value={l}>{l}</option>)}
          </select>

          {(q || activeFn || activeLoc) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setQ(''); setActiveFn(''); setActiveLoc(''); }}
              data-testid="careers-clear-filters"
            >
              Clear
            </Button>
          )}
        </div>
      </section>

      {/* Grid */}
      <main className="max-w-6xl mx-auto px-6 py-10">
        {loading ? (
          <div className="flex items-center justify-center py-24 text-slate-500">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading open roles…
          </div>
        ) : jobs.length === 0 ? (
          <Card>
            <CardContent className="py-16 text-center text-slate-500" data-testid="careers-empty-state">
              <p className="text-lg">No open roles match your search right now.</p>
              <p className="mt-1 text-sm">
                Try broadening filters, or{' '}
                <Link to="/contact" className="text-emerald-600 hover:underline">get in touch</Link> and
                we'll tell you about upcoming mandates.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="careers-jobs-grid">
            {jobs.map(job => (
              <Link
                key={job.id}
                to={`/jobs/${job.id}`}
                className="group"
                data-testid={`careers-job-card-${job.id}`}
              >
                <Card className="h-full hover:border-emerald-500 hover:shadow-md transition-all">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <h2 className="text-base font-semibold text-slate-900 leading-snug group-hover:text-emerald-700">
                        {job.title}
                      </h2>
                      <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-emerald-500 shrink-0 mt-1" />
                    </div>
                    <div className="flex items-center gap-1.5 text-sm text-slate-500 mb-3">
                      <Building2 className="w-3.5 h-3.5" />
                      <span className="truncate">{job.company_display}</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {job.location && (
                        <Badge variant="secondary" className="text-xs">
                          <MapPin className="w-3 h-3 mr-1" />{job.location}
                        </Badge>
                      )}
                      {job.function && <Badge variant="secondary" className="text-xs">{job.function}</Badge>}
                      {job.experience_range && (
                        <Badge variant="secondary" className="text-xs">
                          <Briefcase className="w-3 h-3 mr-1" />{job.experience_range}
                        </Badge>
                      )}
                    </div>
                    {job.posted_at && (
                      <p className="mt-3 text-xs text-slate-400">Updated {job.posted_at}</p>
                    )}
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
