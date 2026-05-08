import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../../ui/dialog';
import { Button } from '../../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { Label } from '../../ui/label';
import { AlertTriangle, Briefcase, User } from 'lucide-react';
import { formatSalaryINR } from '../../../lib/currency';

export function DuplicateWarningDialog({ duplicateDialog, onClose, onAction }) {
  return (
    <Dialog open={!!duplicateDialog} onOpenChange={() => onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" /> Duplicate Candidate Detected
          </DialogTitle>
          <DialogDescription>A candidate with matching information already exists in the database.</DialogDescription>
        </DialogHeader>
        {duplicateDialog?.existingCandidate && (
          <div className="bg-slate-50 rounded-lg p-4 space-y-2">
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-slate-500" />
              <span className="font-medium">{duplicateDialog.existingCandidate.name}</span>
            </div>
            <div className="text-sm text-slate-600">
              <p>Added: {new Date(duplicateDialog.existingCandidate.created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}</p>
              {duplicateDialog.existingCandidate.current_salary && <p>Salary: {formatSalaryINR(duplicateDialog.existingCandidate.current_salary)}</p>}
              {duplicateDialog.existingCandidate.notice_period && <p>Notice: {duplicateDialog.existingCandidate.notice_period}</p>}
            </div>
          </div>
        )}
        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="outline" onClick={() => onAction('link')} className="text-purple-600 border-purple-200 hover:bg-purple-50">
            <Briefcase className="w-4 h-4 mr-2" /> Apply Existing to Job
          </Button>
          <Button onClick={() => onAction('update')} className="bg-amber-500 hover:bg-amber-600">Update Existing</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function LinkToJobDialog({ linkDialog, onClose, jobs, selectedJob, setSelectedJob, onLink }) {
  return (
    <Dialog open={!!linkDialog} onOpenChange={() => onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading">Add as Applicant</DialogTitle>
          <DialogDescription>Select a job to add {linkDialog?.candidate?.name} as an applicant</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Select Job / Mandate</Label>
            <Select value={selectedJob} onValueChange={setSelectedJob}>
              <SelectTrigger data-testid="select-job-dropdown"><SelectValue placeholder="Choose a job..." /></SelectTrigger>
              <SelectContent>
                {jobs.map(job => <SelectItem key={job.id} value={job.id}>{job.title} - {job.company_name || 'Company'}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {linkDialog?.candidate && (
            <div className="bg-slate-50 rounded-lg p-3 text-sm">
              <p><strong>Candidate:</strong> {linkDialog.candidate.name}</p>
              {linkDialog.candidate.current_salary && <p><strong>Salary:</strong> {formatSalaryINR(linkDialog.candidate.current_salary)}</p>}
              {linkDialog.candidate.notice_period && <p><strong>Notice:</strong> {linkDialog.candidate.notice_period}</p>}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={onLink} disabled={!selectedJob} className="bg-[#7CB342] hover:bg-[#689F38]">Add as Applicant</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
