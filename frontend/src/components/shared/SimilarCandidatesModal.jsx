/**
 * SimilarCandidatesModal — Phase 56.4 (Jun 2026)
 *
 * Shown from CandidateProfileDialog's "Find similar" button.
 *
 * Calls GET /api/clustering/similar/{seed_id} which:
 *   1. Resolves the seed's `cluster_id` from candidate_embeddings
 *   2. Picks the top-N cluster members by cosine similarity to seed
 *   3. Returns key display fields + the similarity score
 *
 * If the seed has no embedding yet (e.g. never been clustered), shows
 * a friendly empty state.
 */
import { useEffect, useState, useCallback } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Loader2, Sparkles, ExternalLink } from "lucide-react";
import { toast } from "sonner";

const envUrl = process.env.REACT_APP_BACKEND_URL;
const API_BASE = envUrl ? `${envUrl.replace(/\/+$/, "")}/api` : "/api";
const getToken = () =>
  localStorage.getItem("vhc_token") || localStorage.getItem("access_token");

async function api(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t.slice(0, 150)}`);
  }
  return res.json();
}

export default function SimilarCandidatesModal({ open, onOpenChange, seedId, seedName }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!seedId) return;
    setLoading(true);
    try {
      const r = await api(`/clustering/similar/${seedId}?limit=10`);
      setData(r);
    } catch (e) {
      toast.error(`Failed to find similar candidates: ${e.message}`);
      setData({ similar: [], reason: e.message });
    } finally {
      setLoading(false);
    }
  }, [seedId]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const openCandidate = (id) => {
    // Open in a new tab so the current profile dialog stays put
    window.open(`/admin/candidate-bank?candidateId=${id}`, "_blank");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" data-testid="similar-candidates-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-purple-600" />
            Candidates similar to {seedName || "this profile"}
          </DialogTitle>
        </DialogHeader>

        {loading && (
          <div className="py-10 text-center text-slate-500">
            <Loader2 className="w-5 h-5 animate-spin inline mr-1" />
            Looking through the cluster…
          </div>
        )}

        {!loading && data && data.similar?.length === 0 && (
          <div className="py-8 text-center text-slate-500">
            <p className="text-sm">No similar candidates found.</p>
            {data.reason && (
              <p className="text-xs text-slate-400 mt-1">{data.reason}</p>
            )}
            <p className="text-xs text-slate-400 mt-2">
              {data.reason === "no embedding or cluster"
                ? "This profile hasn't been embedded into a cluster yet. Run /admin/clusters → Re-run Clustering."
                : null}
            </p>
          </div>
        )}

        {!loading && data && data.similar?.length > 0 && (
          <>
            <div className="text-xs text-slate-500 mb-2">
              Searched {data.scanned} members of cluster #{data.cluster_id} ({data.cluster_size} total).
              Higher similarity = closer profile.
            </div>
            <div className="max-h-[60vh] overflow-y-auto divide-y divide-slate-100 border border-slate-200 rounded-lg">
              {data.similar.map((c) => (
                <div
                  key={c.id}
                  className="p-3 hover:bg-slate-50 transition cursor-pointer flex items-start gap-3"
                  onClick={() => openCandidate(c.id)}
                  data-testid={`similar-candidate-${c.id}`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-medium text-slate-900 truncate">{c.name || "(no name)"}</span>
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4">
                        sim {c.similarity?.toFixed(3)}
                      </Badge>
                    </div>
                    <div className="text-sm text-slate-600 truncate">
                      {c.current_designation || c.designation || "—"}
                      {(c.current_employer) && <> at <span className="text-slate-800">{c.current_employer}</span></>}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {(c.current_location || c.location) || "—"}
                      {(c.total_experience ?? c.experience_years) !== undefined &&
                        ` · ${c.total_experience ?? c.experience_years}y exp`}
                      {c.annual_ctc && ` · ₹${(c.annual_ctc / 100000).toFixed(1)} LPA`}
                    </div>
                  </div>
                  <ExternalLink className="w-4 h-4 text-slate-400 mt-1" />
                </div>
              ))}
            </div>
          </>
        )}

        <div className="flex justify-end pt-3">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Close</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
