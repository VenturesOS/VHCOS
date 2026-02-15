import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Checkbox } from '../../components/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
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
  Info,
  Sparkles,
  ShieldAlert,
  Paperclip,
  Building2,
  Briefcase,
  GraduationCap,
  MapPin,
  DollarSign,
  Phone,
  Mail,
  History
} from 'lucide-react';

const API_URL = '';

// Chunked upload configuration
const CHUNK_SIZE = 512 * 1024; // 512KB chunks (matches backend)
const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB max

export default function BulkImportPage() {
  const navigate = useNavigate();
  
  // Mode state
  const [activeMode, setActiveMode] = useState('excel');
  
  // File states
  const [excelFile, setExcelFile] = useState(null);
  const [zipFile, setZipFile] = useState(null);
  
  // Processing states
  const [isParsing, setIsParsing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [parseProgress, setParseProgress] = useState(0);
  const [saveProgress, setSaveProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState(''); // '', 'chunking', 'processing'
  
  // Result states
  const [batchId, setBatchId] = useState(null);
  const [parsedCandidates, setParsedCandidates] = useState([]);
  const [selectedCandidates, setSelectedCandidates] = useState(new Set());
  const [columnsFound, setColumnsFound] = useState([]);
  const [aiIndustryCount, setAiIndustryCount] = useState(0);
  const [saveResults, setSaveResults] = useState(null);
  
  // Dialog states
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [previewCandidate, setPreviewCandidate] = useState(null);
  
  // Get auth token
  const getToken = () => localStorage.getItem('vhc_token');

  // Format time remaining
  const formatTimeRemaining = (seconds) => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  // Chunked upload helper function with progress notifications
  const uploadFileInChunks = async (file) => {
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    const fileSizeMB = (file.size / (1024 * 1024)).toFixed(1);
    let startTime = Date.now();
    let chunkTimes = [];
    
    // Step 1: Initialize the upload
    setUploadPhase('chunking');
    toast.info(`Starting upload of ${fileSizeMB}MB file (${totalChunks} chunks)...`);
    
    const initResponse = await fetch(`${API_URL}/api/admin/bulk-import/chunk/init`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        filename: file.name,
        total_size: file.size,
        total_chunks: totalChunks
      })
    });
    
    if (!initResponse.ok) {
      const error = await initResponse.json();
      throw new Error(error.detail || 'Failed to initialize upload');
    }
    
    const { upload_id } = await initResponse.json();
    
    // Step 2: Upload each chunk with progress tracking
    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
      const chunkStartTime = Date.now();
      const start = chunkIndex * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);
      
      const formData = new FormData();
      formData.append('upload_id', upload_id);
      formData.append('chunk_index', chunkIndex.toString());
      formData.append('chunk', chunk, `chunk_${chunkIndex}`);
      
      const chunkResponse = await fetch(`${API_URL}/api/admin/bulk-import/chunk/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
        body: formData
      });
      
      if (!chunkResponse.ok) {
        const error = await chunkResponse.json();
        throw new Error(error.detail || `Failed to upload chunk ${chunkIndex + 1}`);
      }
      
      // Track chunk upload time for estimation
      const chunkTime = (Date.now() - chunkStartTime) / 1000;
      chunkTimes.push(chunkTime);
      
      // Calculate progress and ETA
      const chunkProgress = Math.round(((chunkIndex + 1) / totalChunks) * 60);
      setParseProgress(chunkProgress);
      
      // Show progress toast every 10 chunks or at certain milestones
      if ((chunkIndex + 1) % 10 === 0 || chunkIndex === totalChunks - 1) {
        const avgChunkTime = chunkTimes.reduce((a, b) => a + b, 0) / chunkTimes.length;
        const remainingChunks = totalChunks - (chunkIndex + 1);
        const uploadETA = remainingChunks * avgChunkTime;
        const processingETA = totalChunks * 2; // ~2 seconds per CV for AI parsing
        const totalETA = uploadETA + processingETA;
        
        const progressPercent = Math.round(((chunkIndex + 1) / totalChunks) * 100);
        
        if (chunkIndex < totalChunks - 1) {
          toast.info(`Upload progress: ${progressPercent}% • ETA: ~${formatTimeRemaining(totalETA)}`, {
            id: 'upload-progress',
            duration: 3000
          });
        }
      }
    }
    
    // Step 3: Complete the upload
    toast.success('Upload complete! Now processing CVs...', { id: 'upload-progress' });
    
    const completeResponse = await fetch(`${API_URL}/api/admin/bulk-import/chunk/complete?upload_id=${upload_id}`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${getToken()}` }
    });
    
    if (!completeResponse.ok) {
      const error = await completeResponse.json();
      throw new Error(error.detail || 'Failed to complete upload');
    }
    
    setParseProgress(65);
    return upload_id;
  };

  // Download template
  const handleDownloadTemplate = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/bulk-import/template`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (!response.ok) throw new Error('Failed to download template');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'bulk_import_template.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success('Template downloaded!');
    } catch (error) {
      toast.error('Failed to download template');
    }
  };

  // Handle Excel file selection
  const handleExcelChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const ext = file.name.split('.').pop().toLowerCase();
      if (!['xlsx', 'xls', 'csv'].includes(ext)) {
        toast.error('Please upload an Excel file (.xlsx, .xls) or CSV file');
        return;
      }
      setExcelFile(file);
      resetResults();
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
      resetResults();
    }
  };

  // Reset results
  const resetResults = () => {
    setParsedCandidates([]);
    setSelectedCandidates(new Set());
    setBatchId(null);
    setColumnsFound([]);
    setAiIndustryCount(0);
    setSaveResults(null);
  };

  // Parse Excel (Mode A)
  const handleParseExcel = async () => {
    if (!excelFile) {
      toast.error('Please upload an Excel file');
      return;
    }

    setIsParsing(true);
    setParseProgress(10);
    
    try {
      const formData = new FormData();
      formData.append('excel_file', excelFile);
      
      setParseProgress(30);
      
      const response = await fetch(`${API_URL}/api/admin/bulk-import/excel`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
        body: formData
      });
      
      setParseProgress(80);
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to parse Excel');
      }
      
      const data = await response.json();
      
      setBatchId(data.batch_id);
      setParsedCandidates(data.candidates);
      setColumnsFound(data.columns_found || []);
      setAiIndustryCount(data.ai_industry_detected || 0);
      
      // Auto-select valid candidates
      const validIds = new Set();
      data.candidates.forEach((c, idx) => {
        if (c.is_valid) validIds.add(idx);
      });
      setSelectedCandidates(validIds);
      
      setParseProgress(100);
      toast.success(`Parsed ${data.total_rows} candidates. ${data.valid_rows} valid, ${data.invalid_rows} with errors.`);
      
      if (data.ai_industry_detected > 0) {
        toast.info(`AI detected industry for ${data.ai_industry_detected} candidates`);
      }
      
    } catch (error) {
      toast.error(error.message);
    } finally {
      setIsParsing(false);
      setParseProgress(0);
    }
  };

  // Parse CV/ZIP (Mode B)
  const handleParseCVZip = async () => {
    if (!zipFile) {
      toast.error('Please upload a ZIP file');
      return;
    }

    // Check file size
    if (zipFile.size > MAX_FILE_SIZE) {
      toast.error(`File too large. Maximum size is ${MAX_FILE_SIZE / (1024 * 1024)}MB`);
      return;
    }

    setIsParsing(true);
    setParseProgress(5);
    setUploadPhase('');
    const startTime = Date.now();
    
    try {
      let data;
      
      // Use chunked upload for files > 1MB (to bypass proxy limits)
      if (zipFile.size > 1 * 1024 * 1024) {
        // Upload file in chunks (notifications handled in uploadFileInChunks)
        const upload_id = await uploadFileInChunks(zipFile);
        
        // Process the uploaded file
        setUploadPhase('processing');
        setParseProgress(70);
        
        toast.loading('AI is parsing your CVs... This may take a few minutes for large batches.', {
          id: 'cv-processing',
          duration: Infinity
        });
        
        const response = await fetch(`${API_URL}/api/admin/bulk-import/cv-zip-chunked?upload_id=${upload_id}`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${getToken()}` }
        });
        
        setParseProgress(90);
        
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to process CV/ZIP');
        }
        
        data = await response.json();
        toast.dismiss('cv-processing');
        
      } else {
        // Standard upload for small files
        const formData = new FormData();
        formData.append('zip_file', zipFile);
        
        setParseProgress(30);
        toast.loading('Processing CVs...', { id: 'cv-processing' });
        
        const response = await fetch(`${API_URL}/api/admin/bulk-import/cv-zip`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${getToken()}` },
          body: formData
        });
        
        setParseProgress(80);
        
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to parse CV/ZIP');
        }
        
        data = await response.json();
        toast.dismiss('cv-processing');
      }
      
      setBatchId(data.batch_id);
      setParsedCandidates(data.candidates);
      
      // Auto-select valid candidates
      const validIds = new Set();
      data.candidates.forEach((c, idx) => {
        if (c.is_valid) validIds.add(idx);
      });
      setSelectedCandidates(validIds);
      
      // Calculate processing time
      const totalTime = ((Date.now() - startTime) / 1000).toFixed(1);
      
      setParseProgress(100);
      toast.success(`✅ Processed ${data.total_files} CVs in ${totalTime}s • ${data.valid_files} valid, ${data.invalid_files} with errors`, {
        duration: 5000
      });
      
      if (data.excel_files_found > 0) {
        toast.info(`Found ${data.excel_files_found} Excel files with additional metadata`);
      }
      
    } catch (error) {
      toast.dismiss('cv-processing');
      toast.error(error.message);
    } finally {
      setIsParsing(false);
      setParseProgress(0);
      setUploadPhase('');
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
          candidatesToSave.push(c);
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
          mode: activeMode,
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
      
      toast.success(`Import complete! ${data.successful} saved, ${data.duplicates_merged} merged, ${data.failed} failed.`);
      
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
    resetResults();
  };

  // Stats
  const validCount = parsedCandidates.filter(c => c.is_valid).length;
  const invalidCount = parsedCandidates.length - validCount;
  const selectedValidCount = [...selectedCandidates].filter(idx => parsedCandidates[idx]?.is_valid).length;

  return (
    <div className="space-y-6" data-testid="bulk-import-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Enhanced Bulk Import</h1>
          <p className="text-slate-500 mt-1 text-sm">
            Two modes: Excel-Only or CV/ZIP
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={() => navigate('/admin/import-history')} data-testid="import-history-btn">
            <History className="w-4 h-4 mr-1 sm:mr-2" />
            <span className="hidden sm:inline">Import </span>History
          </Button>
          <Button variant="outline" size="sm" onClick={handleDownloadTemplate} data-testid="download-template-btn">
            <Download className="w-4 h-4 mr-1 sm:mr-2" />
            <span className="hidden sm:inline">Download </span>Template
          </Button>
        </div>
      </div>

      {/* Governance Notice */}
      <Card className="border-amber-200 bg-amber-50">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-amber-600 mt-0.5" />
            <div className="text-sm text-amber-800">
              <p className="font-medium mb-1">Strict Governance Rules</p>
              <ul className="list-disc list-inside space-y-1 text-amber-700">
                <li>All imported profiles are <strong>Admin-only</strong> by default</li>
                <li>Employers/Recruiters can only see them via <strong>AI Screening results</strong></li>
                <li>Permanent visibility granted only after <strong>&quot;Add as Applicant&quot;</strong> action</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Mode Selection Tabs */}
      <Tabs value={activeMode} onValueChange={(v) => { setActiveMode(v); handleReset(); }} className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="excel" data-testid="mode-excel-tab">
            <FileSpreadsheet className="w-4 h-4 mr-2" />
            Mode A: Excel-Only
          </TabsTrigger>
          <TabsTrigger value="cv_zip" data-testid="mode-cvzip-tab">
            <FolderArchive className="w-4 h-4 mr-2" />
            Mode B: CV/ZIP
          </TabsTrigger>
        </TabsList>

        {/* Excel-Only Mode */}
        <TabsContent value="excel" className="space-y-6">
          <Card className="border-blue-200 bg-blue-50">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-blue-600 mt-0.5" />
                <div className="text-sm text-blue-800">
                  <p className="font-medium mb-2">Excel-Only Mode</p>
                  <ul className="list-disc list-inside space-y-1 text-blue-700">
                    <li>Upload Excel with candidate data (no CV required)</li>
                    <li>Profiles created with <code className="bg-blue-100 px-1 rounded">cv_attached: false</code></li>
                    <li>CVs can be attached later using the &quot;Attach CV&quot; feature</li>
                    <li>If <strong>Industry</strong> column is empty, AI will detect it from employer name</li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Excel Upload */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-green-600" />
                Upload Excel File
              </CardTitle>
              <CardDescription>
                Required columns: Name*, Contact*, Email*, Work Exp*, Salary*, Location*, Employer*, Designation*, Education*, Industry*, DOB*
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
                  <div className="flex justify-between items-center">
                    <Button variant="ghost" size="sm" onClick={() => setExcelFile(null)}>
                      Remove file
                    </Button>
                    <Button
                      onClick={handleParseExcel}
                      disabled={isParsing}
                      className="bg-[#7CB342] hover:bg-[#689F38]"
                      data-testid="parse-excel-btn"
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
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* CV/ZIP Mode */}
        <TabsContent value="cv_zip" className="space-y-6">
          <Card className="border-purple-200 bg-purple-50">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-purple-600 mt-0.5" />
                <div className="text-sm text-purple-800">
                  <p className="font-medium mb-2">CV/ZIP Mode</p>
                  <ul className="list-disc list-inside space-y-1 text-purple-700">
                    <li>Upload ZIP containing resume files (PDF, DOC, DOCX)</li>
                    <li>Optionally include Excel files for additional metadata</li>
                    <li>CVs are parsed using AI to extract candidate data</li>
                    <li>Profiles created with <code className="bg-purple-100 px-1 rounded">cv_attached: true</code></li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ZIP Upload */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FolderArchive className="w-5 h-5 text-purple-600" />
                Upload ZIP File
              </CardTitle>
              <CardDescription>
                ZIP containing resume files (PDF, DOC, DOCX) and optional Excel files. Max size: 100MB.
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
                        <p className="text-xs text-slate-400">PDF, DOC, DOCX files + optional Excel</p>
                      </div>
                    )}
                  </label>
                </div>
                {zipFile && (
                  <div className="flex justify-between items-center">
                    <Button variant="ghost" size="sm" onClick={() => setZipFile(null)}>
                      Remove file
                    </Button>
                    <Button
                      onClick={handleParseCVZip}
                      disabled={isParsing}
                      className="bg-purple-600 hover:bg-purple-700"
                      data-testid="parse-cvzip-btn"
                    >
                      {isParsing ? (
                        <>
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          {uploadPhase === 'chunking' ? `Uploading... ${parseProgress}%` :
                           uploadPhase === 'processing' ? `Processing CVs... ${parseProgress}%` :
                           `Parsing CVs... ${parseProgress}%`}
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
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {isParsing && (
        <Progress value={parseProgress} className="h-2" />
      )}

      {/* AI Industry Detection Notice */}
      {aiIndustryCount > 0 && (
        <Card className="border-green-200 bg-green-50">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-green-800">
              <Sparkles className="w-5 h-5 text-green-600" />
              <span className="font-medium">
                AI detected industry for {aiIndustryCount} candidate(s) based on employer name
              </span>
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
                {activeMode === 'excel' 
                  ? 'Review parsed data. Missing mandatory fields will be marked as "Unknown".'
                  : 'Review AI-parsed data from CVs. Excel metadata will be merged if found.'
                }
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
                      {activeMode === 'excel' ? (
                        <>
                          <th className="p-2 text-left">Employer</th>
                          <th className="p-2 text-left">Industry</th>
                          <th className="p-2 text-left">Salary</th>
                        </>
                      ) : (
                        <>
                          <th className="p-2 text-left">Skills</th>
                          <th className="p-2 text-left">Exp</th>
                          <th className="p-2 text-left">CV</th>
                        </>
                      )}
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
                        <td className="p-2 font-medium">
                          {activeMode === 'excel' ? candidate.candidate_name : candidate.name || 'Unknown'}
                        </td>
                        <td className="p-2">{candidate.email || '-'}</td>
                        <td className="p-2">
                          {activeMode === 'excel' ? candidate.contact_no : candidate.phone || '-'}
                        </td>
                        
                        {activeMode === 'excel' ? (
                          <>
                            <td className="p-2 text-sm">{candidate.current_employer || '-'}</td>
                            <td className="p-2">
                              {candidate.industry ? (
                                <div className="flex items-center gap-1">
                                  <span>{candidate.industry}</span>
                                  {candidate.industry_source === 'ai_detected' && (
                                    <Badge variant="secondary" className="bg-green-100 text-green-700 text-xs">
                                      <Sparkles className="w-3 h-3 mr-1" /> AI
                                    </Badge>
                                  )}
                                </div>
                              ) : '-'}
                            </td>
                            <td className="p-2">{candidate.annual_salary || '-'}</td>
                          </>
                        ) : (
                          <>
                            <td className="p-2">
                              <div className="flex flex-wrap gap-1 max-w-xs">
                                {candidate.skills?.slice(0, 3).map((s, i) => (
                                  <Badge key={i} variant="secondary" className="text-xs">
                                    {s}
                                  </Badge>
                                ))}
                                {(candidate.skills?.length || 0) > 3 && (
                                  <Badge variant="outline" className="text-xs">
                                    +{candidate.skills.length - 3}
                                  </Badge>
                                )}
                              </div>
                            </td>
                            <td className="p-2">{candidate.experience_years || 0}y</td>
                            <td className="p-2">
                              {candidate.resume_file_id ? (
                                <Badge variant="secondary" className="bg-green-100 text-green-700">
                                  <FileText className="w-3 h-3 mr-1" /> OK
                                </Badge>
                              ) : (
                                <Badge variant="secondary" className="bg-red-100 text-red-700">
                                  Error
                                </Badge>
                              )}
                            </td>
                          </>
                        )}
                        
                        <td className="p-2">
                          {candidate.is_valid ? (
                            candidate.missing_mandatory?.length > 0 ? (
                              <Badge className="bg-amber-100 text-amber-700">
                                <AlertTriangle className="w-3 h-3 mr-1" />
                                Warnings
                              </Badge>
                            ) : (
                              <Badge className="bg-green-100 text-green-700">Valid</Badge>
                            )
                          ) : (
                            <Badge variant="destructive">Invalid</Badge>
                          )}
                        </td>
                        <td className="p-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setPreviewCandidate(candidate)}
                            data-testid={`preview-candidate-${idx}`}
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
              <div className="grid grid-cols-4 gap-4">
                <div className="p-4 bg-white rounded-lg text-center">
                  <p className="text-2xl sm:text-3xl font-bold text-slate-900">{saveResults.total_attempted}</p>
                  <p className="text-sm text-slate-500">Total Attempted</p>
                </div>
                <div className="p-4 bg-white rounded-lg text-center">
                  <p className="text-2xl sm:text-3xl font-bold text-green-600">{saveResults.successful}</p>
                  <p className="text-sm text-slate-500">Successful</p>
                </div>
                <div className="p-4 bg-white rounded-lg text-center">
                  <p className="text-2xl sm:text-3xl font-bold text-blue-600">{saveResults.duplicates_merged}</p>
                  <p className="text-sm text-slate-500">Merged</p>
                </div>
                <div className="p-4 bg-white rounded-lg text-center">
                  <p className="text-2xl sm:text-3xl font-bold text-red-600">{saveResults.failed}</p>
                  <p className="text-sm text-slate-500">Failed</p>
                </div>
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <p className="text-sm text-amber-800 font-medium">
                  <ShieldAlert className="w-4 h-4 inline mr-1" />
                  Reminder: All imported profiles are restricted to Admin view only until discovered via AI Screening.
                </p>
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
                        <tr key={i} className={`border-b ${r.status === 'failed' ? 'bg-red-50' : r.status === 'merged' ? 'bg-blue-50' : ''}`}>
                          <td className="p-2">{r.name}</td>
                          <td className="p-2">{r.email || '-'}</td>
                          <td className="p-2">
                            <Badge className={
                              r.status === 'failed' ? 'bg-red-100 text-red-700' : 
                              r.status === 'merged' ? 'bg-blue-100 text-blue-700' : 
                              'bg-green-100 text-green-700'
                            }>
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
                <Button onClick={handleReset} data-testid="new-import-btn">
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
                {activeMode === 'cv_zip' && <li>Upload CVs to Cloudflare R2 storage</li>}
                <li>Tag all records with batch ID: {batchId?.slice(0, 8)}...</li>
                <li>Mark profiles as <strong>Admin-only</strong> (restricted)</li>
                <li>Smart deduplication: merge existing candidates by email/phone</li>
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
              {/* Validation Errors */}
              {!previewCandidate.is_valid && previewCandidate.validation_errors?.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="font-medium text-red-800 mb-1">Validation Errors:</p>
                  <ul className="text-sm text-red-700 list-disc list-inside">
                    {previewCandidate.validation_errors.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
              )}
              
              {/* Warnings */}
              {previewCandidate.warnings?.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                  <p className="font-medium text-amber-800 mb-1">Warnings:</p>
                  <ul className="text-sm text-amber-700 list-disc list-inside">
                    {previewCandidate.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}

              {/* Missing Mandatory Fields */}
              {previewCandidate.missing_mandatory?.length > 0 && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                  <p className="font-medium text-blue-800 mb-1">Missing Mandatory (will be &quot;Unknown&quot;):</p>
                  <div className="flex flex-wrap gap-1">
                    {previewCandidate.missing_mandatory.map((f, i) => (
                      <Badge key={i} variant="secondary" className="bg-blue-100 text-blue-700">{f}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Candidate Data */}
              {activeMode === 'excel' ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Name:</span>
                      <span className="font-medium">{previewCandidate.candidate_name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Mail className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Email:</span>
                      <span>{previewCandidate.email || '-'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Phone className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Phone:</span>
                      <span>{previewCandidate.contact_no || '-'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <MapPin className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Location:</span>
                      <span>{previewCandidate.current_location || '-'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <DollarSign className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Salary:</span>
                      <span>{previewCandidate.annual_salary || '-'}</span>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Employer:</span>
                      <span>{previewCandidate.current_employer || '-'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Briefcase className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Designation:</span>
                      <span>{previewCandidate.designation || '-'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Industry:</span>
                      <span>{previewCandidate.industry || '-'}</span>
                      {previewCandidate.industry_source === 'ai_detected' && (
                        <Badge variant="secondary" className="bg-green-100 text-green-700 text-xs">AI</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <GraduationCap className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Education:</span>
                      <span>{previewCandidate.ug_course || '-'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Briefcase className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Experience:</span>
                      <span>{previewCandidate.work_exp || '-'}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Users className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-500">Name:</span>
                        <span className="font-medium">{previewCandidate.name || '-'}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Mail className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-500">Email:</span>
                        <span>{previewCandidate.email || '-'}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Phone className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-500">Phone:</span>
                        <span>{previewCandidate.phone || '-'}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-500">Location:</span>
                        <span>{previewCandidate.location || '-'}</span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Briefcase className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-500">Experience:</span>
                        <span>{previewCandidate.experience_years || 0} years</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-500">CV File:</span>
                        <span>{previewCandidate.filename || '-'}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-500">Headline:</span>
                        <span>{previewCandidate.headline || '-'}</span>
                      </div>
                    </div>
                  </div>
                  
                  {previewCandidate.skills?.length > 0 && (
                    <div>
                      <p className="text-sm text-slate-500 mb-2">Skills:</p>
                      <div className="flex flex-wrap gap-1">
                        {previewCandidate.skills.map((s, i) => (
                          <Badge key={i} variant="secondary">{s}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {previewCandidate.summary && (
                    <div>
                      <p className="text-sm text-slate-500 mb-1">Summary:</p>
                      <p className="text-sm bg-slate-50 p-2 rounded">{previewCandidate.summary}</p>
                    </div>
                  )}
                  
                  {previewCandidate.excel_data && (
                    <div className="border-t pt-4">
                      <p className="font-medium text-purple-800 mb-2">Additional Data from Excel:</p>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        {previewCandidate.excel_data.employer && (
                          <div><span className="text-slate-500">Employer:</span> {previewCandidate.excel_data.employer}</div>
                        )}
                        {previewCandidate.excel_data.designation && (
                          <div><span className="text-slate-500">Designation:</span> {previewCandidate.excel_data.designation}</div>
                        )}
                        {previewCandidate.excel_data.salary && (
                          <div><span className="text-slate-500">Salary:</span> ₹{previewCandidate.excel_data.salary?.toLocaleString()}</div>
                        )}
                        {previewCandidate.excel_data.location && (
                          <div><span className="text-slate-500">Location:</span> {previewCandidate.excel_data.location}</div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
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
