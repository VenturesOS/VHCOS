import { useState, useEffect } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { jobAPI, accountManagerAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { ArrowLeft, Save, Loader2, X, Plus } from 'lucide-react';
import { useAuth } from '../../lib/auth';

export default function AMCreateJobPage() {
  const navigate = useNavigate();
  const { companyId } = useParams();
  const { user } = useAuth();
  const basePath = user?.role === 'employer' ? '/employer' : '/recruiter';
  const [loading, setLoading] = useState(false);
  const [company, setCompany] = useState(null);
  const [skillInput, setSkillInput] = useState('');
  const [form, setForm] = useState({
    title: '', description: '', location: '', employment_type: 'full_time',
    experience_min: '', experience_max: '', salary_min: '', salary_max: '',
    skills: [], department: '', positions: 1, public_company_alias: '',
    company_id: companyId,
  });

  useEffect(() => {
    accountManagerAPI.getMyCompanies().then(res => {
      const comp = (res.data.companies || []).find(c => c.id === companyId);
      if (comp) {
        setCompany(comp);
        setForm(f => ({ ...f, public_company_alias: comp.name }));
      }
    });
  }, [companyId]);

  const update = (field, value) => setForm(f => ({ ...f, [field]: value }));

  const addSkill = () => {
    const s = skillInput.trim();
    if (s && !form.skills.includes(s)) {
      setForm(f => ({ ...f, skills: [...f.skills, s] }));
      setSkillInput('');
    }
  };

  const removeSkill = (skill) => setForm(f => ({ ...f, skills: f.skills.filter(s => s !== skill) }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title || !form.description) {
      toast.error('Title and description are required');
      return;
    }
    setLoading(true);
    try {
      const payload = {
        ...form,
        experience_min: form.experience_min ? Number(form.experience_min) : 0,
        experience_max: form.experience_max ? Number(form.experience_max) : 0,
        salary_min: form.salary_min ? Number(form.salary_min) : 0,
        salary_max: form.salary_max ? Number(form.salary_max) : 0,
        positions: Number(form.positions) || 1,
      };
      await jobAPI.create(payload);
      toast.success('Job created successfully');
      navigate(`${basePath}/account-manager/company/${companyId}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create job');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6" data-testid="am-create-job">
      <div className="flex items-center gap-4">
        <Link to={`${basePath}/account-manager/company/${companyId}`}>
          <Button variant="ghost" size="sm"><ArrowLeft className="w-4 h-4 mr-1" /> Back</Button>
        </Link>
        <div>
          <h1 className="font-heading text-xl sm:text-2xl font-bold text-slate-900">Create Job</h1>
          <p className="text-sm text-slate-500">For {company?.name || 'Company'}</p>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader><CardTitle>Job Details</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Job Title *</Label>
              <Input value={form.title} onChange={e => update('title', e.target.value)} placeholder="e.g. Senior Software Engineer" data-testid="job-title-input" />
            </div>
            <div>
              <Label>Description *</Label>
              <Textarea value={form.description} onChange={e => update('description', e.target.value)} rows={6} placeholder="Job description..." data-testid="job-desc-input" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label>Location</Label>
                <Input value={form.location} onChange={e => update('location', e.target.value)} placeholder="e.g. Mumbai, Remote" />
              </div>
              <div>
                <Label>Department</Label>
                <Input value={form.department} onChange={e => update('department', e.target.value)} placeholder="e.g. Engineering" />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label>Employment Type</Label>
                <Select value={form.employment_type} onValueChange={v => update('employment_type', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="full_time">Full Time</SelectItem>
                    <SelectItem value="part_time">Part Time</SelectItem>
                    <SelectItem value="contract">Contract</SelectItem>
                    <SelectItem value="internship">Internship</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>No. of Positions</Label>
                <Input type="number" min={1} value={form.positions} onChange={e => update('positions', e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <Label>Exp Min (yrs)</Label>
                <Input type="number" min={0} value={form.experience_min} onChange={e => update('experience_min', e.target.value)} />
              </div>
              <div>
                <Label>Exp Max (yrs)</Label>
                <Input type="number" min={0} value={form.experience_max} onChange={e => update('experience_max', e.target.value)} />
              </div>
              <div>
                <Label>Salary Min</Label>
                <Input type="number" min={0} value={form.salary_min} onChange={e => update('salary_min', e.target.value)} />
              </div>
              <div>
                <Label>Salary Max</Label>
                <Input type="number" min={0} value={form.salary_max} onChange={e => update('salary_max', e.target.value)} />
              </div>
            </div>
            <div>
              <Label>Public Company Alias</Label>
              <Input value={form.public_company_alias} onChange={e => update('public_company_alias', e.target.value)} placeholder="Company name shown publicly" />
            </div>
            <div>
              <Label>Skills</Label>
              <div className="flex gap-2">
                <Input value={skillInput} onChange={e => setSkillInput(e.target.value)} placeholder="Add a skill"
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSkill(); } }} />
                <Button type="button" variant="outline" onClick={addSkill}><Plus className="w-4 h-4" /></Button>
              </div>
              {form.skills.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {form.skills.map(s => (
                    <span key={s} className="inline-flex items-center gap-1 px-2 py-1 bg-slate-100 rounded text-sm">
                      {s}
                      <button type="button" onClick={() => removeSkill(s)}><X className="w-3 h-3" /></button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end mt-4">
          <Button type="submit" disabled={loading} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="submit-job-btn">
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
            Create Job
          </Button>
        </div>
      </form>
    </div>
  );
}
