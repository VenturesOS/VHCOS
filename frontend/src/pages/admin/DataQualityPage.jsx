import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../components/ui/dialog';
import { candidateBankAPI, statsAPI } from '../../lib/api';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import {
  ShieldCheck, AlertTriangle, Mail, Phone, Briefcase, MapPin,
  Wrench, ChevronLeft, ChevronRight, Loader2, Pencil, Check,
  ArrowLeft, BarChart3, Users, Tag, ExternalLink, Trash2, Save,
  UserPlus, X, Link2, Sparkles, TrendingUp, Award, Eye,
  ArrowUpDown, Search, Filter, ChevronDown, Cpu,
} from 'lucide-react';

const FIELD_META = {
  email:            { label: 'Email',       icon: Mail,      critical: true },
  phone:            { label: 'Phone',       icon: Phone,     critical: true },
  skills:           { label: 'Skills',      icon: Tag,       critical: false },
  current_employer: { label: 'Company',     icon: Briefcase, critical: false },
  designation:      { label: 'Designation', icon: Briefcase, critical: false },
  location:         { label: 'Location',    icon: MapPin,    critical: false },
  industry:         { label: 'Industry',    icon: BarChart3, critical: false },
};

export default function DataQualityPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeField, setActiveField] = useState(null);
  const [activeSource, setActiveSource] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [listLoading, setListLoading] = useState(false);
  const [listPage, setListPage] = useState(1);
  const [listTotal, setListTotal] = useState(0);
  const [listPages, setListPages] = useState(1);
  const [editId, setEditId] = useState(null);
  const [editValues, setEditValues] = useState({});
  const [saving, setSaving] = useState(false);

  // Tab state
  const [activeTab, setActiveTab] = useState('quality'); // 'quality' | 'team'
  const [teamStats, setTeamStats] = useState(null);
  const [teamLoading, setTeamLoading] = useState(false);
  const [expandedUser, setExpandedUser] = useState(null);
  const [teamRoleFilter, setTeamRoleFilter] = useState('all');
  const [teamSortField, setTeamSortField] = useState('score');
  const [teamSortDir, setTeamSortDir] = useState('desc');
  const [teamSearch, setTeamSearch] = useState('');

  // Failed captures state
  const [fcView, setFcView] = useState(false);
  const [fcLogs, setFcLogs] = useState([]);
  const [fcTotal, setFcTotal] = useState(0);
  const [fcUnrecovered, setFcUnrecovered] = useState(0);
  const [fcPage, setFcPage] = useState(1);
  const [fcPages, setFcPages] = useState(1);
  const [fcLoading, setFcLoading] = useState(false);
  const [fcShow, setFcShow] = useState('unrecovered');
  const [fcEditCapture, setFcEditCapture] = useState(null);
  const [fcForm, setFcForm] = useState({});
  const [fcSaving, setFcSaving] = useState(false);
  const [fcSelected, setFcSelected] = useState(new Set());
  const [classifyResult, setClassifyResult] = useState(null);
  const [classifying, setClassifying] = useState(false);

  // Regex Parser Quality — relocated from Admin Dashboard on 2026-05-01
  const [regexQuality, setRegexQuality] = useState(null);

  useEffect(() => {
    statsAPI.extractionQuality().then(r => setRegexQuality(r.data)).catch(() => {});
  }, []);

  const loadStats = useCallback(async () => {
    try {
      setLoading(true);
      const res = await candidateBankAPI.dataQualityStats();
      setStats(res.data);
    } catch { toast.error('Failed to load data quality stats'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);

  const loadTeamStats = useCallback(async () => {
    setTeamLoading(true);
    try {
      const res = await candidateBankAPI.dataQualityTeamStats();
      setTeamStats(res.data.team || []);
    } catch { toast.error('Failed to load team stats'); }
    finally { setTeamLoading(false); }
  }, []);

  useEffect(() => { if (activeTab === 'team' && !teamStats) loadTeamStats(); }, [activeTab, teamStats, loadTeamStats]);

  // Load failed captures count on mount
  const loadFcCount = useCallback(async () => {
    try {
      const res = await candidateBankAPI.getFailedCaptures({ page: 1, limit: 1, show: 'unrecovered' });
      setFcUnrecovered(res.data.unrecovered || 0);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadFcCount(); }, [loadFcCount]);

  const loadFailedCaptures = useCallback(async (page = 1, show = 'unrecovered') => {
    setFcLoading(true);
    try {
      const res = await candidateBankAPI.getFailedCaptures({ page, limit: 15, show });
      setFcLogs(res.data.logs || []);
      setFcTotal(res.data.total || 0);
      setFcPages(res.data.pages || 1);
      setFcPage(res.data.page || 1);
      setFcUnrecovered(res.data.unrecovered || 0);
      setFcSelected(new Set());
    } catch { toast.error('Failed to load failed captures'); }
    finally { setFcLoading(false); }
  }, []);

  const loadIncomplete = useCallback(async (field, source, page) => {
    setListLoading(true);
    try {
      const params = { field, page, limit: 15 };
      if (source) params.source = source;
      const res = await candidateBankAPI.dataQualityIncomplete(params);
      setCandidates(res.data.candidates || []);
      setListTotal(res.data.total || 0);
      setListPages(res.data.pages || 1);
      setListPage(res.data.page || 1);
    } catch { toast.error('Failed to load candidates'); }
    finally { setListLoading(false); }
  }, []);

  const handleFieldClick = (field) => {
    setActiveField(field);
    setActiveSource(null);
    setListPage(1);
    setEditId(null);
    setFcView(false);
    loadIncomplete(field, null, 1);
  };

  const handleSourceFilter = (source) => {
    setActiveSource(source === activeSource ? null : source);
    setListPage(1);
    loadIncomplete(activeField, source === activeSource ? null : source, 1);
  };

  const handlePageChange = (newPage) => {
    setListPage(newPage);
    loadIncomplete(activeField, activeSource, newPage);
  };

  const handleStartEdit = (candidate) => {
    setEditId(candidate.id);
    setEditValues({
      [activeField]: activeField === 'skills' ? (candidate.skills || []).join(', ') : (candidate[activeField] || ''),
    });
  };

  const handleSaveEdit = async (candidateId) => {
    setSaving(true);
    try {
      const payload = { ...editValues };
      if (activeField === 'skills' && typeof payload.skills === 'string') {
        payload.skills = payload.skills.split(',').map(s => s.trim()).filter(Boolean);
      }
      await candidateBankAPI.dataQualityUpdate(candidateId, payload);
      toast.success('Updated');
      setEditId(null);
      loadIncomplete(activeField, activeSource, listPage);
      loadStats();
    } catch { toast.error('Update failed'); }
    finally { setSaving(false); }
  };

  // Failed capture handlers
  const handleOpenFcView = () => {
    setFcView(true);
    setActiveField(null);
    loadFailedCaptures(1, fcShow);
  };

  const handleFcEdit = (capture) => {
    setFcEditCapture(capture);
    setFcForm({
      name: capture.candidate_name || '',
      email: capture.candidate_email || '',
      phone: capture.candidate_phone || '',
      profile_url: capture.profile_url || '',
      current_employer: '',
      designation: '',
      location: '',
      skills: '',
      experience_years: 0,
    });
  };

  const handleFcSave = async () => {
    if (!fcEditCapture) return;
    setFcSaving(true);
    try {
      const res = await candidateBankAPI.saveFailedCapture(fcEditCapture.id, fcForm);
      if (res.data.was_duplicate) {
        toast.info(res.data.message);
      } else {
        toast.success('Saved to candidate bank');
      }
      setFcEditCapture(null);
      loadFailedCaptures(fcPage, fcShow);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Save failed');
    } finally {
      setFcSaving(false);
    }
  };

  const handleFcBulkDismiss = async () => {
    const ids = Array.from(fcSelected);
    if (ids.length === 0) return;
    if (!window.confirm(`Dismiss ${ids.length} junk capture(s)?`)) return;
    try {
      const res = await candidateBankAPI.bulkDismissCaptures(ids);
      toast.success(`Dismissed ${res.data.dismissed} capture(s)`);
      setFcSelected(new Set());
      loadFailedCaptures(fcPage, fcShow);
    } catch { toast.error('Dismiss failed'); }
  };

  const toggleFcSelect = (id) => {
    setFcSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleFcSelectAll = () => {
    if (fcSelected.size === fcLogs.length) {
      setFcSelected(new Set());
    } else {
      setFcSelected(new Set(fcLogs.map(l => l.id)));
    }
  };

  const handleAutoClassify = async (autoDismiss = false) => {
    setClassifying(true);
    try {
      const res = await candidateBankAPI.autoClassifyCaptures(autoDismiss);
      setClassifyResult(res.data);
      if (autoDismiss && res.data.auto_dismissed > 0) {
        toast.success(`Auto-dismissed ${res.data.auto_dismissed} junk capture(s)`);
        loadFailedCaptures(1, fcShow);
      }
    } catch { toast.error('Classification failed'); }
    finally { setClassifying(false); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  const scoreColor = stats?.score >= 80 ? '#7CB342' : stats?.score >= 50 ? '#F59E0B' : '#EF4444';

  return (
    <div className="space-y-6" data-testid="data-quality-page">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/admin/candidate-bank')} data-testid="back-btn">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight" style={{ fontFamily: 'Manrope, sans-serif' }}>
            Data Quality
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {stats?.total.toLocaleString()} candidates &middot; Identify and fix incomplete profiles
          </p>
        </div>
      </div>

      {/* Tab Toggle */}
      <div className="flex gap-1 bg-slate-100 rounded-lg p-1 w-fit" data-testid="dq-tab-toggle">
        <button
          onClick={() => setActiveTab('quality')}
          data-testid="tab-quality"
          className={`px-4 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${
            activeTab === 'quality' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <ShieldCheck className="w-4 h-4" /> Field Quality
        </button>
        <button
          onClick={() => setActiveTab('team')}
          data-testid="tab-team"
          className={`px-4 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${
            activeTab === 'team' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          <Users className="w-4 h-4" /> Team Performance
        </button>
      </div>

      {/* ═══ TEAM PERFORMANCE TAB ═══ */}
      {activeTab === 'team' && (
        teamLoading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
          </div>
        ) : teamStats && teamStats.length > 0 ? (() => {
          // Filter and sort logic
          const filtered = teamStats.filter(m => {
            if (teamRoleFilter !== 'all' && m.role !== teamRoleFilter) return false;
            if (teamSearch && !m.name.toLowerCase().includes(teamSearch.toLowerCase()) && !m.email.toLowerCase().includes(teamSearch.toLowerCase())) return false;
            return true;
          });
          const sorted = [...filtered].sort((a, b) => {
            let aVal, bVal;
            if (teamSortField === 'score') { aVal = a.score; bVal = b.score; }
            else if (teamSortField === 'total') { aVal = a.total; bVal = b.total; }
            else if (teamSortField === 'name') { return teamSortDir === 'asc' ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name); }
            else { aVal = a.field_rates[teamSortField] || 0; bVal = b.field_rates[teamSortField] || 0; }
            return teamSortDir === 'asc' ? aVal - bVal : bVal - aVal;
          });
          const top3 = [...teamStats].filter(m => m.total > 0).sort((a, b) => b.score - a.score).slice(0, 3);
          const toggleSort = (field) => {
            if (teamSortField === field) setTeamSortDir(d => d === 'asc' ? 'desc' : 'asc');
            else { setTeamSortField(field); setTeamSortDir('desc'); }
          };
          const SortIcon = ({ field }) => (
            <ArrowUpDown className={`w-3 h-3 ml-0.5 inline-block cursor-pointer transition-colors ${teamSortField === field ? 'text-blue-600' : 'text-slate-300'}`} />
          );
          const roleCounts = { all: teamStats.length, admin: 0, recruiter: 0, employer: 0 };
          teamStats.forEach(m => { if (roleCounts[m.role] !== undefined) roleCounts[m.role]++; });

          return (
          <div className="space-y-4" data-testid="team-performance-section">
            {/* Top 3 Leaderboard */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {top3.map((member, idx) => {
                const medals = ['#FFD700', '#C0C0C0', '#CD7F32'];
                const bgClasses = ['bg-amber-50 border-amber-200', 'bg-slate-50 border-slate-200', 'bg-orange-50 border-orange-200'];
                return (
                  <Card key={member.user_id} className={`border ${bgClasses[idx]}`} data-testid={`leaderboard-${idx}`}>
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <Award className="w-5 h-5" style={{ color: medals[idx] }} />
                          <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">#{idx + 1}</span>
                        </div>
                        <span className="text-2xl font-bold" style={{
                          color: member.score >= 80 ? '#7CB342' : member.score >= 50 ? '#F59E0B' : '#EF4444',
                          fontFamily: 'Manrope, sans-serif'
                        }}>
                          {member.score}%
                        </span>
                      </div>
                      <p className="text-sm font-semibold text-slate-900 truncate" style={{ fontFamily: 'Manrope, sans-serif' }}>
                        {member.name}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5">{member.total.toLocaleString()} candidates &middot; {member.role}</p>
                      <div className="mt-3 grid grid-cols-2 gap-2">
                        <div className="text-center p-1.5 rounded bg-white/60">
                          <p className="text-xs font-bold" style={{ color: member.field_rates.phone >= 80 ? '#7CB342' : member.field_rates.phone >= 50 ? '#F59E0B' : '#EF4444' }}>
                            {member.field_rates.phone}%
                          </p>
                          <p className="text-[10px] text-slate-400">Phone</p>
                        </div>
                        <div className="text-center p-1.5 rounded bg-white/60">
                          <p className="text-xs font-bold" style={{ color: member.field_rates.email >= 80 ? '#7CB342' : member.field_rates.email >= 50 ? '#F59E0B' : '#EF4444' }}>
                            {member.field_rates.email}%
                          </p>
                          <p className="text-[10px] text-slate-400">Email</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            {/* Filter & Sort Controls */}
            <div className="flex flex-wrap items-center gap-3" data-testid="team-controls">
              <div className="relative flex-1 min-w-[200px] max-w-xs">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <Input
                  placeholder="Search by name or email..."
                  value={teamSearch}
                  onChange={e => setTeamSearch(e.target.value)}
                  className="pl-9 h-9 text-sm"
                  data-testid="team-search"
                />
              </div>
              <div className="flex items-center gap-1.5 bg-slate-100 rounded-lg p-0.5" data-testid="team-role-filter">
                {[
                  { key: 'all', label: 'All' },
                  { key: 'recruiter', label: 'Recruiter' },
                  { key: 'admin', label: 'Admin' },
                  { key: 'employer', label: 'Employer' },
                ].map(opt => (
                  <button
                    key={opt.key}
                    onClick={() => setTeamRoleFilter(opt.key)}
                    data-testid={`filter-${opt.key}`}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      teamRoleFilter === opt.key
                        ? 'bg-white text-slate-900 shadow-sm'
                        : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    {opt.label} <span className="text-slate-400 ml-0.5">({roleCounts[opt.key]})</span>
                  </button>
                ))}
              </div>
              <div className="text-xs text-slate-400">
                {sorted.length} of {teamStats.length} members
              </div>
            </div>

            {/* Full Team Table */}
            <Card className="border border-slate-200" data-testid="team-table">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 bg-slate-50/50">
                        <th className="text-left p-3 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => toggleSort('name')}>
                          Team Member <SortIcon field="name" />
                        </th>
                        <th className="text-center p-3 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => toggleSort('total')}>
                          Captures <SortIcon field="total" />
                        </th>
                        <th className="text-center p-3 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => toggleSort('score')}>
                          Score <SortIcon field="score" />
                        </th>
                        <th className="text-center p-3 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => toggleSort('phone')}>
                          <span className="flex items-center justify-center gap-1"><Phone className="w-3 h-3" /> Phone <SortIcon field="phone" /></span>
                        </th>
                        <th className="text-center p-3 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => toggleSort('email')}>
                          <span className="flex items-center justify-center gap-1"><Mail className="w-3 h-3" /> Email <SortIcon field="email" /></span>
                        </th>
                        <th className="text-center p-3 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => toggleSort('current_employer')}>
                          <span className="flex items-center justify-center gap-1"><Briefcase className="w-3 h-3" /> Company <SortIcon field="current_employer" /></span>
                        </th>
                        <th className="text-center p-3 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => toggleSort('location')}>
                          <span className="flex items-center justify-center gap-1"><MapPin className="w-3 h-3" /> Location <SortIcon field="location" /></span>
                        </th>
                        <th className="text-center p-3 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => toggleSort('skills')}>
                          <span className="flex items-center justify-center gap-1"><Tag className="w-3 h-3" /> Skills <SortIcon field="skills" /></span>
                        </th>
                        <th className="text-center p-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Sources</th>
                        <th className="w-10 p-3" />
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.length === 0 ? (
                        <tr><td colSpan={10} className="text-center py-10 text-slate-400 text-sm">No members match the current filters</td></tr>
                      ) : sorted.map((member, idx) => {
                        const isExpanded = expandedUser === member.user_id;
                        const roleColors = { admin: 'bg-purple-50 text-purple-600', recruiter: 'bg-blue-50 text-blue-600', employer: 'bg-emerald-50 text-emerald-600' };
                        return (
                          <tr
                            key={member.user_id}
                            data-testid={`team-row-${member.user_id}`}
                            className={`border-b border-slate-50 transition-colors ${isExpanded ? 'bg-blue-50/30' : 'hover:bg-slate-50/50'}`}
                          >
                            <td className="p-3">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-mono text-slate-300 w-5">{idx + 1}.</span>
                                <div>
                                  <p className="font-medium text-slate-800 text-sm">{member.name}</p>
                                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${roleColors[member.role] || 'bg-slate-50 text-slate-500'}`}>
                                    {member.role}
                                  </span>
                                </div>
                              </div>
                            </td>
                            <td className="p-3 text-center">
                              <span className="font-semibold text-slate-700" style={{ fontFamily: 'Manrope, sans-serif' }}>
                                {member.total.toLocaleString()}
                              </span>
                            </td>
                            <td className="p-3 text-center">
                              {member.total > 0 ? (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold" style={{
                                  backgroundColor: member.score >= 80 ? '#f0fdf4' : member.score >= 50 ? '#fefce8' : '#fef2f2',
                                  color: member.score >= 80 ? '#7CB342' : member.score >= 50 ? '#F59E0B' : '#EF4444',
                                }}>
                                  {member.score}%
                                </span>
                              ) : (
                                <span className="text-xs text-slate-300">—</span>
                              )}
                            </td>
                            {['phone', 'email', 'current_employer', 'location', 'skills'].map(f => {
                              const rate = member.field_rates[f] || 0;
                              if (member.total === 0) return <td key={f} className="p-3 text-center"><span className="text-xs text-slate-300">—</span></td>;
                              const color = rate >= 90 ? '#7CB342' : rate >= 60 ? '#F59E0B' : '#EF4444';
                              return (
                                <td key={f} className="p-3 text-center">
                                  <div className="flex flex-col items-center gap-1">
                                    <span className="text-xs font-semibold" style={{ color }}>{rate}%</span>
                                    <div className="w-12 h-1 bg-slate-100 rounded-full overflow-hidden">
                                      <div className="h-full rounded-full" style={{ width: `${rate}%`, backgroundColor: color }} />
                                    </div>
                                  </div>
                                </td>
                              );
                            })}
                            <td className="p-3 text-center">
                              {member.total > 0 ? (
                                <div className="flex items-center justify-center gap-1.5 flex-wrap">
                                  {member.sources.extension > 0 && (
                                    <span className="text-[10px] px-1.5 py-0.5 bg-orange-50 text-orange-600 rounded font-medium">
                                      Ext {member.sources.extension}
                                    </span>
                                  )}
                                  {member.sources.excel > 0 && (
                                    <span className="text-[10px] px-1.5 py-0.5 bg-emerald-50 text-emerald-600 rounded font-medium">
                                      Excel {member.sources.excel}
                                    </span>
                                  )}
                                  {member.sources.manual > 0 && (
                                    <span className="text-[10px] px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded font-medium">
                                      Manual {member.sources.manual}
                                    </span>
                                  )}
                                </div>
                              ) : <span className="text-xs text-slate-300">—</span>}
                            </td>
                            <td className="p-3">
                              {member.total > 0 && (
                                <Button
                                  variant="ghost" size="sm"
                                  className="h-7 w-7 p-0"
                                  onClick={() => setExpandedUser(isExpanded ? null : member.user_id)}
                                  data-testid={`expand-${member.user_id}`}
                                >
                                  <Eye className="w-3.5 h-3.5 text-slate-400" />
                                </Button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            {/* Expanded detail for selected user */}
            {expandedUser && (() => {
              const member = teamStats.find(m => m.user_id === expandedUser);
              if (!member) return null;
              const allFields = ['email', 'phone', 'skills', 'current_employer', 'designation', 'location', 'industry'];
              return (
                <Card className="border border-blue-200 bg-blue-50/30" data-testid="expanded-user-detail">
                  <CardContent className="p-5">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900" style={{ fontFamily: 'Manrope, sans-serif' }}>
                          {member.name} — Detailed Breakdown
                        </h3>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {member.total.toLocaleString()} candidates &middot; Last active: {member.latest_capture ? new Date(member.latest_capture).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'N/A'}
                        </p>
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => setExpandedUser(null)} data-testid="close-expanded">
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
                      {allFields.map(f => {
                        const rate = member.field_rates[f] || 0;
                        const missing = Math.round(member.total * (100 - rate) / 100);
                        const color = rate >= 90 ? '#7CB342' : rate >= 60 ? '#F59E0B' : '#EF4444';
                        const label = FIELD_META[f]?.label || f;
                        return (
                          <div key={f} className="bg-white rounded-lg border border-slate-200 p-3 text-center">
                            <p className="text-lg font-bold" style={{ color, fontFamily: 'Manrope, sans-serif' }}>{rate}%</p>
                            <p className="text-xs font-medium text-slate-600 mt-0.5">{label}</p>
                            <p className="text-[10px] text-slate-400 mt-1">{missing} missing</p>
                            <div className="h-1 bg-slate-100 rounded-full mt-2 overflow-hidden">
                              <div className="h-full rounded-full" style={{ width: `${rate}%`, backgroundColor: color }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              );
            })()}
          </div>
          );
          })()
        : (
          <div className="text-center py-20 text-slate-400">
            <Users className="w-10 h-10 mx-auto mb-3 text-slate-300" />
            <p className="text-sm">No team data available yet</p>
          </div>
        )
      )}

      {activeTab === 'quality' && (<>
      {/* ═══ FAILED CAPTURES BANNER ═══ */}
      {fcUnrecovered > 0 && !fcView && (
        <button
          onClick={handleOpenFcView}
          data-testid="failed-captures-banner"
          className="w-full text-left p-4 rounded-lg border border-amber-200 bg-amber-50/60 hover:bg-amber-50 transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-amber-100">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <p className="text-sm font-semibold text-amber-900">
                  {fcUnrecovered} Failed Extension Capture{fcUnrecovered > 1 ? 's' : ''}
                </p>
                <p className="text-xs text-amber-700 mt-0.5">
                  Candidates that couldn't be auto-captured. Click to review, fix & add to bank.
                </p>
              </div>
            </div>
            <Badge className="bg-amber-200 text-amber-800 hover:bg-amber-200">{fcUnrecovered}</Badge>
          </div>
        </button>
      )}

      {/* Regex Parser Quality — moved from Admin Dashboard on 2026-05-01 */}
      {regexQuality && (
        <Card className="border-slate-200" data-testid="extraction-quality-card">
          <CardContent className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Cpu className="w-4 h-4 text-violet-600" /> Regex Parser Quality
              </h3>
              <div className="flex items-center gap-2 text-xs">
                <Badge variant="secondary" className="text-[10px]">{regexQuality.total_regex_enriched} regex</Badge>
                <Badge variant="secondary" className="text-[10px]">{regexQuality.total_claude_enriched} claude</Badge>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {(() => {
                const score = regexQuality.overall_quality_score || 0;
                const scoreColor = score >= 80 ? 'text-emerald-600' : score >= 60 ? 'text-amber-600' : 'text-red-600';
                const scoreBg = score >= 80 ? 'bg-emerald-50' : score >= 60 ? 'bg-amber-50' : 'bg-red-50';
                const scoreRing = score >= 80 ? 'border-emerald-300' : score >= 60 ? 'border-amber-300' : 'border-red-300';
                return (
                  <div className={`relative w-16 h-16 rounded-full border-4 ${scoreRing} ${scoreBg} flex items-center justify-center flex-shrink-0`}>
                    <span className={`text-lg font-bold ${scoreColor}`}>{score}%</span>
                  </div>
                );
              })()}
              <p className="text-xs text-slate-600">
                Average field extraction rate across&nbsp;
                <strong>{regexQuality.total_regex_enriched}</strong>&nbsp;profiles.
              </p>
            </div>
            {regexQuality.field_stats?.length > 0 && (
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-1">
                {[...regexQuality.field_stats].sort((a, b) => b.rate - a.rate).map((f) => {
                  const barColor = f.rate >= 80 ? 'bg-emerald-500' : f.rate >= 50 ? 'bg-amber-400' : 'bg-red-400';
                  return (
                    <div key={f.label} className="flex items-center gap-1.5 text-[11px]">
                      <span className="text-slate-500 w-20 truncate">{f.label}</span>
                      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${f.rate}%` }} />
                      </div>
                      <span className="text-slate-600 font-semibold w-8 text-right">{f.rate}%</span>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Score + Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Overall Score */}
        <Card className="border border-slate-200 lg:row-span-2" data-testid="quality-score-card">
          <CardContent className="p-6 flex flex-col items-center justify-center h-full">
            <div className="relative w-28 h-28 mb-3">
              <svg className="w-28 h-28 -rotate-90" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="none" stroke="#F1F5F9" strokeWidth="8" />
                <circle
                  cx="50" cy="50" r="42" fill="none"
                  stroke={scoreColor}
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={`${(stats?.score || 0) * 2.64} 264`}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-2xl font-bold" style={{ color: scoreColor, fontFamily: 'Manrope, sans-serif' }}>
                  {stats?.score || 0}%
                </span>
              </div>
            </div>
            <p className="text-sm font-medium text-slate-700">Data Quality Score</p>
            <p className="text-xs text-slate-400 mt-1 text-center">
              Based on critical (60%) & important (40%) fields
            </p>
          </CardContent>
        </Card>

        {/* Field Cards */}
        {Object.entries(FIELD_META).map(([field, meta]) => {
          const fieldData = stats?.fields?.[field];
          if (!fieldData) return null;
          const pct = fieldData.pct_filled;
          const missing = fieldData.missing;
          const color = pct >= 95 ? '#7CB342' : pct >= 70 ? '#F59E0B' : '#EF4444';
          const isActive = activeField === field;

          return (
            <button
              key={field}
              onClick={() => handleFieldClick(field)}
              data-testid={`field-card-${field}`}
              className={`text-left transition-all rounded-lg border p-4 ${
                isActive
                  ? 'border-[#7CB342] bg-green-50/50 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <meta.icon className="w-4 h-4 text-slate-400" />
                  <span className="text-sm font-medium text-slate-700">{meta.label}</span>
                </div>
                {meta.critical && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-red-50 text-red-600 rounded font-medium">CRITICAL</span>
                )}
              </div>
              <div className="flex items-end justify-between">
                <div>
                  <span className="text-lg font-bold" style={{ color, fontFamily: 'Manrope, sans-serif' }}>
                    {pct}%
                  </span>
                  <span className="text-xs text-slate-400 ml-1">filled</span>
                </div>
                {missing > 0 && (
                  <span className="text-xs text-slate-500">{missing} missing</span>
                )}
              </div>
              <div className="h-1.5 bg-slate-100 rounded-full mt-2 overflow-hidden">
                <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
              </div>
            </button>
          );
        })}
      </div>

      {/* Source Breakdown */}
      {stats?.by_source && Object.keys(stats.by_source).length > 0 && (
        <Card className="border border-slate-200" data-testid="source-breakdown">
          <CardContent className="p-6">
            <h3 className="text-sm font-semibold text-slate-900 mb-3" style={{ fontFamily: 'Manrope, sans-serif' }}>
              Critical Fields Missing by Source
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(stats.by_source)
                .filter(([, v]) => Object.keys(v.missing_critical).length > 0)
                .sort((a, b) => b[1].total - a[1].total)
                .map(([src, data]) => (
                  <button
                    key={src}
                    onClick={() => { if (activeField) handleSourceFilter(src); }}
                    data-testid={`source-${src}`}
                    className={`p-3 rounded-lg border text-left transition-all ${
                      activeSource === src
                        ? 'border-[#7CB342] bg-green-50/50'
                        : 'border-slate-200 hover:border-slate-300'
                    } ${!activeField ? 'opacity-60 cursor-default' : 'cursor-pointer'}`}
                  >
                    <div className="text-xs font-medium text-slate-700 mb-1 truncate">{src}</div>
                    <div className="text-xs text-slate-400">{data.total} candidates</div>
                    {Object.entries(data.missing_critical).map(([f, c]) => (
                      <div key={f} className="text-xs text-red-500 mt-0.5">
                        {c} missing {f}
                      </div>
                    ))}
                  </button>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ═══ FAILED CAPTURES LIST ═══ */}
      {fcView && (
        <Card className="border border-amber-200" data-testid="failed-captures-section">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
                <div>
                  <h3 className="text-sm font-semibold text-slate-900" style={{ fontFamily: 'Manrope, sans-serif' }}>
                    Failed Extension Captures
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">{fcUnrecovered} unrecovered &middot; Review and fix data to add to bank</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {/* Filter toggle */}
                <div className="flex gap-0.5 bg-slate-100 rounded-md p-0.5">
                  {['unrecovered', 'recovered', 'all'].map(v => (
                    <button
                      key={v}
                      onClick={() => { setFcShow(v); setClassifyResult(null); loadFailedCaptures(1, v); }}
                      data-testid={`fc-filter-${v}`}
                      className={`px-2.5 py-1 rounded text-[11px] font-medium transition-all ${
                        fcShow === v ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'
                      }`}
                    >
                      {v === 'unrecovered' ? 'Pending' : v === 'recovered' ? 'Resolved' : 'All'}
                    </button>
                  ))}
                </div>
                {/* Auto-classify button */}
                <Button
                  variant="outline" size="sm"
                  className="gap-1.5 text-indigo-600 hover:bg-indigo-50 border-indigo-200"
                  onClick={() => handleAutoClassify(false)}
                  disabled={classifying}
                  data-testid="fc-auto-classify-btn"
                >
                  {classifying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  Auto-Classify
                </Button>
                {fcSelected.size > 0 && (
                  <Button variant="outline" size="sm" className="text-red-600 hover:bg-red-50 gap-1" onClick={handleFcBulkDismiss} data-testid="fc-bulk-dismiss-btn">
                    <Trash2 className="w-3.5 h-3.5" /> Dismiss ({fcSelected.size})
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => { setFcView(false); setClassifyResult(null); }} data-testid="fc-close-btn">
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* ─── Classification Results Panel ─── */}
            {classifyResult && (
              <div className="mb-4 p-4 rounded-lg border border-indigo-200 bg-indigo-50/50" data-testid="classify-results-panel">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-semibold text-indigo-900 flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-500" /> Classification Results
                  </h4>
                  <Button
                    variant="ghost" size="sm"
                    className="text-slate-400 h-6 w-6 p-0"
                    onClick={() => setClassifyResult(null)}
                    data-testid="classify-close-btn"
                  >
                    <X className="w-3.5 h-3.5" />
                  </Button>
                </div>
                <div className="grid grid-cols-3 gap-3 mb-3">
                  <div className="p-2.5 rounded-md bg-red-50 border border-red-200 text-center">
                    <p className="text-lg font-bold text-red-700">{classifyResult.junk_count}</p>
                    <p className="text-[10px] text-red-600 font-medium">Junk / UI Text</p>
                  </div>
                  <div className="p-2.5 rounded-md bg-emerald-50 border border-emerald-200 text-center">
                    <p className="text-lg font-bold text-emerald-700">{classifyResult.genuine_count}</p>
                    <p className="text-[10px] text-emerald-600 font-medium">Genuine Candidates</p>
                  </div>
                  <div className="p-2.5 rounded-md bg-amber-50 border border-amber-200 text-center">
                    <p className="text-lg font-bold text-amber-700">{classifyResult.uncertain_count}</p>
                    <p className="text-[10px] text-amber-600 font-medium">Needs Review</p>
                  </div>
                </div>

                {/* Junk details (collapsible) */}
                {classifyResult.junk_count > 0 && (
                  <div className="mb-3">
                    <p className="text-xs text-slate-600 mb-1.5">
                      <span className="font-medium">Junk captures</span> — UI text and navigation elements mistakenly captured:
                    </p>
                    <div className="max-h-32 overflow-y-auto space-y-1">
                      {classifyResult.junk.map((j, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-slate-500 py-0.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                          <span className="font-medium text-slate-700 truncate max-w-[140px]">{j.name || '(empty)'}</span>
                          <span className="text-slate-400 truncate flex-1">{j.reason}</span>
                          <span className="text-[10px] text-slate-300">{Math.round(j.confidence * 100)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Auto-dismiss button */}
                {classifyResult.junk_count > 0 && classifyResult.auto_dismissed === 0 && (
                  <Button
                    size="sm"
                    className="w-full bg-red-600 hover:bg-red-700 gap-1.5"
                    onClick={() => handleAutoClassify(true)}
                    disabled={classifying}
                    data-testid="fc-auto-dismiss-junk-btn"
                  >
                    {classifying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    Auto-Dismiss {classifyResult.junk_count} Junk Capture{classifyResult.junk_count > 1 ? 's' : ''}
                  </Button>
                )}
                {classifyResult.auto_dismissed > 0 && (
                  <div className="text-center py-2">
                    <Badge className="bg-emerald-100 text-emerald-700">
                      <Check className="w-3 h-3 mr-1" /> {classifyResult.auto_dismissed} junk captures auto-dismissed
                    </Badge>
                  </div>
                )}
              </div>
            )}

            {fcLoading ? (
              <div className="text-center py-8"><Loader2 className="w-5 h-5 animate-spin mx-auto text-slate-400" /></div>
            ) : fcLogs.length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                <ShieldCheck className="w-8 h-8 mx-auto mb-2 text-emerald-400" />
                <p className="text-sm">No {fcShow === 'unrecovered' ? 'pending' : ''} failed captures</p>
              </div>
            ) : (
              <>
                {/* Select all checkbox */}
                {fcShow === 'unrecovered' && (
                  <div className="flex items-center gap-2 mb-3 pb-2 border-b border-slate-100">
                    <input
                      type="checkbox"
                      checked={fcSelected.size === fcLogs.length && fcLogs.length > 0}
                      onChange={toggleFcSelectAll}
                      className="rounded border-slate-300"
                      data-testid="fc-select-all"
                    />
                    <span className="text-xs text-slate-500">Select all for bulk dismiss</span>
                  </div>
                )}

                <div className="space-y-2">
                  {fcLogs.map((fc) => (
                    <div
                      key={fc.id}
                      data-testid={`fc-row-${fc.id}`}
                      className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
                        fc.is_recovered ? 'border-slate-100 bg-slate-50/50 opacity-60' : 'border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      {!fc.is_recovered && (
                        <input
                          type="checkbox"
                          checked={fcSelected.has(fc.id)}
                          onChange={() => toggleFcSelect(fc.id)}
                          className="rounded border-slate-300 mt-1 shrink-0"
                          data-testid={`fc-check-${fc.id}`}
                        />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-slate-800">{fc.candidate_name || 'Unknown'}</span>
                          <Badge variant="outline" className="text-[9px] text-red-600 border-red-200">{fc.failed_step || 'unknown'}</Badge>
                          {fc.is_recovered && <Badge className="text-[9px] bg-emerald-100 text-emerald-700">Resolved</Badge>}
                        </div>
                        <p className="text-xs text-slate-500 mt-0.5 truncate">{fc.failure_reason}</p>
                        <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-400 flex-wrap">
                          {fc.candidate_email && fc.candidate_email !== '' && (
                            <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{fc.candidate_email}</span>
                          )}
                          {fc.candidate_phone && fc.candidate_phone !== '' && (
                            <span className="flex items-center gap-1"><Phone className="w-3 h-3" />{fc.candidate_phone}</span>
                          )}
                          {fc.profile_url && (
                            <a href={fc.profile_url} target="_blank" rel="noopener noreferrer"
                              className="flex items-center gap-1 text-blue-500 hover:underline"
                              data-testid={`fc-profile-link-${fc.id}`}
                              onClick={(e) => e.stopPropagation()}>
                              <Link2 className="w-3 h-3" />Naukri Profile
                            </a>
                          )}
                          {fc.data_missing_fields?.length > 0 && (
                            <span className="text-amber-500">Missing: {fc.data_missing_fields.join(', ')}</span>
                          )}
                          <span>{new Date(fc.timestamp).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' })}</span>
                        </div>
                      </div>
                      {!fc.is_recovered && (
                        <Button
                          size="sm" variant="outline"
                          className="shrink-0 text-xs h-8 gap-1.5"
                          onClick={() => handleFcEdit(fc)}
                          data-testid={`fc-fix-btn-${fc.id}`}
                        >
                          <UserPlus className="w-3.5 h-3.5" /> Fix & Add
                        </Button>
                      )}
                    </div>
                  ))}
                </div>

                {/* Pagination */}
                {fcPages > 1 && (
                  <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-100">
                    <Button variant="outline" size="sm" disabled={fcPage <= 1}
                      onClick={() => loadFailedCaptures(fcPage - 1, fcShow)} data-testid="fc-prev-page">
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <span className="text-xs text-slate-500">Page {fcPage} of {fcPages}</span>
                    <Button variant="outline" size="sm" disabled={fcPage >= fcPages}
                      onClick={() => loadFailedCaptures(fcPage + 1, fcShow)} data-testid="fc-next-page">
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* ═══ FIX & SAVE DIALOG ═══ */}
      <Dialog open={!!fcEditCapture} onOpenChange={() => setFcEditCapture(null)}>
        <DialogContent className="max-w-lg" data-testid="fc-edit-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2" style={{ fontFamily: 'Manrope, sans-serif' }}>
              <Wrench className="w-5 h-5 text-amber-600" /> Fix & Add to Candidate Bank
            </DialogTitle>
          </DialogHeader>
          {fcEditCapture && (
            <div className="space-y-4">
              {/* Failure info */}
              <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs">
                <p className="text-amber-800 font-medium">Failure: {fcEditCapture.failure_reason}</p>
                {fcEditCapture.profile_url && (
                  <a href={fcEditCapture.profile_url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-blue-600 hover:underline mt-1"
                    data-testid="fc-dialog-profile-link">
                    <ExternalLink className="w-3 h-3" /> Open Naukri Profile to get correct details
                  </a>
                )}
              </div>

              {/* Form fields */}
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Name *</label>
                  <Input
                    value={fcForm.name || ''}
                    onChange={(e) => setFcForm({ ...fcForm, name: e.target.value })}
                    placeholder="Candidate name"
                    data-testid="fc-input-name"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Email</label>
                  <Input
                    value={fcForm.email || ''}
                    onChange={(e) => setFcForm({ ...fcForm, email: e.target.value })}
                    placeholder="email@example.com"
                    data-testid="fc-input-email"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Phone</label>
                  <Input
                    value={fcForm.phone || ''}
                    onChange={(e) => setFcForm({ ...fcForm, phone: e.target.value })}
                    placeholder="+91 98765 43210"
                    data-testid="fc-input-phone"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Current Company</label>
                  <Input
                    value={fcForm.current_employer || ''}
                    onChange={(e) => setFcForm({ ...fcForm, current_employer: e.target.value })}
                    placeholder="Company name"
                    data-testid="fc-input-company"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Designation</label>
                  <Input
                    value={fcForm.designation || ''}
                    onChange={(e) => setFcForm({ ...fcForm, designation: e.target.value })}
                    placeholder="Job title"
                    data-testid="fc-input-designation"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Location</label>
                  <Input
                    value={fcForm.location || ''}
                    onChange={(e) => setFcForm({ ...fcForm, location: e.target.value })}
                    placeholder="City, State"
                    data-testid="fc-input-location"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Experience (years)</label>
                  <Input
                    type="number" min="0"
                    value={fcForm.experience_years || 0}
                    onChange={(e) => setFcForm({ ...fcForm, experience_years: parseInt(e.target.value) || 0 })}
                    data-testid="fc-input-experience"
                  />
                </div>
                <div className="col-span-2">
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Skills (comma-separated)</label>
                  <Input
                    value={fcForm.skills || ''}
                    onChange={(e) => setFcForm({ ...fcForm, skills: e.target.value })}
                    placeholder="Python, JavaScript, React..."
                    data-testid="fc-input-skills"
                  />
                </div>
                <div className="col-span-2">
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Naukri Profile URL</label>
                  <Input
                    value={fcForm.profile_url || ''}
                    onChange={(e) => setFcForm({ ...fcForm, profile_url: e.target.value })}
                    placeholder="https://resdex.naukri.com/..."
                    data-testid="fc-input-url"
                  />
                </div>
              </div>

              <p className="text-[11px] text-slate-400">* Name + at least one of email/phone required</p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setFcEditCapture(null)} data-testid="fc-cancel-btn">Cancel</Button>
            <Button onClick={handleFcSave} disabled={fcSaving} className="bg-[#7CB342] hover:bg-[#689F38] gap-1.5" data-testid="fc-save-to-bank-btn">
              {fcSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save to Bank
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Incomplete Candidates List (existing) */}
      {activeField && (
        <Card className="border border-slate-200" data-testid="incomplete-list">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-slate-900" style={{ fontFamily: 'Manrope, sans-serif' }}>
                Candidates Missing {FIELD_META[activeField]?.label}
                {activeSource && <span className="text-slate-400 font-normal"> from {activeSource}</span>}
              </h3>
              <span className="text-xs text-slate-500">{listTotal} total</span>
            </div>

            {listLoading ? (
              <div className="text-center py-8">
                <Loader2 className="w-5 h-5 animate-spin mx-auto text-slate-400" />
              </div>
            ) : candidates.length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                <ShieldCheck className="w-8 h-8 mx-auto mb-2 text-[#7CB342]" />
                <p className="text-sm">All candidates have this field filled!</p>
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  {candidates.map(c => (
                    <div
                      key={c.id}
                      className="flex items-center gap-3 p-3 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors"
                      data-testid={`candidate-row-${c.id}`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-slate-800 truncate">{c.name || 'Unknown'}</div>
                        <div className="flex items-center gap-3 mt-0.5 text-xs text-slate-400">
                          {c.email && <span>{c.email}</span>}
                          {c.phone && <span>{c.phone}</span>}
                          {c.source && (
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              c.source === 'naukri_extension' ? 'bg-orange-50 text-orange-600' :
                              c.source === 'naukri_mailer_extension' ? 'bg-amber-100 text-amber-700 border border-amber-300' :
                              c.source === 'linkedin_extension' ? 'bg-blue-50 text-blue-700' :
                              c.source === 'foundit_extension' ? 'bg-purple-50 text-purple-600' :
                              c.source === 'bulk_import' ? 'bg-amber-50 text-amber-600' :
                              c.source === 'cv_upload' ? 'bg-teal-50 text-teal-600' :
                              'bg-slate-100 text-slate-500'
                            }`}>
                              {c.source === 'naukri_extension' ? 'Naukri' :
                               c.source === 'linkedin_extension' ? 'LinkedIn' :
                               c.source === 'foundit_extension' ? 'Foundit' :
                               c.source === 'naukri_mailer_extension' ? 'M Mailer' :
                               c.source === 'bulk_import' ? 'Bulk' :
                               c.source === 'cv_upload' ? 'CV Upload' : c.source}
                            </span>
                          )}
                        </div>
                      </div>
                      {editId === c.id ? (
                        <div className="flex items-center gap-2">
                          <Input
                            value={editValues[activeField] || ''}
                            onChange={(e) => setEditValues({ ...editValues, [activeField]: e.target.value })}
                            placeholder={`Enter ${FIELD_META[activeField]?.label}`}
                            className="w-48 h-8 text-sm"
                            data-testid={`edit-input-${c.id}`}
                            autoFocus
                            onKeyDown={(e) => { if (e.key === 'Enter') handleSaveEdit(c.id); }}
                          />
                          <Button
                            size="sm"
                            onClick={() => handleSaveEdit(c.id)}
                            disabled={saving}
                            className="h-8 bg-[#7CB342] hover:bg-[#689F38]"
                            data-testid={`save-${c.id}`}
                          >
                            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                          </Button>
                        </div>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleStartEdit(c)}
                          className="text-slate-400 hover:text-slate-700"
                          data-testid={`edit-btn-${c.id}`}
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>

                {/* Pagination */}
                {listPages > 1 && (
                  <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-100">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={listPage <= 1}
                      onClick={() => handlePageChange(listPage - 1)}
                      data-testid="prev-page"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <span className="text-xs text-slate-500">Page {listPage} of {listPages}</span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={listPage >= listPages}
                      onClick={() => handlePageChange(listPage + 1)}
                      data-testid="next-page"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}
      </>)}

      {/* Phone Number Blocklist */}
      <PhoneBlocklistSection />
    </div>
  );
}

function PhoneBlocklistSection() {
  const [blocklist, setBlocklist] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newNumbers, setNewNumbers] = useState('');
  const [adding, setAdding] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const loadBlocklist = async () => {
    try {
      const res = await candidateBankAPI.getPhoneBlocklist();
      setBlocklist(res.data.numbers || []);
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  useEffect(() => { loadBlocklist(); }, []);

  const handleAdd = async () => {
    if (!newNumbers.trim()) return;
    setAdding(true);
    try {
      const nums = newNumbers.split(/[,\s\n]+/).filter(n => n.trim());
      const res = await candidateBankAPI.addToBlocklist(nums);
      toast.success(res.data.message);
      setNewNumbers('');
      loadBlocklist();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add');
    } finally { setAdding(false); }
  };

  const handleRemove = async (phone) => {
    try {
      await candidateBankAPI.removeFromBlocklist(phone);
      toast.success(`Removed ${phone}`);
      loadBlocklist();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to remove');
    }
  };

  const handleCleanup = async () => {
    setCleaning(true);
    try {
      const res = await candidateBankAPI.cleanupBlockedNumbers();
      toast.success(res.data.message);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Cleanup failed');
    } finally { setCleaning(false); }
  };

  const displayed = showAll ? blocklist : blocklist.slice(0, 10);

  return (
    <Card className="border-slate-200 mt-6" data-testid="phone-blocklist-card">
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-heading font-semibold text-base text-slate-900 flex items-center gap-2">
              <Phone className="w-4 h-4 text-red-500" /> Phone Number Blocklist
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Block Naukri license numbers from being captured as candidate contacts. {blocklist.length} numbers blocked.
            </p>
          </div>
          <Button size="sm" variant="outline" className="text-red-600 border-red-300 hover:bg-red-50" onClick={handleCleanup} disabled={cleaning} data-testid="cleanup-blocked-btn">
            {cleaning ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Trash2 className="w-3.5 h-3.5 mr-1" />}
            {cleaning ? 'Cleaning...' : 'Clean Existing Profiles'}
          </Button>
        </div>

        {/* Add numbers */}
        <div className="flex gap-2 mb-4">
          <Input value={newNumbers} onChange={e => setNewNumbers(e.target.value)}
            placeholder="Enter phone numbers (comma-separated)" className="text-sm flex-1" data-testid="blocklist-input" />
          <Button size="sm" onClick={handleAdd} disabled={adding || !newNumbers.trim()} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="add-blocklist-btn">
            {adding ? 'Adding...' : 'Add'}
          </Button>
        </div>

        {/* Blocked numbers list */}
        {loading ? (
          <div className="text-center py-4"><Loader2 className="w-5 h-5 animate-spin mx-auto text-slate-400" /></div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {displayed.map(num => (
              <span key={num} className="inline-flex items-center gap-1 px-2.5 py-1 bg-red-50 text-red-600 text-xs rounded-full border border-red-100" data-testid={`blocked-${num}`}>
                {num}
                <button onClick={() => handleRemove(num)} className="hover:text-red-800"><X className="w-3 h-3" /></button>
              </span>
            ))}
            {blocklist.length > 10 && !showAll && (
              <button onClick={() => setShowAll(true)} className="text-xs text-blue-600 hover:underline px-2 py-1">
                +{blocklist.length - 10} more
              </button>
            )}
            {blocklist.length === 0 && <p className="text-sm text-slate-400">No numbers blocked</p>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
