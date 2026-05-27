import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Download, RefreshCw, Puzzle, Copy } from 'lucide-react';
import { toast } from 'sonner';
import api from '../../lib/api';

const fmtTime = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

const daysSince = (iso) => {
  if (!iso) return 9999;
  try { return (Date.now() - new Date(iso).getTime()) / 86400000; } catch { return 9999; }
};

export default function ExtensionVersionsPage() {
  const [stats, setStats] = useState(null);
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [s, i] = await Promise.all([
        api.get('/extension/version-stats'),
        api.get('/extension/latest-version'),
      ]);
      setStats(s.data);
      setInfo(i.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const copyId = () => {
    if (info?.extension_id) {
      navigator.clipboard.writeText(info.extension_id);
      toast.success('Extension ID copied');
    }
  };

  const downloadWebstoreZip = async () => {
    try {
      // Use the same axios instance so the JWT auth header is attached.
      // We need responseType:blob for binary zips.
      const res = await api.get('/extension/download-webstore-zip', { responseType: 'blob' });
      const cd = res.headers?.['content-disposition'] || '';
      const m = /filename="?([^"]+)"?/.exec(cd);
      const filename = m ? m[1] : `vhc-naukri-extension-webstore-v${info?.version || 'latest'}.zip`;
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Downloaded ${filename}`);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 404) {
        toast.error('No Web Store zip built yet. Run scripts/build_webstore_zip.py on EC2 first.');
      } else {
        toast.error(e?.response?.data?.detail || 'Download failed');
      }
    }
  };

  return (
    <div className="space-y-4" data-testid="extension-versions-page">
      {/* Installation info */}
      <Card>
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Puzzle className="w-4 h-4 text-purple-600" />
            Extension — Latest Release
          </CardTitle>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <div className="text-xs text-slate-500">Latest version</div>
              <div className="font-semibold">{info?.version || '—'}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500">CRX available</div>
              <div>
                {info?.crx_available ?
                  <Badge className="bg-green-100 text-green-800 border-green-300">YES (auto-update)</Badge> :
                  <Badge className="bg-amber-100 text-amber-800 border-amber-300">NO (zip only)</Badge>}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Total recruiters</div>
              <div className="font-semibold">{stats?.total_recruiters || 0}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Stale (&gt;7d)</div>
              <div className="font-semibold text-amber-700">{stats?.stale_over_7d || 0}</div>
            </div>
          </div>

          {info?.extension_id && (
            <div className="pt-3 border-t">
              <div className="text-xs text-slate-500 mb-1">Extension ID (stable — never changes)</div>
              <div className="flex items-center gap-2">
                <code className="bg-slate-100 px-2 py-1 rounded text-xs font-mono flex-1 truncate">{info.extension_id}</code>
                <Button size="sm" variant="outline" onClick={copyId}><Copy className="w-3 h-3" /></Button>
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-3 border-t">
            {info?.crx_url && (
              <a href={info.crx_url} download>
                <Button size="sm" className="bg-purple-600 hover:bg-purple-700">
                  <Download className="w-3.5 h-3.5 mr-1" /> Download CRX (auto-updating)
                </Button>
              </a>
            )}
            <a href={info?.zip_url || '/api/download/naukri-extension'} download>
              <Button size="sm" variant="outline">
                <Download className="w-3.5 h-3.5 mr-1" /> Download ZIP (manual install)
              </Button>
            </a>
            <a href="/api/extension/install-policy.reg" download>
              <Button size="sm" variant="outline" className="border-amber-400 text-amber-700">
                <Download className="w-3.5 h-3.5 mr-1" /> Windows Install Policy (.reg)
              </Button>
            </a>
            <Button
              size="sm"
              variant="outline"
              className="border-blue-400 text-blue-700 hover:bg-blue-50"
              onClick={downloadWebstoreZip}
              data-testid="download-webstore-zip-btn"
            >
              <Download className="w-3.5 h-3.5 mr-1" /> Download Web Store ZIP (for Chrome publish)
            </Button>
          </div>

          <div className="pt-3 border-t text-xs text-slate-600 leading-relaxed">
            <div className="font-semibold text-slate-700 mb-1">⚠️  First-time install on Windows</div>
            Chrome blocks self-hosted CRX installs by default (<code className="bg-slate-100 px-1 rounded">CRX_REQUIRED_PROOF_MISSING</code>).
            To enable <strong>drag-drop install + silent auto-updates</strong>:
            <ol className="list-decimal ml-5 mt-1 space-y-0.5">
              <li>Download the <strong>Windows Install Policy (.reg)</strong> file above</li>
              <li>Double-click the downloaded file → click "Yes" to merge into Registry</li>
              <li>Restart Chrome completely (close ALL Chrome windows, reopen)</li>
              <li>Now drag-drop the CRX into <code>chrome://extensions</code> (Developer mode ON) — it'll install and future updates happen silently</li>
            </ol>
            <div className="mt-2 italic text-slate-500">
              Prefer a one-time manual install? Use "Download ZIP" instead — no policy needed, but no auto-update.
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Version distribution */}
      {stats?.by_version?.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Version Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {stats.by_version.map((b) => {
                const isLatest = b.version === stats.latest_version;
                const pct = stats.total_recruiters ? (b.count / stats.total_recruiters * 100) : 0;
                return (
                  <div key={b.version} className="flex items-center gap-3">
                    <Badge className={isLatest ? 'bg-green-100 text-green-800 border-green-300' : 'bg-slate-100 text-slate-700'}>
                      v{b.version}
                    </Badge>
                    <div className="flex-1 h-2 bg-slate-100 rounded overflow-hidden">
                      <div
                        className={`h-full ${isLatest ? 'bg-green-500' : 'bg-slate-400'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-xs font-semibold w-16 text-right">{b.count} ({pct.toFixed(0)}%)</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* User table */}
      {stats?.users?.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Recruiters</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto border rounded">
              <table className="w-full text-xs">
                <thead className="bg-slate-100">
                  <tr>
                    <th className="text-left p-2">User</th>
                    <th className="text-left p-2">Role</th>
                    <th className="text-left p-2">Version</th>
                    <th className="text-left p-2">Install Type</th>
                    <th className="text-left p-2">Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.users.map((u) => {
                    const neverUsed = !u.last_seen;
                    const isLatest = !neverUsed && u.version === stats.latest_version;
                    const stale = !neverUsed && daysSince(u.last_seen) > 7;
                    return (
                      <tr key={u.user_id} className="border-b">
                        <td className="p-2">
                          <div className="font-medium">{u.user_name}</div>
                          <div className="text-slate-500 text-[10px]">{u.user_email}</div>
                        </td>
                        <td className="p-2"><Badge variant="outline" className="text-[10px]">{u.user_role}</Badge></td>
                        <td className="p-2">
                          {neverUsed ? (
                            <Badge className="text-[10px] bg-slate-100 text-slate-500 border-slate-300">
                              Not installed
                            </Badge>
                          ) : (
                            <Badge className={`text-[10px] ${isLatest ? 'bg-green-100 text-green-800 border-green-300' : 'bg-amber-100 text-amber-800 border-amber-300'}`}>
                              v{u.version}
                            </Badge>
                          )}
                        </td>
                        <td className="p-2 text-slate-600">{neverUsed ? '—' : u.install_type}</td>
                        <td className={`p-2 ${neverUsed ? 'text-slate-400 italic' : (stale ? 'text-red-600 font-medium' : 'text-slate-600')}`}>
                          {neverUsed ? 'Never used the extension' : fmtTime(u.last_seen)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
