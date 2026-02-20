import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Checkbox } from '../../components/ui/checkbox';
import { Badge } from '../../components/ui/badge';
import { Separator } from '../../components/ui/separator';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '../../components/ui/select';
import { toast } from 'sonner';
import {
  MapPin,
  Briefcase,
  Clock,
  DollarSign,
  ArrowLeft,
  Upload,
  Building2,
  FileText,
  Loader2,
  CheckCircle2,
  ShieldCheck,
  Lock
} from 'lucide-react';
import TrustBadge from '../../components/compliance/TrustBadge';

const API_URL = '';

export default function MandateApplyPage() {
  const { jobId } = useParams();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const navigate = useNavigate();
  
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showApplyForm, setShowApplyForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  
  // Form state
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    current_salary: '',
    notice_period: '',
    consent_given: false,
    consent_future_opportunities: false
  });
  const [resumeFile, setResumeFile] = useState(null);

  useEffect(() => {
    if (!token) {
      setError('Invalid or missing share token');
      setLoading(false);
      return;
    }
    fetchJob();
  }, [jobId, token]);

  const fetchJob = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_URL}/api/public/mandate/${jobId}?token=${encodeURIComponent(token)}`);
      
      if (!response.ok) {
        if (response.status === 404) {
          setError('Job not found or link has expired');
        } else if (response.status === 400) {
          setError('Invalid share link');
        } else {
          setError('Failed to load job details');
        }
        return;
      }
      
      const data = await response.json();
      setJob(data);
    } catch (err) {
      setError('Failed to load job details');
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
      if (!allowedTypes.includes(file.type)) {
        toast.error('Please upload a PDF or Word document');
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        toast.error('File size must be less than 5MB');
        return;
      }
      setResumeFile(file);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.name || !formData.email) {
      toast.error('Please fill in all required fields');
      return;
    }
    
    if (!resumeFile) {
      toast.error('Please upload your resume');
      return;
    }
    
    if (!formData.consent_given) {
      toast.error('Please provide consent to process your application');
      return;
    }

    setSubmitting(true);
    
    try {
      const submitFormData = new FormData();
      submitFormData.append('job_id', job.id);
      submitFormData.append('name', formData.name);
      submitFormData.append('email', formData.email);
      submitFormData.append('phone', formData.phone || '');
      submitFormData.append('current_salary', formData.current_salary || '');
      submitFormData.append('notice_period', formData.notice_period || '');
      submitFormData.append('resume', resumeFile);
      submitFormData.append('consent_given', 'true');
      submitFormData.append('mandate_token', token); // Include mandate token for verification
      
      const response = await fetch(`${API_URL}/api/public/apply`, {
        method: 'POST',
        body: submitFormData
      });
      
      const result = await response.json();
      
      if (!response.ok) {
        throw new Error(result.detail || 'Failed to submit application');
      }
      
      navigate('/application-success');
      
    } catch (err) {
      toast.error(err.message || 'Failed to submit application');
    } finally {
      setSubmitting(false);
    }
  };

  const formatSalary = (amount) => {
    if (!amount) return 'Not disclosed';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-purple-600 mx-auto" />
          <p className="mt-2 text-slate-600">Loading job details...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="p-8 text-center">
            <Lock className="h-12 w-12 text-slate-400 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-slate-900 mb-2">Access Denied</h2>
            <p className="text-slate-600 mb-6">{error}</p>
            <p className="text-sm text-slate-500">
              If you believe this is an error, please contact the recruiter who shared this link with you.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-purple-600" />
            <span className="text-sm font-medium text-purple-600">Confidential Opportunity</span>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Job Details Card */}
        <Card className="mb-6" data-testid="mandate-job-card">
          <CardContent className="p-6 md:p-8">
            {/* Job Header */}
            <div className="mb-6">
              <div className="flex items-center gap-2 mb-2">
                <Badge variant="secondary" className="bg-purple-100 text-purple-700">
                  {job.job_public_id}
                </Badge>
                <Badge variant="outline" className="text-slate-600">
                  <Lock className="h-3 w-3 mr-1" />
                  Private Listing
                </Badge>
              </div>
              <h1 className="text-2xl md:text-3xl font-bold text-slate-900 mb-2">
                {job.title}
              </h1>
              <p className="text-lg text-slate-600 flex items-center gap-2">
                <Building2 className="h-5 w-5" />
                {job.company_name}
              </p>
            </div>

            {/* Key Details */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="flex items-center gap-2 text-slate-600">
                <MapPin className="h-4 w-4 text-slate-400" />
                <span>{job.location}</span>
              </div>
              <div className="flex items-center gap-2 text-slate-600">
                <Briefcase className="h-4 w-4 text-slate-400" />
                <span className="capitalize">{job.job_type?.replace('-', ' ')}</span>
              </div>
              {job.experience_min !== null && (
                <div className="flex items-center gap-2 text-slate-600">
                  <Clock className="h-4 w-4 text-slate-400" />
                  <span>{job.experience_min}-{job.experience_max || job.experience_min + 5} years</span>
                </div>
              )}
              {(job.salary_min || job.salary_max) && (
                <div className="flex items-center gap-2 text-slate-600">
                  <DollarSign className="h-4 w-4 text-slate-400" />
                  <span>{formatSalary(job.salary_min)} - {formatSalary(job.salary_max)}</span>
                </div>
              )}
            </div>

            {/* Skills */}
            {job.skills?.length > 0 && (
              <div className="mb-6">
                <h3 className="text-sm font-medium text-slate-700 mb-2">Required Skills</h3>
                <div className="flex flex-wrap gap-2">
                  {job.skills.map((skill, idx) => (
                    <Badge key={idx} variant="secondary" className="bg-slate-100">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            <Separator className="my-6" />

            {/* Description */}
            <div className="mb-6">
              <h3 className="text-lg font-semibold text-slate-900 mb-3">Job Description</h3>
              <div className="prose prose-slate max-w-none text-slate-600 whitespace-pre-wrap">
                {job.description}
              </div>
            </div>

            {/* Requirements */}
            {job.requirements && (
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-slate-900 mb-3">Requirements</h3>
                <div className="prose prose-slate max-w-none text-slate-600 whitespace-pre-wrap">
                  {job.requirements}
                </div>
              </div>
            )}

            <Separator className="my-6" />

            {/* Apply Button */}
            {!showApplyForm ? (
              <div className="text-center">
                <Button 
                  size="lg" 
                  className="bg-purple-600 hover:bg-purple-700"
                  onClick={() => setShowApplyForm(true)}
                  data-testid="show-apply-form-btn"
                >
                  Apply for this Position
                </Button>
              </div>
            ) : (
              /* Application Form */
              <form onSubmit={handleSubmit} className="space-y-6" data-testid="mandate-apply-form">
                <h3 className="text-lg font-semibold text-slate-900">Apply Now</h3>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">Full Name *</Label>
                    <Input
                      id="name"
                      name="name"
                      value={formData.name}
                      onChange={handleInputChange}
                      placeholder="Your full name"
                      required
                      data-testid="apply-name-input"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="email">Email *</Label>
                    <Input
                      id="email"
                      name="email"
                      type="email"
                      value={formData.email}
                      onChange={handleInputChange}
                      placeholder="your.email@example.com"
                      required
                      data-testid="apply-email-input"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="phone">Phone Number</Label>
                    <Input
                      id="phone"
                      name="phone"
                      value={formData.phone}
                      onChange={handleInputChange}
                      placeholder="+91 98765 43210"
                      data-testid="apply-phone-input"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="current_salary">Current CTC (INR)</Label>
                    <Input
                      id="current_salary"
                      name="current_salary"
                      type="number"
                      value={formData.current_salary}
                      onChange={handleInputChange}
                      placeholder="e.g., 1200000"
                      data-testid="apply-salary-input"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="notice_period">Notice Period</Label>
                    <Select
                      value={formData.notice_period}
                      onValueChange={(value) => setFormData(prev => ({ ...prev, notice_period: value }))}
                    >
                      <SelectTrigger data-testid="apply-notice-select">
                        <SelectValue placeholder="Select notice period" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="immediate">Immediate</SelectItem>
                        <SelectItem value="15 days">15 Days</SelectItem>
                        <SelectItem value="30 days">30 Days</SelectItem>
                        <SelectItem value="60 days">60 Days</SelectItem>
                        <SelectItem value="90 days">90 Days</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Resume Upload */}
                <div className="space-y-2">
                  <Label htmlFor="resume">Resume/CV *</Label>
                  <div className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center hover:border-purple-300 transition-colors">
                    <input
                      type="file"
                      id="resume"
                      className="hidden"
                      accept=".pdf,.doc,.docx"
                      onChange={handleFileChange}
                      data-testid="apply-resume-input"
                    />
                    <label htmlFor="resume" className="cursor-pointer">
                      {resumeFile ? (
                        <div className="flex items-center justify-center gap-2 text-purple-600">
                          <CheckCircle2 className="h-5 w-5" />
                          <span className="font-medium">{resumeFile.name}</span>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <Upload className="h-8 w-8 text-slate-400 mx-auto" />
                          <p className="text-slate-600">
                            <span className="text-purple-600 font-medium">Click to upload</span> or drag and drop
                          </p>
                          <p className="text-xs text-slate-500">PDF, DOC, DOCX (max 5MB)</p>
                        </div>
                      )}
                    </label>
                  </div>
                </div>

                {/* DPDP Consent Block */}
                <div className="space-y-3 p-4 bg-slate-50 rounded-lg border border-slate-200" data-testid="consent-block">
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    <span className="text-xs font-semibold text-slate-700">Data Consent (DPDP 2023)</span>
                  </div>
                  <div className="flex items-start gap-3">
                    <Checkbox
                      id="consent"
                      checked={formData.consent_given}
                      onCheckedChange={(checked) => setFormData(prev => ({ ...prev, consent_given: checked }))}
                      data-testid="apply-consent-checkbox"
                    />
                    <label htmlFor="consent" className="text-xs text-slate-600 cursor-pointer leading-relaxed">
                      I consent to Ventures HRD collecting and processing my personal data including resume, contact details, and professional information for recruitment purposes under the Digital Personal Data Protection Act, 2023. I understand I can withdraw consent at any time by contacting <span className="text-emerald-700">privacy@vhc.in</span>.
                      <span className="text-red-500 ml-0.5">*</span>
                    </label>
                  </div>
                  <div className="flex items-start gap-3">
                    <Checkbox
                      id="consent_future"
                      checked={formData.consent_future_opportunities}
                      onCheckedChange={(checked) => setFormData(prev => ({ ...prev, consent_future_opportunities: checked }))}
                      data-testid="apply-consent-future-checkbox"
                    />
                    <label htmlFor="consent_future" className="text-xs text-slate-500 cursor-pointer leading-relaxed">
                      I also consent to being contacted for future relevant opportunities (optional).
                    </label>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-slate-400 mt-1">
                    <a href="/privacy-policy" target="_blank" rel="noopener" className="underline hover:text-slate-600">Privacy Policy</a>
                    <a href="/terms-of-use" target="_blank" rel="noopener" className="underline hover:text-slate-600">Terms of Use</a>
                  </div>
                </div>

                {/* Submit Button */}
                <div className="flex gap-4">
                  <Button 
                    type="button" 
                    variant="outline" 
                    onClick={() => setShowApplyForm(false)}
                  >
                    Cancel
                  </Button>
                  <Button 
                    type="submit" 
                    className="flex-1 bg-purple-600 hover:bg-purple-700"
                    disabled={submitting}
                    data-testid="submit-application-btn"
                  >
                    {submitting ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Submitting...
                      </>
                    ) : (
                      'Submit Application'
                    )}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>

        {/* Privacy Notice + Trust Badges */}
        <div className="text-center text-sm text-slate-500 space-y-3">
          <TrustBadge />
          <p>This is a confidential job opportunity shared via a secure link.</p>
          <p className="text-xs">Your application data will be handled in accordance with our <a href="/privacy-policy" target="_blank" rel="noopener" className="text-emerald-600 underline">Privacy Policy</a>.</p>
        </div>
      </main>
    </div>
  );
}
