import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth';
import {
  LayoutDashboard,
  Users,
  Briefcase,
  UserCircle,
  Building2,
  Settings,
  LogOut,
  FileText,
  Mail,
  Search,
  ClipboardList,
  BarChart3,
  UserPlus,
  Menu,
  X,
  Sparkles,
  Database,
  Bell,
  Network,
  UsersRound,
  CheckCircle,
  Upload,
  History,
  Bug,
  Activity,
  Download,
  Radar,
  IndianRupee,
  Linkedin,
  Shield,
  ShieldCheck
} from 'lucide-react';
import { useState } from 'react';
import { Button } from '../ui/button';
import { ReportIssueDialog } from '../shared/ReportIssueDialog';

const LOGO_URL = 'https://customer-assets.emergentagent.com/job_vhc-edit/artifacts/46yye45w_logo.svg';

const navItems = {
  admin: [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/admin' },
    { icon: Briefcase, label: 'Jobs', path: '/admin/jobs' },
    { icon: ClipboardList, label: 'Pipeline', path: '/admin/pipeline' },
    { icon: FileText, label: 'Submission Tracker', path: '/admin/submission-tracker' },
    { icon: BarChart3, label: 'Analytics', path: '/admin/analytics' },
    { icon: IndianRupee, label: 'Revenue', path: '/admin/revenue' },
    { icon: UserCircle, label: 'Candidates', path: '/admin/candidates' },
    { icon: Database, label: 'Candidate Bank', path: '/admin/candidate-bank' },
    { icon: Upload, label: 'Bulk Import', path: '/admin/bulk-import' },
    { icon: History, label: 'Import History', path: '/admin/import-history' },
    { icon: Users, label: 'Users', path: '/admin/users' },
    { icon: Building2, label: 'Companies', path: '/admin/companies' },
    { icon: UsersRound, label: 'Teams', path: '/admin/teams' },
    { icon: Network, label: 'Hierarchy', path: '/admin/hierarchy' },
    { icon: FileText, label: 'Blog Engine', path: '/admin/blog-engine' },
    { icon: BarChart3, label: 'Blog Analytics', path: '/admin/blog-analytics' },
    { icon: Radar, label: 'SEO Monitoring', path: '/admin/seo-monitoring' },
    { icon: Mail, label: 'Digest Email', path: '/admin/digest-email' },
    { icon: Linkedin, label: 'LinkedIn', path: '/admin/linkedin-settings' },
    { icon: Mail, label: 'Contact Leads', path: '/admin/contact-submissions' },
    { icon: Bug, label: 'Bug Reports', path: '/admin/bug-reports' },
    { icon: Activity, label: 'System Health', path: '/admin/system-health' },
    { icon: ShieldCheck, label: 'Security Audit', path: '/admin/security-audit' },
    { icon: Shield, label: 'Compliance', path: '/admin/compliance-dashboard' },
    { icon: Download, label: 'Resources', path: '/admin/resources' },
    { icon: Settings, label: 'Settings', path: '/admin/settings' },
  ],
  recruiter: [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/recruiter' },
    { icon: Briefcase, label: 'Mandates', path: '/recruiter/jobs' },
    { icon: ClipboardList, label: 'Pipeline', path: '/recruiter/pipeline' },
    { icon: UserPlus, label: 'Referrals', path: '/recruiter/referrals' },
    { icon: UserCircle, label: 'Candidates', path: '/recruiter/candidates' },
    { icon: Sparkles, label: 'AI Screening', path: '/recruiter/find-candidates' },
    { icon: History, label: 'Match History', path: '/recruiter/match-history' },
    { icon: Database, label: 'Candidate Bank', path: '/recruiter/candidate-bank' },
    { icon: FileText, label: 'Submission Tracker', path: '/recruiter/submission-tracker' },
  ],
  employer: [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/employer' },
    { icon: BarChart3, label: 'Analytics', path: '/employer/analytics' },
    { icon: UsersRound, label: 'My Team', path: '/employer/my-team' },
    { icon: Building2, label: 'Companies', path: '/employer/companies' },
    { icon: ClipboardList, label: 'Pipeline', path: '/employer/pipeline' },
    { icon: FileText, label: 'Trackers', path: '/employer/submission-tracker' },
    { icon: Briefcase, label: 'My Jobs', path: '/employer/jobs' },
    { icon: UserPlus, label: 'Post Job', path: '/employer/jobs/new' },
    { icon: CheckCircle, label: 'Approvals', path: '/employer/approvals' },
    { icon: Database, label: 'Candidate Bank', path: '/employer/candidate-bank' },
    { icon: Sparkles, label: 'Find Candidates', path: '/employer/find-candidates' },
    { icon: History, label: 'Match History', path: '/employer/match-history' },
  ],
  candidate: [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/candidate' },
    { icon: UserCircle, label: 'My Profile', path: '/candidate/profile' },
    { icon: Search, label: 'Browse Jobs', path: '/candidate/jobs' },
    { icon: Sparkles, label: 'Jobs For You', path: '/candidate/matching-jobs' },
    { icon: FileText, label: 'Applications', path: '/candidate/applications' },
    { icon: Mail, label: 'Messages', path: '/candidate/messages' },
    { icon: Bell, label: 'Job Alerts', path: '/candidate/notifications' },
  ],
};

export const Sidebar = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const items = navItems[user?.role] || [];

  const SidebarContent = () => (
    <>
      {/* Logo */}
      <div className="p-4 lg:p-6 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <img src={LOGO_URL} alt="Ventures HRD" className="h-10 lg:h-14 w-auto" />
          <div>
            <h1 className="font-heading font-bold text-base lg:text-lg text-slate-900">Ventures HRD</h1>
            <p className="text-xs text-slate-500 capitalize">{user?.role} Portal</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        {items.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === `/${user?.role}`}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 text-sm font-medium rounded-lg transition-colors ${
                isActive
                  ? 'bg-[#DCFCE7] text-[#7CB342]'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-[#7CB342]'
              }`
            }
          >
            <item.icon className="w-5 h-5" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* User section */}
      <div className="p-4 border-t border-slate-200">
        <div className="flex items-center gap-3 mb-4 px-2">
          <div className="w-10 h-10 rounded-full bg-[#DCFCE7] flex items-center justify-center">
            <span className="text-[#7CB342] font-semibold">
              {user?.name?.charAt(0).toUpperCase()}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-900 truncate">{user?.name}</p>
            <p className="text-xs text-slate-500 truncate">{user?.email}</p>
          </div>
        </div>
        {/* Download Extension - Only for admin, employer, recruiter */}
        {['admin', 'employer', 'recruiter'].includes(user?.role) && (
          <Button
            variant="ghost"
            className="w-full justify-start text-slate-600 hover:text-[#7CB342] hover:bg-[#DCFCE7] mb-1"
            onClick={() => {
              const link = document.createElement('a');
              link.href = `/api/download/naukri-extension`;
              link.download = 'vhc-naukri-extension.zip';
              link.click();
            }}
            data-testid="download-extension-btn"
          >
            <Download className="w-4 h-4 mr-2" />
            Naukri Extension
          </Button>
        )}
        <Button
          variant="ghost"
          className="w-full justify-start text-slate-600 hover:text-amber-600 hover:bg-amber-50 mb-1"
          onClick={() => setReportOpen(true)}
          data-testid="report-issue-btn"
        >
          <Bug className="w-4 h-4 mr-2" />
          Report Issue
        </Button>
        <Button
          variant="ghost"
          className="w-full justify-start text-slate-600 hover:text-red-600 hover:bg-red-50"
          onClick={handleLogout}
          data-testid="logout-btn"
        >
          <LogOut className="w-4 h-4 mr-2" />
          Logout
        </Button>
      </div>
      <ReportIssueDialog open={reportOpen} onClose={() => setReportOpen(false)} />
    </>
  );

  return (
    <>
      {/* Mobile menu button */}
      <button
        className="lg:hidden fixed top-3 left-3 z-50 p-2.5 bg-white rounded-xl shadow-lg border border-slate-200 hover:bg-slate-50 transition-colors"
        onClick={() => setMobileOpen(!mobileOpen)}
        data-testid="mobile-menu-btn"
      >
        {mobileOpen ? <X className="w-5 h-5 text-slate-700" /> : <Menu className="w-5 h-5 text-slate-700" />}
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-40"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 h-screen bg-white border-r border-slate-200 flex flex-col z-40 w-64 transition-transform duration-300 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <SidebarContent />
      </aside>
    </>
  );
};

export default Sidebar;
