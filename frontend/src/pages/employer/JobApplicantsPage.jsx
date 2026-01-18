import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { jobAPI, applicationAPI } from '../../lib/api';
import { formatSalaryINR, formatSalaryDisplay } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import { toast } from 'sonner';
import { 
  ArrowLeft, Users, Mail, Phone, MapPin, Briefcase, DollarSign, 
  Clock, FileText, CheckCircle, XCircle, AlertCircle, Pause,
  TrendingDown, UserX, ChevronRight, Star
} from 'lucide-react';

// Stage configuration with colors and icons
const STAGES = {
  applied: { label: 'Applied', color: 'bg-blue-100 text-blue-700', icon: Users },
  shortlisted: { label: 'Shortlisted', color: 'bg-green-100 text-green-700', icon: CheckCircle },
  interview: { label: 'Interview', color: 'bg-purple-100 text-purple-700', icon: Users },
  offered: { label: 'Offered', color: 'bg-amber-100 text-amber-700', icon: Star },
  hired: { label: 'Hired', color: 'bg-emerald-100 text-emerald-700', icon: CheckCircle },
  rejected: { label: 'Rejected', color: 'bg-red-100 text-red-700', icon: XCircle },
  on_hold: { label: 'On Hold', color: 'bg-gray-100 text-gray-700', icon: Pause },
  over_budget: { label: 'Over Budget', color: 'bg-orange-100 text-orange-700', icon: TrendingDown },
  not_qualified: { label: 'Not Qualified', color: 'bg-rose-100 text-rose-700', icon: UserX }
};

// Career stability indicator colors
const STABILITY_COLORS = {
  green: 'bg-green-500',
  yellow: 'bg-yellow-500',
  red: 'bg-red-500'
};

export default function JobApplicantsPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [jobData, setJobData] = useState(null);
  const [applicants, setApplicants] = useState([]);
  const [stageCounts, setStageCounts] = useState({});
  const [selectedApplicant, setSelectedApplicant] = useState(null);
  const [activeTab, setActiveTab] = useState('all');

  useEffect(() => {
    if (jobId) {
      loadApplicants();
    }
  }, [jobId]);

  const loadApplicants = async () => {
    setLoading(true);
    try {
      const res = await jobAPI.getApplicants(jobId);
      setJobData(res.data.job);
      setApplicants(res.data.applicants);
      setStageCounts(res.data.stage_counts);
    } catch (error) {
      toast.error('Failed to load applicants');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateStage = async (appId, newStage) => {
    try {
      await applicationAPI.update(appId, { stage: newStage });
      toast.success(`Applicant moved to ${STAGES[newStage]?.label || newStage}`);
      loadApplicants();
      setSelectedApplicant(null);
    } catch (error) {
      toast.error('Failed to update applicant status');
    }
  };

  const filteredApplicants = activeTab === 'all' 
    ? applicants 
    : applicants.filter(a => a.stage === activeTab);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="job-applicants-page">
      {/* Header with back button */}
      <div className="flex items-center gap-4">
        <Button 
          variant="ghost" 
          size="icon"
          onClick={() => navigate(-1)}
          data-testid="back-btn"
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex-1">
          <h1 className="font-heading text-2xl font-bold text-slate-900">
            Applicants for {jobData?.title}
          </h1>
          <div className="flex items-center gap-4 text-sm text-slate-500 mt-1">
            <span className="flex items-center gap-1">
              <MapPin className="h-4 w-4" /> {jobData?.location}
            </span>
            <span className="flex items-center gap-1">
              <Briefcase className="h-4 w-4" /> {jobData?.job_type}
            </span>
            {jobData?.salary_min && (
              <span className="flex items-center gap-1">
                <DollarSign className="h-4 w-4" /> 
                {formatSalaryINR(jobData.salary_min)} - {formatSalaryINR(jobData.salary_max)}
              </span>
            )}
          </div>
        </div>
        <Badge variant="secondary" className="text-lg px-4 py-2">
          {applicants.length} Applicants
        </Badge>
      </div>

      {/* Stage Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="flex flex-wrap gap-2 h-auto p-2 bg-slate-100">
          <TabsTrigger 
            value="all" 
            className="data-[state=active]:bg-white"
            data-testid="tab-all"
          >
            All ({applicants.length})
          </TabsTrigger>
          {Object.entries(STAGES).map(([key, config]) => (
            stageCounts[key] > 0 && (
              <TabsTrigger 
                key={key} 
                value={key}
                className="data-[state=active]:bg-white"
                data-testid={`tab-${key}`}
              >
                {config.label} ({stageCounts[key]})
              </TabsTrigger>
            )
          ))}
        </TabsList>

        <TabsContent value={activeTab} className="mt-4">
          <Card className="border-slate-200">
            <CardContent className="p-0">
              {filteredApplicants.length === 0 ? (
                <div className="p-8 text-center">
                  <Users className="w-12 h-12 text-slate-300 mx-auto mb-2" />
                  <p className="text-slate-500">No applicants in this category</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {filteredApplicants.map((applicant) => (
                    <ApplicantCard 
                      key={applicant.id} 
                      applicant={applicant}
                      jobData={jobData}
                      onClick={() => setSelectedApplicant(applicant)}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Applicant Detail Dialog */}
      <ApplicantDetailDialog
        applicant={selectedApplicant}
        jobData={jobData}
        onClose={() => setSelectedApplicant(null)}
        onUpdateStage={handleUpdateStage}
      />
    </div>
  );
}

// Applicant Card Component
function ApplicantCard({ applicant, jobData, onClick }) {
  const StageIcon = STAGES[applicant.stage]?.icon || Users;
  
  return (
    <div
      className="p-4 hover:bg-slate-50 transition-colors cursor-pointer"
      onClick={onClick}
      data-testid={`applicant-card-${applicant.id}`}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: Avatar and Basic Info */}
        <div className="flex items-start gap-4">
          <div className="relative">
            <div className="w-14 h-14 rounded-full bg-[#DCFCE7] flex items-center justify-center">
              <span className="text-[#7CB342] font-bold text-xl">
                {applicant.candidate_name?.charAt(0).toUpperCase()}
              </span>
            </div>
            {/* Career Stability Indicator with Tooltip */}
            {applicant.career_stability && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div 
                      className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full border-2 border-white cursor-help ${STABILITY_COLORS[applicant.career_stability.score]}`}
                      data-testid={`stability-indicator-${applicant.id}`}
                    />
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-xs">
                    <p className="font-semibold">Career Stability: {applicant.career_stability.score.charAt(0).toUpperCase() + applicant.career_stability.score.slice(1)}</p>
                    <p className="text-xs text-muted-foreground">{applicant.career_stability.tooltip}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-slate-900">{applicant.candidate_name}</h3>
              {applicant.match_score >= 80 && (
                <Badge className="bg-green-100 text-green-700 text-xs">
                  {applicant.match_score}% Match
                </Badge>
              )}
              {applicant.match_score >= 50 && applicant.match_score < 80 && (
                <Badge className="bg-amber-100 text-amber-700 text-xs">
                  {applicant.match_score}% Match
                </Badge>
              )}
              {applicant.match_score < 50 && applicant.match_score > 0 && (
                <Badge className="bg-red-100 text-red-700 text-xs">
                  {applicant.match_score}% Match
                </Badge>
              )}
            </div>
            <p className="text-sm text-slate-600">{applicant.headline || 'No headline'}</p>
            <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-slate-500">
              {applicant.experience_years && (
                <span className="flex items-center gap-1">
                  <Briefcase className="h-3 w-3" /> {applicant.experience_years} yrs exp
                </span>
              )}
              {applicant.location && (
                <span className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" /> {applicant.location}
                </span>
              )}
              {applicant.current_salary && (
                <span className="flex items-center gap-1 font-medium text-slate-700">
                  <DollarSign className="h-3 w-3" /> {formatSalaryINR(applicant.current_salary)}
                </span>
              )}
              {applicant.notice_period && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" /> {applicant.notice_period}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Stage and Action */}
        <div className="flex items-center gap-3">
          <Badge className={STAGES[applicant.stage]?.color}>
            {STAGES[applicant.stage]?.label || applicant.stage}
          </Badge>
          <ChevronRight className="w-4 h-4 text-slate-400" />
        </div>
      </div>

      {/* Must-Have Indicators */}
      {applicant.must_haves_met && applicant.must_haves_met.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {applicant.must_haves_met.slice(0, 5).map((mh, idx) => (
            <span 
              key={idx}
              className={`text-xs px-2 py-1 rounded-full flex items-center gap-1 ${
                mh.met 
                  ? 'bg-green-50 text-green-700' 
                  : 'bg-red-50 text-red-600'
              }`}
            >
              {mh.met ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
              {mh.requirement}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// Applicant Detail Dialog Component
function ApplicantDetailDialog({ applicant, jobData, onClose, onUpdateStage }) {
  if (!applicant) return null;

  const StageIcon = STAGES[applicant.stage]?.icon || Users;

  return (
    <Dialog open={!!applicant} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-heading text-xl">Applicant Review</DialogTitle>
          <DialogDescription>
            Review candidate details and take action
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-6">
          {/* Header with avatar and basic info */}
          <div className="flex items-start gap-4">
            <div className="relative">
              <div className="w-20 h-20 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                <span className="text-[#7CB342] font-bold text-3xl">
                  {applicant.candidate_name?.charAt(0).toUpperCase()}
                </span>
              </div>
              {applicant.career_stability && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div 
                        className={`absolute -bottom-1 -right-1 w-5 h-5 rounded-full border-2 border-white cursor-help ${STABILITY_COLORS[applicant.career_stability.score]}`}
                        data-testid="stability-indicator-detail"
                      />
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-xs">
                      <p className="font-semibold">Career Stability: {applicant.career_stability.score.charAt(0).toUpperCase() + applicant.career_stability.score.slice(1)}</p>
                      <p className="text-xs text-muted-foreground">{applicant.career_stability.tooltip}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="font-bold text-xl">{applicant.candidate_name}</h2>
                <Badge className={STAGES[applicant.stage]?.color}>
                  {STAGES[applicant.stage]?.label || applicant.stage}
                </Badge>
                {applicant.match_score > 0 && (
                  <Badge variant="outline" className="text-sm">
                    {applicant.match_score}% Match
                  </Badge>
                )}
              </div>
              <p className="text-slate-600 mt-1">{applicant.headline}</p>
              
              {/* Contact Info */}
              <div className="flex flex-wrap gap-4 mt-3 text-sm">
                <a href={`mailto:${applicant.candidate_email}`} className="flex items-center gap-1 text-slate-600 hover:text-[#7CB342]">
                  <Mail className="h-4 w-4" /> {applicant.candidate_email}
                </a>
                {applicant.candidate_phone && (
                  <span className="flex items-center gap-1 text-slate-600">
                    <Phone className="h-4 w-4" /> {applicant.candidate_phone}
                  </span>
                )}
                {applicant.location && (
                  <span className="flex items-center gap-1 text-slate-600">
                    <MapPin className="h-4 w-4" /> {applicant.location}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Key Details Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Experience</p>
              <p className="font-semibold text-lg">{applicant.experience_years || 0} years</p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Current Salary (INR)</p>
              <p className="font-semibold text-lg">
                {applicant.current_salary ? formatSalaryINR(applicant.current_salary) : 'Not provided'}
              </p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Notice Period</p>
              <p className="font-semibold text-lg">{applicant.notice_period || 'Not provided'}</p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Career Stability</p>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="flex items-center gap-2 cursor-help">
                      <div className={`w-3 h-3 rounded-full ${STABILITY_COLORS[applicant.career_stability?.score] || 'bg-gray-300'}`} />
                      <p className="font-semibold capitalize">{applicant.career_stability?.score || 'N/A'}</p>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{applicant.career_stability?.tooltip || 'No stability data available'}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>

          {/* Must-Have Requirements */}
          {applicant.must_haves_met && applicant.must_haves_met.length > 0 && (
            <div>
              <h4 className="font-semibold mb-2 flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-[#7CB342]" />
                Must-Have Requirements
              </h4>
              <div className="flex flex-wrap gap-2">
                {applicant.must_haves_met.map((mh, idx) => (
                  <span 
                    key={idx}
                    className={`px-3 py-1 rounded-full text-sm flex items-center gap-1 ${
                      mh.met 
                        ? 'bg-green-100 text-green-700' 
                        : 'bg-red-100 text-red-600'
                    }`}
                  >
                    {mh.met ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                    {mh.requirement}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Skills */}
          {applicant.skills && applicant.skills.length > 0 && (
            <div>
              <h4 className="font-semibold mb-2">Skills</h4>
              <div className="flex flex-wrap gap-2">
                {applicant.skills.map((skill, idx) => (
                  <Badge key={idx} variant="secondary">{skill}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* Summary */}
          {applicant.summary && (
            <div>
              <h4 className="font-semibold mb-2">Summary</h4>
              <p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">{applicant.summary}</p>
            </div>
          )}

          {/* Cover Letter */}
          {applicant.cover_letter && (
            <div>
              <h4 className="font-semibold mb-2">Cover Letter</h4>
              <p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">{applicant.cover_letter}</p>
            </div>
          )}

          {/* Resume Link */}
          {applicant.resume_url && (
            <div>
              <a 
                href={applicant.resume_url} 
                target="_blank" 
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-[#7CB342] hover:underline"
              >
                <FileText className="h-4 w-4" />
                View Resume
              </a>
            </div>
          )}

          {/* Action Buttons */}
          <div className="border-t pt-4">
            <h4 className="font-semibold mb-3">Take Action</h4>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              <Button
                className="bg-green-600 hover:bg-green-700 text-white"
                onClick={() => onUpdateStage(applicant.id, 'shortlisted')}
                data-testid="action-shortlist"
              >
                <CheckCircle className="h-4 w-4 mr-1" /> Shortlist
              </Button>
              <Button
                variant="outline"
                className="text-red-600 border-red-200 hover:bg-red-50"
                onClick={() => onUpdateStage(applicant.id, 'rejected')}
                data-testid="action-reject"
              >
                <XCircle className="h-4 w-4 mr-1" /> Reject
              </Button>
              <Button
                variant="outline"
                className="text-gray-600 hover:bg-gray-50"
                onClick={() => onUpdateStage(applicant.id, 'on_hold')}
                data-testid="action-hold"
              >
                <Pause className="h-4 w-4 mr-1" /> Hold
              </Button>
              <Button
                variant="outline"
                className="text-orange-600 border-orange-200 hover:bg-orange-50"
                onClick={() => onUpdateStage(applicant.id, 'over_budget')}
                data-testid="action-over-budget"
              >
                <TrendingDown className="h-4 w-4 mr-1" /> Over Budget
              </Button>
              <Button
                variant="outline"
                className="text-rose-600 border-rose-200 hover:bg-rose-50"
                onClick={() => onUpdateStage(applicant.id, 'not_qualified')}
                data-testid="action-not-qualified"
              >
                <UserX className="h-4 w-4 mr-1" /> Not Qualified
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
