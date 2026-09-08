import { useState, useEffect, useRef } from 'react';
import { Shield, X, Settings2, Check } from 'lucide-react';
import { Button } from '../ui/button';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function CookieConsentBanner() {
  const [visible, setVisible] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const bannerRef = useRef(null);
  const [bannerHeight, setBannerHeight] = useState(0);
  const [prefs, setPrefs] = useState({
    essential: true,
    analytics: false,
    marketing: false,
  });

  useEffect(() => {
    const stored = localStorage.getItem('vhc_cookie_consent');
    if (!stored) setVisible(true);
  }, []);

  useEffect(() => {
    if (!visible || !bannerRef.current) return;
    const measure = () => setBannerHeight(bannerRef.current?.getBoundingClientRect().height || 0);
    const observer = new ResizeObserver(measure);
    observer.observe(bannerRef.current);
    measure();
    return () => observer.disconnect();
  }, [visible, showSettings]);

  const save = async (action, preferences) => {
    localStorage.setItem('vhc_cookie_consent', JSON.stringify({ ...preferences, timestamp: new Date().toISOString() }));
    setVisible(false);
    try {
      await fetch(`${API_URL}/api/compliance/cookie-consent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, preferences }),
      });
    } catch (_) {}
  };

  const acceptAll = () => save('accept_all', { essential: true, analytics: true, marketing: true });
  const rejectNonEssential = () => save('reject_non_essential', { essential: true, analytics: false, marketing: false });
  const saveCustom = () => save('custom', prefs);

  if (!visible) return null;

  return (
    <>
    <div aria-hidden="true" style={{ height: bannerHeight }} data-testid="cookie-consent-scroll-space" />
    <div ref={bannerRef} className="fixed bottom-0 inset-x-0 z-[100] p-4" data-testid="cookie-consent-banner">
      <div className="max-w-3xl max-h-[60vh] overflow-y-auto mx-auto bg-white border border-slate-200 rounded-xl shadow-lg">
        {!showSettings ? (
          <div className="p-5">
            <div className="flex items-start gap-3 mb-4">
              <Shield className="w-5 h-5 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <h3 className="text-sm font-semibold text-slate-900 mb-1">Cookie Preferences</h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  We use essential cookies for platform functionality. Analytics and marketing cookies help us improve our services.
                  Read our <a href="/cookie-policy" className="text-emerald-700 underline underline-offset-2" data-testid="cookie-policy-link">Cookie Policy</a>.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={acceptAll} className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs h-8 px-4" data-testid="cookie-accept-all">
                Accept All
              </Button>
              <Button size="sm" variant="outline" onClick={rejectNonEssential} className="text-xs h-8 px-4" data-testid="cookie-reject-nonessential">
                Reject Non-Essential
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowSettings(true)} className="text-xs h-8 px-4 text-slate-500" data-testid="cookie-manage-settings">
                <Settings2 className="w-3.5 h-3.5 mr-1" /> Manage Settings
              </Button>
            </div>
          </div>
        ) : (
          <div className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-slate-900">Cookie Settings</h3>
              <button onClick={() => setShowSettings(false)} className="text-slate-400 hover:text-slate-600" aria-label="Close cookie settings" data-testid="cookie-settings-close"><X className="w-4 h-4" /></button>
            </div>
            <div className="space-y-3 mb-4">
              {[
                { key: 'essential', label: 'Essential', desc: 'Required for core platform features', locked: true },
                { key: 'analytics', label: 'Analytics', desc: 'Help us understand usage patterns' },
                { key: 'marketing', label: 'Marketing', desc: 'Enable personalised recommendations' },
              ].map((c) => (
                <label key={c.key} className="flex items-center justify-between p-2.5 rounded-lg border border-slate-100 hover:bg-slate-50 cursor-pointer">
                  <div>
                    <span className="text-xs font-medium text-slate-800">{c.label}</span>
                    <p className="text-[11px] text-slate-400">{c.desc}</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={prefs[c.key]}
                    disabled={c.locked}
                    onChange={() => !c.locked && setPrefs(p => ({ ...p, [c.key]: !p[c.key] }))}
                    className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                    data-testid={`cookie-toggle-${c.key}`}
                  />
                </label>
              ))}
            </div>
            <Button size="sm" onClick={saveCustom} className="w-full bg-emerald-600 hover:bg-emerald-700 text-white text-xs h-8" data-testid="cookie-save-preferences">
              Save Preferences
            </Button>
          </div>
        )}
      </div>
    </div>
    </>
  );
}
