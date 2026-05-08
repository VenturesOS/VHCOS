import { useState, useEffect } from 'react';
import { settingsAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import { toast } from 'sonner';
import { Settings, Save, Shield, Bell, Zap } from 'lucide-react';

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    ai_parsing_enabled: true,
    email_notifications: true,
    max_applications_per_job: 100,
    resume_size_limit_mb: 5,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const res = await settingsAPI.get();
      setSettings(res.data);
    } catch (error) {
      toast.error('Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await settingsAPI.update(settings);
      toast.success('Settings saved successfully');
    } catch (error) {
      toast.error('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl" data-testid="settings-page">
      <div>
        <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Settings</h1>
        <p className="text-slate-500 mt-1">Configure platform settings</p>
      </div>

      {/* AI Features */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Zap className="w-5 h-5 text-[#7CB342]" />
            AI Features
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base">AI Resume Parsing</Label>
              <p className="text-sm text-slate-500">Automatically extract data from uploaded resumes</p>
            </div>
            <Switch
              checked={settings.ai_parsing_enabled}
              onCheckedChange={(checked) => setSettings({ ...settings, ai_parsing_enabled: checked })}
              data-testid="ai-parsing-toggle"
            />
          </div>
        </CardContent>
      </Card>

      {/* Notifications */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Bell className="w-5 h-5 text-[#7CB342]" />
            Notifications
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base">Email Notifications</Label>
              <p className="text-sm text-slate-500">Send email alerts for applications and updates</p>
            </div>
            <Switch
              checked={settings.email_notifications}
              onCheckedChange={(checked) => setSettings({ ...settings, email_notifications: checked })}
              data-testid="email-notifications-toggle"
            />
          </div>
        </CardContent>
      </Card>

      {/* Limits */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <Shield className="w-5 h-5 text-[#7CB342]" />
            Limits & Restrictions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Max Applications per Job</Label>
              <Input
                type="number"
                value={settings.max_applications_per_job}
                onChange={(e) =>
                  setSettings({ ...settings, max_applications_per_job: parseInt(e.target.value) || 0 })
                }
                data-testid="max-applications-input"
              />
            </div>
            <div className="space-y-2">
              <Label>Resume Size Limit (MB)</Label>
              <Input
                type="number"
                value={settings.resume_size_limit_mb}
                onChange={(e) =>
                  setSettings({ ...settings, resume_size_limit_mb: parseInt(e.target.value) || 0 })
                }
                data-testid="resume-size-input"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button
          onClick={handleSave}
          disabled={saving}
          className="bg-[#7CB342] hover:bg-[#689F38]"
          data-testid="save-settings-btn"
        >
          {saving ? (
            <div className="spinner w-4 h-4 border-2 border-white border-t-transparent mr-2" />
          ) : (
            <Save className="w-4 h-4 mr-2" />
          )}
          Save Settings
        </Button>
      </div>
    </div>
  );
}
