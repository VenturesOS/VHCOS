import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
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
  CheckCircle2
} from 'lucide-react';
import { TurnstileWidget, isTurnstileEnabled } from '../../components/TurnstileWidget';
import SEOHead from '../../components/shared/SEOHead';
import { jobPostingLD, breadcrumbLD } from '../../lib/structuredData';

const API_URL = '';

export default function PublicJobPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showApplyForm, setShowApplyForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState('');
  
  // Form state
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    current_salary: '',
    notice_period: '',
    consent_given: false
  });
  const [resumeFile, setResumeFile] = useState(null);

  const fetchJob = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_URL}/api/public/jobs/${jobId}`);
      
      if (!response.ok) {
        if (response.status === 404) {
          setError('Job not found or no longer available');
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
  }, [jobId]);

  useEffect(() => {
    fetchJob();
  }, [fetchJob]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Validate file type
      const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
      if (!allowedTypes.includes(file.type)) {
        toast.error('Please upload a PDF or Word document');
        return;
      }
      // Validate file size (5MB max)
      if (file.size > 5 * 1024 * 1024) {
        toast.error('File size must be less than 5MB');
        return;
      }
      setResumeFile(file);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validation
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

    if (isTurnstileEnabled && !turnstileToken) {
      toast.error('Please complete the CAPTCHA verification');
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
      if (turnstileToken) {
        submitFormData.append('turnstile_token', turnstileToken);
      }
      
      const response = await fetch(`${API_URL}/api/public/apply`, {
        method: 'POST',
        body: submitFormData
      });
      
      let result;
      try {
        result = await response.json();
      } catch {
        throw new Error('Server error. Please try again.');
      }
      
      if (!response.ok) {
        throw new Error(result.detail || 'Failed to submit application');
      }
      
      // Navigate to success page
      navigate('/application-success');
      
    } catch (err) {
      toast.error(err.message || 'Failed to submit application');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-8 text-center">
            <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Job Not Found</h2>
            <p className="text-gray-600 mb-6">{error}</p>
            <Link to="/website/careers.html">
              <Button variant="outline">
                <ArrowLeft className="h-4 w-4 mr-2" />
                View All Jobs
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50" data-testid="public-job-page">
      {/* SEO: JobPosting JSON-LD makes this listing eligible for the
          Google for Jobs panel. Was previously absent — free channel unused. */}
      <SEOHead
        title={job ? `${job.title}${job.location ? ` — ${job.location}` : ''}` : 'Job'}
        description={(job?.description || job?.title || '').replace(/<[^>]+>/g, '').slice(0, 155)}
        path={`/jobs/${job?.id || ''}`}
        jsonLd={job ? [
          jobPostingLD(job),
          breadcrumbLD([
            { name: 'Careers', path: '/website/careers.html' },
            { name: job.title || 'Job', path: `/jobs/${job.id}` },
          ]),
        ] : null}
      />
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link to="/website/careers.html" className="flex items-center text-gray-600 hover:text-gray-900">
            <ArrowLeft className="h-5 w-5 mr-2" />
            Back to Jobs
          </Link>
          <img 
            src="/website/images/logo.svg" 
            alt="Ventures HRD" 
            className="h-8"
            onError={(e) => { e.target.style.display = 'none'; }}
          />
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Job Details Card */}
        <Card className="mb-6">
          <CardHeader className="pb-4">
            {/* Job ID Badge */}
            {job.job_public_id && (
              <Badge variant="outline" className="w-fit mb-3 text-xs font-mono">
                {job.job_public_id}
              </Badge>
            )}
            
            <CardTitle className="text-2xl md:text-3xl font-bold text-gray-900">
              {job.title}
            </CardTitle>
            
            <div className="flex flex-wrap gap-4 mt-4 text-gray-600">
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4" />
                <span>{job.company_name}</span>
              </div>
              <div className="flex items-center gap-2">
                <MapPin className="h-4 w-4" />
                <span>{job.location}</span>
              </div>
              <div className="flex items-center gap-2">
                <Briefcase className="h-4 w-4" />
                <span className="capitalize">{job.job_type?.replace('-', ' ')}</span>
              </div>
              {(job.experience_min || job.experience_max) && (
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  <span>
                    {job.experience_min && job.experience_max 
                      ? `${job.experience_min}-${job.experience_max} years`
                      : job.experience_min 
                        ? `${job.experience_min}+ years`
                        : `Up to ${job.experience_max} years`
                    }
                  </span>
                </div>
              )}
              {(job.salary_min || job.salary_max) && (
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4" />
                  <span>
                    {job.salary_min && job.salary_max 
                      ? `₹${(job.salary_min/100000).toFixed(1)}L - ₹${(job.salary_max/100000).toFixed(1)}L`
                      : job.salary_min 
                        ? `₹${(job.salary_min/100000).toFixed(1)}L+`
                        : `Up to ₹${(job.salary_max/100000).toFixed(1)}L`
                    }
                  </span>
                </div>
              )}
            </div>
          </CardHeader>
          
          <Separator />
          
          <CardContent className="pt-6">
            {/* Skills */}
            {job.skills && job.skills.length > 0 && (
              <div className="mb-6">
                <h3 className="font-semibold text-gray-900 mb-3">Required Skills</h3>
                <div className="flex flex-wrap gap-2">
                  {job.skills.map((skill, index) => (
                    <Badge key={index} variant="secondary">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            
            {/* Description */}
            <div className="mb-6">
              <h3 className="font-semibold text-gray-900 mb-3">Job Description</h3>
              <div className="prose prose-gray max-w-none">
                <p className="text-gray-700 whitespace-pre-wrap">{job.description}</p>
              </div>
            </div>
            
            {/* Requirements */}
            {job.requirements && (
              <div className="mb-6">
                <h3 className="font-semibold text-gray-900 mb-3">Requirements</h3>
                <div className="prose prose-gray max-w-none">
                  <p className="text-gray-700 whitespace-pre-wrap">{job.requirements}</p>
                </div>
              </div>
            )}
            
            {/* Apply Button */}
            {!showApplyForm && (
              <Button 
                size="lg" 
                className="w-full md:w-auto mt-4"
                onClick={() => setShowApplyForm(true)}
                data-testid="apply-now-btn"
              >
                Apply Now
              </Button>
            )}
          </CardContent>
        </Card>

        {/* Application Form */}
        {showApplyForm && (
          <Card data-testid="application-form">
            <CardHeader>
              <CardTitle className="text-xl">Apply for this Position</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* Resume Upload */}
                <div className="space-y-2">
                  <Label htmlFor="resume">Resume/CV *</Label>
                  <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 transition-colors">
                    <input
                      type="file"
                      id="resume"
                      accept=".pdf,.doc,.docx"
                      onChange={handleFileChange}
                      className="hidden"
                    />
                    <label htmlFor="resume" className="cursor-pointer">
                      {resumeFile ? (
                        <div className="flex items-center justify-center gap-2 text-green-600">
                          <CheckCircle2 className="h-5 w-5" />
                          <span>{resumeFile.name}</span>
                        </div>
                      ) : (
                        <>
                          <Upload className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                          <p className="text-gray-600">Click to upload your resume</p>
                          <p className="text-sm text-gray-400">PDF or Word (Max 5MB)</p>
                        </>
                      )}
                    </label>
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  {/* Name */}
                  <div className="space-y-2">
                    <Label htmlFor="name">Full Name *</Label>
                    <Input
                      id="name"
                      name="name"
                      value={formData.name}
                      onChange={handleInputChange}
                      placeholder="Enter your full name"
                      required
                    />
                  </div>

                  {/* Email */}
                  <div className="space-y-2">
                    <Label htmlFor="email">Email Address *</Label>
                    <Input
                      id="email"
                      name="email"
                      type="email"
                      value={formData.email}
                      onChange={handleInputChange}
                      placeholder="your@email.com"
                      required
                    />
                  </div>

                  {/* Phone */}
                  <div className="space-y-2">
                    <Label htmlFor="phone">Phone Number</Label>
                    <Input
                      id="phone"
                      name="phone"
                      type="tel"
                      value={formData.phone}
                      onChange={handleInputChange}
                      placeholder="+91 XXXXX XXXXX"
                    />
                  </div>

                  {/* Current Salary */}
                  <div className="space-y-2">
                    <Label htmlFor="current_salary">Current Salary (INR per annum)</Label>
                    <Input
                      id="current_salary"
                      name="current_salary"
                      type="number"
                      value={formData.current_salary}
                      onChange={handleInputChange}
                      placeholder="e.g., 1200000"
                    />
                  </div>

                  {/* Notice Period */}
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="notice_period">Notice Period</Label>
                    <Select
                      value={formData.notice_period}
                      onValueChange={(value) => setFormData(prev => ({ ...prev, notice_period: value }))}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select notice period" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="immediate">Immediate</SelectItem>
                        <SelectItem value="15 days">15 Days</SelectItem>
                        <SelectItem value="30 days">30 Days</SelectItem>
                        <SelectItem value="60 days">60 Days</SelectItem>
                        <SelectItem value="90 days">90 Days</SelectItem>
                        <SelectItem value="90+ days">More than 90 Days</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* DPDP Consent Block */}
                <div className="space-y-3 p-4 bg-gray-50 rounded-lg border border-slate-200" data-testid="consent-block">
                  <div className="flex items-start gap-3">
                    <Checkbox
                      id="consent"
                      checked={formData.consent_given}
                      onCheckedChange={(checked) => setFormData(prev => ({ ...prev, consent_given: checked }))}
                      data-testid="consent-checkbox"
                    />
                    <Label htmlFor="consent" className="text-xs text-gray-600 leading-relaxed cursor-pointer">
                      I consent to Ventures HRD collecting and processing my personal data including resume, contact details, and professional information for recruitment purposes under the Digital Personal Data Protection Act, 2023. I understand I can withdraw consent at any time by contacting <span className="text-emerald-700">privacy@vhc.in</span>.<span className="text-red-500 ml-0.5">*</span>
                    </Label>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-slate-400">
                    <a href="/privacy-policy" target="_blank" rel="noopener" className="underline hover:text-slate-600">Privacy Policy</a>
                    <a href="/terms-of-use" target="_blank" rel="noopener" className="underline hover:text-slate-600">Terms of Use</a>
                  </div>
                </div>

                {/* CAPTCHA */}
                {isTurnstileEnabled && (
                  <div data-testid="public-job-turnstile-container">
                    <TurnstileWidget
                      onVerify={setTurnstileToken}
                      onExpire={() => setTurnstileToken('')}
                      className="mb-2"
                    />
                  </div>
                )}

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
                    disabled={submitting || !formData.consent_given || (isTurnstileEnabled && !turnstileToken)}
                    className="flex-1"
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
            </CardContent>
          </Card>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t mt-12 py-6">
        <div className="max-w-4xl mx-auto px-4 text-center text-gray-500 text-sm space-y-2">
          <p>© {new Date().getFullYear()} Ventures HRD. All rights reserved.</p>
          <div className="flex items-center justify-center gap-4 text-xs">
            <a href="/privacy-policy" className="hover:text-slate-700 underline underline-offset-2">Privacy Policy</a>
            <a href="/terms-of-use" className="hover:text-slate-700 underline underline-offset-2">Terms of Use</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
