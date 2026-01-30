import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Checkbox } from '../../components/ui/checkbox';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Progress } from '../../components/ui/progress';
import { toast } from 'sonner';
import {
  Upload,
  FileSpreadsheet,
  FolderArchive,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Download,
  Eye,
  Loader2,
  Users,
  FileText,
  Info
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function BulkImportPage() {
  // File states
  const [excelFile, setExcelFile] = useState(null);
  const [zipFile, setZipFile] = useState(null);
  
  // Processing states
  const [isParsing, setIsParsing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [parseProgress, setParseProgress] = useState(0);
  const [saveProgress, setSaveProgress] = useState(0);
  
  // Result states
  const [batchId, setBatchId] = useState(null);
  const [parsedCandidates, setParsedCandidates] = useState([]);
  const [selectedCandidates, setSelectedCandidates] = useState(new Set());
  const [globalErrors, setGlobalErrors] = useState([]);
  const [globalWarnings, setGlobalWarnings] = useState([]);
  const [saveResults, setSaveResults] = useState(null);
  
  // Dialog states
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [previewCandidate, setPreviewCandidate] = useState(null);
  
  // Get auth token
  const getToken = () => localStorage.getItem('vhc_token');

  // Download template
  const handleDownloadTemplate = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/bulk-import/template`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });
      
      if (!response.ok) throw new Error('Failed to download template');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'bulk_import_template.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      toast.error('Failed to download template');
    }
  };

  // Handle Excel file selection
  const handleExcelChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const validTypes = [
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/csv'
      ];
      const ext = file.name.split('.').pop().toLowerCase();
      if (!['xlsx', 'xls', 'csv'].includes(ext)) {
        toast.error('Please upload an Excel file (.xlsx, .xls) or CSV file');
        return;
      }
      setExcelFile(file);
      // Reset parsed data
      setParsedCandidates([]);
      setSelectedCandidates(new Set());
      setBatchId(null);
    }
  };

  // Handle ZIP file selection
  const handleZipChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.zip')) {
        toast.error('Please upload a ZIP file');
        return;
      }
      setZipFile(file);
      // Reset parsed data
      setParsedCandidates([]);
      setSelectedCandidates(new Set());
      setBatchId(null);
    }
  };

  // Parse files
  const handleParse = async () => {
    if (!excelFile || !zipFile) {
      toast.error('Please upload both Excel file and ZIP of resumes');
      return;
    }

    setIsParsing(true);
    setParseProgress(10);
    
    try {
      const formData = new FormData();
      formData.append('excel_file', excelFile);
      formData.append('resume_zip', zipFile);
      
      setParseProgress(30);
      
      const response = await fetch(`${API_URL}/api/admin/bulk-import/parse`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`
        },
        body: formData
      });
      
      setParseProgress(80);
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to parse files');
      }
      
      const data = await response.json();
      
      setBatchId(data.batch_id);
      setParsedCandidates(data.candidates);
      setGlobalErrors(data.global_errors || []);
      setGlobalWarnings(data.global_warnings || []);
      
      // Auto-select valid candidates
      const validIds = new Set();
      data.candidates.forEach((c, idx) => {
        if (c.is_valid) validIds.add(idx);
      });
      setSelectedCandidates(validIds);
      
      setParseProgress(100);
      toast.success(`Parsed ${data.total_rows} candidates. ${data.valid_rows} valid, ${data.invalid_rows} with errors.`);
      
    } catch (error) {
      toast.error(error.message);
    } finally {
      setIsParsing(false);
      setParseProgress(0);
    }
  };

  // Toggle candidate selection
  const toggleCandidate = (idx) => {
    const newSelected = new Set(selectedCandidates);
    if (newSelected.has(idx)) {
      newSelected.delete(idx);
    } else {
      newSelected.add(idx);
    }
    setSelectedCandidates(newSelected);
  };

  // Select all valid candidates
  const selectAllValid = () => {
    const validIds = new Set();
    parsedCandidates.forEach((c, idx) => {
      if (c.is_valid) validIds.add(idx);
    });
    setSelectedCandidates(validIds);
  };

  // Deselect all
  const deselectAll = () => {
    setSelectedCandidates(new Set());
  };

  // Open confirm dialog
  const handleOpenConfirm = () => {
    if (selectedCandidates.size === 0) {
      toast.error('Please select at least one candidate to import');
      return;
    }
    setShowConfirmDialog(true);
  };

  // Confirm and save
  const handleConfirmSave = async () => {
    setShowConfirmDialog(false);
    setIsSaving(true);
    setSaveProgress(10);
    
    try {
      const candidatesToSave = [];
      selectedCandidates.forEach(idx => {
        const c = parsedCandidates[idx];
        if (c && c.is_valid) {
          candidatesToSave.push({
            row_index: c.row_index,
            final_name: c.final_name,
            final_email: c.final_email,
            final_phone: c.final_phone,
            final_location: c.final_location,
            final_experience_years: c.final_experience_years,
            final_skills: c.final_skills,
            final_current_salary: c.final_current_salary,
            final_notice_period: c.final_notice_period,
            final_headline: c.final_headline,
            final_summary: c.final_summary,
            final_experience: c.final_experience,
            final_education: c.final_education,
            resume_file_id: c.resume_file_id,
            resume_fingerprint: c.resume_fingerprint,
            r2_metadata: c.r2_metadata,
            resume_filename: c.resume_filename
          });
        }
      });
      
      setSaveProgress(30);
      
      const response = await fetch(`${API_URL}/api/admin/bulk-import/save`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          batch_id: batchId,
          candidates: candidatesToSave
        })
      });
      
      setSaveProgress(80);
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to save candidates');
      }
      
      const data = await response.json();
      setSaveResults(data);
      setSaveProgress(100);
      
      toast.success(`Import complete! ${data.successful} saved, ${data.failed} failed.`);
      
    } catch (error) {
      toast.error(error.message);
    } finally {
      setIsSaving(false);
      setSaveProgress(0);
    }
  };

  // Reset form
  const handleReset = () => {
    setExcelFile(null);
    setZipFile(null);
    setParsedCandidates([]);
    setSelectedCandidates(new Set());
    setBatchId(null);
    setGlobalErrors([]);
    setGlobalWarnings([]);
    setSaveResults(null);
  };

  // Stats
  const validCount = parsedCandidates.filter(c => c.is_valid).length;
  const invalidCount = parsedCandidates.length - validCount;
  const selectedValidCount = [...selectedCandidates].filter(idx => parsedCandidates[idx]?.is_valid).length;

  return (
    <div className="space-y-6" data-testid="bulk-import-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Bulk Candidate Import</h1>
          <p className="text-slate-500 mt-1">
            Upload Excel + ZIP of resumes for controlled production-grade data seeding
          </p>
        </div>
        <Button variant="outline" onClick={handleDownloadTemplate}>
          <Download className="w-4 h-4 mr-2" />
          Download Template
        </Button>
      </div>

      {/* Instructions Card */}
      <Card className="border-blue-200 bg-blue-50">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-blue-600 mt-0.5" />
            <div className="text-sm text-blue-800">
              <p className="font-medium mb-2">How to use:</p>
              <ol className="list-decimal list-inside space-y-1 text-blue-700">
                <li>Download the Excel template and fill in candidate details</li>
                <li>Create a ZIP file containing all resume files (PDF, DOC, DOCX)</li>
                <li>Upload both files below and click &quot;Parse & Preview&quot;</li>
                <li>Review the merged data, then click &quot;Confirm & Save&quot;</li>
              </ol>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Upload Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Excel Upload */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileSpreadsheet className="w-5 h-5 text-green-600" />
              Excel/CSV File
            </CardTitle>
            <CardDescription>
              Contains candidate metadata (name, email, skills, etc.)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center hover:border-green-300 transition-colors">
                <input
                  type="file"
                  id="excel-upload"
                  className="hidden"
                  accept=".xlsx,.xls,.csv"
                  onChange={handleExcelChange}
                  data-testid="excel-file-input"
                />
                <label htmlFor="excel-upload" className="cursor-pointer">
                  {excelFile ? (
                    <div className="flex items-center justify-center gap-2 text-green-600">
                      <CheckCircle2 className="w-5 h-5" />
                      <span className="font-medium">{excelFile.name}</span>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Upload className="w-8 h-8 text-slate-400 mx-auto" />
                      <p className="text-slate-600">
                        <span className="text-green-600 font-medium">Click to upload</span> Excel/CSV
                      </p>
                      <p className="text-xs text-slate-400">Supports .xlsx, .xls, .csv</p>
                    </div>
                  )}
                </label>
              </div>
              {excelFile && (
                <Button variant="ghost" size="sm" onClick={() => setExcelFile(null)}>
                  Remove file
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* ZIP Upload */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FolderArchive className="w-5 h-5 text-purple-600" />
              Resume ZIP File
            </CardTitle>
            <CardDescription>
              Contains resume files matching resume_filename column
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center hover:border-purple-300 transition-colors">
                <input
                  type="file"
                  id="zip-upload"
                  className="hidden"
                  accept=".zip"
                  onChange={handleZipChange}
                  data-testid="zip-file-input"
                />
                <label htmlFor="zip-upload" className="cursor-pointer">
                  {zipFile ? (
                    <div className="flex items-center justify-center gap-2 text-purple-600">
                      <CheckCircle2 className="w-5 h-5" />
                      <span className="font-medium">{zipFile.name}</span>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Upload className="w-8 h-8 text-slate-400 mx-auto" />
                      <p className="text-slate-600">
                        <span className="text-purple-600 font-medium">Click to upload</span> ZIP
                      </p>
                      <p className="text-xs text-slate-400">PDF, DOC, DOCX files in ZIP</p>
                    </div>
                  )}
                </label>
              </div>
              {zipFile && (
                <Button variant="ghost" size="sm" onClick={() => setZipFile(null)}>
                  Remove file
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Parse Button */}
      {!parsedCandidates.length && (
        <div className="flex justify-center">
          <Button
            size="lg"
            onClick={handleParse}
            disabled={!excelFile || !zipFile || isParsing}
            className="bg-[#7CB342] hover:bg-[#689F38]"
            data-testid="parse-btn"
          >
            {isParsing ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Parsing... {parseProgress}%
              </>
            ) : (
              <>
                <Eye className="w-4 h-4 mr-2" />
                Parse &amp; Preview
              </>
            )}
          </Button>
        </div>
      )}

      {isParsing && (
        <Progress value={parseProgress} className="h-2" />
      )}

      {/* Global Warnings/Errors */}
      {globalWarnings.length > 0 && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="p-4">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5" />
              <div>
                <p className="font-medium text-amber-800">Warnings:</p>
                <ul className="text-sm text-amber-700 list-disc list-inside">
                  {globalWarnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {globalErrors.length > 0 && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-4">
            <div className="flex items-start gap-2">
              <XCircle className="w-5 h-5 text-red-600 mt-0.5" />
              <div>
                <p className="font-medium text-red-800">Errors:</p>
                <ul className="text-sm text-red-700 list-disc list-inside">
                  {globalErrors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results Section */}
      {parsedCandidates.length > 0 && !saveResults && (
        <>
          {/* Stats Bar */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-2">
                    <Users className="w-5 h-5 text-slate-600" />
                    <span className="font-medium">{parsedCandidates.length} Total</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-green-600" />
                    <span className="text-green-700">{validCount} Valid</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <XCircle className="w-5 h-5 text-red-600" />
                    <span className="text-red-700">{invalidCount} Invalid</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-blue-600" />
                    <span className="text-blue-700">{selectedValidCount} Selected</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={selectAllValid}>
                    Select All Valid
                  </Button>
                  <Button variant="outline" size="sm" onClick={deselectAll}>
                    Deselect All
                  </Button>
                  <Button variant="outline" size="sm" onClick={handleReset}>
                    Reset
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Candidates Table */}
          <Card>
            <CardHeader>
              <CardTitle>Preview Candidates</CardTitle>
              <CardDescription>
                Review the merged data before saving. Excel data takes priority.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="p-2 text-left w-10">
                        <Checkbox
                          checked={selectedCandidates.size === validCount && validCount > 0}
                          onCheckedChange={(checked) => checked ? selectAllValid() : deselectAll()}
                        />
                      </th>
                      <th className="p-2 text-left">Name</th>
                      <th className="p-2 text-left">Email</th>
                      <th className="p-2 text-left">Phone</th>
                      <th className="p-2 text-left">Location</th>
                      <th className="p-2 text-left">Exp</th>
                      <th className="p-2 text-left">Skills</th>
                      <th className="p-2 text-left">Resume</th>
                      <th className="p-2 text-left">Status</th>
                      <th className="p-2 text-left">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsedCandidates.map((candidate, idx) => (
                      <tr 
                        key={idx} 
                        className={`border-b hover:bg-slate-50 ${!candidate.is_valid ? 'bg-red-50' : ''}`}
                      >
                        <td className="p-2">
                          <Checkbox
                            checked={selectedCandidates.has(idx)}
                            disabled={!candidate.is_valid}
                            onCheckedChange={() => toggleCandidate(idx)}
                            data-testid={`select-candidate-${idx}`}
                          />
                        </td>
                        <td className="p-2 font-medium">{candidate.final_name}</td>
                        <td className="p-2">{candidate.final_email || '-'}</td>
                        <td className="p-2">{candidate.final_phone || '-'}</td>
                        <td className="p-2">{candidate.final_location || '-'}</td>
                        <td className="p-2">{candidate.final_experience_years || 0}y</td>
                        <td className="p-2">
                          <div className="flex flex-wrap gap-1 max-w-xs">
                            {candidate.final_skills?.slice(0, 3).map((s, i) => (
                              <Badge key={i} variant="secondary" className="text-xs">
                                {s}
                              </Badge>
                            ))}
                            {(candidate.final_skills?.length || 0) > 3 && (
                              <Badge variant="outline" className="text-xs">
                                +{candidate.final_skills.length - 3}
                              </Badge>
                            )}
                          </div>
                        </td>
                        <td className="p-2">
                          {candidate.resume_file_id ? (
                            <Badge variant="secondary" className="bg-green-100 text-green-700">
                              <FileText className="w-3 h-3 mr-1" /> Uploaded
                            </Badge>
                          ) : (
                            <Badge variant="secondary" className="bg-red-100 text-red-700">
                              Missing
                            </Badge>
                          )}
                        </td>
                        <td className="p-2">
                          {candidate.is_valid ? (
                            <Badge className="bg-green-100 text-green-700">Valid</Badge>
                          ) : (
                            <Badge variant="destructive">Invalid</Badge>
                          )}
                        </td>
                        <td className="p-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setPreviewCandidate(candidate)}
                          >
                            <Eye className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Confirm Button */}
          <div className="flex justify-center">
            <Button
              size="lg"
              onClick={handleOpenConfirm}
              disabled={selectedValidCount === 0 || isSaving}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="confirm-save-btn"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving... {saveProgress}%
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Confirm &amp; Save ({selectedValidCount} candidates)
                </>
              )}
            </Button>
          </div>

          {isSaving && (
            <Progress value={saveProgress} className="h-2" />
          )}
        </>
      )}

      {/* Save Results */}
      {saveResults && (
        <Card className="border-green-200 bg-green-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-green-800">
              <CheckCircle2 className="w-5 h-5" />
              Import Complete
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="p-4 bg-white rounded-lg text-center">
                  <p className="text-3xl font-bold text-slate-900">{saveResults.total_attempted}</p>
                  <p className="text-sm text-slate-500">Total Attempted</p>
                </div>
                <div className="p-4 bg-white rounded-lg text-center">
                  <p className="text-3xl font-bold text-green-600">{saveResults.successful}</p>
                  <p className="text-sm text-slate-500">Successful</p>
                </div>
                <div className="p-4 bg-white rounded-lg text-center">
                  <p className="text-3xl font-bold text-red-600">{saveResults.failed}</p>
                  <p className="text-sm text-slate-500">Failed</p>
                </div>
              </div>

              <div className="mt-4">
                <p className="font-medium mb-2">Results:</p>
                <div className="max-h-60 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-slate-100">
                        <th className="p-2 text-left">Name</th>
                        <th className="p-2 text-left">Email</th>
                        <th className="p-2 text-left">Status</th>
                        <th className="p-2 text-left">Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {saveResults.results.map((r, i) => (
                        <tr key={i} className={`border-b ${r.status === 'failed' ? 'bg-red-50' : ''}`}>
                          <td className="p-2">{r.name}</td>
                          <td className="p-2">{r.email || '-'}</td>
                          <td className="p-2">
                            <Badge className={r.status === 'failed' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}>
                              {r.status}
                            </Badge>
                          </td>
                          <td className="p-2 text-xs">{r.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="flex justify-center gap-4 mt-4">
                <Button onClick={handleReset}>
                  Start New Import
                </Button>
                <Button variant="outline" onClick={() => window.location.href = '/admin/candidate-bank'}>
                  Go to Candidate Bank
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Confirm Dialog */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Import</DialogTitle>
            <DialogDescription>
              You are about to import {selectedValidCount} candidate(s) to the Candidate Bank.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4 space-y-3">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
              <p className="text-sm text-amber-800">
                <strong>Important:</strong> This action will:
              </p>
              <ul className="text-sm text-amber-700 list-disc list-inside mt-2">
                <li>Save {selectedValidCount} candidate(s) to the Candidate Bank</li>
                <li>Upload resumes to Cloudflare R2 storage</li>
                <li>Tag all records with batch ID: {batchId?.slice(0, 8)}...</li>
                <li>Enable AI Screening for imported candidates</li>
              </ul>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConfirmDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleConfirmSave}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="final-confirm-btn"
            >
              Confirm &amp; Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Preview Candidate Dialog */}
      <Dialog open={!!previewCandidate} onOpenChange={() => setPreviewCandidate(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Candidate Details</DialogTitle>
          </DialogHeader>
          {previewCandidate && (
            <div className="space-y-4">
              {/* Validation Status */}
              {!previewCandidate.is_valid && previewCandidate.validation_errors?.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="font-medium text-red-800 mb-1">Validation Errors:</p>
                  <ul className="text-sm text-red-700 list-disc list-inside">
                    {previewCandidate.validation_errors.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
              )}
              
              {previewCandidate.warnings?.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                  <p className="font-medium text-amber-800 mb-1">Warnings:</p>
                  <ul className="text-sm text-amber-700 list-disc list-inside">
                    {previewCandidate.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}

              {/* Data Comparison */}
              <div className="grid grid-cols-2 gap-4">
                <div className="border rounded-lg p-3">
                  <p className="font-medium text-blue-800 mb-2">From Excel</p>
                  <dl className="text-sm space-y-1">
                    <div><dt className="text-slate-500 inline">Name:</dt> <dd className="inline">{previewCandidate.excel_name}</dd></div>
                    <div><dt className="text-slate-500 inline">Email:</dt> <dd className="inline">{previewCandidate.excel_email || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Phone:</dt> <dd className="inline">{previewCandidate.excel_phone || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Location:</dt> <dd className="inline">{previewCandidate.excel_location || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Exp:</dt> <dd className="inline">{previewCandidate.excel_experience_years ?? '-'} years</dd></div>
                    <div><dt className="text-slate-500 inline">Salary:</dt> <dd className="inline">{previewCandidate.excel_current_salary || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Notice:</dt> <dd className="inline">{previewCandidate.excel_notice_period || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Skills:</dt> <dd className="inline">{previewCandidate.excel_skills?.join(', ') || '-'}</dd></div>
                  </dl>
                </div>
                <div className="border rounded-lg p-3">
                  <p className="font-medium text-purple-800 mb-2">From Resume</p>
                  <dl className="text-sm space-y-1">
                    <div><dt className="text-slate-500 inline">Name:</dt> <dd className="inline">{previewCandidate.parsed_name || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Email:</dt> <dd className="inline">{previewCandidate.parsed_email || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Phone:</dt> <dd className="inline">{previewCandidate.parsed_phone || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Location:</dt> <dd className="inline">{previewCandidate.parsed_location || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Exp:</dt> <dd className="inline">{previewCandidate.parsed_experience_years ?? '-'} years</dd></div>
                    <div><dt className="text-slate-500 inline">Headline:</dt> <dd className="inline">{previewCandidate.parsed_headline || '-'}</dd></div>
                    <div><dt className="text-slate-500 inline">Skills:</dt> <dd className="inline">{previewCandidate.parsed_skills?.join(', ') || '-'}</dd></div>
                  </dl>
                </div>
              </div>

              {/* Final Merged Data */}
              <div className="border border-green-200 rounded-lg p-3 bg-green-50">
                <p className="font-medium text-green-800 mb-2">Final Merged Data (To Be Saved)</p>
                <dl className="text-sm space-y-1">
                  <div><dt className="text-slate-600 inline font-medium">Name:</dt> <dd className="inline">{previewCandidate.final_name}</dd></div>
                  <div><dt className="text-slate-600 inline font-medium">Email:</dt> <dd className="inline">{previewCandidate.final_email || '-'}</dd></div>
                  <div><dt className="text-slate-600 inline font-medium">Phone:</dt> <dd className="inline">{previewCandidate.final_phone || '-'}</dd></div>
                  <div><dt className="text-slate-600 inline font-medium">Location:</dt> <dd className="inline">{previewCandidate.final_location || '-'}</dd></div>
                  <div><dt className="text-slate-600 inline font-medium">Experience:</dt> <dd className="inline">{previewCandidate.final_experience_years} years</dd></div>
                  <div><dt className="text-slate-600 inline font-medium">Salary:</dt> <dd className="inline">{previewCandidate.final_current_salary || '-'}</dd></div>
                  <div><dt className="text-slate-600 inline font-medium">Notice:</dt> <dd className="inline">{previewCandidate.final_notice_period || '-'}</dd></div>
                  <div><dt className="text-slate-600 inline font-medium">Skills:</dt> <dd className="inline">{previewCandidate.final_skills?.join(', ') || '-'}</dd></div>
                  <div><dt className="text-slate-600 inline font-medium">Resume:</dt> <dd className="inline">{previewCandidate.resume_filename} {previewCandidate.resume_file_id ? '✓' : '✗'}</dd></div>
                </dl>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setPreviewCandidate(null)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
