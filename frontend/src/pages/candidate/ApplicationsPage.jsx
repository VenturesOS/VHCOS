import { useState, useEffect } from 'react';
import { applicationAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { toast } from 'sonner';
import { FileText, Briefcase, Clock, MapPin } from 'lucide-react';

export default function ApplicationsPage() {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadApplications();
  }, []);

  const loadApplications = async () => {
    try {
      const res = await applicationAPI.getAll();
      setApplications(res.data);
    } catch (error) {
      toast.error('Failed to load applications');
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

  return (
    <div className="space-y-6" data-testid="applications-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">My Applications</h1>
        <p className="text-slate-500 mt-1">Track your job applications</p>
      </div>

      <Card className="border-slate-200">
        <CardHeader className="border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <FileText className="w-5 h-5 text-[#7CB342]" />
            All Applications ({applications.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-slate-100">
            {applications.map((app) => (
              <div key={app.id} className="p-4 hover:bg-slate-50 transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-xl bg-[#DCFCE7] flex items-center justify-center shrink-0">
                      <Briefcase className="w-6 h-6 text-[#7CB342]" />
                    </div>
                    <div>
                      <h3 className="font-medium text-slate-900">{app.job_title}</h3>
                      <p className="text-sm text-slate-500">{app.company_name || 'Company'}</p>
                      <div className="flex items-center gap-2 mt-2 text-xs text-slate-400">
                        <Clock className="w-3 h-3" />
                        Applied {new Date(app.created_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                  <span className={`badge badge-${app.stage}`}>{app.stage}</span>
                </div>
                {app.notes?.length > 0 && (
                  <div className="mt-4 ml-16 p-3 bg-slate-50 rounded-lg">
                    <p className="text-xs text-slate-500 mb-1">Latest update:</p>
                    <p className="text-sm text-slate-600">
                      {app.notes[app.notes.length - 1].content}
                    </p>
                  </div>
                )}
              </div>
            ))}
            {applications.length === 0 && (
              <div className="p-8 text-center">
                <FileText className="w-12 h-12 text-slate-300 mx-auto mb-2" />
                <p className="text-slate-500">No applications yet</p>
                <p className="text-sm text-slate-400">Start applying to jobs to track them here</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
