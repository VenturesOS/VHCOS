import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { jobAPI, matchingAPI, employerPortalAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Separator } from '../../components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import { 
  Briefcase, 
  ArrowLeft, 
  Save, 
  Sparkles, 
  Loader2, 
  X,
  Plus,
  AlertCircle,
  Upload,
  FileUp,
  CheckCircle2,
  Type,
  Building2,
  DollarSign
} from 'lucide-react';

/**
 * CreateJobPage with JD Parsing
 * 
 * JD Parsing Architecture (matches CV Parser pattern):
 * - Single request → single JSON response
 * - Backend handles file extraction + AI parsing in one call
 * - Frontend reads response exactly once
 * - No streaming, no double-read issues
 * 
 * Root cause of previous bug: Response body was being read twice
 * when error handling tried to access response after json() was called.
 */
export default function CreateJobPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [showJdParser, setShowJdParser] = useState(false);
  const [parsedSuggestions, setParsedSuggestions] = useState(null);
  const [skillInput, setSkillInput] = useState('');
  
  // Company selection state
  const [companies, setCompanies] = useState([]);
  const [loadingCompanies, setLoadingCompanies] = useState(true);
  const [selectedCompany, setSelectedCompany] = useState(null);
  
  // JD Parser state
  const [jdInputMode, setJdInputMode] = useState('paste'); // 'paste' or 'upload'
  const [jdText, setJdText] = useState('');
  const [jdFile, setJdFile] = useState(null);
  const [parseError, setParseError] = useState(null);
  
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    requirements: '',
    location: '',
    job_type: '',
    department: '',
    salary_min: '',
    salary_max: '',
    skills: [],
    experience_min: '',
    experience_max: '',
    public_company_alias: '',
    company_id: '',
    company_name: ''
  });

  // Load assigned companies on mount
  useEffect(() => {
    const loadCompanies = async () => {
      try {
        const res = await employerPortalAPI.getMyCompanies();
        setCompanies(res.data.companies || []);
      } catch (error) {
      } finally {
        setLoadingCompanies(false);
      }
    };
    loadCompanies();
  }, []);

  // Handle company selection
  const handleCompanyChange = (companyId) => {
    const company = companies.find(c => c.id === companyId);
    if (company) {
      setSelectedCompany(company);
      setFormData(prev => ({
        ...prev,
        company_id: company.id,
        company_name: company.name
      }));
    }
  };

  const handleChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleAddSkill = () => {
    if (skillInput.trim() && !formData.skills.includes(skillInput.trim())) {
      setFormData(prev => ({
        ...prev,
        skills: [...prev.skills, skillInput.trim()]
      }));
      setSkillInput('');
    }
  };

  const handleRemoveSkill = (skillToRemove) => {
    setFormData(prev => ({
      ...prev,
      skills: prev.skills.filter(skill => skill !== skillToRemove)
    }));
  };

  // Handle file selection for JD upload
  const handleJdFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      const allowedExtensions = ['pdf', 'doc', 'docx'];
      const fileExt = file.name.split('.').pop().toLowerCase();
      
      if (!allowedExtensions.includes(fileExt)) {
        toast.error('Unsupported file format. Please use PDF, DOC, or DOCX');
        setJdFile(null);
        return;
      }
      
      if (file.size > 10 * 1024 * 1024) { // 10MB limit
        toast.error('File size must be less than 10MB');
        setJdFile(null);
        return;
      }
      
      setJdFile(file);
      setParseError(null);
      setParsedSuggestions(null);
    }
  };

  /**
   * Parse JD - Using axios-based API wrapper for reliability
   * 
   * This matches the CV parser architecture:
   * - Uses axios with proper interceptors
   * - Single request → single response
   * - No body stream issues
   */
  const handleParseJD = async () => {
    // Validate input based on mode
    if (jdInputMode === 'paste' && !jdText.trim()) {
      toast.error('Please enter a job description to parse');
      return;
    }
    
    if (jdInputMode === 'upload' && !jdFile) {
      toast.error('Please select a file to parse');
      return;
    }

    setParsing(true);
    setParseError(null);
    setParsedSuggestions(null);
    
    try {
      // Use axios-based API wrapper (matches CV parser pattern)
      const response = await matchingAPI.parseJD(
        jdInputMode === 'paste' ? jdText : null,
        jdInputMode === 'upload' ? jdFile : null,
        jdInputMode
      );
      
      const data = response.data;
      
      // Handle parsing errors from AI
      if (data.success === false) {
        const errorMessage = data.parse_error || 'JD parsing failed';
        setParseError(errorMessage);
        toast.error('Parsing failed: ' + errorMessage);
        return;
      }
      
      // Success - set suggestions
      setParsedSuggestions(data);
      toast.success('JD parsed successfully! Review suggestions below.');
      
    } catch (error) {
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to parse job description';
      setParseError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setParsing(false);
    }
  };

  const applySuggestion = (field, value) => {
    if (field === 'skills' && Array.isArray(value)) {
      setFormData(prev => ({
        ...prev,
        skills: [...new Set([...prev.skills, ...value])]
      }));
    } else if (field === 'requirements' && Array.isArray(value)) {
      const reqText = value.map(r => `• ${r}`).join('\n');
      handleChange('requirements', reqText);
    } else if (field === 'description' && parsedSuggestions?.summary) {
      handleChange('description', parsedSuggestions.summary);
    } else {
      handleChange(field, value);
    }
    toast.success(`Applied suggestion for ${field}`);
  };

  const applyAllSuggestions = () => {
    if (!parsedSuggestions) return;
    
    if (parsedSuggestions.title) handleChange('title', parsedSuggestions.title);
    if (parsedSuggestions.location) handleChange('location', parsedSuggestions.location);
    if (parsedSuggestions.salary_min) handleChange('salary_min', parsedSuggestions.salary_min);
    if (parsedSuggestions.salary_max) handleChange('salary_max', parsedSuggestions.salary_max);
    if (parsedSuggestions.experience_min) handleChange('experience_min', parsedSuggestions.experience_min);
    if (parsedSuggestions.experience_max) handleChange('experience_max', parsedSuggestions.experience_max);
    if (parsedSuggestions.summary) handleChange('description', parsedSuggestions.summary);
    if (parsedSuggestions.requirements?.length) {
      handleChange('requirements', parsedSuggestions.requirements.map(r => `• ${r}`).join('\n'));
    }
    if (parsedSuggestions.skills?.length) {
      setFormData(prev => ({
        ...prev,
        skills: [...new Set([...prev.skills, ...parsedSuggestions.skills])]
      }));
    }
    
    toast.success('Applied all suggestions. Please review before saving.');
    setParsedSuggestions(null);
    setShowJdParser(false);
  };

  const resetParser = () => {
    setJdText('');
    setJdFile(null);
    setParseError(null);
    setParsedSuggestions(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.company_id) {
      toast.error('Please select a client company');
      return;
    }
    
    if (!formData.title || !formData.description || !formData.location || !formData.job_type) {
      toast.error('Please fill in all required fields');
      return;
    }

    setLoading(true);
    try {
      const payload = {
        ...formData,
        salary_min: formData.salary_min ? parseInt(formData.salary_min) : null,
        salary_max: formData.salary_max ? parseInt(formData.salary_max) : null,
        experience_min: formData.experience_min ? parseInt(formData.experience_min) : null,
        experience_max: formData.experience_max ? parseInt(formData.experience_max) : null,
      };
      await jobAPI.create(payload);
      toast.success('Job posted successfully!');
      navigate(-1);
    } catch (error) {
      toast.error('Failed to create job');
    } finally {
      setLoading(false);
    }
  };

  // Check if parse button should be enabled
  const canParse = jdInputMode === 'paste' 
    ? jdText.trim().length > 0 
    : jdFile !== null;

  return (
    <div className="max-w-3xl mx-auto space-y-6" data-testid="create-job-page">
      <Button
        variant="ghost"
        onClick={() => navigate(-1)}
        className="text-slate-600"
      >
        <ArrowLeft className="w-4 h-4 mr-2" /> Back
      </Button>

      {/* JD Parser Section */}
      <Card className="border-blue-200 bg-blue-50/50">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-blue-600" />
              <CardTitle className="text-lg text-blue-900">AI Job Description Parser</CardTitle>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowJdParser(!showJdParser);
                if (!showJdParser) resetParser();
              }}
              className="text-blue-600 border-blue-300"
            >
              {showJdParser ? 'Hide Parser' : 'Use AI Parser'}
            </Button>
          </div>
          <CardDescription className="text-blue-700">
            Paste or upload a job description to auto-fill form fields using AI
          </CardDescription>
        </CardHeader>
        
        {showJdParser && (
          <CardContent className="space-y-4">
            {/* Input Mode Tabs */}
            <Tabs value={jdInputMode} onValueChange={(v) => {
              setJdInputMode(v);
              setParseError(null);
              setParsedSuggestions(null);
            }}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="paste" className="flex items-center gap-2">
                  <Type className="w-4 h-4" />
                  Paste Text
                </TabsTrigger>
                <TabsTrigger value="upload" className="flex items-center gap-2">
                  <FileUp className="w-4 h-4" />
                  Upload File
                </TabsTrigger>
              </TabsList>
              
              {/* Paste Mode */}
              <TabsContent value="paste" className="space-y-4 mt-4">
                <Textarea
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  placeholder="Paste your job description here..."
                  rows={8}
                  className="bg-white"
                  data-testid="jd-paste-input"
                />
                <div className="text-xs text-slate-500">
                  {jdText.length > 0 && `${jdText.length} characters`}
                </div>
              </TabsContent>
              
              {/* Upload Mode */}
              <TabsContent value="upload" className="space-y-4 mt-4">
                <div className="border-2 border-dashed border-blue-300 rounded-lg p-6 text-center bg-white hover:border-blue-400 transition-colors">
                  <input
                    type="file"
                    id="jd-file-upload"
                    accept=".pdf,.doc,.docx"
                    onChange={handleJdFileSelect}
                    className="hidden"
                    data-testid="jd-file-input"
                  />
                  <label htmlFor="jd-file-upload" className="cursor-pointer">
                    {jdFile ? (
                      <div className="flex flex-col items-center gap-2">
                        <div className="flex items-center gap-2 text-green-600">
                          <CheckCircle2 className="h-5 w-5" />
                          <span className="font-medium">{jdFile.name}</span>
                        </div>
                        <span className="text-xs text-slate-500">
                          {(jdFile.size / 1024).toFixed(1)} KB
                        </span>
                        <span className="text-xs text-blue-600 underline">Click to change file</span>
                      </div>
                    ) : (
                      <>
                        <Upload className="h-8 w-8 text-blue-400 mx-auto mb-2" />
                        <p className="text-slate-600 font-medium">Click to upload JD file</p>
                        <p className="text-sm text-slate-400 mt-1">PDF, DOC, or DOCX (Max 10MB)</p>
                      </>
                    )}
                  </label>
                </div>
                
                {jdFile && (
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => {
                      setJdFile(null);
                      setParseError(null);
                      setParsedSuggestions(null);
                    }}
                    className="text-slate-600"
                  >
                    <X className="w-4 h-4 mr-1" />
                    Remove File
                  </Button>
                )}
              </TabsContent>
            </Tabs>
            
            {/* Error Display */}
            {parseError && (
              <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded border border-red-200">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{parseError}</span>
              </div>
            )}
            
            {/* Parse Button */}
            <div className="flex gap-2 pt-2">
              <Button 
                onClick={handleParseJD} 
                disabled={parsing || !canParse}
                className="bg-blue-600 hover:bg-blue-700 flex-1"
                data-testid="parse-jd-btn"
              >
                {parsing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {jdInputMode === 'upload' ? 'Extracting & Parsing...' : 'Parsing...'}
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 mr-2" />
                    Parse JD
                  </>
                )}
              </Button>
            </div>

            {/* Parsed Suggestions */}
            {parsedSuggestions && (
              <div className="mt-4 p-4 bg-white rounded-lg border border-blue-200 space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-blue-900">Suggested Fields</h4>
                  <Button size="sm" onClick={applyAllSuggestions} data-testid="apply-all-suggestions-btn">
                    Apply All
                  </Button>
                </div>
                
                <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 p-2 rounded">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>Review suggestions before applying - AI parsing is advisory only. No auto-save.</span>
                </div>
                
                {/* Audit info */}
                {parsedSuggestions.input_type && (
                  <div className="text-xs text-slate-500 bg-slate-50 p-2 rounded">
                    Parsed via {parsedSuggestions.input_type === 'upload' ? 'file upload' : 'text paste'} 
                    {parsedSuggestions.parsed_by_role && ` by ${parsedSuggestions.parsed_by_role}`}
                  </div>
                )}
                
                <div className="grid gap-3 text-sm">
                  {parsedSuggestions.title && (
                    <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <span><strong>Title:</strong> {parsedSuggestions.title}</span>
                      <Button size="sm" variant="ghost" onClick={() => applySuggestion('title', parsedSuggestions.title)}>
                        Apply
                      </Button>
                    </div>
                  )}
                  {parsedSuggestions.location && (
                    <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <span><strong>Location:</strong> {parsedSuggestions.location}</span>
                      <Button size="sm" variant="ghost" onClick={() => applySuggestion('location', parsedSuggestions.location)}>
                        Apply
                      </Button>
                    </div>
                  )}
                  {parsedSuggestions.skills?.length > 0 && (
                    <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <span><strong>Skills:</strong> {parsedSuggestions.skills.slice(0, 5).join(', ')}{parsedSuggestions.skills.length > 5 ? '...' : ''}</span>
                      <Button size="sm" variant="ghost" onClick={() => applySuggestion('skills', parsedSuggestions.skills)}>
                        Apply
                      </Button>
                    </div>
                  )}
                  {(parsedSuggestions.experience_min || parsedSuggestions.experience_max || parsedSuggestions.experience_years) && (
                    <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <span><strong>Experience:</strong> {parsedSuggestions.experience_min || parsedSuggestions.experience_years || 0}-{parsedSuggestions.experience_max || parsedSuggestions.experience_years || 0} years</span>
                      <Button size="sm" variant="ghost" onClick={() => {
                        const exp = parsedSuggestions.experience_min || parsedSuggestions.experience_years;
                        if (exp) applySuggestion('experience_min', exp);
                        if (parsedSuggestions.experience_max) applySuggestion('experience_max', parsedSuggestions.experience_max);
                      }}>
                        Apply
                      </Button>
                    </div>
                  )}
                  {parsedSuggestions.summary && (
                    <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <span className="flex-1 mr-2"><strong>Summary:</strong> {parsedSuggestions.summary.substring(0, 100)}...</span>
                      <Button size="sm" variant="ghost" onClick={() => applySuggestion('description', parsedSuggestions.summary)}>
                        Apply
                      </Button>
                    </div>
                  )}
                  {parsedSuggestions.requirements?.length > 0 && (
                    <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <span><strong>Requirements:</strong> {parsedSuggestions.requirements.length} items</span>
                      <Button size="sm" variant="ghost" onClick={() => applySuggestion('requirements', parsedSuggestions.requirements)}>
                        Apply
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        )}
      </Card>

      {/* Main Form */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="font-heading text-xl flex items-center gap-2">
            <Briefcase className="w-5 h-5 text-[#7CB342]" />
            Post a New Job
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Client Company Selection */}
            <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-4">
              <div className="flex items-center gap-2 text-slate-700">
                <Building2 className="w-5 h-5 text-[#7CB342]" />
                <span className="font-semibold">Client Company *</span>
              </div>
              
              {loadingCompanies ? (
                <div className="flex items-center gap-2 text-slate-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Loading companies...</span>
                </div>
              ) : companies.length === 0 ? (
                <div className="text-amber-600 text-sm bg-amber-50 p-3 rounded flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  <span>No companies assigned. Please contact admin to assign companies to your account.</span>
                </div>
              ) : (
                <div className="space-y-3">
                  <Select
                    value={formData.company_id}
                    onValueChange={handleCompanyChange}
                    required
                  >
                    <SelectTrigger data-testid="company-select">
                      <SelectValue placeholder="Select client company" />
                    </SelectTrigger>
                    <SelectContent>
                      {companies.map(company => (
                        <SelectItem key={company.id} value={company.id}>
                          <div className="flex items-center gap-2">
                            <Building2 className="w-4 h-4 text-slate-400" />
                            <span>{company.name}</span>
                            {company.industry && (
                              <span className="text-xs text-slate-400">• {company.industry}</span>
                            )}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  
                  {/* Selected Company Commercial Info */}
                  {selectedCompany && selectedCompany.commercial && (
                    <div className="p-3 bg-white rounded border border-slate-200">
                      <div className="flex items-center gap-2 text-sm text-slate-600 mb-2">
                        <DollarSign className="w-4 h-4 text-green-600" />
                        <span className="font-medium">Commercial Terms</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        {selectedCompany.commercial.fee_percentage && (
                          <div>
                            <span className="text-slate-500">Fee:</span>
                            <span className="ml-1 font-medium text-green-700">
                              {selectedCompany.commercial.fee_percentage}%
                            </span>
                          </div>
                        )}
                        {selectedCompany.commercial.payment_terms && (
                          <div>
                            <span className="text-slate-500">Terms:</span>
                            <span className="ml-1">{selectedCompany.commercial.payment_terms}</span>
                          </div>
                        )}
                      </div>
                      {selectedCompany.commercial.commercial_slabs?.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-slate-100">
                          <p className="text-xs text-slate-500">Level-based slabs available</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <Separator />
            
            <div className="space-y-2">
              <Label>Job Title *</Label>
              <Input
                value={formData.title}
                onChange={(e) => handleChange('title', e.target.value)}
                placeholder="e.g., Senior Software Engineer"
                required
                data-testid="job-title-input"
              />
            </div>

            <div className="space-y-2">
              <Label>Company Alias (Public Display)</Label>
              <Input
                value={formData.public_company_alias}
                onChange={(e) => handleChange('public_company_alias', e.target.value)}
                placeholder="e.g., Leading MNC, Fortune 500 Company"
              />
              <p className="text-xs text-slate-500">This name will be shown on public job listings instead of the actual company name</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Location *</Label>
                <Input
                  value={formData.location}
                  onChange={(e) => handleChange('location', e.target.value)}
                  placeholder="e.g., Mumbai, India"
                  required
                  data-testid="job-location-input"
                />
              </div>
              <div className="space-y-2">
                <Label>Job Type *</Label>
                <Select
                  value={formData.job_type}
                  onValueChange={(value) => handleChange('job_type', value)}
                  required
                >
                  <SelectTrigger data-testid="job-type-select">
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="full-time">Full-time</SelectItem>
                    <SelectItem value="part-time">Part-time</SelectItem>
                    <SelectItem value="contract">Contract</SelectItem>
                    <SelectItem value="remote">Remote</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Department</Label>
              <Input
                value={formData.department}
                onChange={(e) => handleChange('department', e.target.value)}
                placeholder="e.g., Engineering, Marketing"
              />
            </div>

            <Separator />

            {/* Skills */}
            <div className="space-y-2">
              <Label>Required Skills</Label>
              <div className="flex gap-2">
                <Input
                  value={skillInput}
                  onChange={(e) => setSkillInput(e.target.value)}
                  placeholder="Add a skill..."
                  onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddSkill())}
                />
                <Button type="button" variant="outline" onClick={handleAddSkill}>
                  <Plus className="w-4 h-4" />
                </Button>
              </div>
              {formData.skills.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {formData.skills.map((skill, index) => (
                    <Badge key={index} variant="secondary" className="pr-1">
                      {skill}
                      <button
                        type="button"
                        onClick={() => handleRemoveSkill(skill)}
                        className="ml-1 hover:bg-slate-300 rounded-full p-0.5"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            {/* Experience */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Min Experience (Years)</Label>
                <Input
                  type="number"
                  min="0"
                  value={formData.experience_min}
                  onChange={(e) => handleChange('experience_min', e.target.value)}
                  placeholder="e.g., 2"
                />
              </div>
              <div className="space-y-2">
                <Label>Max Experience (Years)</Label>
                <Input
                  type="number"
                  min="0"
                  value={formData.experience_max}
                  onChange={(e) => handleChange('experience_max', e.target.value)}
                  placeholder="e.g., 5"
                />
              </div>
            </div>

            {/* Salary */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Salary Min (₹ INR / Year)</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">₹</span>
                  <Input
                    type="number"
                    value={formData.salary_min}
                    onChange={(e) => handleChange('salary_min', e.target.value)}
                    placeholder="e.g., 500000"
                    className="pl-8"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label>Salary Max (₹ INR / Year)</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">₹</span>
                  <Input
                    type="number"
                    value={formData.salary_max}
                    onChange={(e) => handleChange('salary_max', e.target.value)}
                    placeholder="e.g., 1200000"
                    className="pl-8"
                  />
                </div>
              </div>
            </div>

            <Separator />

            <div className="space-y-2">
              <Label>Job Description *</Label>
              <Textarea
                value={formData.description}
                onChange={(e) => handleChange('description', e.target.value)}
                placeholder="Describe the role, responsibilities, and what makes this opportunity exciting..."
                rows={5}
                required
                data-testid="job-description-input"
              />
            </div>

            <div className="space-y-2">
              <Label>Requirements</Label>
              <Textarea
                value={formData.requirements}
                onChange={(e) => handleChange('requirements', e.target.value)}
                placeholder="List the skills, experience, and qualifications required..."
                rows={4}
              />
            </div>

            <div className="flex justify-end gap-3">
              <Button type="button" variant="outline" onClick={() => navigate(-1)}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={loading}
                className="bg-[#7CB342] hover:bg-[#689F38]"
                data-testid="submit-job-btn"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Save className="w-4 h-4 mr-2" />
                )}
                Post Job
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
