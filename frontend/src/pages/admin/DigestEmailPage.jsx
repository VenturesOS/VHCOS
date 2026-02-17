import { useState, useEffect, useCallback } from 'react';
import { digestAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import {
  Mail, Send, Eye, Users, CheckCircle, XCircle,
  Loader2, Calendar, BarChart3, UserMinus, RefreshCw
} from 'lucide-react';

const SEGMENTS = [
  { key: 'employer', label: 'Employers' },
  { key: 'recruiter', label: 'Recruiters' },
  { key: 'candidate', label: 'Candidates' },
];

function StatCard({ icon: Icon, label, value, sub, color = 'gray' }) {
  const colors = {
    teal: 'bg-teal-50 text-teal-700',
    green: 'bg-green-50 text-green-700',
    red: 'bg-red-50 text-red-700',
    amber: 'bg-amber-50 text-amber-700',
    gray: 'bg-gray-50 text-gray-500',
  };
  return (
    <Card data-testid={`digest-stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <CardContent className="pt-5 pb-4 px-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{value ?? '—'}</p>
            {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
          </div>
          <div className={`p-2 rounded-lg ${colors[color]}`}><Icon className="w-5 h-5" /></div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function DigestEmailPage() {
  const [digests, setDigests] = useState([]);
  const [sendLogs, setSendLogs] = useState([]);
  const [subStats, setSubStats] = useState(null);
  const [selectedSegments, setSelectedSegments] = useState(['employer', 'recruiter', 'candidate']);
  const [recipientPreview, setRecipientPreview] = useState(null);
  const [emailPreview, setEmailPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [previewingEmail, setPreviewingEmail] = useState(false);
  const [previewingRecipients, setPreviewingRecipients] = useState(false);
  const [selectedDigest, setSelectedDigest] = useState(null);

  const loadAll = useCallback(async () => {
    try {
      const [dRes, lRes, sRes] = await Promise.all([
        digestAPI.list(),
        digestAPI.sendLogs(),
        digestAPI.subscriptionStats(),
      ]);
      setDigests(dRes.data.digests || []);
      setSendLogs(lRes.data.logs || []);
      setSubStats(sRes.data);
    } catch (e) {
      toast.error('Failed to load digest data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await digestAPI.trigger();
      if (res.data.status === 'success') {
        toast.success('Digest generated successfully');
      } else if (res.data.status === 'skipped') {
        toast.info(`Digest skipped: ${res.data.reason}`);
      } else {
        toast.error(`Generation issue: ${res.data.reason || 'Unknown'}`);
      }
      loadAll();
    } catch (e) {
      toast.error('Failed to generate digest');
    } finally {
      setGenerating(false);
    }
  };

  const handlePreviewEmail = async (weekKey) => {
    setPreviewingEmail(true);
    try {
      const res = await digestAPI.preview(weekKey);
      setEmailPreview(res.data);
    } catch (e) {
      toast.error('Failed to load preview');
    } finally {
      setPreviewingEmail(false);
    }
  };

  const handlePreviewRecipients = async () => {
    if (!selectedSegments.length) return toast.error('Select at least one segment');
    setPreviewingRecipients(true);
    try {
      const res = await digestAPI.recipients(selectedSegments.join(','));
      setRecipientPreview(res.data);
    } catch (e) {
      toast.error('Failed to load recipients');
    } finally {
      setPreviewingRecipients(false);
    }
  };

  const handleSend = async () => {
    if (!selectedSegments.length) return toast.error('Select at least one segment');
    const weekKey = selectedDigest || digests[0]?.week_key;
    if (!weekKey) return toast.error('No digest available to send');

    setSending(true);
    try {
      const res = await digestAPI.send(selectedSegments, weekKey);
      const d = res.data;
      if (d.status === 'completed') {
        toast.success(`Sent to ${d.success_count}/${d.total_recipients} recipients`);
      } else if (d.status === 'skipped') {
        toast.info(`Send skipped: ${d.reason}`);
      } else {
        toast.error('Send encountered issues');
      }
      loadAll();
      setRecipientPreview(null);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to send digest');
    } finally {
      setSending(false);
    }
  };

  const toggleSegment = (key) => {
    setSelectedSegments(prev =>
      prev.includes(key) ? prev.filter(s => s !== key) : [...prev, key]
    );
    setRecipientPreview(null);
  };

  const latestDigest = digests[0];
  const latestLog = sendLogs[0];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="digest-loading">
        <Loader2 className="w-6 h-6 animate-spin text-teal-600" />
        <span className="ml-2 text-gray-500">Loading digest data...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="digest-email-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Blog Digest Distribution</h1>
          <p className="text-sm text-gray-500 mt-1">Send weekly digests to segmented user groups</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadAll} data-testid="digest-refresh-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={handleGenerate} disabled={generating} data-testid="digest-generate-btn">
            {generating ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Calendar className="w-4 h-4 mr-1" />}
            Generate Digest
          </Button>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Mail} label="Total Digests" value={digests.length} color="teal" />
        <StatCard icon={Send} label="Total Sends" value={sendLogs.length} color="green" />
        <StatCard
          icon={CheckCircle} label="Last Send"
          value={latestLog ? `${latestLog.success_count}/${latestLog.total_recipients}` : 'None'}
          sub={latestLog?.completed_at ? new Date(latestLog.completed_at).toLocaleDateString() : ''}
          color="green"
        />
        <StatCard
          icon={UserMinus} label="Unsubscribed"
          value={subStats?.total_unsubscribed ?? 0}
          color={subStats?.total_unsubscribed > 0 ? 'amber' : 'gray'}
        />
      </div>

      {/* Send Panel */}
      <Card data-testid="digest-send-panel">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Send className="w-4 h-4 text-teal-600" /> Send Digest
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Digest Selector */}
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">Select Digest</label>
            <select
              className="w-full sm:w-80 border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
              value={selectedDigest || latestDigest?.week_key || ''}
              onChange={e => setSelectedDigest(e.target.value)}
              data-testid="digest-select"
            >
              {digests.map(d => (
                <option key={d.week_key} value={d.week_key}>
                  {d.week_key} — {d.title?.substring(0, 50)}{d.send_log ? ' (sent)' : ''}
                </option>
              ))}
              {!digests.length && <option value="">No digests available</option>}
            </select>
          </div>

          {/* Segment Selector */}
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1.5">Recipients</label>
            <div className="flex flex-wrap gap-2">
              {SEGMENTS.map(s => (
                <button
                  key={s.key}
                  onClick={() => toggleSegment(s.key)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                    selectedSegments.includes(s.key)
                      ? 'bg-teal-600 text-white border-teal-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                  }`}
                  data-testid={`digest-segment-${s.key}`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap gap-2 pt-2">
            <Button
              variant="outline" size="sm"
              onClick={() => handlePreviewEmail(selectedDigest || latestDigest?.week_key)}
              disabled={previewingEmail || !digests.length}
              data-testid="digest-preview-email-btn"
            >
              {previewingEmail ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Eye className="w-4 h-4 mr-1" />}
              Preview Email
            </Button>
            <Button
              variant="outline" size="sm"
              onClick={handlePreviewRecipients}
              disabled={previewingRecipients || !selectedSegments.length}
              data-testid="digest-preview-recipients-btn"
            >
              {previewingRecipients ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Users className="w-4 h-4 mr-1" />}
              Preview Recipients ({selectedSegments.length})
            </Button>
            <Button
              size="sm"
              onClick={handleSend}
              disabled={sending || !selectedSegments.length || !digests.length}
              className="bg-teal-600 hover:bg-teal-700"
              data-testid="digest-send-btn"
            >
              {sending ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Send className="w-4 h-4 mr-1" />}
              Send to {selectedSegments.length} Segment{selectedSegments.length !== 1 ? 's' : ''}
            </Button>
          </div>

          {/* Recipient Preview */}
          {recipientPreview && (
            <div className="mt-3 border rounded-lg overflow-hidden" data-testid="digest-recipient-list">
              <div className="bg-gray-50 px-4 py-2 text-sm font-medium text-gray-700 border-b flex justify-between">
                <span>Recipients ({recipientPreview.total})</span>
                <button onClick={() => setRecipientPreview(null)} className="text-gray-400 hover:text-gray-600 text-xs">Close</button>
              </div>
              <div className="max-h-48 overflow-y-auto divide-y">
                {recipientPreview.recipients?.map((r, i) => (
                  <div key={i} className="px-4 py-2 text-sm flex justify-between items-center">
                    <span className="text-gray-800">{r.name || 'No name'}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400 text-xs">{r.email}</span>
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">{r.role}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Email Preview */}
      {emailPreview && (
        <Card data-testid="digest-email-preview">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Eye className="w-4 h-4 text-teal-600" /> Email Preview — {emailPreview.week_key}
              </CardTitle>
              <button onClick={() => setEmailPreview(null)} className="text-sm text-gray-400 hover:text-gray-600">Close</button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="border rounded-lg overflow-hidden bg-gray-50">
              <iframe
                title="Email Preview"
                srcDoc={emailPreview.html}
                className="w-full border-0"
                style={{ minHeight: '600px' }}
                sandbox=""
                data-testid="digest-email-iframe"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Send History */}
      <Card data-testid="digest-send-history">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-teal-600" /> Send History
          </CardTitle>
        </CardHeader>
        <CardContent>
          {sendLogs.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">No sends yet</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500 text-xs uppercase tracking-wider">
                    <th className="py-2 pr-4">Week</th>
                    <th className="py-2 pr-4">Segments</th>
                    <th className="py-2 pr-4">Recipients</th>
                    <th className="py-2 pr-4">Success</th>
                    <th className="py-2 pr-4">Failed</th>
                    <th className="py-2">Sent At</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {sendLogs.map((log, i) => (
                    <tr key={i} className="hover:bg-gray-50" data-testid={`send-log-row-${i}`}>
                      <td className="py-2.5 pr-4 font-medium text-gray-800">{log.digest_week_key}</td>
                      <td className="py-2.5 pr-4">
                        <div className="flex flex-wrap gap-1">
                          {log.segments?.map(s => (
                            <span key={s} className="px-2 py-0.5 rounded-full text-xs bg-teal-50 text-teal-700">{s}</span>
                          ))}
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 text-gray-600">{log.total_recipients}</td>
                      <td className="py-2.5 pr-4">
                        <span className="flex items-center gap-1 text-green-600">
                          <CheckCircle className="w-3.5 h-3.5" /> {log.success_count}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4">
                        {log.failure_count > 0 ? (
                          <span className="flex items-center gap-1 text-red-600">
                            <XCircle className="w-3.5 h-3.5" /> {log.failure_count}
                          </span>
                        ) : (
                          <span className="text-gray-300">0</span>
                        )}
                      </td>
                      <td className="py-2.5 text-gray-400 text-xs">
                        {log.completed_at ? new Date(log.completed_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Digest List */}
      <Card data-testid="digest-list">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Calendar className="w-4 h-4 text-teal-600" /> Generated Digests
          </CardTitle>
        </CardHeader>
        <CardContent>
          {digests.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">No digests generated yet. Click "Generate Digest" to create one.</p>
          ) : (
            <div className="space-y-3">
              {digests.map(d => (
                <div
                  key={d.week_key}
                  className="border rounded-lg p-4 hover:border-teal-200 transition-colors"
                  data-testid={`digest-item-${d.week_key}`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-teal-700 bg-teal-50 px-2 py-0.5 rounded">{d.week_key}</span>
                        {d.send_log && (
                          <span className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" /> Sent
                          </span>
                        )}
                      </div>
                      <h3 className="text-sm font-semibold text-gray-900 truncate">{d.title}</h3>
                      <p className="text-xs text-gray-500 mt-1 line-clamp-2">{d.summary}</p>
                      <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                        <span>{d.blog_count || 0} blogs</span>
                        <span>{d.highlights?.length || 0} highlights</span>
                        {d.generated_at && <span>{new Date(d.generated_at).toLocaleDateString()}</span>}
                      </div>
                    </div>
                    <Button
                      variant="ghost" size="sm"
                      onClick={() => handlePreviewEmail(d.week_key)}
                      className="shrink-0 ml-3"
                      data-testid={`digest-preview-btn-${d.week_key}`}
                    >
                      <Eye className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
