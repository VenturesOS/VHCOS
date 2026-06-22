/**
 * Tally Bridge Health page (Phase 55.9 / 55.10).
 *
 * Read-only dashboard for admins to see whether the Windows-side bridge
 * is polling, what's queued, and what failed. Refreshes every 30s.
 *
 * Backend: `GET /api/tally/admin/health` + `/api/tally/admin/receipts/unmatched`.
 */
import React, { useCallback, useEffect, useState } from "react";

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

const fmtRelative = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return d.toLocaleDateString();
};

const heartbeatHealth = (heartbeat) => {
  if (!heartbeat?.last_seen_at) return { label: "Never seen", tone: "rose" };
  const sec = (Date.now() - new Date(heartbeat.last_seen_at).getTime()) / 1000;
  if (sec < 300) return { label: "Healthy", tone: "emerald" };
  if (sec < 1800) return { label: "Slow", tone: "amber" };
  return { label: "Stale", tone: "rose" };
};

const ToneTile = ({ label, value, hint, tone = "slate", dataTestid }) => {
  const toneClasses = {
    slate:   "border-slate-200 bg-white text-slate-900",
    emerald: "border-emerald-300 bg-emerald-50 text-emerald-800",
    amber:   "border-amber-300 bg-amber-50 text-amber-800",
    rose:    "border-rose-300 bg-rose-50 text-rose-800",
  };
  return (
    <div
      className={`border rounded-lg px-4 py-3 ${toneClasses[tone] || toneClasses.slate}`}
      data-testid={dataTestid}
    >
      <div className="text-xs opacity-70">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
      {hint && <div className="text-[11px] opacity-60 mt-0.5">{hint}</div>}
    </div>
  );
};

const TallyHealthPage = () => {
  const [health, setHealth] = useState(null);
  const [unmatched, setUnmatched] = useState([]);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [h, u] = await Promise.all([
        api("/tally/admin/health"),
        api("/tally/admin/receipts/unmatched?limit=50").catch(() => []),
      ]);
      setHealth(h);
      setUnmatched(Array.isArray(u) ? u : []);
      setErr(null);
    } catch (e) {
      setErr(e?.message || "Failed to load Tally bridge health");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, [load]);

  const hb = heartbeatHealth(health?.heartbeat);

  return (
    <div className="p-6 space-y-5" data-testid="tally-health-page">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Tally Bridge — Health</h1>
          <p className="text-sm text-slate-500">
            Phase 55.8 (bills) · 55.9 (client ledgers) · 55.10 (receipt pull) — auto-refresh 30s.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-sm border border-slate-300 rounded px-3 py-1.5 bg-white hover:bg-slate-50 disabled:opacity-50"
          data-testid="tally-health-refresh-btn"
        >
          {loading ? "Refreshing…" : "Refresh now"}
        </button>
      </header>

      {err && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded px-4 py-3 text-sm" data-testid="tally-health-error">
          {err}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <ToneTile
          label="Bridge"
          value={hb.label}
          hint={health?.heartbeat?.last_seen_at ? `last seen ${fmtRelative(health.heartbeat.last_seen_at)}` : "no heartbeat yet"}
          tone={hb.tone}
          dataTestid="tally-tile-bridge"
        />
        <ToneTile
          label="Pending bills"
          value={health?.pending_bills ?? "—"}
          hint="awaiting Tally push"
          tone={(health?.pending_bills || 0) > 20 ? "amber" : "slate"}
          dataTestid="tally-tile-pending-bills"
        />
        <ToneTile
          label="Pending ledgers"
          value={health?.pending_ledgers ?? "—"}
          hint="client masters to create"
          tone={(health?.pending_ledgers || 0) > 0 ? "amber" : "slate"}
          dataTestid="tally-tile-pending-ledgers"
        />
        <ToneTile
          label="Pushed today"
          value={health?.pushed_today ?? "—"}
          dataTestid="tally-tile-pushed-today"
        />
        <ToneTile
          label="Receipts today"
          value={health?.receipts_today ?? "—"}
          hint="pulled from Tally"
          dataTestid="tally-tile-receipts-today"
        />
        <ToneTile
          label="Unmatched"
          value={health?.receipts_unmatched ?? "—"}
          hint="manual reconciliation"
          tone={(health?.receipts_unmatched || 0) > 0 ? "rose" : "emerald"}
          dataTestid="tally-tile-unmatched"
        />
      </div>

      <section className="bg-white border border-slate-200 rounded-lg p-4" data-testid="tally-failures-section">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Recent push failures</h2>
        {health?.recent_failures?.length ? (
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-500">
              <tr><th className="text-left pb-1">Bill</th><th className="text-left pb-1">Party</th><th className="text-left pb-1">Error</th><th className="text-left pb-1">When</th></tr>
            </thead>
            <tbody>
              {health.recent_failures.map((f) => (
                <tr key={f.id} className="border-t border-slate-100" data-testid={`tally-failure-${f.id}`}>
                  <td className="py-1.5 font-mono text-xs">{f.bill_number || f.id?.slice(0, 8)}</td>
                  <td className="py-1.5">{f.client_legal_name}</td>
                  <td className="py-1.5 text-rose-700 max-w-md truncate" title={f.tally?.last_error}>{f.tally?.last_error}</td>
                  <td className="py-1.5 text-slate-500 text-xs">{fmtRelative(f.tally?.last_attempt_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-sm text-slate-400 italic">No recent failures.</div>
        )}
      </section>

      <section className="bg-white border border-slate-200 rounded-lg p-4" data-testid="tally-unmatched-section">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">
          Unmatched receipts ({unmatched.length}) — finance manual reconciliation
        </h2>
        {unmatched.length ? (
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-500">
              <tr>
                <th className="text-left pb-1">Date</th>
                <th className="text-left pb-1">Party</th>
                <th className="text-right pb-1">Amount</th>
                <th className="text-left pb-1">Bill ref (Tally)</th>
                <th className="text-left pb-1">Instrument</th>
              </tr>
            </thead>
            <tbody>
              {unmatched.map((r) => (
                <tr key={r.id} className="border-t border-slate-100" data-testid={`tally-unmatched-${r.id}`}>
                  <td className="py-1.5 text-slate-500 text-xs">{r.receipt_date}</td>
                  <td className="py-1.5">{r.party_name}</td>
                  <td className="py-1.5 text-right font-mono">₹ {(r.amount || 0).toLocaleString("en-IN")}</td>
                  <td className="py-1.5 text-slate-500">{r.against_bill_number || "—"}</td>
                  <td className="py-1.5 text-slate-500">{r.instrument || "—"} {r.instrument_no}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-sm text-slate-400 italic">All receipts matched ✓</div>
        )}
      </section>
    </div>
  );
};

export default TallyHealthPage;
