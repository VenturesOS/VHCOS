/**
 * Reusable Candidate Profile Dialog Component
 * Shows complete candidate profile with all mandatory fields and edit capability
 * Used across: Candidate Bank, AI Screening, Pipeline, and anywhere candidate profile is shown
 */
import { useState, useEffect } from 'react';
import { candidateBankAPI, extensionAPI } from '../../lib/api';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { toast } from 'sonner';
import { Download, Edit2, Save, X, FileText, RefreshCw, Sparkles } from 'lucide-react';

import CandidateActivityTimeline from './CandidateActivityTimeline';
import ProfileTab from './profile-tabs/ProfileTab';
import ExperienceTab from './profile-tabs/ExperienceTab';
import EducationTab from './profile-tabs/EducationTab';
import ActivityTab from './profile-tabs/ActivityTab';
import AuditLogTab from './profile-tabs/AuditLogTab';
import SimilarCandidatesModal from './SimilarCandidatesModal';

const INITIAL_FORM = {
  name: '', email: '', phone: '', location: '', experience_years: '',
  current_salary: '', notice_period: '', current_employer: '', designation: '',
  industry: '', ug_course: '', date_of_birth: '', headline: '', summary: '',
};

function buildEditForm(c) {
  return {
    name: c.name || '', email: c.email || '', phone: c.phone || '',
    location: c.location || '', experience_years: c.experience_years?.toString() || '0',
    current_salary: c.current_salary?.toString() || '', notice_period: c.notice_period || '',
    current_employer: c.current_employer || '', designation: c.designation || c.headline || '',
    industry: c.industry || '', ug_course: c.ug_course || '',
    date_of_birth: c.date_of_birth || '', headline: c.headline || '', summary: c.summary || '',
  };
}

export default function CandidateProfileDialog({
  candidate, isOpen, onClose, onUpdate,
  showDownloadResume = true, showEditButton = true,
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reEnriching, setReEnriching] = useState(false);
  const [auditLog, setAuditLog] = useState([]);
  const [activityHistory, setActivityHistory] = useState(null);
  const [editForm, setEditForm] = useState(INITIAL_FORM);
  const [similarOpen, setSimilarOpen] = useState(false);

  const loadCandidateDetails = async (cand) => {
    if (!cand?.id) return;
    try {
      const [fullRes, auditRes, activityRes] = await Promise.all([
        candidateBankAPI.getById(cand.id),
        candidateBankAPI.getAuditLog(cand.id),
        candidateBankAPI.getHistory(cand.id),
      ]);
      if (fullRes.data) Object.assign(cand, fullRes.data);
      setAuditLog(auditRes.data || []);
      setActivityHistory(activityRes.data || null);
    } catch (error) {
    }
  };

  useEffect(() => {
    if (candidate && isOpen) {
      loadCandidateDetails(candidate);
      setEditForm(buildEditForm(candidate));
    }
  }, [candidate, isOpen]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await candidateBankAPI.updateSalaryNotice(
        candidate.id,
        editForm.current_salary ? parseInt(editForm.current_salary) : null,
        editForm.notice_period, editForm.location,
        editForm.experience_years ? parseInt(editForm.experience_years) : 0,
      );
      await candidateBankAPI.update(candidate.id, {
        name: editForm.name, phone: editForm.phone,
        headline: editForm.designation || editForm.headline, summary: editForm.summary,
        current_employer: editForm.current_employer, designation: editForm.designation,
        industry: editForm.industry, ug_course: editForm.ug_course, date_of_birth: editForm.date_of_birth,
      });
      toast.success('Profile updated successfully');
      setIsEditing(false);
      if (onUpdate) onUpdate();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update profile');
    } finally { setSaving(false); }
  };

  const handleCancel = () => { setIsEditing(false); setEditForm(buildEditForm(candidate)); };

  const downloadResume = () => {
    if (!candidate?.resume_url && !candidate?.active_resume_id) return toast.error('No resume available');
    const token = localStorage.getItem('vhc_token');
    const link = document.createElement('a');
    link.href = `${candidateBankAPI.getResumeDownloadUrl(candidate.id)}?token=${token}`;
    link.target = '_blank';
    document.body.appendChild(link); link.click(); document.body.removeChild(link);
  };

  const handleReEnrich = async () => {
    if (!candidate?.id) return;
    setReEnriching(true);
    try {
      const res = await extensionAPI.reEnrich(candidate.id);
      toast.success(`Re-enriched: ${res.data?.fields_updated?.length || 0} fields updated`);
      if (onUpdate) onUpdate();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Re-enrichment failed');
    } finally { setReEnriching(false); }
  };

  const downloadAtsCv = () => {
    const token = localStorage.getItem('vhc_token');
    const link = document.createElement('a');
    link.href = `${candidateBankAPI.getAtsCvUrl(candidate.id)}?token=${token}`;
    link.target = '_blank';
    document.body.appendChild(link); link.click(); document.body.removeChild(link);
  };

  if (!candidate) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="font-heading text-xl">Candidate Profile</DialogTitle>
            <div className="flex items-center gap-2">
              {showDownloadResume && (candidate.resume_url || candidate.active_resume_id) && (
                <Button variant="outline" size="sm" onClick={downloadResume} className="text-[#7CB342] border-[#7CB342] hover:bg-green-50" data-testid="download-resume-btn">
                  <Download className="w-4 h-4 mr-1" /> Download CV
                </Button>
              )}
              {showDownloadResume && (
                <Button variant="outline" size="sm" onClick={downloadAtsCv} className="text-blue-600 border-blue-400 hover:bg-blue-50" data-testid="generate-ats-cv-btn">
                  <FileText className="w-4 h-4 mr-1" /> Resume (.tex)
                </Button>
              )}
              {showEditButton && !isEditing && (
                <>
                  <Button variant="outline" size="sm" onClick={() => setSimilarOpen(true)} className="text-purple-700 border-purple-300 hover:bg-purple-50" data-testid="find-similar-btn" title="Find candidates similar to this profile">
                    <Sparkles className="w-4 h-4 mr-1" /> Find similar
                  </Button>
                  <Button variant="outline" size="sm" onClick={handleReEnrich} disabled={reEnriching} data-testid="re-enrich-btn" title="Re-run AI extraction">
                    <RefreshCw className={`w-4 h-4 mr-1 ${reEnriching ? 'animate-spin' : ''}`} /> {reEnriching ? 'Enriching...' : 'AI Re-enrich'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setIsEditing(true)} data-testid="edit-profile-btn">
                    <Edit2 className="w-4 h-4 mr-1" /> Edit
                  </Button>
                </>
              )}
              {isEditing && (
                <>
                  <Button variant="outline" size="sm" onClick={handleCancel}><X className="w-4 h-4 mr-1" /> Cancel</Button>
                  <Button size="sm" onClick={handleSave} disabled={saving} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="save-profile-btn">
                    <Save className="w-4 h-4 mr-1" /> {saving ? 'Saving...' : 'Save'}
                  </Button>
                </>
              )}
            </div>
          </div>
        </DialogHeader>

        <Tabs defaultValue="profile" className="w-full mt-4">
          <TabsList className="mb-4 flex-wrap h-auto gap-1">
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="experience">Experience</TabsTrigger>
            <TabsTrigger value="education">Education</TabsTrigger>
            <TabsTrigger value="activity">Activity</TabsTrigger>
            <TabsTrigger value="timeline" data-testid="tab-timeline">Timeline</TabsTrigger>
            <TabsTrigger value="audit">Audit Log</TabsTrigger>
          </TabsList>

          <TabsContent value="profile">
            <ProfileTab candidate={candidate} isEditing={isEditing} editForm={editForm} setEditForm={setEditForm} />
          </TabsContent>
          <TabsContent value="experience">
            <ExperienceTab candidate={candidate} />
          </TabsContent>
          <TabsContent value="education">
            <EducationTab candidate={candidate} />
          </TabsContent>
          <TabsContent value="activity">
            <ActivityTab activityHistory={activityHistory} />
          </TabsContent>
          <TabsContent value="timeline">
            <div className="bg-zinc-950 rounded-lg p-4 -mx-2 border border-zinc-800/50">
              <CandidateActivityTimeline candidateId={candidate.id} />
            </div>
          </TabsContent>
          <TabsContent value="audit">
            <AuditLogTab auditLog={auditLog} />
          </TabsContent>
        </Tabs>
      </DialogContent>
      <SimilarCandidatesModal
        open={similarOpen}
        onOpenChange={setSimilarOpen}
        seedId={candidate?.id}
        seedName={candidate?.name}
      />
    </Dialog>
  );
}
