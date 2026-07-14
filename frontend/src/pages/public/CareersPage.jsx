import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import SEOHead from '../../components/shared/SEOHead';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../components/ui/select';
import {
  Search, MapPin, Briefcase, Building2, Loader2, ArrowRight, X, SlidersHorizontal, Sparkles,
} from 'lucide-react';

/**
 * CareersPage — public /careers listing of live job mandates.
 *
 * Data source: GET /api/public/careers/jobs (no auth). Each card links to
 * /jobs/{id} which ships JobPosting JSON-LD.
 *
 * Design decisions:
 *   • URL-synced filters — every filter change patches the query string so the
 *     view is shareable, bookmarkable, and crawlable (Google will index
 *     `?function=Quality` as a separate landing page for that facet).
 *   • Load-more pagination — total > 24 → button that appends the next page
 *     in-place (better UX than numbered pagination for a job board).
 *   • Overlap semantics on experience filter — a "5-10 yrs" filter matches
 *     any job whose band intersects [5,10], NOT just jobs strictly inside it.
 *   • Freshness signal — jobs updated in the last 7 days get a "New" chip.
 *     This drives clicks *and* helps Google Jobs prioritize the listing.
 */

const API = import.meta.env.VITE_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '';
const PAGE_SIZE = 24;

// Predefined experience buckets — matches how recruiters actually think about
// bands, so users click one chip instead of typing min/max.
const EXP_BUCKETS = [
  { key: '0-3',   label: '0–3 yrs',  min: 0,  max: 3  },
  { key: '3-7',   label: '3–7 yrs',  min: 3,  max: 7  },
  { key: '7-15',  label: '7–15 yrs', min: 7,  max: 15 },
  { key: '15+',   label: '15+ yrs',  min: 15, max: null },
];

const titleCase = (s) =>
  !s ? s : s.replace(/\w\S*/g, (t) => t.charAt(0).toUpperCase() + t.slice(1).toLowerCase());

const isNewJob = (isoDate) => {
  if (!isoDate) return false;
  const days = (Date.now() - new Date(isoDate).getTime()) / (1000 * 60 * 60 * 24);
  return days < 7;
};

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
  const [searchParams, setSearchParams] = useSearchParams();

  // Read initial filter state from URL — makes the page shareable/deep-linkable.
  const [q, setQ] = useState(searchParams.get('q') || '');
  const [activeFn, setActiveFn] = useState(searchParams.get('function') || '');
  const [activeLoc, setActiveLoc] = useState(searchParams.get('location') || '');
  const [activeSen, setActiveSen] = useState(searchParams.get('seniority') || '');
  const [activeExp, setActiveExp] = useState(searchParams.get('exp') || '');
  const [sort, setSort] = useState(searchParams.get('sort') || 'recent');

  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [filters, setFilters] = useState({ functions: [], locations: [], seniorities: [] });
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);

  // Load facet options once. Cached at HTTP layer.
  useEffect(() => {
    axios.get(`${API}/api/public/careers/filters`)
      .then(r => setFilters(r.data || {}))
      .catch(() => {});
  }, []);

  const buildParams = useCallback((overrides = {}) => {
    const state = { q, function: activeFn, location: activeLoc, seniority: activeSen, exp: activeExp, sort, ...overrides };
    const bucket = EXP_BUCKETS.find(b => b.key === state.exp);
    const params = new URLSearchParams();
    if (state.q)          params.set('q', state.q);
    if (state.function)   params.set('function', state.function);
    if (state.location)   params.set('location', state.location);
    if (state.seniority)  params.set('seniority', state.seniority);
    if (bucket) {
      if (bucket.min !== null && bucket.min !== undefined) params.set('experience_min', bucket.min);
      if (bucket.max !== null && bucket.max !== undefined) params.set('experience_max', bucket.max);
    }
    if (state.sort && state.sort !== 'recent') params.set('sort', state.sort);
    return params;
  }, [q, activeFn, activeLoc, activeSen, activeExp, sort]);

  // Sync filters to the URL query string. Debounced to avoid a history entry
  // per keystroke while searching.
  useEffect(() => {
    const t = setTimeout(() => {
      const urlParams = new URLSearchParams();
      if (q)         urlParams.set('q', q);
      if (activeFn)  urlParams.set('function', activeFn);
      if (activeLoc) urlParams.set('location', activeLoc);
      if (activeSen) urlParams.set('seniority', activeSen);
      if (activeExp) urlParams.set('exp', activeExp);
      if (sort && sort !== 'recent') urlParams.set('sort', sort);
      setSearchParams(urlParams, { replace: true });
    }, 250);
    return () => clearTimeout(t);
  }, [q, activeFn, activeLoc, activeSen, activeExp, sort, setSearchParams]);

  // Refetch whenever the filter state changes. Resets pagination.
  useEffect(() => {
    setLoading(true);
    setSkip(0);
    const params = buildParams();
    params.set('limit', String(PAGE_SIZE));
    params.set('skip', '0');
    let cancelled = false;
    axios.get(`${API}/api/public/careers/jobs?${params.toString()}`)
      .then(r => {
        if (cancelled) return;
        setJobs(r.data?.jobs || []);
        setTotal(r.data?.total || 0);
      })
      .catch(() => { if (!cancelled) { setJobs([]); setTotal(0); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [q, activeFn, activeLoc, activeSen, activeExp, sort, buildParams]);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    const nextSkip = skip + PAGE_SIZE;
    const params = buildParams();
    params.set('limit', String(PAGE_SIZE));
    params.set('skip', String(nextSkip));
    try {
      const r = await axios.get(`${API}/api/public/careers/jobs?${params.toString()}`);
      setJobs(prev => [...prev, ...(r.data?.jobs || [])]);
      setSkip(nextSkip);
    } finally {
      setLoadingMore(false);
    }
  }, [skip, buildParams]);

  const clearAll = () => {
    setQ(''); setActiveFn(''); setActiveLoc(''); setActiveSen(''); setActiveExp(''); setSort('recent');
  };

  const activeFilters = [
    q && { key: 'q', label: `"${q}"`, clear: () => setQ('') },
    activeFn && { key: 'fn', label: activeFn, clear: () => setActiveFn('') },
    activeLoc && { key: 'loc', label: titleCase(activeLoc), clear: () => setActiveLoc('') },
    activeSen && { key: 'sen', label: activeSen, clear: () => setActiveSen('') },
    activeExp && { key: 'exp', label: EXP_BUCKETS.find(b => b.key === activeExp)?.label || activeExp, clear: () => setActiveExp('') },
  ].filter(Boolean);

  const jsonLd = useMemo(() => JSON.stringify(itemListJsonLd(jobs)), [jobs]);
  const hasMore = jobs.length < total;

  const seoTitle = useMemo(() => {
    const parts = [];
    if (activeFn)  parts.push(activeFn);
    if (activeLoc) parts.push(`in ${titleCase(activeLoc)}`);
    const suffix = parts.length ? `${parts.join(' ')} jobs — ` : 'Open roles — ';
    return `${suffix}Manufacturing & Industrial Careers | Ventures HRD Centre`;
  }, [activeFn, activeLoc]);

  const seoDesc = useMemo(() => {
    const count = total || 'live';
    const scope = activeFn ? `${activeFn} ` : '';
    const loc = activeLoc ? `in ${titleCase(activeLoc)} ` : 'across India ';
    return `Explore ${count} ${scope}open roles ${loc}in manufacturing, automotive, aerospace and OEM hiring. Plant Head, Operations, Quality, Design and Shopfloor engineering positions.`;
  }, [total, activeFn, activeLoc]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="careers-page">
      <SEOHead title={seoTitle} description={seoDesc} canonical="https://ventureshrd.com/careers" />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd }} />

      {/* Hero */}
      <header className="bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-900 text-white">
        <div className="max-w-6xl mx-auto px-6 py-14 sm:py-16">
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight">
            Open roles across India's<br className="hidden sm:block" /> industrial hiring landscape.
          </h1>
          <p className="mt-5 text-base sm:text-lg text-slate-300 max-w-2xl">
            {total > 0
              ? `${total.toLocaleString()} live mandates from manufacturing, automotive, aerospace, and OEM clients — updated the moment new roles open.`
              : 'Live mandates from manufacturing, automotive, aerospace, and OEM clients across India.'}
          </p>
        </div>
      </header>

      {/* Sticky toolbar with search + sort + mobile filter toggle */}
      <section className="border-b border-slate-200 bg-white sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-6 py-3 flex flex-wrap items-center gap-3">
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

          <div className="flex items-center gap-2 ml-auto">
            <Button
              variant="outline"
              size="sm"
              className="lg:hidden"
              onClick={() => setMobileFiltersOpen(v => !v)}
              data-testid="careers-mobile-filter-toggle"
            >
              <SlidersHorizontal className="w-4 h-4 mr-2" />
              Filters {activeFilters.length ? `(${activeFilters.length})` : ''}
            </Button>

            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger className="w-[160px] h-10" data-testid="careers-sort-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="recent">Most recent</SelectItem>
                <SelectItem value="oldest">Oldest first</SelectItem>
                <SelectItem value="title">A – Z</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Active filter chips — one-click remove */}
        {activeFilters.length > 0 && (
          <div className="max-w-6xl mx-auto px-6 pb-3 flex flex-wrap items-center gap-2" data-testid="careers-active-filters">
            <span className="text-xs uppercase tracking-wide text-slate-500 mr-1">Filters:</span>
            {activeFilters.map((f) => (
              <button
                key={f.key}
                onClick={f.clear}
                className="inline-flex items-center gap-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 px-3 py-1 text-xs font-medium hover:bg-emerald-100 transition-colors"
                data-testid={`careers-active-filter-${f.key}`}
              >
                {f.label}
                <X className="w-3 h-3" />
              </button>
            ))}
            <button
              onClick={clearAll}
              className="text-xs text-slate-500 hover:text-slate-800 underline ml-1"
              data-testid="careers-clear-all"
            >
              Clear all
            </button>
          </div>
        )}
      </section>

      {/* Main layout: sidebar filters + grid */}
      <main className="max-w-6xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-8">
        {/* Sidebar filters (desktop persistent, mobile drawer) */}
        <aside
          className={`${mobileFiltersOpen ? 'block' : 'hidden'} lg:block space-y-6`}
          data-testid="careers-filters-panel"
        >
          <FilterGroup label="Function">
            <FilterSelect
              value={activeFn}
              onChange={setActiveFn}
              placeholder="All functions"
              options={filters.functions}
              testId="careers-filter-function"
            />
          </FilterGroup>

          <FilterGroup label="Location">
            <FilterSelect
              value={activeLoc}
              onChange={setActiveLoc}
              placeholder="All locations"
              options={filters.locations.map(l => ({ value: l, label: titleCase(l) }))}
              testId="careers-filter-location"
            />
          </FilterGroup>

          <FilterGroup label="Seniority">
            <FilterSelect
              value={activeSen}
              onChange={setActiveSen}
              placeholder="All levels"
              options={filters.seniorities}
              testId="careers-filter-seniority"
            />
          </FilterGroup>

          <FilterGroup label="Experience">
            <div className="flex flex-wrap gap-2">
              {EXP_BUCKETS.map((b) => {
                const active = activeExp === b.key;
                return (
                  <button
                    key={b.key}
                    onClick={() => setActiveExp(active ? '' : b.key)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                      active
                        ? 'bg-emerald-600 text-white border-emerald-600'
                        : 'bg-white text-slate-700 border-slate-200 hover:border-emerald-500 hover:text-emerald-700'
                    }`}
                    data-testid={`careers-filter-exp-${b.key}`}
                  >
                    {b.label}
                  </button>
                );
              })}
            </div>
          </FilterGroup>
        </aside>

        {/* Job grid */}
        <div>
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
                {activeFilters.length > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-6"
                    onClick={clearAll}
                    data-testid="careers-empty-clear-btn"
                  >
                    Clear all filters
                  </Button>
                )}
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="careers-jobs-grid">
                {jobs.map((job) => <JobCard key={job.id} job={job} />)}
              </div>

              <div className="mt-8 flex flex-col items-center gap-3">
                <p className="text-sm text-slate-500">
                  Showing <span className="font-semibold text-slate-900">{jobs.length}</span> of{' '}
                  <span className="font-semibold text-slate-900">{total.toLocaleString()}</span> roles
                </p>
                {hasMore && (
                  <Button
                    variant="outline"
                    size="lg"
                    onClick={loadMore}
                    disabled={loadingMore}
                    data-testid="careers-load-more"
                  >
                    {loadingMore ? (
                      <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Loading…</>
                    ) : (
                      <>Load more roles</>
                    )}
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

// ── UI atoms (kept local to this file — used nowhere else) ─────────────────

function FilterGroup({ label, children }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">{label}</h3>
      {children}
    </div>
  );
}

function FilterSelect({ value, onChange, placeholder, options, testId }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
      data-testid={testId}
    >
      <option value="">{placeholder}</option>
      {options.map((o) => {
        const val = typeof o === 'string' ? o : o.value;
        const lbl = typeof o === 'string' ? o : o.label;
        return <option key={val} value={val}>{lbl}</option>;
      })}
    </select>
  );
}

function JobCard({ job }) {
  const location = job.location ? titleCase(job.location) : null;
  const fresh = isNewJob(job.posted_at);

  return (
    <Link
      to={`/jobs/${job.id}`}
      className="group block"
      data-testid={`careers-job-card-${job.id}`}
    >
      <Card className="h-full hover:border-emerald-500 hover:shadow-md transition-all">
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-2 mb-3">
            <h2 className="text-base font-semibold text-slate-900 leading-snug group-hover:text-emerald-700 line-clamp-2">
              {job.title}
            </h2>
            <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-emerald-500 shrink-0 mt-1" />
          </div>

          <div className="flex items-center gap-1.5 text-sm text-slate-500 mb-3">
            <Building2 className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">{job.company_display}</span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {fresh && (
              <Badge className="text-xs bg-emerald-100 text-emerald-800 border-emerald-200 hover:bg-emerald-100">
                <Sparkles className="w-3 h-3 mr-1" /> New
              </Badge>
            )}
            {location && (
              <Badge variant="secondary" className="text-xs">
                <MapPin className="w-3 h-3 mr-1" />{location}
              </Badge>
            )}
            {job.function && <Badge variant="secondary" className="text-xs">{job.function}</Badge>}
            {job.experience_range && (
              <Badge variant="secondary" className="text-xs">
                <Briefcase className="w-3 h-3 mr-1" />{job.experience_range}
              </Badge>
            )}
            {job.seniority && !fresh && (
              <Badge variant="outline" className="text-xs">{job.seniority}</Badge>
            )}
          </div>

          {job.posted_at && !fresh && (
            <p className="mt-3 text-xs text-slate-400">Updated {job.posted_at}</p>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
