import { useState, useEffect } from 'react';
import { notificationAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Switch } from '../../components/ui/switch';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import { Bell, Save, Loader2 } from 'lucide-react';

const PREF_LABELS = [
  { key: 'new_application', label: 'New Applications', desc: 'When someone applies to your job' },
  { key: 'status_change', label: 'Status Changes', desc: 'When your application stage changes' },
  { key: 'job_posted', label: 'Job Posted', desc: 'When a new job is posted' },
  { key: 'job_assigned', label: 'Job Assigned', desc: 'When a job is assigned to you' },
  { key: 'candidate_assigned', label: 'Candidate Assigned', desc: 'When a candidate is assigned to you' },
  { key: 'am_company_assigned', label: 'Account Manager Assignment', desc: 'When you are assigned as account manager' },
];

export default function NotificationPreferencesPage() {
  const [prefs, setPrefs] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadPrefs();
  }, []);

  const loadPrefs = async () => {
    try {
      const res = await notificationAPI.getPreferences();
      setPrefs(res.data);
    } catch {
      toast.error('Failed to load preferences');
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = (key) => {
    setPrefs(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {};
      PREF_LABELS.forEach(p => { payload[p.key] = prefs[p.key] !== false; });
      await notificationAPI.updatePreferences(payload);
      toast.success('Notification preferences saved');
    } catch {
      toast.error('Failed to save preferences');
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
    <div className="max-w-2xl mx-auto space-y-6" data-testid="notification-preferences">
      <div className="flex items-center gap-3">
        <Bell className="w-6 h-6 text-slate-700" />
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-bold text-slate-900">Notification Preferences</h1>
          <p className="text-sm text-slate-500">Choose which notifications you want to receive</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">In-App Notifications</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {PREF_LABELS.map(({ key, label, desc }) => (
            <div key={key} className="flex items-center justify-between py-2">
              <div>
                <p className="font-medium text-sm text-slate-900">{label}</p>
                <p className="text-xs text-slate-500">{desc}</p>
              </div>
              <Switch
                checked={prefs[key] !== false}
                onCheckedChange={() => handleToggle(key)}
                data-testid={`pref-toggle-${key}`}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="save-prefs-btn">
          {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
          Save Preferences
        </Button>
      </div>
    </div>
  );
}
