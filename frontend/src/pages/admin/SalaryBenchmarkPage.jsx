import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import {
  IndianRupee, TrendingUp, Users, Search, MapPin, Briefcase,
  Loader2, BarChart3, ArrowUpRight, ArrowDownRight, Building2,
} from 'lucide-react';

const envUrl = process.env.REACT_APP_BACKEND_URL;
const API_BASE = envUrl ? `${envUrl.replace(/\/+$/, '')}/api` : '/api';
function getToken() { return localStorage.getItem('vhc_token'); }

async function fetchJSON(url) {
  const res = await fetch(`${API_BASE}${url}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

const COLORS = ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#ea580c', '#4f46e5', '#0d9488', '#be185d'];

function fmtSalary(v) {
  if (!v || v === 0) return '0';
  if (v >= 10000000) return `${(v / 10000000).toFixed(1)}Cr`;
  if (v >= 100000) return `${(v / 100000).toFixed(1)}L`;
  if (v >= 1000) return `${(v / 1000).toFixed(0)}K`;
  return v.toLocaleString();
}

function StatCard({ icon: Icon, label, value, sub, color, bg }) {
  return (
    <Card className="border-slate-200" data-testid={`stat-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
            <Icon className={`w-4 h-4 ${color}`} />
          </div>
          <span className="text-xs text-slate-500 font-medium">{label}</span>
        </div>
        <p className="text-2xl font-bold text-slate-900">{value}</p>
        {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

export default function SalaryBenchmarkPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [skills, setSkills] = useState('');
  const [location, setLocation] = useState('');
  const [designation, setDesignation] = useState('');
  const [company, setCompany] = useState('');
  const [industry, setIndustry] = useState('');
  const [expMin, setExpMin] = useState('');
  const [expMax, setExpMax] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [activeField, setActiveField] = useState(null);
  const [sugQuery, setSugQuery] = useState('');

  const fetchBenchmark = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (skills) params.set('skills', skills);
      if (location) params.set('location', location);
      if (designation) params.set('designation', designation);
      if (company) params.set('company', company);
      if (industry) params.set('industry', industry);
      if (expMin) params.set('experience_min', expMin);
      if (expMax) params.set('experience_max', expMax);
      const result = await fetchJSON(`/analytics/salary-benchmark?${params.toString()}`);
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [skills, location, designation, company, industry, expMin, expMax]);

  useEffect(() => { fetchBenchmark(); }, [fetchBenchmark]);

  const fetchSuggestions = async (field, q) => {
    try {
      const params = new URLSearchParams({ field, q: q || '' });
      const result = await fetchJSON(`/analytics/salary-benchmark/suggestions?${params.toString()}`);
      setSuggestions(result.suggestions || []);
    } catch {
      setSuggestions([]);
    }
  };

  const handleSuggestionClick = (field, value) => {
    if (field === 'skills') {
      const current = skills ? skills.split(',').map(s => s.trim()) : [];
      if (!current.includes(value)) setSkills([...current, value].join(', '));
    } else if (field === 'location') setLocation(value);
    else if (field === 'designation') setDesignation(value);
    else if (field === 'company') setCompany(value);
    else if (field === 'industry') setIndustry(value);
    setSuggestions([]);
    setActiveField(null);
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div className="bg-white border border-slate-200 rounded-lg shadow-lg p-3 text-sm">
        <p className="font-medium text-slate-700 mb-1">{label}</p>
        {payload.map((p, i) => (
          <p key={i} className="text-slate-600">
            {p.name}: <span className="font-semibold">{p.name.includes('salary') || p.name.includes('Salary') ? fmtSalary(p.value) : p.value}</span>
          </p>
        ))}
      </div>
    );
  };

  return (
    <div className="space-y-6" data-testid="salary-benchmark-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-[#2563eb]" />
            Salary Benchmarking
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Analyze compensation trends across your talent pool</p>
        </div>
      </div>

      {/* Filters */}
      <Card className="border-slate-200" data-testid="benchmark-filters">
        <CardContent className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-3">
            <div className="relative">
              <label className="text-xs font-medium text-slate-500 mb-1 block">Skills</label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
                <Input
                  placeholder="e.g. Java, Python"
                  value={skills}
                  onChange={(e) => { setSkills(e.target.value); fetchSuggestions('skills', e.target.value); setActiveField('skills'); }}
                  onFocus={() => { fetchSuggestions('skills', skills); setActiveField('skills'); }}
                  onBlur={() => setTimeout(() => setActiveField(null), 200)}
                  className="pl-8 h-9 text-sm"
                  data-testid="filter-skills"
                />
              </div>
              {activeField === 'skills' && suggestions.length > 0 && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  {suggestions.map((s, i) => (
                    <button key={i} className="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 flex justify-between"
                      onMouseDown={() => handleSuggestionClick('skills', s.value)}>
                      <span>{s.value}</span>
                      <span className="text-slate-400 text-xs">{s.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="relative">
              <label className="text-xs font-medium text-slate-500 mb-1 block">Location</label>
              <div className="relative">
                <MapPin className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
                <Input
                  placeholder="e.g. Bangalore"
                  value={location}
                  onChange={(e) => { setLocation(e.target.value); fetchSuggestions('location', e.target.value); setActiveField('location'); }}
                  onFocus={() => { fetchSuggestions('location', location); setActiveField('location'); }}
                  onBlur={() => setTimeout(() => setActiveField(null), 200)}
                  className="pl-8 h-9 text-sm"
                  data-testid="filter-location"
                />
              </div>
              {activeField === 'location' && suggestions.length > 0 && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  {suggestions.map((s, i) => (
                    <button key={i} className="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 flex justify-between"
                      onMouseDown={() => handleSuggestionClick('location', s.value)}>
                      <span>{s.value}</span>
                      <span className="text-slate-400 text-xs">{s.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="relative">
              <label className="text-xs font-medium text-slate-500 mb-1 block">Designation</label>
              <div className="relative">
                <Briefcase className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
                <Input
                  placeholder="e.g. Manager"
                  value={designation}
                  onChange={(e) => { setDesignation(e.target.value); fetchSuggestions('designation', e.target.value); setActiveField('designation'); }}
                  onFocus={() => { fetchSuggestions('designation', designation); setActiveField('designation'); }}
                  onBlur={() => setTimeout(() => setActiveField(null), 200)}
                  className="pl-8 h-9 text-sm"
                  data-testid="filter-designation"
                />
              </div>
              {activeField === 'designation' && suggestions.length > 0 && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  {suggestions.map((s, i) => (
                    <button key={i} className="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 flex justify-between"
                      onMouseDown={() => handleSuggestionClick('designation', s.value)}>
                      <span>{s.value}</span>
                      <span className="text-slate-400 text-xs">{s.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="relative">
              <label className="text-xs font-medium text-slate-500 mb-1 block">Company</label>
              <div className="relative">
                <Building2 className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
                <Input
                  placeholder="e.g. TCS, Infosys"
                  value={company}
                  onChange={(e) => { setCompany(e.target.value); fetchSuggestions('company', e.target.value); setActiveField('company'); }}
                  onFocus={() => { fetchSuggestions('company', company); setActiveField('company'); }}
                  onBlur={() => setTimeout(() => setActiveField(null), 200)}
                  className="pl-8 h-9 text-sm"
                  data-testid="filter-company"
                />
              </div>
              {activeField === 'company' && suggestions.length > 0 && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  {suggestions.map((s, i) => (
                    <button key={i} className="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 flex justify-between"
                      onMouseDown={() => handleSuggestionClick('company', s.value)}>
                      <span>{s.value}</span>
                      <span className="text-slate-400 text-xs">{s.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="relative">
              <label className="text-xs font-medium text-slate-500 mb-1 block">Industry</label>
              <div className="relative">
                <TrendingUp className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
                <Input
                  placeholder="e.g. IT Services"
                  value={industry}
                  onChange={(e) => { setIndustry(e.target.value); fetchSuggestions('industry', e.target.value); setActiveField('industry'); }}
                  onFocus={() => { fetchSuggestions('industry', industry); setActiveField('industry'); }}
                  onBlur={() => setTimeout(() => setActiveField(null), 200)}
                  className="pl-8 h-9 text-sm"
                  data-testid="filter-industry"
                />
              </div>
              {activeField === 'industry' && suggestions.length > 0 && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  {suggestions.map((s, i) => (
                    <button key={i} className="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 flex justify-between"
                      onMouseDown={() => handleSuggestionClick('industry', s.value)}>
                      <span>{s.value}</span>
                      <span className="text-slate-400 text-xs">{s.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="flex gap-2">
              <div className="flex-1">
                <label className="text-xs font-medium text-slate-500 mb-1 block">Min Exp</label>
                <Input type="number" placeholder="0" value={expMin} onChange={(e) => setExpMin(e.target.value)}
                  className="h-9 text-sm" data-testid="filter-exp-min" />
              </div>
              <div className="flex-1">
                <label className="text-xs font-medium text-slate-500 mb-1 block">Max Exp</label>
                <Input type="number" placeholder="30" value={expMax} onChange={(e) => setExpMax(e.target.value)}
                  className="h-9 text-sm" data-testid="filter-exp-max" />
              </div>
            </div>

            <div className="flex items-end">
              <Button onClick={fetchBenchmark} disabled={loading} className="w-full h-9 bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="apply-filters-btn">
                {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Search className="w-4 h-4 mr-1.5" />}
                Analyze
              </Button>
            </div>
          </div>

          {/* Active filters */}
          {(skills || location || designation || company || industry || expMin || expMax) && (
            <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-slate-100">
              {skills && skills.split(',').map((s, i) => s.trim() && (
                <Badge key={i} variant="secondary" className="text-xs bg-blue-50 text-blue-700">{s.trim()}</Badge>
              ))}
              {location && <Badge variant="secondary" className="text-xs bg-green-50 text-green-700"><MapPin className="w-3 h-3 mr-1" />{location}</Badge>}
              {designation && <Badge variant="secondary" className="text-xs bg-purple-50 text-purple-700"><Briefcase className="w-3 h-3 mr-1" />{designation}</Badge>}
              {company && <Badge variant="secondary" className="text-xs bg-indigo-50 text-indigo-700"><Building2 className="w-3 h-3 mr-1" />{company}</Badge>}
              {industry && <Badge variant="secondary" className="text-xs bg-cyan-50 text-cyan-700"><TrendingUp className="w-3 h-3 mr-1" />{industry}</Badge>}
              {(expMin || expMax) && <Badge variant="secondary" className="text-xs bg-amber-50 text-amber-700">{expMin || 0}-{expMax || '30+'}yrs</Badge>}
              <button className="text-xs text-slate-400 hover:text-slate-600 ml-1" data-testid="clear-filters-btn"
                onClick={() => { setSkills(''); setLocation(''); setDesignation(''); setCompany(''); setIndustry(''); setExpMin(''); setExpMax(''); }}>
                Clear all
              </button>
            </div>
          )}
        </CardContent>
      </Card>

      {loading && (
        <div className="flex items-center justify-center py-16" data-testid="benchmark-loading">
          <Loader2 className="w-6 h-6 animate-spin text-[#2563eb] mr-2" />
          <span className="text-slate-500">Analyzing salary data...</span>
        </div>
      )}

      {!loading && data && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3" data-testid="benchmark-kpis">
            <StatCard icon={Users} label="Sample Size" value={data.count.toLocaleString()} color="text-blue-600" bg="bg-blue-50" />
            <StatCard icon={IndianRupee} label="Average" value={fmtSalary(data.avg_salary)} color="text-emerald-600" bg="bg-emerald-50" />
            <StatCard icon={TrendingUp} label="Median" value={fmtSalary(data.median_salary)} color="text-violet-600" bg="bg-violet-50" />
            <StatCard icon={ArrowDownRight} label="25th %ile" value={fmtSalary(data.p25)} color="text-amber-600" bg="bg-amber-50" />
            <StatCard icon={ArrowUpRight} label="75th %ile" value={fmtSalary(data.p75)} color="text-sky-600" bg="bg-sky-50" />
            <StatCard icon={ArrowDownRight} label="Min" value={fmtSalary(data.min_salary)} color="text-slate-600" bg="bg-slate-100" />
            <StatCard icon={ArrowUpRight} label="Max" value={fmtSalary(data.max_salary)} color="text-rose-600" bg="bg-rose-50" />
          </div>

          {data.count === 0 ? (
            <Card className="border-slate-200">
              <CardContent className="py-12 text-center">
                <Search className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                <p className="text-lg font-medium text-slate-700">No matching candidates</p>
                <p className="text-sm text-slate-500 mt-1">Try broader filters to see salary data.</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Salary Distribution */}
              {data.salary_ranges?.length > 0 && (
                <Card className="border-slate-200" data-testid="salary-distribution-chart">
                  <CardContent className="p-4">
                    <h3 className="text-sm font-semibold text-slate-700 mb-3">Salary Distribution</h3>
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={data.salary_ranges}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} />
                        <Tooltip content={<CustomTooltip />} />
                        <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} name="Candidates" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {/* By Experience */}
              {data.by_experience?.length > 0 && (
                <Card className="border-slate-200" data-testid="experience-salary-chart">
                  <CardContent className="p-4">
                    <h3 className="text-sm font-semibold text-slate-700 mb-3">Avg Salary by Experience</h3>
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={data.by_experience}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} tickFormatter={fmtSalary} />
                        <Tooltip content={<CustomTooltip />} />
                        <Bar dataKey="avg_salary" fill="#059669" radius={[4, 4, 0, 0]} name="Avg Salary" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {/* By Location */}
              {data.by_location?.length > 0 && (
                <Card className="border-slate-200" data-testid="location-salary-chart">
                  <CardContent className="p-4">
                    <h3 className="text-sm font-semibold text-slate-700 mb-3">Avg Salary by Location</h3>
                    <div className="space-y-2">
                      {data.by_location.map((loc, i) => (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-xs text-slate-600 w-28 truncate" title={loc.location}>{loc.location}</span>
                          <div className="flex-1 bg-slate-100 rounded-full h-6 relative overflow-hidden">
                            <div
                              className="h-full rounded-full flex items-center px-2"
                              style={{
                                width: `${Math.max(10, (loc.avg_salary / (data.by_location[0]?.avg_salary || 1)) * 100)}%`,
                                backgroundColor: COLORS[i % COLORS.length],
                              }}
                            >
                              <span className="text-xs text-white font-medium whitespace-nowrap">{fmtSalary(loc.avg_salary)}</span>
                            </div>
                          </div>
                          <span className="text-xs text-slate-400 w-12 text-right">{loc.count}</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* By Designation */}
              {data.by_designation?.length > 0 && (
                <Card className="border-slate-200" data-testid="designation-salary-chart">
                  <CardContent className="p-4">
                    <h3 className="text-sm font-semibold text-slate-700 mb-3">Top Designations by Salary</h3>
                    <div className="space-y-2">
                      {data.by_designation.map((d, i) => (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-xs text-slate-600 w-36 truncate" title={d.designation}>{d.designation}</span>
                          <div className="flex-1 bg-slate-100 rounded-full h-6 relative overflow-hidden">
                            <div
                              className="h-full rounded-full flex items-center px-2"
                              style={{
                                width: `${Math.max(10, (d.avg_salary / (data.by_designation[0]?.avg_salary || 1)) * 100)}%`,
                                backgroundColor: COLORS[i % COLORS.length],
                              }}
                            >
                              <span className="text-xs text-white font-medium whitespace-nowrap">{fmtSalary(d.avg_salary)}</span>
                            </div>
                          </div>
                          <span className="text-xs text-slate-400 w-12 text-right">{d.count}</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Top Skills */}
              {data.top_skills?.length > 0 && (
                <Card className="border-slate-200 lg:col-span-2" data-testid="top-skills-chart">
                  <CardContent className="p-4">
                    <h3 className="text-sm font-semibold text-slate-700 mb-3">Top Skills in This Segment</h3>
                    <div className="flex flex-wrap gap-2">
                      {data.top_skills.map((s, i) => (
                        <Badge key={i} variant="outline" className="text-xs cursor-pointer hover:bg-blue-50"
                          onClick={() => { setSkills(s.skill); fetchBenchmark(); }}>
                          {s.skill} <span className="text-slate-400 ml-1">({s.count})</span>
                        </Badge>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
