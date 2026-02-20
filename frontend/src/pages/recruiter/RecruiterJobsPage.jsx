import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { jobAPI } from '../../lib/api';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { toast } from 'sonner';
import { Search, Briefcase, MapPin, Clock, Users, Eye, Linkedin } from 'lucide-react';
import { shareJobOnLinkedIn } from '../../lib/linkedin';

export default function RecruiterJobsPage() {
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

  const filteredJobs = jobs.filter((job) =>
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
    <div className="space-y-6" data-testid="recruiter-jobs-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Jobs</h1>
          <p className="text-slate-500 mt-1">View and manage job postings</p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search jobs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
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
                  <Button
                    variant="default"
                    size="sm"
                    className="bg-[#7CB342] hover:bg-[#689F38]"
                    onClick={() => navigate(`/recruiter/jobs/${job.id}/applicants`)}
                    data-testid={`view-applicants-${job.id}`}
                  >
                    <Eye className="w-4 h-4 mr-1" /> View Applicants
                  </Button>
                  <span className={`badge ${job.status === 'active' ? 'badge-active' : 'badge-inactive'}`}>
                    {job.status}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {filteredJobs.length === 0 && (
          <div className="empty-state">
            <Briefcase className="empty-state-icon" />
            <p className="empty-state-title">No jobs found</p>
            <p className="empty-state-text">Jobs will appear here</p>
          </div>
        )}
      </div>
    </div>
  );
}
