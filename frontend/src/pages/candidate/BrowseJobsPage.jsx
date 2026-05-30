import { useState, useEffect, useCallback } from 'react';
import { jobAPI, applicationAPI } from '../../lib/api';
import { trackEvent } from '../../hooks/useAnalytics';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { toast } from 'sonner';
import { Search, Briefcase, MapPin, Clock, IndianRupee, Send } from 'lucide-react';
import { formatSalaryDisplay } from '../../lib/currency';

export default function BrowseJobsPage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [location, setLocation] = useState('');
  const [jobType, setJobType] = useState('all');
  const [selectedJob, setSelectedJob] = useState(null);
  const [coverLetter, setCoverLetter] = useState('');
  const [applying, setApplying] = useState(false);

  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    loadJobs();
  }, []);
  /* eslint-enable react-hooks/exhaustive-deps */

  const loadJobs = async () => {
    setLoading(true);
    try {
      const params = {};
      if (search) params.search = search;
      if (location) params.location = location;
      if (jobType && jobType !== 'all') params.job_type = jobType;
      
      const res = await jobAPI.browse(params);
      setJobs(res.data);
    } catch (error) {
      toast.error('Failed to load jobs');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    loadJobs();
  };

  const handleApply = async () => {
    if (!selectedJob) return;
    setApplying(true);
    try {
      await applicationAPI.create({
        job_id: selectedJob.id,
        cover_letter: coverLetter,
      });
      trackEvent('application_submitted', {
        job_id: selectedJob.id,
        job_title: selectedJob.title || null,
        has_cover_letter: !!coverLetter?.trim(),
        source: 'browse_jobs',
      });
      toast.success('Application submitted!');
      setSelectedJob(null);
      setCoverLetter('');
    } catch (error) {
      const message = error.response?.data?.detail || 'Failed to apply';
      toast.error(message);
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="browse-jobs-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Browse Jobs</h1>
        <p className="text-slate-500 mt-1">Find your next opportunity</p>
      </div>

      {/* Search Filters */}
      <Card className="border-slate-200">
        <CardContent className="p-4">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Job title or keyword"
                className="pl-10"
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                data-testid="job-search-input"
              />
            </div>
            <div className="flex-1">
              <Input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="Location"
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <Select value={jobType} onValueChange={setJobType}>
              <SelectTrigger className="w-40">
                <SelectValue placeholder="Job type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                <SelectItem value="full-time">Full-time</SelectItem>
                <SelectItem value="part-time">Part-time</SelectItem>
                <SelectItem value="contract">Contract</SelectItem>
                <SelectItem value="remote">Remote</SelectItem>
              </SelectContent>
            </Select>
            <Button
              onClick={handleSearch}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="search-jobs-btn"
            >
              <Search className="w-4 h-4 mr-2" /> Search
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Job Listings */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="spinner" />
        </div>
      ) : (
        <div className="grid gap-4">
          {jobs.map((job) => (
            <Card
              key={job.id}
              className="border-slate-200 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => setSelectedJob(job)}
            >
              <CardContent className="p-6">
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="w-14 h-14 rounded-xl bg-[#DCFCE7] flex items-center justify-center shrink-0">
                      <Briefcase className="w-7 h-7 text-[#7CB342]" />
                    </div>
                    <div>
                      <h3 className="font-heading font-semibold text-lg text-slate-900 hover:text-[#7CB342]">
                        {job.title}
                      </h3>
                      <p className="text-slate-500">{job.company_name || 'Company'}</p>
                      <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-slate-500">
                        <span className="flex items-center gap-1">
                          <MapPin className="w-4 h-4" /> {job.location}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-4 h-4" /> {job.job_type}
                        </span>
                        {(job.salary_min || job.salary_max) && (
                          <span className="flex items-center gap-1">
                            <IndianRupee className="w-4 h-4" />
                            {formatSalaryDisplay(job.salary_min, job.salary_max)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <Button
                    className="bg-[#7CB342] hover:bg-[#689F38] shrink-0"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedJob(job);
                    }}
                    data-testid={`apply-job-${job.id}`}
                  >
                    Apply Now
                  </Button>
                </div>
                <p className="mt-4 text-slate-600 text-sm line-clamp-2">{job.description}</p>
              </CardContent>
            </Card>
          ))}
          {jobs.length === 0 && (
            <div className="empty-state">
              <Briefcase className="empty-state-icon" />
              <p className="empty-state-title">No jobs found</p>
              <p className="empty-state-text">Try adjusting your search filters</p>
            </div>
          )}
        </div>
      )}

      {/* Apply Dialog */}
      <Dialog open={!!selectedJob} onOpenChange={() => setSelectedJob(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">Apply to {selectedJob?.title}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="bg-slate-50 p-4 rounded-lg">
              <p className="font-medium text-slate-900">{selectedJob?.title}</p>
              <p className="text-sm text-slate-500">{selectedJob?.company_name || 'Company'}</p>
              <p className="text-sm text-slate-500">{selectedJob?.location} • {selectedJob?.job_type}</p>
            </div>
            <div className="space-y-2">
              <Label>Cover Letter (Optional)</Label>
              <Textarea
                value={coverLetter}
                onChange={(e) => setCoverLetter(e.target.value)}
                placeholder="Tell the employer why you're a great fit..."
                rows={5}
                data-testid="cover-letter-input"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedJob(null)}>
              Cancel
            </Button>
            <Button
              onClick={handleApply}
              disabled={applying}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="submit-application-btn"
            >
              {applying ? (
                <div className="spinner w-4 h-4 border-2 border-white border-t-transparent mr-2" />
              ) : (
                <Send className="w-4 h-4 mr-2" />
              )}
              Submit Application
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
