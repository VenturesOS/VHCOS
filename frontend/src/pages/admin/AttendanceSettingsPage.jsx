import { useState, useEffect } from 'react';
import { attendanceAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { Settings, Clock, AlertTriangle, Calendar, Timer, Save, Loader2, RotateCcw, PauseCircle, PlayCircle, Trash2, ShieldAlert } from 'lucide-react';

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
