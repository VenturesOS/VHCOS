import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { accountManagerAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import {
  Building2, Briefcase, Users, ArrowLeft, Plus, TrendingUp,
  ChevronRight, UserPlus
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../../lib/auth';

const stageBadge = {
  sourced: 'bg-slate-100 text-slate-700',
  submitted_to_client: 'bg-cyan-100 text-cyan-700',
  shortlisted: 'bg-amber-100 text-amber-700',
  interview: 'bg-purple-100 text-purple-700',
  offered: 'bg-green-100 text-green-700',
  hired: 'bg-emerald-100 text-emerald-700',
  joined: 'bg-teal-100 text-teal-700',
  rejected: 'bg-red-100 text-red-700',
  on_hold: 'bg-gray-100 text-gray-700',
};

export default function CompanyDetailPage() {
  const { companyId } = useParams();
  const { user } = useAuth();
  const basePath = user?.role === 'employer' ? '/employer' : '/recruiter';
  const [company, setCompany] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [pipeline, setPipeline] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [recruiters, setRecruiters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assigningId, setAssigningId] = useState(null);

  const loadAll = useCallback(async () => {
    try {
      const [companiesRes, jobsRes, pipelineRes, analyticsRes, recruitersRes] = await Promise.all([
        accountManagerAPI.getMyCompanies(),
        accountManagerAPI.getCompanyJobs(companyId),
        accountManagerAPI.getCompanyPipeline(companyId),
        accountManagerAPI.getCompanyAnalytics(companyId),
        accountManagerAPI.getRecruiters(),
      ]);
      const comp = (companiesRes.data.companies || []).find(c => c.id === companyId);
      setCompany(comp || { name: 'Company', id: companyId });
      setJobs(jobsRes.data.jobs || []);
      setPipeline(pipelineRes.data.applications || []);
      setAnalytics(analyticsRes.data);
      setRecruiters(recruitersRes.data.recruiters || []);
    } catch (error) {
      toast.error('Failed to load company data');
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleAssignRecruiter = async (applicationId, recruiterId) => {
    try {
      setAssigningId(applicationId);
      await accountManagerAPI.assignCandidate(applicationId, recruiterId);
      toast.success('Candidate assigned successfully');
      loadAll();
    } catch (error) {
      toast.error('Failed to assign candidate');
    } finally {
      setAssigningId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="company-detail-page">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to={`${basePath}/account-manager`}>
          <Button variant="ghost" size="sm">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
              <Building2 className="w-5 h-5 text-slate-600" />
            </div>
            <div>
              <h1 className="font-heading text-xl sm:text-2xl font-bold text-slate-900">
                {company?.name}
              </h1>
              <p className="text-sm text-slate-500">{company?.industry || ''}</p>
            </div>
          </div>
        </div>
        <Link to={`${basePath}/account-manager/company/${companyId}/new-job`}>
          <Button className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="create-job-btn">
            <Plus className="w-4 h-4 mr-2" /> Create Job
          </Button>
        </Link>
      </div>

      {/* Analytics Summary */}
      {analytics && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <p className="text-2xl font-bold text-slate-900">{analytics.total_jobs}</p>
              <p className="text-xs text-slate-500">Total Jobs</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-2xl font-bold text-green-600">{analytics.active_jobs}</p>
              <p className="text-xs text-slate-500">Active Jobs</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-2xl font-bold text-slate-900">{analytics.total_applications}</p>
              <p className="text-xs text-slate-500">Total Applications</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-2xl font-bold text-amber-600">{analytics.closed_jobs}</p>
              <p className="text-xs text-slate-500">Closed Jobs</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tabs: Jobs / Pipeline */}
      <Tabs defaultValue="jobs">
        <TabsList>
          <TabsTrigger value="jobs">Jobs ({jobs.length})</TabsTrigger>
          <TabsTrigger value="pipeline">Pipeline ({pipeline.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="jobs" className="mt-4">
          {jobs.length === 0 ? (
            <Card>
              <CardContent className="p-8 text-center text-slate-500">
                No jobs yet. Create one to get started.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {jobs.map((job) => (
                <Card key={job.id} data-testid={`job-card-${job.id}`}>
                  <CardContent className="p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Briefcase className="w-5 h-5 text-slate-400" />
                      <div>
                        <p className="font-medium text-slate-900">{job.title}</p>
                        <p className="text-sm text-slate-500">
                          {job.location} {job.job_public_id && `| ${job.job_public_id}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge className={job.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}>
                        {job.status}
                      </Badge>
                      <span className="text-sm text-slate-400">{job.applicant_count || 0} applicants</span>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="pipeline" className="mt-4">
          {pipeline.length === 0 ? (
            <Card>
              <CardContent className="p-8 text-center text-slate-500">
                No applications in pipeline yet.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {pipeline.map((app) => (
                <Card key={app.id} data-testid={`pipeline-card-${app.id}`}>
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between flex-wrap gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <Users className="w-5 h-5 text-slate-400 shrink-0" />
                        <div className="min-w-0">
                          <p className="font-medium text-slate-900 truncate">
                            {app.candidate_name || 'Unknown'}
                          </p>
                          <p className="text-sm text-slate-500 truncate">{app.job_title}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge className={stageBadge[app.stage] || 'bg-slate-100 text-slate-600'}>
                          {(app.stage || 'sourced').replace(/_/g, ' ')}
                        </Badge>
                        {app.assigned_recruiter_name ? (
                          <span className="text-xs text-slate-500 bg-slate-50 px-2 py-1 rounded">
                            Assigned: {app.assigned_recruiter_name}
                          </span>
                        ) : (
                          <Select
                            onValueChange={(val) => handleAssignRecruiter(app.id, val)}
                            disabled={assigningId === app.id}
                          >
                            <SelectTrigger className="w-[160px] h-8 text-xs" data-testid={`assign-recruiter-${app.id}`}>
                              <SelectValue placeholder="Assign recruiter" />
                            </SelectTrigger>
                            <SelectContent>
                              {recruiters.map((r) => (
                                <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
