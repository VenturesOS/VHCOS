import { useState, useEffect } from 'react';
import { governanceAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { 
  Clock, CheckCircle, XCircle, PauseCircle, 
  Briefcase, MapPin, User, Calendar, History,
  AlertCircle, ChevronDown, ChevronUp
} from 'lucide-react';

export default function JobApprovalPage() {
  const [pendingJobs, setPendingJobs] = useState([]);
  const [allJobs, setAllJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAction, setShowAction] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [actionType, setActionType] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [expandedHistory, setExpandedHistory] = useState({});

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [pendingRes, allJobsRes] = await Promise.all([
        governanceAPI.getPendingJobs(),
        jobAPI.getAll(),
      ]);
      setPendingJobs(pendingRes.data);
      setAllJobs(allJobsRes.data);
    } catch (error) {
      toast.error('Failed to load jobs');
    } finally {
      setLoading(false);
    }
  };

  const openActionDialog = (job, action) => {
    setSelectedJob(job);
    setActionType(action);
    setReason('');
    setShowAction(true);
  };

  const handleAction = async () => {
    if (!selectedJob || !actionType) return;
    
    setSubmitting(true);
    try {
      const statusMap = {
        approve: 'active',
        reject: 'closed',
        hold: 'on_hold',
      };
      
      await governanceAPI.transitionJob(
        selectedJob.id, 
        statusMap[actionType], 
        reason || `Job ${actionType}d by employer`
      );
      
      toast.success(`Job ${actionType}d successfully`);
      setShowAction(false);
      setSelectedJob(null);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || `Failed to ${actionType} job`);
    } finally {
      setSubmitting(false);
    }
  };

  const toggleHistory = (jobId) => {
    setExpandedHistory(prev => ({
      ...prev,
      [jobId]: !prev[jobId]
    }));
  };

  const getStatusBadge = (status) => {
    const styles = {
      draft: 'bg-slate-100 text-slate-600',
      pending_approval: 'bg-amber-100 text-amber-700',
      active: 'bg-green-100 text-green-700',
      on_hold: 'bg-orange-100 text-orange-700',
      closed: 'bg-red-100 text-red-700',
      archived: 'bg-gray-100 text-gray-600',
    };
    return styles[status] || 'bg-slate-100 text-slate-600';
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Separate jobs by status for overview
  const jobsByStatus = {
    pending_approval: allJobs.filter(j => j.status === 'pending_approval'),
    active: allJobs.filter(j => j.status === 'active'),
    on_hold: allJobs.filter(j => j.status === 'on_hold'),
    closed: allJobs.filter(j => j.status === 'closed'),
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="job-approval-page">
      {/* Header */}
      <div>
        <h1 className="font-heading text-3xl font-bold text-slate-900">Job Approvals</h1>
        <p className="text-slate-500 mt-1">Review and approve job postings from your team</p>
      </div>

      {/* Status Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
              <Clock className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-amber-700">{jobsByStatus.pending_approval.length}</p>
              <p className="text-xs text-amber-600">Pending Approval</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-green-200 bg-green-50">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
              <CheckCircle className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-green-700">{jobsByStatus.active.length}</p>
              <p className="text-xs text-green-600">Active</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-orange-200 bg-orange-50">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-orange-100 flex items-center justify-center">
              <PauseCircle className="w-5 h-5 text-orange-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-orange-700">{jobsByStatus.on_hold.length}</p>
              <p className="text-xs text-orange-600">On Hold</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
              <XCircle className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-red-700">{jobsByStatus.closed.length}</p>
              <p className="text-xs text-red-600">Closed</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Pending Approval Queue */}
      <Card className="border-amber-200">
        <CardHeader className="border-b border-amber-100 bg-amber-50/50">
          <CardTitle className="font-heading flex items-center gap-2 text-amber-700">
            <AlertCircle className="w-5 h-5" />
            Pending Approval Queue ({pendingJobs.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {pendingJobs.length === 0 ? (
            <div className="text-center py-12">
              <CheckCircle className="w-12 h-12 text-green-300 mx-auto mb-3" />
              <p className="text-slate-500">No jobs pending approval</p>
              <p className="text-sm text-slate-400 mt-1">All caught up!</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {pendingJobs.map((job) => (
                <JobApprovalCard
                  key={job.id}
                  job={job}
                  onApprove={() => openActionDialog(job, 'approve')}
                  onReject={() => openActionDialog(job, 'reject')}
                  onHold={() => openActionDialog(job, 'hold')}
                  expandedHistory={expandedHistory[job.id]}
                  onToggleHistory={() => toggleHistory(job.id)}
                  formatDate={formatDate}
                  getStatusBadge={getStatusBadge}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* All Jobs Overview */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading flex items-center gap-2">
            <Briefcase className="w-5 h-5 text-[#7CB342]" />
            All Jobs Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Job Title</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Location</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Created By</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Status</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Applicants</th>
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Actions</th>
                </tr>
              </thead>
              <tbody>
                {allJobs.slice(0, 10).map((job) => (
                  <tr key={job.id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-3 px-4">
                      <p className="font-medium text-slate-900">{job.title}</p>
                      <p className="text-xs text-slate-400">{job.job_type}</p>
                    </td>
                    <td className="py-3 px-4 text-slate-600">{job.location}</td>
                    <td className="py-3 px-4 text-slate-600">{job.created_by_name || 'Unknown'}</td>
                    <td className="py-3 px-4">
                      <Badge className={getStatusBadge(job.status)}>
                        {job.status?.replace('_', ' ')}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-slate-600">{job.applicant_count || 0}</td>
                    <td className="py-3 px-4">
                      {job.status === 'pending_approval' && (
                        <Button 
                          size="sm" 
                          className="bg-[#7CB342] hover:bg-[#689F38] text-xs"
                          onClick={() => openActionDialog(job, 'approve')}
                        >
                          Review
                        </Button>
                      )}
                      {job.status === 'active' && (
                        <Button 
                          size="sm" 
                          variant="outline"
                          className="text-xs"
                          onClick={() => openActionDialog(job, 'hold')}
                        >
                          Put on Hold
                        </Button>
                      )}
                      {job.status === 'on_hold' && (
                        <Button 
                          size="sm" 
                          variant="outline"
                          className="text-xs text-green-600 border-green-300"
                          onClick={() => openActionDialog(job, 'approve')}
                        >
                          Reactivate
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Action Dialog */}
      <Dialog open={showAction} onOpenChange={setShowAction}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              {actionType === 'approve' && <CheckCircle className="w-5 h-5 text-green-600" />}
              {actionType === 'reject' && <XCircle className="w-5 h-5 text-red-600" />}
              {actionType === 'hold' && <PauseCircle className="w-5 h-5 text-orange-600" />}
              {actionType === 'approve' && 'Approve Job'}
              {actionType === 'reject' && 'Reject Job'}
              {actionType === 'hold' && 'Put Job on Hold'}
            </DialogTitle>
            <DialogDescription>
              {actionType === 'approve' && 'This job will become active and visible to candidates.'}
              {actionType === 'reject' && 'This job will be closed and not visible to candidates.'}
              {actionType === 'hold' && 'This job will be paused and not visible to candidates.'}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="bg-slate-50 p-4 rounded-lg mb-4">
              <p className="font-medium text-slate-900">{selectedJob?.title}</p>
              <p className="text-sm text-slate-500">{selectedJob?.location} • {selectedJob?.job_type}</p>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">
                Reason {actionType !== 'approve' && '(recommended)'}
              </label>
              <Textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={`Enter reason for ${actionType}ing this job...`}
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAction(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button
              onClick={handleAction}
              disabled={submitting}
              className={
                actionType === 'approve' ? 'bg-green-600 hover:bg-green-700' :
                actionType === 'reject' ? 'bg-red-600 hover:bg-red-700' :
                'bg-orange-600 hover:bg-orange-700'
              }
              data-testid={`confirm-${actionType}-btn`}
            >
              {submitting ? 'Processing...' : `${actionType.charAt(0).toUpperCase() + actionType.slice(1)} Job`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Job Approval Card Component
function JobApprovalCard({ job, onApprove, onReject, onHold, expandedHistory, onToggleHistory, formatDate, getStatusBadge }) {
  return (
    <div className="p-6 hover:bg-slate-50 transition-colors">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
        {/* Job Info */}
        <div className="flex items-start gap-4 flex-1">
          <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
            <Briefcase className="w-6 h-6 text-amber-600" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-heading font-semibold text-lg text-slate-900">{job.title}</h3>
            <div className="flex flex-wrap items-center gap-3 mt-2 text-sm text-slate-500">
              <span className="flex items-center gap-1">
                <MapPin className="w-4 h-4" /> {job.location}
              </span>
              <span className="flex items-center gap-1">
                <User className="w-4 h-4" /> {job.created_by_name || 'Unknown'}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="w-4 h-4" /> {formatDate(job.created_at)}
              </span>
            </div>
            {job.public_company_alias && (
              <p className="text-sm text-slate-400 mt-1">
                Public alias: <span className="font-medium">{job.public_company_alias}</span>
              </p>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <Button
            onClick={onApprove}
            className="bg-green-600 hover:bg-green-700"
            data-testid={`approve-job-${job.id}`}
          >
            <CheckCircle className="w-4 h-4 mr-2" /> Approve
          </Button>
          <Button
            variant="outline"
            onClick={onHold}
            className="text-orange-600 border-orange-300 hover:bg-orange-50"
            data-testid={`hold-job-${job.id}`}
          >
            <PauseCircle className="w-4 h-4 mr-2" /> Hold
          </Button>
          <Button
            variant="outline"
            onClick={onReject}
            className="text-red-600 border-red-300 hover:bg-red-50"
            data-testid={`reject-job-${job.id}`}
          >
            <XCircle className="w-4 h-4 mr-2" /> Reject
          </Button>
        </div>
      </div>

      {/* Audit History Toggle */}
      {job.approval_history && job.approval_history.length > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-4">
          <button
            onClick={onToggleHistory}
            className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700"
          >
            <History className="w-4 h-4" />
            <span>Approval History ({job.approval_history.length})</span>
            {expandedHistory ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          
          {expandedHistory && (
            <div className="mt-3 space-y-2">
              {job.approval_history.map((entry, idx) => (
                <div key={idx} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg text-sm">
                  <Badge className={getStatusBadge(entry.status || entry.to_status)}>
                    {(entry.status || entry.to_status)?.replace('_', ' ')}
                  </Badge>
                  <div className="flex-1">
                    <p className="text-slate-600">
                      by <span className="font-medium">{entry.changed_by_name || 'Unknown'}</span>
                      {entry.changed_by_role && ` (${entry.changed_by_role})`}
                    </p>
                    {entry.reason && <p className="text-slate-500 text-xs mt-1">{entry.reason}</p>}
                  </div>
                  <span className="text-xs text-slate-400">{formatDate(entry.timestamp)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
