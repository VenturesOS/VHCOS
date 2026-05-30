/**
 * ClustersPage — Phase 56 (Feb 2026)
 *
 * Admin browser for candidate clusters produced by the k-Means + PCA
 * pipeline at backend/scripts/cluster_candidates.py
 *
 * Sections:
 *   1. Status strip + "Re-run clustering" button (admin only)
 *   2. Grid of clusters with size + label + sample names
 *   3. Drill-down modal showing all candidates in a cluster
 */
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "../../components/ui/dialog";
import { Layers, Users, Play, RefreshCw, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

const envUrl = process.env.REACT_APP_BACKEND_URL;
const API_BASE = envUrl ? `${envUrl.replace(/\/+$/, "")}/api` : "/api";
const getToken = () => localStorage.getItem("access_token") || localStorage.getItem("vhc_token");

async function api(path, init = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
      ...(init.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function ClusterCard({ cluster, onOpen }) {
  return (
    <Card
      className="border-slate-200 hover:border-blue-300 hover:shadow-md transition cursor-pointer"
      onClick={() => onOpen(cluster)}
      data-testid={`cluster-card-${cluster.cluster_id}`}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center">
              <Layers className="w-4 h-4 text-blue-600" />
            </div>
            <span className="text-xs text-slate-400 font-mono">#{cluster.cluster_id}</span>
          </div>
          <Badge variant="secondary" className="text-xs">
            {cluster.size.toLocaleString()}
          </Badge>
        </div>
        <h3 className="text-sm font-semibold text-slate-900 mb-2 line-clamp-1">
          {cluster.label || "Mixed"}
        </h3>
        {cluster.sample_candidates?.length ? (
          <div className="space-y-1 mt-2">
            {cluster.sample_candidates.slice(0, 4).map((s) => (
              <div key={s.id} className="text-[11px] text-slate-500 truncate">
                <span className="text-slate-700">{s.name || "Unknown"}</span>
                {s.designation && <span className="text-slate-400"> · {s.designation}</span>}
              </div>
            ))}
            {cluster.sample_candidates.length > 4 && (
              <div className="text-[11px] text-slate-400 italic">
                +{cluster.size - 4} more
              </div>
            )}
          </div>
        ) : (
          <p className="text-[11px] text-slate-400 italic">No samples</p>
        )}
      </CardContent>
    </Card>
  );
}

function ClusterDrillDownModal({ cluster, open, onClose }) {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !cluster) return;
    setLoading(true);
    api(`/clustering/clusters/${cluster.cluster_id}/candidates?limit=100`)
      .then((d) => setCandidates(d.candidates || []))
      .catch((e) => toast.error(`Failed: ${e.message}`))
      .finally(() => setLoading(false));
  }, [open, cluster]);

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto" data-testid="cluster-drill-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-blue-600" />
            <span>Cluster #{cluster?.cluster_id}: {cluster?.label}</span>
            <Badge variant="secondary" className="ml-2 text-xs">
              {cluster?.size?.toLocaleString()} candidates
            </Badge>
          </DialogTitle>
        </DialogHeader>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
          </div>
        ) : (
          <div className="space-y-2 mt-4" data-testid="cluster-candidates-list">
            {candidates.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-8">No candidates loaded</p>
            ) : (
              candidates.map((c) => (
                <div
                  key={c.id}
                  className="flex items-center justify-between py-2 px-3 border border-slate-200 rounded-md hover:bg-slate-50 transition"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">
                      {c.name || "—"}
                    </p>
                    <p className="text-xs text-slate-500 truncate">
                      {c.designation || c.current_designation || "—"}
                      {c.current_employer && ` · ${c.current_employer}`}
                      {c.current_location && ` · ${c.current_location}`}
                    </p>
                  </div>
                  <a
                    href={`/candidates/${c.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-600 hover:underline ml-3"
                    data-testid={`cluster-cand-open-${c.id}`}
                  >
                    Open →
                  </a>
                </div>
              ))
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function ClustersPage() {
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState(null);
  const [selected, setSelected] = useState(null);
  const [running, setRunning] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [cs, st] = await Promise.all([
        api("/clustering/clusters"),
        api("/clustering/status"),
      ]);
      setClusters(cs.clusters || []);
      setStatus(st);
    } catch (e) {
      toast.error(`Failed to load: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const triggerRun = async () => {
    setRunning(true);
    try {
      await api("/clustering/run?k=25&pca_dim=32", { method: "POST" });
      toast.success("Re-clustering started in background. Refresh in ~30s.");
    } catch (e) {
      toast.error(`Trigger failed: ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto" data-testid="clusters-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Candidate Clusters</h1>
          <p className="text-sm text-slate-500 mt-1">
            BGE embeddings → PCA(32) → k-Means. Find similar candidates by browsing clusters.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={refresh}
            data-testid="clusters-refresh-btn"
          >
            <RefreshCw className="w-4 h-4 mr-2" /> Refresh
          </Button>
          <Button
            size="sm"
            onClick={triggerRun}
            disabled={running}
            data-testid="clusters-rerun-btn"
          >
            {running ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
            Re-run Clustering
          </Button>
        </div>
      </div>

      {/* Status strip */}
      <Card className="border-slate-200">
        <CardContent className="p-4 grid grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-slate-400 text-xs flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> Active Clusters
            </div>
            <div className="text-lg font-bold mt-1">
              {status?.cluster_count ?? "—"}
            </div>
          </div>
          <div>
            <div className="text-slate-400 text-xs flex items-center gap-1">
              <Users className="w-3 h-3" /> Tagged Candidates
            </div>
            <div className="text-lg font-bold mt-1">
              {(status?.embeddings_tagged || 0).toLocaleString()}
            </div>
          </div>
          <div>
            <div className="text-slate-400 text-xs">Last Run</div>
            <div className="text-xs mt-1 text-slate-600">
              {status?.last_run?.kicked_at
                ? new Date(status.last_run.kicked_at).toLocaleString()
                : "Never"}
              {status?.last_run?.by && (
                <span className="block text-[10px] text-slate-400">
                  by {status.last_run.by}
                </span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Grid */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        </div>
      ) : clusters.length === 0 ? (
        <Card className="border-slate-200">
          <CardContent className="py-12 text-center">
            <Layers className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <p className="text-sm text-slate-500">No clusters yet.</p>
            <p className="text-xs text-slate-400 mt-1">
              Click "Re-run Clustering" to generate them from candidate embeddings.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3" data-testid="clusters-grid">
          {clusters.map((c) => (
            <ClusterCard key={c.cluster_id} cluster={c} onOpen={setSelected} />
          ))}
        </div>
      )}

      <ClusterDrillDownModal
        cluster={selected}
        open={!!selected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
