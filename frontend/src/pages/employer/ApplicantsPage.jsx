import { useState, useEffect } from 'react';
import { applicationAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { Users, Mail, FileText, Check, X, ChevronRight } from 'lucide-react';

const STAGES = ['applied', 'shortlisted', 'interview', 'offered', 'hired', 'rejected'];

export default function ApplicantsPage() {
  const [applications, setApplications] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState('all');
  const [loading, setLoading] = useState(true);
  const [selectedApp, setSelectedApp] = useState(null);

  useEffect(() => {
    loadJobs();
  }, []);

  useEffect(() => {
    loadApplications();
  }, [selectedJob]);

  const loadJobs = async () => {
    try {
      const res = await jobAPI.getAll();
      setJobs(res.data);
    } catch (error) {
      toast.error('Failed to load jobs');
    }
  };

  const loadApplications = async () => {
    setLoading(true);
    try {
      const params = selectedJob !== 'all' ? { job_id: selectedJob } : {};
      const res = await applicationAPI.getAll(params);
      setApplications(res.data);
    } catch (error) {
      toast.error('Failed to load applicants');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateStage = async (appId, newStage) => {
    try {
      await applicationAPI.update(appId, { stage: newStage });
      toast.success(`Moved to ${newStage}`);
      loadApplications();
      setSelectedApp(null);
    } catch (error) {
      toast.error('Failed to update');
    }
  };

  if (loading && applications.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="applicants-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Applicants</h1>
          <p className="text-slate-500 mt-1">Review and manage job applicants</p>
        </div>
        <Select value={selectedJob} onValueChange={setSelectedJob}>
          <SelectTrigger className="w-64" data-testid="job-filter">
            <SelectValue placeholder="Filter by job" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Jobs</SelectItem>
            {jobs.map((job) => (
              <SelectItem key={job.id} value={job.id}>
                {job.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card className="border-slate-200">
        <CardHeader className="border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Users className="w-5 h-5 text-[#7CB342]" />
            Applicants ({applications.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-slate-100">
            {applications.map((app) => (
              <div
                key={app.id}
                className="p-4 hover:bg-slate-50 transition-colors cursor-pointer"
                onClick={() => setSelectedApp(app)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                      <span className="text-[#7CB342] font-semibold">
                        {app.candidate_name?.charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <p className="font-medium text-slate-900">{app.candidate_name}</p>
                      <p className="text-sm text-slate-500">{app.job_title}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`badge badge-${app.stage}`}>{app.stage}</span>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </div>
                </div>
              </div>
            ))}
            {applications.length === 0 && (
              <div className="p-8 text-center">
                <Users className="w-12 h-12 text-slate-300 mx-auto mb-2" />
                <p className="text-slate-500">No applicants yet</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Applicant Detail Dialog */}
      <Dialog open={!!selectedApp} onOpenChange={() => setSelectedApp(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading">Applicant Details</DialogTitle>
          </DialogHeader>
          {selectedApp && (
            <div className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                  <span className="text-[#7CB342] font-bold text-2xl">
                    {selectedApp.candidate_name?.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <h3 className="font-semibold text-xl">{selectedApp.candidate_name}</h3>
                  <p className="text-slate-500">{selectedApp.job_title}</p>
                </div>
              </div>

              <div className="space-y-2">
                <p className="flex items-center gap-2 text-slate-600">
                  <Mail className="w-4 h-4" /> {selectedApp.candidate_email}
                </p>
                <p className="flex items-center gap-2">
                  <span className={`badge badge-${selectedApp.stage}`}>
                    {selectedApp.stage}
                  </span>
                </p>
              </div>

              {selectedApp.cover_letter && (
                <div>
                  <h4 className="font-medium mb-2">Cover Letter</h4>
                  <p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">
                    {selectedApp.cover_letter}
                  </p>
                </div>
              )}

              <div>
                <h4 className="font-medium mb-3">Update Stage</h4>
                <div className="flex flex-wrap gap-2">
                  {STAGES.map((stage) => (
                    <Button
                      key={stage}
                      variant={selectedApp.stage === stage ? 'default' : 'outline'}
                      size="sm"
                      className={selectedApp.stage === stage ? 'bg-[#7CB342]' : ''}
                      onClick={() => handleUpdateStage(selectedApp.id, stage)}
                      data-testid={`stage-${stage}-btn`}
                    >
                      {stage}
                    </Button>
                  ))}
                </div>
              </div>

              <div className="flex gap-2 pt-4 border-t">
                <Button
                  className="flex-1 bg-[#7CB342] hover:bg-[#689F38]"
                  onClick={() => handleUpdateStage(selectedApp.id, 'shortlisted')}
                >
                  <Check className="w-4 h-4 mr-2" /> Shortlist
                </Button>
                <Button
                  variant="outline"
                  className="flex-1 text-red-600 hover:bg-red-50"
                  onClick={() => handleUpdateStage(selectedApp.id, 'rejected')}
                >
                  <X className="w-4 h-4 mr-2" /> Reject
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
