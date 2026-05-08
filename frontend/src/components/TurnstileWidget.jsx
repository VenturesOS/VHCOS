import { useEffect, useRef, useState } from 'react';

const SITE_KEY = process.env.REACT_APP_TURNSTILE_SITE_KEY || '';

/**
 * Cloudflare Turnstile CAPTCHA Widget
 * Only renders when REACT_APP_TURNSTILE_SITE_KEY is configured.
 * Passes verified token to parent via onVerify callback.
 */
export function TurnstileWidget({ onVerify, onExpire, className = '' }) {
  const containerRef = useRef(null);
  const widgetIdRef = useRef(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!SITE_KEY) return;

    // Load Turnstile script if not already loaded
    if (!window.turnstile) {
      const script = document.createElement('script');
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onTurnstileLoad';
      script.async = true;
      window.onTurnstileLoad = () => setLoaded(true);
      document.head.appendChild(script);
      return () => {
        delete window.onTurnstileLoad;
      };
    } else {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (!SITE_KEY || !loaded || !containerRef.current || !window.turnstile) return;

    // Render widget
    widgetIdRef.current = window.turnstile.render(containerRef.current, {
      sitekey: SITE_KEY,
      callback: (token) => onVerify?.(token),
      'expired-callback': () => {
        onExpire?.();
        onVerify?.('');
      },
      'error-callback': () => {
        onVerify?.('');
      },
      theme: 'light',
      size: 'normal',
    });

    return () => {
      if (widgetIdRef.current != null && window.turnstile) {
        try { window.turnstile.remove(widgetIdRef.current); } catch (_) {}
      }
    };
  }, [loaded, onVerify, onExpire]);

  if (!SITE_KEY) return null;

  return (
    <div
      ref={containerRef}
      className={className}
      data-testid="turnstile-widget"
    />
  );
}

export const isTurnstileEnabled = Boolean(SITE_KEY);
