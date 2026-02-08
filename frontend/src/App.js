import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./lib/auth";
import { Toaster } from "./components/ui/sonner";

// Auth Pages
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import PasswordReset from "./pages/auth/PasswordReset";

// Public Website Redirect
import PublicWebsiteRedirect from "./pages/PublicWebsite";

// Public Job Pages (No Auth Required)
import PublicJobPage from "./pages/public/PublicJobPage";
import ApplicationSuccessPage from "./pages/public/ApplicationSuccessPage";
import MandateApplyPage from "./pages/public/MandateApplyPage";

// Layout
import DashboardLayout from "./components/layout/DashboardLayout";

// Admin Pages
import AdminDashboard from "./pages/admin/AdminDashboard";
import UsersPage from "./pages/admin/UsersPage";
import AdminJobsPage from "./pages/admin/JobsPage";
import AdminCandidatesPage from "./pages/admin/CandidatesPage";
import CompaniesPage from "./pages/admin/CompaniesPage";
import SettingsPage from "./pages/admin/SettingsPage";
import CandidateDataBankPage from "./pages/admin/CandidateDataBankPage";
import AdminPipelinePage from "./pages/admin/AdminPipelinePage";
import BatchUploadPage from "./pages/admin/BatchUploadPage";
import BulkImportPage from "./pages/admin/BulkImportPage";
import ImportHistoryPage from "./pages/admin/ImportHistoryPage";
import TeamsPage from "./pages/admin/TeamsPage";
import HierarchyPage from "./pages/admin/HierarchyPage";
import AdminAnalyticsPage from "./pages/admin/AdminAnalyticsPage";
import CommercialsPage from "./pages/admin/CommercialsPage";

// Recruiter Pages
import RecruiterDashboard from "./pages/recruiter/RecruiterDashboard";
import RecruiterJobsPage from "./pages/recruiter/RecruiterJobsPage";
import PipelinePage from "./pages/recruiter/PipelinePage";
import RecruiterCandidatesPage from "./pages/recruiter/RecruiterCandidatesPage";
import RecruiterReferralsPage from "./pages/recruiter/RecruiterReferralsPage";
import RecruiterCandidateBankPage from "./pages/recruiter/RecruiterCandidateBankPage";

// Employer Pages
import EmployerDashboard from "./pages/employer/EmployerDashboard";
import EmployerJobsPage from "./pages/employer/EmployerJobsPage";
import CreateJobPage from "./pages/employer/CreateJobPage";
import ApplicantsPage from "./pages/employer/ApplicantsPage";
import JobApplicantsPage from "./pages/employer/JobApplicantsPage";
import AnalyticsPage from "./pages/employer/AnalyticsPage";
import FindCandidatesPage from "./pages/employer/FindCandidatesPage";
import MatchHistoryPage from "./pages/shared/MatchHistoryPage";
import BugReportsPage from "./pages/admin/BugReportsPage";
import SystemHealthPage from "./pages/admin/SystemHealthPage";
import JobApprovalPage from "./pages/employer/JobApprovalPage";
import EmployerCandidateBankPage from "./pages/employer/EmployerCandidateBankPage";

import EmployerAnalyticsPage from "./pages/employer/EmployerAnalyticsPage";
import EmployerMyTeamPage from "./pages/employer/EmployerMyTeamPage";
import EmployerCompaniesPage from "./pages/employer/EmployerCompaniesPage";
import EmployerPipelinePage from "./pages/employer/EmployerPipelinePage";

// Candidate Pages
import CandidateDashboard from "./pages/candidate/CandidateDashboard";
import ProfilePage from "./pages/candidate/ProfilePage";
import BrowseJobsPage from "./pages/candidate/BrowseJobsPage";
import ApplicationsPage from "./pages/candidate/ApplicationsPage";
import MessagesPage from "./pages/candidate/MessagesPage";
import MatchingJobsPage from "./pages/candidate/MatchingJobsPage";
import NotificationSettingsPage from "./pages/candidate/NotificationSettingsPage";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes (No Auth Required) */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/reset-password" element={<PasswordReset />} />
          
          {/* Public Job Pages - Shareable Links */}
          <Route path="/jobs/:jobId" element={<PublicJobPage />} />
          <Route path="/apply/mandate/:jobId" element={<MandateApplyPage />} />
          <Route path="/application-success" element={<ApplicationSuccessPage />} />

          {/* Admin Routes */}
          <Route path="/admin" element={<DashboardLayout allowedRoles={["admin"]} />}>
            <Route index element={<AdminDashboard />} />
            <Route path="analytics" element={<AdminAnalyticsPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="jobs" element={<AdminJobsPage />} />
            <Route path="jobs/new" element={<CreateJobPage />} />
            <Route path="jobs/:jobId/applicants" element={<JobApplicantsPage />} />
            <Route path="candidates" element={<AdminCandidatesPage />} />
            <Route path="candidate-bank" element={<CandidateDataBankPage />} />
            <Route path="candidate-bank/batch-upload" element={<BatchUploadPage />} />
            <Route path="companies" element={<CompaniesPage />} />
            <Route path="commercials" element={<CommercialsPage />} />
            <Route path="teams" element={<TeamsPage />} />
            <Route path="hierarchy" element={<HierarchyPage />} />
            <Route path="pipeline" element={<AdminPipelinePage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="bulk-import" element={<BulkImportPage />} />
            <Route path="import-history" element={<ImportHistoryPage />} />
            <Route path="bug-reports" element={<BugReportsPage />} />
          </Route>

          {/* Recruiter Routes */}
          <Route path="/recruiter" element={<DashboardLayout allowedRoles={["recruiter"]} />}>
            <Route index element={<RecruiterDashboard />} />
            <Route path="jobs" element={<RecruiterJobsPage />} />
            <Route path="jobs/:jobId/applicants" element={<JobApplicantsPage />} />
            <Route path="pipeline" element={<PipelinePage />} />
            <Route path="referrals" element={<RecruiterReferralsPage />} />
            <Route path="candidate-bank" element={<RecruiterCandidateBankPage />} />
            <Route path="candidates" element={<RecruiterCandidatesPage />} />
            <Route path="find-candidates" element={<FindCandidatesPage />} />
            <Route path="match-history" element={<MatchHistoryPage />} />
          </Route>

          {/* Employer Routes */}
          <Route path="/employer" element={<DashboardLayout allowedRoles={["employer"]} />}>
            <Route index element={<EmployerDashboard />} />
            <Route path="analytics" element={<EmployerAnalyticsPage />} />
            <Route path="my-team" element={<EmployerMyTeamPage />} />
            <Route path="companies" element={<EmployerCompaniesPage />} />
            <Route path="pipeline" element={<EmployerPipelinePage />} />
            <Route path="jobs" element={<EmployerJobsPage />} />
            <Route path="jobs/new" element={<CreateJobPage />} />
            <Route path="jobs/:jobId/applicants" element={<JobApplicantsPage />} />
            <Route path="applicants" element={<ApplicantsPage />} />
            <Route path="approvals" element={<JobApprovalPage />} />
            <Route path="find-candidates" element={<FindCandidatesPage />} />
            <Route path="match-history" element={<MatchHistoryPage />} />
            <Route path="candidate-bank" element={<EmployerCandidateBankPage />} />
          </Route>

          {/* Candidate Routes */}
          <Route path="/candidate" element={<DashboardLayout allowedRoles={["candidate"]} />}>
            <Route index element={<CandidateDashboard />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="jobs" element={<BrowseJobsPage />} />
            <Route path="matching-jobs" element={<MatchingJobsPage />} />
            <Route path="applications" element={<ApplicationsPage />} />
            <Route path="messages" element={<MessagesPage />} />
            <Route path="notifications" element={<NotificationSettingsPage />} />
            <Route path="settings/notifications" element={<NotificationSettingsPage />} />
          </Route>

          {/* Default Redirect - Public Website is the landing page */}
          <Route path="/" element={<PublicWebsiteRedirect />} />
          <Route path="*" element={<PublicWebsiteRedirect />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </AuthProvider>
  );
}

export default App;
