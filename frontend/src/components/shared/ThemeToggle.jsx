import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { Button } from '../ui/button';

/**
 * ThemeToggle — light/dark switcher backed by next-themes.
 *
 * next-themes writes `class="dark"` on <html> which activates the
 * `.dark { ... }` HSL variables in index.css. Storage key
 * `vhc-theme` is set in App.js so multiple tabs stay in sync.
 *
 * `mounted` guard avoids the SSR/CSR mismatch flash that next-themes
 * warns about — first render shows a stable placeholder icon.
 */
export default function ThemeToggle({ className = '' }) {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = mounted && (resolvedTheme || theme) === 'dark';

  return (
    <Button
      variant="ghost"
      className={`w-full justify-start text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white ${className}`}
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      data-testid="theme-toggle-btn"
    >
      {isDark ? <Sun className="w-4 h-4 mr-2" /> : <Moon className="w-4 h-4 mr-2" />}
      {mounted ? (isDark ? 'Light mode' : 'Dark mode') : 'Theme'}
    </Button>
  );
}
