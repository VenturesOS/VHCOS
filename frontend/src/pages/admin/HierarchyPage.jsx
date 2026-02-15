import { useState, useEffect } from 'react';
import { governanceAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { 
  Users, Building2, UserCircle, Briefcase, 
  ChevronDown, ChevronRight, Network, AlertCircle
} from 'lucide-react';

export default function HierarchyPage() {
  const [hierarchy, setHierarchy] = useState([]);
  const [unassignedRecruiters, setUnassignedRecruiters] = useState([]);
  const [unassignedCompanies, setUnassignedCompanies] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [expandedEmployers, setExpandedEmployers] = useState({});
  const [expandedTeams, setExpandedTeams] = useState({});

  useEffect(() => {
    loadHierarchy();
  }, []);

  const loadHierarchy = async () => {
    try {
      const res = await governanceAPI.getHierarchy();
      setHierarchy(res.data.hierarchy || []);
      setUnassignedRecruiters(res.data.unassigned_recruiters || []);
      setUnassignedCompanies(res.data.unassigned_companies || []);
      setSummary(res.data.summary || {});
      
      // Auto-expand all employers initially
      const expanded = {};
      res.data.hierarchy?.forEach(emp => {
        expanded[emp.employer_id] = true;
      });
      setExpandedEmployers(expanded);
    } catch (error) {
      toast.error('Failed to load hierarchy data');
    } finally {
      setLoading(false);
    }
  };

  const toggleEmployer = (employerId) => {
    setExpandedEmployers(prev => ({
      ...prev,
      [employerId]: !prev[employerId]
    }));
  };

  const toggleTeam = (teamId) => {
    setExpandedTeams(prev => ({
      ...prev,
      [teamId]: !prev[teamId]
    }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="hierarchy-page">
      {/* Header */}
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Organization Hierarchy</h1>
        <p className="text-slate-500 mt-1">Visual overview of employers, teams, recruiters, and companies</p>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
              <UserCircle className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{summary.total_employers || 0}</p>
              <p className="text-xs text-slate-500">Employers</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#DCFCE7] flex items-center justify-center">
              <Users className="w-5 h-5 text-[#7CB342]" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{summary.total_teams || 0}</p>
              <p className="text-xs text-slate-500">Teams</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
              <AlertCircle className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{summary.total_unassigned_recruiters || 0}</p>
              <p className="text-xs text-slate-500">Unassigned Recruiters</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center">
              <Building2 className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{summary.total_unassigned_companies || 0}</p>
              <p className="text-xs text-slate-500">Unassigned Companies</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Hierarchy Tree */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading flex items-center gap-2">
            <Network className="w-5 h-5 text-[#7CB342]" />
            Organization Structure
          </CardTitle>
        </CardHeader>
        <CardContent>
          {hierarchy.length === 0 ? (
            <div className="text-center py-12">
              <Network className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500">No hierarchy data</p>
              <p className="text-sm text-slate-400 mt-1">Create teams to build your organization structure</p>
            </div>
          ) : (
            <div className="space-y-4">
              {hierarchy.map((employer) => (
                <EmployerNode 
                  key={employer.employer_id}
                  employer={employer}
                  expanded={expandedEmployers[employer.employer_id]}
                  expandedTeams={expandedTeams}
                  onToggle={() => toggleEmployer(employer.employer_id)}
                  onToggleTeam={toggleTeam}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Unassigned Resources */}
      {(unassignedRecruiters.length > 0 || unassignedCompanies.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Unassigned Recruiters */}
          {unassignedRecruiters.length > 0 && (
            <Card className="border-amber-200 bg-amber-50/50">
              <CardHeader className="pb-3">
                <CardTitle className="font-heading text-amber-700 flex items-center gap-2 text-lg">
                  <AlertCircle className="w-5 h-5" />
                  Unassigned Recruiters
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {unassignedRecruiters.map((rec) => (
                    <div key={rec.id} className="flex items-center gap-3 p-3 bg-white rounded-lg border border-amber-100">
                      <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center">
                        <UserCircle className="w-4 h-4 text-amber-600" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-700">{rec.name}</p>
                        <p className="text-xs text-slate-400">{rec.email}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-amber-600 mt-3">
                  Assign these recruiters to teams via the Teams page
                </p>
              </CardContent>
            </Card>
          )}

          {/* Unassigned Companies */}
          {unassignedCompanies.length > 0 && (
            <Card className="border-red-200 bg-red-50/50">
              <CardHeader className="pb-3">
                <CardTitle className="font-heading text-red-700 flex items-center gap-2 text-lg">
                  <Building2 className="w-5 h-5" />
                  Unassigned Companies
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {unassignedCompanies.map((comp) => (
                    <div key={comp.id} className="flex items-center gap-3 p-3 bg-white rounded-lg border border-red-100">
                      <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center">
                        <Building2 className="w-4 h-4 text-red-600" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-700">{comp.name}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-red-600 mt-3">
                  Assign these companies to teams via the Teams page
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Permissions Matrix (Read-Only) */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading">Permissions Matrix</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-3 px-4 font-medium text-slate-600">Action</th>
                  <th className="text-center py-3 px-4 font-medium text-slate-600">Admin</th>
                  <th className="text-center py-3 px-4 font-medium text-slate-600">Employer</th>
                  <th className="text-center py-3 px-4 font-medium text-slate-600">Recruiter</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-slate-100">
                  <td className="py-3 px-4 text-slate-700">Create Jobs</td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge allowed note="Pending Approval" /></td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-3 px-4 text-slate-700">Approve Jobs</td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge allowed note="Own Team" /></td>
                  <td className="text-center py-3 px-4"><PermBadge /></td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-3 px-4 text-slate-700">Create Teams</td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge /></td>
                  <td className="text-center py-3 px-4"><PermBadge /></td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-3 px-4 text-slate-700">Manage Team Members</td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge /></td>
                  <td className="text-center py-3 px-4"><PermBadge /></td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-3 px-4 text-slate-700">Create Referrals</td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-3 px-4 text-slate-700">Approve Referrals</td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge /></td>
                </tr>
                <tr>
                  <td className="py-3 px-4 text-slate-700">View Hierarchy</td>
                  <td className="text-center py-3 px-4"><PermBadge allowed /></td>
                  <td className="text-center py-3 px-4"><PermBadge allowed note="Own Teams" /></td>
                  <td className="text-center py-3 px-4"><PermBadge /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// Employer Node Component
function EmployerNode({ employer, expanded, expandedTeams, onToggle, onToggleTeam }) {
  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden">
      {/* Employer Header */}
      <div 
        className="flex items-center gap-3 p-4 bg-blue-50 cursor-pointer hover:bg-blue-100 transition-colors"
        onClick={onToggle}
      >
        {expanded ? (
          <ChevronDown className="w-5 h-5 text-blue-600" />
        ) : (
          <ChevronRight className="w-5 h-5 text-blue-600" />
        )}
        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
          <UserCircle className="w-5 h-5 text-blue-600" />
        </div>
        <div className="flex-1">
          <p className="font-medium text-slate-900">{employer.employer_name}</p>
          <p className="text-xs text-slate-500">{employer.employer_email}</p>
        </div>
        <Badge variant="outline" className="text-blue-600 border-blue-200">
          {employer.teams?.length || 0} Teams
        </Badge>
      </div>

      {/* Teams */}
      {expanded && employer.teams?.length > 0 && (
        <div className="pl-8 border-t border-slate-100">
          {employer.teams.map((team) => (
            <TeamNode 
              key={team.team_id}
              team={team}
              expanded={expandedTeams[team.team_id]}
              onToggle={() => onToggleTeam(team.team_id)}
            />
          ))}
        </div>
      )}

      {expanded && (!employer.teams || employer.teams.length === 0) && (
        <div className="pl-8 py-4 border-t border-slate-100 text-sm text-slate-400">
          No teams assigned to this employer
        </div>
      )}
    </div>
  );
}

// Team Node Component
function TeamNode({ team, expanded, onToggle }) {
  return (
    <div className="border-b border-slate-100 last:border-b-0">
      {/* Team Header */}
      <div 
        className="flex items-center gap-3 p-4 cursor-pointer hover:bg-slate-50 transition-colors"
        onClick={onToggle}
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-[#7CB342]" />
        ) : (
          <ChevronRight className="w-4 h-4 text-[#7CB342]" />
        )}
        <div className="w-8 h-8 rounded-lg bg-[#DCFCE7] flex items-center justify-center">
          <Users className="w-4 h-4 text-[#7CB342]" />
        </div>
        <div className="flex-1">
          <p className="font-medium text-slate-800">{team.team_name}</p>
          <div className="flex gap-2 mt-1">
            <span className="text-xs text-slate-400">{team.recruiters?.length || 0} recruiters</span>
            <span className="text-xs text-slate-400">•</span>
            <span className="text-xs text-slate-400">{team.companies?.length || 0} companies</span>
          </div>
        </div>
        <Badge className="bg-[#DCFCE7] text-[#7CB342]">
          {team.active_jobs_count || 0} Jobs
        </Badge>
      </div>

      {/* Team Members */}
      {expanded && (
        <div className="pl-12 pb-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Recruiters */}
          <div>
            <p className="text-xs font-medium text-slate-500 mb-2">Recruiters</p>
            {team.recruiters?.length > 0 ? (
              <div className="space-y-1">
                {team.recruiters.map((rec) => (
                  <div key={rec.id} className="flex items-center gap-2 text-sm text-slate-600">
                    <UserCircle className="w-4 h-4 text-purple-500" />
                    <span>{rec.name}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">No recruiters assigned</p>
            )}
          </div>

          {/* Companies */}
          <div>
            <p className="text-xs font-medium text-slate-500 mb-2">Companies</p>
            {team.companies?.length > 0 ? (
              <div className="space-y-1">
                {team.companies.map((comp) => (
                  <div key={comp.id} className="flex items-center gap-2 text-sm text-slate-600">
                    <Building2 className="w-4 h-4 text-amber-500" />
                    <span>{comp.name}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">No companies assigned</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Permission Badge Component
function PermBadge({ allowed, note }) {
  if (allowed) {
    return (
      <div className="inline-flex flex-col items-center">
        <span className="w-6 h-6 rounded-full bg-[#DCFCE7] text-[#7CB342] flex items-center justify-center text-xs font-bold">✓</span>
        {note && <span className="text-[10px] text-slate-400 mt-1">{note}</span>}
      </div>
    );
  }
  return (
    <span className="w-6 h-6 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center text-xs mx-auto">–</span>
  );
}
