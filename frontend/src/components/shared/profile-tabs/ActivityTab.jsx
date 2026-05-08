import { Badge } from '../../ui/badge';

export default function ActivityTab({ activityHistory }) {
  return (
    <div className="space-y-4">
      {activityHistory?.summary && (
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-blue-50 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-blue-600">{activityHistory.summary.total_applications || 0}</p>
            <p className="text-xs text-blue-600">Total Applications</p>
          </div>
          <div className="bg-green-50 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-green-600">{activityHistory.summary.stages?.hired || 0}</p>
            <p className="text-xs text-green-600">Hired</p>
          </div>
          <div className="bg-amber-50 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-amber-600">{activityHistory.summary.stages?.interview || 0}</p>
            <p className="text-xs text-amber-600">Interviews</p>
          </div>
        </div>
      )}
      <div>
        <h4 className="font-semibold mb-2">Application History</h4>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {activityHistory?.applications?.map((app) => (
            <div key={app.application_id} className="p-3 bg-slate-50 rounded-lg text-sm border-l-4 border-[#7CB342]">
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-slate-800">{app.job_title}</span>
                <Badge className={
                  app.stage === 'hired' ? 'bg-green-100 text-green-700' :
                  app.stage === 'rejected' ? 'bg-red-100 text-red-700' :
                  app.stage === 'interview' ? 'bg-blue-100 text-blue-700' :
                  'bg-slate-100 text-slate-600'
                }>{app.stage}</Badge>
              </div>
              <p className="text-slate-500">{app.company_name}</p>
              <p className="text-xs text-slate-400 mt-1">
                Applied: {new Date(app.applied_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}
              </p>
            </div>
          ))}
          {(!activityHistory?.applications || activityHistory.applications.length === 0) && (
            <p className="text-slate-400 text-sm text-center py-4">No application history</p>
          )}
        </div>
      </div>
    </div>
  );
}
