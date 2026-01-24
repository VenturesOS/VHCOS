import { useState, useEffect } from 'react';
import { jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { toast } from 'sonner';
import { Search, Briefcase, MapPin, Clock, Users, Eye, Trash2, Globe, GlobeOff, History, AlertTriangle } from 'lucide-react';

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
                <div className="flex items-center gap-2">
                  <span className={`badge ${job.status === 'active' ? 'badge-active' : 'badge-inactive'}`}>
                    {job.status}
                  </span>
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
    </div>
  );
}
