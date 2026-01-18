import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./lib/auth";
import { Toaster } from "./components/ui/sonner";

// Auth Pages
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import PasswordReset from "./pages/auth/PasswordReset";

// Layout
import DashboardLayout from "./components/layout/DashboardLayout";

// Admin Pages
import AdminDashboard from "./pages/admin/AdminDashboard";
import UsersPage from "./pages/admin/UsersPage";
import AdminJobsPage from "./pages/admin/JobsPage";
import AdminCandidatesPage from "./pages/admin/CandidatesPage";
import CompaniesPage from "./pages/admin/CompaniesPage";
import SettingsPage from "./pages/admin/SettingsPage";

// Recruiter Pages
import RecruiterDashboard from "./pages/recruiter/RecruiterDashboard";
import RecruiterJobsPage from "./pages/recruiter/RecruiterJobsPage";
import PipelinePage from "./pages/recruiter/PipelinePage";
import RecruiterCandidatesPage from "./pages/recruiter/RecruiterCandidatesPage";

// Employer Pages
import EmployerDashboard from "./pages/employer/EmployerDashboard";
import EmployerJobsPage from "./pages/employer/EmployerJobsPage";
import CreateJobPage from "./pages/employer/CreateJobPage";
import ApplicantsPage from "./pages/employer/ApplicantsPage";
import AnalyticsPage from "./pages/employer/AnalyticsPage";

// Candidate Pages
import CandidateDashboard from "./pages/candidate/CandidateDashboard";
import ProfilePage from "./pages/candidate/ProfilePage";
import BrowseJobsPage from "./pages/candidate/BrowseJobsPage";
import ApplicationsPage from "./pages/candidate/ApplicationsPage";
import MessagesPage from "./pages/candidate/MessagesPage";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          {/* Admin Routes */}
          <Route path="/admin" element={<DashboardLayout allowedRoles={["admin"]} />}>
            <Route index element={<AdminDashboard />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="jobs" element={<AdminJobsPage />} />
            <Route path="candidates" element={<AdminCandidatesPage />} />
            <Route path="companies" element={<CompaniesPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>

          {/* Recruiter Routes */}
          <Route path="/recruiter" element={<DashboardLayout allowedRoles={["recruiter"]} />}>
            <Route index element={<RecruiterDashboard />} />
            <Route path="jobs" element={<RecruiterJobsPage />} />
            <Route path="pipeline" element={<PipelinePage />} />
            <Route path="candidates" element={<RecruiterCandidatesPage />} />
          </Route>

          {/* Employer Routes */}
          <Route path="/employer" element={<DashboardLayout allowedRoles={["employer"]} />}>
            <Route index element={<EmployerDashboard />} />
            <Route path="jobs" element={<EmployerJobsPage />} />
            <Route path="jobs/new" element={<CreateJobPage />} />
            <Route path="applicants" element={<ApplicantsPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
          </Route>

          {/* Candidate Routes */}
          <Route path="/candidate" element={<DashboardLayout allowedRoles={["candidate"]} />}>
            <Route index element={<CandidateDashboard />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="jobs" element={<BrowseJobsPage />} />
            <Route path="applications" element={<ApplicationsPage />} />
            <Route path="messages" element={<MessagesPage />} />
          </Route>

          {/* Default Redirect */}
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </AuthProvider>
  );
}

export default App;
