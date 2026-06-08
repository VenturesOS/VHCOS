import { useState, useEffect, useCallback } from 'react';
import { adminAPI, applicationAPI, revenueAPI } from '../../lib/api';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import { DeleteDialog, OfferDialog, HiredDialog, JoinDialog } from '../../components/admin/pipeline/PipelineDialogs';
import { 
  LayoutGrid, Users, CheckCircle, Clock, Award, UserCheck, 
  XCircle, Pause, Filter, Building2, Send,
  Briefcase, FileText, Trash2, AlertCircle, IndianRupee, Lock, ArrowRight,
  CalendarClock
} from 'lucide-react';

// Stage configuration — simplified (no approval gate)
const STAGES = [
  { id: 'sourced', label: 'Sourced', color: 'bg-slate-500', icon: Users, bgLight: 'bg-slate-50' },
  { id: 'submitted_to_client', label: 'Submitted', color: 'bg-cyan-500', icon: Send, bgLight: 'bg-cyan-50' },
  { id: 'shortlisted', label: 'Shortlisted', color: 'bg-amber-500', icon: CheckCircle, bgLight: 'bg-amber-50' },
  { id: 'interview', label: 'Interviewed', color: 'bg-purple-500', icon: Clock, bgLight: 'bg-purple-50' },
  { id: 'offered', label: 'Offered', color: 'bg-green-500', icon: Award, bgLight: 'bg-green-50' },
  { id: 'hired', label: 'Hired', color: 'bg-emerald-500', icon: UserCheck, bgLight: 'bg-emerald-50' },
  { id: 'joined', label: 'Joined', color: 'bg-teal-500', icon: Lock, bgLight: 'bg-teal-50' },
  { id: 'rejected', label: 'Rejected', color: 'bg-red-500', icon: XCircle, bgLight: 'bg-red-50' },
  { id: 'on_hold', label: 'On Hold', color: 'bg-gray-500', icon: Pause, bgLight: 'bg-gray-50' },
];

const PRIMARY_STAGES = ['sourced', 'submitted_to_client', 'shortlisted', 'interview', 'offered', 'hired', 'joined'];

export default function AdminPipelinePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [pipelineData, setPipelineData] = useState({});
  const [stageCounts, setStageCounts] = useState({});
  const [totalApplications, setTotalApplications] = useState(0);
  const [filters, setFilters] = useState({ employers: [], recruiters: [], jobs: [] });
  
  // Filter state
  const [selectedEmployer, setSelectedEmployer] = useState('all');
  const [selectedRecruiter, setSelectedRecruiter] = useState('all');
  const [selectedJob, setSelectedJob] = useState(searchParams.get('job_id') || 'all');
  // Pipeline timeline filter (v5.5.10) — shows only stage MOVEMENTS in window.
  // Default 'all' preserves the old global view.
  const [pipelineWindow, setPipelineWindow] = useState(searchParams.get('window') || 'all');

  // Deep-link: if URL contains ?job_id=X, keep it in sync with state.
  useEffect(() => {
    const urlJob = searchParams.get('job_id');
    if (urlJob && urlJob !== selectedJob) setSelectedJob(urlJob);
  }, [searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateSelectedJob = (v) => {
    setSelectedJob(v);
    if (v === 'all') {
      if (searchParams.get('job_id')) {
        searchParams.delete('job_id');
        setSearchParams(searchParams, { replace: true });
      }
    } else if (searchParams.get('job_id') !== v) {
      searchParams.set('job_id', v);
      setSearchParams(searchParams, { replace: true });
    }
  };

  const updateWindow = (v) => {
    setPipelineWindow(v);
    if (!v || v === 'all') {
      if (searchParams.get('window')) {
        searchParams.delete('window');
        setSearchParams(searchParams, { replace: true });
      }
    } else if (searchParams.get('window') !== v) {
      searchParams.set('window', v);
      setSearchParams(searchParams, { replace: true });
    }
  };

  const loadFilters = useCallback(async () => {
    // Phase 54.12 — dropdowns load separately from data so filter
    // changes don't pay the dropdown-fetch cost every click.
    try {
      const params = {};
      if (selectedEmployer !== 'all') params.employer_id = selectedEmployer;
      const res = await adminAPI.getPipelineFilters(params);
      setFilters(res.data);
    } catch (e) {
      // Non-fatal — pipeline still loads, just without dropdowns
    }
  }, [selectedEmployer]);

  const loadPipeline = useCallback(async () => {
    setLoading(true);
    try {
      const params = { include_filters: false };  // Phase 54.12
      if (selectedEmployer !== 'all') params.employer_id = selectedEmployer;
      if (selectedRecruiter !== 'all') params.recruiter_id = selectedRecruiter;
      if (selectedJob !== 'all') params.job_id = selectedJob;
      if (pipelineWindow && pipelineWindow !== 'all') params.window = pipelineWindow;

      const res = await adminAPI.getPipeline(params);
      setPipelineData(res.data.pipeline);
      setStageCounts(res.data.stage_counts);
      setTotalApplications(res.data.total_applications);
    } catch (error) {
      toast.error('Failed to load pipeline data');
    } finally {
      setLoading(false);
    }
  }, [selectedEmployer, selectedRecruiter, selectedJob, pipelineWindow]);

  // Load filters once on mount + whenever employer cascade changes
  useEffect(() => {
    loadFilters();
  }, [loadFilters]);

  useEffect(() => {
    loadPipeline();
  }, [loadPipeline]);

  const clearFilters = () => {
    setSelectedEmployer('all');
    setSelectedRecruiter('all');
    updateSelectedJob('all');
    updateWindow('all');
  };

  // Phase 52 cascade: when employer changes, reset recruiter + job because
  // the prior selections may no longer be valid under the new employer scope.
  // The pipeline reload (triggered by selectedEmployer in the dep array of
  // loadPipeline) will refresh the dropdown lists automatically.
  const handleEmployerChange = (v) => {
    setSelectedEmployer(v);
    if (selectedRecruiter !== 'all') setSelectedRecruiter('all');
    if (selectedJob !== 'all') updateSelectedJob('all');
  };

  // Same cascade for recruiter → job (a recruiter from a different team
  // shouldn't keep a job from the previous filter context).
  const handleRecruiterChange = (v) => {
    setSelectedRecruiter(v);
    if (selectedJob !== 'all') updateSelectedJob('all');
  };

  // Delete application state
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [applicationToDelete, setApplicationToDelete] = useState(null);

  // Revenue stage dialogs
  const [showOfferDialog, setShowOfferDialog] = useState(false);
  const [showHiredDialog, setShowHiredDialog] = useState(false);
  const [showJoinDialog, setShowJoinDialog] = useState(false);
  const [selectedApp, setSelectedApp] = useState(null);
  const [offerForm, setOfferForm] = useState({ offered_ctc: '', offer_date: '' });
  const [hiredForm, setHiredForm] = useState({ date_of_joining: '' });
  const [joinForm, setJoinForm] = useState({ join_date: '' });
  const [stageLoading, setStageLoading] = useState(false);

  const openOfferDialog = (app) => {
    setSelectedApp(app);
    setOfferForm({ offered_ctc: app.offered_ctc || app.expected_salary || '', offer_date: new Date().toISOString().split('T')[0] });
    setShowOfferDialog(true);
  };

  const openHiredDialog = (app) => {
    setSelectedApp(app);
    setHiredForm({ date_of_joining: app.join_date || '' });
    setShowHiredDialog(true);
  };

  const openJoinDialog = (app) => {
    setSelectedApp(app);
    setJoinForm({ join_date: app.join_date || new Date().toISOString().split('T')[0] });
    setShowJoinDialog(true);
  };

  const handleProcessOffer = async () => {
    if (!offerForm.offered_ctc || parseFloat(offerForm.offered_ctc) <= 0) return toast.error('Offered CTC is required');
    if (!offerForm.offer_date) return toast.error('Offer date is required');
    setStageLoading(true);
    try {
      const res = await revenueAPI.offered(selectedApp.id, {
        offered_ctc: parseFloat(offerForm.offered_ctc),
        offer_date: offerForm.offer_date,
      });
      const d = res.data;
      let msg = `Offered: Revenue ₹${Math.round(d.revenue_amount).toLocaleString('en-IN')}`;
      if (d.slab_shift) msg += ' (slab changed!)';
      toast.success(msg);
      setShowOfferDialog(false);
      loadPipeline();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to process offer');
    } finally {
      setStageLoading(false);
    }
  };

  const handleProcessHired = async () => {
    if (!hiredForm.date_of_joining) return toast.error('Date of Joining (DOJ) is required');
    setStageLoading(true);
    try {
      await revenueAPI.hired(selectedApp.id, { date_of_joining: hiredForm.date_of_joining });
      toast.success('Hired: Offer accepted, DOJ set');
      setShowHiredDialog(false);
      loadPipeline();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to process hired stage');
    } finally {
      setStageLoading(false);
    }
  };

  const handleProcessJoin = async () => {
    if (!joinForm.join_date) return toast.error('Join date is required');
    setStageLoading(true);
    try {
      const res = await revenueAPI.joined(selectedApp.id, { join_date: joinForm.join_date });
      toast.success(`Joined: Revenue ₹${Math.round(res.data.final_revenue).toLocaleString('en-IN')} locked`);
      setShowJoinDialog(false);
      loadPipeline();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to process join');
    } finally {
      setStageLoading(false);
    }
  };

  const openDeleteDialog = (app) => {
    setApplicationToDelete(app);
    setShowDeleteDialog(true);
  };

  const handleDeleteApplication = async () => {
    if (!applicationToDelete) return;
    try {
      await applicationAPI.delete(applicationToDelete.id);
      toast.success(`${applicationToDelete.candidate_name} removed from pipeline`);
      setShowDeleteDialog(false);
      setApplicationToDelete(null);
      loadPipeline();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to remove candidate');
    }
  };

  // Phase 54.10 — distinguish FIRST load from re-fetch:
  //  • First load (no data yet)        → full-page spinner (existing behaviour)
  //  • Re-fetch on filter change       → keep table visible + overlay
  // This eliminates the 3-4s "page goes blank then comes back" jank
  // visible after selecting an employer / recruiter / job.
  const isFirstLoad = loading && totalApplications === 0 && Object.keys(pipelineData).length === 0;
  if (isFirstLoad) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6 relative" data-testid="admin-pipeline-page">
      {/* Re-fetch indicator (Phase 54.10) — small floating pill that appears
          while applying a filter, so the user gets immediate feedback even
          though the table itself stays in place. */}
      {loading && !isFirstLoad && (
        <div
          className="fixed top-4 right-4 z-50 flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 rounded-full shadow-md text-xs text-slate-700"
          data-testid="pipeline-refetch-indicator"
        >
          <div className="animate-spin rounded-full h-3 w-3 border-2 border-[#7CB342] border-t-transparent" />
          Updating…
        </div>
      )}
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Collective Pipeline</h1>
          <p className="text-slate-500 mt-1">Global view across all employers and recruiters</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="text-lg px-4 py-2">
            {totalApplications} Total Applications
          </Badge>
        </div>
      </div>

      {/* Deep-link banner — shown when user arrived via Jobs page eye-icon */}
      {selectedJob !== 'all' && (
        <div
          className="bg-[#DCFCE7] border border-[#7CB342]/40 rounded-lg px-4 py-2 flex items-center justify-between gap-3 text-sm"
          data-testid="pipeline-active-filter-banner"
        >
          <div className="flex items-center gap-2 text-[#3f6d1b]">
            <Briefcase className="w-4 h-4" />
            <span>
              Showing pipeline for:&nbsp;
              <strong>
                {filters.jobs.find((j) => j.id === selectedJob)?.title || 'Selected job'}
              </strong>
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="text-[#3f6d1b] hover:bg-[#7CB342]/10 h-7"
            onClick={() => updateSelectedJob('all')}
            data-testid="pipeline-clear-job-filter-btn"
          >
            Show all jobs
          </Button>
        </div>
      )}

      {/* Filters */}
      <Card className="border-slate-200">
        <CardHeader className="py-3 px-4 border-b border-slate-100 bg-slate-50/50">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-500" />
            <span className="font-medium text-slate-700">Filters</span>
            {(selectedEmployer !== 'all' || selectedRecruiter !== 'all' || selectedJob !== 'all' || pipelineWindow !== 'all') && (
              <button 
                onClick={clearFilters}
                className="ml-auto text-sm text-[#7CB342] hover:underline"
              >
                Clear all
              </button>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="space-y-1">
              <label className="text-sm text-slate-500 flex items-center gap-1">
                <Building2 className="w-3 h-3" /> Employer
              </label>
              <Select value={selectedEmployer} onValueChange={handleEmployerChange}>
                <SelectTrigger data-testid="filter-employer">
                  <SelectValue placeholder="All Employers" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Employers</SelectItem>
                  {filters.employers.map((emp) => (
                    <SelectItem key={emp.id} value={emp.id}>
                      {emp.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-sm text-slate-500 flex items-center gap-1">
                <Users className="w-3 h-3" /> Recruiter
              </label>
              <Select value={selectedRecruiter} onValueChange={handleRecruiterChange}>
                <SelectTrigger data-testid="filter-recruiter">
                  <SelectValue placeholder="All Recruiters" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Recruiters</SelectItem>
                  {filters.recruiters.map((rec) => (
                    <SelectItem key={rec.id} value={rec.id}>
                      {rec.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-sm text-slate-500 flex items-center gap-1">
                <Briefcase className="w-3 h-3" /> Job
              </label>
              <Select value={selectedJob} onValueChange={updateSelectedJob}>
                <SelectTrigger data-testid="filter-job">
                  <SelectValue placeholder="All Jobs" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Jobs</SelectItem>
                  {filters.jobs.map((job) => (
                    <SelectItem key={job.id} value={job.id}>
                      {job.company_name ? `${job.company_name} · ${job.title}` : job.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {/* v5.5.10 — Activity window: filters to applications whose stage CHANGED in window. */}
            <div className="space-y-1">
              <label className="text-sm text-slate-500 flex items-center gap-1">
                <CalendarClock className="w-3 h-3" /> Activity window
              </label>
              <Select value={pipelineWindow} onValueChange={updateWindow}>
                <SelectTrigger data-testid="filter-window">
                  <SelectValue placeholder="All Time" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" data-testid="window-opt-all">All Time</SelectItem>
                  <SelectItem value="week" data-testid="window-opt-week">This Week</SelectItem>
                  <SelectItem value="month" data-testid="window-opt-month">This Month</SelectItem>
                  <SelectItem value="quarter" data-testid="window-opt-quarter">This Quarter</SelectItem>
                  <SelectItem value="year" data-testid="window-opt-year">This Year</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stage Summary Cards */}
      <div className="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-10 gap-2 sm:gap-3">
        {STAGES.map((stage) => {
          const Icon = stage.icon;
          const count = stageCounts[stage.id] || 0;
          return (
            <Card key={stage.id} className={`border-l-4 ${stage.color.replace('bg-', 'border-')}`}>
              <CardContent className="p-3 text-center">
                <div className={`w-8 h-8 mx-auto rounded-full ${stage.bgLight} flex items-center justify-center mb-1`}>
                  <Icon className={`w-4 h-4 ${stage.color.replace('bg-', 'text-')}`} />
                </div>
                <div className="text-2xl font-bold text-slate-900">{count}</div>
                <div className="text-xs text-slate-500 truncate">{stage.label}</div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Pipeline Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {STAGES.filter(s => PRIMARY_STAGES.includes(s.id)).map((stage) => {
          const Icon = stage.icon;
          const applications = pipelineData[stage.id] || [];
          
          return (
            <Card key={stage.id} className="border-slate-200">
              <CardHeader className={`py-3 px-4 border-b ${stage.bgLight}`}>
                <CardTitle className="font-heading text-sm flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Icon className={`w-4 h-4 ${stage.color.replace('bg-', 'text-')}`} />
                    {stage.label}
                  </div>
                  <Badge variant="secondary" className="text-xs">
                    {applications.length}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-2 max-h-[500px] overflow-y-auto">
                {applications.length === 0 ? (
                  <div className="text-center py-8 text-slate-400 text-sm">
                    No candidates
                  </div>
                ) : (
                  <div className="space-y-2">
                    {applications.map((app) => (
                      <div 
                        key={app.id}
                        className="p-3 bg-white rounded-lg border border-slate-100 hover:shadow-sm transition-shadow group"
                      >
                        <div className="flex items-start gap-2">
                          <div className="w-8 h-8 rounded-full bg-[#DCFCE7] flex items-center justify-center flex-shrink-0">
                            <span className="text-[#7CB342] font-semibold text-xs">
                              {app.candidate_name?.charAt(0).toUpperCase() || '?'}
                            </span>
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-1">
                              <div className="font-medium text-sm text-slate-900 truncate">
                                {app.candidate_name}
                              </div>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity text-red-500 hover:text-red-600 hover:bg-red-50"
                                onClick={() => openDeleteDialog(app)}
                                title="Remove from pipeline"
                                data-testid={`delete-app-${app.id}`}
                              >
                                <Trash2 className="w-3 h-3" />
                              </Button>
                            </div>
                            <div className="text-xs text-slate-500 truncate">
                              {app.job_title}
                            </div>
                            {app.match_score > 0 && (
                              <Badge variant="outline" className="text-xs mt-1">
                                {app.match_score}% match
                              </Badge>
                            )}
                          </div>
                        </div>
                        <div className="mt-2 pt-2 border-t border-slate-50 flex items-center justify-between text-xs text-slate-500">
                          {app.current_salary && (
                            <span>{formatSalaryINR(app.current_salary)}</span>
                          )}
                          {app.notice_period && (
                            <span>{app.notice_period}</span>
                          )}
                          {app.candidate_id && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-5 px-1.5 text-xs text-orange-600 hover:text-orange-700 hover:bg-orange-50"
                              onClick={() => navigate(`../naukri-profile/${app.candidate_id}`)}
                              data-testid={`view-full-profile-${app.id}`}
                            >
                              <FileText className="w-3 h-3 mr-0.5" /> Profile
                            </Button>
                          )}
                          {app.resume_url && !app.candidate_id && (
                            <FileText className="w-3 h-3 text-green-500" title="Has Resume" />
                          )}
                        </div>
                        {/* Revenue actions */}
                        {stage.id === 'interview' && (
                          <Button
                            size="sm" variant="outline"
                            className="w-full mt-2 h-7 text-xs text-green-700 border-green-200 hover:bg-green-50"
                            onClick={() => openOfferDialog(app)}
                            data-testid={`offer-btn-${app.id}`}
                          >
                            <ArrowRight className="w-3 h-3 mr-1" /> Move to Offered
                          </Button>
                        )}
                        {stage.id === 'offered' && (
                          <div className="mt-2 space-y-1">
                            {app.offered_ctc && (
                              <div className="flex items-center gap-1 text-xs text-teal-700 bg-teal-50 rounded px-2 py-1">
                                <IndianRupee className="w-3 h-3" />
                                <span>CTC: {(app.offered_ctc / 100000).toFixed(1)}L</span>
                                {app.forecast_revenue && <span className="ml-auto font-medium">Rev: ₹{Math.round(app.forecast_revenue).toLocaleString('en-IN')}</span>}
                              </div>
                            )}
                            <Button
                              size="sm" variant="outline"
                              className="w-full h-7 text-xs text-emerald-700 border-emerald-200 hover:bg-emerald-50"
                              onClick={() => openHiredDialog(app)}
                              data-testid={`hired-btn-${app.id}`}
                            >
                              <UserCheck className="w-3 h-3 mr-1" /> Move to Hired
                            </Button>
                          </div>
                        )}
                        {stage.id === 'hired' && (
                          <div className="mt-2 space-y-1">
                            {app.offered_ctc && (
                              <div className="flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 rounded px-2 py-1">
                                <IndianRupee className="w-3 h-3" />
                                <span>CTC: {(app.offered_ctc / 100000).toFixed(1)}L</span>
                                {app.join_date && <span className="ml-auto">DOJ: {new Date(app.join_date).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>}
                              </div>
                            )}
                            <Button
                              size="sm" variant="outline"
                              className="w-full h-7 text-xs text-teal-700 border-teal-200 hover:bg-teal-50"
                              onClick={() => openJoinDialog(app)}
                              data-testid={`join-btn-${app.id}`}
                            >
                              <Lock className="w-3 h-3 mr-1" /> Move to Joined
                            </Button>
                          </div>
                        )}
                        {stage.id === 'joined' && app.offered_ctc && (
                          <div className="mt-2 flex items-center gap-1 text-xs text-green-700 bg-green-50 rounded px-2 py-1">
                            <Lock className="w-3 h-3" />
                            <span>CTC: {(app.offered_ctc / 100000).toFixed(1)}L</span>
                            <span className="ml-auto font-medium">Locked</span>
                          </div>
                        )}
                        {/* Quick-move chips (simple stages only; Offered/Hired/Joined need revenue dialogs) */}
                        <div className="mt-2 pt-2 border-t border-slate-100 flex flex-wrap gap-1">
                          {STAGES
                            .filter((s) => s.id !== stage.id && !['offered','hired','joined'].includes(s.id))
                            .map((s) => (
                              <button
                                key={s.id}
                                onClick={async () => {
                                  try {
                                    await applicationAPI.update(app.id, { stage: s.id });
                                    toast.success(`Moved to ${s.label}`);
                                    loadPipeline();
                                  } catch (e) { toast.error('Failed to update'); }
                                }}
                                className="px-1.5 py-0.5 text-[10px] rounded border border-slate-200 text-slate-600 hover:bg-slate-100 hover:border-slate-300 transition-colors"
                                data-testid={`admin-quick-move-${app.id}-${s.id}`}
                                title={`Move to ${s.label}`}
                              >
                                {s.label}
                              </button>
                            ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Secondary Stages (Rejected, On Hold, etc.) */}
      <Card className="border-slate-200">
        <CardHeader className="py-3 px-4 border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-sm">Other Stages</CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {STAGES.filter(s => !PRIMARY_STAGES.includes(s.id)).map((stage) => {
              const Icon = stage.icon;
              const applications = pipelineData[stage.id] || [];
              
              return (
                <div key={stage.id} className={`p-4 rounded-lg ${stage.bgLight}`}>
                  <div className="flex items-center gap-2 mb-3">
                    <Icon className={`w-4 h-4 ${stage.color.replace('bg-', 'text-')}`} />
                    <span className="font-medium text-sm text-slate-700">{stage.label}</span>
                    <Badge variant="secondary" className="ml-auto text-xs">
                      {applications.length}
                    </Badge>
                  </div>
                  <div className="space-y-1 max-h-32 overflow-y-auto">
                    {applications.slice(0, 5).map((app) => (
                      <div key={app.id} className="text-xs text-slate-600 truncate">
                        • {app.candidate_name} - {app.job_title}
                      </div>
                    ))}
                    {applications.length > 5 && (
                      <div className="text-xs text-slate-400">
                        +{applications.length - 5} more
                      </div>
                    )}
                    {applications.length === 0 && (
                      <div className="text-xs text-slate-400">No candidates</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <DeleteDialog open={showDeleteDialog} onClose={setShowDeleteDialog} app={applicationToDelete} onConfirm={handleDeleteApplication} />
      <OfferDialog open={showOfferDialog} onClose={setShowOfferDialog} app={selectedApp} form={offerForm} setForm={setOfferForm} onConfirm={handleProcessOffer} loading={stageLoading} />
      <HiredDialog open={showHiredDialog} onClose={setShowHiredDialog} app={selectedApp} form={hiredForm} setForm={setHiredForm} onConfirm={handleProcessHired} loading={stageLoading} />
      <JoinDialog open={showJoinDialog} onClose={setShowJoinDialog} app={selectedApp} form={joinForm} setForm={setJoinForm} onConfirm={handleProcessJoin} loading={stageLoading} />
    </div>
  );
}
