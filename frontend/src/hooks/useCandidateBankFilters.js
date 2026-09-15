import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

// Spec 5.11 (2026-09-08): Source, Has Resume, Mandate, AI Source and Smart
// Tags filters were removed from the visible panel by user request. Their
// keys were removed here too so no stale URL params can re-open them.
const FILTER_KEYS = [
  'phone', 'email', 'location', 'company', 'noticePeriod',
  'minExperience', 'maxExperience', 'minSalary', 'maxSalary',
  'contactHidden', 'capturedAfter', 'capturedBefore',
];

const EMPTY_FILTERS = Object.fromEntries(FILTER_KEYS.map(k => [k, '']));

function useDebounce(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/**
 * Shared hook for Candidate Bank filter state with URL persistence.
 * Filters are synced to URL search params so they survive refresh & back-navigation.
 */
export function useCandidateBankFilters() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Read initial state from URL params
  const initFromUrl = useCallback((key, fallback = '') => searchParams.get(key) || fallback, [searchParams]);

  const [search, setSearch] = useState(() => initFromUrl('search'));
  const [skills, setSkills] = useState(() => initFromUrl('skills'));
  const [filtersOpen, setFiltersOpen] = useState(() => {
    // auto-open if any filter is set in URL
    return FILTER_KEYS.some(k => searchParams.get(k));
  });
  const [currentPage, setCurrentPage] = useState(() => {
    const p = parseInt(searchParams.get('page'));
    return p > 0 ? p : 1;
  });
  const [filters, setFilters] = useState(() =>
    Object.fromEntries(FILTER_KEYS.map(k => [k, initFromUrl(k)]))
  );

  const debouncedSearch = useDebounce(search);
  const debouncedSkills = useDebounce(skills);
  // Spec 5.11 (2026-09-08): headline count and list must reload whenever ANY
  // filter changes, not just search/skills. This debounced JSON key drives
  // the fresh-load effect on each Bank page without firing on every keystroke.
  const filtersKey = useMemo(() => JSON.stringify(filters), [filters]);
  const debouncedFiltersKey = useDebounce(filtersKey, 400);

  const activeFilterCount = useMemo(
    () => Object.values(filters).filter(v => v !== '').length + (skills ? 1 : 0),
    [filters, skills]
  );

  // Sync state → URL params (debounced values only)
  useEffect(() => {
    const params = new URLSearchParams();
    if (debouncedSearch) params.set('search', debouncedSearch);
    if (debouncedSkills) params.set('skills', debouncedSkills);
    if (currentPage > 1) params.set('page', String(currentPage));
    FILTER_KEYS.forEach(k => {
      if (filters[k]) params.set(k, filters[k]);
    });
    setSearchParams(params, { replace: true });
  }, [debouncedSearch, debouncedSkills, currentPage, filters, setSearchParams]);

  const updateFilter = useCallback((key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({ ...EMPTY_FILTERS });
    setSkills('');
    setSearch('');
    setCurrentPage(1);
  }, []);

  const setDatePreset = useCallback((preset) => {
    const now = new Date();
    let after = '';
    if (preset === 'today') after = now.toISOString().split('T')[0];
    else if (preset === 'week') { const d = new Date(now); d.setDate(d.getDate() - 7); after = d.toISOString().split('T')[0]; }
    else if (preset === 'month') { const d = new Date(now); d.setMonth(d.getMonth() - 1); after = d.toISOString().split('T')[0]; }
    setFilters(prev => ({ ...prev, capturedAfter: after, capturedBefore: '' }));
  }, []);

  /** Build the query params object for the API call */
  const getApiParams = useCallback((page) => {
    const params = { page: page || currentPage, limit: 50 };
    if (debouncedSearch) params.search = debouncedSearch;
    if (debouncedSkills) params.skills = debouncedSkills;
    if (filters.phone) params.phone = filters.phone;
    if (filters.email) params.email = filters.email;
    if (filters.location) params.location = filters.location;
    if (filters.company) params.company = filters.company;
    if (filters.noticePeriod) params.notice_period = filters.noticePeriod;
    if (filters.minExperience !== '') params.min_experience = parseInt(filters.minExperience);
    if (filters.maxExperience !== '') params.max_experience = parseInt(filters.maxExperience);
    if (filters.minSalary !== '') params.min_salary = parseInt(filters.minSalary);
    if (filters.maxSalary !== '') params.max_salary = parseInt(filters.maxSalary);
    if (filters.capturedAfter) params.captured_after = filters.capturedAfter;
    if (filters.capturedBefore) params.captured_before = filters.capturedBefore;
    if (filters.contactHidden) params.contact_hidden = filters.contactHidden;
    return params;
  }, [currentPage, debouncedSearch, debouncedSkills, filters]);

  const applyFilters = useCallback(() => {
    setCurrentPage(1);
  }, []);

  return {
    search, setSearch,
    skills, setSkills,
    filters, updateFilter,
    filtersOpen, setFiltersOpen,
    currentPage, setCurrentPage,
    debouncedSearch, debouncedSkills, debouncedFiltersKey,
    activeFilterCount,
    clearFilters, setDatePreset, applyFilters,
    getApiParams,
  };
}
