import { useState, useEffect, useCallback } from 'react';
import { seoDashboardAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import {
  FileText, Link2, AlertTriangle, Calendar, Camera,
  CheckCircle, XCircle, Info, Loader2
} from 'lucide-react';

const SEV_STYLES = {
  critical: 'bg-red-100 text-red-800 border-red-200',
  warning: 'bg-amber-100 text-amber-800 border-amber-200',
  info: 'bg-blue-100 text-blue-800 border-blue-200',
};

function StatusDot({ ok }) {
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${ok ? 'bg-green-500' : 'bg-red-500'}`} />;
}

function MetricCard({ icon: Icon, label, value, sub, status }) {
  const borderColor = status === 'red' ? 'border-red-400' : status === 'yellow' ? 'border-amber-400' : 'border-transparent';
  return (
    <Card className={`border-l-4 ${borderColor}`} data-testid={`seo-card-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <CardContent className="pt-5 pb-4 px-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{value ?? '—'}</p>
            {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
          </div>
          <div className="p-2 bg-gray-50 rounded-lg"><Icon className="w-5 h-5 text-gray-400" /></div>
        </div>
      </CardContent>
    </Card>
  );
}

function wordCountColor(wc) {
  if (wc < 1000) return 'text-red-600 font-bold';
  if (wc < 1200) return 'text-amber-600 font-semibold';
  return 'text-gray-900';
}
function metaColor(len, max) {
  if (len === 0) return 'text-red-600 font-bold';
  if (len > max) return 'text-amber-600';
  return 'text-gray-700';
}

export default function SEOMonitoringPage() {
  const [data, setData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [snapping, setSnapping] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [dashRes, alertRes, snapRes] = await Promise.all([
        seoDashboardAPI.getLive(),
        seoDashboardAPI.getAlerts(),
        seoDashboardAPI.getSnapshots(),
      ]);
      setData(dashRes.data);
      setAlerts(alertRes.data.alerts || []);
      setSnapshots(snapRes.data.snapshots || []);
    } catch {
      toast.error('Failed to load SEO dashboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleSnapshot = async () => {
    setSnapping(true);
    try {
      const res = await seoDashboardAPI.createSnapshot();
      toast.success(`Snapshot created. ${res.data.alerts_created} new alert(s).`);
      loadAll();
    } catch {
      toast.error('Snapshot failed');
    } finally {
      setSnapping(false);
    }
  };

  const handleResolve = async (id) => {
    try {
      await seoDashboardAPI.resolveAlert(id);
      setAlerts(prev => prev.map(a => a.id === id ? { ...a, status: 'resolved' } : a));
      toast.success('Alert resolved');
    } catch {
      toast.error('Failed to resolve alert');
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-7 h-7 animate-spin text-gray-400" /></div>;
  }

  const pm = data?.pillar_metrics || {};
  const bm = data?.blog_metrics || {};
  const il = data?.internal_linking || {};
  const ds = data?.digest_status || {};
  const th = data?.technical_health || {};
  const pillarCount = Object.values(pm).filter(Boolean).length;
  const activeAlerts = alerts.filter(a => a.status === 'active');

  return (
    <div className="space-y-8" data-testid="seo-monitoring-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">SEO Monitoring</h1>
          <p className="text-sm text-gray-500 mt-1">Content silo health, technical SEO, and alert management</p>
        </div>
        <Button onClick={handleSnapshot} disabled={snapping} data-testid="seo-snapshot-btn" className="gap-2">
          {snapping ? <Loader2 className="w-4 h-4 animate-spin" /> : <Camera className="w-4 h-4" />}
          {snapping ? 'Generating...' : 'Take Snapshot'}
        </Button>
      </div>

      {/* Section 1: Overview Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4" data-testid="seo-overview-cards">
        <MetricCard icon={FileText} label="Pillar Pages" value={pillarCount} sub="Published authority pages" />
        <MetricCard icon={FileText} label="Blog Posts" value={bm.total_posts} sub={`${bm.posts_last_30_days} in last 30 days`} />
        <MetricCard icon={Link2} label="Internal Links" value={il.total_links_detected} sub="Across all pillar pages" />
        <MetricCard icon={Calendar} label="Last Digest" value={ds.last_generated ? new Date(ds.last_generated).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' }) : 'Never'} status={ds.weeks_without_digest > 1 ? 'red' : undefined} />
        <MetricCard icon={AlertTriangle} label="Active Alerts" value={activeAlerts.length} status={activeAlerts.length > 0 ? 'yellow' : undefined} />
      </div>

      {/* Section 2: Pillar Authority Table */}
      <Card data-testid="seo-pillar-table">
        <CardHeader><CardTitle className="text-base">Pillar Authority</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <th className="pb-3 pr-4">Slug</th>
                <th className="pb-3 pr-4">Words</th>
                <th className="pb-3 pr-4">Links</th>
                <th className="pb-3 pr-4">FAQs</th>
                <th className="pb-3 pr-4">Title Len</th>
                <th className="pb-3 pr-4">Desc Len</th>
                <th className="pb-3 pr-4">JSON-LD</th>
                <th className="pb-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(pm).map(([slug, m]) => (
                <tr key={slug} className="border-b last:border-0" data-testid={`pillar-row-${slug}`}>
                  <td className="py-3 pr-4 font-medium text-gray-900">/{slug}</td>
                  <td className={`py-3 pr-4 ${m ? wordCountColor(m.word_count) : 'text-gray-400'}`}>{m?.word_count ?? '—'}</td>
                  <td className="py-3 pr-4 text-gray-700">{m?.internal_links ?? '—'}</td>
                  <td className="py-3 pr-4 text-gray-700">{m?.faq_count ?? '—'}</td>
                  <td className={`py-3 pr-4 ${m ? metaColor(m.meta_title_length, 60) : ''}`}>{m?.meta_title_length ?? '—'}</td>
                  <td className={`py-3 pr-4 ${m ? metaColor(m.meta_description_length, 160) : ''}`}>{m?.meta_description_length ?? '—'}</td>
                  <td className="py-3 pr-4">{m ? (m.has_json_ld ? <CheckCircle className="w-4 h-4 text-green-500" /> : <XCircle className="w-4 h-4 text-red-500" />) : '—'}</td>
                  <td className="py-3"><StatusDot ok={m?.status === 'published'} /> <span className="ml-1.5 text-xs">{m?.status ?? 'missing'}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Section 3: Technical Health */}
      <Card data-testid="seo-tech-health">
        <CardHeader><CardTitle className="text-base">Technical Health</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-6 text-sm">
            <div>
              <p className="text-xs text-gray-500 uppercase font-medium">Sitemap URLs</p>
              <p className="text-lg font-bold mt-1">{th.sitemap_count}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase font-medium">Duplicate Slugs</p>
              <p className={`text-lg font-bold mt-1 ${th.duplicate_slugs?.length ? 'text-red-600' : 'text-gray-900'}`}>{th.duplicate_slugs?.length || 0}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase font-medium">Orphan Pages</p>
              <p className={`text-lg font-bold mt-1 ${il.orphan_pages?.length ? 'text-red-600' : 'text-gray-900'}`}>{il.orphan_pages?.length || 0}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase font-medium">Missing Meta</p>
              <p className={`text-lg font-bold mt-1 ${th.missing_meta_pages?.length ? 'text-red-600' : 'text-gray-900'}`}>{th.missing_meta_pages?.length || 0}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase font-medium">Weeks Without Digest</p>
              <p className={`text-lg font-bold mt-1 ${ds.weeks_without_digest > 1 ? 'text-red-600' : 'text-gray-900'}`}>{ds.weeks_without_digest}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section 4: Alerts Panel */}
      <Card data-testid="seo-alerts-panel">
        <CardHeader><CardTitle className="text-base">SEO Alerts ({activeAlerts.length} active)</CardTitle></CardHeader>
        <CardContent>
          {alerts.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">No alerts. Take a snapshot to check for issues.</p>
          ) : (
            <div className="space-y-2">
              {alerts.map(a => (
                <div key={a.id} className={`flex items-center justify-between p-3 rounded-lg border text-sm ${a.status === 'resolved' ? 'opacity-50 bg-gray-50' : SEV_STYLES[a.severity] || 'bg-gray-50'}`} data-testid={`seo-alert-${a.id}`}>
                  <div className="flex items-center gap-3 min-w-0">
                    {a.severity === 'critical' ? <XCircle className="w-4 h-4 shrink-0" /> : a.severity === 'warning' ? <AlertTriangle className="w-4 h-4 shrink-0" /> : <Info className="w-4 h-4 shrink-0" />}
                    <span className="truncate">{a.message}</span>
                    {a.slug && <code className="text-xs bg-white/60 px-1.5 py-0.5 rounded shrink-0">{a.slug}</code>}
                  </div>
                  {a.status === 'active' && (
                    <Button variant="ghost" size="sm" onClick={() => handleResolve(a.id)} data-testid={`resolve-alert-${a.id}`} className="shrink-0 ml-2">
                      Resolve
                    </Button>
                  )}
                  {a.status === 'resolved' && <span className="text-xs text-gray-400 shrink-0 ml-2">Resolved</span>}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Section 5: Snapshot History */}
      <Card data-testid="seo-snapshot-history">
        <CardHeader><CardTitle className="text-base">Snapshot History</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          {snapshots.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">No snapshots yet. Click "Take Snapshot" to generate one.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  <th className="pb-3 pr-4">Date</th>
                  <th className="pb-3 pr-4">Internal Links</th>
                  <th className="pb-3 pr-4">Blog Posts</th>
                  <th className="pb-3 pr-4">Digest Status</th>
                  <th className="pb-3">Orphans</th>
                </tr>
              </thead>
              <tbody>
                {snapshots.map((s, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-3 pr-4 font-medium">{new Date(s.snapshot_date).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}</td>
                    <td className="py-3 pr-4">{s.internal_linking?.total_links_detected ?? '—'}</td>
                    <td className="py-3 pr-4">{s.blog_metrics?.total_posts ?? '—'}</td>
                    <td className="py-3 pr-4">{s.digest_status?.weeks_without_digest === 0 ? <span className="text-green-600">Current</span> : <span className="text-amber-600">{s.digest_status?.weeks_without_digest}w behind</span>}</td>
                    <td className="py-3">{s.internal_linking?.orphan_pages?.length || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
