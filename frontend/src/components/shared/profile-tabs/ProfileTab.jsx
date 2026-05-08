import { Badge } from '../../ui/badge';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { Textarea } from '../../ui/textarea';
import { formatSalaryINR } from '../../../lib/currency';
import {
  Phone, Mail, Briefcase, DollarSign, Building2, MapPin,
  Clock, Calendar, Sparkles, ShieldAlert, GraduationCap,
} from 'lucide-react';

const NOTICE_PERIODS = ["Immediate", "15 days", "30 days", "45 days", "60 days", "90 days", "90+ days"];

function EditableField({ icon: Icon, label, value, editValue, onChange, isEditing, placeholder, type = 'text', badge }) {
  return (
    <div className="space-y-1">
      <Label className="flex items-center gap-2 text-slate-600">
        <Icon className="w-4 h-4" /> {label} {badge}
      </Label>
      {isEditing ? (
        <Input type={type} value={editValue} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
      ) : (
        <p className="font-medium">{value || <span className="text-amber-600">Unknown</span>}</p>
      )}
    </div>
  );
}

export default function ProfileTab({ candidate, isEditing, editForm, setEditForm }) {
  return (
    <div className="space-y-6">
      {candidate.source === 'bulk_import' && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="flex items-start gap-2">
            <ShieldAlert className="w-5 h-5 text-amber-600 mt-0.5" />
            <div className="flex-1">
              <p className="font-medium text-amber-800 text-sm">Bulk Import Candidate</p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <Badge variant="outline" className="border-amber-300">Type: {candidate.bulk_import_type || 'N/A'}</Badge>
                <Badge variant="outline" className={candidate.cv_attached ? 'border-green-300 text-green-700' : 'border-red-300 text-red-700'}>
                  CV: {candidate.cv_attached ? 'Attached' : 'Not attached'}
                </Badge>
                {candidate.bulk_import_restricted && <Badge variant="outline" className="border-amber-500 text-amber-700">Admin Only</Badge>}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-4">
        <div className="w-20 h-20 rounded-full bg-[#DCFCE7] flex items-center justify-center">
          <span className="text-[#7CB342] font-bold text-3xl">
            {(isEditing ? editForm.name : candidate.name)?.charAt(0).toUpperCase() || '?'}
          </span>
        </div>
        <div className="flex-1">
          {isEditing ? (
            <>
              <Input value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })} className="text-xl font-semibold mb-1" placeholder="Full Name" />
              <Input value={editForm.designation} onChange={e => setEditForm({ ...editForm, designation: e.target.value })} className="text-sm" placeholder="Designation/Headline" />
            </>
          ) : (
            <>
              <h2 className="text-xl font-semibold text-slate-900">{candidate.name || 'Unknown'}</h2>
              <p className="text-slate-500">{candidate.designation || candidate.headline || '-'}</p>
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <EditableField icon={Phone} label="Contact No. *" value={candidate.phone} editValue={editForm.phone} onChange={v => setEditForm({ ...editForm, phone: v })} isEditing={isEditing} placeholder="Phone number" />
        <div className="space-y-1">
          <Label className="flex items-center gap-2 text-slate-600"><Mail className="w-4 h-4" /> Email *</Label>
          <p className="font-medium">{candidate.email || <span className="text-amber-600">Unknown</span>}</p>
        </div>
        <EditableField icon={Briefcase} label="Work Experience *" value={`${candidate.experience_years || 0} years`} editValue={editForm.experience_years} onChange={v => setEditForm({ ...editForm, experience_years: v })} isEditing={isEditing} placeholder="Years" type="number" />
        <div className="space-y-1">
          <Label className="flex items-center gap-2 text-slate-600"><DollarSign className="w-4 h-4" /> Current CTC *</Label>
          {isEditing ? (
            <div>
              <Input type="number" value={editForm.current_salary} onChange={e => setEditForm({ ...editForm, current_salary: e.target.value })} placeholder="Annual salary in INR" />
              {editForm.current_salary && <p className="text-xs text-slate-500 mt-1">{formatSalaryINR(parseInt(editForm.current_salary))}</p>}
            </div>
          ) : (
            <p className="font-medium">{candidate.current_salary ? formatSalaryINR(candidate.current_salary) : <span className="text-amber-600">Unknown</span>}</p>
          )}
        </div>
        <EditableField icon={MapPin} label="Current Location *" value={candidate.location} editValue={editForm.location} onChange={v => setEditForm({ ...editForm, location: v })} isEditing={isEditing} placeholder="City, State" />
        <div className="space-y-1">
          <Label className="flex items-center gap-2 text-slate-600"><Clock className="w-4 h-4" /> Notice Period *</Label>
          {isEditing ? (
            <Select value={editForm.notice_period} onValueChange={v => setEditForm({ ...editForm, notice_period: v })}>
              <SelectTrigger><SelectValue placeholder="Select notice period" /></SelectTrigger>
              <SelectContent>{NOTICE_PERIODS.map(np => <SelectItem key={np} value={np}>{np}</SelectItem>)}</SelectContent>
            </Select>
          ) : (
            <p className="font-medium">{candidate.notice_period || <span className="text-amber-600">Unknown</span>}</p>
          )}
        </div>
        <EditableField icon={Building2} label="Current Employer *" value={candidate.current_employer} editValue={editForm.current_employer} onChange={v => setEditForm({ ...editForm, current_employer: v })} isEditing={isEditing} placeholder="Company name" />
        <EditableField icon={Briefcase} label="Current Designation *" value={candidate.designation || candidate.headline} editValue={editForm.designation} onChange={v => setEditForm({ ...editForm, designation: v })} isEditing={isEditing} placeholder="Job title" />
        <EditableField icon={Building2} label="Industry" value={candidate.industry} editValue={editForm.industry} onChange={v => setEditForm({ ...editForm, industry: v })} isEditing={isEditing} placeholder="Industry/Sector"
          badge={candidate.industry_source === 'ai_detected' ? <Badge variant="secondary" className="bg-green-100 text-green-700 text-xs ml-1"><Sparkles className="w-3 h-3 mr-1" /> AI Detected</Badge> : null} />
        <EditableField icon={Calendar} label="Date of Birth / Age" value={candidate.date_of_birth} editValue={editForm.date_of_birth} onChange={v => setEditForm({ ...editForm, date_of_birth: v })} isEditing={isEditing} placeholder="DOB or Age" />
      </div>

      {candidate.skills?.length > 0 && (
        <div className="space-y-2">
          <Label className="text-slate-600">Skills</Label>
          <div className="flex flex-wrap gap-1">
            {candidate.skills.map((skill, i) => <Badge key={`skill-${skill}-${i}`} variant="secondary" className="bg-[#DCFCE7] text-[#7CB342]">{skill}</Badge>)}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <Label className="text-slate-600">Summary</Label>
        {isEditing ? (
          <Textarea value={editForm.summary} onChange={e => setEditForm({ ...editForm, summary: e.target.value })} placeholder="Professional summary..." rows={3} />
        ) : (
          <p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">{candidate.summary || 'No summary available'}</p>
        )}
      </div>
    </div>
  );
}
