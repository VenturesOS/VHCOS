import { useState, useEffect, useCallback } from 'react';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { employerPortalAPI, applicationAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { 
  Users, CheckCircle, Clock, Award, UserCheck, XCircle, Pause, Send,
  Filter, Briefcase, FileText, Mail, Phone, Calendar, Download,
  ChevronRight, MessageSquare, Star, Building2, Lock
} from 'lucide-react';

// Stage configuration — simplified pipeline (no approval barricade)
// Sourced → Submitted → Shortlisted → Interviewed → Offered → Hired → Joined
const STAGES = [
  { id: 'sourced', label: 'Sourced', color: 'border-slate-400 bg-slate-50', textColor: 'text-slate-700', icon: Users, desc: 'Added as applicant' },
  { id: 'submitted_to_client', label: 'Submitted', color: 'border-cyan-400 bg-cyan-50', textColor: 'text-cyan-700', icon: Send, desc: 'Sent to client' },
  { id: 'shortlisted', label: 'Shortlisted', color: 'border-amber-400 bg-amber-50', textColor: 'text-amber-700', icon: CheckCircle, desc: 'Shortlisted' },
  { id: 'interview', label: 'Interviewed', color: 'border-purple-400 bg-purple-50', textColor: 'text-purple-700', icon: Clock, desc: 'In process' },
  { id: 'offered', label: 'Offered', color: 'border-green-400 bg-green-50', textColor: 'text-green-700', icon: Award, desc: 'Offer extended' },
  { id: 'hired', label: 'Hired', color: 'border-emerald-400 bg-emerald-50', textColor: 'text-emerald-700', icon: UserCheck, desc: 'Offer accepted' },
  { id: 'joined', label: 'Joined', color: 'border-teal-400 bg-teal-50', textColor: 'text-teal-700', icon: Lock, desc: 'Revenue confirmed' },
];

const BOTTOM_STAGES = [
  { id: 'rejected', label: 'Rejected', color: 'border-red-400 bg-red-50', textColor: 'text-red-700', icon: XCircle, desc: 'Auto-hides after 7 days' },
  { id: 'on_hold', label: 'On Hold', color: 'border-gray-400 bg-gray-50', textColor: 'text-gray-700', icon: Pause, desc: 'Paused — stays in records' },
];

export default function EmployerPipelinePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [pipelineData, setPipelineData] = useState({});
  const [stageCounts, setStageCounts] = useState({});
  const [totalApplications, setTotalApplications] = useState(0);
  const [filters, setFilters] = useState({ recruiters: [], jobs: [] });
  
  // Filter state
  const [selectedRecruiter, setSelectedRecruiter] = useState('all');
  const [selectedJob, setSelectedJob] = useState(searchParams.get('job_id') || 'all');

  // Deep-link: if URL contains ?job_id=X, keep it in sync with state.
  useEffect(() => {
    const urlJob = searchParams.get('job_id');
    if (urlJob && urlJob !== selectedJob) setSelectedJob(urlJob);
  }, [searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateSelectedJob = (v) => {
    setSelectedJob(v);
    if (v === 'all') {
      if (searchParams.get('job_id')) {
        searchParams.delete('job_id');
        setSearchParams(searchParams, { replace: true });
      }
    } else if (searchParams.get('job_id') !== v) {
      searchParams.set('job_id', v);
      setSearchParams(searchParams, { replace: true });
    }
  };
  
  // Detail dialog
  const [selectedApp, setSelectedApp] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [addingNote, setAddingNote] = useState(false);

  const loadPipeline = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedRecruiter !== 'all') params.recruiter_id = selectedRecruiter;
      if (selectedJob !== 'all') params.job_id = selectedJob;
      
      const res = await employerPortalAPI.getPipeline(params);
      setPipelineData(res.data.pipeline);
      setStageCounts(res.data.stage_counts);
      setTotalApplications(res.data.total_applications);
      setFilters(res.data.filters);
    } catch (error) {
      toast.error('Failed to load pipeline data');
    } finally {
      setLoading(false);
    }
  }, [selectedRecruiter, selectedJob]);

  useEffect(() => {
    loadPipeline();
  }, [loadPipeline]);

  const handleDragEnd = async (result) => {
    if (!result.destination) return;
    
    const { draggableId, source, destination } = result;
    const newStage = destination.droppableId;
    const oldStage = source.droppableId;
    
    if (oldStage === newStage) return;

    // Optimistic update
    const movedApp = pipelineData[oldStage].find(app => app.id === draggableId);
    if (!movedApp) return;

    setPipelineData(prev => ({
      ...prev,
      [oldStage]: (prev[oldStage] || []).filter(app => app.id !== draggableId),
      [newStage]: [...(prev[newStage] || []), { ...movedApp, stage: newStage }]
    }));
    setStageCounts(prev => ({
      ...prev,
      [oldStage]: (prev[oldStage] || 0) - 1,
      [newStage]: (prev[newStage] || 0) + 1
    }));

    try {
      await applicationAPI.update(draggableId, { stage: newStage });
      toast.success(`Moved to ${STAGES.find(s => s.id === newStage)?.label || newStage}`);
    } catch (error) {
      // Revert on error
      toast.error('Failed to update stage');
      loadPipeline();
    }
  };

  const handleAddNote = async () => {
    if (!noteText.trim() || !selectedApp) return;
    
    setAddingNote(true);
    try {
      await applicationAPI.addNote(selectedApp.id, noteText);
      toast.success('Note added');
      setNoteText('');
      // Refresh to get updated notes
      loadPipeline();
      // Update selected app's notes locally
      setSelectedApp(prev => ({
        ...prev,
        notes: [...(prev.notes || []), { content: noteText, created_at: new Date().toISOString() }]
      }));
    } catch (error) {
      toast.error('Failed to add note');
    } finally {
      setAddingNote(false);
    }
  };

  const clearFilters = () => {
    setSelectedRecruiter('all');
    updateSelectedJob('all');
  };

  const getStageConfig = (stageId) => STAGES.find(s => s.id === stageId) || STAGES[0];

  if (loading && totalApplications === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="employer-pipeline-page">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Hiring Pipeline</h1>
          <p className="text-slate-500 mt-1">
            Drag candidates across stages • {totalApplications} total applications
          </p>
        </div>
        
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Filter className="w-4 h-4" />
            <span>Filter:</span>
          </div>
          
          <Select value={selectedRecruiter} onValueChange={setSelectedRecruiter}>
            <SelectTrigger className="w-[180px]" data-testid="recruiter-filter">
              <SelectValue placeholder="All Recruiters" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Recruiters</SelectItem>
              {filters.recruiters.map(rec => (
                <SelectItem key={rec.id} value={rec.id}>{rec.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          
          <Select value={selectedJob} onValueChange={updateSelectedJob}>
            <SelectTrigger className="w-[200px]" data-testid="job-filter">
              <SelectValue placeholder="All Jobs" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Jobs</SelectItem>
              {filters.jobs.map(job => (
                <SelectItem key={job.id} value={job.id}>
                  {job.title} {job.company_name && `(${job.company_name})`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          
          {(selectedRecruiter !== 'all' || selectedJob !== 'all') && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Deep-link banner — shown when user arrived via Jobs page eye-icon */}
      {selectedJob !== 'all' && (
        <div
          className="bg-[#DCFCE7] border border-[#7CB342]/40 rounded-lg px-4 py-2 flex items-center justify-between gap-3 text-sm"
          data-testid="pipeline-active-filter-banner"
        >
          <div className="flex items-center gap-2 text-[#3f6d1b]">
            <Briefcase className="w-4 h-4" />
            <span>
              Showing pipeline for:&nbsp;
              <strong>
                {filters.jobs.find((j) => j.id === selectedJob)?.title || 'Selected job'}
              </strong>
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="text-[#3f6d1b] hover:bg-[#7CB342]/10 h-7"
            onClick={() => updateSelectedJob('all')}
            data-testid="pipeline-clear-job-filter-btn"
          >
            Show all jobs
          </Button>
        </div>
      )}

      {/* Stage Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        {STAGES.map(stage => {
          const Icon = stage.icon;
          const count = stageCounts[stage.id] || 0;
          return (
            <Card key={stage.id} className={`${stage.color} border-2`}>
              <CardContent className="p-3 text-center">
                <Icon className={`w-5 h-5 mx-auto mb-1 ${stage.textColor}`} />
                <p className={`text-2xl font-bold ${stage.textColor}`}>{count}</p>
                <p className="text-xs text-slate-600">{stage.label}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Kanban Board */}
      <DragDropContext onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-4 overflow-x-auto pb-4">
          {STAGES.map(stage => (
            <div key={stage.id} className="min-w-[280px]">
              <div className={`rounded-t-lg p-3 ${stage.color} border-2 border-b-0 ${stage.textColor}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <stage.icon className="w-4 h-4" />
                    <span className="font-semibold">{stage.label}</span>
                  </div>
                  <Badge variant="secondary" className="bg-white/80">
                    {stageCounts[stage.id] || 0}
                  </Badge>
                </div>
                <p className="text-xs mt-1 opacity-75">{stage.desc}</p>
              </div>
              
              <Droppable droppableId={stage.id}>
                {(provided, snapshot) => (
                  <div
                    ref={provided.innerRef}
                    {...provided.droppableProps}
                    className={`min-h-[400px] p-2 border-2 border-t-0 rounded-b-lg transition-colors ${
                      snapshot.isDraggingOver ? 'bg-slate-100' : 'bg-white'
                    }`}
                  >
                    {(pipelineData[stage.id] || []).map((app, index) => (
                      <Draggable key={app.id} draggableId={app.id} index={index}>
                        {(provided, snapshot) => (
                          <div
                            ref={provided.innerRef}
                            {...provided.draggableProps}
                            {...provided.dragHandleProps}
                            className={`mb-2 p-3 bg-white border rounded-lg shadow-sm cursor-grab hover:shadow-md transition-shadow ${
                              snapshot.isDragging ? 'shadow-lg rotate-2' : ''
                            }`}
                            onClick={() => {
                              setSelectedApp(app);
                              setShowDetail(true);
                            }}
                            data-testid={`candidate-card-${app.id}`}
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex-1 min-w-0">
                                <p className="font-medium text-slate-900 truncate">
                                  {app.candidate_name}
                                </p>
                                <p className="text-xs text-slate-500 truncate">
                                  {app.job_title}
                                </p>
                              </div>
                              {app.match_score > 0 && (
                                <Badge variant="outline" className="ml-2 text-xs">
                                  <Star className="w-3 h-3 mr-1 text-amber-500" />
                                  {app.match_score}%
                                </Badge>
                              )}
                            </div>
                            
                            <div className="space-y-1 text-xs text-slate-600">
                              {app.current_salary && (
                                <div className="flex items-center gap-1">
                                  <span className="text-slate-400">CTC:</span>
                                  <span>{formatSalaryINR(app.current_salary)}</span>
                                </div>
                              )}
                              {app.notice_period && (
                                <div className="flex items-center gap-1">
                                  <span className="text-slate-400">Notice:</span>
                                  <span>{app.notice_period}</span>
                                </div>
                              )}
                              {app.company_name && (
                                <div className="flex items-center gap-1">
                                  <Building2 className="w-3 h-3 text-slate-400" />
                                  <span className="truncate">{app.company_name}</span>
                                </div>
                              )}
                            </div>
                            
                            {app.notes?.length > 0 && (
                              <div className="mt-2 pt-2 border-t flex items-center gap-1 text-xs text-slate-400">
                                <MessageSquare className="w-3 h-3" />
                                <span>{app.notes.length} notes</span>
                              </div>
                            )}
                            {/* Quick-move chips */}
                            <div className="mt-2 pt-2 border-t border-slate-100 flex flex-wrap gap-1" onClick={(e) => e.stopPropagation()}>
                              {[...STAGES, ...BOTTOM_STAGES]
                                .filter((s) => s.id !== stage.id)
                                .map((s) => (
                                  <button
                                    key={s.id}
                                    onClick={async (e) => {
                                      e.stopPropagation();
                                      try {
                                        await applicationAPI.update(app.id, { stage: s.id });
                                        toast.success(`Moved to ${s.label}`);
                                        loadPipeline();
                                      } catch { toast.error('Failed to update'); }
                                    }}
                                    className="px-1.5 py-0.5 text-[10px] rounded border border-slate-200 text-slate-600 hover:bg-slate-100 hover:border-slate-300 transition-colors"
                                    data-testid={`employer-quick-move-${app.id}-${s.id}`}
                                  >
                                    {s.label}
                                  </button>
                                ))}
                            </div>
                          </div>
                        )}
                      </Draggable>
                    ))}
                    {provided.placeholder}
                    
                    {(pipelineData[stage.id] || []).length === 0 && (
                      <div className="text-center py-8 text-slate-400 text-sm">
                        No candidates
                      </div>
                    )}
                  </div>
                )}
              </Droppable>
            </div>
          ))}
        </div>

        {/* Bottom row — Rejected / On Hold */}
        <div className="mt-6">
          <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2 px-1">Secondary</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {BOTTOM_STAGES.map(stage => (
              <div key={stage.id}>
                <div className={`rounded-t-lg p-3 ${stage.color} border-2 border-b-0 ${stage.textColor}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <stage.icon className="w-4 h-4" />
                      <span className="font-semibold">{stage.label}</span>
                    </div>
                    <Badge variant="secondary" className="bg-white/80">
                      {stageCounts[stage.id] || 0}
                    </Badge>
                  </div>
                  <p className="text-xs mt-1 opacity-75">{stage.desc}</p>
                </div>
                <Droppable droppableId={stage.id}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      className={`min-h-[120px] p-2 border-2 border-t-0 rounded-b-lg transition-colors ${
                        snapshot.isDraggingOver ? 'bg-slate-100' : 'bg-white'
                      }`}
                    >
                      {(pipelineData[stage.id] || []).map((app, index) => (
                        <Draggable key={app.id} draggableId={app.id} index={index}>
                          {(provided, snapshot) => (
                            <div
                              ref={provided.innerRef}
                              {...provided.draggableProps}
                              {...provided.dragHandleProps}
                              className={`mb-2 p-2 bg-white border rounded-lg shadow-sm cursor-grab hover:shadow-md transition-shadow ${
                                snapshot.isDragging ? 'shadow-lg rotate-2' : ''
                              }`}
                              onClick={() => { setSelectedApp(app); setShowDetail(true); }}
                              data-testid={`candidate-card-${app.id}`}
                            >
                              <p className="font-medium text-sm text-slate-900 truncate">{app.candidate_name}</p>
                              <p className="text-xs text-slate-500 truncate">{app.job_title}</p>
                            </div>
                          )}
                        </Draggable>
                      ))}
                      {provided.placeholder}
                      {(pipelineData[stage.id] || []).length === 0 && (
                        <div className="text-center py-4 text-slate-400 text-xs">No candidates</div>
                      )}
                    </div>
                  )}
                </Droppable>
              </div>
            ))}
          </div>
        </div>
      </DragDropContext>

      {/* Candidate Detail Dialog */}
      <Dialog open={showDetail} onOpenChange={setShowDetail}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="w-5 h-5 text-[#7CB342]" />
              Candidate Details
            </DialogTitle>
          </DialogHeader>
          
          {selectedApp && (
            <div className="space-y-6">
              {/* Basic Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">
                    {selectedApp.candidate_name}
                  </h3>
                  <p className="text-sm text-slate-500">{selectedApp.job_title}</p>
                  <Badge className={`mt-2 ${getStageConfig(selectedApp.stage).color} ${getStageConfig(selectedApp.stage).textColor}`}>
                    {getStageConfig(selectedApp.stage).label}
                  </Badge>
                </div>
                <div className="space-y-2 text-sm">
                  {selectedApp.candidate_email && (
                    <div className="flex items-center gap-2">
                      <Mail className="w-4 h-4 text-slate-400" />
                      <a href={`mailto:${selectedApp.candidate_email}`} className="text-blue-600 hover:underline">
                        {selectedApp.candidate_email}
                      </a>
                    </div>
                  )}
                  {selectedApp.candidate_phone && (
                    <div className="flex items-center gap-2">
                      <Phone className="w-4 h-4 text-slate-400" />
                      <span>{selectedApp.candidate_phone}</span>
                    </div>
                  )}
                  {selectedApp.applied_at && (
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4 text-slate-400" />
                      <span>Applied: {new Date(selectedApp.applied_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* View Full Profile Button */}
              {selectedApp.candidate_id && (
                <Button
                  variant="outline"
                  className="w-full text-orange-600 border-orange-300 hover:bg-orange-50"
                  onClick={() => {
                    setShowDetail(false);
                    navigate(`../naukri-profile/${selectedApp.candidate_id}`);
                  }}
                  data-testid="view-full-profile-pipeline"
                >
                  <FileText className="w-4 h-4 mr-2" /> View Full Profile
                </Button>
              )}

              {/* Salary & Experience */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-slate-50 rounded-lg">
                <div>
                  <p className="text-xs text-slate-500">Current CTC</p>
                  <p className="font-semibold">{selectedApp.current_salary ? formatSalaryINR(selectedApp.current_salary) : '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Expected CTC</p>
                  <p className="font-semibold">{selectedApp.expected_salary ? formatSalaryINR(selectedApp.expected_salary) : '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Experience</p>
                  <p className="font-semibold">{selectedApp.experience_years ? `${selectedApp.experience_years} years` : '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Notice Period</p>
                  <p className="font-semibold">{selectedApp.notice_period || '-'}</p>
                </div>
              </div>

              {/* Additional Mandatory Fields */}
              <div className="grid grid-cols-2 gap-4 p-4 bg-slate-50 rounded-lg">
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Building2 className="w-3 h-3" /> Location
                  </p>
                  <p className="font-medium">{selectedApp.location || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Building2 className="w-3 h-3" /> Current Employer
                  </p>
                  <p className="font-medium truncate">{selectedApp.current_employer || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Briefcase className="w-3 h-3" /> Designation
                  </p>
                  <p className="font-medium truncate">{selectedApp.designation || selectedApp.headline || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Building2 className="w-3 h-3" /> Industry
                  </p>
                  <p className="font-medium">{selectedApp.industry || '-'}</p>
                </div>
                <div className="col-span-2">
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <FileText className="w-3 h-3" /> Education
                  </p>
                  <p className="font-medium">{selectedApp.ug_course || selectedApp.education?.[0]?.degree || '-'}</p>
                </div>
              </div>

              {/* Resume Download */}
              {selectedApp.resume_url && (
                <div>
                  <Button variant="outline" asChild>
                    <a href={selectedApp.resume_url} target="_blank" rel="noopener noreferrer">
                      <Download className="w-4 h-4 mr-2" />
                      Download Resume
                    </a>
                  </Button>
                </div>
              )}

              {/* Stage Transition Buttons */}
              <div>
                <p className="text-sm font-medium text-slate-700 mb-2">Move to Stage:</p>
                <div className="flex flex-wrap gap-2">
                  {[...STAGES, ...BOTTOM_STAGES].filter(s => s.id !== selectedApp.stage).map(stage => (
                    <Button
                      key={stage.id}
                      variant="outline"
                      size="sm"
                      className={`${stage.color} ${stage.textColor} border-2 hover:opacity-80`}
                      onClick={async () => {
                        try {
                          await applicationAPI.update(selectedApp.id, { stage: stage.id });
                          toast.success(`Moved to ${stage.label}`);
                          setSelectedApp(prev => ({ ...prev, stage: stage.id }));
                          loadPipeline();
                        } catch (error) {
                          toast.error('Failed to update stage');
                        }
                      }}
                      data-testid={`move-to-${stage.id}`}
                    >
                      <stage.icon className="w-4 h-4 mr-1" />
                      {stage.label}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Notes Section */}
              <div className="border-t pt-4">
                <h4 className="font-medium text-slate-700 mb-3 flex items-center gap-2">
                  <MessageSquare className="w-4 h-4" />
                  Notes ({selectedApp.notes?.length || 0})
                </h4>
                
                {/* Existing Notes */}
                <div className="space-y-2 mb-4 max-h-40 overflow-y-auto">
                  {selectedApp.notes?.map((note, idx) => (
                    <div key={idx} className="p-3 bg-slate-50 rounded-lg text-sm">
                      <p className="text-slate-700">{note.content}</p>
                      <p className="text-xs text-slate-400 mt-1">
                        {note.author_name && `${note.author_name} • `}
                        {new Date(note.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
                      </p>
                    </div>
                  ))}
                  {(!selectedApp.notes || selectedApp.notes.length === 0) && (
                    <p className="text-sm text-slate-400">No notes yet</p>
                  )}
                </div>
                
                {/* Add Note */}
                <div className="flex gap-2">
                  <Textarea
                    placeholder="Add a note..."
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value)}
                    className="flex-1"
                    rows={2}
                    data-testid="note-input"
                  />
                  <Button 
                    onClick={handleAddNote} 
                    disabled={!noteText.trim() || addingNote}
                    data-testid="add-note-btn"
                  >
                    {addingNote ? 'Adding...' : 'Add'}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
