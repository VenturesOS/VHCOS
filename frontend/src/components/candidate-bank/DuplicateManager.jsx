import { useState, useEffect } from 'react';
import { candidateBankAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../ui/dialog';
import { toast } from 'sonner';
import {
  Users, Mail, Phone, MapPin, AlertTriangle,
  Merge, Loader2, RefreshCw, ChevronDown, ChevronUp,
  Check, FileText, Calendar, Building2,
} from 'lucide-react';

function DuplicateGroup({ group, type, onMerge, merging }) {
  const [expanded, setExpanded] = useState(false);
  const candidates = group.candidates || [];
  const groupKey = group._id;

  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden" data-testid={`dup-group-${groupKey}`}>
      <div
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 bg-slate-50 hover:bg-slate-100 transition-colors text-left cursor-pointer"
        role="button"
        tabIndex={0}
        data-testid={`dup-group-toggle-${groupKey}`}
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            <span className="font-medium text-sm text-slate-900">
              {type === 'email' ? <Mail className="w-3.5 h-3.5 inline mr-1 text-slate-400" /> : <Phone className="w-3.5 h-3.5 inline mr-1 text-slate-400" />}
              {groupKey}
            </span>
          </div>
          <Badge variant="secondary" className="text-xs bg-amber-100 text-amber-700">
            {group.count} duplicates
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={(e) => { e.stopPropagation(); onMerge(candidates.map(c => c.id)); }}
            disabled={merging}
            className="bg-[#7CB342] hover:bg-[#689F38] text-xs h-7"
            data-testid={`merge-btn-${groupKey}`}
          >
            {merging ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Merge className="w-3 h-3 mr-1" />}
            Merge All
          </Button>
          {expanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </div>
      </div>

      {expanded && (
        <div className="divide-y divide-slate-100">
          {candidates.map((c, idx) => (
            <div key={c.id || idx} className="px-4 py-2.5 flex items-center gap-4 text-sm hover:bg-slate-50/50">
              <div className="w-8 h-8 rounded-full bg-[#7CB342]/10 text-[#7CB342] flex items-center justify-center text-xs font-bold flex-shrink-0">
                {(c.name || '?')[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-slate-900 truncate">{c.name || 'Unknown'}</p>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500 mt-0.5">
                  {c.email && <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{c.email}</span>}
                  {c.phone && <span className="flex items-center gap-1"><Phone className="w-3 h-3" />{c.phone}</span>}
                </div>
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-400 flex-shrink-0">
                {c.source && <Badge variant="outline" className="text-xs">{c.source}</Badge>}
                {c.created_at && <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{new Date(c.created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>}
              </div>
              {idx === 0 && (
                <Badge className="bg-blue-100 text-blue-700 text-xs flex-shrink-0">Master</Badge>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function DuplicateManager() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [merging, setMerging] = useState(null);
  const [confirmMerge, setConfirmMerge] = useState(null);
  const [activeTab, setActiveTab] = useState('email');
  const [mergingAll, setMergingAll] = useState(false);
  const [confirmMergeAll, setConfirmMergeAll] = useState(false);
  const [lastBulkResult, setLastBulkResult] = useState(null);

  const loadDuplicates = async () => {
    setLoading(true);
    try {
      const res = await candidateBankAPI.findAllDuplicates();
      setData(res.data);
    } catch {
      toast.error('Failed to load duplicates');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadDuplicates(); }, []);

  const handleMerge = async (ids) => {
    setMerging(ids[0]);
    try {
      const res = await candidateBankAPI.mergeDuplicates(ids);
      toast.success(res.data.message);
      loadDuplicates();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Merge failed');
    } finally {
      setMerging(null);
      setConfirmMerge(null);
    }
  };

  const handleMergeAll = async () => {
    setMergingAll(true);
    setConfirmMergeAll(false);
    try {
      const res = await candidateBankAPI.mergeAllDuplicates();
      setLastBulkResult(res.data);
      toast.success(res.data.message || 'Bulk merge complete');
      loadDuplicates();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bulk merge failed');
    } finally {
      setMergingAll(false);
    }
  };

  const emailGroups = data?.email_duplicates || [];
  const phoneGroups = data?.phone_duplicates || [];
  const totalGroups = emailGroups.length + phoneGroups.length;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16" data-testid="dup-loading">
        <Loader2 className="w-6 h-6 animate-spin text-[#7CB342] mr-2" />
        <span className="text-slate-500">Scanning for duplicates...</span>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="duplicate-manager">
      {/* Summary */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm">
            <Users className="w-4 h-4 text-amber-500" />
            <span className="font-medium text-slate-700">{totalGroups} duplicate groups found</span>
          </div>
          <div className="flex gap-1.5 text-xs text-slate-500">
            <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-600">{emailGroups.length} by email</span>
            <span className="px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">{phoneGroups.length} by phone</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {totalGroups > 0 && (
            <Button
              size="sm"
              onClick={() => setConfirmMergeAll(true)}
              disabled={loading || mergingAll || !!merging}
              className="bg-amber-600 hover:bg-amber-700 text-white"
              data-testid="merge-all-duplicates-btn"
            >
              {mergingAll ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Merge className="w-3.5 h-3.5 mr-1.5" />}
              Auto-merge All ({totalGroups})
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={loadDuplicates} disabled={loading || mergingAll} data-testid="refresh-duplicates">
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      {/* Bulk result banner */}
      {lastBulkResult && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm" data-testid="bulk-merge-result">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1">
              <p className="font-medium text-amber-900">Last bulk merge run</p>
              <p className="text-amber-800">{lastBulkResult.message}</p>
              <div className="flex flex-wrap gap-3 text-xs text-amber-700 pt-1">
                <span>Groups: {lastBulkResult.total_groups}</span>
                <span>Merged: {lastBulkResult.groups_merged}</span>
                <span>Candidates removed: {lastBulkResult.total_candidates_merged}</span>
                <span>Skipped: {lastBulkResult.groups_skipped}</span>
                {lastBulkResult.groups_failed > 0 && <span className="text-red-700">Failed: {lastBulkResult.groups_failed}</span>}
                {lastBulkResult.total_donors_flagged > 0 && <span>Flagged: {lastBulkResult.total_donors_flagged}</span>}
              </div>
            </div>
            <button
              onClick={() => setLastBulkResult(null)}
              className="text-amber-600 hover:text-amber-800 text-xs"
              data-testid="dismiss-bulk-result"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {totalGroups === 0 ? (
        <Card className="border-slate-200">
          <CardContent className="py-12 text-center">
            <Check className="w-10 h-10 text-green-500 mx-auto mb-3" />
            <p className="text-lg font-medium text-slate-700">No duplicates found</p>
            <p className="text-sm text-slate-500 mt-1">Your candidate database is clean.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Tab toggle */}
          <div className="flex gap-1 bg-slate-100 rounded-lg p-0.5 w-fit" data-testid="dup-tabs">
            <button
              onClick={() => setActiveTab('email')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'email' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
              data-testid="dup-tab-email"
            >
              <Mail className="w-3.5 h-3.5 inline mr-1.5" />
              Email ({emailGroups.length})
            </button>
            <button
              onClick={() => setActiveTab('phone')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'phone' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
              data-testid="dup-tab-phone"
            >
              <Phone className="w-3.5 h-3.5 inline mr-1.5" />
              Phone ({phoneGroups.length})
            </button>
          </div>

          {/* Groups list */}
          <div className="space-y-2" data-testid="dup-groups-list">
            {(activeTab === 'email' ? emailGroups : phoneGroups).map((group, idx) => (
              <DuplicateGroup
                key={group._id || idx}
                group={group}
                type={activeTab}
                merging={merging === group.candidates?.[0]?.id}
                onMerge={(ids) => setConfirmMerge({ ids, group })}
              />
            ))}
          </div>
        </>
      )}

      {/* Confirm merge dialog */}
      <Dialog open={!!confirmMerge} onOpenChange={() => setConfirmMerge(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Merge className="w-5 h-5 text-[#7CB342]" />
              Confirm Merge
            </DialogTitle>
            <DialogDescription>
              This will combine {confirmMerge?.ids?.length || 0} candidates into one record. The most recent and complete data will be kept. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          {confirmMerge?.group && (
            <div className="bg-slate-50 rounded-lg p-3 text-sm space-y-1">
              <p className="font-medium text-slate-700">Candidates to merge:</p>
              {confirmMerge.group.candidates?.map((c, i) => (
                <div key={i} className="text-slate-600 pl-2">
                  {i === 0 && <Badge className="bg-blue-100 text-blue-700 text-xs mr-1.5">Master</Badge>}
                  {c.name || 'Unknown'} - {c.email || c.phone}
                </div>
              ))}
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setConfirmMerge(null)} data-testid="cancel-merge">Cancel</Button>
            <Button
              onClick={() => handleMerge(confirmMerge.ids)}
              disabled={!!merging}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="confirm-merge-btn"
            >
              {merging ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Merge className="w-4 h-4 mr-1.5" />}
              Merge {confirmMerge?.ids?.length || 0} Candidates
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirm Merge All dialog */}
      <Dialog open={confirmMergeAll} onOpenChange={(open) => !mergingAll && setConfirmMergeAll(open)}>
        <DialogContent className="max-w-md" data-testid="confirm-merge-all-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              Auto-merge ALL duplicates?
            </DialogTitle>
            <DialogDescription>
              This will run the merge logic on every duplicate group ({totalGroups} groups,
              {' '}{emailGroups.length} by email + {phoneGroups.length} by phone).
              Each group only merges if donors pass the 2-of-3 safety gate (name + email + phone).
              Weak matches stay flagged for manual review. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
            <p className="font-medium mb-1">Safety guards in place:</p>
            <ul className="list-disc list-inside text-xs space-y-0.5">
              <li>Donors needing ≥2 of (name, email, phone) match the master</li>
              <li>The most recent + complete record is kept as master</li>
              <li>All associated applications are re-pointed to the master</li>
              <li>Groups that overlap (same person in both email + phone) merge once</li>
            </ul>
          </div>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setConfirmMergeAll(false)}
              disabled={mergingAll}
              data-testid="cancel-merge-all"
            >
              Cancel
            </Button>
            <Button
              onClick={handleMergeAll}
              disabled={mergingAll}
              className="bg-amber-600 hover:bg-amber-700 text-white"
              data-testid="confirm-merge-all-btn"
            >
              {mergingAll ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Merge className="w-4 h-4 mr-1.5" />}
              Yes, merge all {totalGroups} groups
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
