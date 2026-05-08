import { useState } from 'react';
import { Badge } from '../../ui/badge';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { FileText, Trash2, AlertTriangle, Check, X, Plus, DollarSign, Clock } from 'lucide-react';

const NOTICE_PERIODS = ['Immediate', '15 Days', '30 Days', '45 Days', '60 Days', '90 Days', '90+ Days'];

export default function CandidateCard({ candidate, onUpdate, onAddSkill, onRemoveSkill, onRemove, onShowDuplicate }) {
  const [newSkill, setNewSkill] = useState('');

  if (!candidate.success) {
    return (
      <div className="border border-red-200 bg-red-50 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <X className="w-5 h-5 text-red-500" />
            <span className="font-medium text-red-700">{candidate.filename}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={onRemove}><Trash2 className="w-4 h-4" /></Button>
        </div>
        <p className="text-sm text-red-600 mt-1">{candidate.error}</p>
      </div>
    );
  }

  const isDuplicate = candidate.duplicate_check?.is_duplicate;

  return (
    <div className={`border rounded-lg p-4 ${isDuplicate ? 'border-amber-300 bg-amber-50' : candidate.isValid ? 'border-green-300 bg-green-50' : 'border-slate-200 bg-white'}`}
      data-testid={`candidate-card-${candidate.temp_id}`}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-slate-500" />
          <span className="text-sm text-slate-600">{candidate.filename}</span>
          {isDuplicate && <Badge variant="outline" className="text-amber-600 border-amber-300"><AlertTriangle className="w-3 h-3 mr-1" /> Duplicate</Badge>}
          {candidate.isValid && !isDuplicate && <Badge variant="outline" className="text-green-600 border-green-300"><Check className="w-3 h-3 mr-1" /> Ready</Badge>}
        </div>
        <div className="flex gap-2">
          {isDuplicate && <Button variant="outline" size="sm" onClick={onShowDuplicate}><AlertTriangle className="w-4 h-4 mr-1" /> Resolve</Button>}
          <Button variant="ghost" size="sm" onClick={onRemove}><Trash2 className="w-4 h-4" /></Button>
        </div>
      </div>

      {candidate.errors?.length > 0 && (
        <div className="mb-4 p-2 bg-red-100 border border-red-200 rounded text-sm text-red-700">
          {candidate.errors.map((err, ei) => <p key={`err-${ei}`}>{'\u2022'} {err}</p>)}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Name *</Label>
          <Input value={candidate.editing.name} onChange={e => onUpdate('name', e.target.value)} placeholder="Full name" data-testid={`name-input-${candidate.temp_id}`} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Email</Label>
          <Input value={candidate.editing.email} onChange={e => onUpdate('email', e.target.value)} placeholder="Email address" type="email" data-testid={`email-input-${candidate.temp_id}`} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Phone</Label>
          <Input value={candidate.editing.phone} onChange={e => onUpdate('phone', e.target.value)} placeholder="Phone number" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500 flex items-center gap-1"><DollarSign className="w-3 h-3" /> Current Salary (INR)</Label>
          <Input value={candidate.editing.current_salary} onChange={e => onUpdate('current_salary', e.target.value)} placeholder="e.g., 1500000" type="number" data-testid={`salary-input-${candidate.temp_id}`} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500 flex items-center gap-1"><Clock className="w-3 h-3" /> Notice Period</Label>
          <Select value={candidate.editing.notice_period} onValueChange={v => onUpdate('notice_period', v)}>
            <SelectTrigger data-testid={`notice-input-${candidate.temp_id}`}><SelectValue placeholder="Select..." /></SelectTrigger>
            <SelectContent>{NOTICE_PERIODS.map(np => <SelectItem key={np} value={np}>{np}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Location</Label>
          <Input value={candidate.editing.location} onChange={e => onUpdate('location', e.target.value)} placeholder="e.g., Mumbai, Delhi" data-testid={`location-input-${candidate.temp_id}`} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Experience (years)</Label>
          <Input value={candidate.editing.experience_years} onChange={e => onUpdate('experience_years', e.target.value)} placeholder="e.g., 5" type="number" min="0" data-testid={`exp-input-${candidate.temp_id}`} />
        </div>
        <div className="space-y-1 md:col-span-2">
          <Label className="text-xs text-slate-500">Skills</Label>
          <div className="flex flex-wrap gap-2 mb-2">
            {candidate.editing.skills.map((skill, si) => (
              <Badge key={`skill-${skill}-${si}`} variant="secondary" className="flex items-center gap-1">
                {skill}
                <button onClick={() => onRemoveSkill(skill)} className="ml-1 hover:text-red-500"><X className="w-3 h-3" /></button>
              </Badge>
            ))}
          </div>
          <div className="flex gap-2">
            <Input value={newSkill} onChange={e => setNewSkill(e.target.value)} placeholder="Add skill..."
              onKeyPress={e => { if (e.key === 'Enter') { e.preventDefault(); onAddSkill(newSkill); setNewSkill(''); } }} />
            <Button variant="outline" size="sm" onClick={() => { onAddSkill(newSkill); setNewSkill(''); }}><Plus className="w-4 h-4" /></Button>
          </div>
        </div>
        <div className="space-y-1 md:col-span-2">
          <Label className="text-xs text-slate-500">Experience Summary</Label>
          <Textarea value={candidate.editing.experience_summary} onChange={e => onUpdate('experience_summary', e.target.value)} placeholder="Brief summary of experience..." rows={2} />
        </div>
      </div>
    </div>
  );
}
