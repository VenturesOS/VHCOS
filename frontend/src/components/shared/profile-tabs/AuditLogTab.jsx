export default function AuditLogTab({ auditLog }) {
  return (
    <div className="space-y-2 max-h-80 overflow-y-auto">
      {auditLog.length > 0 ? (
        auditLog.map((log, i) => (
          <div key={`audit-${log.field_changed}-${i}`} className="p-3 bg-slate-50 rounded-lg text-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium text-slate-700">{log.field_changed}</span>
              <span className="text-xs text-slate-400">
                {new Date(log.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
              </span>
            </div>
            <p className="text-slate-500">
              <span className="text-red-500 line-through">{log.old_value || 'null'}</span>
              {' → '}
              <span className="text-green-600">{log.new_value}</span>
            </p>
            <p className="text-xs text-slate-400 mt-1">By {log.updated_by_name} ({log.updated_by_role})</p>
          </div>
        ))
      ) : (
        <p className="text-slate-400 text-sm text-center py-8">No audit history</p>
      )}
    </div>
  );
}
