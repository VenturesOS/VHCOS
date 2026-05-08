import { useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { bulkImportAPI } from '../../lib/api';
import { toast } from 'sonner';
import {
  Upload, FileSpreadsheet, Loader2, CheckCircle2, AlertTriangle,
  Users, XCircle, ArrowLeft, ChevronDown, ChevronUp, Eye,
  Mail, Phone, MapPin, Briefcase, GraduationCap, Clock,
  Tag, Star, CalendarDays, IndianRupee, Link2, UserCheck,
  AlertCircle, FileCheck,
} from 'lucide-react';

const API_URL = '';
function getToken() { return localStorage.getItem('vhc_token'); }

export default function BulkImportPage() {
  const navigate = useNavigate();
  const fileRef = useRef(null);

  // Upload state
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  // Parse results
  const [batchId, setBatchId] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [columnsFound, setColumnsFound] = useState([]);
  const [showColumns, setShowColumns] = useState(false);
  const [fileDetails, setFileDetails] = useState([]);

  // Save state
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState(null);
  const [saveProgress, setSaveProgress] = useState(null);

  // Preview dialog
  const [previewCandidate, setPreviewCandidate] = useState(null);

  const reset = () => {
    setFiles([]);
    setBatchId(null);
    setCandidates([]);
    setColumnsFound([]);
    setFileDetails([]);
    setSaveResult(null);
    setProgress(0);
    if (fileRef.current) fileRef.current.value = '';
  };

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || []);
    if (selected.length === 0) return;
    if (selected.length > 20) {
      toast.error('Maximum 20 files allowed per upload');
      return;
    }
    const valid = selected.filter(f => {
      const ext = f.name.toLowerCase();
      return ext.endsWith('.xlsx') || ext.endsWith('.xls') || ext.endsWith('.csv');
    });
    if (valid.length === 0) {
      toast.error('Please upload Excel (.xlsx, .xls) or CSV files');
      return;
    }
    if (valid.length < selected.length) {
      toast.warning(`${selected.length - valid.length} non-Excel file(s) were skipped`);
    }
    setFiles(valid);
    setSaveResult(null);
    setBatchId(null);
    setCandidates([]);
    setFileDetails([]);
  };

  const removeFile = (idx) => {
    setFiles(prev => prev.filter((_, i) => i !== idx));
  };

  const handleUploadAndParse = useCallback(async () => {
    if (files.length === 0) return;
    setUploading(true);
    setProgress(10);
    try {
      setProgress(30);
      const res = await bulkImportAPI.parseExcel(files);
      setProgress(90);
      const data = res.data;
      setBatchId(data.batch_id);
      setCandidates(data.candidates || []);
      setColumnsFound(data.columns_found || []);
      setFileDetails(data.file_details || []);
      if (data.ai_industry_detected > 0) {
        toast.info(`AI detected industry for ${data.ai_industry_detected} candidate(s)`);
      }
      const fileLabel = data.files_parsed > 1 ? ` from ${data.files_parsed} files` : '';
      toast.success(`Parsed ${data.total_rows} candidates (${data.valid_rows} valid)${fileLabel}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to parse Excel');
    } finally {
      setUploading(false);
      setProgress(100);
    }
  }, [files]);

  const handleSave = async () => {
    if (!batchId || candidates.length === 0) return;
    const validCandidates = candidates.filter(c => c.is_valid);
    if (validCandidates.length === 0) {
      toast.error('No valid candidates to import');
      return;
    }

    setSaving(true);
    setSaveProgress({ current: 0, total: validCandidates.length, successful: 0, merged: 0, failed: 0 });

    const CHUNK_SIZE = 50;
    const chunks = [];
    for (let i = 0; i < validCandidates.length; i += CHUNK_SIZE) {
      chunks.push(validCandidates.slice(i, i + CHUNK_SIZE));
    }

    let totalSuccessful = 0;
    let totalMerged = 0;
    let totalFailed = 0;
    let lastResults = [];

    try {
      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        const processed = i * CHUNK_SIZE;
        setSaveProgress(prev => ({ ...prev, current: processed, status: `Batch ${i + 1}/${chunks.length}...` }));

        try {
          const res = await bulkImportAPI.save(batchId, 'excel', chunk);
          totalSuccessful += res.data.successful || 0;
          totalMerged += res.data.duplicates_merged || 0;
          totalFailed += res.data.failed || 0;
          if (res.data.results) lastResults = [...lastResults, ...res.data.results];
        } catch (chunkErr) {
          totalFailed += chunk.length;
          toast.error(`Batch ${i + 1} failed: ${chunkErr.response?.data?.detail || 'Server error'}`);
        }
      }

      setSaveProgress(prev => ({ ...prev, current: validCandidates.length, successful: totalSuccessful, merged: totalMerged, failed: totalFailed, status: 'Complete' }));
      setSaveResult({ successful: totalSuccessful, duplicates_merged: totalMerged, failed: totalFailed, results: lastResults });
      toast.success(`Imported ${totalSuccessful} candidates, merged ${totalMerged}${totalFailed > 0 ? `, ${totalFailed} failed` : ''}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Import failed');
    } finally {
      setSaving(false);
    }
  };

  const validCount = candidates.filter(c => c.is_valid).length;
  const invalidCount = candidates.length - validCount;
  const hasNaukriData = candidates.some(c => c.naukri_data && Object.keys(c.naukri_data).length > 0);

  return (
    <div className="space-y-5" data-testid="naukri-import-page">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/admin/candidate-bank')} data-testid="back-btn">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight" style={{ fontFamily: 'Manrope, sans-serif' }}>
            Naukri Excel Import
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Upload Naukri job response Excel to add candidates with full profile data
          </p>
        </div>
      </div>

      {/* ══════ STEP 1: Upload ══════ */}
      {!batchId && !saveResult && (
        <Card className="border-2 border-dashed border-slate-200 hover:border-slate-300 transition-colors" data-testid="upload-section">
          <CardContent className="p-8">
            <div className="flex flex-col items-center text-center">
              <div className="p-4 rounded-2xl bg-blue-50 mb-4">
                <FileSpreadsheet className="w-10 h-10 text-blue-500" />
              </div>
              <h2 className="text-lg font-semibold text-slate-800 mb-1" style={{ fontFamily: 'Manrope, sans-serif' }}>
                Upload Naukri Excel
              </h2>
              <p className="text-sm text-slate-500 mb-4 max-w-md">
                Download candidate responses from Naukri, then upload Excel files here.
                Select up to 20 files at once — all candidates merge into one preview.
              </p>

              {files.length === 0 ? (
                <label
                  htmlFor="naukri-file"
                  className="cursor-pointer px-6 py-3 rounded-lg border-2 border-dashed border-blue-200 bg-blue-50/50 hover:bg-blue-50 transition-colors text-sm font-medium text-blue-700 flex items-center gap-2"
                  data-testid="file-drop-area"
                >
                  <Upload className="w-4 h-4" />
                  Choose Excel files (up to 20)
                  <input
                    id="naukri-file"
                    ref={fileRef}
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    multiple
                    onChange={handleFileChange}
                    className="hidden"
                    data-testid="file-input"
                  />
                </label>
              ) : (
                <div className="space-y-3 w-full max-w-lg">
                  <div className="space-y-2 max-h-60 overflow-y-auto">
                    {files.map((f, i) => (
                      <div key={i} className="flex items-center gap-3 p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                        <FileSpreadsheet className="w-4 h-4 text-green-600 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">{f.name}</p>
                          <p className="text-xs text-slate-400">{(f.size / 1024).toFixed(0)} KB</p>
                        </div>
                        <button onClick={() => removeFile(i)} className="text-slate-400 hover:text-red-500" data-testid={`remove-file-${i}`}>
                          <XCircle className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-slate-500">{files.length} file{files.length > 1 ? 's' : ''} selected</p>
                    <button onClick={reset} className="text-xs text-red-500 hover:text-red-700">Clear all</button>
                  </div>
                  <Button
                    onClick={handleUploadAndParse}
                    disabled={uploading}
                    className="w-full bg-blue-600 hover:bg-blue-700 gap-2"
                    data-testid="parse-btn"
                  >
                    {uploading ? (
                      <><Loader2 className="w-4 h-4 animate-spin" /> Parsing {files.length} file{files.length > 1 ? 's' : ''}... ({progress}%)</>
                    ) : (
                      <><FileCheck className="w-4 h-4" /> Parse & Preview {files.length > 1 ? `${files.length} Files` : ''}</>
                    )}
                  </Button>
                </div>
              )}

              <div className="mt-6 text-xs text-slate-400 max-w-lg">
                <p>Supported: <span className="font-medium">.xlsx, .xls, .csv</span></p>
                <p className="mt-1">Auto-detects: Name, Email, Phone, Skills, Experience, Education (UG/PG/Doctorate), Salary, Company, Designation, Notice Period, Location, Resume Headline, Summary, and 30+ more fields.</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ══════ STEP 2: Preview ══════ */}
      {batchId && !saveResult && (
        <>
          {/* Stats bar */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="parse-stats">
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="p-2 rounded-lg bg-blue-50"><Users className="w-5 h-5 text-blue-600" /></div>
                <div>
                  <p className="text-xl font-bold text-slate-900">{candidates.length}</p>
                  <p className="text-xs text-slate-500">Total Found</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="p-2 rounded-lg bg-emerald-50"><CheckCircle2 className="w-5 h-5 text-emerald-600" /></div>
                <div>
                  <p className="text-xl font-bold text-emerald-700">{validCount}</p>
                  <p className="text-xs text-slate-500">Valid</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="p-2 rounded-lg bg-red-50"><XCircle className="w-5 h-5 text-red-600" /></div>
                <div>
                  <p className="text-xl font-bold text-red-700">{invalidCount}</p>
                  <p className="text-xs text-slate-500">Invalid</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="p-2 rounded-lg bg-indigo-50"><Tag className="w-5 h-5 text-indigo-600" /></div>
                <div>
                  <p className="text-xl font-bold text-indigo-700">{columnsFound.length}</p>
                  <p className="text-xs text-slate-500">Columns Detected</p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* File breakdown (multi-file only) */}
          {fileDetails.length > 1 && (
            <div className="flex flex-wrap gap-2" data-testid="file-breakdown">
              {fileDetails.map((fd, i) => (
                <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                  <FileSpreadsheet className="w-3.5 h-3.5 text-blue-500" />
                  <span className="font-medium text-slate-700 truncate max-w-[180px]">{fd.filename}</span>
                  <Badge variant="secondary" className="text-[10px] px-1.5">{fd.rows} rows</Badge>
                  <span className="text-emerald-600 font-medium">{fd.valid} valid</span>
                </div>
              ))}
            </div>
          )}

          {/* Columns detected (collapsible) */}
          <button
            onClick={() => setShowColumns(!showColumns)}
            className="w-full flex items-center justify-between px-4 py-2.5 rounded-lg bg-slate-50 border border-slate-200 hover:bg-slate-100 transition-colors text-sm"
            data-testid="toggle-columns-btn"
          >
            <span className="font-medium text-slate-700">{columnsFound.length} columns auto-detected from your Excel</span>
            {showColumns ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>
          {showColumns && (
            <div className="flex flex-wrap gap-1.5 px-4 py-3 rounded-lg border border-slate-200 bg-white" data-testid="columns-list">
              {columnsFound.map((col, i) => (
                <span key={i} className="px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-600 font-mono">{col}</span>
              ))}
            </div>
          )}

          {/* Candidate list */}
          <Card data-testid="candidates-preview">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold text-slate-700">
                  Candidates Preview
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={reset} data-testid="reset-btn">
                    Upload New Files
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleSave}
                    disabled={saving || validCount === 0}
                    className="bg-[#7CB342] hover:bg-[#689F38] gap-1.5"
                    data-testid="import-btn"
                  >
                    {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserCheck className="w-4 h-4" />}
                    Import {validCount} Candidate{validCount !== 1 ? 's' : ''}
                  </Button>
                </div>
              </div>
            </CardHeader>
            {saving && saveProgress && (
              <div className="px-5 pb-3" data-testid="save-progress">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
                  <span>{saveProgress.status || 'Saving...'}</span>
                  <span>{saveProgress.current}/{saveProgress.total} candidates</span>
                </div>
                <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-[#7CB342] h-2 rounded-full transition-all duration-300"
                    style={{ width: `${Math.round((saveProgress.current / saveProgress.total) * 100)}%` }}
                  />
                </div>
                {saveProgress.current > 0 && (
                  <div className="flex gap-3 mt-1.5 text-xs">
                    <span className="text-emerald-600">{saveProgress.successful + saveProgress.merged} saved</span>
                    {saveProgress.merged > 0 && <span className="text-blue-600">{saveProgress.merged} merged</span>}
                    {saveProgress.failed > 0 && <span className="text-red-500">{saveProgress.failed} failed</span>}
                  </div>
                )}
              </div>
            )}
            <CardContent className="p-0">
              <div className="divide-y divide-slate-100">
                {candidates.map((c, i) => {
                  const nd = c.naukri_data || {};
                  return (
                    <div
                      key={i}
                      className={`px-4 py-3 hover:bg-slate-50 transition-colors ${!c.is_valid ? 'opacity-60 bg-red-50/30' : ''}`}
                      data-testid={`candidate-row-${i}`}
                    >
                      <div className="flex items-start gap-3">
                        {/* Status dot */}
                        <div className={`w-2 h-2 rounded-full mt-2 shrink-0 ${c.is_valid ? 'bg-emerald-500' : 'bg-red-500'}`} />

                        {/* Main info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-slate-800">{c.candidate_name || 'Unknown'}</span>
                            {c.designation && <span className="text-xs text-slate-500">{c.designation}</span>}
                            {c.current_employer && <span className="text-xs text-slate-400">at {c.current_employer}</span>}
                            {fileDetails.length > 1 && c.source_file && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] bg-violet-50 text-violet-600 font-medium truncate max-w-[120px]" title={c.source_file}>
                                {c.source_file.replace(/\.[^.]+$/, '').slice(0, 20)}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-500 flex-wrap">
                            {c.email && (
                              <span className="flex items-center gap-1"><Mail className="w-3 h-3 text-slate-400" />{c.email}</span>
                            )}
                            {c.contact_no && (
                              <span className="flex items-center gap-1"><Phone className="w-3 h-3 text-slate-400" />{c.contact_no}</span>
                            )}
                            {c.current_location && (
                              <span className="flex items-center gap-1"><MapPin className="w-3 h-3 text-slate-400" />{c.current_location}</span>
                            )}
                            {c.experience_years > 0 && (
                              <span className="flex items-center gap-1"><Briefcase className="w-3 h-3 text-slate-400" />{c.experience_years}y exp</span>
                            )}
                            {nd.notice_period && (
                              <span className="flex items-center gap-1"><Clock className="w-3 h-3 text-slate-400" />{nd.notice_period}</span>
                            )}
                          </div>

                          {/* Skills preview */}
                          {nd.key_skills && (
                            <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                              {nd.key_skills.split(',').slice(0, 5).map((s, j) => (
                                <span key={j} className="px-1.5 py-0.5 rounded text-[10px] bg-blue-50 text-blue-700 font-medium">{s.trim()}</span>
                              ))}
                              {nd.key_skills.split(',').length > 5 && (
                                <span className="text-[10px] text-slate-400">+{nd.key_skills.split(',').length - 5} more</span>
                              )}
                            </div>
                          )}

                          {/* Validation errors */}
                          {!c.is_valid && c.validation_errors?.length > 0 && (
                            <div className="flex items-center gap-1.5 mt-1.5">
                              <AlertTriangle className="w-3 h-3 text-red-500 shrink-0" />
                              <span className="text-[11px] text-red-600">{c.validation_errors.join(', ')}</span>
                            </div>
                          )}
                        </div>

                        {/* Education badge + preview btn */}
                        <div className="flex items-center gap-2 shrink-0">
                          {(c.ug_course || nd.pg_degree) && (
                            <div className="text-right">
                              {c.ug_course && <p className="text-[10px] text-slate-500">{c.ug_course}</p>}
                              {nd.pg_degree && <p className="text-[10px] text-indigo-600 font-medium">{nd.pg_degree}</p>}
                            </div>
                          )}
                          <Button
                            variant="ghost" size="sm"
                            onClick={() => setPreviewCandidate(c)}
                            className="text-slate-400 hover:text-blue-600"
                            data-testid={`preview-btn-${i}`}
                          >
                            <Eye className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Bottom import button */}
          <div className="flex justify-end">
            <Button
              onClick={handleSave}
              disabled={saving || validCount === 0}
              className="bg-[#7CB342] hover:bg-[#689F38] gap-1.5 px-6"
              data-testid="import-btn-bottom"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserCheck className="w-4 h-4" />}
              Import {validCount} Candidate{validCount !== 1 ? 's' : ''} to Bank
            </Button>
          </div>
        </>
      )}

      {/* ══════ STEP 3: Import Result ══════ */}
      {saveResult && (
        <Card data-testid="import-result">
          <CardContent className="p-8 text-center">
            <div className="inline-flex p-4 rounded-full bg-emerald-50 mb-4">
              <CheckCircle2 className="w-10 h-10 text-emerald-600" />
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-2" style={{ fontFamily: 'Manrope, sans-serif' }}>
              Import Complete
            </h2>
            <div className="grid grid-cols-3 gap-4 max-w-md mx-auto mt-4 mb-6">
              <div className="p-3 rounded-lg bg-emerald-50">
                <p className="text-2xl font-bold text-emerald-700">{saveResult.successful || 0}</p>
                <p className="text-xs text-emerald-600">Imported</p>
              </div>
              <div className="p-3 rounded-lg bg-blue-50">
                <p className="text-2xl font-bold text-blue-700">{saveResult.duplicates_merged || 0}</p>
                <p className="text-xs text-blue-600">Merged</p>
              </div>
              <div className="p-3 rounded-lg bg-amber-50">
                <p className="text-2xl font-bold text-amber-700">{saveResult.failed || 0}</p>
                <p className="text-xs text-amber-600">Failed</p>
              </div>
            </div>
            <div className="flex justify-center gap-3">
              <Button variant="outline" onClick={reset} data-testid="import-another-btn">
                Import Another File
              </Button>
              <Button
                onClick={() => navigate('/admin/candidate-bank')}
                className="bg-[#7CB342] hover:bg-[#689F38]"
                data-testid="go-to-bank-btn"
              >
                View Candidate Bank
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ══════ FULL PROFILE PREVIEW DIALOG ══════ */}
      <Dialog open={!!previewCandidate} onOpenChange={() => setPreviewCandidate(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="profile-preview-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2" style={{ fontFamily: 'Manrope, sans-serif' }}>
              <Eye className="w-5 h-5 text-blue-500" /> Candidate Profile Preview
            </DialogTitle>
          </DialogHeader>
          {previewCandidate && <CandidateProfilePreview candidate={previewCandidate} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ══════════════════════════════════════════════════════════
// Full Profile Preview Component
// ══════════════════════════════════════════════════════════

function CandidateProfilePreview({ candidate }) {
  const c = candidate;
  const nd = c.naukri_data || {};
  const skills = nd.key_skills ? nd.key_skills.split(',').map(s => s.trim()).filter(Boolean) : [];

  return (
    <div className="space-y-5" data-testid="candidate-profile-preview">
      {/* Header */}
      <div className="p-4 rounded-lg bg-gradient-to-r from-slate-50 to-blue-50 border border-slate-200">
        <h3 className="text-lg font-bold text-slate-900" style={{ fontFamily: 'Manrope, sans-serif' }}>
          {c.candidate_name}
        </h3>
        {nd.resume_headline && (
          <p className="text-sm text-slate-600 mt-0.5">{nd.resume_headline}</p>
        )}
        <div className="flex items-center gap-3 mt-2 text-xs text-slate-500 flex-wrap">
          {c.designation && (
            <span className="flex items-center gap-1"><Briefcase className="w-3.5 h-3.5" />{c.designation}</span>
          )}
          {c.current_employer && (
            <span className="font-medium text-slate-700">at {c.current_employer}</span>
          )}
          {c.current_location && (
            <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{c.current_location}</span>
          )}
          {c.experience_years > 0 && (
            <Badge variant="outline" className="text-[10px]">{c.experience_years} yrs exp</Badge>
          )}
        </div>
      </div>

      {/* Contact */}
      <div className="grid grid-cols-2 gap-3">
        {c.email && (
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-50">
            <Mail className="w-4 h-4 text-slate-400" />
            <div>
              <p className="text-[10px] text-slate-400">Email</p>
              <p className="text-xs font-medium text-slate-700">{c.email}</p>
            </div>
          </div>
        )}
        {c.contact_no && (
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-50">
            <Phone className="w-4 h-4 text-slate-400" />
            <div>
              <p className="text-[10px] text-slate-400">Phone</p>
              <p className="text-xs font-medium text-slate-700">{c.contact_no}</p>
            </div>
          </div>
        )}
        {nd.notice_period && (
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-50">
            <Clock className="w-4 h-4 text-slate-400" />
            <div>
              <p className="text-[10px] text-slate-400">Notice Period</p>
              <p className="text-xs font-medium text-slate-700">{nd.notice_period}</p>
            </div>
          </div>
        )}
        {c.salary_inr && (
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-50">
            <IndianRupee className="w-4 h-4 text-slate-400" />
            <div>
              <p className="text-[10px] text-slate-400">Annual Salary</p>
              <p className="text-xs font-medium text-slate-700">{(c.salary_inr / 100000).toFixed(1)} LPA</p>
            </div>
          </div>
        )}
      </div>

      {/* Skills */}
      {skills.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1.5">
            <Tag className="w-3.5 h-3.5" /> Skills
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {skills.map((s, i) => (
              <span key={i} className="px-2 py-0.5 rounded-md text-[11px] bg-blue-50 text-blue-700 font-medium border border-blue-100">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Summary */}
      {nd.summary && (
        <div>
          <h4 className="text-xs font-semibold text-slate-600 mb-1.5 flex items-center gap-1.5">
            <Star className="w-3.5 h-3.5" /> Summary
          </h4>
          <p className="text-xs text-slate-600 leading-relaxed bg-slate-50 rounded-lg p-3 whitespace-pre-line">
            {nd.summary}
          </p>
        </div>
      )}

      {/* Education */}
      {(c.ug_course || nd.pg_degree || nd.doc_degree) && (
        <div>
          <h4 className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1.5">
            <GraduationCap className="w-3.5 h-3.5" /> Education
          </h4>
          <div className="space-y-2">
            {nd.doc_degree && (
              <EduRow
                level="Doctorate"
                degree={nd.doc_degree}
                spec={nd.doc_specialization}
                uni={nd.doc_university}
                year={nd.doc_year}
                color="purple"
              />
            )}
            {nd.pg_degree && (
              <EduRow
                level="Post Graduate"
                degree={nd.pg_degree}
                spec={nd.pg_specialization}
                uni={nd.pg_university}
                year={nd.pg_year}
                color="indigo"
              />
            )}
            {c.ug_course && (
              <EduRow
                level="Under Graduate"
                degree={c.ug_course}
                spec={nd.ug_specialization}
                uni={nd.ug_university}
                year={nd.ug_year}
                color="blue"
              />
            )}
          </div>
        </div>
      )}

      {/* Additional Details */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        {nd.gender && <DetailRow label="Gender" value={nd.gender} />}
        {nd.home_town && <DetailRow label="Hometown" value={nd.home_town} />}
        {nd.preferred_locations && <DetailRow label="Preferred Locations" value={nd.preferred_locations} />}
        {nd.department && <DetailRow label="Department" value={nd.department} />}
        {nd.role_category && <DetailRow label="Role" value={nd.role_category} />}
        {c.industry && <DetailRow label="Industry" value={c.industry} />}
        {nd.naukri_job_title && <DetailRow label="Applied For" value={nd.naukri_job_title} />}
        {nd.application_date && <DetailRow label="Applied On" value={nd.application_date} />}
        {nd.candidate_source && <DetailRow label="Source" value={nd.candidate_source} />}
        {nd.work_permit_usa && <DetailRow label="USA Work Permit" value={nd.work_permit_usa} />}
      </div>

      {/* Naukri Profile Link */}
      {nd.candidate_profile && (
        <a
          href={nd.candidate_profile}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 p-3 rounded-lg bg-orange-50 border border-orange-200 text-sm text-orange-700 hover:bg-orange-100 transition-colors"
          data-testid="naukri-profile-link"
        >
          <Link2 className="w-4 h-4" />
          View on Naukri
        </a>
      )}
    </div>
  );
}

function EduRow({ level, degree, spec, uni, year, color }) {
  const colors = {
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    indigo: 'bg-indigo-50 border-indigo-200 text-indigo-700',
    purple: 'bg-purple-50 border-purple-200 text-purple-700',
  };
  return (
    <div className={`p-2.5 rounded-lg border ${colors[color] || colors.blue}`}>
      <div className="flex items-center justify-between">
        <div>
          <Badge variant="outline" className="text-[9px] mb-1">{level}</Badge>
          <p className="text-xs font-semibold">{degree}{spec ? ` — ${spec}` : ''}</p>
          {uni && <p className="text-[10px] opacity-75 mt-0.5">{uni}</p>}
        </div>
        {year && <span className="text-[10px] font-medium opacity-60">{year}</span>}
      </div>
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div className="p-2 rounded bg-slate-50">
      <span className="text-[10px] text-slate-400">{label}</span>
      <p className="text-xs text-slate-700 font-medium truncate">{value}</p>
    </div>
  );
}
