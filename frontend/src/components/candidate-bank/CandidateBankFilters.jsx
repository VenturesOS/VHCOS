import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import {
  Search, Filter, X, ChevronDown, ChevronUp,
  Phone, Mail, MapPin, Building2, Code, Clock,
  Briefcase, DollarSign, Database, FileText, EyeOff, Calendar, Target,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { jobAPI } from '../../lib/api';

export const NOTICE_PERIODS = [
  'Immediate', '15 days', '30 days', '45 days', '60 days', '90 days', '90+ days',
];

function FilterChip({ label, onRemove }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#DCFCE7] text-[#4A7C2C] text-xs font-medium">
      {label}
      <button onClick={onRemove} className="hover:text-red-600 ml-0.5"><X className="w-3 h-3" /></button>
    </span>
  );
}

/**
 * Reusable filter panel for Candidate Bank pages (Admin, Employer, Recruiter).
 * Accepts filter state from `useCandidateBankFilters` hook.
 */
export function CandidateBankFilters({
  search, setSearch,
  skills, setSkills,
  filters, updateFilter,
  filtersOpen, setFiltersOpen,
  activeFilterCount,
  clearFilters, setDatePreset,
  onSearch,
  isAdmin = false,
}) {
  const [mandates, setMandates] = useState([]);
  useEffect(() => {
    jobAPI.getAll().then(res => {
      const active = (res.data || []).filter(j => j.status === 'active');
      setMandates(active);
    }).catch(() => {});
  }, []);

  const mandateLabel = mandates.find(m => m.id === filters.mandateId)?.title || filters.mandateId || '';

  return (
    <div className="p-4 space-y-3" data-testid="candidate-bank-filters">
      {/* Primary search bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, email, phone, designation..."
            className="pl-10"
            onKeyDown={(e) => e.key === 'Enter' && onSearch()}
            data-testid="search-input"
          />
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => setFiltersOpen(!filtersOpen)}
            variant="outline"
            className={`relative ${activeFilterCount > 0 ? 'border-[#7CB342] text-[#7CB342]' : ''}`}
            data-testid="toggle-filters-btn"
          >
            <Filter className="w-4 h-4 mr-1.5" />
            Filters
            {activeFilterCount > 0 && (
              <span className="ml-1.5 bg-[#7CB342] text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                {activeFilterCount}
              </span>
            )}
            {filtersOpen ? <ChevronUp className="w-4 h-4 ml-1" /> : <ChevronDown className="w-4 h-4 ml-1" />}
          </Button>
          <Button onClick={onSearch} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="search-btn">
            <Search className="w-4 h-4 mr-1.5" /> Search
          </Button>
        </div>
      </div>

      {/* Active filter chips */}
      {activeFilterCount > 0 && (
        <div className="flex flex-wrap gap-1.5 items-center" data-testid="active-filters">
          <span className="text-xs text-slate-500 mr-1">Active:</span>
          {skills && <FilterChip label={`Skills: ${skills}`} onRemove={() => setSkills('')} />}
          {filters.phone && <FilterChip label={`Phone: ${filters.phone}`} onRemove={() => updateFilter('phone', '')} />}
          {filters.email && <FilterChip label={`Email: ${filters.email}`} onRemove={() => updateFilter('email', '')} />}
          {filters.location && <FilterChip label={`Location: ${filters.location}`} onRemove={() => updateFilter('location', '')} />}
          {filters.company && <FilterChip label={`Company: ${filters.company}`} onRemove={() => updateFilter('company', '')} />}
          {filters.noticePeriod && <FilterChip label={`Notice: ${filters.noticePeriod}`} onRemove={() => updateFilter('noticePeriod', '')} />}
          {(filters.minExperience || filters.maxExperience) && (
            <FilterChip label={`Exp: ${filters.minExperience || '0'}-${filters.maxExperience || 'any'} yrs`} onRemove={() => { updateFilter('minExperience', ''); updateFilter('maxExperience', ''); }} />
          )}
          {(filters.minSalary || filters.maxSalary) && (
            <FilterChip label={`Salary: ${filters.minSalary || '0'}-${filters.maxSalary || 'any'}`} onRemove={() => { updateFilter('minSalary', ''); updateFilter('maxSalary', ''); }} />
          )}
          {filters.source && <FilterChip label={`Source: ${filters.source}`} onRemove={() => updateFilter('source', '')} />}
          {filters.hasResume && <FilterChip label={`Resume: ${filters.hasResume}`} onRemove={() => updateFilter('hasResume', '')} />}
          {filters.contactHidden && <FilterChip label={`Contact: ${filters.contactHidden === 'yes' ? 'Hidden' : 'Visible'}`} onRemove={() => updateFilter('contactHidden', '')} />}
          {filters.capturedAfter && <FilterChip label={`After: ${filters.capturedAfter}`} onRemove={() => updateFilter('capturedAfter', '')} />}
          {filters.capturedBefore && <FilterChip label={`Before: ${filters.capturedBefore}`} onRemove={() => updateFilter('capturedBefore', '')} />}
          {filters.mandateId && <FilterChip label={`Mandate: ${mandateLabel}`} onRemove={() => updateFilter('mandateId', '')} />}
          {filters.aiSource && <FilterChip label={`AI: ${filters.aiSource === 'nvidia' ? 'NVIDIA Nemotron' : filters.aiSource === 'gpt_oss' ? 'GPT-OSS 120B' : filters.aiSource === 'runpod' ? 'RunPod' : filters.aiSource === 'anthropic' ? 'Anthropic' : filters.aiSource === 'emergent' ? 'Emergent' : filters.aiSource}`} onRemove={() => updateFilter('aiSource', '')} />}
          {filters.smartTags && <FilterChip label={`Tags: ${filters.smartTags}`} onRemove={() => updateFilter('smartTags', '')} />}
          <button onClick={clearFilters} className="text-xs text-red-500 hover:text-red-700 ml-1 underline" data-testid="clear-all-filters">Clear all</button>
        </div>
      )}

      {/* Expandable filter grid */}
      {filtersOpen && (
        <div className="border-t pt-3 mt-1 space-y-3 animate-in slide-in-from-top-2 duration-200" data-testid="filter-panel">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Phone className="w-3 h-3" /> Phone</Label>
              <Input value={filters.phone} onChange={(e) => updateFilter('phone', e.target.value)} placeholder="Search by phone number" data-testid="filter-phone" className="text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Mail className="w-3 h-3" /> Email</Label>
              <Input value={filters.email} onChange={(e) => updateFilter('email', e.target.value)} placeholder="Search by email" data-testid="filter-email" className="text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><MapPin className="w-3 h-3" /> Location</Label>
              <Input value={filters.location} onChange={(e) => updateFilter('location', e.target.value)} placeholder="City or location" data-testid="filter-location" className="text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Building2 className="w-3 h-3" /> Company</Label>
              <Input value={filters.company} onChange={(e) => updateFilter('company', e.target.value)} placeholder="Current company" data-testid="filter-company" className="text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Code className="w-3 h-3" /> Skills</Label>
              <Input value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="Java, React, Python..." data-testid="filter-skills" className="text-sm" />
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Clock className="w-3 h-3" /> Notice Period</Label>
              <Select value={filters.noticePeriod} onValueChange={(v) => updateFilter('noticePeriod', v === '_all' ? '' : v)}>
                <SelectTrigger className="text-sm" data-testid="filter-notice"><SelectValue placeholder="Any" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">Any</SelectItem>
                  {NOTICE_PERIODS.map(np => <SelectItem key={np} value={np}>{np}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Briefcase className="w-3 h-3" /> Experience (years)</Label>
              <div className="flex gap-1.5">
                <Input value={filters.minExperience} onChange={(e) => updateFilter('minExperience', e.target.value)} placeholder="Min" type="number" min="0" data-testid="filter-min-exp" className="text-sm" />
                <span className="text-slate-400 self-center text-xs">to</span>
                <Input value={filters.maxExperience} onChange={(e) => updateFilter('maxExperience', e.target.value)} placeholder="Max" type="number" min="0" data-testid="filter-max-exp" className="text-sm" />
              </div>
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><DollarSign className="w-3 h-3" /> Salary (INR)</Label>
              <div className="flex gap-1.5">
                <Input value={filters.minSalary} onChange={(e) => updateFilter('minSalary', e.target.value)} placeholder="Min" type="number" data-testid="filter-min-salary" className="text-sm" />
                <span className="text-slate-400 self-center text-xs">to</span>
                <Input value={filters.maxSalary} onChange={(e) => updateFilter('maxSalary', e.target.value)} placeholder="Max" type="number" data-testid="filter-max-salary" className="text-sm" />
              </div>
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Database className="w-3 h-3" /> Source</Label>
              <Select value={filters.source} onValueChange={(v) => updateFilter('source', v === '_all' ? '' : v)}>
                <SelectTrigger className="text-sm" data-testid="filter-source"><SelectValue placeholder="Any source" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">Any source</SelectItem>
                  <SelectItem value="extension">Naukri Extension</SelectItem>
                  <SelectItem value="manual">Manual Upload</SelectItem>
                  <SelectItem value="bulk">Bulk Import</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><FileText className="w-3 h-3" /> Has Resume</Label>
              <Select value={filters.hasResume} onValueChange={(v) => updateFilter('hasResume', v === '_all' ? '' : v)}>
                <SelectTrigger className="text-sm" data-testid="filter-has-resume"><SelectValue placeholder="Any" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">Any</SelectItem>
                  <SelectItem value="yes">Yes - Has resume</SelectItem>
                  <SelectItem value="no">No - Missing resume</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><EyeOff className="w-3 h-3" /> Contact Status</Label>
              <Select value={filters.contactHidden} onValueChange={(v) => updateFilter('contactHidden', v === '_all' ? '' : v)}>
                <SelectTrigger className="text-sm" data-testid="filter-contact-hidden"><SelectValue placeholder="Any" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">Any</SelectItem>
                  <SelectItem value="yes">Hidden (missing email/phone)</SelectItem>
                  <SelectItem value="no">Visible (has both)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Target className="w-3 h-3" /> Mandate</Label>
              <Select value={filters.mandateId || '_all'} onValueChange={(v) => updateFilter('mandateId', v === '_all' ? '' : v)}>
                <SelectTrigger className="text-sm" data-testid="filter-mandate"><SelectValue placeholder="Any mandate" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">All Mandates</SelectItem>
                  {mandates.map(m => <SelectItem key={m.id} value={m.id}>{m.title} — {m.company_name || ''}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Calendar className="w-3 h-3" /> Captured</Label>
              <div className="flex gap-1 mb-1.5">
                {[['Today', 'today'], ['Week', 'week'], ['Month', 'month']].map(([l, v]) => (
                  <button key={v} onClick={() => setDatePreset(v)} className="px-2 py-0.5 text-xs rounded border border-slate-200 hover:border-[#7CB342] hover:text-[#7CB342] transition-colors" data-testid={`date-preset-${v}`}>{l}</button>
                ))}
              </div>
              <div className="flex gap-1.5">
                <Input value={filters.capturedAfter} onChange={(e) => updateFilter('capturedAfter', e.target.value)} type="date" data-testid="filter-date-after" className="text-sm" />
                <Input value={filters.capturedBefore} onChange={(e) => updateFilter('capturedBefore', e.target.value)} type="date" data-testid="filter-date-before" className="text-sm" />
              </div>
            </div>
            {isAdmin && (
              <div>
                <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Briefcase className="w-3 h-3" /> AI Source</Label>
                <Select value={filters.aiSource || '_all'} onValueChange={(v) => updateFilter('aiSource', v === '_all' ? '' : v)}>
                  <SelectTrigger className="text-sm" data-testid="filter-ai-source"><SelectValue placeholder="Any AI source" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_all">All Sources</SelectItem>
                    <SelectItem value="nvidia">N - NVIDIA Nemotron 550B</SelectItem>
                    <SelectItem value="gpt_oss">GO - OpenAI GPT-OSS 120B</SelectItem>
                    <SelectItem value="runpod">Q - RunPod (Qwen)</SelectItem>
                    <SelectItem value="anthropic">AC - Anthropic Direct</SelectItem>
                    <SelectItem value="emergent">EC - Emergent Key</SelectItem>
                    <SelectItem value="regex">Regex (No AI)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            <div>
              <Label className="text-xs text-slate-500 flex items-center gap-1 mb-1"><Target className="w-3 h-3" /> Smart Tags</Label>
              <Input value={filters.smartTags || ''} onChange={(e) => updateFilter('smartTags', e.target.value)} placeholder="Senior, Java Developer, Immediate Joiner" data-testid="filter-smart-tags" className="text-sm" />
              <p className="text-[10px] text-slate-400 mt-0.5">Comma-separated tags</p>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={clearFilters} className="text-slate-500" data-testid="clear-filters-btn">
              <X className="w-3.5 h-3.5 mr-1" /> Clear
            </Button>
            <Button size="sm" onClick={onSearch} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="apply-filters-btn">
              <Search className="w-3.5 h-3.5 mr-1" /> Apply Filters
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
