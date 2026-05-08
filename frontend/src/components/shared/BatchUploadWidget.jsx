import { useBatchUpload } from '../../contexts/BatchUploadContext';
import { useNavigate } from 'react-router-dom';
import { Upload, Check, X, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

export function BatchUploadWidget() {
  const { tasks, isActive, stats } = useBatchUpload();
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();

  if (tasks.length === 0) return null;

  const pct = stats.total > 0 ? Math.round(((stats.completed + stats.failed) / stats.total) * 100) : 0;

  return (
    <div
      className="fixed bottom-4 right-4 z-50 w-80 bg-white rounded-xl shadow-2xl border border-slate-200 overflow-hidden"
      data-testid="batch-upload-widget"
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
        data-testid="batch-widget-header"
      >
        <div className="flex items-center gap-2">
          {isActive ? (
            <Loader2 className="w-4 h-4 text-[#7CB342] animate-spin" />
          ) : stats.failed > 0 ? (
            <X className="w-4 h-4 text-red-500" />
          ) : (
            <Check className="w-4 h-4 text-[#7CB342]" />
          )}
          <span className="text-sm font-medium text-slate-800">
            {isActive ? 'Uploading CVs...' : `Upload ${stats.failed > 0 ? 'finished with errors' : 'complete'}`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">{stats.completed + stats.failed}/{stats.total}</span>
          {expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronUp className="w-4 h-4 text-slate-400" />}
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-slate-100">
        <div
          className={`h-full transition-all duration-500 ${stats.failed > 0 ? 'bg-amber-500' : 'bg-[#7CB342]'}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Expanded file list */}
      {expanded && (
        <div className="max-h-48 overflow-y-auto divide-y divide-slate-100">
          {tasks.map((task) => (
            <div key={task.id} className="px-4 py-2 flex items-center gap-2 text-sm">
              <StatusIcon status={task.status} />
              <span className="truncate flex-1 text-slate-700" title={task.filename}>{task.filename}</span>
              <StatusLabel status={task.status} />
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      {!isActive && (
        <div className="px-4 py-2 bg-slate-50 border-t flex justify-between items-center">
          <button
            onClick={() => navigate('/admin/candidate-bank/batch-upload')}
            className="text-xs text-[#7CB342] hover:underline"
            data-testid="batch-widget-view-results"
          >
            View Results
          </button>
        </div>
      )}
    </div>
  );
}

function StatusIcon({ status }) {
  switch (status) {
    case 'completed': return <Check className="w-3.5 h-3.5 text-green-500 shrink-0" />;
    case 'failed': return <X className="w-3.5 h-3.5 text-red-500 shrink-0" />;
    case 'uploading':
    case 'parsing': return <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin shrink-0" />;
    default: return <Upload className="w-3.5 h-3.5 text-slate-300 shrink-0" />;
  }
}

function StatusLabel({ status }) {
  const styles = {
    queued: 'text-slate-400',
    uploading: 'text-blue-500',
    parsing: 'text-blue-500',
    completed: 'text-green-600',
    failed: 'text-red-500',
  };
  const labels = { queued: 'Queued', uploading: 'Uploading', parsing: 'Parsing...', completed: 'Done', failed: 'Failed' };
  return <span className={`text-xs ${styles[status] || 'text-slate-400'}`}>{labels[status] || status}</span>;
}
