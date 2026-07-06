import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput,
  CommandItem, CommandList, CommandSeparator, CommandShortcut,
} from '../ui/command';
import {
  Users, Briefcase, LayoutDashboard, GitBranch, Upload,
  BarChart3, Settings, Building2, UserSearch, Loader2,
} from 'lucide-react';
import { useAuth } from '../../lib/auth';
import { candidateBankAPI } from '../../lib/api';

/**
 * CommandPalette — global ⌘K / Ctrl+K launcher.
 *
 * The cmdk primitives have shipped in components/ui/command.jsx since
 * the design system was installed, but nothing mounts them. This wires
 * them up: role-aware navigation + live candidate lookup against the
 * existing /candidate-bank endpoint (250 ms debounce, 3-char minimum).
 *
 * Mount ONCE inside DashboardLayout (it must live under AuthProvider
 * and the Router).
 */

const NAV = [
  { label: 'Dashboard',       icon: LayoutDashboard, path: '/dashboard',        roles: ['admin', 'recruiter', 'account_manager', 'employer'] },
  { label: 'Candidate Bank',  icon: Users,           path: '/candidate-bank',   roles: ['admin', 'recruiter', 'account_manager'] },
  { label: 'Find Candidates', icon: UserSearch,      path: '/find-candidates',  roles: ['employer'] },
  { label: 'Jobs',            icon: Briefcase,       path: '/jobs',             roles: ['admin', 'recruiter', 'employer'] },
  { label: 'Pipeline',        icon: GitBranch,       path: '/pipeline',         roles: ['admin', 'recruiter', 'employer'] },
  { label: 'Companies',       icon: Building2,       path: '/companies',        roles: ['admin'] },
  { label: 'Bulk Import',     icon: Upload,          path: '/bulk-import',      roles: ['admin'] },
  { label: 'Reports',         icon: BarChart3,       path: '/reports',          roles: ['admin', 'account_manager'] },
  { label: 'Settings',        icon: Settings,        path: '/settings',         roles: ['admin', 'recruiter', 'account_manager', 'employer'] },
];

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef(null);
  const navigate = useNavigate();
  const { user } = useAuth();

  const role = user?.role || 'recruiter';
  const navItems = useMemo(
    () => NAV.filter((item) => item.roles.includes(role)),
    [role]
  );

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    const onOpenEvent = () => setOpen(true);
    document.addEventListener('keydown', onKey);
    window.addEventListener('open-command-palette', onOpenEvent);
    return () => {
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('open-command-palette', onOpenEvent);
    };
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!open || query.trim().length < 3) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await candidateBankAPI.getAll({ search: query.trim(), limit: 6 });
        setResults(res?.data?.candidates || []);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(debounceRef.current);
  }, [query, open]);

  const go = useCallback(
    (path) => {
      setOpen(false);
      setQuery('');
      navigate(path);
    },
    [navigate]
  );

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="Search candidates, or jump to a page…"
        value={query}
        onValueChange={setQuery}
        data-testid="command-palette-input"
      />
      <CommandList>
        <CommandEmpty>
          {searching ? (
            <span className="flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Searching candidate bank…
            </span>
          ) : query.trim().length >= 3 ? (
            'No matches. Try a skill, name, or phone number.'
          ) : (
            'Type at least 3 characters to search candidates.'
          )}
        </CommandEmpty>

        {results.length > 0 && (
          <>
            <CommandGroup heading="Candidates">
              {results.map((c) => (
                <CommandItem
                  key={c.id}
                  value={`${c.name} ${c.current_designation || c.designation || ''} ${c.id}`}
                  onSelect={() => go(`/candidate-bank?candidate=${c.id}`)}
                  data-testid={`command-palette-candidate-${c.id}`}
                >
                  <Users className="mr-2 h-4 w-4 text-muted-foreground" />
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate font-medium">{c.name}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {[c.current_designation || c.designation, c.current_employer || c.current_company, c.current_location || c.location]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        <CommandGroup heading="Go to">
          {navItems.map((item) => (
            <CommandItem
              key={item.path}
              value={item.label}
              onSelect={() => go(item.path)}
              data-testid={`command-palette-nav-${item.path.replace(/\//g, '-')}`}
            >
              <item.icon className="mr-2 h-4 w-4 text-muted-foreground" />
              {item.label}
              <CommandShortcut>↵</CommandShortcut>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
