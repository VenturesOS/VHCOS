import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { adminAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import { Building2, Briefcase, Users, MapPin, Globe, Phone, Mail, ChevronDown, ChevronUp, ExternalLink, Clock, CheckCircle, UserPlus } from 'lucide-react';

const STAGE_COLORS = {
  sourced: 'bg-slate-100 text-slate-600',
  submitted_to_client: 'bg-cyan-50 text-cyan-600',
  shortlisted: 'bg-amber-50 text-amber-600',
  interview: 'bg-violet-50 text-violet-600', offered: 'bg-green-50 text-green-600',
  hired: 'bg-emerald-50 text-emerald-600', joined: 'bg-teal-50 text-teal-700',
  rejected: 'bg-red-50 text-red-500',
  on_hold: 'bg-gray-100 text-gray-600',
  dropped: 'bg-slate-100 text-slate-400',
};

export default function CompanyProfilePage() {
  const { companyId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedMandates, setExpandedMandates] = useState(new Set());

  useEffect(() => {
    setLoading(true);
    adminAPI.getCompanyProfile(companyId)
      .then(res => setData(res.data))
      .catch(() => toast.error('Failed to load company profile'))
      .finally(() => setLoading(false));
  }, [companyId]);

  const toggleMandate = (id) => {
    setExpandedMandates(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="spinner" /></div>;
  if (!data) return <p className="text-slate-400 text-center py-12">Company not found</p>;

  const { company, summary, mandates } = data;

  return (
    <div className="space-y-6" data-testid="company-profile-page">
      {/* Company Header */}
      <Card className="border-slate-200">
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-start gap-4">
            <div className="w-14 h-14 rounded-xl bg-indigo-50 flex items-center justify-center shrink-0">
              <Building2 className="w-7 h-7 text-indigo-600" />
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="font-heading text-xl sm:text-2xl font-bold text-slate-900">{company.name}</h1>
              <div className="flex flex-wrap gap-3 mt-2 text-sm text-slate-500">
                {company.industry && <span className="flex items-center gap-1"><Briefcase className="w-3.5 h-3.5" />{company.industry}</span>}
                {company.location && <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{company.location}</span>}
                {company.website && (
                  <a href={company.website} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-blue-600 hover:underline">
                    <Globe className="w-3.5 h-3.5" />{company.website}
                  </a>
                )}
              </div>
              {company.description && <p className="text-sm text-slate-600 mt-3">{company.description}</p>}
            </div>
          </div>
          {/* HR Contacts */}
          {company.hr_contacts?.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <p className="text-xs font-medium text-slate-500 mb-2">HR Contacts</p>
              <div className="flex flex-wrap gap-4">
                {company.hr_contacts.map((hr, i) => (
                  <div key={i} className="text-sm text-slate-600">
                    <span className="font-medium">{hr.name}</span>
                    {hr.designation && <span className="text-slate-400"> ({hr.designation})</span>}
                    {hr.phone && <span className="flex items-center gap-1 text-xs mt-0.5"><Phone className="w-3 h-3" />{hr.phone}</span>}
                    {hr.email && <span className="flex items-center gap-1 text-xs"><Mail className="w-3 h-3" />{hr.email}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-slate-900">{summary.total_mandates}</p>
            <p className="text-xs text-slate-500">Total Mandates</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-green-600">{summary.active_mandates}</p>
            <p className="text-xs text-slate-500">Active</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-blue-600">{summary.total_candidates_sourced}</p>
            <p className="text-xs text-slate-500">Candidates Sourced</p>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-emerald-600">{summary.total_hired}</p>
            <p className="text-xs text-slate-500">Hired</p>
          </CardContent>
        </Card>
      </div>

      {/* Mandate History */}
      <div>
        <h2 className="font-heading text-lg font-semibold text-slate-900 mb-3">Mandate History</h2>
        <div className="space-y-3">
          {mandates.map((m) => (
            <Card key={m.id} className="border-slate-200" data-testid={`mandate-${m.id}`}>
              <button className="w-full text-left p-4 flex items-start justify-between gap-3" onClick={() => toggleMandate(m.id)}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-medium text-slate-900">{m.title}</h3>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${m.status === 'active' ? 'bg-green-50 text-green-600' : 'bg-slate-100 text-slate-500'}`}>
                      {m.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    {m.location && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{m.location}</span>}
                    <span className="flex items-center gap-1"><Users className="w-3 h-3" />{m.candidates_count} candidates</span>
                    {m.created_by && <span className="flex items-center gap-1"><UserPlus className="w-3 h-3" />by {m.created_by}</span>}
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(m.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                  </div>
                  {/* Stage breakdown pills */}
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {Object.entries(m.stage_breakdown).map(([stage, count]) => (
                      <span key={stage} className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${STAGE_COLORS[stage] || 'bg-slate-100 text-slate-500'}`}>
                        {stage.replace(/_/g, ' ')}: {count}
                      </span>
                    ))}
                  </div>
                  {m.team_members?.length > 0 && (
                    <p className="text-[11px] text-slate-400 mt-1.5">Team: {m.team_members.join(', ')}</p>
                  )}
                </div>
                {expandedMandates.has(m.id) ? <ChevronUp className="w-4 h-4 text-slate-400 shrink-0 mt-1" /> : <ChevronDown className="w-4 h-4 text-slate-400 shrink-0 mt-1" />}
              </button>

              {/* Expanded: Candidate List */}
              {expandedMandates.has(m.id) && m.candidates.length > 0 && (
                <div className="border-t border-slate-100 px-4 pb-4">
                  <div className="divide-y divide-slate-50">
                    {m.candidates.map((c, i) => (
                      <div key={`${c.candidate_id}-${i}`} className="py-2.5 flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">{c.candidate_name}</p>
                          <div className="flex items-center gap-2 text-[11px] text-slate-400">
                            {c.submitted_by && <span>by {c.submitted_by}</span>}
                            <span>{new Date(c.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${STAGE_COLORS[c.stage] || 'bg-slate-100 text-slate-500'}`}>
                            {c.stage?.replace(/_/g, ' ')}
                          </span>
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0"
                            onClick={(e) => { e.stopPropagation(); navigate(`../naukri-profile/${c.candidate_id}`); }}>
                            <ExternalLink className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          ))}
          {mandates.length === 0 && (
            <p className="text-slate-400 text-sm text-center py-8">No mandates found for this client.</p>
          )}
        </div>
      </div>
    </div>
  );
}
