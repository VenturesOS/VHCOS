import { useState, useEffect } from 'react';
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
import { Search, Briefcase, MapPin, Clock, Users, Eye, Trash2, Globe, GlobeLock, History, AlertTriangle, Link2, Copy, ExternalLink } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function AdminJobsPage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  
  // Career Page Status Control
  const [showCareerPageDialog, setShowCareerPageDialog] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [careerPageAction, setCareerPageAction] = useState('');
  const [careerPageReason, setCareerPageReason] = useState('');
  const [updatingCareerPage, setUpdatingCareerPage] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [careerPageHistory, setCareerPageHistory] = useState([]);

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
      toast.success('Job deleted successfully');
      loadJobs();
    } catch (error) {
      toast.error('Failed to delete job');
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

  // Shareable Link Toggle
  const handleShareableLinkToggle = async (job, enabled) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/jobs/${job.id}/shareable-link`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ enabled })
      });
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to update');
      }
      
      toast.success(enabled ? 'Shareable link enabled' : 'Shareable link disabled');
      loadJobs();
    } catch (error) {
      toast.error(error.message || 'Failed to update shareable link');
    }
  };

  const copyShareableLink = (job) => {
    const jobIdForLink = job.job_public_id || job.id;
    const link = `${window.location.origin}/jobs/${jobIdForLink}`;
    navigator.clipboard.writeText(link);
    toast.success('Link copied to clipboard!');
  };

  const openShareableLink = (job) => {
    const jobIdForLink = job.job_public_id || job.id;
    window.open(`/jobs/${jobIdForLink}`, '_blank');
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
          <h1 className="font-heading text-3xl font-bold text-slate-900">Jobs</h1>
          <p className="text-slate-500 mt-1">All job postings on the platform</p>
        </div>
        <div className="relative w-full sm:w-64">
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
                  <span className={`px-2 py-1 rounded text-xs font-medium ${job.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}`}>
                    {job.status}
                  </span>
                  
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
                  <Button variant="ghost" size="sm">
                    <Eye className="w-4 h-4" />
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
                        <span className="text-xs text-slate-400">{new Date(entry.timestamp).toLocaleString()}</span>
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
    </div>
  );
}
