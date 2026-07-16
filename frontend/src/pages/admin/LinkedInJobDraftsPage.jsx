import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import { linkedinAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../components/ui/select';
import {
  Linkedin, Copy, Check, Loader2, Search, MapPin, Briefcase, Send, ExternalLink, RefreshCw,
} from 'lucide-react';

/**
 * LinkedIn Job Drafts page — stopgap until w_organization_social approval.
 *
 * Every active mandate (`status=active` AND `career_page_status != removed`)
 * gets a pre-composed "We're hiring" narrative draft that the admin can copy
 * and paste onto the company LinkedIn page.
 *
 * Once LinkedIn approves the org-post scope, the same draft template plugs
 * into an auto-post pipeline; this UI stays valid as a preview/history view.
 */

const PAGE_SIZE = 20;

export default function LinkedInJobDraftsPage() {
  const [drafts, setDrafts] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [status, setStatus] = useState('unposted');
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [copiedId, setCopiedId] = useState(null);
  const [togglingId, setTogglingId] = useState(null);

  // Debounce search input so we don't hammer the API on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const fetchDrafts = useCallback(async (nextSkip = 0, append = false) => {
    if (!append) setLoading(true);
    else setLoadingMore(true);
    try {
      const params = { status, limit: PAGE_SIZE, skip: nextSkip };
      if (debouncedQ) params.q = debouncedQ;
      const r = await linkedinAPI.listJobDrafts(params);
      if (append) {
        setDrafts(prev => [...prev, ...(r.data?.drafts || [])]);
      } else {
        setDrafts(r.data?.drafts || []);
      }
      setTotal(r.data?.total || 0);
      setSkip(nextSkip);
    } catch {
      toast.error('Failed to load LinkedIn drafts');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [status, debouncedQ]);

  useEffect(() => {
    fetchDrafts(0, false);
  }, [fetchDrafts]);

  const loadMore = () => fetchDrafts(skip + PAGE_SIZE, true);

  const handleCopy = async (draft) => {
    try {
      await navigator.clipboard.writeText(draft.text);
      setCopiedId(draft.job_id);
      toast.success('Draft copied — paste it on LinkedIn');
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      toast.error('Copy failed — select the text and press Ctrl+C');
    }
  };

  const handleTogglePosted = async (draft) => {
    const nextPosted = !draft.posted_at;
    setTogglingId(draft.job_id);
    try {
      const r = await linkedinAPI.toggleJobDraftPosted(draft.job_id, nextPosted);
      // Update the row in place — no full refetch needed.
      setDrafts(prev => prev.map(d =>
        d.job_id === draft.job_id ? { ...d, posted_at: r.data.linkedin_posted_at } : d
      ));
      toast.success(nextPosted ? 'Marked as posted' : 'Un-marked');
    } catch {
      toast.error('Failed to update status');
    } finally {
      setTogglingId(null);
    }
  };

  const hasMore = drafts.length < total;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5" data-testid="linkedin-drafts-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Linkedin className="h-5 w-5 text-[#0A66C2]" />
            <h1 className="text-xl font-semibold text-slate-900">LinkedIn Job Drafts</h1>
          </div>
          <p className="text-sm text-slate-500 max-w-2xl">
            Copy-paste &ldquo;We&rsquo;re hiring&rdquo; posts for every live mandate. Once LinkedIn approves the
            organization-post scope on our app, these drafts will auto-publish. Until then,
            paste them to <a
              href="https://www.linkedin.com/company/ventures-hrd-centre/admin/"
              target="_blank" rel="noreferrer"
              className="text-[#0A66C2] hover:underline inline-flex items-center gap-0.5"
            >
              our company page <ExternalLink className="h-3 w-3" />
            </a>.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchDrafts(0, false)}
          disabled={loading}
          data-testid="linkedin-drafts-refresh"
        >
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              type="text"
              placeholder="Search title / function / location…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="pl-9 h-9"
              data-testid="linkedin-drafts-search"
            />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-[180px] h-9" data-testid="linkedin-drafts-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="unposted">Not yet posted</SelectItem>
              <SelectItem value="posted">Already posted</SelectItem>
              <SelectItem value="all">All drafts</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-xs text-slate-500 ml-auto" data-testid="linkedin-drafts-count">
            {loading ? 'Loading…' : `${total.toLocaleString()} draft${total === 1 ? '' : 's'}`}
          </span>
        </CardContent>
      </Card>

      {/* Draft list */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading drafts…
        </div>
      ) : drafts.length === 0 ? (
        <Card>
          <CardContent className="py-14 text-center text-slate-500" data-testid="linkedin-drafts-empty">
            <p className="text-lg">No matching drafts.</p>
            <p className="text-sm mt-1">
              {status === 'posted'
                ? 'You haven\'t marked any drafts as posted yet.'
                : status === 'unposted'
                  ? 'You\'ve posted them all — nice work.'
                  : 'Try broadening your search.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="space-y-4" data-testid="linkedin-drafts-list">
            {drafts.map((d) => (
              <DraftCard
                key={d.job_id}
                draft={d}
                copied={copiedId === d.job_id}
                toggling={togglingId === d.job_id}
                onCopy={() => handleCopy(d)}
                onTogglePosted={() => handleTogglePosted(d)}
              />
            ))}
          </div>

          <div className="pt-2 pb-8 flex flex-col items-center gap-2">
            <p className="text-xs text-slate-500">
              Showing {drafts.length} of {total.toLocaleString()}
            </p>
            {hasMore && (
              <Button
                variant="outline"
                onClick={loadMore}
                disabled={loadingMore}
                data-testid="linkedin-drafts-load-more"
              >
                {loadingMore
                  ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Loading…</>
                  : 'Load more'}
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function DraftCard({ draft, copied, toggling, onCopy, onTogglePosted }) {
  const posted = Boolean(draft.posted_at);

  return (
    <Card data-testid={`linkedin-draft-card-${draft.job_id}`} className={posted ? 'opacity-80 border-emerald-200 bg-emerald-50/30' : ''}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <CardTitle className="text-base font-semibold text-slate-900">{draft.title}</CardTitle>
            <div className="flex items-center gap-2 mt-1 text-xs text-slate-500 flex-wrap">
              {draft.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3 w-3" />{draft.location}
                </span>
              )}
              {draft.experience && (
                <span className="inline-flex items-center gap-1">
                  <Briefcase className="h-3 w-3" />{draft.experience}
                </span>
              )}
              {draft.function && (
                <Badge variant="secondary" className="text-xs h-5">{draft.function}</Badge>
              )}
              {draft.seniority && (
                <Badge variant="outline" className="text-xs h-5">{draft.seniority}</Badge>
              )}
              <a
                href={draft.url}
                target="_blank"
                rel="noreferrer"
                className="text-slate-500 hover:text-emerald-700 hover:underline inline-flex items-center gap-0.5"
              >
                View job <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>
          {posted && (
            <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200 hover:bg-emerald-100">
              <Check className="h-3 w-3 mr-1" />
              Posted {new Date(draft.posted_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0 space-y-3">
        <Textarea
          value={draft.text}
          readOnly
          rows={16}
          className="font-mono text-xs bg-slate-50 border-slate-200 resize-y whitespace-pre-wrap"
          data-testid={`linkedin-draft-text-${draft.job_id}`}
        />
        <div className="flex items-center justify-between flex-wrap gap-2">
          <span className="text-xs text-slate-400">{draft.char_count} chars</span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={copied ? 'secondary' : 'default'}
              onClick={onCopy}
              className={copied ? '' : 'bg-[#0A66C2] hover:bg-[#004182]'}
              data-testid={`linkedin-draft-copy-${draft.job_id}`}
            >
              {copied ? <><Check className="h-4 w-4 mr-1" /> Copied</>
                      : <><Copy className="h-4 w-4 mr-1" /> Copy draft</>}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onTogglePosted}
              disabled={toggling}
              data-testid={`linkedin-draft-toggle-${draft.job_id}`}
            >
              {toggling
                ? <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> …</>
                : posted
                  ? 'Mark as unposted'
                  : <><Send className="h-4 w-4 mr-1" /> Mark as posted</>}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
