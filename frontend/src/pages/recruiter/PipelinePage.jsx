import { useState, useEffect } from 'react';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';
import { applicationAPI, jobAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { ClipboardList, User, Mail, FileText, Plus, MessageSquare } from 'lucide-react';

const STAGES = [
  { id: 'applied', label: 'New CVs', color: 'border-blue-400 bg-blue-50', desc: 'Awaiting screening' },
  { id: 'shortlisted', label: 'Shortlisted', color: 'border-amber-400 bg-amber-50', desc: 'Ready for interview' },
  { id: 'interview', label: 'Interview', color: 'border-purple-400 bg-purple-50', desc: 'In process' },
  { id: 'offered', label: 'Offered', color: 'border-green-400 bg-green-50', desc: 'Offer extended' },
  { id: 'hired', label: 'Hired', color: 'border-emerald-400 bg-emerald-50', desc: 'Joined' },
];

export default function PipelinePage() {
  const [applications, setApplications] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState('all');
  const [loading, setLoading] = useState(true);
  const [selectedApp, setSelectedApp] = useState(null);
  const [noteText, setNoteText] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    loadApplications();
  }, [selectedJob]);

  const loadData = async () => {
    try {
      const jobsRes = await jobAPI.getAll();
      setJobs(jobsRes.data);
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
      toast.error('Failed to load applications');
    } finally {
      setLoading(false);
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
          <h1 className="font-heading text-3xl font-bold text-slate-900">Candidate Pipeline</h1>
          <p className="text-slate-500 mt-1">Drag candidates between stages to update status</p>
        </div>
        <Select value={selectedJob} onValueChange={setSelectedJob}>
          <SelectTrigger className="w-64" data-testid="job-filter-select">
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

      {/* Help Tip */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-700 flex items-start gap-3">
        <ClipboardList className="w-5 h-5 shrink-0 mt-0.5" />
        <div>
          <p className="font-medium">Workflow Tip</p>
          <p className="text-blue-600">Drag candidate cards to move them through the pipeline. Click on a card to view details and add notes.</p>
        </div>
      </div>

      <DragDropContext onDragEnd={handleDragEnd}>
        <div className="flex gap-4 overflow-x-auto pb-4">
          {STAGES.map((stage) => (
            <div key={stage.id} className="flex-shrink-0 w-72">
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
                              </div>
                            </div>
                            {app.notes?.length > 0 && (
                              <div className="mt-2 flex items-center gap-1 text-xs text-slate-400">
                                <MessageSquare className="w-3 h-3" />
                                {app.notes.length} notes
                              </div>
                            )}
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
      </DragDropContext>

      {/* Candidate Detail Dialog */}
      <Dialog open={!!selectedApp} onOpenChange={() => setSelectedApp(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading">Candidate Details</DialogTitle>
          </DialogHeader>
          {selectedApp && (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                  <span className="text-[#7CB342] font-bold text-xl">
                    {selectedApp.candidate_name?.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <h3 className="font-semibold text-lg">{selectedApp.candidate_name}</h3>
                  <p className="text-sm text-slate-500">{selectedApp.job_title}</p>
                </div>
              </div>
              <div className="space-y-2 text-sm">
                <p className="flex items-center gap-2 text-slate-600">
                  <Mail className="w-4 h-4" /> {selectedApp.candidate_email}
                </p>
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
                        {note.author_name} • {new Date(note.created_at).toLocaleDateString()}
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
