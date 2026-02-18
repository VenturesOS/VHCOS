import { useState, useEffect } from 'react';
import { adminAPI, applicationAPI, revenueAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { 
  LayoutGrid, Users, CheckCircle, Clock, Award, UserCheck, 
  XCircle, Pause, TrendingDown, UserX, Filter, Building2,
  Briefcase, FileText, Trash2, AlertCircle, IndianRupee, Lock, ArrowRight
} from 'lucide-react';

// Stage configuration
const STAGES = [
  { id: 'applied', label: 'Applied', color: 'bg-blue-500', icon: Users, bgLight: 'bg-blue-50' },
  { id: 'shortlisted', label: 'Shortlisted', color: 'bg-amber-500', icon: CheckCircle, bgLight: 'bg-amber-50' },
  { id: 'interview', label: 'Interview', color: 'bg-purple-500', icon: Clock, bgLight: 'bg-purple-50' },
  { id: 'offered', label: 'Offered', color: 'bg-green-500', icon: Award, bgLight: 'bg-green-50' },
  { id: 'joined', label: 'Joined', color: 'bg-teal-500', icon: Lock, bgLight: 'bg-teal-50' },
  { id: 'hired', label: 'Hired', color: 'bg-emerald-500', icon: UserCheck, bgLight: 'bg-emerald-50' },
  { id: 'rejected', label: 'Rejected', color: 'bg-red-500', icon: XCircle, bgLight: 'bg-red-50' },
  { id: 'on_hold', label: 'On Hold', color: 'bg-gray-500', icon: Pause, bgLight: 'bg-gray-50' },
  { id: 'over_budget', label: 'Over Budget', color: 'bg-orange-500', icon: TrendingDown, bgLight: 'bg-orange-50' },
  { id: 'not_qualified', label: 'Not Qualified', color: 'bg-rose-500', icon: UserX, bgLight: 'bg-rose-50' },
];

const PRIMARY_STAGES = ['applied', 'shortlisted', 'interview', 'offered', 'joined'];

export default function AdminPipelinePage() {
  const [loading, setLoading] = useState(true);
  const [pipelineData, setPipelineData] = useState({});
  const [stageCounts, setStageCounts] = useState({});
  const [totalApplications, setTotalApplications] = useState(0);
  const [filters, setFilters] = useState({ employers: [], recruiters: [], jobs: [] });
  
  // Filter state
  const [selectedEmployer, setSelectedEmployer] = useState('all');
  const [selectedRecruiter, setSelectedRecruiter] = useState('all');
  const [selectedJob, setSelectedJob] = useState('all');

  useEffect(() => {
    loadPipeline();
  }, [selectedEmployer, selectedRecruiter, selectedJob]);

  const loadPipeline = async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEmployer !== 'all') params.employer_id = selectedEmployer;
      if (selectedRecruiter !== 'all') params.recruiter_id = selectedRecruiter;
      if (selectedJob !== 'all') params.job_id = selectedJob;
      
      const res = await adminAPI.getPipeline(params);
      setPipelineData(res.data.pipeline);
      setStageCounts(res.data.stage_counts);
      setTotalApplications(res.data.total_applications);
      setFilters(res.data.filters);
    } catch (error) {
      toast.error('Failed to load pipeline data');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const clearFilters = () => {
    setSelectedEmployer('all');
    setSelectedRecruiter('all');
    setSelectedJob('all');
  };

  // Delete application state
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [applicationToDelete, setApplicationToDelete] = useState(null);

  // Revenue stage dialogs
  const [showOfferDialog, setShowOfferDialog] = useState(false);
  const [showJoinDialog, setShowJoinDialog] = useState(false);
  const [selectedApp, setSelectedApp] = useState(null);
  const [offerForm, setOfferForm] = useState({ offered_ctc: '', offer_date: '' });
  const [joinForm, setJoinForm] = useState({ join_date: '' });
  const [stageLoading, setStageLoading] = useState(false);

  const openOfferDialog = (app) => {
    setSelectedApp(app);
    setOfferForm({ offered_ctc: app.offered_ctc || app.expected_salary || '', offer_date: new Date().toISOString().split('T')[0] });
    setShowOfferDialog(true);
  };

  const openJoinDialog = (app) => {
    setSelectedApp(app);
    setJoinForm({ join_date: new Date().toISOString().split('T')[0] });
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="admin-pipeline-page">
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

      {/* Filters */}
      <Card className="border-slate-200">
        <CardHeader className="py-3 px-4 border-b border-slate-100 bg-slate-50/50">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-500" />
            <span className="font-medium text-slate-700">Filters</span>
            {(selectedEmployer !== 'all' || selectedRecruiter !== 'all' || selectedJob !== 'all') && (
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1">
              <label className="text-sm text-slate-500 flex items-center gap-1">
                <Building2 className="w-3 h-3" /> Employer
              </label>
              <Select value={selectedEmployer} onValueChange={setSelectedEmployer}>
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
              <Select value={selectedRecruiter} onValueChange={setSelectedRecruiter}>
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
              <Select value={selectedJob} onValueChange={setSelectedJob}>
                <SelectTrigger data-testid="filter-job">
                  <SelectValue placeholder="All Jobs" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Jobs</SelectItem>
                  {filters.jobs.map((job) => (
                    <SelectItem key={job.id} value={job.id}>
                      {job.title}
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
                          {app.resume_url && (
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

      {/* Delete Application Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading text-red-600 flex items-center gap-2">
              <AlertCircle className="w-5 h-5" /> Remove from Pipeline
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to remove <strong>{applicationToDelete?.candidate_name}</strong> from the pipeline?
            </DialogDescription>
          </DialogHeader>
          <div className="py-4 space-y-3">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
              <p className="text-sm text-amber-700">
                <strong>Note:</strong> This will only remove the candidate from this job&apos;s pipeline.
              </p>
              <ul className="text-sm text-amber-600 mt-2 space-y-1 list-disc list-inside">
                <li>The candidate will NOT be deleted from the data bank</li>
                <li>Historical data will be preserved for audit</li>
                <li>This action can be undone by re-adding the candidate</li>
              </ul>
            </div>
            {applicationToDelete && (
              <div className="text-sm text-slate-600">
                <p><strong>Job:</strong> {applicationToDelete.job_title}</p>
                <p><strong>Current Stage:</strong> {applicationToDelete.stage}</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteApplication}
              data-testid="confirm-delete-application-btn"
            >
              Remove from Pipeline
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Offer Dialog */}
      <Dialog open={showOfferDialog} onOpenChange={setShowOfferDialog}>
        <DialogContent data-testid="offer-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Award className="w-5 h-5 text-green-600" /> Process Offer
            </DialogTitle>
            <DialogDescription>
              {selectedApp?.candidate_name} — {selectedApp?.job_title}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label className="text-sm font-medium">Offered CTC (Annual, INR) *</Label>
              <Input
                type="number" min="0" step="1000" placeholder="e.g. 1800000"
                value={offerForm.offered_ctc}
                onChange={e => setOfferForm(p => ({ ...p, offered_ctc: e.target.value }))}
                data-testid="offer-ctc-input"
              />
              {offerForm.offered_ctc > 0 && (
                <p className="text-xs text-gray-500 mt-1">
                  ₹{(parseFloat(offerForm.offered_ctc) / 100000).toFixed(1)} LPA
                </p>
              )}
            </div>
            <div>
              <Label className="text-sm font-medium">Offer Date *</Label>
              <Input
                type="date"
                value={offerForm.offer_date}
                onChange={e => setOfferForm(p => ({ ...p, offer_date: e.target.value }))}
                data-testid="offer-date-input"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowOfferDialog(false)}>Cancel</Button>
            <Button onClick={handleProcessOffer} disabled={stageLoading} className="bg-green-600 hover:bg-green-700" data-testid="confirm-offer-btn">
              {stageLoading ? 'Processing...' : 'Confirm Offer'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Join Dialog */}
      <Dialog open={showJoinDialog} onOpenChange={setShowJoinDialog}>
        <DialogContent data-testid="join-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Lock className="w-5 h-5 text-teal-600" /> Process Joining
            </DialogTitle>
            <DialogDescription>
              {selectedApp?.candidate_name} — Offered CTC: ₹{selectedApp?.offered_ctc ? (selectedApp.offered_ctc / 100000).toFixed(1) + 'L' : '—'}
              <br />
              <span className="text-amber-600 text-xs font-medium">Revenue will be locked after this action.</span>
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label className="text-sm font-medium">Join Date *</Label>
              <Input
                type="date"
                value={joinForm.join_date}
                onChange={e => setJoinForm({ join_date: e.target.value })}
                data-testid="join-date-input"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowJoinDialog(false)}>Cancel</Button>
            <Button onClick={handleProcessJoin} disabled={stageLoading} className="bg-teal-600 hover:bg-teal-700" data-testid="confirm-join-btn">
              {stageLoading ? 'Processing...' : 'Confirm Joining'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
