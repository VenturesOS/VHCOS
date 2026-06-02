/**
 * BadgeAuditPage — Phase 56.3 (Feb 2026)
 *
 * Admin verification bench for the extension's "Already in Database"
 * badge endpoint (/api/extension/check-existing).
 *
 * What it shows
 *   1. Top: rolling-7-day stats — total cards scanned, recall %,
 *      avg latency, fast-path % (Naukri ID resolution).
 *   2. Left list: recent batches (each /check-existing call). Click to
 *      drill down. Each row shows hit-rate + #labeled + #client-feedback.
 *   3. Right panel: per-card decision tree for the selected batch.
 *      Card payload (what extension sent) on left, backend decision
 *      (score, signals, matched DB record, conflict reason) on right,
 *      thumbs up/down to label each card (correct / false_positive /
 *      false_negative / uncertain). Labels accumulate as a benchmark
 *      dataset for future scoring tweaks.
 *
 * Address
 *   /admin/badge-audit
 */
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Textarea } from "../../components/ui/textarea";
import {
  CheckCircle2, XCircle, HelpCircle, AlertTriangle,
  RefreshCw, Loader2, ExternalLink, Search, Activity,
} from "lucide-react";
import { toast } from "sonner";

const envUrl = process.env.REACT_APP_BACKEND_URL;
const API_BASE = envUrl ? `${envUrl.replace(/\/+$/, "")}/api` : "/api";
const getToken = () =>
  localStorage.getItem("access_token") || localStorage.getItem("vhc_token");

async function api(path, init = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`HTTP ${res.status}: ${txt.slice(0, 200)}`);
  }
  return res.json();
}

const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
};

// ── Header stats strip ───────────────────────────────────────────────
function StatsStrip({ stats }) {
  const tiles = [
    { label: "Batches", value: stats?.n_batches ?? "—" },
    { label: "Cards", value: stats?.n_cards ?? "—" },
    { label: "Recall", value: stats ? `${stats.recall_pct}%` : "—",
      hint: `${stats?.n_hits ?? 0} matched / ${stats?.n_cards ?? 0}` },
    { label: "Via Naukri ID",
      value: stats?.n_via_naukri_id ?? "—",
      hint: "fast path (no scoring)" },
    { label: "Avg latency",
      value: stats ? `${stats.avg_took_ms}ms` : "—" },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
      {tiles.map((t) => (
        <div
          key={t.label}
          className="bg-white border border-slate-200 rounded-lg px-4 py-3"
          data-testid={`audit-stat-${t.label.toLowerCase().replace(/\s/g, "-")}`}
        >
          <div className="text-xs text-slate-500">{t.label}</div>
          <div className="text-2xl font-semibold text-slate-900">{t.value}</div>
          {t.hint && <div className="text-[11px] text-slate-400 mt-0.5">{t.hint}</div>}
        </div>
      ))}
    </div>
  );
}

// ── Batches list (left column) ───────────────────────────────────────
function BatchRow({ batch, selected, onClick }) {
  const hitPct = batch.batch_size ? Math.round(batch.hit_rate * 100) : 0;
  return (
    <div
      onClick={onClick}
      className={`px-3 py-2.5 border-b border-slate-100 cursor-pointer transition ${
        selected ? "bg-blue-50 border-l-4 border-l-blue-500"
                 : "hover:bg-slate-50 border-l-4 border-l-transparent"
      }`}
      data-testid={`audit-batch-row-${batch.id}`}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-xs text-slate-500">{fmtTime(batch.ts)}</span>
        {batch.used_v2 && (
          <Badge className="bg-purple-100 text-purple-700 text-[10px] px-1.5 py-0 h-4">V2</Badge>
        )}
      </div>
      <div className="flex items-center gap-2 text-sm mb-1">
        <span className="font-medium text-slate-800">{batch.batch_size} cards</span>
        <span className="text-slate-400">·</span>
        <span className={`font-medium ${hitPct >= 50 ? "text-green-700" : "text-amber-700"}`}>
          {hitPct}% hit
        </span>
        <span className="text-slate-400">·</span>
        <span className="text-slate-500">{batch.took_ms}ms</span>
      </div>
      <div className="flex items-center gap-1.5 text-[10px]">
        {batch.n_labeled > 0 && (
          <Badge variant="outline" className="px-1 py-0 h-4">
            {batch.n_labeled} labeled
          </Badge>
        )}
        {batch.n_client_feedback > 0 && (
          <Badge variant="outline" className="px-1 py-0 h-4 bg-blue-50">
            {batch.n_client_feedback} client-fb
          </Badge>
        )}
      </div>
      {batch.page_url && (
        <div className="text-[10px] text-slate-400 truncate mt-1" title={batch.page_url}>
          {batch.page_url.replace(/^https?:\/\//, "")}
        </div>
      )}
    </div>
  );
}

// ── Card decision card (right column) ────────────────────────────────
const LABEL_OPTIONS = [
  { value: "correct", label: "Correct", icon: CheckCircle2, color: "text-green-700 border-green-300 hover:bg-green-50" },
  { value: "false_positive", label: "False +", icon: XCircle, color: "text-red-700 border-red-300 hover:bg-red-50" },
  { value: "false_negative", label: "False −", icon: AlertTriangle, color: "text-amber-700 border-amber-300 hover:bg-amber-50" },
  { value: "uncertain", label: "Uncertain", icon: HelpCircle, color: "text-slate-700 border-slate-300 hover:bg-slate-50" },
];

function CardDecisionRow({ card, batchId, onLabel }) {
  const [notes, setNotes] = useState(card.label_notes || "");
  const [labeling, setLabeling] = useState(false);

  const applyLabel = async (label) => {
    setLabeling(true);
    try {
      await api(`/admin/badge-audit/${batchId}/cards/${card.card_idx}/label`, {
        method: "POST",
        body: JSON.stringify({ label, notes: notes || null }),
      });
      toast.success(`Labeled "${card.card_name}" as ${label}`);
      onLabel(card.card_idx, label, notes);
    } catch (e) {
      toast.error(`Label failed: ${e.message}`);
    } finally {
      setLabeling(false);
    }
  };

  const badgeColor = card.exists
    ? (card.match_confidence === "high" ? "bg-green-100 text-green-700"
                                        : "bg-blue-100 text-blue-700")
    : "bg-slate-100 text-slate-600";

  return (
    <Card
      className={`border ${card.label ? "border-slate-400" : "border-slate-200"} mb-3`}
      data-testid={`audit-card-${card.card_idx}`}
    >
      <CardContent className="p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Card payload (what extension sent) */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                #{card.card_idx} · Naukri Card
              </span>
              <Badge className={`${badgeColor} text-[10px] px-1.5 py-0 h-4`}>
                {card.exists
                  ? `${card.match_confidence ?? "match"} · score ${card.match_score}`
                  : `no match${card.match_score ? ` · top score ${card.match_score}` : ""}`}
              </Badge>
            </div>
            <div className="font-medium text-slate-900 mb-1">{card.card_name || "—"}</div>
            <div className="text-sm text-slate-600">{card.card_headline || <span className="italic text-slate-400">no headline</span>}</div>
            <div className="text-xs text-slate-500 mt-1">
              {card.card_location || "—"}
              {card.card_employer && ` · ${card.card_employer}`}
              {card.card_designation && ` · ${card.card_designation}`}
              {card.card_experience_years !== null && card.card_experience_years !== undefined
                && ` · ${card.card_experience_years}y exp`}
            </div>
            {card.card_naukri_id && (
              <div className="text-[10px] text-purple-700 mt-1 font-mono">
                naukri_id: {card.card_naukri_id.slice(0, 24)}...
              </div>
            )}
          </div>

          {/* Backend decision */}
          <div className="bg-slate-50 rounded p-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
              Backend Decision
            </div>
            {card.matched_candidate_name ? (
              <>
                <div className="text-sm text-slate-900">
                  Best match: <span className="font-medium">{card.matched_candidate_name}</span>
                </div>
                <div className="text-xs text-slate-600">
                  {card.matched_candidate_employer && <>at {card.matched_candidate_employer} · </>}
                  {card.matched_candidate_location || "—"}
                </div>
                {card.matched_signals?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {card.matched_signals.map((s) => (
                      <Badge key={s} variant="outline" className="text-[10px] px-1.5 py-0 h-4">
                        {s}
                      </Badge>
                    ))}
                  </div>
                )}
                {card.matched_candidate_id && (
                  <a
                    href={`/admin/candidate-bank?candidateId=${card.matched_candidate_id}`}
                    target="_blank" rel="noreferrer"
                    className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1 mt-2"
                  >
                    Open in Candidate Bank <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </>
            ) : (
              <div className="text-sm text-slate-500 italic">
                No candidate in this batch's bucket passed the name match.
              </div>
            )}
            {card.conflict_reason && (
              <div className="text-xs text-red-700 mt-2 font-medium">
                ⚠ Rejected: {card.conflict_reason}
              </div>
            )}
            {card.client_rendered !== null && (
              <div className="text-xs mt-2">
                <span className="text-slate-500">Client: </span>
                {card.client_rendered
                  ? <span className="text-green-700">rendered badge</span>
                  : <span className="text-amber-700">skipped ({card.client_skip_reason || "no reason"})</span>}
              </div>
            )}
          </div>
        </div>

        {/* Label row */}
        <div className="mt-3 pt-3 border-t border-slate-100">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-xs text-slate-500 mr-1">Label:</span>
            {LABEL_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const isActive = card.label === opt.value;
              return (
                <Button
                  key={opt.value}
                  size="sm"
                  variant="outline"
                  disabled={labeling}
                  onClick={() => applyLabel(opt.value)}
                  className={`h-7 text-xs ${opt.color} ${isActive ? "bg-slate-100 ring-2 ring-offset-1 ring-slate-400" : ""}`}
                  data-testid={`label-${opt.value}-card-${card.card_idx}`}
                >
                  <Icon className="w-3 h-3 mr-1" />
                  {opt.label}
                </Button>
              );
            })}
            {card.label && (
              <span className="text-[10px] text-slate-400 ml-auto">
                by {card.labeled_by} · {fmtTime(card.labeled_at)}
              </span>
            )}
          </div>
          <Textarea
            placeholder="Notes (optional) — e.g. 'extension didn't badge this' or 'totally different person'"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="text-xs min-h-[40px]"
            data-testid={`label-notes-card-${card.card_idx}`}
          />
        </div>
      </CardContent>
    </Card>
  );
}

// ── Main page ────────────────────────────────────────────────────────
export default function BadgeAuditPage() {
  const [stats, setStats] = useState(null);
  const [batches, setBatches] = useState([]);
  const [selected, setSelected] = useState(null);  // full batch detail
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [filters, setFilters] = useState({ only_v2: false, has_unlabeled: false });

  const loadStats = useCallback(async () => {
    try {
      const s = await api("/admin/badge-audit/_/stats/overview?days=7");
      setStats(s);
    } catch (e) {
      // soft fail — stats are nice-to-have
      console.warn("stats load failed", e);
    }
  }, []);

  const loadBatches = useCallback(async () => {
    setLoadingList(true);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (filters.only_v2) params.set("only_v2", "true");
      if (filters.has_unlabeled) params.set("has_unlabeled", "true");
      const rows = await api(`/admin/badge-audit?${params}`);
      setBatches(rows);
    } catch (e) {
      toast.error(`Failed to load batches: ${e.message}`);
    } finally {
      setLoadingList(false);
    }
  }, [filters]);

  const loadBatchDetail = useCallback(async (id) => {
    setLoadingDetail(true);
    try {
      const detail = await api(`/admin/badge-audit/${id}`);
      setSelected(detail);
    } catch (e) {
      toast.error(`Failed to load batch: ${e.message}`);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => { loadStats(); loadBatches(); }, [loadStats, loadBatches]);

  const onCardLabel = (cardIdx, label, notes) => {
    if (!selected) return;
    setSelected((s) => ({
      ...s,
      cards: s.cards.map((c) =>
        c.card_idx === cardIdx ? { ...c, label, label_notes: notes,
          labeled_by: "you (just now)", labeled_at: new Date().toISOString() } : c),
    }));
  };

  return (
    <div className="p-4 md:p-6 max-w-[1600px] mx-auto" data-testid="badge-audit-page">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Badge Audit</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Every <code className="text-xs bg-slate-100 px-1 rounded">/check-existing</code> call from V2 users is logged.
            Review decisions, label correctness, build a benchmark.
          </p>
        </div>
        <Button
          variant="outline" size="sm"
          onClick={() => { loadStats(); loadBatches(); }}
          data-testid="audit-refresh-btn"
        >
          <RefreshCw className="w-3 h-3 mr-1.5" /> Refresh
        </Button>
      </div>

      <StatsStrip stats={stats} />

      <div className="flex items-center gap-2 mb-3">
        <Button
          size="sm" variant={filters.only_v2 ? "default" : "outline"}
          onClick={() => setFilters((f) => ({ ...f, only_v2: !f.only_v2 }))}
          data-testid="audit-filter-v2"
        >V2 only</Button>
        <Button
          size="sm" variant={filters.has_unlabeled ? "default" : "outline"}
          onClick={() => setFilters((f) => ({ ...f, has_unlabeled: !f.has_unlabeled }))}
          data-testid="audit-filter-unlabeled"
        >Has unlabeled</Button>
        <span className="text-xs text-slate-500 ml-auto">{batches.length} batches</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4">
        {/* Left: batches list */}
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-slate-100 bg-slate-50 text-xs font-semibold text-slate-600">
            Recent batches
          </div>
          <div className="max-h-[75vh] overflow-y-auto">
            {loadingList && (
              <div className="p-6 text-center text-slate-500">
                <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> Loading…
              </div>
            )}
            {!loadingList && batches.length === 0 && (
              <div className="p-6 text-center text-slate-500 text-sm">
                No batches yet. Use the extension on a Naukri search page first.
              </div>
            )}
            {batches.map((b) => (
              <BatchRow
                key={b.id}
                batch={b}
                selected={selected?.id === b.id}
                onClick={() => loadBatchDetail(b.id)}
              />
            ))}
          </div>
        </div>

        {/* Right: batch detail */}
        <div>
          {loadingDetail && (
            <div className="p-8 text-center text-slate-500">
              <Loader2 className="w-5 h-5 animate-spin inline mr-1" /> Loading detail…
            </div>
          )}
          {!loadingDetail && !selected && (
            <div className="bg-white border border-dashed border-slate-300 rounded-lg p-10 text-center">
              <Activity className="w-8 h-8 mx-auto text-slate-300 mb-2" />
              <p className="text-sm text-slate-500">
                Pick a batch on the left to inspect per-card decisions.
              </p>
            </div>
          )}
          {!loadingDetail && selected && (
            <>
              <div className="bg-white border border-slate-200 rounded-lg p-4 mb-3">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <div className="text-xs text-slate-500">
                      Batch {selected.id.slice(0, 8)}… ·{" "}
                      {selected.user_email} · {fmtTime(selected.ts)}
                    </div>
                    <div className="text-base font-medium text-slate-900 mt-1">
                      {selected.batch_size} cards ·{" "}
                      <span className="text-green-700">{selected.n_exists} matched</span> ·{" "}
                      {selected.took_ms}ms
                    </div>
                  </div>
                  {selected.used_v2 && (
                    <Badge className="bg-purple-100 text-purple-700">V2 scoring</Badge>
                  )}
                </div>
                {selected.page_url && (
                  <a
                    href={selected.page_url}
                    target="_blank" rel="noreferrer"
                    className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1"
                  >
                    <Search className="w-3 h-3" />
                    {selected.page_url.length > 80 ? selected.page_url.slice(0, 80) + "…" : selected.page_url}
                  </a>
                )}
              </div>
              {(selected.cards || []).map((card) => (
                <CardDecisionRow
                  key={card.card_idx}
                  card={card}
                  batchId={selected.id}
                  onLabel={onCardLabel}
                />
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
