import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { jobAPI, mandateAPI } from '../../lib/api';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { Checkbox } from '../../components/ui/checkbox';
import { toast } from 'sonner';
import { Search, Briefcase, MapPin, Clock, Users, Plus, Edit2, Trash2, Eye, Globe, GlobeLock, AlertTriangle, History, UserPlus, UserCheck } from 'lucide-react';

export default function EmployerJobsPage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();
  
  // Career Page Status Control
  const [showCareerPageDialog, setShowCareerPageDialog] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [careerPageAction, setCareerPageAction] = useState(''); // 'live' or 'removed'
  const [careerPageReason, setCareerPageReason] = useState('');
  const [updatingCareerPage, setUpdatingCareerPage] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [careerPageHistory, setCareerPageHistory] = useState([]);

  // Recruiter Assignment State
  const [showAssignDialog, setShowAssignDialog] = useState(false);
  const [assigningJob, setAssigningJob] = useState(null);
  const [teamRecruiters, setTeamRecruiters] = useState([]);
  const [selectedRecruiters, setSelectedRecruiters] = useState([]);
  const [loadingRecruiters, setLoadingRecruiters] = useState(false);
  const [assigningInProgress, setAssigningInProgress] = useState(false);
  const [showAssignmentHistory, setShowAssignmentHistory] = useState(false);
  const [assignmentHistory, setAssignmentHistory] = useState([]);

  useEffect(() => {
    loadJobs();
  }, []);

  const loadJobs = async () => {
    try {
      const res = await jobAPI.getAll();
      setJobs(res.data);
    } catch (error) {
      toast.error('Failed to load jobs');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (jobId) => {
    if (!window.confirm('Are you sure you want to delete this job?')) return;
    try {
      await jobAPI.delete(jobId);
      toast.success('Job deleted');
      loadJobs();
    } catch (error) {
      toast.error('Failed to delete job');
    }
  };

  const handleToggleStatus = async (job) => {
    try {
      await jobAPI.update(job.id, { status: job.status === 'active' ? 'closed' : 'active' });
      toast.success('Job status updated');
      loadJobs();
    } catch (error) {
      toast.error('Failed to update status');
    }
  };

  // Career Page Control
  const openCareerPageDialog = (job, action) => {
    setSelectedJob(job);
    setCareerPageAction(action);
    setCareerPageReason('');
    setShowCareerPageDialog(true);
  };

  const handleCareerPageUpdate = async () => {
    if (!selectedJob) return;
    
    setUpdatingCareerPage(true);
    try {
      await jobAPI.updateCareerPageStatus(selectedJob.id, careerPageAction, careerPageReason || undefined);
      toast.success(
        careerPageAction === 'live' 
          ? 'Job posted to career page' 
          : 'Job removed from career page'
      );
      setShowCareerPageDialog(false);
      loadJobs();
    } catch (error) {
      const detail = error.response?.data?.detail;
      toast.error(detail || 'Failed to update career page status');
    } finally {
      setUpdatingCareerPage(false);
    }
  };

  const openHistoryDialog = async (job) => {
    try {
      const res = await jobAPI.getCareerPageHistory(job.id);
      setCareerPageHistory(res.data.history || []);
      setSelectedJob(job);
      setShowHistoryDialog(true);
    } catch (error) {
      toast.error('Failed to load history');
    }
  };

  // Recruiter Assignment Functions
  const openAssignDialog = async (job) => {
    setAssigningJob(job);
    setSelectedRecruiters(job.assigned_recruiters || []);
    setShowAssignDialog(true);
    setLoadingRecruiters(true);
    
    try {
      const res = await mandateAPI.getTeamRecruiters();
      setTeamRecruiters(res.data.recruiters || []);
    } catch (error) {
      toast.error('Failed to load team recruiters');
      setTeamRecruiters([]);
    } finally {
      setLoadingRecruiters(false);
    }
  };

  const handleRecruiterToggle = (recruiterId) => {
    setSelectedRecruiters(prev => 
      prev.includes(recruiterId)
        ? prev.filter(id => id !== recruiterId)
        : [...prev, recruiterId]
    );
  };

  const handleAssignRecruiters = async () => {
    if (!assigningJob) return;
    
    setAssigningInProgress(true);
    try {
      await mandateAPI.assignRecruiters(assigningJob.id, selectedRecruiters);
      toast.success(
        selectedRecruiters.length === 0 
          ? 'All recruiters unassigned from mandate' 
          : `${selectedRecruiters.length} recruiter(s) assigned to mandate`
      );
      setShowAssignDialog(false);
      loadJobs();
    } catch (error) {
      const detail = error.response?.data?.detail;
      toast.error(detail || 'Failed to assign recruiters');
    } finally {
      setAssigningInProgress(false);
    }
  };

  const openAssignmentHistoryDialog = async (job) => {
    try {
      const res = await mandateAPI.getAssignments(job.id);
      setAssignmentHistory(res.data.assignment_history || []);
      setAssigningJob(job);
      setShowAssignmentHistory(true);
    } catch (error) {
      toast.error('Failed to load assignment history');
    }
  };

  const filteredJobs = jobs.filter((job) =>
    job.title.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="employer-jobs-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">My Jobs</h1>
          <p className="text-slate-500 mt-1">Manage your job postings</p>
        </div>
        <div className="flex gap-3">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              placeholder="Search jobs..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
            />
          </div>
          <Link to="/employer/jobs/new">
            <Button className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="create-job-btn">
              <Plus className="w-4 h-4 mr-2" /> New Job
            </Button>
          </Link>
        </div>
      </div>

      <div className="grid gap-4">
        {filteredJobs.map((job) => (
          <Card key={job.id} className="border-slate-200 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center shrink-0">
                    <Briefcase className="w-6 h-6 text-[#7CB342]" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-heading font-semibold text-lg text-slate-900">{job.title}</h3>
                      {/* Career Page Status Badge */}
                      {job.career_page_status === 'live' && (
                        <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full flex items-center gap-1">
                          <Globe className="w-3 h-3" /> Live on Career Page
                        </span>
                      )}
                      {/* Assigned Recruiters Badge */}
                      {job.assigned_recruiters?.length > 0 && (
                        <span 
                          className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full flex items-center gap-1 cursor-pointer hover:bg-blue-200"
                          onClick={() => openAssignmentHistoryDialog(job)}
                          data-testid={`assigned-count-${job.id}`}
                        >
                          <UserCheck className="w-3 h-3" /> {job.assigned_recruiters.length} Assigned
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-slate-500">
                      <span className="flex items-center gap-1">
                        <MapPin className="w-4 h-4" /> {job.location}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-4 h-4" /> {job.job_type}
                      </span>
                      <span className="flex items-center gap-1">
                        <Users className="w-4 h-4" /> {job.applicant_count} applicants
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {/* Assign Recruiters Button - Only for active/pending jobs */}
                  {(job.status === 'active' || job.status === 'pending_approval') && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-blue-600 border-blue-300 hover:bg-blue-50"
                      onClick={() => openAssignDialog(job)}
                      data-testid={`assign-recruiters-${job.id}`}
                    >
                      <UserPlus className="w-4 h-4 mr-1" /> 
                      {job.assigned_recruiters?.length > 0 ? 'Manage Recruiters' : 'Assign Recruiter'}
                    </Button>
                  )}
                  
                  <Button
                    variant="default"
                    size="sm"
                    className="bg-[#7CB342] hover:bg-[#689F38]"
                    onClick={() => navigate(`/employer/jobs/${job.id}/applicants`)}
                    data-testid={`view-applicants-${job.id}`}
                  >
                    <Eye className="w-4 h-4 mr-1" /> View Applicants
                  </Button>
                  
                  {/* Career Page Controls */}
                  {job.status === 'active' && (
                    job.career_page_status === 'live' ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-amber-600 border-amber-300 hover:bg-amber-50"
                        onClick={() => openCareerPageDialog(job, 'removed')}
                        data-testid={`remove-career-page-${job.id}`}
                      >
                        <GlobeLock className="w-4 h-4 mr-1" /> Remove from Career Page
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-green-600 border-green-300 hover:bg-green-50"
                        onClick={() => openCareerPageDialog(job, 'live')}
                        data-testid={`post-career-page-${job.id}`}
                      >
                        <Globe className="w-4 h-4 mr-1" /> Post to Career Page
                      </Button>
                    )
                  )}
                  
                  {/* Career Page History */}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openHistoryDialog(job)}
                    title="Career Page History"
                  >
                    <History className="w-4 h-4" />
                  </Button>
                  
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleToggleStatus(job)}
                  >
                    {job.status === 'active' ? 'Close' : 'Reopen'}
                  </Button>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${job.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}`}>
                    {job.status}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-red-600 hover:bg-red-50"
                    onClick={() => handleDelete(job.id)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {filteredJobs.length === 0 && (
          <div className="empty-state">
            <Briefcase className="empty-state-icon" />
            <p className="empty-state-title">No jobs posted</p>
            <p className="empty-state-text">Create your first job posting</p>
            <Link to="/employer/jobs/new">
              <Button className="mt-4 bg-[#7CB342] hover:bg-[#689F38]">
                <Plus className="w-4 h-4 mr-2" /> Post a Job
              </Button>
            </Link>
          </div>
        )}
      </div>

      {/* Career Page Status Dialog */}
      <Dialog open={showCareerPageDialog} onOpenChange={setShowCareerPageDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              {careerPageAction === 'live' ? (
                <>
                  <Globe className="w-5 h-5 text-green-600" />
                  Post to Career Page
                </>
              ) : (
                <>
                  <GlobeLock className="w-5 h-5 text-amber-600" />
                  Remove from Career Page
                </>
              )}
            </DialogTitle>
            <DialogDescription>
              {careerPageAction === 'live' 
                ? "This job will be visible on the public career page. Are you sure?"
                : "This job will be removed from the public career page but will remain active internally."
              }
            </DialogDescription>
          </DialogHeader>

          {selectedJob && (
            <div className="space-y-4">
              <div className="p-4 bg-slate-50 rounded-lg">
                <p className="font-medium">{selectedJob.title}</p>
                <p className="text-sm text-slate-500">{selectedJob.company_name} • {selectedJob.location}</p>
              </div>

              {careerPageAction === 'live' && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                  <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
                  <p className="text-sm text-amber-700">
                    Posting to career page will make this job publicly visible. Not all jobs need to be on the career page.
                  </p>
                </div>
              )}

              <div className="space-y-2">
                <Label>Reason (optional)</Label>
                <Textarea
                  value={careerPageReason}
                  onChange={(e) => setCareerPageReason(e.target.value)}
                  placeholder={careerPageAction === 'live' 
                    ? "e.g., Approved for public posting..."
                    : "e.g., Position filled internally..."
                  }
                  rows={2}
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCareerPageDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCareerPageUpdate}
              disabled={updatingCareerPage}
              className={careerPageAction === 'live' 
                ? "bg-green-600 hover:bg-green-700"
                : "bg-amber-600 hover:bg-amber-700"
              }
              data-testid="confirm-career-page-btn"
            >
              {updatingCareerPage 
                ? 'Processing...' 
                : careerPageAction === 'live' ? 'Post to Career Page' : 'Remove from Career Page'
              }
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Career Page History Dialog */}
      <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <History className="w-5 h-5 text-slate-600" />
              Career Page History
            </DialogTitle>
          </DialogHeader>
          
          {selectedJob && (
            <div className="space-y-4">
              <div className="p-3 bg-slate-50 rounded-lg">
                <p className="font-medium text-sm">{selectedJob.title}</p>
                <p className="text-xs text-slate-500">
                  Current Status: {selectedJob.career_page_status === 'live' ? 'Live on Career Page' : 'Not Posted'}
                </p>
              </div>

              <div className="space-y-2 max-h-64 overflow-y-auto">
                {careerPageHistory.length > 0 ? (
                  careerPageHistory.map((entry, idx) => (
                    <div key={idx} className="p-3 bg-slate-50 rounded-lg text-sm border-l-4 border-slate-300">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium">
                          {entry.from_status || 'not_posted'} → {entry.to_status}
                        </span>
                        <span className="text-xs text-slate-400">
                          {new Date(entry.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-slate-600">
                        By: {entry.changed_by_name} ({entry.changed_by_role})
                      </p>
                      {entry.reason && (
                        <p className="text-slate-500 mt-1 italic">&ldquo;{entry.reason}&rdquo;</p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-slate-400 text-sm text-center py-4">No status changes recorded</p>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Assign Recruiters Dialog */}
      <Dialog open={showAssignDialog} onOpenChange={setShowAssignDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <UserPlus className="w-5 h-5 text-blue-600" />
              Assign Recruiters to Mandate
            </DialogTitle>
            <DialogDescription>
              Select recruiters from your team to work on this mandate. Only assigned recruiters will see this job.
            </DialogDescription>
          </DialogHeader>

          {assigningJob && (
            <div className="space-y-4">
              <div className="p-3 bg-slate-50 rounded-lg">
                <p className="font-medium text-sm">{assigningJob.title}</p>
                <p className="text-xs text-slate-500">
                  {assigningJob.company_name} • {assigningJob.location} • {assigningJob.job_public_id || assigningJob.id.slice(0, 8)}
                </p>
              </div>

              {loadingRecruiters ? (
                <div className="flex items-center justify-center py-8">
                  <div className="spinner" />
                </div>
              ) : teamRecruiters.length === 0 ? (
                <div className="text-center py-6">
                  <Users className="w-12 h-12 text-slate-300 mx-auto mb-2" />
                  <p className="text-slate-500">No recruiters in your team</p>
                  <p className="text-xs text-slate-400 mt-1">Contact admin to add recruiters to your team</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {teamRecruiters.map((recruiter) => (
                    <div 
                      key={recruiter.id}
                      className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                        selectedRecruiters.includes(recruiter.id)
                          ? 'bg-blue-50 border-blue-300'
                          : 'bg-white border-slate-200 hover:border-slate-300'
                      }`}
                      onClick={() => handleRecruiterToggle(recruiter.id)}
                      data-testid={`recruiter-option-${recruiter.id}`}
                    >
                      <div className="flex items-center gap-3">
                        <Checkbox
                          checked={selectedRecruiters.includes(recruiter.id)}
                          onCheckedChange={() => handleRecruiterToggle(recruiter.id)}
                        />
                        <div className="flex-1">
                          <p className="font-medium text-sm">{recruiter.name}</p>
                          <p className="text-xs text-slate-500">{recruiter.email}</p>
                        </div>
                        <span className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded-full">
                          {recruiter.active_mandates_count || 0} mandates
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-center justify-between text-sm text-slate-500 pt-2 border-t">
                <span>{selectedRecruiters.length} recruiter(s) selected</span>
                {selectedRecruiters.length > 0 && (
                  <button 
                    className="text-blue-600 hover:underline"
                    onClick={() => setSelectedRecruiters([])}
                  >
                    Clear all
                  </button>
                )}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAssignDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAssignRecruiters}
              disabled={assigningInProgress || loadingRecruiters}
              className="bg-blue-600 hover:bg-blue-700"
              data-testid="confirm-assign-btn"
            >
              {assigningInProgress ? 'Assigning...' : 'Save Assignments'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Assignment History Dialog */}
      <Dialog open={showAssignmentHistory} onOpenChange={setShowAssignmentHistory}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <History className="w-5 h-5 text-blue-600" />
              Assignment History
            </DialogTitle>
          </DialogHeader>

          {assigningJob && (
            <div className="space-y-4">
              <div className="p-3 bg-slate-50 rounded-lg">
                <p className="font-medium text-sm">{assigningJob.title}</p>
                <p className="text-xs text-slate-500">
                  Currently assigned: {assigningJob.assigned_recruiters?.length || 0} recruiter(s)
                </p>
              </div>

              <div className="space-y-2 max-h-64 overflow-y-auto">
                {assignmentHistory.length > 0 ? (
                  assignmentHistory.map((entry, idx) => (
                    <div key={idx} className="p-3 bg-slate-50 rounded-lg text-sm border-l-4 border-blue-300">
                      <div className="flex items-center justify-between mb-1">
                        <span className={`font-medium ${entry.action === 'recruiter_removed' ? 'text-red-600' : 'text-blue-600'}`}>
                          {entry.action === 'recruiter_removed' ? 'Recruiter Removed' : 'Recruiters Assigned'}
                        </span>
                        <span className="text-xs text-slate-400">
                          {new Date(entry.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-slate-600">
                        By: {entry.assigned_by_name || entry.removed_by_name} ({entry.assigned_by_role || entry.removed_by_role})
                      </p>
                      {entry.action === 'recruiter_removed' && (
                        <p className="text-slate-500 mt-1">
                          Removed: {entry.removed_recruiter_name}
                        </p>
                      )}
                      {entry.new_recruiters && (
                        <p className="text-slate-500 mt-1">
                          Assigned: {entry.new_recruiters.length} recruiter(s)
                        </p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-slate-400 text-sm text-center py-4">No assignment changes recorded</p>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
