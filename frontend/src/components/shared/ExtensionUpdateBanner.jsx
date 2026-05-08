import { useEffect, useState } from 'react';
import { AlertTriangle, Download, X } from 'lucide-react';
import { useAuth } from '../../lib/auth';

/**
 * Shows a dismissible banner when the logged-in user's Chrome extension
 * is behind the latest published version. Only rendered for roles that
 * actually use the extension (recruiter, admin). Dismissal is per-session
 * so it reappears on the next login.
 */
const DISMISS_KEY = 'vhc_ext_update_dismissed_v';
const ROLES_WITH_EXTENSION = ['recruiter', 'admin'];

export default function ExtensionUpdateBanner() {
  const { user } = useAuth();
  const [status, setStatus] = useState(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    if (!user || !ROLES_WITH_EXTENSION.includes((user.role || '').toLowerCase())) return;

    let cancelled = false;
    const envUrl = process.env.REACT_APP_BACKEND_URL;
    const base = envUrl ? `${envUrl.replace(/\/+$/, '')}/api` : '/api';
    const token = localStorage.getItem('vhc_token');
    if (!token) return;

    fetch(`${base}/extension/my-version-status`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data) return;
        setStatus(data);
        // Auto-dismiss if user already dismissed THIS exact latest version
        const dismissed = sessionStorage.getItem(DISMISS_KEY);
        if (data.is_stale && dismissed === data.latest_version) setHidden(true);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (!status || !status.is_stale || hidden) return null;

  const { your_version, latest_version, download_url } = status;
  const envUrl = process.env.REACT_APP_BACKEND_URL;
  const fullDownloadUrl = envUrl
    ? `${envUrl.replace(/\/+$/, '')}${download_url}`
    : download_url;

  const handleDismiss = () => {
    sessionStorage.setItem(DISMISS_KEY, latest_version);
    setHidden(true);
  };

  return (
    <div
      className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3"
      data-testid="extension-update-banner"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
        <div className="text-sm">
          <p className="font-semibold text-amber-900" data-testid="extension-update-title">
            Chrome Extension update available — v{latest_version}
          </p>
          <p className="text-amber-800 mt-0.5">
            You're running v{your_version}. Download the new ZIP, remove the old extension from{' '}
            <code className="px-1 py-0.5 rounded bg-amber-100 text-[11px]">chrome://extensions</code>, then
            "Load Unpacked" the fresh folder.
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <a
          href={fullDownloadUrl}
          className="inline-flex items-center gap-1.5 rounded-md bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium px-3 py-1.5 transition-colors"
          data-testid="extension-update-download-btn"
        >
          <Download className="w-4 h-4" />
          Download v{latest_version}
        </a>
        <button
          onClick={handleDismiss}
          className="text-amber-700 hover:text-amber-900 p-1 rounded"
          aria-label="Dismiss"
          data-testid="extension-update-dismiss-btn"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
