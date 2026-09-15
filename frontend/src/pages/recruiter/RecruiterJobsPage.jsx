import { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { jobAPI } from '../../lib/api';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Switch } from '../../components/ui/switch';
import { toast } from 'sonner';
import { Search, Briefcase, MapPin, Clock, Users, Eye, Plus, Trash2, Linkedin, Link2, Copy, ExternalLink, Sparkles, UserPlus, LayoutGrid } from 'lucide-react';
import { shareJobOnLinkedIn } from '../../lib/linkedin';
import { AddCandidateToMandateDialog } from '../../components/dialogs/AddCandidateToMandateDialog';
import { JobSortDropdown } from '../../components/shared/JobSortDropdown';

export default function RecruiterJobsPage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sortOrder, setSortOrder] = useState('newest');
  const [addCandidateJob, setAddCandidateJob] = useState(null);
  const navigate = useNavigate();

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

  const handleDelete = async (jobId, jobTitle) => {
    if (!window.confirm(`Are you sure you want to delete "${jobTitle}"?`)) return;
    try {
      await jobAPI.delete(jobId);
      toast.success('Job deleted');
      loadJobs();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete job');
    }
  };

  const toggleMandateLink = async (job, enabled) => {
    try {
      const res = await jobAPI.updateMandateShareableLink(job.id, enabled);
      if (enabled && res.data.mandate_share_token) {
        const link = `${window.location.origin}/apply/mandate/${job.id}?token=${res.data.mandate_share_token}`;
        await navigator.clipboard.writeText(link);
        toast.success('Mandate link enabled & copied!');
      } else {
        toast.success('Mandate link disabled');
      }
      loadJobs();
    } catch (error) {
      const detail = error.response?.data?.detail;
      toast.error(detail || 'Failed to update mandate link');
    }
  };

  const copyMandateLink = async (job) => {
    if (!job.mandate_share_token) return;
    const link = `${window.location.origin}/apply/mandate/${job.id}?token=${job.mandate_share_token}`;
    await navigator.clipboard.writeText(link);
    toast.success('Mandate link copied!');
  };

  const openMandateLink = (job) => {
    if (!job.mandate_share_token) return;
    window.open(`/apply/mandate/${job.id}?token=${job.mandate_share_token}`, '_blank');
  };

  const filteredJobs = jobs.filter((job) =>
    job.title?.toLowerCase().includes(search.toLowerCase()) ||
    job.location?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="recruiter-jobs-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Job Mandates</h1>
          <p className="text-slate-500 mt-1">Create and manage job mandates</p>
        </div>
        <div className="flex items-center gap-3">
          <JobSortDropdown value={sortOrder} onChange={setSortOrder} />
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              placeholder="Search jobs..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
            />
          </div>
          <Link to="/recruiter/jobs/new">
            <Button className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="create-job-btn">
              <Plus className="w-4 h-4 mr-1" /> Create Job
            </Button>
          </Link>
        </div>
      </div>

      <div className="grid gap-4">
        {filteredJobs.map((job) => (
          <Card key={job.id} className="border-slate-200 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center shrink-0">
                  <Briefcase className="w-6 h-6 text-[#7CB342]" />
                </div>
                <div className="flex-1">
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
                <div className="flex flex-col items-end gap-2">
                  <div className="flex items-center gap-2">
                    {job.status === 'active' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-[#0A66C2] hover:bg-blue-50"
                        onClick={() => shareJobOnLinkedIn(job)}
                        title="Share on LinkedIn"
                        data-testid={`linkedin-share-${job.id}`}
                      >
                        <Linkedin className="w-4 h-4" />
                      </Button>
                    )}
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
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-[#7CB342] border-[#7CB342]/40 hover:bg-[#DCFCE7]"
                      onClick={() => navigate(`/recruiter/pipeline?job_id=${job.id}`)}
                      data-testid={`view-pipeline-${job.id}`}
                      title="View pipeline filtered to this job"
                    >
                      <LayoutGrid className="w-4 h-4 mr-1" /> Pipeline
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      className="bg-[#7CB342] hover:bg-[#689F38]"
                      onClick={() => navigate(`/recruiter/jobs/${job.id}/applicants`)}
                      data-testid={`view-applicants-${job.id}`}
                    >
                      <Eye className="w-4 h-4 mr-1" /> View
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-500 hover:bg-red-50"
                      onClick={() => handleDelete(job.id, job.title)}
                      data-testid={`delete-job-${job.id}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      job.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                    }`}>
                      {job.status}
                    </span>
                  </div>
                  {job.status === 'active' && (
                    <div className="flex items-center gap-2 px-2 py-1 bg-purple-50 rounded-lg" data-testid={`mandate-link-section-${job.id}`}>
                      <Link2 className="w-3.5 h-3.5 text-purple-600" />
                      <span className="text-xs font-medium text-purple-700">Mandate Link</span>
                      <Switch
                        checked={job.mandate_shareable_link_enabled || false}
                        onCheckedChange={(checked) => toggleMandateLink(job, checked)}
                        data-testid={`mandate-link-toggle-${job.id}`}
                      />
                      {job.mandate_shareable_link_enabled && job.mandate_share_token && (
                        <>
                          <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-purple-600" onClick={() => copyMandateLink(job)} title="Copy mandate link" data-testid={`copy-mandate-link-${job.id}`}>
                            <Copy className="w-3.5 h-3.5" />
                          </Button>
                          <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-purple-600" onClick={() => openMandateLink(job)} title="Open mandate link" data-testid={`open-mandate-link-${job.id}`}>
                            <ExternalLink className="w-3.5 h-3.5" />
                          </Button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {filteredJobs.length === 0 && (
          <div className="text-center py-16">
            <Briefcase className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <p className="text-lg font-medium text-slate-600">No jobs found</p>
            <p className="text-slate-400 mb-4">Create your first job mandate</p>
            <Link to="/recruiter/jobs/new">
              <Button className="bg-[#7CB342] hover:bg-[#689F38]">
                <Plus className="w-4 h-4 mr-1" /> Create Job
              </Button>
            </Link>
          </div>
        )}
      </div>

      {/* Add Candidate to Mandate Dialog */}
      <AddCandidateToMandateDialog
        open={!!addCandidateJob}
        onOpenChange={(open) => !open && setAddCandidateJob(null)}
        job={addCandidateJob}
        onCandidateLinked={loadJobs}
      />
    </div>
  );
}
