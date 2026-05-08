import { useState, useEffect, useCallback } from 'react';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { applicationAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { ClipboardList, User, Mail, FileText, Plus, MessageSquare } from 'lucide-react';

const STAGES = [
  { id: 'sourced', label: 'Sourced', color: 'border-slate-400 bg-slate-50', desc: 'Added as applicant' },
  { id: 'submitted_to_client', label: 'Submitted', color: 'border-cyan-400 bg-cyan-50', desc: 'Sent to client' },
  { id: 'shortlisted', label: 'Shortlisted', color: 'border-amber-400 bg-amber-50', desc: 'Shortlisted' },
  { id: 'interview', label: 'Interviewed', color: 'border-purple-400 bg-purple-50', desc: 'In process' },
  { id: 'offered', label: 'Offered', color: 'border-green-400 bg-green-50', desc: 'Offer extended' },
  { id: 'hired', label: 'Hired', color: 'border-emerald-400 bg-emerald-50', desc: 'Offer accepted' },
  { id: 'joined', label: 'Joined', color: 'border-teal-400 bg-teal-50', desc: 'Revenue confirmed' },
];

const BOTTOM_STAGES = [
  { id: 'rejected', label: 'Rejected', color: 'border-red-400 bg-red-50', desc: 'Auto-hides after 7 days' },
  { id: 'on_hold', label: 'On Hold', color: 'border-gray-400 bg-gray-50', desc: 'Paused — stays in records' },
];

export default function PipelinePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [applications, setApplications] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(searchParams.get('job_id') || 'all');
  const [loading, setLoading] = useState(true);
  const [selectedApp, setSelectedApp] = useState(null);
  const [noteText, setNoteText] = useState('');

  // Keep URL ↔ state in sync so the filter survives refreshes and can be
  // deep-linked (e.g. from the Jobs page "View Pipeline" icon).
  useEffect(() => {
    const urlJob = searchParams.get('job_id');
    if (urlJob && urlJob !== selectedJob) {
      setSelectedJob(urlJob);
    }
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

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadApplications = useCallback(async () => {
    setLoading(true);
    try {
      const params = selectedJob !== 'all' ? { job_id: selectedJob } : {};
      const res = await applicationAPI.getAll(params);
      setApplications(res.data);
    } catch (error) {
      toast.error('Failed to load applications');
    } finally {
      setLoading(false);
    }
  }, [selectedJob]);

  useEffect(() => {
    loadApplications();
  }, [loadApplications]);

  const loadData = async () => {
    try {
      const jobsRes = await jobAPI.getAll();
      setJobs(jobsRes.data);
    } catch (error) {
      toast.error('Failed to load jobs');
    }
  };

  const handleDragEnd = async (result) => {
    if (!result.destination) return;

    const { draggableId, destination } = result;
    const newStage = destination.droppableId;

    try {
      await applicationAPI.update(draggableId, { stage: newStage });
      setApplications((prev) =>
        prev.map((app) => (app.id === draggableId ? { ...app, stage: newStage } : app))
      );
      toast.success(`Moved to ${newStage}`);
    } catch (error) {
      toast.error('Failed to update status');
    }
  };

  const handleAddNote = async () => {
    if (!noteText.trim()) return;
    try {
      await applicationAPI.addNote(selectedApp.id, noteText);
      toast.success('Note added');
      setNoteText('');
      loadApplications();
    } catch (error) {
      toast.error('Failed to add note');
    }
  };

  const handleQuickMove = async (appId, newStage, e) => {
    e?.stopPropagation?.();
    try {
      await applicationAPI.update(appId, { stage: newStage });
      setApplications((prev) =>
        prev.map((app) => (app.id === appId ? { ...app, stage: newStage } : app))
      );
      const label = [...STAGES, ...BOTTOM_STAGES].find(s => s.id === newStage)?.label || newStage;
      toast.success(`Moved to ${label}`);
    } catch (error) {
      toast.error('Failed to update status');
    }
  };

  const getApplicationsByStage = (stageId) =>
    applications.filter((app) => app.stage === stageId);

  if (loading && applications.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="pipeline-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Candidate Pipeline</h1>
          <p className="text-slate-500 mt-1">Drag candidates between stages to update status</p>
        </div>
        <Select value={selectedJob} onValueChange={updateSelectedJob}>
          <SelectTrigger className="w-full sm:w-64" data-testid="job-filter-select">
            <SelectValue placeholder="Filter by mandate" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Mandates</SelectItem>
            {jobs.map((job) => (
              <SelectItem key={job.id} value={job.id}>
                {job.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Active filter indicator — shown when user deep-linked here from Jobs page */}
      {selectedJob !== 'all' && (
        <div
          className="bg-[#DCFCE7] border border-[#7CB342]/40 rounded-lg px-4 py-2 flex items-center justify-between gap-3 text-sm"
          data-testid="pipeline-active-filter-banner"
        >
          <div className="flex items-center gap-2 text-[#3f6d1b]">
            <ClipboardList className="w-4 h-4" />
            <span>
              Showing pipeline for:&nbsp;
              <strong>{jobs.find((j) => j.id === selectedJob)?.title || 'Selected mandate'}</strong>
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="text-[#3f6d1b] hover:bg-[#7CB342]/10 h-7"
            onClick={() => updateSelectedJob('all')}
            data-testid="pipeline-clear-job-filter-btn"
          >
            Show all mandates
          </Button>
        </div>
      )}

      {/* Help Tip */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-700 flex items-start gap-3">
        <ClipboardList className="w-5 h-5 shrink-0 mt-0.5" />
        <div>
          <p className="font-medium">Workflow Tip</p>
          <p className="text-blue-600">Drag candidate cards to move them through the pipeline. Click on a card to view details and add notes.</p>
        </div>
      </div>

      <DragDropContext onDragEnd={handleDragEnd}>
        <div className="flex gap-3 sm:gap-4 overflow-x-auto pb-4 -mx-4 px-4 sm:mx-0 sm:px-0">
          {STAGES.map((stage) => (
            <div key={stage.id} className="flex-shrink-0 w-[260px] sm:w-72">
              <div className={`rounded-t-lg px-4 py-3 ${stage.color} border-t-4`}>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-slate-700">{stage.label}</h3>
                    <p className="text-xs text-slate-500">{stage.desc}</p>
                  </div>
                  <span className="text-sm text-slate-500 bg-white px-2 py-0.5 rounded-full">
                    {getApplicationsByStage(stage.id).length}
                  </span>
                </div>
              </div>
              <Droppable droppableId={stage.id}>
                {(provided, snapshot) => (
                  <div
                    ref={provided.innerRef}
                    {...provided.droppableProps}
                    className={`min-h-[400px] bg-slate-50 rounded-b-lg p-3 space-y-3 transition-colors ${
                      snapshot.isDraggingOver ? 'bg-slate-100' : ''
                    }`}
                  >
                    {getApplicationsByStage(stage.id).map((app, index) => (
                      <Draggable key={app.id} draggableId={app.id} index={index}>
                        {(provided, snapshot) => (
                          <div
                            ref={provided.innerRef}
                            {...provided.draggableProps}
                            {...provided.dragHandleProps}
                            className={`bg-white border border-slate-200 rounded-lg p-4 cursor-grab hover:shadow-md transition-shadow ${
                              snapshot.isDragging ? 'shadow-lg rotate-2' : ''
                            }`}
                            onClick={() => setSelectedApp(app)}
                            data-testid={`pipeline-card-${app.id}`}
                          >
                            <div className="flex items-start gap-3">
                              <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                                <span className="text-[#7CB342] font-semibold text-sm">
                                  {app.candidate_name?.charAt(0).toUpperCase()}
                                </span>
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="font-medium text-slate-900 truncate">{app.candidate_name}</p>
                                <p className="text-xs text-slate-500 truncate">{app.job_title}</p>
                                <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-slate-500">
                                  {app.experience_years != null && app.experience_years > 0 && (
                                    <span>{Number(app.experience_years).toFixed(2)}y</span>
                                  )}
                                  {app.current_salary > 0 && (
                                    <span>₹{new Intl.NumberFormat('en-IN').format(app.current_salary)}</span>
                                  )}
                                  {app.notice_period && <span className="text-amber-600">NP: {app.notice_period}</span>}
                                  {app.location && <span>· {app.location}</span>}
                                </div>
                              </div>
                            </div>
                            {app.notes?.length > 0 && (
                              <div className="mt-2 flex items-center gap-1 text-xs text-slate-400">
                                <MessageSquare className="w-3 h-3" />
                                {app.notes.length} notes
                              </div>
                            )}
                            {/* Quick-move chips */}
                            <div className="mt-2 pt-2 border-t border-slate-100 flex flex-wrap gap-1" onClick={(e) => e.stopPropagation()}>
                              {[...STAGES, ...BOTTOM_STAGES]
                                .filter((s) => s.id !== stage.id)
                                .map((s) => (
                                  <button
                                    key={s.id}
                                    onClick={(e) => handleQuickMove(app.id, s.id, e)}
                                    className="px-1.5 py-0.5 text-[10px] rounded border border-slate-200 text-slate-600 hover:bg-slate-100 hover:border-slate-300 transition-colors"
                                    data-testid={`quick-move-${app.id}-${s.id}`}
                                    title={`Move to ${s.label}`}
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
                  </div>
                )}
              </Droppable>
            </div>
          ))}
        </div>

        {/* Bottom row — Rejected / On Hold */}
        <div className="mt-6">
          <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2 px-1">Secondary</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
            {BOTTOM_STAGES.map((stage) => (
              <div key={stage.id}>
                <div className={`rounded-t-lg px-4 py-3 ${stage.color} border-t-4`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-slate-700">{stage.label}</h3>
                      <p className="text-xs text-slate-500">{stage.desc}</p>
                    </div>
                    <span className="text-sm text-slate-500 bg-white px-2 py-0.5 rounded-full">
                      {getApplicationsByStage(stage.id).length}
                    </span>
                  </div>
                </div>
                <Droppable droppableId={stage.id}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      className={`min-h-[120px] bg-slate-50 rounded-b-lg p-3 space-y-2 transition-colors ${
                        snapshot.isDraggingOver ? 'bg-slate-100' : ''
                      }`}
                    >
                      {getApplicationsByStage(stage.id).map((app, index) => (
                        <Draggable key={app.id} draggableId={app.id} index={index}>
                          {(provided, snapshot) => (
                            <div
                              ref={provided.innerRef}
                              {...provided.draggableProps}
                              {...provided.dragHandleProps}
                              className={`bg-white border border-slate-200 rounded-lg p-3 cursor-grab hover:shadow-md transition-shadow ${
                                snapshot.isDragging ? 'shadow-lg rotate-2' : ''
                              }`}
                              onClick={() => setSelectedApp(app)}
                              data-testid={`pipeline-card-${app.id}`}
                            >
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center shrink-0">
                                  <span className="text-slate-600 font-semibold text-xs">
                                    {app.candidate_name?.charAt(0).toUpperCase()}
                                  </span>
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="font-medium text-sm text-slate-900 truncate">{app.candidate_name}</p>
                                  <p className="text-xs text-slate-500 truncate">{app.job_title}</p>
                                </div>
                              </div>
                              {/* Quick-move chips */}
                              <div className="mt-2 pt-2 border-t border-slate-100 flex flex-wrap gap-1" onClick={(e) => e.stopPropagation()}>
                                {[...STAGES, ...BOTTOM_STAGES]
                                  .filter((s) => s.id !== stage.id)
                                  .map((s) => (
                                    <button
                                      key={s.id}
                                      onClick={(e) => handleQuickMove(app.id, s.id, e)}
                                      className="px-1.5 py-0.5 text-[10px] rounded border border-slate-200 text-slate-600 hover:bg-slate-100 hover:border-slate-300 transition-colors"
                                      data-testid={`quick-move-${app.id}-${s.id}`}
                                      title={`Move to ${s.label}`}
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
                    </div>
                  )}
                </Droppable>
              </div>
            ))}
          </div>
        </div>
      </DragDropContext>

      {/* Candidate Detail Dialog */}
      <Dialog open={!!selectedApp} onOpenChange={() => setSelectedApp(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">Candidate Details</DialogTitle>
          </DialogHeader>
          {selectedApp && (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-full bg-[#DCFCE7] flex items-center justify-center flex-shrink-0">
                  <span className="text-[#7CB342] font-bold text-xl">
                    {selectedApp.candidate_name?.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <h3 className="font-semibold text-lg">{selectedApp.candidate_name}</h3>
                  <p className="text-sm text-slate-500">{selectedApp.job_title}</p>
                </div>
              </div>
              
              {/* All Mandatory Fields Grid */}
              <div className="grid grid-cols-2 gap-3 bg-slate-50 p-3 rounded-lg text-sm">
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Mail className="w-3 h-3" /> Email
                  </p>
                  <p className="font-medium truncate">{selectedApp.candidate_email || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <User className="w-3 h-3" /> Phone
                  </p>
                  <p className="font-medium">{selectedApp.candidate_phone || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <ClipboardList className="w-3 h-3" /> Experience
                  </p>
                  <p className="font-medium">{selectedApp.experience_years || 0} years</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <FileText className="w-3 h-3" /> CTC
                  </p>
                  <p className="font-medium">{selectedApp.current_salary ? `₹${(selectedApp.current_salary / 100000).toFixed(1)}L` : '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <User className="w-3 h-3" /> Location
                  </p>
                  <p className="font-medium">{selectedApp.location || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <ClipboardList className="w-3 h-3" /> Notice
                  </p>
                  <p className="font-medium">{selectedApp.notice_period || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <User className="w-3 h-3" /> Employer
                  </p>
                  <p className="font-medium truncate">{selectedApp.current_employer || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <User className="w-3 h-3" /> Designation
                  </p>
                  <p className="font-medium truncate">{selectedApp.designation || selectedApp.headline || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <User className="w-3 h-3" /> Industry
                  </p>
                  <p className="font-medium">{selectedApp.industry || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <FileText className="w-3 h-3" /> Education
                  </p>
                  <p className="font-medium truncate">{selectedApp.ug_course || selectedApp.education?.[0]?.degree || '-'}</p>
                </div>
              </div>

              {/* View Full Profile Button */}
              {selectedApp.candidate_id && (
                <Button
                  variant="outline"
                  className="w-full text-orange-600 border-orange-300 hover:bg-orange-50"
                  onClick={() => {
                    setSelectedApp(null);
                    navigate(`../naukri-profile/${selectedApp.candidate_id}`);
                  }}
                  data-testid="view-full-profile-pipeline"
                >
                  <FileText className="w-4 h-4 mr-2" /> View Full Profile
                </Button>
              )}

              <div className="text-sm">
                <p className="flex items-center gap-2 text-slate-600">
                  <ClipboardList className="w-4 h-4" /> Stage: <span className="capitalize font-medium">{selectedApp.stage}</span>
                </p>
              </div>

              {/* Notes Section */}
              <div className="border-t pt-4">
                <h4 className="font-medium mb-2">Notes</h4>
                <div className="space-y-2 max-h-40 overflow-y-auto mb-3">
                  {selectedApp.notes?.map((note) => (
                    <div key={note.id} className="bg-slate-50 p-3 rounded text-sm">
                      <p className="text-slate-700">{note.content}</p>
                      <p className="text-xs text-slate-400 mt-1">
                        {note.author_name} • {new Date(note.created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}
                      </p>
                    </div>
                  ))}
                  {(!selectedApp.notes || selectedApp.notes.length === 0) && (
                    <p className="text-slate-400 text-sm">No notes yet</p>
                  )}
                </div>
                <div className="flex gap-2">
                  <Textarea
                    placeholder="Add a note..."
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value)}
                    rows={2}
                    data-testid="add-note-input"
                  />
                </div>
                <Button
                  onClick={handleAddNote}
                  className="mt-2 bg-[#7CB342] hover:bg-[#689F38]"
                  size="sm"
                  data-testid="add-note-btn"
                >
                  <Plus className="w-4 h-4 mr-1" /> Add Note
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
