import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { AlertCircle } from 'lucide-react';

export function DeleteCandidateDialog({ open, onOpenChange, candidate, onConfirm }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="delete-candidate-dialog">
        <DialogHeader>
          <DialogTitle className="text-red-600 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" /> Delete Candidate
          </DialogTitle>
          <DialogDescription>
            This will permanently remove this candidate from the data bank. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm text-gray-600 font-medium">
          {candidate?.name} {candidate?.email ? `(${candidate.email})` : ''}
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="delete-candidate-cancel">Cancel</Button>
          <Button variant="destructive" onClick={onConfirm} data-testid="delete-candidate-confirm">Delete</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
