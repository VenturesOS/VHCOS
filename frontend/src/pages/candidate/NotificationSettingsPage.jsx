import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import { Badge } from '../../components/ui/badge';
import { Alert, AlertDescription } from '../../components/ui/alert';
import { Bell, Mail, MessageCircle, Plus, X, Save, Pause, Play, CheckCircle, AlertTriangle } from 'lucide-react';
import api from '../../lib/api';

export default function NotificationSettingsPage() {
  const [preferences, setPreferences] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [newSkill, setNewSkill] = useState('');
  const [whatsappNumber, setWhatsappNumber] = useState('');
  const [notificationHistory, setNotificationHistory] = useState([]);

  const fetchPreferences = useCallback(async () => {
    try {
      const response = await api.get('/alerts/preferences');
      setPreferences(response.data);
      setWhatsappNumber(response.data.whatsapp_number || '');
    } catch (err) {
      setError('Failed to load notification preferences');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const response = await api.get('/notifications/history?limit=10');
      setNotificationHistory(response.data);
    } catch {
      // Silent fail - notification history is non-critical
    }
  }, []);

  useEffect(() => {
    fetchPreferences();
    fetchHistory();
  }, [fetchPreferences, fetchHistory]);

  const handleSavePreferences = async () => {
    setSaving(true);
    setError('');
    setSuccess('');
    
    try {
      const endpoint = preferences.is_active ? '/alerts/preferences' : '/alerts/preferences';
      const method = preferences.is_active ? 'put' : 'post';
      
      await api[method](endpoint, {
        skills: preferences.skills,
        location_preference: preferences.location_preference,
        experience_min: preferences.experience_min,
        experience_max: preferences.experience_max,
        job_types: preferences.job_types,
        frequency: preferences.frequency,
        email_enabled: preferences.email_enabled
      });
      
      setSuccess('Preferences saved successfully!');
      fetchPreferences();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save preferences');
    } finally {
      setSaving(false);
    }
  };

  const handlePauseResume = async () => {
    setSaving(true);
    setError('');
    
    try {
      const endpoint = preferences.is_active ? '/alerts/pause' : '/alerts/resume';
      await api.post(endpoint);
      setSuccess(preferences.is_active ? 'Alerts paused' : 'Alerts resumed');
      fetchPreferences();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update alert status');
    } finally {
      setSaving(false);
    }
  };

  const handleWhatsAppOptIn = async () => {
    if (!whatsappNumber) {
      setError('Please enter a valid phone number');
      return;
    }
    
    setSaving(true);
    setError('');
    
    try {
      await api.post('/alerts/whatsapp/opt-in', {
        whatsapp_number: whatsappNumber,
        opt_in: true
      });
      setSuccess('WhatsApp notifications enabled!');
      fetchPreferences();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to enable WhatsApp notifications');
    } finally {
      setSaving(false);
    }
  };

  const handleWhatsAppOptOut = async () => {
    setSaving(true);
    setError('');
    
    try {
      await api.post('/alerts/whatsapp/opt-out');
      setSuccess('WhatsApp notifications disabled');
      fetchPreferences();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to disable WhatsApp notifications');
    } finally {
      setSaving(false);
    }
  };

  const addSkill = () => {
    if (newSkill.trim() && !preferences.skills.includes(newSkill.trim())) {
      setPreferences({
        ...preferences,
        skills: [...preferences.skills, newSkill.trim()]
      });
      setNewSkill('');
    }
  };

  const removeSkill = (skill) => {
    setPreferences({
      ...preferences,
      skills: preferences.skills.filter(s => s !== skill)
    });
  };

  const toggleJobType = (type) => {
    const types = preferences.job_types || [];
    if (types.includes(type)) {
      setPreferences({
        ...preferences,
        job_types: types.filter(t => t !== type)
      });
    } else {
      setPreferences({
        ...preferences,
        job_types: [...types, type]
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7CB342]"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="notification-settings-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Notification Settings</h1>
          <p className="text-gray-600">Manage your job alerts and notification preferences</p>
        </div>
        <div className="flex items-center gap-2">
          {preferences?.is_active ? (
            <Badge className="bg-green-100 text-green-800">
              <CheckCircle className="w-3 h-3 mr-1" />
              Alerts Active
            </Badge>
            ) : (
              <Badge variant="secondary">
                <Pause className="w-3 h-3 mr-1" />
                Alerts Paused
              </Badge>
            )}
          </div>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert className="border-green-200 bg-green-50">
            <CheckCircle className="h-4 w-4 text-green-600" />
            <AlertDescription className="text-green-800">{success}</AlertDescription>
          </Alert>
        )}

        <div className="grid gap-6 md:grid-cols-2">
          {/* Job Alert Preferences */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-[#7CB342]" />
                Job Alert Preferences
              </CardTitle>
              <CardDescription>
                Define what types of jobs you want to be notified about
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Skills */}
              <div className="space-y-2">
                <Label>Skills to Match</Label>
                <div className="flex gap-2">
                  <Input
                    placeholder="Add a skill..."
                    value={newSkill}
                    onChange={(e) => setNewSkill(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && addSkill()}
                    data-testid="skill-input"
                  />
                  <Button onClick={addSkill} size="icon" variant="outline">
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {preferences?.skills?.map((skill) => (
                    <Badge key={skill} variant="secondary" className="pl-2 pr-1 py-1">
                      {skill}
                      <button
                        onClick={() => removeSkill(skill)}
                        className="ml-1 hover:bg-gray-200 rounded-full p-0.5"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Location */}
              <div className="space-y-2">
                <Label htmlFor="location">Preferred Location</Label>
                <Input
                  id="location"
                  placeholder="e.g., Remote, New York, Bangalore"
                  value={preferences?.location_preference || ''}
                  onChange={(e) => setPreferences({...preferences, location_preference: e.target.value})}
                  data-testid="location-input"
                />
              </div>

              {/* Experience Range */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="exp-min">Min Experience (years)</Label>
                  <Input
                    id="exp-min"
                    type="number"
                    min="0"
                    value={preferences?.experience_min || ''}
                    onChange={(e) => setPreferences({...preferences, experience_min: parseInt(e.target.value) || null})}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="exp-max">Max Experience (years)</Label>
                  <Input
                    id="exp-max"
                    type="number"
                    min="0"
                    value={preferences?.experience_max || ''}
                    onChange={(e) => setPreferences({...preferences, experience_max: parseInt(e.target.value) || null})}
                  />
                </div>
              </div>

              {/* Job Types */}
              <div className="space-y-2">
                <Label>Job Types</Label>
                <div className="flex flex-wrap gap-2">
                  {['full-time', 'part-time', 'contract', 'remote'].map((type) => (
                    <Badge
                      key={type}
                      variant={preferences?.job_types?.includes(type) ? 'default' : 'outline'}
                      className={`cursor-pointer ${preferences?.job_types?.includes(type) ? 'bg-[#7CB342]' : ''}`}
                      onClick={() => toggleJobType(type)}
                    >
                      {type}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="pt-4 flex gap-2">
                <Button
                  onClick={handleSavePreferences}
                  disabled={saving}
                  className="bg-[#7CB342] hover:bg-[#689f38]"
                  data-testid="save-preferences-btn"
                >
                  <Save className="h-4 w-4 mr-2" />
                  {saving ? 'Saving...' : 'Save Preferences'}
                </Button>
                <Button
                  onClick={handlePauseResume}
                  disabled={saving}
                  variant="outline"
                >
                  {preferences?.is_active ? (
                    <>
                      <Pause className="h-4 w-4 mr-2" />
                      Pause Alerts
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4 mr-2" />
                      Resume Alerts
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Notification Channels */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mail className="h-5 w-5 text-[#7CB342]" />
                Notification Channels
              </CardTitle>
              <CardDescription>
                Choose how you want to receive job match notifications
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Email Toggle */}
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-3">
                  <Mail className="h-5 w-5 text-gray-600" />
                  <div>
                    <p className="font-medium">Email Notifications</p>
                    <p className="text-sm text-gray-500">Receive job matches via email</p>
                  </div>
                </div>
                <Switch
                  checked={preferences?.email_enabled ?? true}
                  onCheckedChange={(checked) => setPreferences({...preferences, email_enabled: checked})}
                  data-testid="email-toggle"
                />
              </div>

              {/* WhatsApp Toggle */}
              <div className="p-4 bg-gray-50 rounded-lg space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <MessageCircle className="h-5 w-5 text-green-600" />
                    <div>
                      <p className="font-medium">WhatsApp Notifications</p>
                      <p className="text-sm text-gray-500">
                        {preferences?.whatsapp_opt_in 
                          ? `Enabled: ${preferences.whatsapp_number}` 
                          : 'Get instant alerts on WhatsApp'}
                      </p>
                    </div>
                  </div>
                  {preferences?.whatsapp_opt_in && (
                    <Badge className="bg-green-100 text-green-800">Enabled</Badge>
                  )}
                </div>

                {!preferences?.whatsapp_opt_in ? (
                  <div className="space-y-2">
                    <Input
                      placeholder="Enter phone number (e.g., +919876543210)"
                      value={whatsappNumber}
                      onChange={(e) => setWhatsappNumber(e.target.value)}
                      data-testid="whatsapp-number-input"
                    />
                    <Button
                      onClick={handleWhatsAppOptIn}
                      disabled={saving}
                      variant="outline"
                      className="w-full"
                      data-testid="whatsapp-optin-btn"
                    >
                      <MessageCircle className="h-4 w-4 mr-2" />
                      Enable WhatsApp Notifications
                    </Button>
                    <p className="text-xs text-gray-500">
                      By enabling, you consent to receive job match notifications via WhatsApp.
                    </p>
                  </div>
                ) : (
                  <Button
                    onClick={handleWhatsAppOptOut}
                    disabled={saving}
                    variant="destructive"
                    size="sm"
                    data-testid="whatsapp-optout-btn"
                  >
                    Disable WhatsApp
                  </Button>
                )}
              </div>

              {/* Frequency */}
              <div className="space-y-2">
                <Label>Alert Frequency</Label>
                <div className="flex gap-2">
                  {['instant', 'daily', 'weekly'].map((freq) => (
                    <Button
                      key={freq}
                      variant={preferences?.frequency === freq ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setPreferences({...preferences, frequency: freq})}
                      className={preferences?.frequency === freq ? 'bg-[#7CB342]' : ''}
                    >
                      {freq.charAt(0).toUpperCase() + freq.slice(1)}
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Notification History */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Notifications</CardTitle>
            <CardDescription>
              Your notification history (last 10)
            </CardDescription>
          </CardHeader>
          <CardContent>
            {notificationHistory.length === 0 ? (
              <p className="text-gray-500 text-center py-4">No notifications yet</p>
            ) : (
              <div className="space-y-2">
                {notificationHistory.map((notif) => (
                  <div
                    key={notif.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      {notif.channel === 'email' ? (
                        <Mail className="h-4 w-4 text-blue-500" />
                      ) : (
                        <MessageCircle className="h-4 w-4 text-green-500" />
                      )}
                      <div>
                        <p className="text-sm font-medium">{notif.type.replace('_', ' ')}</p>
                        <p className="text-xs text-gray-500">
                          {new Date(notif.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
                        </p>
                      </div>
                    </div>
                    <Badge variant={notif.status === 'sent' ? 'default' : 'secondary'}>
                      {notif.status}
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
