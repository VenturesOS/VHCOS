import { useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Paperclip, Building2, Sparkles } from 'lucide-react';

export function AttachCVDialog({ open, onOpenChange, candidate, onAttachCV, attaching }) {
  const fileInputRef = useRef(null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-heading flex items-center gap-2">
            <Paperclip className="w-5 h-5 text-amber-600" /> Attach CV
          </DialogTitle>
          <DialogDescription>Upload a CV for this bulk-imported candidate.</DialogDescription>
        </DialogHeader>

        {candidate && (
          <div className="space-y-4 py-4">
            <div className="bg-slate-50 rounded-lg p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                  <span className="text-[#7CB342] font-semibold">{candidate.name?.charAt(0).toUpperCase()}</span>
                </div>
                <div>
                  <p className="font-medium text-slate-900">{candidate.name}</p>
                  <p className="text-sm text-slate-500">{candidate.email}</p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline" className="text-xs">
                  <Building2 className="w-3 h-3 mr-1" /> {candidate.current_employer || 'Unknown employer'}
                </Badge>
                {candidate.industry && (
                  <Badge variant="outline" className="text-xs">
                    {candidate.industry_source === 'ai_detected' && <Sparkles className="w-3 h-3 mr-1 text-green-500" />}
                    {candidate.industry}
                  </Badge>
                )}
              </div>
            </div>

            <div className="border-2 border-dashed border-amber-200 rounded-lg p-6 text-center hover:border-amber-400 transition-colors">
              <input
                type="file"
                ref={fileInputRef}
                onChange={(e) => onAttachCV(e.target.files?.[0])}
                accept=".pdf,.doc,.docx"
                className="hidden"
                data-testid="attach-cv-file-input"
              />
              <Paperclip className="w-8 h-8 text-amber-400 mx-auto mb-2" />
              <p className="text-sm text-slate-600 mb-2">
                <span className="text-amber-600 font-medium">Click to upload</span> CV file
              </p>
              <p className="text-xs text-slate-400 mb-4">Supports PDF, DOC, DOCX</p>
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={attaching}
                className="border-amber-400 text-amber-600 hover:bg-amber-50"
              >
                {attaching ? 'Uploading...' : 'Choose File'}
              </Button>
            </div>

            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
              <p>Attaching a CV will:</p>
              <ul className="list-disc list-inside mt-1 text-xs">
                <li>Upload the file to secure storage</li>
                <li>Update <code className="bg-blue-100 px-1 rounded">cv_attached</code> status to true</li>
                <li>Enable the Download Resume button</li>
              </ul>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
