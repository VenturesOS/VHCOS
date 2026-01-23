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

// Employer Pages
import EmployerDashboard from "./pages/employer/EmployerDashboard";
import EmployerJobsPage from "./pages/employer/EmployerJobsPage";
import CreateJobPage from "./pages/employer/CreateJobPage";
import ApplicantsPage from "./pages/employer/ApplicantsPage";
import JobApplicantsPage from "./pages/employer/JobApplicantsPage";
import AnalyticsPage from "./pages/employer/AnalyticsPage";
import FindCandidatesPage from "./pages/employer/FindCandidatesPage";
import JobApprovalPage from "./pages/employer/JobApprovalPage";

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
          {/* Public Routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/reset-password" element={<PasswordReset />} />

          {/* Admin Routes */}
          <Route path="/admin" element={<DashboardLayout allowedRoles={["admin"]} />}>
            <Route index element={<AdminDashboard />} />
            <Route path="analytics" element={<AdminAnalyticsPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="jobs" element={<AdminJobsPage />} />
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
          </Route>

          {/* Recruiter Routes */}
          <Route path="/recruiter" element={<DashboardLayout allowedRoles={["recruiter"]} />}>
            <Route index element={<RecruiterDashboard />} />
            <Route path="jobs" element={<RecruiterJobsPage />} />
            <Route path="jobs/:jobId/applicants" element={<JobApplicantsPage />} />
            <Route path="pipeline" element={<PipelinePage />} />
            <Route path="referrals" element={<RecruiterReferralsPage />} />
            <Route path="candidate-bank" element={<CandidateDataBankPage />} />
            <Route path="candidate-bank/batch-upload" element={<BatchUploadPage />} />
            <Route path="candidates" element={<RecruiterCandidatesPage />} />
            <Route path="find-candidates" element={<FindCandidatesPage />} />
          </Route>

          {/* Employer Routes */}
          <Route path="/employer" element={<DashboardLayout allowedRoles={["employer"]} />}>
            <Route index element={<EmployerDashboard />} />
            <Route path="jobs" element={<EmployerJobsPage />} />
            <Route path="jobs/new" element={<CreateJobPage />} />
            <Route path="jobs/:jobId/applicants" element={<JobApplicantsPage />} />
            <Route path="applicants" element={<ApplicantsPage />} />
            <Route path="approvals" element={<JobApprovalPage />} />
            <Route path="find-candidates" element={<FindCandidatesPage />} />
            <Route path="candidate-bank" element={<CandidateDataBankPage />} />
            <Route path="candidate-bank/batch-upload" element={<BatchUploadPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
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
