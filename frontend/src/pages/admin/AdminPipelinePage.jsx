import { useState, useEffect, useCallback } from 'react';
import { adminAPI, applicationAPI } from '../../lib/api';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import { DeleteDialog } from '../../components/admin/pipeline/PipelineDialogs';
import { 
  LayoutGrid, Users, CheckCircle, Clock, Award, UserCheck, 
  XCircle, Pause, Filter, Building2, Send,
  Briefcase, FileText, Trash2, AlertCircle, Lock,
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
  // Spec fix.docx (2026-09-15): the legacy "Activity window" preset dropdown
  // (All Time / This Week / …) has been removed. The two date pickers below
  // are the only date filter, they now sit at the TOP of the filter card,
  // and their values only push into the fetch once the user clicks Apply.
  //   • `windowFrom` / `windowTo`     — APPLIED values, feed the API call.
  //   • `draftFrom`  / `draftTo`      — user's typing, buffered until Apply.
  const [windowFrom, setWindowFrom] = useState(searchParams.get('window_from') || '');
  const [windowTo, setWindowTo] = useState(searchParams.get('window_to') || '');
  const [draftFrom, setDraftFrom] = useState(windowFrom);
  const [draftTo, setDraftTo] = useState(windowTo);

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

  // Apply the buffered date-picker values. Also persists them to the URL
  // so a refresh keeps the same window, and so pipeline links can be shared.
  const applyDateWindow = () => {
    setWindowFrom(draftFrom);
    setWindowTo(draftTo);
    const next = new URLSearchParams(searchParams);
    if (draftFrom) next.set('window_from', draftFrom); else next.delete('window_from');
    if (draftTo)   next.set('window_to',   draftTo);   else next.delete('window_to');
    // Kill any stale ?window=… left over from the removed preset dropdown.
    next.delete('window');
    setSearchParams(next, { replace: true });
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
      if (windowFrom) params.window_from = windowFrom;
      if (windowTo) params.window_to = windowTo;

      const res = await adminAPI.getPipeline(params);
      setPipelineData(res.data.pipeline);
      setStageCounts(res.data.stage_counts);
      setTotalApplications(res.data.total_applications);
    } catch (error) {
      toast.error('Failed to load pipeline data');
    } finally {
      setLoading(false);
    }
  }, [selectedEmployer, selectedRecruiter, selectedJob, windowFrom, windowTo]);

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
    setWindowFrom('');
    setWindowTo('');
    setDraftFrom('');
    setDraftTo('');
    const next = new URLSearchParams(searchParams);
    next.delete('window_from');
    next.delete('window_to');
    next.delete('window');
    setSearchParams(next, { replace: true });
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

  // Stage movement is unconditional — a move is a move, no CTC or revenue
  // is asked for on the board (user spec, Sep 2026). Money is entered once,
  // on the Joining List.
  const moveStage = async (app, stageId, label) => {
    try {
      await applicationAPI.update(app.id, { stage: stageId });
      toast.success(`Moved to ${label}`);
      loadPipeline();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to update');
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
            {(selectedEmployer !== 'all' || selectedRecruiter !== 'all' || selectedJob !== 'all' || windowFrom || windowTo) && (
              <button
                onClick={clearFilters}
                className="ml-auto text-sm text-[#7CB342] hover:underline"
                data-testid="clear-filters-btn"
              >
                Clear all
              </button>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-4 space-y-4">
          {/* Date window — TOP of the filter panel (fix.docx 2026-09-15).
              User buffers From/To in the two pickers; the fetch only fires
              when they hit Apply, so mistyping a year no longer stalls the
              page mid-keystroke. */}
          <div className="space-y-2" data-testid="pipeline-date-window">
            <label className="text-sm text-slate-500 flex items-center gap-1">
              <CalendarClock className="w-3 h-3" /> Date window
            </label>
            <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-end">
              <div className="flex-1">
                <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-0.5">From</div>
                <input
                  type="date"
                  value={draftFrom}
                  onChange={(e) => setDraftFrom(e.target.value)}
                  className="w-full rounded border border-slate-200 text-sm px-2 py-1.5"
                  data-testid="filter-window-from"
                />
              </div>
              <div className="flex-1">
                <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-0.5">To</div>
                <input
                  type="date"
                  value={draftTo}
                  onChange={(e) => setDraftTo(e.target.value)}
                  className="w-full rounded border border-slate-200 text-sm px-2 py-1.5"
                  data-testid="filter-window-to"
                />
              </div>
              <Button
                onClick={applyDateWindow}
                className="bg-[#7CB342] hover:bg-[#689F38] text-white sm:w-32"
                data-testid="apply-window-btn"
                disabled={draftFrom === windowFrom && draftTo === windowTo}
              >
                Apply
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                        {/* Quick-move chips — every stage, no conditions */}
                        <div className="mt-2 pt-2 border-t border-slate-100 flex flex-wrap gap-1">
                          {STAGES
                            .filter((s) => s.id !== stage.id)
                            .map((s) => (
                              <button
                                key={s.id}
                                onClick={() => moveStage(app, s.id, s.label)}
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
    </div>
  );
}
