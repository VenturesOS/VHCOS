import { useState, useEffect } from 'react';
import { employerPortalAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import { Building2, Briefcase, TrendingUp, DollarSign, MapPin, Users, FileText, ChevronRight, Info, Banknote, Clock, Target, BarChart3, Lock } from 'lucide-react';

export default function EmployerCompaniesPage() {
  const [companiesData, setCompaniesData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedCompany, setSelectedCompany] = useState(null);

  useEffect(() => {
    loadCompanies();
  }, []);

  const loadCompanies = async () => {
    try {
      const res = await employerPortalAPI.getMyCompanies();
      setCompaniesData(res.data);
    } catch (error) {
      toast.error('Failed to load companies');
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

  const companies = companiesData?.companies || [];

  if (companies.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-heading font-bold text-slate-900">Companies</h1>
          <p className="text-sm text-slate-500 mt-1">View your assigned companies and their details</p>
        </div>
        <Card className="border-slate-200">
          <CardContent className="p-12 text-center">
            <Building2 className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-600 mb-2">No Companies Assigned</h3>
            <p className="text-slate-500">Contact your administrator to assign companies to your team.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Calculate totals
  const totalMandates = companies.reduce((sum, c) => sum + c.mandates.length, 0);
  const totalPipeline = companies.reduce((sum, c) => sum + c.total_pipeline, 0);
  const totalRevenue = companies.reduce((sum, c) => sum + c.total_revenue_closed, 0);

  return (
    <div className="space-y-6" data-testid="employer-companies">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-heading font-bold text-slate-900">Companies</h1>
        <p className="text-sm text-slate-500 mt-1">Companies assigned by Admin • {companies.length} companies</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <Building2 className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{companies.length}</p>
                <p className="text-xs text-slate-500">Companies</p>
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
                <p className="text-2xl font-bold text-slate-900">{totalMandates}</p>
                <p className="text-xs text-slate-500">Total Mandates</p>
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
                <p className="text-2xl font-bold text-slate-900">{totalPipeline}</p>
                <p className="text-xs text-slate-500">Total Pipeline</p>
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
                <p className="text-2xl font-bold text-green-600">{formatSalaryINR(totalRevenue)}</p>
                <p className="text-xs text-slate-500">Closed Revenue</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Companies List */}
      <Card className="border-slate-200">
        <CardHeader className="border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Building2 className="w-5 h-5 text-[#7CB342]" />
            Assigned Companies
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-slate-100">
            {companies.map((company) => (
              <div
                key={company.id}
                className="p-4 hover:bg-slate-50 transition-colors cursor-pointer flex items-center justify-between"
                onClick={() => setSelectedCompany(company)}
                data-testid={`company-row-${company.id}`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center overflow-hidden">
                    {company.logo_url ? (
                      <img src={company.logo_url} alt={company.name} className="w-full h-full object-contain" />
                    ) : (
                      <Building2 className="w-6 h-6 text-slate-400" />
                    )}
                  </div>
                  <div>
                    <p className="font-medium text-slate-900">{company.name}</p>
                    <div className="flex items-center gap-3 text-sm text-slate-500">
                      {company.industry && <span>{company.industry}</span>}
                      {company.location && (
                        <span className="flex items-center gap-1">
                          <MapPin className="w-3 h-3" /> {company.location}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-8">
                  {/* Active Mandates */}
                  <div className="text-center">
                    <p className="text-lg font-semibold text-slate-900">{company.active_mandates_count}</p>
                    <p className="text-xs text-slate-500">Active Mandates</p>
                  </div>

                  {/* Pipeline */}
                  <div className="text-center">
                    <p className="text-lg font-semibold text-slate-900">{company.total_pipeline}</p>
                    <p className="text-xs text-slate-500">Pipeline</p>
                  </div>

                  {/* Fee % */}
                  <div className="text-center hidden md:block">
                    <p className="text-lg font-semibold text-purple-600">
                      {company.commercial?.fee_percentage || '-'}%
                    </p>
                    <p className="text-xs text-slate-500">Fee %</p>
                  </div>

                  {/* Revenue Closed */}
                  <div className="text-center hidden md:block">
                    <p className="text-lg font-semibold text-green-600">{formatSalaryINR(company.total_revenue_closed)}</p>
                    <p className="text-xs text-slate-500">Closed</p>
                  </div>

                  <ChevronRight className="w-5 h-5 text-slate-400" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Company Detail Dialog */}
      <Dialog open={!!selectedCompany} onOpenChange={() => setSelectedCompany(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              {selectedCompany?.logo_url ? (
                <img src={selectedCompany.logo_url} alt="" className="w-8 h-8 rounded object-contain" />
              ) : (
                <Building2 className="w-6 h-6 text-slate-400" />
              )}
              {selectedCompany?.name}
            </DialogTitle>
          </DialogHeader>
          {selectedCompany && (
            <Tabs defaultValue="commercial" className="w-full">
              <TabsList className="mb-4">
                <TabsTrigger value="commercial">
                  <DollarSign className="w-4 h-4 mr-1" /> Commercial Details
                </TabsTrigger>
                <TabsTrigger value="mandates">
                  <Briefcase className="w-4 h-4 mr-1" /> Active Mandates
                </TabsTrigger>
                <TabsTrigger value="pipeline">
                  <BarChart3 className="w-4 h-4 mr-1" /> Pipelines
                </TabsTrigger>
              </TabsList>

              {/* Commercial Details Tab */}
              <TabsContent value="commercial">
                <div className="space-y-4">
                  {/* Read-only notice */}
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-start gap-2">
                    <Lock className="w-4 h-4 text-blue-500 mt-0.5" />
                    <p className="text-sm text-blue-700">
                      Commercial details are managed by Admin. Contact your administrator to make changes.
                    </p>
                  </div>

                  {selectedCompany.commercial ? (
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Fee Percentage</p>
                        <p className="text-2xl font-bold text-purple-600">
                          {selectedCompany.commercial.fee_percentage || '-'}%
                        </p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Currency</p>
                        <p className="text-2xl font-bold text-slate-800">
                          {selectedCompany.commercial.currency || 'INR'}
                        </p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Fee Structure</p>
                        <p className="font-medium text-slate-800 capitalize">
                          {selectedCompany.commercial.fee_structure || '-'}
                        </p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Payment Terms</p>
                        <p className="font-medium text-slate-800">
                          {selectedCompany.commercial.payment_terms || '-'}
                        </p>
                      </div>

                      {/* Commercial Slabs */}
                      {selectedCompany.commercial.commercial_slabs?.length > 0 && (
                        <div className="col-span-2">
                          <p className="text-sm text-slate-500 mb-2">Commercial Slabs</p>
                          <div className="space-y-2">
                            {selectedCompany.commercial.commercial_slabs.map((slab, idx) => (
                              <div key={idx} className="flex items-center justify-between p-3 bg-slate-100 rounded">
                                <span className="text-sm">
                                  {formatSalaryINR(slab.min_salary)} - {slab.max_salary ? formatSalaryINR(slab.max_salary) : 'Above'}
                                </span>
                                <span className="font-medium text-purple-600">{slab.fee_percentage}%</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <Banknote className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                      <p className="text-slate-500">No commercial terms defined</p>
                    </div>
                  )}
                </div>
              </TabsContent>

              {/* Active Mandates Tab */}
              <TabsContent value="mandates">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="font-medium">Active Mandates</h4>
                    <span className="text-sm text-slate-500">{selectedCompany.active_mandates_count} active</span>
                  </div>
                  
                  <div className="space-y-2 max-h-80 overflow-y-auto">
                    {selectedCompany.mandates?.filter(m => m.status === 'active').map((mandate) => (
                      <div key={mandate.id} className="p-4 bg-slate-50 rounded-lg border-l-4 border-[#7CB342]">
                        <div className="flex items-center justify-between mb-2">
                          <p className="font-medium text-slate-800">{mandate.title}</p>
                          <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full capitalize">
                            {mandate.status}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-sm text-slate-500">
                          {mandate.location && (
                            <span className="flex items-center gap-1">
                              <MapPin className="w-3 h-3" /> {mandate.location}
                            </span>
                          )}
                          <span>Pipeline: {mandate.pipeline_count}</span>
                          <span className="text-green-600">Closed: {formatSalaryINR(mandate.total_revenue_closed)}</span>
                        </div>
                      </div>
                    ))}
                    
                    {selectedCompany.mandates?.filter(m => m.status !== 'active').length > 0 && (
                      <>
                        <p className="text-sm text-slate-500 mt-4 pt-4 border-t">Other Mandates</p>
                        {selectedCompany.mandates?.filter(m => m.status !== 'active').map((mandate) => (
                          <div key={mandate.id} className="p-3 bg-slate-100/50 rounded-lg opacity-70">
                            <div className="flex items-center justify-between">
                              <p className="font-medium text-slate-600">{mandate.title}</p>
                              <span className="px-2 py-0.5 bg-slate-200 text-slate-600 text-xs rounded-full capitalize">
                                {mandate.status}
                              </span>
                            </div>
                          </div>
                        ))}
                      </>
                    )}
                    
                    {(!selectedCompany.mandates || selectedCompany.mandates.length === 0) && (
                      <p className="text-slate-400 text-sm text-center py-4">No mandates found</p>
                    )}
                  </div>
                </div>
              </TabsContent>

              {/* Pipelines Tab */}
              <TabsContent value="pipeline">
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3 mb-4">
                    <div className="p-3 bg-amber-50 rounded-lg text-center">
                      <p className="text-2xl font-bold text-amber-600">{selectedCompany.total_pipeline}</p>
                      <p className="text-xs text-amber-600">Total Pipeline</p>
                    </div>
                    <div className="p-3 bg-green-50 rounded-lg text-center">
                      <p className="text-2xl font-bold text-green-600">{formatSalaryINR(selectedCompany.total_revenue_closed)}</p>
                      <p className="text-xs text-green-600">Closed Revenue</p>
                    </div>
                  </div>

                  <h4 className="font-medium">Pipeline by Mandate</h4>
                  <div className="space-y-3 max-h-64 overflow-y-auto">
                    {selectedCompany.mandates?.map((mandate) => (
                      <div key={mandate.id} className="p-3 bg-slate-50 rounded-lg">
                        <div className="flex items-center justify-between mb-2">
                          <p className="font-medium text-slate-800 text-sm">{mandate.title}</p>
                          <span className="text-xs text-green-600">{formatSalaryINR(mandate.total_revenue_closed)} closed</span>
                        </div>
                        <div className="flex gap-2 flex-wrap">
                          {Object.entries(mandate.stages).map(([stage, count]) => (
                            <span key={stage} className={`px-2 py-0.5 text-xs rounded ${
                              stage === 'hired' ? 'bg-green-100 text-green-700' :
                              stage === 'rejected' ? 'bg-red-100 text-red-700' :
                              stage === 'offered' ? 'bg-purple-100 text-purple-700' :
                              stage === 'interview' ? 'bg-blue-100 text-blue-700' :
                              stage === 'shortlisted' ? 'bg-amber-100 text-amber-700' :
                              'bg-slate-100 text-slate-600'
                            }`}>
                              {stage}: {count}
                            </span>
                          ))}
                        </div>
                        {/* Revenue by stage */}
                        <div className="flex gap-2 flex-wrap mt-2 text-xs">
                          {Object.entries(mandate.revenue_by_stage).filter(([, rev]) => rev > 0).map(([stage, rev]) => (
                            <span key={stage} className="text-slate-500">
                              {stage}: {formatSalaryINR(rev)}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
