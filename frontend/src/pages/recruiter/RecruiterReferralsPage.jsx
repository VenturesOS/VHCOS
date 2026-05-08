import { useState, useEffect } from 'react';
import { referralAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { 
  Search, UserPlus, Users, Briefcase, Mail, Phone,
  Clock, CheckCircle, Link2, Play, Target, XCircle,
  ChevronDown, ChevronUp, Plus
} from 'lucide-react';

export default function RecruiterReferralsPage() {
  const [referrals, setReferrals] = useState([]);
  const [activeJobs, setActiveJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [expandedReferral, setExpandedReferral] = useState({});
  
  const [createForm, setCreateForm] = useState({
    job_id: '',
    candidate_name: '',
    candidate_email: '',
    candidate_phone: '',
    note: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [referralsRes, jobsRes] = await Promise.all([
        referralAPI.getAll(),
        jobAPI.getAll(),
      ]);
      setReferrals(referralsRes.data);
      // Only show active jobs for referral creation
      setActiveJobs(jobsRes.data.filter(j => j.status === 'active'));
    } catch (error) {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!createForm.job_id || !createForm.candidate_name || !createForm.candidate_email) {
      toast.error('Job, candidate name and email are required');
      return;
    }

    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(createForm.candidate_email)) {
      toast.error('Please enter a valid email address');
      return;
    }

    setSubmitting(true);
    try {
      await referralAPI.create(createForm);
      toast.success('Referral submitted successfully');
      setShowCreate(false);
      setCreateForm({
        job_id: '',
        candidate_name: '',
        candidate_email: '',
        candidate_phone: '',
        note: '',
      });
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to submit referral');
    } finally {
      setSubmitting(false);
    }
  };

  const toggleExpand = (id) => {
    setExpandedReferral(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  const getStatusBadge = (status) => {
    const styles = {
      submitted: 'bg-blue-100 text-blue-700',
      validated: 'bg-purple-100 text-purple-700',
      linked: 'bg-indigo-100 text-indigo-700',
      in_process: 'bg-amber-100 text-amber-700',
      outcome_reached: 'bg-green-100 text-green-700',
      closed: 'bg-slate-100 text-slate-600',
    };
    return styles[status] || 'bg-slate-100 text-slate-600';
  };

  const getStatusIcon = (status) => {
    const icons = {
      submitted: Clock,
      validated: CheckCircle,
      linked: Link2,
      in_process: Play,
      outcome_reached: Target,
      closed: XCircle,
    };
    return icons[status] || Clock;
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'Asia/Kolkata',
    });
  };

  // Filter referrals
  const filteredReferrals = referrals.filter(ref => {
    const matchesSearch = 
      ref.candidate_name?.toLowerCase().includes(search.toLowerCase()) ||
      ref.candidate_email?.toLowerCase().includes(search.toLowerCase()) ||
      ref.job_title?.toLowerCase().includes(search.toLowerCase());
    
    const matchesStatus = statusFilter === 'all' || ref.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  // Stats
  const stats = {
    total: referrals.length,
    submitted: referrals.filter(r => r.status === 'submitted').length,
    in_process: referrals.filter(r => ['validated', 'linked', 'in_process'].includes(r.status)).length,
    outcome_reached: referrals.filter(r => r.status === 'outcome_reached').length,
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="referrals-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">My Referrals</h1>
          <p className="text-slate-500 mt-1">Submit and track candidate referrals</p>
        </div>
        <Button
          onClick={() => setShowCreate(true)}
          className="bg-[#7CB342] hover:bg-[#689F38]"
          data-testid="create-referral-btn"
        >
          <UserPlus className="w-4 h-4 mr-2" /> New Referral
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#DCFCE7] flex items-center justify-center">
              <Users className="w-5 h-5 text-[#7CB342]" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{stats.total}</p>
              <p className="text-xs text-slate-500">Total Referrals</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
              <Clock className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{stats.submitted}</p>
              <p className="text-xs text-slate-500">Pending Review</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
              <Play className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{stats.in_process}</p>
              <p className="text-xs text-slate-500">In Process</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-green-50 flex items-center justify-center">
              <Target className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{stats.outcome_reached}</p>
              <p className="text-xs text-slate-500">Outcomes</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search by name, email, or job..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-full sm:w-48">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="submitted">Submitted</SelectItem>
            <SelectItem value="validated">Validated</SelectItem>
            <SelectItem value="linked">Linked</SelectItem>
            <SelectItem value="in_process">In Process</SelectItem>
            <SelectItem value="outcome_reached">Outcome Reached</SelectItem>
            <SelectItem value="closed">Closed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Referrals List */}
      <Card className="border-slate-200">
        <CardContent className="p-0">
          {filteredReferrals.length === 0 ? (
            <div className="text-center py-12">
              <UserPlus className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500">No referrals found</p>
              <p className="text-sm text-slate-400 mt-1">
                {referrals.length === 0 
                  ? 'Submit your first candidate referral to get started' 
                  : 'Try adjusting your filters'}
              </p>
              {referrals.length === 0 && (
                <Button
                  onClick={() => setShowCreate(true)}
                  className="mt-4 bg-[#7CB342] hover:bg-[#689F38]"
                >
                  <Plus className="w-4 h-4 mr-2" /> New Referral
                </Button>
              )}
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {filteredReferrals.map((referral) => {
                const StatusIcon = getStatusIcon(referral.status);
                return (
                  <div key={referral.id} className="p-5 hover:bg-slate-50 transition-colors">
                    <div className="flex items-start gap-4">
                      {/* Avatar */}
                      <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                        <span className="text-[#7CB342] font-semibold text-lg">
                          {referral.candidate_name?.charAt(0).toUpperCase()}
                        </span>
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <h3 className="font-semibold text-slate-900">{referral.candidate_name}</h3>
                            <div className="flex flex-wrap items-center gap-3 mt-1 text-sm text-slate-500">
                              <span className="flex items-center gap-1">
                                <Mail className="w-3 h-3" /> {referral.candidate_email}
                              </span>
                              {referral.candidate_phone && (
                                <span className="flex items-center gap-1">
                                  <Phone className="w-3 h-3" /> {referral.candidate_phone}
                                </span>
                              )}
                            </div>
                          </div>
                          <Badge className={getStatusBadge(referral.status)}>
                            <StatusIcon className="w-3 h-3 mr-1" />
                            {referral.status?.replace('_', ' ')}
                          </Badge>
                        </div>

                        {/* Job Info */}
                        <div className="flex items-center gap-2 mt-3 text-sm">
                          <Briefcase className="w-4 h-4 text-slate-400" />
                          <span className="text-slate-600">{referral.job_title}</span>
                          <span className="text-slate-400">•</span>
                          <span className="text-slate-400">Submitted {formatDate(referral.created_at)}</span>
                        </div>

                        {referral.note && (
                          <p className="mt-2 text-sm text-slate-500 bg-slate-50 p-2 rounded">
                            {referral.note}
                          </p>
                        )}

                        {/* Status History Toggle */}
                        {referral.status_history && referral.status_history.length > 0 && (
                          <button
                            onClick={() => toggleExpand(referral.id)}
                            className="flex items-center gap-1 mt-3 text-xs text-slate-500 hover:text-slate-700"
                          >
                            <Clock className="w-3 h-3" />
                            Status History ({referral.status_history.length})
                            {expandedReferral[referral.id] ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                          </button>
                        )}

                        {expandedReferral[referral.id] && referral.status_history && (
                          <div className="mt-3 space-y-2 pl-4 border-l-2 border-slate-200">
                            {referral.status_history.map((entry, idx) => (
                              <div key={idx} className="flex items-start gap-2 text-xs">
                                <Badge className={`${getStatusBadge(entry.to_status || entry.status)} text-[10px]`}>
                                  {(entry.to_status || entry.status)?.replace('_', ' ')}
                                </Badge>
                                <span className="text-slate-500">
                                  {entry.changed_by_name} • {formatDate(entry.timestamp)}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Referral Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">Submit Candidate Referral</DialogTitle>
            <DialogDescription>
              Refer a candidate for an active job opening. They will be added to the hiring pipeline.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {/* Job Selection */}
            <div className="space-y-2">
              <Label>Select Job *</Label>
              <Select
                value={createForm.job_id}
                onValueChange={(value) => setCreateForm({ ...createForm, job_id: value })}
              >
                <SelectTrigger data-testid="job-select">
                  <SelectValue placeholder="Select an active job" />
                </SelectTrigger>
                <SelectContent>
                  {activeJobs.length === 0 ? (
                    <div className="p-3 text-center text-sm text-slate-500">
                      No active jobs available
                    </div>
                  ) : (
                    activeJobs.map((job) => (
                      <SelectItem key={job.id} value={job.id}>
                        {job.title} - {job.location}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>

            {/* Candidate Name */}
            <div className="space-y-2">
              <Label>Candidate Name *</Label>
              <Input
                value={createForm.candidate_name}
                onChange={(e) => setCreateForm({ ...createForm, candidate_name: e.target.value })}
                placeholder="Enter candidate's full name"
                data-testid="candidate-name-input"
              />
            </div>

            {/* Candidate Email */}
            <div className="space-y-2">
              <Label>Candidate Email *</Label>
              <Input
                type="email"
                value={createForm.candidate_email}
                onChange={(e) => setCreateForm({ ...createForm, candidate_email: e.target.value })}
                placeholder="candidate@example.com"
                data-testid="candidate-email-input"
              />
            </div>

            {/* Candidate Phone */}
            <div className="space-y-2">
              <Label>Candidate Phone</Label>
              <Input
                value={createForm.candidate_phone}
                onChange={(e) => setCreateForm({ ...createForm, candidate_phone: e.target.value })}
                placeholder="+91-9876543210"
              />
            </div>

            {/* Note */}
            <div className="space-y-2">
              <Label>Note (Optional)</Label>
              <Textarea
                value={createForm.note}
                onChange={(e) => setCreateForm({ ...createForm, note: e.target.value })}
                placeholder="Why is this candidate a good fit?"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={submitting || activeJobs.length === 0}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="submit-referral-btn"
            >
              {submitting ? 'Submitting...' : 'Submit Referral'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
