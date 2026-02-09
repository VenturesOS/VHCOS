import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { extensionAPI } from '../../lib/api';
import { formatSalaryINR } from '../../lib/currency';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import {
  ArrowLeft, User, Mail, Phone, MapPin, Briefcase, GraduationCap,
  Clock, Globe, Award, FolderOpen, Languages, FileText,
  Building2, Calendar, ExternalLink, ChevronRight
} from 'lucide-react';

function Section({ title, icon: Icon, children, testId }) {
  return (
    <div className="mb-6" data-testid={testId}>
      <h3 className="font-heading text-base font-semibold text-slate-800 flex items-center gap-2 mb-3 pb-2 border-b border-slate-100">
        {Icon && <Icon className="w-4 h-4 text-[#7CB342]" />}
        {title}
      </h3>
      {children}
    </div>
  );
}

function InfoRow({ label, value, icon: Icon }) {
  if (!value && value !== 0) return null;
  return (
    <div className="flex items-start gap-2 py-1.5 text-sm">
      {Icon && <Icon className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />}
      <span className="text-slate-500 min-w-[120px]">{label}</span>
      <span className="text-slate-800 font-medium">{value}</span>
    </div>
  );
}

function TimelineCard({ title, subtitle, duration, description, location, isCurrent }) {
  return (
    <div className="relative pl-6 pb-6 last:pb-0">
      <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full border-2 border-[#7CB342] bg-white" />
      <div className="absolute left-[5px] top-4 bottom-0 w-0.5 bg-slate-200 last:hidden" />
      <div className="bg-slate-50 rounded-lg p-4 border border-slate-100">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-slate-900">{title}</p>
            {subtitle && <p className="text-sm text-slate-600 mt-0.5">{subtitle}</p>}
          </div>
          {isCurrent && <Badge className="bg-[#DCFCE7] text-[#7CB342] text-xs">Current</Badge>}
        </div>
        {duration && <p className="text-xs text-slate-400 mt-1">{duration}</p>}
        {location && <p className="text-xs text-slate-400 flex items-center gap-1"><MapPin className="w-3 h-3" />{location}</p>}
        {description && <p className="text-sm text-slate-600 mt-2">{description}</p>}
      </div>
    </div>
  );
}

export default function NaukriProfileView() {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProfile();
  }, [candidateId]);

  const loadProfile = async () => {
    try {
      const res = await extensionAPI.getProfile(candidateId);
      setProfile(res.data);
    } catch (error) {
      toast.error('Failed to load profile');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="spinner" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="text-center py-20">
        <p className="text-slate-500">Profile not found</p>
        <Button variant="outline" className="mt-4" onClick={() => navigate(-1)}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Go Back
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto" data-testid="naukri-profile-view">
      {/* Back button */}
      <Button variant="ghost" onClick={() => navigate(-1)} className="text-slate-600 hover:text-slate-800 -ml-2" data-testid="back-button">
        <ArrowLeft className="w-4 h-4 mr-1" /> Back to Candidate Bank
      </Button>

      {/* Profile Header */}
      <Card className="border-slate-200 overflow-hidden">
        <div className="bg-gradient-to-r from-slate-800 to-slate-700 px-6 py-5">
          <div className="flex items-center gap-4">
            {profile.photo_url ? (
              <img src={profile.photo_url} alt={profile.name} className="w-16 h-16 rounded-full border-2 border-white object-cover" />
            ) : (
              <div className="w-16 h-16 rounded-full bg-[#7CB342] flex items-center justify-center border-2 border-white">
                <span className="text-white font-bold text-2xl">{profile.name?.charAt(0).toUpperCase()}</span>
              </div>
            )}
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-heading font-bold text-white truncate" data-testid="profile-name">{profile.name}</h1>
              <p className="text-slate-300 text-sm truncate">{profile.designation || profile.headline || ''}</p>
              {profile.current_employer && (
                <p className="text-slate-400 text-sm flex items-center gap-1 mt-0.5">
                  <Building2 className="w-3 h-3" /> {profile.current_employer}
                </p>
              )}
            </div>
            <div className="flex flex-col items-end gap-1">
              <Badge className="bg-[#7CB342] text-white text-xs">Naukri Sourced</Badge>
              {profile.naukri_profile_url && (
                <a href={profile.naukri_profile_url} target="_blank" rel="noopener noreferrer" className="text-xs text-slate-400 hover:text-white flex items-center gap-1">
                  View on Naukri <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Quick info bar */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-slate-100">
          {[
            { icon: Mail, label: profile.email || 'N/A' },
            { icon: Phone, label: profile.phone || 'N/A' },
            { icon: MapPin, label: profile.location || profile.preferred_locations?.[0] || 'N/A' },
            { icon: Clock, label: profile.experience_years ? `${profile.experience_years} yrs exp` : 'N/A' },
            { icon: Briefcase, label: profile.notice_period || 'N/A' },
          ].map((item, i) => (
            <div key={i} className="bg-white px-4 py-2.5 flex items-center gap-2 text-sm">
              <item.icon className="w-4 h-4 text-slate-400 flex-shrink-0" />
              <span className="text-slate-700 truncate">{item.label}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Main content tabs */}
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="mb-4 bg-slate-100">
          <TabsTrigger value="overview" data-testid="tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="experience" data-testid="tab-experience">Experience</TabsTrigger>
          <TabsTrigger value="education" data-testid="tab-education">Education</TabsTrigger>
          <TabsTrigger value="skills" data-testid="tab-skills">Skills</TabsTrigger>
          <TabsTrigger value="personal" data-testid="tab-personal">Personal</TabsTrigger>
          <TabsTrigger value="preferences" data-testid="tab-preferences">Preferences</TabsTrigger>
        </TabsList>

        {/* OVERVIEW TAB */}
        <TabsContent value="overview">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left column */}
            <div className="lg:col-span-2 space-y-6">
              {/* Summary */}
              {profile.summary && (
                <Section title="Profile Summary" icon={User} testId="section-summary">
                  <p className="text-sm text-slate-600 leading-relaxed">{profile.summary}</p>
                </Section>
              )}

              {/* Key Skills */}
              {profile.skills?.length > 0 && (
                <Section title="Key Skills" testId="section-skills">
                  <div className="flex flex-wrap gap-1.5">
                    {profile.skills.map((skill, i) => (
                      <Badge key={i} variant="secondary" className="bg-[#DCFCE7] text-[#558B2F] text-xs px-2.5 py-1">{skill}</Badge>
                    ))}
                  </div>
                </Section>
              )}

              {/* Work Experience (top 3) */}
              {profile.experience?.length > 0 && (
                <Section title="Recent Experience" icon={Briefcase} testId="section-recent-exp">
                  {profile.experience.slice(0, 3).map((exp, i) => (
                    <TimelineCard
                      key={i}
                      title={exp.designation || exp.title || 'Role'}
                      subtitle={exp.company}
                      duration={exp.duration || `${exp.from_date || ''} - ${exp.to_date || 'Present'}`}
                      location={exp.location}
                      description={exp.description}
                      isCurrent={exp.is_current}
                    />
                  ))}
                  {profile.experience.length > 3 && (
                    <p className="text-xs text-slate-400 pl-6">+{profile.experience.length - 3} more positions</p>
                  )}
                </Section>
              )}
            </div>

            {/* Right column */}
            <div className="space-y-4">
              {/* Salary Info */}
              <Card className="border-slate-200">
                <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-700">Compensation</CardTitle></CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <InfoRow label="Current CTC" value={profile.current_salary ? formatSalaryINR(profile.current_salary) : null} />
                  <InfoRow label="Expected CTC" value={profile.expected_salary ? formatSalaryINR(profile.expected_salary) : null} />
                  <InfoRow label="Notice Period" value={profile.notice_period} />
                </CardContent>
              </Card>

              {/* Education summary */}
              {(profile.highest_qualification || profile.education?.length > 0) && (
                <Card className="border-slate-200">
                  <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-700">Education</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {profile.highest_qualification && <InfoRow label="Highest" value={profile.highest_qualification} />}
                    {profile.education?.slice(0, 2).map((edu, i) => (
                      <div key={i} className="py-1 border-t border-slate-50 first:border-0">
                        <p className="font-medium text-slate-800">{edu.degree}</p>
                        {edu.institution && <p className="text-slate-500 text-xs">{edu.institution}</p>}
                        {edu.year_of_passing && <p className="text-slate-400 text-xs">{edu.year_of_passing}</p>}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Source info */}
              <Card className="border-slate-200">
                <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-700">Source Details</CardTitle></CardHeader>
                <CardContent className="space-y-1 text-xs text-slate-500">
                  <p>Captured by: {profile.source_details?.captured_by_name || 'N/A'}</p>
                  <p>Captured at: {profile.source_details?.captured_at ? new Date(profile.source_details.captured_at).toLocaleString() : 'N/A'}</p>
                  <p>Extension v{profile.source_details?.extension_version || '2.0.0'}</p>
                  {profile.naukri_profile_updated && <p>Naukri Updated: {profile.naukri_profile_updated}</p>}
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        {/* EXPERIENCE TAB */}
        <TabsContent value="experience">
          <Section title="Work Experience" icon={Briefcase} testId="section-work-experience">
            {profile.experience?.length > 0 ? (
              profile.experience.map((exp, i) => (
                <TimelineCard
                  key={i}
                  title={exp.designation || exp.title || 'Role'}
                  subtitle={exp.company}
                  duration={exp.duration || `${exp.from_date || ''} - ${exp.to_date || 'Present'}`}
                  location={exp.location}
                  description={exp.description}
                  isCurrent={exp.is_current}
                />
              ))
            ) : (
              <p className="text-slate-400 text-sm text-center py-8">No work experience data captured</p>
            )}
          </Section>
        </TabsContent>

        {/* EDUCATION TAB */}
        <TabsContent value="education">
          <Section title="Education" icon={GraduationCap} testId="section-education">
            {profile.education?.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {profile.education.map((edu, i) => (
                  <Card key={i} className="border-slate-200">
                    <CardContent className="p-4">
                      <p className="font-semibold text-slate-900">{edu.degree || 'Degree'}</p>
                      {edu.specialization && <p className="text-sm text-[#7CB342]">{edu.specialization}</p>}
                      {edu.institution && <p className="text-sm text-slate-600 mt-1">{edu.institution}</p>}
                      {edu.university && <p className="text-xs text-slate-400">{edu.university}</p>}
                      <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                        {edu.year_of_passing && <span>{edu.year_of_passing}</span>}
                        {edu.score && <span>Score: {edu.score}</span>}
                        {edu.degree_type && <Badge variant="outline" className="text-xs">{edu.degree_type}</Badge>}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : (
              <p className="text-slate-400 text-sm text-center py-8">No education data captured</p>
            )}

            {/* Certifications */}
            {profile.certifications_detailed?.length > 0 && (
              <Section title="Certifications" icon={Award} testId="section-certifications">
                <div className="space-y-2">
                  {profile.certifications_detailed.map((cert, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                      <Award className="w-5 h-5 text-amber-500 flex-shrink-0" />
                      <div>
                        <p className="font-medium text-sm text-slate-800">{cert.name}</p>
                        {cert.issuing_authority && <p className="text-xs text-slate-500">{cert.issuing_authority}</p>}
                        {cert.issue_date && <p className="text-xs text-slate-400">{cert.issue_date}</p>}
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </Section>
        </TabsContent>

        {/* SKILLS TAB */}
        <TabsContent value="skills">
          {/* Key Skills */}
          {profile.skills?.length > 0 && (
            <Section title="Key Skills" testId="section-key-skills">
              <div className="flex flex-wrap gap-2">
                {profile.skills.map((skill, i) => (
                  <Badge key={i} variant="secondary" className="bg-[#DCFCE7] text-[#558B2F] px-3 py-1.5">{skill}</Badge>
                ))}
              </div>
            </Section>
          )}

          {/* IT Skills table */}
          {profile.it_skills?.length > 0 && (
            <Section title="IT / Technical Skills" testId="section-it-skills">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 text-left">
                      <th className="px-4 py-2 font-medium text-slate-600">Skill</th>
                      <th className="px-4 py-2 font-medium text-slate-600">Version</th>
                      <th className="px-4 py-2 font-medium text-slate-600">Last Used</th>
                      <th className="px-4 py-2 font-medium text-slate-600">Experience</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {profile.it_skills.map((skill, i) => (
                      <tr key={i} className="hover:bg-slate-50">
                        <td className="px-4 py-2 font-medium text-slate-800">{skill.name}</td>
                        <td className="px-4 py-2 text-slate-600">{skill.version || '-'}</td>
                        <td className="px-4 py-2 text-slate-600">{skill.last_used || '-'}</td>
                        <td className="px-4 py-2 text-slate-600">{skill.experience_years ? `${skill.experience_years} yrs` : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}

          {/* Languages */}
          {profile.languages?.length > 0 && (
            <Section title="Languages" icon={Languages} testId="section-languages">
              <div className="flex flex-wrap gap-2">
                {profile.languages.map((lang, i) => (
                  <div key={i} className="px-3 py-2 bg-slate-50 rounded-lg border border-slate-100 text-sm">
                    <span className="font-medium text-slate-800">{lang.language}</span>
                    {lang.proficiency && <span className="text-slate-400 ml-1">({lang.proficiency})</span>}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Projects */}
          {profile.projects?.length > 0 && (
            <Section title="Projects" icon={FolderOpen} testId="section-projects">
              <div className="space-y-3">
                {profile.projects.map((proj, i) => (
                  <Card key={i} className="border-slate-200">
                    <CardContent className="p-4">
                      <p className="font-semibold text-slate-900">{proj.title}</p>
                      {proj.role && <p className="text-sm text-[#7CB342]">Role: {proj.role}</p>}
                      {proj.client && <p className="text-xs text-slate-500">Client: {proj.client}</p>}
                      {proj.description && <p className="text-sm text-slate-600 mt-2">{proj.description}</p>}
                      {proj.status && <Badge variant="outline" className="mt-2 text-xs">{proj.status}</Badge>}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </Section>
          )}

          {(!profile.skills?.length && !profile.it_skills?.length) && (
            <p className="text-slate-400 text-sm text-center py-8">No skills data captured</p>
          )}
        </TabsContent>

        {/* PERSONAL TAB */}
        <TabsContent value="personal">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Section title="Personal Details" icon={User} testId="section-personal-details">
              <div className="space-y-1">
                <InfoRow label="Date of Birth" value={profile.date_of_birth} icon={Calendar} />
                <InfoRow label="Age" value={profile.age} />
                <InfoRow label="Gender" value={profile.gender} />
                <InfoRow label="Marital Status" value={profile.marital_status} />
                <InfoRow label="Nationality" value={profile.nationality} />
                <InfoRow label="Category" value={profile.category} />
                <InfoRow label="Passport" value={profile.has_passport ? `Yes${profile.passport_number ? ` (${profile.passport_number})` : ''}` : null} />
                {profile.differently_abled && <InfoRow label="Differently Abled" value="Yes" />}
              </div>
            </Section>

            <Section title="Address" icon={MapPin} testId="section-address">
              <div className="space-y-3">
                {(profile.current_address || profile.current_city) && (
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Current Address</p>
                    <p className="text-sm text-slate-700">
                      {[profile.current_address, profile.current_city, profile.current_state, profile.current_country, profile.current_pincode].filter(Boolean).join(', ')}
                    </p>
                  </div>
                )}
                {(profile.permanent_address || profile.permanent_city) && (
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Permanent Address</p>
                    <p className="text-sm text-slate-700">
                      {[profile.permanent_address, profile.permanent_city, profile.permanent_state, profile.permanent_country, profile.permanent_pincode].filter(Boolean).join(', ')}
                    </p>
                  </div>
                )}
                {!profile.current_address && !profile.current_city && !profile.permanent_address && !profile.permanent_city && (
                  <p className="text-slate-400 text-sm">No address data captured</p>
                )}
              </div>
            </Section>

            {/* Online Profiles */}
            {profile.online_profiles?.length > 0 && (
              <Section title="Online Profiles" icon={Globe} testId="section-online-profiles">
                <div className="space-y-2">
                  {profile.online_profiles.map((op, i) => (
                    <a key={i} href={op.url} target="_blank" rel="noopener noreferrer"
                       className="flex items-center gap-2 p-2 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                      <Globe className="w-4 h-4 text-[#7CB342]" />
                      <span className="font-medium text-slate-700">{op.platform}</span>
                      <ExternalLink className="w-3 h-3 text-slate-400 ml-auto" />
                    </a>
                  ))}
                </div>
              </Section>
            )}
            {profile.linkedin_url && !profile.online_profiles?.some(p => p.platform === 'LinkedIn') && (
              <InfoRow label="LinkedIn" value={<a href={profile.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{profile.linkedin_url}</a>} icon={Globe} />
            )}
          </div>
        </TabsContent>

        {/* PREFERENCES TAB */}
        <TabsContent value="preferences">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Section title="Salary & Notice" testId="section-salary-notice">
              <div className="space-y-1">
                <InfoRow label="Current CTC" value={profile.current_salary ? formatSalaryINR(profile.current_salary) : null} />
                <InfoRow label="Expected CTC" value={profile.expected_salary ? formatSalaryINR(profile.expected_salary) : null} />
                <InfoRow label="Notice Period" value={profile.notice_period} />
                {profile.is_serving_notice && <InfoRow label="Serving Notice" value="Yes" />}
                {profile.last_working_day && <InfoRow label="Last Working Day" value={profile.last_working_day} />}
                {profile.notice_negotiable && <InfoRow label="Negotiable" value="Yes" />}
              </div>
            </Section>

            <Section title="Location Preferences" testId="section-location-prefs">
              <div className="space-y-1">
                <InfoRow label="Current Location" value={profile.location} icon={MapPin} />
                {profile.preferred_locations?.length > 0 && (
                  <div className="py-1.5">
                    <p className="text-sm text-slate-500 mb-1">Preferred Locations</p>
                    <div className="flex flex-wrap gap-1">
                      {profile.preferred_locations.map((loc, i) => (
                        <Badge key={i} variant="outline" className="text-xs">{loc}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {profile.willing_to_relocate && <InfoRow label="Willing to Relocate" value="Yes" />}
              </div>
            </Section>

            <Section title="Industry & Role" testId="section-industry-role">
              <div className="space-y-1">
                <InfoRow label="Industry" value={profile.industry} />
                {profile.preferred_industry?.length > 0 && (
                  <div className="py-1.5">
                    <p className="text-sm text-slate-500 mb-1">Preferred Industry</p>
                    <div className="flex flex-wrap gap-1">
                      {profile.preferred_industry.map((ind, i) => (
                        <Badge key={i} variant="outline" className="text-xs">{ind}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {profile.preferred_functional_area?.length > 0 && (
                  <div className="py-1.5">
                    <p className="text-sm text-slate-500 mb-1">Functional Area</p>
                    <div className="flex flex-wrap gap-1">
                      {profile.preferred_functional_area.map((fa, i) => (
                        <Badge key={i} variant="outline" className="text-xs">{fa}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {profile.preferred_role?.length > 0 && (
                  <div className="py-1.5">
                    <p className="text-sm text-slate-500 mb-1">Preferred Role</p>
                    <div className="flex flex-wrap gap-1">
                      {profile.preferred_role.map((r, i) => (
                        <Badge key={i} variant="outline" className="text-xs">{r}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Section>

            <Section title="Job Type Preferences" testId="section-job-type-prefs">
              <div className="space-y-1">
                {profile.preferred_job_type?.length > 0 && <InfoRow label="Job Type" value={profile.preferred_job_type.join(', ')} />}
                {profile.preferred_employment_type?.length > 0 && <InfoRow label="Employment" value={profile.preferred_employment_type.join(', ')} />}
                {profile.preferred_shift?.length > 0 && <InfoRow label="Shift" value={profile.preferred_shift.join(', ')} />}
                {profile.work_from_home && <InfoRow label="WFH" value="Preferred" />}
                {profile.remote_work_preference && <InfoRow label="Remote" value={profile.remote_work_preference} />}
              </div>
            </Section>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
