import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Database, FileText, Briefcase, Download, Paperclip, ShieldAlert } from 'lucide-react';

const SOURCE_STYLES = {
  naukri_extension: { bg: 'bg-orange-50 text-orange-600', label: 'Naukri' },
  naukri_mailer_extension: { bg: 'bg-amber-100 text-amber-700 border border-amber-300', label: 'M Mailer' },
  linkedin_extension: { bg: 'bg-blue-50 text-blue-700', label: 'LinkedIn' },
  foundit_extension: { bg: 'bg-purple-50 text-purple-600', label: 'Foundit' },
  cv_upload: { bg: 'bg-teal-50 text-teal-600', label: 'CV Upload' },
  bulk_import: { bg: 'bg-amber-50 text-amber-600', label: 'Bulk Import' },
  public_application: { bg: 'bg-blue-50 text-blue-600', label: 'Applied' },
  job_application: { bg: 'bg-blue-50 text-blue-600', label: 'Applied' },
  recruiter: { bg: 'bg-purple-50 text-purple-600', label: 'Recruiter' },
  recruiter_upload: { bg: 'bg-purple-50 text-purple-600', label: 'Recruiter' },
  self_registered: { bg: 'bg-green-50 text-green-600', label: 'Registered' },
  candidate_registration: { bg: 'bg-green-50 text-green-600', label: 'Registered' },
  employer: { bg: 'bg-indigo-50 text-indigo-600', label: 'Employer' },
  talent_pool_upload: { bg: 'bg-cyan-50 text-cyan-600', label: 'Pool Upload' },
  admin: { bg: 'bg-rose-50 text-rose-600', label: 'Admin' },
};

const AI_SOURCE_BADGES = {
  runpod_qwen14b: { label: 'Q', bg: 'bg-sky-100 text-sky-700 border border-sky-300', title: 'RunPod Qwen 14B' },
  anthropic_direct_haiku: { label: 'AC', bg: 'bg-violet-100 text-violet-700 border border-violet-300', title: 'Anthropic Direct (Haiku)' },
  claude_haiku_4_5_emergent: { label: 'EC', bg: 'bg-emerald-100 text-emerald-700 border border-emerald-300', title: 'Emergent Key (Haiku)' },
  emergent_haiku_4_5: { label: 'EC', bg: 'bg-emerald-100 text-emerald-700 border border-emerald-300', title: 'Emergent Key (Haiku)' },
  regex_zero_cost: { label: 'RX', bg: 'bg-slate-100 text-slate-600 border border-slate-300', title: 'Regex (No AI)' },
  regex_hybrid: { label: 'RX', bg: 'bg-slate-100 text-slate-600 border border-slate-300', title: 'Regex Hybrid' },
  local_llm_gemma4: { label: 'Q', bg: 'bg-sky-100 text-sky-700 border border-sky-300', title: 'Local Gemma 4' },
};

export function CandidateListItem({ candidate, onSelect, onAddApplicant, onAttachCV, onDownloadResume, navigate, isAdmin = false }) {
  const sourceStyle = SOURCE_STYLES[candidate.source] || { bg: 'bg-slate-100 text-slate-600', label: candidate.source || 'Unknown' };

  return (
    <div
      className="p-3 sm:p-4 hover:bg-slate-50 transition-colors cursor-pointer"
      onClick={() => onSelect(candidate)}
      data-testid={`candidate-row-${candidate.id}`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-3 sm:gap-4 min-w-0 flex-1">
          <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
            <span className="text-[#7CB342] font-semibold text-sm sm:text-base">
              {candidate.name?.charAt(0).toUpperCase()}
            </span>
          </div>
          <div className="min-w-0">
            <p className="font-medium text-slate-900 truncate">{candidate.name}</p>
            <p className="text-sm text-slate-500 truncate">{candidate.headline || candidate.email}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap ml-13 sm:ml-0">
          {candidate.smart_tags?.length > 0 && (
            <div className="hidden lg:flex flex-wrap gap-1 max-w-xs">
              {candidate.smart_tags.slice(0, 3).map((tag) => (
                <span key={tag} className="px-1.5 py-0.5 bg-indigo-50 text-indigo-600 text-[10px] rounded font-medium border border-indigo-100" data-testid={`smart-tag-${candidate.id}`}>
                  {tag}
                </span>
              ))}
              {candidate.smart_tags.length > 3 && (
                <span className="text-[10px] text-indigo-400">+{candidate.smart_tags.length - 3}</span>
              )}
            </div>
          )}
          {(!candidate.smart_tags || candidate.smart_tags.length === 0) && (
            <div className="hidden lg:flex flex-wrap gap-1 max-w-xs">
              {candidate.skills?.slice(0, 4).map((skill) => (
                <span key={skill} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full">
                  {skill}
                </span>
              ))}
              {(candidate.skills?.length || 0) > 4 && (
                <span className="text-xs text-slate-400">+{candidate.skills.length - 4}</span>
              )}
            </div>
          )}
          <span className={`px-2 py-1 text-xs rounded-full font-medium ${sourceStyle.bg}`} data-testid={`source-badge-${candidate.id}`}>
            {sourceStyle.label}
          </span>
          {isAdmin && candidate.ai_enrichment_source && (() => {
            const aiStyle = AI_SOURCE_BADGES[candidate.ai_enrichment_source];
            if (!aiStyle) return null;
            return (
              <span
                className={`px-1.5 py-0.5 text-[10px] rounded font-bold ${aiStyle.bg}`}
                title={aiStyle.title}
                data-testid={`ai-source-badge-${candidate.id}`}
              >
                {aiStyle.label}
              </span>
            );
          })()}
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => { e.stopPropagation(); navigate(`../naukri-profile/${candidate.id}`); }}
            className="text-orange-600 border-orange-300 hover:bg-orange-50 hidden sm:inline-flex"
            data-testid={`view-full-profile-${candidate.id}`}
          >
            <FileText className="w-4 h-4 sm:mr-1" /> <span className="hidden md:inline">Full Profile</span>
          </Button>
          {candidate.bulk_import_restricted && (
            <Badge variant="outline" className="border-amber-300 text-amber-600 text-xs hidden sm:inline-flex">
              <ShieldAlert className="w-3 h-3 mr-1" /> Admin
            </Badge>
          )}
          {candidate.source === 'bulk_import' && !candidate.cv_attached && !candidate.resume_url && (
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => { e.stopPropagation(); onAttachCV(candidate); }}
              className="text-amber-600 border-amber-400 hover:bg-amber-50 hidden sm:inline-flex"
              data-testid={`attach-cv-btn-${candidate.id}`}
            >
              <Paperclip className="w-4 h-4 sm:mr-1" /> <span className="hidden md:inline">Attach CV</span>
            </Button>
          )}
          {candidate.source !== 'bulk_import' && !candidate.cv_attached && !candidate.resume_url && (
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => { e.stopPropagation(); onAttachCV(candidate); }}
              className="text-blue-600 border-blue-400 hover:bg-blue-50 hidden sm:inline-flex"
              data-testid={`attach-cv-btn-${candidate.id}`}
            >
              <Paperclip className="w-4 h-4 sm:mr-1" /> <span className="hidden md:inline">Attach CV</span>
            </Button>
          )}
          {candidate.is_active !== false && (
            <span className="w-2 h-2 bg-green-500 rounded-full hidden sm:block" title="Active"></span>
          )}
          {(candidate.cv_attached || candidate.resume_url) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => { e.stopPropagation(); onDownloadResume(candidate); }}
              className="text-slate-600 hover:text-[#7CB342] p-1 sm:p-2"
              data-testid={`download-resume-btn-${candidate.id}`}
              title="Download Resume"
            >
              <Download className="w-4 h-4" />
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => { e.stopPropagation(); onAddApplicant(candidate); }}
            className="text-[#7CB342] border-[#7CB342] hover:bg-green-50 text-xs sm:text-sm"
            data-testid={`add-applicant-btn-${candidate.id}`}
          >
            <Briefcase className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Add</span>
          </Button>
        </div>
      </div>
    </div>
  );
}
