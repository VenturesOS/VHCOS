import "@/App.css";
import React, { Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { AuthProvider } from "./lib/auth";
import { Toaster } from "./components/ui/sonner";
import GoogleAnalytics from "./components/GoogleAnalytics";
import { BatchUploadProvider } from "./contexts/BatchUploadContext";
import { BatchUploadWidget } from "./components/shared/BatchUploadWidget";

// ── Loading fallback ──
const PageLoader = () => (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "#fafafa" }}>
    <div style={{ textAlign: "center" }}>
      <div style={{ width: 36, height: 36, border: "3px solid #e5e7eb", borderTop: "3px solid #2563eb", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
      <p style={{ color: "#6b7280", fontSize: 14 }}>Loading...</p>
    </div>
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
);

// ── Auth Pages (keep static — needed immediately) ──
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import PasswordReset from "./pages/auth/PasswordReset";
import ForgotPassword from "./pages/auth/ForgotPassword";

// ── Public Website (keep static — landing page) ──
import PublicWebsiteRedirect from "./pages/PublicWebsite";
import StaticPageRedirect from "./components/StaticPageRedirect";

// ── Layout (keep static — wraps all dashboard routes) ──
import DashboardLayout from "./components/layout/DashboardLayout";
import CookieConsentBanner from "./components/compliance/CookieConsentBanner";

// ── Public Pages (lazy — not always needed) ──
const PublicJobPage = React.lazy(() => import("./pages/public/PublicJobPage"));
const ApplicationSuccessPage = React.lazy(() => import("./pages/public/ApplicationSuccessPage"));
const MandateApplyPage = React.lazy(() => import("./pages/public/MandateApplyPage"));
const PillarPage = React.lazy(() => import("./pages/public/PillarPage"));
const BlogPages = React.lazy(() => import("./pages/public/BlogPages"));

// Blog components need named exports — wrap them
const LazyEmployerBlogList = React.lazy(() => import("./pages/public/BlogPages").then(m => ({ default: m.EmployerBlogList })));
const LazyEmployerBlogArticle = React.lazy(() => import("./pages/public/BlogPages").then(m => ({ default: m.EmployerBlogArticle })));
const LazyCandidateBlogArticle = React.lazy(() => import("./pages/public/BlogPages").then(m => ({ default: m.CandidateBlogArticle })));

// Policy pages
const PolicyPages = React.lazy(() => import("./pages/policy/PolicyPages"));
const LazyPrivacyPolicy = React.lazy(() => import("./pages/policy/PolicyPages").then(m => ({ default: m.PrivacyPolicyPage })));
const LazyTermsOfUse = React.lazy(() => import("./pages/policy/PolicyPages").then(m => ({ default: m.TermsOfUsePage })));
const LazyCookiePolicy = React.lazy(() => import("./pages/policy/PolicyPages").then(m => ({ default: m.CookiePolicyPage })));

// ── Admin Pages (lazy) ──
const AdminDashboard = React.lazy(() => import("./pages/admin/AdminDashboard"));
const UsersPage = React.lazy(() => import("./pages/admin/UsersPage"));
const AdminJobsPage = React.lazy(() => import("./pages/admin/JobsPage"));
const CompaniesPage = React.lazy(() => import("./pages/admin/CompaniesPage"));
const DataQualityPage = React.lazy(() => import("./pages/admin/DataQualityPage"));
const AdminPipelinePage = React.lazy(() => import("./pages/admin/AdminPipelinePage"));
const BatchUploadPage = React.lazy(() => import("./pages/admin/BatchUploadPage"));
const AdminAnalyticsPage = React.lazy(() => import("./pages/admin/AdminAnalyticsPage"));
const DigestEmailPage = React.lazy(() => import("./pages/admin/DigestEmailPage"));
const RevenueDashboardPage = React.lazy(() => import("./pages/admin/RevenueDashboardPage"));
const SalaryBenchmarkPage = React.lazy(() => import("./pages/admin/SalaryBenchmarkPage"));
const ContactSubmissionsPage = React.lazy(() => import("./pages/admin/ContactSubmissionsPage"));
const SubmissionTrackerPage = React.lazy(() => import("./pages/admin/SubmissionTrackerPage"));
const HiringFunnelPage = React.lazy(() => import("./pages/admin/HiringFunnelPage"));
const AdvancedSearchPage = React.lazy(() => import("./pages/shared/AdvancedSearchPage"));
const CompanyProfilePage = React.lazy(() => import("./pages/admin/CompanyProfilePage"));
// Tab wrapper pages (merged sidebar items)
const CandidateBankTabsPage = React.lazy(() => import("./pages/admin/CandidateBankTabsPage"));
const NaukriImportTabsPage = React.lazy(() => import("./pages/admin/NaukriImportTabsPage"));
const TeamsTabsPage = React.lazy(() => import("./pages/admin/TeamsTabsPage"));
const BlogTabsPage = React.lazy(() => import("./pages/admin/BlogTabsPage"));
const ActivityTabsPage = React.lazy(() => import("./pages/admin/ActivityTabsPage"));
const SystemHealthTabsPage = React.lazy(() => import("./pages/admin/SystemHealthTabsPage"));
const SecurityTabsPage = React.lazy(() => import("./pages/admin/SecurityTabsPage"));
const AttendanceTabsPage = React.lazy(() => import("./pages/admin/AttendanceTabsPage"));
const SettingsTabsPage = React.lazy(() => import("./pages/admin/SettingsTabsPage"));

// ── Recruiter Pages (lazy) ──
const RecruiterDashboard = React.lazy(() => import("./pages/recruiter/RecruiterDashboard"));
const RecruiterJobsPage = React.lazy(() => import("./pages/recruiter/RecruiterJobsPage"));
const PipelinePage = React.lazy(() => import("./pages/recruiter/PipelinePage"));
const RecruiterCandidatesPage = React.lazy(() => import("./pages/recruiter/RecruiterCandidatesPage"));
const RecruiterReferralsPage = React.lazy(() => import("./pages/recruiter/RecruiterReferralsPage"));
const RecruiterCandidateBankPage = React.lazy(() => import("./pages/recruiter/RecruiterCandidateBankPage"));

// ── Employer Pages (lazy) ──
const EmployerDashboard = React.lazy(() => import("./pages/employer/EmployerDashboard"));
const EmployerJobsPage = React.lazy(() => import("./pages/employer/EmployerJobsPage"));
const CreateJobPage = React.lazy(() => import("./pages/employer/CreateJobPage"));
const ApplicantsPage = React.lazy(() => import("./pages/employer/ApplicantsPage"));
const JobApplicantsPage = React.lazy(() => import("./pages/employer/JobApplicantsPage"));
const AnalyticsPage = React.lazy(() => import("./pages/employer/AnalyticsPage"));
const FindCandidatesPage = React.lazy(() => import("./pages/employer/FindCandidatesPage"));
const JobApprovalPage = React.lazy(() => import("./pages/employer/JobApprovalPage"));
const EmployerCandidateBankPage = React.lazy(() => import("./pages/employer/EmployerCandidateBankPage"));
const EmployerAnalyticsPage = React.lazy(() => import("./pages/employer/EmployerAnalyticsPage"));
const EmployerMyTeamPage = React.lazy(() => import("./pages/employer/EmployerMyTeamPage"));
const EmployerCompaniesPage = React.lazy(() => import("./pages/employer/EmployerCompaniesPage"));
const EmployerPipelinePage = React.lazy(() => import("./pages/employer/EmployerPipelinePage"));
const EmployerTeamAttendancePage = React.lazy(() => import("./pages/employer/EmployerTeamAttendancePage"));
const EmployerReportsPage = React.lazy(() => import("./pages/employer/EmployerReportsPage"));

// ── Shared Pages (lazy) ──
const MatchHistoryPage = React.lazy(() => import("./pages/shared/MatchHistoryPage"));
const NaukriProfileView = React.lazy(() => import("./pages/shared/NaukriProfileView"));
const AttendancePage = React.lazy(() => import("./pages/shared/AttendancePage"));
const LeaveManagementPage = React.lazy(() => import("./pages/shared/LeaveManagementPage"));
const ResumeBuilderPage = React.lazy(() => import("./pages/shared/ResumeBuilderPage"));
const ActivityFeedPage = React.lazy(() => import("./pages/shared/ActivityFeedPage"));

// ── Pages shared across multiple roles (used by recruiter/employer/accounts) ──
const LinkedInSettingsPage = React.lazy(() => import("./pages/admin/LinkedInSettingsPage"));
const AttendanceInsightsPage = React.lazy(() => import("./pages/admin/AttendanceInsightsPage"));
const AdminAttendancePage = React.lazy(() => import("./pages/admin/AdminAttendancePage"));
const AdminLeaveManagementPage = React.lazy(() => import("./pages/admin/AdminLeaveManagementPage"));
const AttendanceSettingsPage = React.lazy(() => import("./pages/admin/AttendanceSettingsPage"));

// ── Candidate Pages (lazy) ──
const CandidateDashboard = React.lazy(() => import("./pages/candidate/CandidateDashboard"));
const ProfilePage = React.lazy(() => import("./pages/candidate/ProfilePage"));
const BrowseJobsPage = React.lazy(() => import("./pages/candidate/BrowseJobsPage"));
const ApplicationsPage = React.lazy(() => import("./pages/candidate/ApplicationsPage"));
const MessagesPage = React.lazy(() => import("./pages/candidate/MessagesPage"));
const MatchingJobsPage = React.lazy(() => import("./pages/candidate/MatchingJobsPage"));
const NotificationSettingsPage = React.lazy(() => import("./pages/candidate/NotificationSettingsPage"));

// ── Account Manager Pages (lazy) ──
const AccountManagerDashboard = React.lazy(() => import("./pages/account-manager/AccountManagerDashboard"));
const CompanyDetailPage = React.lazy(() => import("./pages/account-manager/CompanyDetailPage"));
const AMCreateJobPage = React.lazy(() => import("./pages/account-manager/AMCreateJobPage"));

// ── Settings (lazy) ──
const NotificationPreferencesPage = React.lazy(() => import("./pages/settings/NotificationPreferencesPage"));

// ── Accounts Pages (lazy) ──
const AccountsDashboard = React.lazy(() => import("./pages/accounts/AccountsDashboard"));
const InvoicePage = React.lazy(() => import("./pages/accounts/InvoicePage"));
const ClientBillingPage = React.lazy(() => import("./pages/accounts/ClientBillingPage"));
const ExpenseTrackingPage = React.lazy(() => import("./pages/accounts/ExpenseTrackingPage"));
const AccountsRevenueDashboard = React.lazy(() => import("./pages/accounts/RevenueDashboardPage"));
const FinancialReportsPage = React.lazy(() => import("./pages/accounts/FinancialReportsPage"));

function App() {
  return (
    <HelmetProvider>
    <AuthProvider>
      <BrowserRouter>
      <BatchUploadProvider>
        <GoogleAnalytics />
        <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Public Routes (No Auth Required) */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/reset-password" element={<PasswordReset />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          
          {/* Public Job Pages - Shareable Links */}
          <Route path="/jobs/:jobId" element={<PublicJobPage />} />
          <Route path="/apply/mandate/:jobId" element={<MandateApplyPage />} />
          <Route path="/application-success" element={<ApplicationSuccessPage />} />

          {/* SEO Pillar Pages */}
          <Route path="/industrial-recruitment" element={<PillarPage />} />
          <Route path="/hr-consulting-services" element={<PillarPage />} />

          {/* Public Blog Routes */}
          <Route path="/industrial-hiring-insights" element={<LazyEmployerBlogList />} />
          <Route path="/industrial-hiring-insights/:slug" element={<LazyEmployerBlogArticle />} />
          <Route path="/career-insights" element={<PillarPage />} />
          <Route path="/career-insights/:slug" element={<LazyCandidateBlogArticle />} />

          {/* Admin Routes */}
          <Route path="/admin" element={<DashboardLayout allowedRoles={["admin"]} />}>
            <Route index element={<AdminDashboard />} />
            <Route path="analytics" element={<AdminAnalyticsPage />} />
            <Route path="salary-benchmark" element={<SalaryBenchmarkPage />} />
            <Route path="find-candidates" element={<FindCandidatesPage />} />
            <Route path="advanced-search" element={<AdvancedSearchPage />} />
            <Route path="company-profile/:companyId" element={<CompanyProfilePage />} />
            <Route path="match-history" element={<MatchHistoryPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="jobs" element={<AdminJobsPage />} />
            <Route path="jobs/new" element={<CreateJobPage />} />
            <Route path="jobs/:jobId/applicants" element={<JobApplicantsPage />} />
            <Route path="candidate-bank" element={<CandidateBankTabsPage />} />
            <Route path="candidate-bank/batch-upload" element={<BatchUploadPage />} />
            <Route path="candidate-bank/data-quality" element={<DataQualityPage />} />
            <Route path="companies" element={<CompaniesPage />} />
            <Route path="teams" element={<TeamsTabsPage />} />
            <Route path="pipeline" element={<AdminPipelinePage />} />
            <Route path="revenue" element={<RevenueDashboardPage />} />
            <Route path="settings" element={<SettingsTabsPage />} />
            <Route path="bulk-import" element={<NaukriImportTabsPage />} />
            <Route path="system-health" element={<SystemHealthTabsPage />} />
            <Route path="security-audit" element={<SecurityTabsPage />} />
            <Route path="contact-submissions" element={<ContactSubmissionsPage />} />
            <Route path="blog-engine" element={<BlogTabsPage />} />
            <Route path="digest-email" element={<DigestEmailPage />} />
            <Route path="submission-tracker" element={<SubmissionTrackerPage />} />
            <Route path="hiring-funnel" element={<HiringFunnelPage />} />
            <Route path="attendance" element={<AttendanceTabsPage />} />
            <Route path="naukri-profile/:candidateId" element={<NaukriProfileView />} />
            <Route path="activity-monitor" element={<ActivityTabsPage />} />
            <Route path="settings/notifications" element={<NotificationPreferencesPage />} />
          </Route>

          {/* Recruiter Routes */}
          <Route path="/recruiter" element={<DashboardLayout allowedRoles={["recruiter"]} />}>
            <Route index element={<RecruiterDashboard />} />
            <Route path="jobs" element={<RecruiterJobsPage />} />
            <Route path="jobs/new" element={<CreateJobPage />} />
            <Route path="jobs/:jobId/applicants" element={<JobApplicantsPage />} />
            <Route path="pipeline" element={<PipelinePage />} />
            <Route path="referrals" element={<RecruiterReferralsPage />} />
            <Route path="candidate-bank" element={<RecruiterCandidateBankPage />} />
            <Route path="candidate-bank/batch-upload" element={<BatchUploadPage />} />
            <Route path="candidates" element={<RecruiterCandidatesPage />} />
            <Route path="find-candidates" element={<FindCandidatesPage />} />
            <Route path="advanced-search" element={<AdvancedSearchPage />} />
            <Route path="match-history" element={<MatchHistoryPage />} />
            <Route path="naukri-profile/:candidateId" element={<NaukriProfileView />} />
            <Route path="submission-tracker" element={<SubmissionTrackerPage />} />
            <Route path="attendance" element={<AttendancePage />} />
            <Route path="leaves" element={<LeaveManagementPage />} />
            <Route path="resume-builder" element={<ResumeBuilderPage />} />
            <Route path="activity-feed" element={<ActivityFeedPage />} />
            <Route path="linkedin-settings" element={<LinkedInSettingsPage />} />
            <Route path="salary-benchmark" element={<SalaryBenchmarkPage />} />
            {/* Account Manager Routes (for recruiters with is_account_manager flag) */}
            <Route path="account-manager" element={<AccountManagerDashboard />} />
            <Route path="account-manager/company/:companyId" element={<CompanyDetailPage />} />
            <Route path="account-manager/company/:companyId/new-job" element={<AMCreateJobPage />} />
            <Route path="settings/notifications" element={<NotificationPreferencesPage />} />
          </Route>

          {/* Employer Routes */}
          <Route path="/employer" element={<DashboardLayout allowedRoles={["employer"]} />}>
            <Route index element={<EmployerDashboard />} />
            <Route path="analytics" element={<EmployerAnalyticsPage />} />
            <Route path="my-team" element={<EmployerMyTeamPage />} />
            <Route path="companies" element={<EmployerCompaniesPage />} />
            <Route path="pipeline" element={<EmployerPipelinePage />} />
            <Route path="submission-tracker" element={<SubmissionTrackerPage />} />
            <Route path="jobs" element={<EmployerJobsPage />} />
            <Route path="jobs/new" element={<CreateJobPage />} />
            <Route path="jobs/:jobId/applicants" element={<JobApplicantsPage />} />
            <Route path="applicants" element={<ApplicantsPage />} />
            <Route path="approvals" element={<JobApprovalPage />} />
            <Route path="find-candidates" element={<FindCandidatesPage />} />
            <Route path="advanced-search" element={<AdvancedSearchPage />} />
            <Route path="match-history" element={<MatchHistoryPage />} />
            <Route path="candidate-bank" element={<EmployerCandidateBankPage />} />
            <Route path="candidate-bank/batch-upload" element={<BatchUploadPage />} />
            <Route path="naukri-profile/:candidateId" element={<NaukriProfileView />} />
            <Route path="attendance" element={<AttendancePage />} />
            <Route path="team-attendance" element={<EmployerTeamAttendancePage />} />
            <Route path="leaves" element={<LeaveManagementPage />} />
            <Route path="attendance-insights" element={<AttendanceInsightsPage />} />
            <Route path="reports" element={<EmployerReportsPage />} />
            <Route path="resume-builder" element={<ResumeBuilderPage />} />
            <Route path="activity-feed" element={<ActivityFeedPage />} />
            <Route path="linkedin-settings" element={<LinkedInSettingsPage />} />
            <Route path="salary-benchmark" element={<SalaryBenchmarkPage />} />
            <Route path="settings/notifications" element={<NotificationPreferencesPage />} />
            {/* Account Manager Routes (for employers) */}
            <Route path="account-manager" element={<AccountManagerDashboard />} />
            <Route path="account-manager/company/:companyId" element={<CompanyDetailPage />} />
            <Route path="account-manager/company/:companyId/new-job" element={<AMCreateJobPage />} />
          </Route>

          {/* Accounts Routes */}
          <Route path="/accounts" element={<DashboardLayout allowedRoles={["accounts"]} />}>
            <Route index element={<AccountsDashboard />} />
            <Route path="invoices" element={<InvoicePage />} />
            <Route path="clients" element={<ClientBillingPage />} />
            <Route path="expenses" element={<ExpenseTrackingPage />} />
            <Route path="revenue" element={<AccountsRevenueDashboard />} />
            <Route path="reports" element={<FinancialReportsPage />} />
            <Route path="my-attendance" element={<AttendancePage />} />
            <Route path="attendance" element={<AdminAttendancePage />} />
            <Route path="leave-management" element={<AdminLeaveManagementPage />} />
            <Route path="attendance-insights" element={<AttendanceInsightsPage />} />
            <Route path="attendance-settings" element={<AttendanceSettingsPage />} />
          </Route>

          {/* Candidate Routes */}
          <Route path="/candidate" element={<DashboardLayout allowedRoles={["candidate"]} />}>
            <Route index element={<CandidateDashboard />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="resume-builder" element={<ResumeBuilderPage />} />
            <Route path="jobs" element={<BrowseJobsPage />} />
            <Route path="matching-jobs" element={<MatchingJobsPage />} />
            <Route path="applications" element={<ApplicationsPage />} />
            <Route path="messages" element={<MessagesPage />} />
            <Route path="notifications" element={<NotificationSettingsPage />} />
            <Route path="settings/notifications" element={<NotificationPreferencesPage />} />
          </Route>

          {/* Policy Pages */}
          <Route path="/privacy-policy" element={<LazyPrivacyPolicy />} />
          <Route path="/terms-of-use" element={<LazyTermsOfUse />} />
          <Route path="/cookie-policy" element={<LazyCookiePolicy />} />

          {/* Static Website Pages */}
          <Route path="/recruitment-expertise" element={<StaticPageRedirect page="recruitment-expertise.html" />} />
          <Route path="/about" element={<StaticPageRedirect page="about.html" />} />
          <Route path="/services" element={<StaticPageRedirect page="services.html" />} />
          <Route path="/industries" element={<StaticPageRedirect page="industries.html" />} />
          <Route path="/careers" element={<StaticPageRedirect page="careers.html" />} />
          <Route path="/contact" element={<StaticPageRedirect page="contact.html" />} />
          <Route path="/global-hiring" element={<StaticPageRedirect page="global-hiring.html" />} />

          {/* Default Redirect - Public Website is the landing page */}
          <Route path="/" element={<PublicWebsiteRedirect />} />
          <Route path="*" element={<PublicWebsiteRedirect />} />
        </Routes>
        </Suspense>
        <BatchUploadWidget />
      </BatchUploadProvider>
      </BrowserRouter>
      <CookieConsentBanner />
      <Toaster position="top-right" richColors />
    </AuthProvider>
    </HelmetProvider>
  );
}

export default App;
