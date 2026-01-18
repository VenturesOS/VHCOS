import { useState, useEffect, useRef } from 'react';
import { candidateAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { toast } from 'sonner';
import { UserCircle, Upload, Save, Plus, X, FileText } from 'lucide-react';

export default function ProfilePage() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [newSkill, setNewSkill] = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const res = await candidateAPI.getProfile();
      setProfile(res.data);
    } catch (error) {
      toast.error('Failed to load profile');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await candidateAPI.updateProfile({
        headline: profile.headline,
        summary: profile.summary,
        phone: profile.phone,
        skills: profile.skills,
        experience: profile.experience,
        education: profile.education,
      });
      toast.success('Profile updated!');
    } catch (error) {
      toast.error('Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  const handleResumeUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.match(/\.(pdf|doc|docx)$/i)) {
      toast.error('Please upload a PDF or DOC file');
      return;
    }

    setUploading(true);
    try {
      const res = await candidateAPI.uploadResume(file);
      setProfile({ ...profile, resume_url: res.data.resume_url });
      toast.success('Resume uploaded!');
    } catch (error) {
      toast.error('Failed to upload resume');
    } finally {
      setUploading(false);
    }
  };

  const handleAddSkill = () => {
    if (!newSkill.trim()) return;
    if (profile.skills?.includes(newSkill.trim())) {
      toast.error('Skill already added');
      return;
    }
    setProfile({
      ...profile,
      skills: [...(profile.skills || []), newSkill.trim()],
    });
    setNewSkill('');
  };

  const handleRemoveSkill = (skill) => {
    setProfile({
      ...profile,
      skills: profile.skills.filter((s) => s !== skill),
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6" data-testid="profile-page">
      <div>
        <h1 className="font-heading text-3xl font-bold text-slate-900">My Profile</h1>
        <p className="text-slate-500 mt-1">Manage your professional profile</p>
      </div>

      {/* Profile Header */}
      <Card className="border-slate-200">
        <CardContent className="p-6">
          <div className="flex items-center gap-6">
            <div className="w-24 h-24 rounded-full bg-[#DCFCE7] flex items-center justify-center">
              <span className="text-[#7CB342] font-bold text-4xl">
                {profile?.name?.charAt(0).toUpperCase()}
              </span>
            </div>
            <div className="flex-1">
              <h2 className="font-heading text-2xl font-bold text-slate-900">{profile?.name}</h2>
              <p className="text-slate-500">{profile?.email}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Resume Upload */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg flex items-center gap-2">
            <FileText className="w-5 h-5 text-[#7CB342]" />
            Resume
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            {profile?.resume_url ? (
              <a
                href={profile.resume_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#7CB342] hover:underline flex items-center gap-2"
              >
                <FileText className="w-5 h-5" /> View Current Resume
              </a>
            ) : (
              <p className="text-slate-500">No resume uploaded</p>
            )}
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleResumeUpload}
              accept=".pdf,.doc,.docx"
              className="hidden"
            />
            <Button
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              data-testid="upload-resume-btn"
            >
              {uploading ? (
                <div className="spinner w-4 h-4 border-2 mr-2" />
              ) : (
                <Upload className="w-4 h-4 mr-2" />
              )}
              Upload New
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Basic Info */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg">Basic Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Professional Headline</Label>
            <Input
              value={profile?.headline || ''}
              onChange={(e) => setProfile({ ...profile, headline: e.target.value })}
              placeholder="e.g., Senior Software Engineer at Tech Corp"
              data-testid="headline-input"
            />
          </div>
          <div className="space-y-2">
            <Label>Phone</Label>
            <Input
              value={profile?.phone || ''}
              onChange={(e) => setProfile({ ...profile, phone: e.target.value })}
              placeholder="Your contact number"
              data-testid="phone-input"
            />
          </div>
          <div className="space-y-2">
            <Label>Summary</Label>
            <Textarea
              value={profile?.summary || ''}
              onChange={(e) => setProfile({ ...profile, summary: e.target.value })}
              placeholder="Tell employers about yourself..."
              rows={4}
              data-testid="summary-input"
            />
          </div>
        </CardContent>
      </Card>

      {/* Skills */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-lg">Skills</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2 mb-4">
            {profile?.skills?.map((skill) => (
              <span
                key={skill}
                className="px-3 py-1.5 bg-[#DCFCE7] text-[#7CB342] rounded-full text-sm flex items-center gap-2"
              >
                {skill}
                <button onClick={() => handleRemoveSkill(skill)} className="hover:text-[#689F38]">
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
            {(!profile?.skills || profile.skills.length === 0) && (
              <p className="text-slate-400 text-sm">No skills added yet</p>
            )}
          </div>
          <div className="flex gap-2">
            <Input
              value={newSkill}
              onChange={(e) => setNewSkill(e.target.value)}
              placeholder="Add a skill"
              onKeyDown={(e) => e.key === 'Enter' && handleAddSkill()}
              data-testid="skill-input"
            />
            <Button variant="outline" onClick={handleAddSkill} data-testid="add-skill-btn">
              <Plus className="w-4 h-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button
          onClick={handleSave}
          disabled={saving}
          className="bg-[#7CB342] hover:bg-[#689F38]"
          data-testid="save-profile-btn"
        >
          {saving ? (
            <div className="spinner w-4 h-4 border-2 border-white border-t-transparent mr-2" />
          ) : (
            <Save className="w-4 h-4 mr-2" />
          )}
          Save Profile
        </Button>
      </div>
    </div>
  );
}
