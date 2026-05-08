import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { Search, Briefcase, MapPin, Clock, Users, Eye, Trash2, Globe, GlobeLock, History, AlertTriangle, Link2, Copy, ExternalLink, Linkedin, Sparkles, UserPlus, Pencil } from 'lucide-react';
import { shareJobOnLinkedIn } from '../../lib/linkedin';
import { AddCandidateToMandateDialog } from '../../components/dialogs/AddCandidateToMandateDialog';
import { JobSortDropdown } from '../../components/shared/JobSortDropdown';

const API_URL = '';

export default function AdminJobsPage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sortOrder, setSortOrder] = useState('newest');
  
  // Career Page Status Control
  const [showCareerPageDialog, setShowCareerPageDialog] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [careerPageAction, setCareerPageAction] = useState('');
  const [careerPageReason, setCareerPageReason] = useState('');
  const [updatingCareerPage, setUpdatingCareerPage] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [careerPageHistory, setCareerPageHistory] = useState([]);
  const [addCandidateJob, setAddCandidateJob] = useState(null);

  // Edit Job state
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editJob, setEditJob] = useState(null);
  const [editForm, setEditForm] = useState({ title: '', description: '', requirements: '', location: '', job_type: '', salary_min: '', salary_max: '', department: '', public_company_alias: '' });
  const [savingEdit, setSavingEdit] = useState(false);

  const loadJobs = useCallback(async () => {
    try {
      const res = await jobAPI.getAll({ sort_order: sortOrder });
      setJobs(res.data);
    } catch (error) {
      toast.error('Failed to load jobs');
    } finally {
      setLoading(false);
    }
  }, [sortOrder]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const handleDelete = async (jobId) => {
    if (!window.confirm('Are you sure you want to delete this job?')) return;
    try {
      await jobAPI.delete(jobId);
      toast.success('Job deleted successfully');
      loadJobs();
    } catch (error) {
      toast.error('Failed to delete job');
    }
  };

  const openEditDialog = (job) => {
    setEditJob(job);
    setEditForm({
      title: job.title || '',
      description: job.description || '',
      requirements: job.requirements || '',
      location: job.location || '',
      job_type: job.job_type || '',
      salary_min: job.salary_min?.toString() || '',
      salary_max: job.salary_max?.toString() || '',
      department: job.department || '',
      public_company_alias: job.public_company_alias || '',
    });
    setShowEditDialog(true);
  };

  const handleSaveEdit = async () => {
    if (!editJob) return;
    setSavingEdit(true);
    try {
      const payload = { ...editForm };
      if (payload.salary_min) payload.salary_min = parseInt(payload.salary_min);
      else delete payload.salary_min;
      if (payload.salary_max) payload.salary_max = parseInt(payload.salary_max);
      else delete payload.salary_max;
      await jobAPI.update(editJob.id, payload);
      toast.success('Job updated successfully');
      setShowEditDialog(false);
      loadJobs();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update job');
    } finally {
      setSavingEdit(false);
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

  // Shareable Link Toggle (Career Page)
  const handleShareableLinkToggle = async (job, enabled) => {
    try {
      await jobAPI.updateShareableLink(job.id, enabled);
      toast.success(enabled ? 'Shareable link enabled' : 'Shareable link disabled');
      loadJobs();
    } catch (error) {
      const detail = error.response?.data?.detail;
      toast.error(detail || 'Failed to update shareable link');
    }
  };

  // Mandate Shareable Link Toggle (Independent of Career Page)
  const handleMandateShareableLinkToggle = async (job, enabled) => {
    try {
      const res = await jobAPI.updateMandateShareableLink(job.id, enabled);
      if (enabled && res.data.mandate_share_token) {
        const link = `${window.location.origin}/apply/mandate/${job.id}?token=${res.data.mandate_share_token}`;
        navigator.clipboard.writeText(link);
        toast.success('Mandate link enabled and copied to clipboard!');
      } else {
        toast.success('Mandate link disabled');
      }
      loadJobs();
    } catch (error) {
      const detail = error.response?.data?.detail;
      toast.error(detail || 'Failed to update mandate shareable link');
    }
  };

  const copyMandateShareableLink = (job) => {
    if (!job.mandate_share_token) {
      toast.error('Mandate link token not available');
      return;
    }
    const link = `${window.location.origin}/apply/mandate/${job.id}?token=${job.mandate_share_token}`;
    navigator.clipboard.writeText(link);
    toast.success('Mandate link copied to clipboard!');
  };

  const openMandateShareableLink = (job) => {
    if (!job.mandate_share_token) {
      toast.error('Mandate link token not available');
      return;
    }
    window.open(`/apply/mandate/${job.id}?token=${job.mandate_share_token}`, '_blank');
  };

  const copyShareableLink = (job) => {
    // Use internal ID for URL (no slashes - more URL-friendly)
    const link = `${window.location.origin}/jobs/${job.id}`;
    navigator.clipboard.writeText(link);
    toast.success('Link copied to clipboard!');
  };

  const openShareableLink = (job) => {
    // Use internal ID for URL
    window.open(`/jobs/${job.id}`, '_blank');
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

  const filteredJobs = jobs.filter(
    (job) =>
      job.title.toLowerCase().includes(search.toLowerCase()) ||
      job.location.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="admin-jobs-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Jobs</h1>
          <p className="text-slate-500 mt-1">All job postings on the platform</p>
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <JobSortDropdown value={sortOrder} onChange={setSortOrder} />
          <div className="relative flex-1 sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              placeholder="Search jobs..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
              data-testid="jobs-search-input"
            />
          </div>
        </div>
      </div>

      <div className="grid gap-4">
        {filteredJobs.map((job) => (
          <Card key={job.id} className="border-slate-200 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center shrink-0">
                      <Briefcase className="w-6 h-6 text-[#7CB342]" />
                    </div>
                    <div>
                      {/* Job Public ID Badge */}
                      {job.job_public_id && (
                        <Badge variant="outline" className="mb-1 text-xs font-mono">
                          {job.job_public_id}
                        </Badge>
                      )}
                      <h3 className="font-heading font-semibold text-lg text-slate-900">{job.title}</h3>
                      <p className="text-slate-500 text-sm">{job.company_name || 'Company'}</p>
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
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {/* Career Page Status Badge */}
                  {job.career_page_status === 'live' && (
                    <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full flex items-center gap-1">
                      <Globe className="w-3 h-3" /> Live
                    </span>
                  )}
                  
                  {/* Shareable Link Badge & Controls */}
                  {job.career_page_status === 'live' && (
                    <div className="flex items-center gap-2 px-2 py-1 bg-blue-50 rounded-lg">
                      <Link2 className="w-3 h-3 text-blue-600" />
                      <span className="text-xs text-blue-700">Share</span>
                      <Switch
                        checked={job.shareable_link_enabled || false}
                        onCheckedChange={(checked) => handleShareableLinkToggle(job, checked)}
                        className="scale-75"
                        data-testid={`shareable-toggle-${job.id}`}
                      />
                      {job.shareable_link_enabled && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => copyShareableLink(job)}
                            title="Copy link"
                          >
                            <Copy className="w-3 h-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => openShareableLink(job)}
                            title="Open in new tab"
                          >
                            <ExternalLink className="w-3 h-3" />
                          </Button>
                        </>
                      )}
                    </div>
                  )}
                  
                  {/* LinkedIn Share */}
                  {job.career_page_status === 'live' && job.shareable_link_enabled && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-[#0A66C2] hover:bg-blue-50"
                      onClick={() => shareJobOnLinkedIn(job)}
                      title="Share on LinkedIn"
                      data-testid={`linkedin-share-${job.id}`}
                    >
                      <Linkedin className="w-4 h-4" />
                    </Button>
                  )}

                  {/* Mandate Shareable Link - For Assigned Mandates (Independent of Career Page) */}
                  {job.status === 'active' && (
                    <div className="flex items-center gap-2 px-2 py-1 bg-purple-50 rounded-lg" data-testid={`mandate-link-section-${job.id}`}>
                      <GlobeLock className="w-3 h-3 text-purple-600" />
                      <span className="text-xs text-purple-700">Mandate</span>
                      <Switch
                        checked={job.mandate_shareable_link_enabled || false}
                        onCheckedChange={(checked) => handleMandateShareableLinkToggle(job, checked)}
                        className="scale-75"
                        data-testid={`mandate-shareable-toggle-${job.id}`}
                      />
                      {job.mandate_shareable_link_enabled && job.mandate_share_token && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => copyMandateShareableLink(job)}
                            title="Copy mandate link"
                          >
                            <Copy className="w-3 h-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => openMandateShareableLink(job)}
                            title="Open in new tab"
                          >
                            <ExternalLink className="w-3 h-3" />
                          </Button>
                        </>
                      )}
                    </div>
                  )}
                  
                  <span className={`px-2 py-1 rounded text-xs font-medium ${job.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}`}>
                    {job.status}
                  </span>

                  {/* Find Matching Candidates */}
                  {job.status === 'active' && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-blue-600 border-blue-300 hover:bg-blue-50 gap-1.5"
                      onClick={() => navigate(`/admin/find-candidates?job_id=${job.id}`)}
                      data-testid={`find-candidates-${job.id}`}
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span className="hidden sm:inline">Find Candidates</span>
                    </Button>
                  )}

                  {/* Add Candidate from Bank */}
                  {job.status === 'active' && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-purple-600 border-purple-300 hover:bg-purple-50 gap-1.5"
                      onClick={() => setAddCandidateJob(job)}
                      data-testid={`add-candidate-${job.id}`}
                    >
                      <UserPlus className="w-3.5 h-3.5" />
                      <span className="hidden sm:inline">Add Candidate</span>
                    </Button>
                  )}
                  
                  {/* Career Page Controls - Admin has full access */}
                  {job.status === 'active' && (
                    job.career_page_status === 'live' ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-amber-600 border-amber-300 hover:bg-amber-50"
                        onClick={() => openCareerPageDialog(job, 'removed')}
                        data-testid={`remove-career-page-${job.id}`}
                      >
                        <GlobeLock className="w-4 h-4" />
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-green-600 border-green-300 hover:bg-green-50"
                        onClick={() => openCareerPageDialog(job, 'live')}
                        data-testid={`post-career-page-${job.id}`}
                      >
                        <Globe className="w-4 h-4" />
                      </Button>
                    )
                  )}
                  
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openHistoryDialog(job)}
                    title="Career Page History"
                  >
                    <History className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate(`/admin/pipeline?job_id=${job.id}`)}
                    title="View Pipeline"
                    data-testid={`view-pipeline-${job.id}`}
                  >
                    <Eye className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openEditDialog(job)}
                    title="Edit Job"
                    data-testid={`edit-job-${job.id}`}
                  >
                    <Pencil className="w-4 h-4" />
                  </Button>
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
            <p className="empty-state-title">No jobs found</p>
            <p className="empty-state-text">Jobs posted by employers will appear here</p>
          </div>
        )}
      </div>

      {/* Career Page Status Dialog */}
      <Dialog open={showCareerPageDialog} onOpenChange={setShowCareerPageDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              {careerPageAction === 'live' ? (
                <><Globe className="w-5 h-5 text-green-600" /> Post to Career Page</>
              ) : (
                <><GlobeLock className="w-5 h-5 text-amber-600" /> Remove from Career Page</>
              )}
            </DialogTitle>
            <DialogDescription>
              {careerPageAction === 'live' 
                ? "This job will be visible on the public career page."
                : "This job will be removed from the public career page."
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
                    This job will become publicly visible. Not all jobs need to be on the career page.
                  </p>
                </div>
              )}

              <div className="space-y-2">
                <Label>Reason (optional)</Label>
                <Textarea
                  value={careerPageReason}
                  onChange={(e) => setCareerPageReason(e.target.value)}
                  placeholder="e.g., Approved for public posting..."
                  rows={2}
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCareerPageDialog(false)}>Cancel</Button>
            <Button
              onClick={handleCareerPageUpdate}
              disabled={updatingCareerPage}
              className={careerPageAction === 'live' ? "bg-green-600 hover:bg-green-700" : "bg-amber-600 hover:bg-amber-700"}
            >
              {updatingCareerPage ? 'Processing...' : careerPageAction === 'live' ? 'Post to Career Page' : 'Remove'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Career Page History Dialog */}
      <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <History className="w-5 h-5" /> Career Page History
            </DialogTitle>
          </DialogHeader>
          {selectedJob && (
            <div className="space-y-4">
              <div className="p-3 bg-slate-50 rounded-lg">
                <p className="font-medium text-sm">{selectedJob.title}</p>
                <p className="text-xs text-slate-500">
                  Current: {selectedJob.career_page_status === 'live' ? 'Live' : 'Not Posted'}
                </p>
              </div>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {careerPageHistory.length > 0 ? (
                  careerPageHistory.map((entry, idx) => (
                    <div key={idx} className="p-3 bg-slate-50 rounded-lg text-sm border-l-4 border-slate-300">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium">{entry.from_status || 'not_posted'} → {entry.to_status}</span>
                        <span className="text-xs text-slate-400">{new Date(entry.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
                      </div>
                      <p className="text-slate-600">By: {entry.changed_by_name} ({entry.changed_by_role})</p>
                      {entry.reason && <p className="text-slate-500 mt-1 italic">"{entry.reason}"</p>}
                    </div>
                  ))
                ) : (
                  <p className="text-slate-400 text-sm text-center py-4">No history</p>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Add Candidate to Mandate Dialog */}
      <AddCandidateToMandateDialog
        open={!!addCandidateJob}
        onOpenChange={(open) => !open && setAddCandidateJob(null)}
        job={addCandidateJob}
        onCandidateLinked={loadJobs}
      />

      {/* Edit Job Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <Pencil className="w-5 h-5" /> Edit Job / Mandate
            </DialogTitle>
            <DialogDescription>Update job details. Public alias is used on all shared links.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-slate-500 mb-1">Job Title</Label>
                <Input value={editForm.title} onChange={(e) => setEditForm(f => ({ ...f, title: e.target.value }))} data-testid="edit-job-title" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1">Public Company Alias (shown on shared links)</Label>
                <Input value={editForm.public_company_alias} onChange={(e) => setEditForm(f => ({ ...f, public_company_alias: e.target.value }))} placeholder="e.g. Leading MNC, Top IT Company" data-testid="edit-job-alias" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1">Location</Label>
                <Input value={editForm.location} onChange={(e) => setEditForm(f => ({ ...f, location: e.target.value }))} data-testid="edit-job-location" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1">Job Type</Label>
                <Input value={editForm.job_type} onChange={(e) => setEditForm(f => ({ ...f, job_type: e.target.value }))} placeholder="Full-time, Part-time, Contract" data-testid="edit-job-type" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1">Min Salary (INR)</Label>
                <Input type="number" value={editForm.salary_min} onChange={(e) => setEditForm(f => ({ ...f, salary_min: e.target.value }))} data-testid="edit-job-salary-min" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1">Max Salary (INR)</Label>
                <Input type="number" value={editForm.salary_max} onChange={(e) => setEditForm(f => ({ ...f, salary_max: e.target.value }))} data-testid="edit-job-salary-max" />
              </div>
              <div>
                <Label className="text-xs text-slate-500 mb-1">Department</Label>
                <Input value={editForm.department} onChange={(e) => setEditForm(f => ({ ...f, department: e.target.value }))} data-testid="edit-job-department" />
              </div>
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-1">Description</Label>
              <Textarea value={editForm.description} onChange={(e) => setEditForm(f => ({ ...f, description: e.target.value }))} rows={4} data-testid="edit-job-description" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 mb-1">Requirements</Label>
              <Textarea value={editForm.requirements} onChange={(e) => setEditForm(f => ({ ...f, requirements: e.target.value }))} rows={3} data-testid="edit-job-requirements" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>Cancel</Button>
            <Button onClick={handleSaveEdit} disabled={savingEdit} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="save-edit-job-btn">
              {savingEdit ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
