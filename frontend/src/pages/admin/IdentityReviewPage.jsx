import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import api from '../../lib/api';
import { reviewContextRows, reviewDecisions, reviewList, reviewPayload, reviewSuggestions, reviewText } from '../../lib/identityReview';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogCancel,
} from '../../components/ui/alert-dialog';

const BASE = '/admin/identity-observations';
const time = (value) => {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime()) ? date.toLocaleString() : 'Time unavailable';
};
const label = (value) => reviewText(value).replace(/_/g, ' ');
const errorText = (error) => {
  if (error.response?.status === 403) return 'Administrator access is required.';
  if (error.response?.status === 404) return 'This observation is no longer available. Refresh the queue.';
  return 'The request could not be completed. Refresh before retrying; your previous decision may have been saved.';
};

function Context({ value }) {
  return <dl className="space-y-3 text-sm">
    {reviewContextRows(value).map(([title, values]) => <div key={title}>
      <dt className="text-xs font-medium text-slate-500 dark:text-slate-400">{title}</dt>
      <dd className="mt-0.5 break-words">{values.length
        ? values.map((entry, index) => <div key={index}>{entry}</div>)
        : <span className="text-slate-400">Not observed</span>}</dd>
    </div>)}
  </dl>;
}

function Evidence({ match }) {
  const rows = reviewList(match?.evidence, 20).filter(row => row && typeof row === 'object');
  if (!rows.length) return <p className="text-xs text-slate-500">Field evidence unavailable.</p>;
  return <details className="mt-3 text-xs">
    <summary className="cursor-pointer font-medium">Compare field evidence</summary>
    <div className="mt-2 overflow-x-auto"><table className="w-full text-left">
      <thead><tr><th className="p-2">Field</th><th className="p-2">Observed</th><th className="p-2">Saved</th><th className="p-2">Relation</th></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={index} className="border-t border-slate-200 dark:border-slate-700 align-top">
        <th className="p-2 font-normal">{label(row.field)}</th>
        <td className="p-2">{reviewList(row.incoming_values).map(reviewText).filter(Boolean).join(', ') || 'Not observed'}</td>
        <td className="p-2">{reviewList(row.candidate_values).map(reviewText).filter(Boolean).join(', ') || 'Not observed'}</td>
        <td className="p-2">{label(row.status)}</td>
      </tr>)}</tbody>
    </table></div>
    <p className="mt-2 text-slate-500">A different value can reflect a change over time. Missing values are not contradictions.</p>
  </details>;
}

export default function IdentityReviewPage() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState('unresolved');
  const [selectedId, setSelectedId] = useState('');
  const [observation, setObservation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [candidateId, setCandidateId] = useState('');
  const [decision, setDecision] = useState('');
  const [reason, setReason] = useState('');
  const [confirmation, setConfirmation] = useState(null);
  const [saving, setSaving] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const listRequest = useRef(0);
  const detailRequest = useRef(0);
  const savingRef = useRef(false);

  const resetReview = useCallback(() => {
    setCandidateId(''); setDecision(''); setReason(''); setConfirmation(null);
  }, []);
  const loadList = useCallback(async () => {
    const request = ++listRequest.current;
    setLoading(true);
    try {
      const response = await api.get(BASE, { params: { status, limit: 50 }, timeout: 15000 });
      if (request !== listRequest.current) return;
      setItems(reviewList(response.data?.items, 50).filter(item => typeof item?.id === 'string'));
    } catch (failure) {
      if (request === listRequest.current) { setItems([]); setError(errorText(failure)); }
    } finally { if (request === listRequest.current) setLoading(false); }
  }, [status]);
  const loadDetail = useCallback(async (id) => {
    const request = ++detailRequest.current;
    setObservation(null); setLoadingDetail(true); setNeedsRefresh(true); resetReview();
    try {
      const response = await api.get(`${BASE}/${encodeURIComponent(id)}`, { timeout: 15000 });
      if (request !== detailRequest.current) return;
      if (response.data?.id !== id) throw new Error('Unexpected observation');
      setObservation(response.data); setNeedsRefresh(false);
      if (response.data.status === 'resolving') {
        setDecision('new_person'); setReason(response.data.pending_review?.reason || '');
      }
    } catch (failure) {
      if (request === detailRequest.current) setError(errorText(failure));
    } finally { if (request === detailRequest.current) setLoadingDetail(false); }
  }, [resetReview]);
  useEffect(() => { loadList(); return () => { listRequest.current += 1; }; }, [loadList]);
  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
    else { detailRequest.current += 1; setObservation(null); resetReview(); }
    return () => { detailRequest.current += 1; };
  }, [selectedId, loadDetail, resetReview]);

  const refresh = () => {
    setError(''); setNotice(''); loadList();
    if (selectedId) loadDetail(selectedId);
  };
  const prepareReview = (event) => {
    event.preventDefault(); setError(''); setNotice('');
    try {
      const payload = reviewPayload(observation, decision, candidateId, reason);
      setConfirmation({ observationId: observation.id, name: observation.name || observation.snapshot?.name, payload });
    } catch (failure) { setError(failure.message); }
  };
  const submitReview = async () => {
    if (!confirmation || savingRef.current || needsRefresh) return;
    savingRef.current = true; setSaving(true); setError('');
    const pending = confirmation;
    try {
      const response = await api.post(`${BASE}/${encodeURIComponent(pending.observationId)}/review`, pending.payload, { timeout: 20000 });
      if (response.data?.id !== pending.observationId) throw new Error('Unexpected observation');
      setObservation(response.data); resetReview();
      setNotice('Review saved. Linking records does not overwrite existing candidate fields.');
      loadList();
    } catch (failure) {
      setConfirmation(null); setNeedsRefresh(true);
      if (failure.response?.status === 409) {
        setNotice('This observation changed while you reviewed it. The latest version is loading; compare it again before deciding.');
        await loadDetail(pending.observationId); loadList();
      } else setError(errorText(failure));
    } finally { savingRef.current = false; setSaving(false); }
  };

  const suggestions = reviewSuggestions(observation);
  const resolution = observation?.resolution || {};
  const decisions = reviewDecisions(observation);
  const canReview = decisions.length > 0 && !needsRefresh;
  return <div className="space-y-5 text-slate-900 dark:text-slate-100" data-testid="identity-review-page">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-2xl font-semibold">Identity review</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500 dark:text-slate-400">Review dated observations before attaching them to a person. Profile URLs are navigation metadata, not identity evidence.</p></div>
      <Button variant="outline" onClick={refresh} disabled={saving || loading || loadingDetail}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button>
    </div>
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 flex gap-2"><AlertTriangle className="h-5 w-5 shrink-0" /><p>Suggestions are not confirmed identities. Evidence points are not a probability. An incomplete search or no suggestion does not establish that this is a new person.</p></div>
    {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {notice && <p role="status" className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">{notice}</p>}
    <div className="grid gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="rounded-xl border bg-white dark:bg-slate-900 dark:border-slate-700 overflow-hidden">
        <div className="p-3 border-b dark:border-slate-700"><label htmlFor="identity-status" className="block text-sm font-medium mb-1">Queue</label>
          <select id="identity-status" value={status} disabled={saving} className="w-full rounded border p-2 text-sm bg-transparent dark:border-slate-700" onChange={event => { setStatus(event.target.value); setSelectedId(''); setError(''); setNotice(''); }}>
            <option value="unresolved">Unresolved</option><option value="deferred">Deferred</option><option value="linked">Linked</option>
          </select><p className="mt-2 text-xs text-slate-500">Up to 50 observations. Refresh after reviewing a batch.</p></div>
        {loading ? <p role="status" className="p-4 text-sm flex gap-2"><Loader2 className="h-4 w-4 animate-spin" />Loading queue…</p>
          : items.length === 0 ? <p className="p-4 text-sm text-slate-500">No observations in this queue.</p>
            : <ul className="max-h-[70vh] overflow-y-auto">{items.map(item => <li key={item.id}>
              <button type="button" disabled={saving} aria-current={selectedId === item.id ? 'true' : undefined} onClick={() => { setSelectedId(item.id); setError(''); setNotice(''); }} className={`w-full p-3 text-left border-b dark:border-slate-700 ${selectedId === item.id ? 'bg-blue-50 dark:bg-blue-950' : 'hover:bg-slate-50 dark:hover:bg-slate-800'}`}>
                <span className="block font-medium text-sm">{reviewText(item.name || item.observation_summary?.name) || 'Unnamed observation'}</span>
                <span className="block text-xs text-slate-500 mt-1">{reviewText(item.source) || 'Unknown source'} · {time(item.observed_at)}</span>
                <span className="block text-xs text-slate-500 mt-1">{reviewText(item.observation_summary?.current_employer)}{item.observation_summary?.location ? ` · ${reviewText(item.observation_summary.location)}` : ''}</span>
              </button></li>)}</ul>}
      </aside>
      <section className="min-w-0 space-y-4" aria-busy={loadingDetail}>
        {loadingDetail ? <p role="status" className="p-5 flex gap-2"><Loader2 className="h-4 w-4 animate-spin" />Loading observation…</p>
          : !observation ? <p className="rounded-xl border border-dashed p-8 text-sm text-slate-500">Select an observation to compare its context. No candidate is selected automatically.</p>
            : <>
              <div className="flex flex-wrap gap-2 items-center text-xs text-slate-500"><Badge variant="outline">{label(observation.status)}</Badge><span>{time(observation.observed_at)}</span><span>Revision {observation.revision}</span></div>
              {resolution.retrieval_complete === false && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Candidate retrieval was incomplete. Review the limitations below and do not treat missing suggestions as absence from the database.</p>}
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border bg-white p-4 dark:bg-slate-900 dark:border-slate-700"><h2 className="font-semibold mb-4">Captured observation</h2><Context value={observation.snapshot || observation.observation_summary || { name: observation.name }} /></div>
                <div className="space-y-3"><h2 className="font-semibold">Possible existing people ({suggestions.length})</h2>
                  {!suggestions.length && <p className="text-sm text-slate-500">No suggestions available. This is not proof of a new person.</p>}
                  {suggestions.map(match => <article key={match.candidate_id} className={`rounded-xl border bg-white p-4 dark:bg-slate-900 ${candidateId === match.candidate_id ? 'border-blue-500' : 'dark:border-slate-700'}`}>
                    <div className="flex justify-between gap-2"><h3 className="font-medium">{reviewText(match.name) || 'Unnamed candidate'}</h3><span className="text-xs text-slate-500">{typeof match.score === 'number' && Number.isFinite(match.score) ? `${match.score} evidence points` : 'Score unavailable'}</span></div>
                    <Link to={`/admin/candidate-bank?candidateId=${encodeURIComponent(match.candidate_id)}`} target="_blank" rel="noopener noreferrer" className="my-2 inline-flex items-center gap-1 text-xs text-blue-600">Open candidate record<ExternalLink className="h-3 w-3" /></Link>
                    {match.evidence_observation_id && <p className="mb-2 text-xs text-amber-800">Compared with a reviewed observation from {time(match.evidence_observed_at)}. This is historical evidence, not confirmation of the newly viewed profile.</p>}
                    <Context value={{ ...(match.context || {}), name: match.name }} /><Evidence match={match} />
                    {match.current_context && <details className="mt-3"><summary className="text-xs cursor-pointer">Current saved context</summary><div className="mt-2"><Context value={match.current_context} /></div></details>}
                    <Button type="button" size="sm" variant="outline" className="mt-3" disabled={!canReview || !decisions.includes('link') || saving} onClick={() => { setCandidateId(match.candidate_id); setDecision('link'); }} aria-pressed={candidateId === match.candidate_id}>{candidateId === match.candidate_id ? 'Selected for review' : 'Select for review'}</Button>
                  </article>)}
                </div>
              </div>
              <details className="rounded-lg border p-3 text-xs dark:border-slate-700"><summary className="cursor-pointer font-medium">Decision context and limitations</summary>
                <p className="mt-2">{label(resolution.decision || 'not evaluated')}</p>
                <ul className="mt-1 space-y-1">{reviewList(resolution.reason_codes || observation.reason_codes, 30).map((code, index) => <li key={index}>{label(code)}</li>)}</ul>
              </details>
              {canReview ? <form onSubmit={prepareReview} className="rounded-xl border bg-white p-4 space-y-4 dark:bg-slate-900 dark:border-slate-700">
                <h2 className="font-semibold">Record a review decision</h2>
                {observation.status === 'resolving' && <p className="text-sm text-amber-800">A new-person review was interrupted. Resume the original decision using its reserved person ID; this does not create another person.</p>}
                {observation.status === 'linked' && <p className="text-sm">This observation is linked to <Link className="text-blue-600" to={`/admin/candidate-bank?candidateId=${encodeURIComponent(observation.candidate_id)}`}>its saved person</Link>. Deferring removes that link, keeps the evidence and history, and does not delete the person.</p>}
                <fieldset disabled={saving} className="space-y-3"><legend className="sr-only">Decision</legend>
                  {[['link', 'Link to an existing person', 'Attach this observation only; do not overwrite saved candidate fields.'], ['new_person', observation.status === 'resolving' ? 'Resume new-person creation' : 'Create a new person', 'Create a candidate only after reviewing the evidence for a distinct person.'], ['defer', observation.status === 'linked' ? 'Unlink and defer' : 'Keep unresolved for later', 'Preserve the observation without assigning a person.']].filter(([value]) => decisions.includes(value)).map(([value, title, hint]) => <label key={value} className="flex gap-2 text-sm"><input type="radio" name="identity-decision" value={value} checked={decision === value} onChange={() => setDecision(value)} className="mt-1" /><span>{title}<span className="block text-xs text-slate-500">{hint}</span></span></label>)}
                  {decision === 'link' && <div><label htmlFor="identity-candidate-id" className="block text-sm mb-1">Existing candidate ID</label><Input id="identity-candidate-id" value={candidateId} maxLength={256} onChange={event => setCandidateId(event.target.value)} placeholder="Select above or enter a verified candidate ID" /><p className="mt-1 text-xs text-slate-500">A manually entered ID is an administrator override. Inspect that record before linking.</p>{candidateId.trim() && <Link to={`/admin/candidate-bank?candidateId=${encodeURIComponent(candidateId.trim())}`} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600">Open entered candidate record ↗</Link>}</div>}
                  <div><label htmlFor="identity-review-reason" className="block text-sm mb-1">Reason (required, 10–2,000 characters)</label><Textarea id="identity-review-reason" value={reason} readOnly={observation.status === 'resolving'} minLength={10} maxLength={2000} onChange={event => setReason(event.target.value)} rows={3} placeholder="Explain the supporting evidence, contradictions, and any checks you made. Do not paste contact details." required /></div>
                </fieldset><Button type="submit" disabled={saving || !decision || reason.trim().length < 10 || (decision === 'link' && !candidateId.trim())}>Review decision…</Button>
              </form> : <p className="rounded-lg border p-4 text-sm dark:border-slate-700">{needsRefresh ? 'Refresh this observation before making another decision.' : 'This observation is resolved. Candidate fields have not been overwritten by this review.'}{observation.candidate_id && <Link className="ml-2 text-blue-600" to={`/admin/candidate-bank?candidateId=${encodeURIComponent(observation.candidate_id)}`}>Open linked person</Link>}</p>}
              <details className="rounded-lg border p-3 text-sm dark:border-slate-700"><summary className="cursor-pointer font-medium">Review history</summary>
                {reviewList(observation.review_history || observation.reviews, 50).length ? <ul className="mt-3 space-y-3">{reviewList(observation.review_history || observation.reviews, 50).map((review, index) => <li key={index}><div className="text-xs text-slate-500">{label(review.decision)} · {time(review.reviewed_at || review.at || review.created_at)}</div><p>{reviewText(review.reason)}</p></li>)}</ul> : <p className="mt-2 text-slate-500">No recorded human reviews.</p>}
              </details>
            </>}
      </section>
    </div>
    <AlertDialog open={Boolean(confirmation)} onOpenChange={open => { if (!open && !saving) setConfirmation(null); }}>
      <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Confirm identity review</AlertDialogTitle><AlertDialogDescription>
        {confirmation?.payload.decision === 'link' ? `Attach this observation to candidate ${confirmation.payload.candidate_id}? Existing candidate fields will not be changed.` : confirmation?.payload.decision === 'new_person' ? observation?.status === 'resolving' ? 'Resume the previously reviewed creation using the same reserved person ID?' : 'Create a separate person from this observation? This may create a duplicate if the identity is still uncertain.' : 'Defer this observation and remove any existing link? The person and review history will not be deleted.'}
      </AlertDialogDescription></AlertDialogHeader><p className="text-sm break-words">Reason: {reviewText(confirmation?.payload.reason)}</p><AlertDialogFooter><AlertDialogCancel disabled={saving}>Back to review</AlertDialogCancel><Button onClick={submitReview} disabled={saving}>{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{saving ? 'Saving…' : 'Confirm and save'}</Button></AlertDialogFooter></AlertDialogContent>
    </AlertDialog>
  </div>;
}
