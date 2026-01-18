import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { jobAPI } from '../../lib/api';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { toast } from 'sonner';
import { Search, Briefcase, MapPin, Clock, Users, Plus, Edit2, Trash2, Eye } from 'lucide-react';

export default function EmployerJobsPage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

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
                    <h3 className="font-heading font-semibold text-lg text-slate-900">{job.title}</h3>
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
                <div className="flex items-center gap-2">
                  <Button
                    variant="default"
                    size="sm"
                    className="bg-[#7CB342] hover:bg-[#689F38]"
                    onClick={() => navigate(`/employer/jobs/${job.id}/applicants`)}
                    data-testid={`view-applicants-${job.id}`}
                  >
                    <Eye className="w-4 h-4 mr-1" /> View Applicants
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleToggleStatus(job)}
                  >
                    {job.status === 'active' ? 'Close' : 'Reopen'}
                  </Button>
                  <span className={`badge ${job.status === 'active' ? 'badge-active' : 'badge-inactive'}`}>
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
    </div>
  );
}
