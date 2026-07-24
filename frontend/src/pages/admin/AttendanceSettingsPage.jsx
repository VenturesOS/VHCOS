import { useState, useEffect } from 'react';
import { attendanceAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { Settings, Clock, AlertTriangle, Calendar, Timer, Save, Loader2, RotateCcw, PauseCircle, PlayCircle, Trash2, ShieldAlert, MapPin } from 'lucide-react';
import { OfficeMapPicker } from '../../components/attendance/OfficeMapPicker';

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export default function AttendanceSettingsPage() {
  const [settings, setSettings] = useState(null);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await attendanceAPI.getSettings();
        setSettings(res.data);
        setDraft(res.data);
      } catch { toast.error('Failed to load settings'); }
      finally { setLoading(false); }
    })();
  }, []);

  const hasChanges = JSON.stringify(draft) !== JSON.stringify(settings);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await attendanceAPI.updateSettings(draft);
      setSettings(res.data);
      setDraft(res.data);
      setConfirmOpen(false);
      toast.success('Settings saved successfully!');
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed'); }
    finally { setSaving(false); }
  };

  const handleReset = () => { setDraft(settings); toast.info('Changes reverted'); };

  const toggleWeekend = (day) => {
    const current = draft?.weekend_days || [];
    setDraft(d => ({
      ...d,
      weekend_days: current.includes(day) ? current.filter(d => d !== day) : [...current, day],
    }));
  };

  const update = (key, value) => setDraft(d => ({ ...d, [key]: value }));

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-6 max-w-3xl" data-testid="attendance-settings-page">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-slate-100 border"><Settings className="h-5 w-5 text-slate-700" /></div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight" data-testid="settings-title">Attendance Settings</h1>
            <p className="text-sm text-muted-foreground">Configure work hours, reminders & automation rules</p>
          </div>
        </div>
        <div className="flex gap-2">
          {hasChanges && <Button variant="ghost" onClick={handleReset} data-testid="reset-btn"><RotateCcw className="h-4 w-4 mr-1" /> Revert</Button>}
          <Button onClick={() => setConfirmOpen(true)} disabled={!hasChanges} data-testid="save-btn">
            <Save className="h-4 w-4 mr-1" /> Save Changes
          </Button>
        </div>
      </div>

      {/* Work Hours */}
      <Card data-testid="work-hours-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Clock className="h-4 w-4 text-blue-500" /> Work Hours</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-sm">Work Start Time</Label>
              <Input type="time" value={draft?.work_start_time || '09:00'} onChange={e => update('work_start_time', e.target.value)} className="mt-1.5" data-testid="work-start" />
              <p className="text-[11px] text-muted-foreground mt-1">Employees arriving after this are marked late</p>
            </div>
            <div>
              <Label className="text-sm">Work End Time</Label>
              <Input type="time" value={draft?.work_end_time || '18:00'} onChange={e => update('work_end_time', e.target.value)} className="mt-1.5" data-testid="work-end" />
              <p className="text-[11px] text-muted-foreground mt-1">Checkout after this counts as overtime</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-sm">Full Day Hours</Label>
              <Input type="number" step="0.5" min="1" max="24" value={draft?.full_day_hours || 9} onChange={e => update('full_day_hours', parseFloat(e.target.value) || 9)} className="mt-1.5" data-testid="full-day-hours" />
            </div>
            <div>
              <Label className="text-sm">Half Day Hours</Label>
              <Input type="number" step="0.5" min="1" max="12" value={draft?.half_day_hours || 4.5} onChange={e => update('half_day_hours', parseFloat(e.target.value) || 4.5)} className="mt-1.5" data-testid="half-day-hours" />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Thresholds */}
      <Card data-testid="thresholds-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Timer className="h-4 w-4 text-amber-500" /> Thresholds</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-sm">Late Threshold (minutes)</Label>
              <Input type="number" min="0" max="120" value={draft?.late_threshold_minutes ?? 15} onChange={e => update('late_threshold_minutes', parseInt(e.target.value) || 0)} className="mt-1.5" data-testid="late-threshold" />
              <p className="text-[11px] text-muted-foreground mt-1">Minutes after start time before marking as late</p>
            </div>
            <div>
              <Label className="text-sm">Overtime Threshold (minutes)</Label>
              <Input type="number" min="0" max="300" value={draft?.overtime_threshold_minutes ?? 60} onChange={e => update('overtime_threshold_minutes', parseInt(e.target.value) || 0)} className="mt-1.5" data-testid="overtime-threshold" />
              <p className="text-[11px] text-muted-foreground mt-1">Minutes after end time to count as overtime day</p>
            </div>
          </div>
          <div>
            <Label className="text-sm">Grace Window (minutes)</Label>
            <Input type="number" min="0" max="120" value={draft?.grace_window_minutes ?? 30} onChange={e => update('grace_window_minutes', parseInt(e.target.value) || 0)} className="mt-1.5 max-w-[200px]" data-testid="grace-window" />
            <p className="text-[11px] text-muted-foreground mt-1">Buffer time before auto-absent marks an employee</p>
          </div>
        </CardContent>
      </Card>

      {/* Automation */}
      <Card data-testid="automation-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-red-500" /> Automation Schedule</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-sm">Reminder Time</Label>
              <Input type="time" value={draft?.reminder_time || '10:00'} onChange={e => update('reminder_time', e.target.value)} className="mt-1.5" data-testid="reminder-time" />
              <p className="text-[11px] text-muted-foreground mt-1">Daily reminder for employees who haven't checked in</p>
            </div>
            <div>
              <Label className="text-sm">Auto-Absent Time</Label>
              <Input type="time" value={draft?.auto_absent_time || '18:30'} onChange={e => update('auto_absent_time', e.target.value)} className="mt-1.5" data-testid="auto-absent-time" />
              <p className="text-[11px] text-muted-foreground mt-1">Auto-mark absent for no-shows after this time</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Weekend Days */}
      <Card data-testid="weekend-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Calendar className="h-4 w-4 text-cyan-500" /> Weekend Days</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-3">Select non-working days. Reminders and auto-absent will skip these days.</p>
          <div className="flex gap-2" data-testid="weekend-toggles">
            {WEEKDAY_LABELS.map((label, i) => {
              const active = (draft?.weekend_days || []).includes(i);
              return (
                <button
                  key={i}
                  onClick={() => toggleWeekend(i)}
                  className={`w-12 h-12 rounded-lg text-sm font-medium border-2 transition-all ${active ? 'bg-red-50 border-red-300 text-red-700' : 'bg-white border-slate-200 text-slate-500 hover:border-slate-300'}`}
                  data-testid={`weekend-${label.toLowerCase()}`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Geo-Fencing */}
      <Card className={draft?.geo_fencing_enabled ? 'border-green-300' : ''} data-testid="geo-fencing-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><MapPin className="h-4 w-4 text-green-500" /> Geo-Fencing</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">When enabled, employees can only check in from office mode if they are within the configured radius of any registered office. WFH and field modes bypass this check.</p>
          <Button
            variant={draft?.geo_fencing_enabled ? 'outline' : 'default'}
            onClick={() => update('geo_fencing_enabled', !draft?.geo_fencing_enabled)}
            className={draft?.geo_fencing_enabled ? 'border-red-300 text-red-600 hover:bg-red-50' : 'bg-green-600 hover:bg-green-700'}
            data-testid="geo-fence-toggle-btn"
          >
            <MapPin className="h-4 w-4 mr-1" /> {draft?.geo_fencing_enabled ? 'Disable Geo-Fencing' : 'Enable Geo-Fencing'}
          </Button>
          {draft?.geo_fencing_enabled && (
            <div className="space-y-4 pt-2 border-t">
              <div>
                <Label className="text-sm">Allowed Radius (meters)</Label>
                <Input type="number" min="50" max="5000" value={draft?.geo_fence_radius_meters || 500} onChange={e => update('geo_fence_radius_meters', parseInt(e.target.value) || 500)} className="mt-1.5 w-40" data-testid="geo-radius" />
                <p className="text-[11px] text-muted-foreground mt-1">Employees must be within this distance of any office</p>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-sm font-medium">Office Locations</Label>
                  <Button size="sm" variant="outline" onClick={() => {
                    const offices = [...(draft?.offices || [])];
                    offices.push({ name: '', latitude: '', longitude: '' });
                    update('offices', offices);
                  }} data-testid="add-office-btn">+ Add Office</Button>
                </div>
                {(!draft?.offices || draft.offices.length === 0) && (
                  <p className="text-sm text-muted-foreground text-center py-4 bg-slate-50 rounded-lg">No offices configured. Add an office to enable geo-fencing.</p>
                )}
                <div className="space-y-3">
                  {(draft?.offices || []).map((office, i) => (
                    <div key={i} className="p-3 bg-slate-50 rounded-lg border border-slate-200 space-y-2" data-testid={`office-${i}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-500">Office {i + 1}</span>
                        <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-red-400 hover:text-red-600" onClick={() => {
                          const offices = [...(draft?.offices || [])];
                          offices.splice(i, 1);
                          update('offices', offices);
                        }}>x</Button>
                      </div>
                      <div className="space-y-2">
                        <Input placeholder="Office name (e.g. HQ, Branch-2)" value={office.name || ''} onChange={e => {
                          const offices = [...(draft?.offices || [])];
                          offices[i] = { ...offices[i], name: e.target.value };
                          update('offices', offices);
                        }} className="text-sm" data-testid={`office-name-${i}`} />
                        <OfficeMapPicker
                          latitude={office.latitude}
                          longitude={office.longitude}
                          onChange={(lat, lon) => {
                            const offices = [...(draft?.offices || [])];
                            offices[i] = { ...offices[i], latitude: lat, longitude: lon };
                            update('offices', offices);
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pause Toggle */}
      <Card className={draft?.is_paused ? 'border-amber-300 bg-amber-50/30' : ''} data-testid="pause-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            {draft?.is_paused ? <PauseCircle className="h-4 w-4 text-amber-500" /> : <PlayCircle className="h-4 w-4 text-green-500" />}
            Attendance Tracking — {draft?.is_paused ? 'Paused' : 'Active'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-3">
            {draft?.is_paused
              ? 'Check-in/check-out is disabled for all employees. Cron jobs (reminders, auto-absent) are skipped. Admin can still view data.'
              : 'Attendance tracking is active. Employees can check in and out. Cron jobs run on schedule.'}
          </p>
          <Button
            variant={draft?.is_paused ? 'default' : 'outline'}
            onClick={() => update('is_paused', !draft?.is_paused)}
            className={draft?.is_paused ? 'bg-green-600 hover:bg-green-700' : 'border-amber-300 text-amber-700 hover:bg-amber-50'}
            data-testid="pause-toggle-btn"
          >
            {draft?.is_paused ? <><PlayCircle className="h-4 w-4 mr-1" /> Resume Tracking</> : <><PauseCircle className="h-4 w-4 mr-1" /> Pause Tracking</>}
          </Button>
        </CardContent>
      </Card>

      {/* Pre-Launch Reset */}
      <PreLaunchResetSection />

      {/* Confirmation Dialog */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="max-w-sm" data-testid="confirm-dialog">
          <DialogHeader>
            <DialogTitle>Confirm Changes</DialogTitle>
            <DialogDescription>These settings affect attendance tracking, reminders and auto-absent marking for all employees. Save changes?</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} data-testid="confirm-save-btn">
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
              Save Settings
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PreLaunchResetSection() {
  const [showReset, setShowReset] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [resetting, setResetting] = useState(false);
  const [result, setResult] = useState(null);

  const handleReset = async () => {
    if (confirmText !== 'RESET DATA') return toast.error("Type 'RESET DATA' exactly to confirm.");
    setResetting(true);
    try {
      const res = await attendanceAPI.preLaunchReset({ confirmation: confirmText });
      setResult(res.data);
      toast.success('Pre-launch reset completed!');
    } catch (e) { toast.error(e.response?.data?.detail || 'Reset failed'); }
    finally { setResetting(false); }
  };

  return (
    <>
      <Card className="border-red-200" data-testid="reset-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2 text-red-700"><ShieldAlert className="h-4 w-4" /> Pre-Launch Reset</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-1">Permanently delete all operational data before team launch:</p>
          <ul className="text-xs text-muted-foreground mb-3 space-y-0.5 ml-4 list-disc">
            <li>Attendance records, leave requests, leave balances, health scores</li>
            <li>Notification events, delivery logs, cron job logs</li>
            <li>Jobs, revenue entries, invoices</li>
          </ul>
          <p className="text-xs text-red-600 font-medium mb-3">Users, settings, and holidays will NOT be affected.</p>
          <Button variant="destructive" size="sm" onClick={() => setShowReset(true)} data-testid="open-reset-btn">
            <Trash2 className="h-3.5 w-3.5 mr-1" /> Pre-Launch Reset
          </Button>
        </CardContent>
      </Card>

      <Dialog open={showReset} onOpenChange={(v) => { setShowReset(v); setConfirmText(''); setResult(null); }}>
        <DialogContent className="max-w-md" data-testid="reset-dialog">
          <DialogHeader>
            <DialogTitle className="text-red-700 flex items-center gap-2"><ShieldAlert className="h-5 w-5" /> Pre-Launch Data Reset</DialogTitle>
            <DialogDescription>This action is irreversible. All operational data will be permanently deleted.</DialogDescription>
          </DialogHeader>
          {result ? (
            <div className="py-3 space-y-2">
              <p className="text-sm font-medium text-green-700">Reset completed successfully.</p>
              <div className="text-xs space-y-1 bg-slate-50 rounded-lg p-3">
                {Object.entries(result.deleted || {}).map(([k, v]) => (
                  <div key={k} className="flex justify-between"><span className="text-muted-foreground">{k}</span><span className="font-medium">{v} deleted</span></div>
                ))}
              </div>
            </div>
          ) : (
            <div className="py-2 space-y-3">
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-xs text-red-700">Type <strong>RESET DATA</strong> below to confirm:</p>
              </div>
              <Input
                value={confirmText}
                onChange={e => setConfirmText(e.target.value)}
                placeholder="Type RESET DATA"
                className="font-mono text-center"
                data-testid="reset-confirm-input"
              />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowReset(false); setConfirmText(''); setResult(null); }}>
              {result ? 'Close' : 'Cancel'}
            </Button>
            {!result && (
              <Button variant="destructive" onClick={handleReset} disabled={resetting || confirmText !== 'RESET DATA'} data-testid="confirm-reset-btn">
                {resetting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Trash2 className="h-4 w-4 mr-1" />}
                Reset All Data
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
