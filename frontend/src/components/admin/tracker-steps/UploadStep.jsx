import { useRef } from 'react';
import { trackerAPI } from '../../../lib/api';
import { toast } from 'sonner';
import { Upload, FileSpreadsheet, Loader2 } from 'lucide-react';

export default function UploadStep({ uploadFile, setUploadFile, uploadParsing, setUploadParsing, uploadMapping, setUploadMapping }) {
  const fileRef = useRef(null);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadFile(file);
    setUploadParsing(true);
    try {
      const res = await trackerAPI.parseTemplateFile(file);
      setUploadMapping(res.data);
      toast.success(`Parsed ${res.data.total_headers} columns, ${res.data.matched_count} auto-matched`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to parse file');
      setUploadFile(null);
    } finally { setUploadParsing(false); }
  };

  return (
    <div className="space-y-4" data-testid="step-upload">
      <p className="text-sm text-slate-600">Upload an Excel or CSV file to auto-detect column structure</p>
      <div
        className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-all"
        onClick={() => fileRef.current?.click()}
        data-testid="upload-dropzone"
      >
        <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleFile} className="hidden" />
        {uploadParsing ? (
          <Loader2 className="w-8 h-8 mx-auto text-blue-500 animate-spin" />
        ) : uploadFile ? (
          <>
            <FileSpreadsheet className="w-8 h-8 mx-auto text-emerald-500 mb-2" />
            <p className="text-sm font-medium text-slate-700">{uploadFile.name}</p>
            {uploadMapping && (
              <p className="text-xs text-emerald-600 mt-1">
                {uploadMapping.matched_count}/{uploadMapping.total_headers} columns auto-matched
              </p>
            )}
          </>
        ) : (
          <>
            <Upload className="w-8 h-8 mx-auto text-slate-300 mb-2" />
            <p className="text-sm text-slate-500">Click to upload .xlsx or .csv</p>
          </>
        )}
      </div>

      {uploadMapping?.sample_rows?.length > 0 && (
        <div className="overflow-x-auto">
          <p className="text-xs font-medium text-slate-500 mb-1.5">Sample Data Preview</p>
          <table className="w-full text-xs border border-slate-200 rounded">
            <thead>
              <tr className="bg-slate-50">
                {uploadMapping.headers.map((h, i) => (
                  <th key={i} className="px-2 py-1.5 text-left font-medium text-slate-600 border-b">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {uploadMapping.sample_rows.map((row, i) => (
                <tr key={i} className="border-b border-slate-100">
                  {row.map((cell, j) => (
                    <td key={j} className="px-2 py-1 text-slate-500 max-w-[120px] truncate">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

