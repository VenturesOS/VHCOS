import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { bulkImportAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { toast } from 'sonner';
import {
  History,
  FileSpreadsheet,
  FolderArchive,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Users,
  Search,
  Calendar,
  Loader2,
  ChevronRight,
  GitMerge,
  Eye,
  ArrowLeft,
  Sparkles,
  ShieldAlert
} from 'lucide-react';

const API_URL = '';

export default function ImportHistoryPage() {
  const navigate = useNavigate();
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchBatchId, setSearchBatchId] = useState('');
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [batchDetails, setBatchDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  useEffect(() => {
    loadBatches();
  }, []);

  const loadBatches = async () => {
    setLoading(true);
    try {
      const res = await bulkImportAPI.getBatches();
      setBatches(res.data.batches || []);
    } catch (error) {
      toast.error('Failed to load import history');
    } finally {
      setLoading(false);
    }
  };

  const loadBatchDetails = async (batchId) => {
    setLoadingDetails(true);
    try {
      const res = await bulkImportAPI.getBatchDetails(batchId);
      setBatchDetails(res.data);
      setSelectedBatch(batchId);
    } catch (error) {
      toast.error('Failed to load batch details');
    } finally {
      setLoadingDetails(false);
    }
  };

  // Filter batches by search
  const filteredBatches = batches.filter(batch => {
    if (!searchBatchId) return true;
    return batch.id.toLowerCase().includes(searchBatchId.toLowerCase());
  });

  // Stats
  const totalBatches = batches.length;
  const completedBatches = batches.filter(b => b.status === 'completed').length;
  const totalImported = batches.reduce((sum, b) => sum + (b.results?.successful || 0), 0);
  const totalMerged = batches.reduce((sum, b) => sum + (b.results?.duplicates_merged || 0), 0);

  return (
    <div className="space-y-6" data-testid="import-history-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3 sm:gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/admin/bulk-import')}>
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          <div>
            <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Import History</h1>
            <p className="text-slate-500 mt-1 text-sm">
              View past bulk import batches
            </p>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl sm:text-3xl font-bold text-slate-900">{totalBatches}</p>
            <p className="text-sm text-slate-500">Total Batches</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl sm:text-3xl font-bold text-green-600">{completedBatches}</p>
            <p className="text-sm text-slate-500">Completed</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl sm:text-3xl font-bold text-blue-600">{totalImported}</p>
            <p className="text-sm text-slate-500">Total Imported</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl sm:text-3xl font-bold text-purple-600">{totalMerged}</p>
            <p className="text-sm text-slate-500">Duplicates Merged</p>
          </CardContent>
        </Card>
      </div>

      {/* Search by Batch ID */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                value={searchBatchId}
                onChange={(e) => setSearchBatchId(e.target.value)}
                placeholder="Search by Batch ID..."
                className="pl-10"
                data-testid="search-batch-input"
              />
            </div>
            <Button variant="outline" onClick={() => setSearchBatchId('')}>
              Clear
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Batches List */}
      <Card>
        <CardHeader className="border-b border-slate-100 bg-slate-50/50">
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <History className="w-5 h-5 text-[#7CB342]" />
            Import Batches ({filteredBatches.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
          ) : filteredBatches.length === 0 ? (
            <div className="text-center py-12">
              <History className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500 mb-2">No import batches found</p>
              <p className="text-sm text-slate-400">Import candidates to see history here</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {filteredBatches.map((batch) => (
                <div
                  key={batch.id}
                  className="p-4 hover:bg-slate-50 transition-colors cursor-pointer"
                  onClick={() => loadBatchDetails(batch.id)}
                  data-testid={`batch-row-${batch.id}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      {/* Mode Icon */}
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        batch.mode === 'excel' ? 'bg-green-100' : 'bg-purple-100'
                      }`}>
                        {batch.mode === 'excel' ? (
                          <FileSpreadsheet className="w-5 h-5 text-green-600" />
                        ) : (
                          <FolderArchive className="w-5 h-5 text-purple-600" />
                        )}
                      </div>
                      
                      {/* Batch Info */}
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-slate-900">
                            Batch {batch.id.slice(0, 8)}...
                          </p>
                          <Badge variant={batch.status === 'completed' ? 'default' : 'secondary'} className={
                            batch.status === 'completed' ? 'bg-green-100 text-green-700' :
                            batch.status === 'pending_review' ? 'bg-amber-100 text-amber-700' :
                            'bg-slate-100 text-slate-600'
                          }>
                            {batch.status === 'completed' ? 'Completed' : 
                             batch.status === 'pending_review' ? 'Pending Review' : batch.status}
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            {batch.mode === 'excel' ? 'Excel-Only' : 'CV/ZIP'}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-4 text-sm text-slate-500 mt-1">
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {new Date(batch.created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })} {new Date(batch.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })}
                          </span>
                          <span>by {batch.created_by_name || 'Admin'}</span>
                        </div>
                      </div>
                    </div>
                    
                    {/* Stats */}
                    <div className="flex items-center gap-6">
                      {batch.status === 'completed' && batch.results && (
                        <>
                          <div className="text-center">
                            <p className="text-lg font-semibold text-green-600">{batch.results.successful || 0}</p>
                            <p className="text-xs text-slate-500">Imported</p>
                          </div>
                          <div className="text-center">
                            <p className="text-lg font-semibold text-blue-600">{batch.results.duplicates_merged || 0}</p>
                            <p className="text-xs text-slate-500">Merged</p>
                          </div>
                          <div className="text-center">
                            <p className="text-lg font-semibold text-red-600">{batch.results.failed || 0}</p>
                            <p className="text-xs text-slate-500">Failed</p>
                          </div>
                        </>
                      )}
                      {batch.status === 'pending_review' && (
                        <div className="text-center">
                          <p className="text-lg font-semibold text-amber-600">{batch.total_rows || batch.total_files || 0}</p>
                          <p className="text-xs text-slate-500">Awaiting Review</p>
                        </div>
                      )}
                      {batch.ai_industry_detected > 0 && (
                        <Badge variant="outline" className="text-green-600 border-green-300">
                          <Sparkles className="w-3 h-3 mr-1" />
                          {batch.ai_industry_detected} AI
                        </Badge>
                      )}
                      <ChevronRight className="w-5 h-5 text-slate-400" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Batch Details Dialog */}
      <Dialog open={!!selectedBatch} onOpenChange={() => { setSelectedBatch(null); setBatchDetails(null); }}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <History className="w-5 h-5 text-[#7CB342]" />
              Batch Details
            </DialogTitle>
          </DialogHeader>
          
          {loadingDetails ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
          ) : batchDetails && (
            <div className="space-y-4">
              {/* Batch Info */}
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-slate-500">Batch ID</p>
                    <p className="font-mono text-xs break-all">{batchDetails.id}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Mode</p>
                    <p className="font-medium flex items-center gap-1">
                      {batchDetails.mode === 'excel' ? (
                        <><FileSpreadsheet className="w-4 h-4 text-green-600" /> Excel-Only</>
                      ) : (
                        <><FolderArchive className="w-4 h-4 text-purple-600" /> CV/ZIP</>
                      )}
                    </p>
                  </div>
                  <div>
                    <p className="text-slate-500">Created At</p>
                    <p className="font-medium">{new Date(batchDetails.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Created By</p>
                    <p className="font-medium">{batchDetails.created_by_name || 'Admin'}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Status</p>
                    <Badge className={
                      batchDetails.status === 'completed' ? 'bg-green-100 text-green-700' :
                      batchDetails.status === 'pending_review' ? 'bg-amber-100 text-amber-700' :
                      'bg-slate-100 text-slate-600'
                    }>
                      {batchDetails.status}
                    </Badge>
                  </div>
                  {batchDetails.ai_industry_detected > 0 && (
                    <div>
                      <p className="text-slate-500">AI Industry Detection</p>
                      <p className="font-medium flex items-center gap-1 text-green-600">
                        <Sparkles className="w-4 h-4" /> {batchDetails.ai_industry_detected} candidates
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Results Summary */}
              {batchDetails.results && (
                <div className="grid grid-cols-4 gap-4">
                  <Card className="bg-slate-50">
                    <CardContent className="p-3 text-center">
                      <p className="text-2xl font-bold text-slate-700">
                        {batchDetails.total_rows || batchDetails.total_files || 0}
                      </p>
                      <p className="text-xs text-slate-500">Total Attempted</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-green-50">
                    <CardContent className="p-3 text-center">
                      <p className="text-2xl font-bold text-green-600">{batchDetails.results.successful || 0}</p>
                      <p className="text-xs text-green-700">Successful</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-blue-50">
                    <CardContent className="p-3 text-center">
                      <p className="text-2xl font-bold text-blue-600">{batchDetails.results.duplicates_merged || 0}</p>
                      <p className="text-xs text-blue-700">Merged</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-red-50">
                    <CardContent className="p-3 text-center">
                      <p className="text-2xl font-bold text-red-600">{batchDetails.results.failed || 0}</p>
                      <p className="text-xs text-red-700">Failed</p>
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Governance Reminder */}
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <div className="flex items-start gap-2">
                  <ShieldAlert className="w-5 h-5 text-amber-600 mt-0.5" />
                  <div className="text-sm text-amber-800">
                    <p className="font-medium">Governance Reminder</p>
                    <p className="text-amber-700">All imported candidates are Admin-only until discovered via AI Screening.</p>
                  </div>
                </div>
              </div>

              {/* Detailed Results */}
              {batchDetails.results?.details && (
                <div>
                  <h4 className="font-medium mb-2">Import Results</h4>
                  <div className="max-h-60 overflow-y-auto border rounded-lg">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-100 sticky top-0">
                        <tr>
                          <th className="p-2 text-left">Name</th>
                          <th className="p-2 text-left">Email</th>
                          <th className="p-2 text-left">Status</th>
                          <th className="p-2 text-left">Message</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batchDetails.results.details.map((r, i) => (
                          <tr key={i} className={`border-b ${
                            r.status === 'failed' ? 'bg-red-50' :
                            r.status === 'merged' ? 'bg-blue-50' :
                            ''
                          }`}>
                            <td className="p-2">{r.name}</td>
                            <td className="p-2 text-xs">{r.email || '-'}</td>
                            <td className="p-2">
                              <Badge className={
                                r.status === 'created' ? 'bg-green-100 text-green-700' :
                                r.status === 'merged' ? 'bg-blue-100 text-blue-700' :
                                'bg-red-100 text-red-700'
                              }>
                                {r.status === 'created' && <CheckCircle2 className="w-3 h-3 mr-1" />}
                                {r.status === 'merged' && <GitMerge className="w-3 h-3 mr-1" />}
                                {r.status === 'failed' && <XCircle className="w-3 h-3 mr-1" />}
                                {r.status}
                              </Badge>
                            </td>
                            <td className="p-2 text-xs text-slate-500">{r.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Candidates Preview (for pending batches) */}
              {batchDetails.candidates_preview && batchDetails.status === 'pending_review' && (
                <div>
                  <h4 className="font-medium mb-2">Candidates Preview</h4>
                  <div className="max-h-60 overflow-y-auto border rounded-lg">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-100 sticky top-0">
                        <tr>
                          <th className="p-2 text-left">Name</th>
                          <th className="p-2 text-left">Email</th>
                          <th className="p-2 text-left">Valid</th>
                          <th className="p-2 text-left">Issues</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batchDetails.candidates_preview.slice(0, 50).map((c, i) => (
                          <tr key={i} className={!c.is_valid ? 'bg-red-50' : ''}>
                            <td className="p-2">{c.candidate_name || c.name || 'Unknown'}</td>
                            <td className="p-2 text-xs">{c.email || '-'}</td>
                            <td className="p-2">
                              {c.is_valid ? (
                                <CheckCircle2 className="w-4 h-4 text-green-500" />
                              ) : (
                                <XCircle className="w-4 h-4 text-red-500" />
                              )}
                            </td>
                            <td className="p-2 text-xs text-slate-500">
                              {c.validation_errors?.join(', ') || c.warnings?.join(', ') || '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => { setSelectedBatch(null); setBatchDetails(null); }}>
              Close
            </Button>
            <Button onClick={() => navigate('/admin/candidate-bank')} className="bg-[#7CB342] hover:bg-[#689F38]">
              View Candidate Bank
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
