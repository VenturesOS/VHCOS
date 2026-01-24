import { useState, useEffect } from 'react';
import { employerPortalAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import { Users, Briefcase, TrendingUp, DollarSign, User, Mail, Calendar, CheckCircle, XCircle, ChevronRight, Clock, Target, Award, BarChart3 } from 'lucide-react';

export default function EmployerMyTeamPage() {
  const [teamData, setTeamData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedMember, setSelectedMember] = useState(null);

  useEffect(() => {
    loadTeamData();
  }, []);

  const loadTeamData = async () => {
    try {
      const res = await employerPortalAPI.getMyTeam();
      setTeamData(res.data);
    } catch (error) {
      toast.error('Failed to load team data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  if (!teamData?.team) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-heading font-bold text-slate-900">My Team</h1>
          <p className="text-sm text-slate-500 mt-1">Manage your team and track performance</p>
        </div>
        <Card className="border-slate-200">
          <CardContent className="p-12 text-center">
            <Users className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-600 mb-2">No Team Assigned</h3>
            <p className="text-slate-500">Contact your administrator to set up your team.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { team, members, summary } = teamData;

  return (
    <div className="space-y-6" data-testid="employer-my-team">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-heading font-bold text-slate-900">My Team</h1>
        <p className="text-sm text-slate-500 mt-1">Team: {team.name} • {summary.total_members} members</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <Users className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{summary.total_members}</p>
                <p className="text-xs text-slate-500">Team Members</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
                <Briefcase className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{summary.total_mandates}</p>
                <p className="text-xs text-slate-500">Active Mandates</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <Target className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{summary.total_pipeline}</p>
                <p className="text-xs text-slate-500">Total Pipeline</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-orange-100 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-orange-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{formatSalaryINR(summary.total_revenue_pipeline)}</p>
                <p className="text-xs text-slate-500">Pipeline Revenue</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200 bg-gradient-to-r from-green-50 to-white">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-green-600">{formatSalaryINR(summary.total_revenue_closed)}</p>
                <p className="text-xs text-slate-500">Closed Revenue</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Team Members List */}
      <Card className="border-slate-200">
        <CardHeader className="border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Users className="w-5 h-5 text-[#7CB342]" />
            Team Members
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-slate-100">
            {members.map((member) => (
              <div
                key={member.id}
                className="p-4 hover:bg-slate-50 transition-colors cursor-pointer flex items-center justify-between"
                onClick={() => setSelectedMember(member)}
                data-testid={`team-member-${member.id}`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                    <span className="text-[#7CB342] font-semibold text-lg">
                      {member.name?.charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-slate-900">{member.name}</p>
                      {member.is_active ? (
                        <span className="w-2 h-2 bg-green-500 rounded-full" title="Active"></span>
                      ) : (
                        <span className="w-2 h-2 bg-slate-300 rounded-full" title="Inactive"></span>
                      )}
                    </div>
                    <p className="text-sm text-slate-500">{member.email}</p>
                  </div>
                </div>

                <div className="flex items-center gap-8">
                  {/* Mandates */}
                  <div className="text-center">
                    <p className="text-lg font-semibold text-slate-900">{member.mandates_assigned}</p>
                    <p className="text-xs text-slate-500">Mandates</p>
                  </div>

                  {/* Pipeline */}
                  <div className="text-center">
                    <p className="text-lg font-semibold text-slate-900">{member.total_pipeline_count}</p>
                    <p className="text-xs text-slate-500">Pipeline</p>
                  </div>

                  {/* Revenue Pipeline */}
                  <div className="text-center hidden md:block">
                    <p className="text-lg font-semibold text-amber-600">{formatSalaryINR(member.revenue_pipeline)}</p>
                    <p className="text-xs text-slate-500">In Pipeline</p>
                  </div>

                  {/* Revenue Closed */}
                  <div className="text-center hidden md:block">
                    <p className="text-lg font-semibold text-green-600">{formatSalaryINR(member.revenue_closed)}</p>
                    <p className="text-xs text-slate-500">Closed</p>
                  </div>

                  <ChevronRight className="w-5 h-5 text-slate-400" />
                </div>
              </div>
            ))}

            {members.length === 0 && (
              <div className="p-12 text-center">
                <Users className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <p className="text-slate-500">No team members assigned yet</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Member Detail Dialog */}
      <Dialog open={!!selectedMember} onOpenChange={() => setSelectedMember(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">Team Member Performance</DialogTitle>
          </DialogHeader>
          {selectedMember && (
            <Tabs defaultValue="overview" className="w-full">
              <TabsList className="mb-4">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
                <TabsTrigger value="mandates">Mandates</TabsTrigger>
              </TabsList>

              <TabsContent value="overview">
                <div className="space-y-4">
                  {/* Profile */}
                  <div className="flex items-center gap-4 p-4 bg-slate-50 rounded-lg">
                    <div className="w-16 h-16 rounded-full bg-[#DCFCE7] flex items-center justify-center">
                      <span className="text-[#7CB342] font-bold text-2xl">
                        {selectedMember.name?.charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-xl">{selectedMember.name}</h3>
                        {selectedMember.is_active ? (
                          <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full">Active</span>
                        ) : (
                          <span className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full">Inactive</span>
                        )}
                      </div>
                      <p className="text-slate-500 flex items-center gap-1">
                        <Mail className="w-4 h-4" /> {selectedMember.email}
                      </p>
                      {selectedMember.joined_at && (
                        <p className="text-sm text-slate-400 flex items-center gap-1">
                          <Calendar className="w-3 h-3" /> Joined: {new Date(selectedMember.joined_at).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-3 bg-blue-50 rounded-lg text-center">
                      <p className="text-2xl font-bold text-blue-600">{selectedMember.mandates_assigned}</p>
                      <p className="text-xs text-blue-600">Mandates</p>
                    </div>
                    <div className="p-3 bg-purple-50 rounded-lg text-center">
                      <p className="text-2xl font-bold text-purple-600">{selectedMember.total_pipeline_count}</p>
                      <p className="text-xs text-purple-600">Total Pipeline</p>
                    </div>
                    <div className="p-3 bg-amber-50 rounded-lg text-center">
                      <p className="text-2xl font-bold text-amber-600">{formatSalaryINR(selectedMember.revenue_pipeline)}</p>
                      <p className="text-xs text-amber-600">Pipeline Value</p>
                    </div>
                    <div className="p-3 bg-green-50 rounded-lg text-center">
                      <p className="text-2xl font-bold text-green-600">{formatSalaryINR(selectedMember.revenue_closed)}</p>
                      <p className="text-xs text-green-600">Closed Revenue</p>
                    </div>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="pipeline">
                <div className="space-y-4">
                  <h4 className="font-medium">Pipeline Stages</h4>
                  <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
                    {Object.entries(selectedMember.pipeline).map(([stage, count]) => (
                      <div key={stage} className={`p-3 rounded-lg text-center ${
                        stage === 'hired' ? 'bg-green-50' :
                        stage === 'rejected' ? 'bg-red-50' :
                        stage === 'offered' ? 'bg-purple-50' :
                        stage === 'interview' ? 'bg-blue-50' :
                        stage === 'shortlisted' ? 'bg-amber-50' :
                        'bg-slate-50'
                      }`}>
                        <p className={`text-2xl font-bold ${
                          stage === 'hired' ? 'text-green-600' :
                          stage === 'rejected' ? 'text-red-600' :
                          stage === 'offered' ? 'text-purple-600' :
                          stage === 'interview' ? 'text-blue-600' :
                          stage === 'shortlisted' ? 'text-amber-600' :
                          'text-slate-600'
                        }`}>{count}</p>
                        <p className="text-xs text-slate-500 capitalize">{stage}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="mandates">
                <div className="space-y-3">
                  <h4 className="font-medium">Assigned Mandates ({selectedMember.mandates_assigned})</h4>
                  {selectedMember.mandates?.map((mandate) => (
                    <div key={mandate.id} className="p-3 bg-slate-50 rounded-lg">
                      <p className="font-medium text-slate-800">{mandate.title}</p>
                      <p className="text-sm text-slate-500">{mandate.company_name}</p>
                    </div>
                  ))}
                  {(!selectedMember.mandates || selectedMember.mandates.length === 0) && (
                    <p className="text-slate-400 text-sm">No mandates assigned</p>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
