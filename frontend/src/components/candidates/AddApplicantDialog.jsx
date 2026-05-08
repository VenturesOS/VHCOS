import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Briefcase, DollarSign, Clock, Phone, MapPin, AlertCircle } from 'lucide-react';
import { NOTICE_PERIODS } from '../candidate-bank/CandidateBankFilters';
import { formatSalaryINR } from '../../lib/currency';

export function AddApplicantDialog({
  open, onOpenChange, candidate,
  jobs, selectedJobId, setSelectedJobId,
  editSalary, setEditSalary,
  editNotice, setEditNotice,
  editLocation, setEditLocation,
  editExperience, setEditExperience,
  linking, onConfirm,
}) {
  const allFilled = editSalary && editNotice && editLocation && editExperience !== '' && selectedJobId;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] p-0 flex flex-col gap-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-2 shrink-0">
          <DialogTitle className="font-heading flex items-center gap-2">
            <Briefcase className="w-5 h-5 text-[#7CB342]" /> Add as Applicant
          </DialogTitle>
          <DialogDescription>Add this candidate to a job pipeline. All mandatory fields must be filled.</DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-2 min-h-0">
        {candidate && (
          <div className="space-y-4 py-2">
            <div className="bg-slate-50 rounded-lg p-4">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center flex-shrink-0">
                  <span className="text-[#7CB342] font-semibold text-lg">{candidate.name?.charAt(0).toUpperCase()}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-slate-900 truncate">{candidate.name}</p>
                  <p className="text-sm text-slate-500 truncate">{candidate.email}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex items-center gap-1 text-slate-600">
                  <Phone className="w-3 h-3" /> <span className="truncate">{candidate.phone || 'No phone'}</span>
                </div>
                <div className="flex items-center gap-1 text-slate-600">
                  <MapPin className="w-3 h-3" /> <span className="truncate">{candidate.location || 'No location'}</span>
                </div>
                <div className="flex items-center gap-1 text-slate-600">
                  <Briefcase className="w-3 h-3" /> <span className="truncate">{candidate.experience_years || 0} yrs exp</span>
                </div>
                <div className="flex items-center gap-1 text-slate-600">
                  <DollarSign className="w-3 h-3" />
                  <span className="truncate">{candidate.current_salary ? formatSalaryINR(candidate.current_salary) : 'No salary'}</span>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <Label className="flex items-center gap-1 text-sm font-medium">
                <Briefcase className="w-4 h-4" /> Select Job / Mandate *
              </Label>
              <Select value={selectedJobId} onValueChange={setSelectedJobId}>
                <SelectTrigger data-testid="job-select-dropdown">
                  <SelectValue placeholder="Choose a job..." />
                </SelectTrigger>
                <SelectContent>
                  {jobs.length > 0 ? jobs.map(job => (
                    <SelectItem key={job.id} value={job.id}>
                      {job.title} {job.company_name ? `- ${job.company_name}` : ''}
                    </SelectItem>
                  )) : (
                    <div className="px-2 py-1.5 text-sm text-slate-500">No active jobs available</div>
                  )}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="flex items-center gap-1 text-sm font-medium">
                  <DollarSign className="w-4 h-4" /> Current Salary (INR) *
                </Label>
                <Input
                  type="number" value={editSalary} onChange={(e) => setEditSalary(e.target.value)}
                  placeholder="e.g., 1500000" className={!editSalary ? 'border-amber-400' : ''}
                  data-testid="salary-input"
                />
                {editSalary && parseInt(editSalary) > 0 && (
                  <p className="text-xs text-slate-500">{formatSalaryINR(parseInt(editSalary))}</p>
                )}
              </div>

              <div className="space-y-1">
                <Label className="flex items-center gap-1 text-sm font-medium">
                  <Clock className="w-4 h-4" /> Notice Period *
                </Label>
                <Select value={editNotice} onValueChange={setEditNotice}>
                  <SelectTrigger className={!editNotice ? 'border-amber-400' : ''} data-testid="notice-select">
                    <SelectValue placeholder="Select..." />
                  </SelectTrigger>
                  <SelectContent>
                    {NOTICE_PERIODS.map(np => <SelectItem key={np} value={np}>{np}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <Label className="flex items-center gap-1 text-sm font-medium">
                  <MapPin className="w-4 h-4" /> Location *
                </Label>
                <Input
                  type="text" value={editLocation} onChange={(e) => setEditLocation(e.target.value)}
                  placeholder="e.g., Mumbai" className={!editLocation ? 'border-amber-400' : ''}
                  data-testid="location-input"
                />
              </div>

              <div className="space-y-1">
                <Label className="flex items-center gap-1 text-sm font-medium">
                  <Briefcase className="w-4 h-4" /> Experience (years) *
                </Label>
                <Input
                  type="number" min="0" value={editExperience} onChange={(e) => setEditExperience(e.target.value)}
                  placeholder="e.g., 5" className={editExperience === '' ? 'border-amber-400' : ''}
                  data-testid="experience-input"
                />
              </div>
            </div>

            {!allFilled && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-2 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-amber-700">All mandatory fields must be filled before adding as applicant.</p>
              </div>
            )}
          </div>
        )}
        </div>

        <DialogFooter className="px-6 py-4 border-t border-slate-100 bg-white shrink-0">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            onClick={onConfirm}
            disabled={linking || !allFilled}
            className="bg-[#7CB342] hover:bg-[#689F38]"
            data-testid="confirm-add-applicant-btn"
          >
            {linking ? 'Adding...' : 'Add as Applicant'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
