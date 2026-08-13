import { useState, useEffect, useCallback } from 'react';
import { linkedinAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { Linkedin, Link2, Send, History, Unplug, ExternalLink, CheckCircle2, XCircle, Loader2 } from 'lucide-react';

export default function LinkedInSettingsPage() {
  const [settings, setSettings] = useState({ auto_post_enabled: false, organization_id: '', connection: { connected: false } });
  const [postHistory, setPostHistory] = useState([]);
  const [organizations, setOrganizations] = useState([]);
  const [orgLoadError, setOrgLoadError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const loadOrganizations = useCallback(async () => {
    setOrgLoadError('');
    try {
      const res = await linkedinAPI.listOrganizations();
      setOrganizations(res.data.organizations || []);
    } catch (err) {
      const detail = err.response?.data?.detail || '';
      if (detail.includes('reconnect') || detail.includes('EXPIRED') || detail.includes('401')) {
        setOrgLoadError('Your LinkedIn token needs to be refreshed. Click Disconnect, then Connect LinkedIn again to grant the new company-page permissions.');
      } else {
        setOrgLoadError(detail || 'Could not fetch your LinkedIn Pages. Reconnect LinkedIn and try again.');
      }
      setOrganizations([]);
    }
  }, []);

  const loadData = useCallback(async () => {
    try {
      const [settingsRes, historyRes] = await Promise.all([
        linkedinAPI.getSettings(),
        linkedinAPI.getPostHistory(),
      ]);
      setSettings(settingsRes.data);
      setPostHistory(historyRes.data.posts || []);
      if (settingsRes.data.connection?.connected) {
        loadOrganizations();
      }
    } catch {
      toast.error('Failed to load LinkedIn settings');
    } finally {
      setLoading(false);
    }
  }, [loadOrganizations]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await linkedinAPI.updateSettings({
        auto_post_enabled: settings.auto_post_enabled,
        organization_id: settings.organization_id,
      });
      toast.success('LinkedIn settings saved');
    } catch {
      toast.error('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleConnect = async () => {
    try {
      const res = await linkedinAPI.authorize();
      window.open(res.data.authorization_url, '_blank', 'width=600,height=700');
      toast.info('Complete authorization in the popup window, then refresh this page.');
    } catch {
      toast.error('Failed to start LinkedIn authorization');
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await linkedinAPI.disconnect();
      setSettings(prev => ({ ...prev, connection: { connected: false } }));
      toast.success('LinkedIn disconnected');
    } catch {
      toast.error('Failed to disconnect');
    } finally {
      setDisconnecting(false);
    }
  };

  const handleTestPost = async () => {
    setTesting(true);
    try {
      await linkedinAPI.testPost();
      toast.success('Test post sent to LinkedIn!');
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Test post failed');
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;
  }

  const isConnected = settings.connection?.connected;
  const hasOrgId = settings.organization_id?.trim().length > 0;

  return (
    <div className="space-y-6" data-testid="linkedin-settings-page">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-[#0A66C2]/10">
          <Linkedin className="h-6 w-6 text-[#0A66C2]" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight" data-testid="page-title">LinkedIn Auto-Posting</h1>
          <p className="text-sm text-muted-foreground">Automatically share new blogs and job openings to your LinkedIn company page</p>
        </div>
      </div>

      {/* Connection Status */}
      <Card data-testid="connection-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Link2 className="h-4 w-4" />
            Connection Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {isConnected ? (
                <>
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                  <div>
                    <p className="font-medium text-green-700" data-testid="connection-status">Connected</p>
                    <p className="text-xs text-muted-foreground">
                      {settings.connection.profile_name && `${settings.connection.profile_name} · `}
                      Connected {settings.connection.connected_at ? new Date(settings.connection.connected_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' }) : ''}
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <XCircle className="h-5 w-5 text-red-400" />
                  <div>
                    <p className="font-medium text-red-600" data-testid="connection-status">Not Connected</p>
                    <p className="text-xs text-muted-foreground">Authorize LinkedIn to enable auto-posting</p>
                  </div>
                </>
              )}
            </div>
            {isConnected ? (
              <Button variant="outline" size="sm" onClick={handleDisconnect} disabled={disconnecting} data-testid="disconnect-btn">
                {disconnecting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Unplug className="h-4 w-4 mr-1" />}
                Disconnect
              </Button>
            ) : (
              <Button size="sm" onClick={handleConnect} className="bg-[#0A66C2] hover:bg-[#004182]" data-testid="connect-btn">
                <Linkedin className="h-4 w-4 mr-1" />
                Connect LinkedIn
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Auto-Posting Settings */}
      <Card data-testid="settings-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Auto-Posting Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <Label className="font-medium">Auto-post when a blog or job is published</Label>
              <p className="text-xs text-muted-foreground mt-0.5">New blogs and newly-activated jobs will be shared on your company page automatically</p>
            </div>
            <Switch
              checked={settings.auto_post_enabled}
              onCheckedChange={(val) => setSettings(prev => ({ ...prev, auto_post_enabled: val }))}
              data-testid="auto-post-toggle"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="org-id" className="font-medium">LinkedIn Company Page</Label>
            <p className="text-xs text-muted-foreground">
              Choose the Page to post to. Only Pages you administrate are listed.
            </p>

            {orgLoadError ? (
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2" data-testid="org-load-error">
                {orgLoadError}
              </div>
            ) : organizations.length > 0 ? (
              <select
                id="org-id"
                value={settings.organization_id || ''}
                onChange={(e) => setSettings(prev => ({ ...prev, organization_id: e.target.value }))}
                className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
                data-testid="org-id-select"
              >
                <option value="">— Select a Page —</option>
                {organizations.map((o) => (
                  <option key={o.urn} value={o.urn}>
                    {o.name}{o.vanity_name ? ` (@${o.vanity_name})` : ''} · id {o.id}
                  </option>
                ))}
              </select>
            ) : (
              <Input
                id="org-id"
                placeholder="urn:li:organization:12345678 or bare numeric ID"
                value={settings.organization_id || ''}
                onChange={(e) => setSettings(prev => ({ ...prev, organization_id: e.target.value }))}
                data-testid="org-id-input"
              />
            )}
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button onClick={handleSave} disabled={saving} data-testid="save-settings-btn">
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Save Settings
            </Button>
            <Button
              variant="outline"
              onClick={handleTestPost}
              disabled={testing || !isConnected || !hasOrgId}
              data-testid="test-post-btn"
            >
              {testing ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Send className="h-4 w-4 mr-1" />}
              Send Test Post
            </Button>
          </div>

          {!isConnected && (
            <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
              Connect your LinkedIn account first to enable auto-posting.
            </p>
          )}
        </CardContent>
      </Card>

      {/* RSS Feed Info */}
      <Card data-testid="rss-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <ExternalLink className="h-4 w-4" />
            RSS Feed (Alternative)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-3">
            You can also use LinkedIn's native RSS import. Add this URL in your Company Page Settings &gt; Add Source:
          </p>
          <div className="flex items-center gap-2">
            <Input value="https://ventureshrd.com/api/blog/rss" readOnly className="font-mono text-xs" data-testid="rss-url-input" />
            <Button
              variant="outline"
              size="sm"
              onClick={() => { navigator.clipboard.writeText('https://ventureshrd.com/api/blog/rss'); toast.success('RSS URL copied'); }}
              data-testid="copy-rss-btn"
            >
              Copy
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Post History */}
      <Card data-testid="history-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <History className="h-4 w-4" />
            Post History
            {postHistory.length > 0 && <Badge variant="secondary" className="text-xs">{postHistory.length}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {postHistory.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6" data-testid="no-history">No posts yet. Posts will appear here after auto-posting is enabled and a blog is published.</p>
          ) : (
            <div className="space-y-3" data-testid="history-list">
              {postHistory.map((post, i) => (
                <div key={i} className="flex items-start justify-between border rounded-lg px-4 py-3" data-testid={`history-item-${i}`}>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-sm truncate">{post.job_title || post.blog_title || 'Untitled'}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {post.job_id ? 'Job' : (post.blog_type || 'Blog')} · {new Date(post.posted_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
                      {post.author_type ? ` · ${post.author_type}` : ''}
                      {post.is_test && ' · Test'}
                    </p>
                  </div>
                  <Badge variant={post.status === 'success' ? 'default' : 'destructive'} className="ml-3 shrink-0 text-xs">
                    {post.status === 'success' ? 'Sent' : 'Failed'}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
