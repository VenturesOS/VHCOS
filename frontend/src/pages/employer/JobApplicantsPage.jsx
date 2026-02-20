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
  TrendingDown, UserX, ChevronRight, Star, Edit2, Download, Eye
} from 'lucide-react';

// Stage configuration with colors and icons
const STAGES = {
  applied: { label: 'Applied', color: 'bg-blue-100 text-blue-700', icon: Users },
  shortlisted: { label: 'Shortlisted', color: 'bg-green-100 text-green-700', icon: CheckCircle },
  submitted_to_client: { label: 'Submitted', color: 'bg-cyan-100 text-cyan-700', icon: Users },
  interview: { label: 'Interview', color: 'bg-purple-100 text-purple-700', icon: Users },
  offered: { label: 'Offered', color: 'bg-amber-100 text-amber-700', icon: Star },
  hired: { label: 'Hired', color: 'bg-emerald-100 text-emerald-700', icon: CheckCircle },
  joined: { label: 'Joined', color: 'bg-teal-100 text-teal-700', icon: CheckCircle },
  rejected: { label: 'Rejected', color: 'bg-red-100 text-red-700', icon: XCircle },
  on_hold: { label: 'On Hold', color: 'bg-gray-100 text-gray-700', icon: Pause },
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

  const loadApplicants = async (updateSelectedId = null) => {
    setLoading(true);
    try {
      const res = await jobAPI.getApplicants(jobId);
      setJobData(res.data.job);
      setApplicants(res.data.applicants);
      setStageCounts(res.data.stage_counts);
      
      // If we have a selected applicant, update it with fresh data
      if (updateSelectedId) {
        const updatedApplicant = res.data.applicants.find(a => a.id === updateSelectedId);
        if (updatedApplicant) {
          setSelectedApplicant(updatedApplicant);
        }
      }
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
        onRefresh={(applicantId) => loadApplicants(applicantId)}
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

// Applicant Detail Dialog Component with Edit Mode
function ApplicantDetailDialog({ applicant, jobData, onClose, onUpdateStage, onRefresh }) {
  const [isEditMode, setIsEditMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editForm, setEditForm] = useState({
    current_salary: '',
    notice_period: '',
    skills: [],
    experience_summary: ''
  });
  const [newSkill, setNewSkill] = useState('');

  // Initialize form when applicant changes
  useEffect(() => {
    if (applicant) {
      setEditForm({
        current_salary: applicant.current_salary || '',
        notice_period: applicant.notice_period || '',
        skills: applicant.skills || [],
        experience_summary: applicant.experience_summary || applicant.summary || ''
      });
      setIsEditMode(false);
    }
  }, [applicant]);

  const handleSaveDetails = async () => {
    setSaving(true);
    try {
      const updateData = {
        current_salary: editForm.current_salary ? parseInt(editForm.current_salary) : null,
        notice_period: editForm.notice_period || null,
        skills: editForm.skills.length > 0 ? editForm.skills : null,
        experience_summary: editForm.experience_summary || null
      };
      
      await applicationAPI.updateDetails(applicant.id, updateData);
      toast.success('Details updated successfully');
      setIsEditMode(false);
      if (onRefresh) onRefresh(applicant.id);
    } catch (error) {
      toast.error('Failed to update details');
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  const handleAddSkill = () => {
    if (newSkill.trim() && !editForm.skills.includes(newSkill.trim())) {
      setEditForm(prev => ({
        ...prev,
        skills: [...prev.skills, newSkill.trim()]
      }));
      setNewSkill('');
    }
  };

  const handleRemoveSkill = (skillToRemove) => {
    setEditForm(prev => ({
      ...prev,
      skills: prev.skills.filter(s => s !== skillToRemove)
    }));
  };

  if (!applicant) return null;

  const StageIcon = STAGES[applicant.stage]?.icon || Users;

  return (
    <Dialog open={!!applicant} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <div>
              <DialogTitle className="font-heading text-xl">Applicant Review</DialogTitle>
              <DialogDescription>
                Review candidate details and take action
              </DialogDescription>
            </div>
            {!isEditMode ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsEditMode(true)}
                data-testid="edit-details-btn"
              >
                <Edit2 className="h-4 w-4 mr-1" /> Edit Details
              </Button>
            ) : (
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsEditMode(false)}
                  disabled={saving}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  className="bg-[#7CB342] hover:bg-[#689F38]"
                  onClick={handleSaveDetails}
                  disabled={saving}
                  data-testid="save-details-btn"
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </Button>
              </div>
            )}
          </div>
        </DialogHeader>
        
        <div className="space-y-6">
          {/* Last Edited By Info */}
          {applicant.last_edited_by && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm">
              <span className="text-amber-700">
                Last updated by <strong>{applicant.last_edited_by.name}</strong> ({applicant.last_edited_by.role})
                {applicant.last_edited_by.timestamp && (
                  <> on {new Date(applicant.last_edited_by.timestamp).toLocaleDateString()}</>
                )}
              </span>
            </div>
          )}

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
                {applicant.manually_edited && (
                  <Badge variant="secondary" className="text-xs">Manually Edited</Badge>
                )}
              </div>
              <p className="text-slate-600 mt-1">{applicant.headline}</p>
              
              {/* Contact Info (read-only) */}
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

          {/* Key Details Grid - Editable in Edit Mode */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Experience</p>
              <p className="font-semibold text-lg">{applicant.experience_years || 0} years</p>
            </div>
            
            {/* Current Salary - Editable */}
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Current Salary (INR)</p>
              {isEditMode ? (
                <input
                  type="number"
                  className="w-full p-1 border rounded text-lg font-semibold"
                  value={editForm.current_salary}
                  onChange={(e) => setEditForm(prev => ({ ...prev, current_salary: e.target.value }))}
                  placeholder="e.g., 1500000"
                  data-testid="edit-salary-input"
                />
              ) : (
                <p className="font-semibold text-lg">
                  {applicant.current_salary ? formatSalaryINR(applicant.current_salary) : 'Not provided'}
                </p>
              )}
            </div>
            
            {/* Notice Period - Editable */}
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Notice Period</p>
              {isEditMode ? (
                <select
                  className="w-full p-1 border rounded text-lg font-semibold"
                  value={editForm.notice_period}
                  onChange={(e) => setEditForm(prev => ({ ...prev, notice_period: e.target.value }))}
                  data-testid="edit-notice-select"
                >
                  <option value="">Select...</option>
                  <option value="Immediate">Immediate</option>
                  <option value="15 days">15 days</option>
                  <option value="30 days">30 days</option>
                  <option value="45 days">45 days</option>
                  <option value="60 days">60 days</option>
                  <option value="90 days">90 days</option>
                  <option value="More than 90 days">More than 90 days</option>
                </select>
              ) : (
                <p className="font-semibold text-lg">{applicant.notice_period || 'Not provided'}</p>
              )}
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

          {/* Additional Mandatory Details */}
          <div className="grid grid-cols-2 gap-4 bg-slate-50 p-4 rounded-lg">
            <div>
              <p className="text-xs text-slate-500 flex items-center gap-1">
                <Briefcase className="w-3 h-3" /> Current Employer
              </p>
              <p className="font-medium">{applicant.current_employer || <span className="text-amber-600">Not provided</span>}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500 flex items-center gap-1">
                <Briefcase className="w-3 h-3" /> Designation
              </p>
              <p className="font-medium">{applicant.designation || applicant.headline || <span className="text-amber-600">Not provided</span>}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500 flex items-center gap-1">
                <Briefcase className="w-3 h-3" /> Industry
                {applicant.industry_source === 'ai_detected' && (
                  <Badge variant="secondary" className="bg-green-100 text-green-700 text-xs ml-1">AI</Badge>
                )}
              </p>
              <p className="font-medium">{applicant.industry || '-'}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500 flex items-center gap-1">
                <FileText className="w-3 h-3" /> Education
              </p>
              <p className="font-medium">{applicant.ug_course || applicant.education?.[0]?.degree || '-'}</p>
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

          {/* Skills - Editable */}
          <div>
            <h4 className="font-semibold mb-2">Skills {isEditMode && <span className="text-xs font-normal text-slate-500">(Click × to remove, type to add)</span>}</h4>
            {isEditMode ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2 p-2 border rounded-lg bg-white min-h-[48px]">
                  {editForm.skills.map((skill, idx) => (
                    <span key={idx} className="bg-green-100 text-green-700 px-2 py-1 rounded-full text-sm flex items-center gap-1">
                      {skill}
                      <button
                        type="button"
                        onClick={() => handleRemoveSkill(skill)}
                        className="text-green-700 hover:text-red-600 ml-1"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    className="flex-1 p-2 border rounded"
                    placeholder="Add a skill..."
                    value={newSkill}
                    onChange={(e) => setNewSkill(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddSkill())}
                    data-testid="add-skill-input"
                  />
                  <Button type="button" variant="outline" onClick={handleAddSkill}>Add</Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {(applicant.skills || []).map((skill, idx) => (
                  <Badge key={idx} variant="secondary">{skill}</Badge>
                ))}
                {(!applicant.skills || applicant.skills.length === 0) && (
                  <span className="text-slate-400 text-sm">No skills listed</span>
                )}
              </div>
            )}
          </div>

          {/* Experience Summary - Editable */}
          <div>
            <h4 className="font-semibold mb-2">Experience Summary</h4>
            {isEditMode ? (
              <textarea
                className="w-full p-3 border rounded-lg bg-white"
                rows={4}
                value={editForm.experience_summary}
                onChange={(e) => setEditForm(prev => ({ ...prev, experience_summary: e.target.value }))}
                placeholder="Brief summary of candidate's experience..."
                data-testid="edit-summary-textarea"
              />
            ) : (
              <p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">
                {applicant.experience_summary || applicant.summary || 'No summary available'}
              </p>
            )}
          </div>

          {/* Cover Letter */}
          {applicant.cover_letter && (
            <div>
              <h4 className="font-semibold mb-2">Cover Letter</h4>
              <p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">{applicant.cover_letter}</p>
            </div>
          )}

          {/* Resume Preview & Download */}
          <div>
            <h4 className="font-semibold mb-2">Resume / CV</h4>
            {applicant.resume_url ? (
              <div className="flex flex-wrap items-center gap-3 p-3 bg-slate-50 rounded-lg">
                <FileText className="h-6 w-6 text-[#7CB342]" />
                <span className="text-sm text-slate-600 flex-1">
                  {applicant.candidate_name?.replace(/\s+/g, '_')}_VHC
                  {applicant.resume_url.split('.').pop() ? `.${applicant.resume_url.split('.').pop()}` : '.pdf'}
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      // Open resume in new tab for preview
                      const previewUrl = `${applicant.resume_url}`;
                      window.open(previewUrl, '_blank');
                    }}
                    data-testid="preview-resume-btn"
                  >
                    <Eye className="h-4 w-4 mr-1" /> Preview
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-[#7CB342] border-[#7CB342] hover:bg-green-50"
                    onClick={() => {
                      // Download with proper naming
                      const token = localStorage.getItem('vhc_token');
                      const downloadUrl = `/api/applications/${applicant.id}/resume`;
                      
                      // Create a temporary link to trigger download with auth
                      fetch(downloadUrl, {
                        headers: { Authorization: `Bearer ${token}` }
                      })
                      .then(response => {
                        if (!response.ok) throw new Error('Download failed');
                        const disposition = response.headers.get('content-disposition');
                        let filename = 'resume.pdf';
                        if (disposition) {
                          const match = disposition.match(/filename="?([^";\n]+)"?/);
                          if (match) filename = match[1];
                        }
                        return response.blob().then(blob => ({ blob, filename }));
                      })
                      .then(({ blob, filename }) => {
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = filename;
                        document.body.appendChild(a);
                        a.click();
                        window.URL.revokeObjectURL(url);
                        a.remove();
                        toast.success('Resume downloaded');
                      })
                      .catch(() => toast.error('Failed to download resume'));
                    }}
                    data-testid="download-resume-btn"
                  >
                    <Download className="h-4 w-4 mr-1" /> Download
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-400 italic p-3 bg-slate-50 rounded-lg">
                No resume uploaded for this application
              </p>
            )}
          </div>

          {/* Action Buttons */}
          {!isEditMode && (
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
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
