import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import {
  Shield, ShieldCheck, ShieldAlert, AlertTriangle, FileText, Users,
  RefreshCw, ChevronLeft, ChevronRight, Search, Activity
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';
function getToken() { return localStorage.getItem('vhc_token'); }

const SEVERITY_CONFIG = {
  CRITICAL: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', badge: 'bg-red-100 text-red-800' },
  HIGH: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', badge: 'bg-orange-100 text-orange-800' },
  MEDIUM: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-700', badge: 'bg-yellow-100 text-yellow-800' },
  LOW: { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-600', badge: 'bg-slate-100 text-slate-700' },
};

export default function ComplianceDashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [auditPage, setAuditPage] = useState(1);
  const [auditFilter, setAuditFilter] = useState({ action: '', source: '' });

  const headers = { Authorization: `Bearer ${getToken()}` };

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/compliance/dashboard-stats`, { headers });
      if (res.ok) setStats(await res.json());
    } catch (_) {}
  }, []);

  const fetchAuditLogs = useCallback(async () => {
    const params = new URLSearchParams({ page: auditPage, limit: 20 });
    if (auditFilter.action) params.set('action', auditFilter.action);
    if (auditFilter.source) params.set('source', auditFilter.source);
    try {
      const res = await fetch(`${API_URL}/api/compliance/audit-logs?${params}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setAuditLogs(data.logs);
        setAuditTotal(data.total);
      }
    } catch (_) {}
  }, [auditPage, auditFilter]);

  useEffect(() => { fetchStats().finally(() => setLoading(false)); }, [fetchStats]);
  useEffect(() => { fetchAuditLogs(); }, [fetchAuditLogs]);

  const refresh = () => { setLoading(true); fetchStats().finally(() => setLoading(false)); fetchAuditLogs(); };

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  const h = stats?.consent_health || {};
  const alerts = stats?.data_risk_alerts || [];

  return (
    <div className="space-y-6" data-testid="compliance-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Shield className="w-6 h-6 text-emerald-600" />
            Compliance Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-1">DPDP 2023 compliance monitoring — Consent version: {stats?.consent_version}</p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} data-testid="compliance-refresh-btn">
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
      </div>

      {/* Consent Health Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Users} label="Total Profiles" value={h.total_profiles} color="slate" testId="stat-total-profiles" />
        <StatCard icon={ShieldCheck} label="Consent Recorded" value={h.consent_recorded} sub={`${h.compliance_percentage || 0}%`} color="emerald" testId="stat-consent-recorded" />
        <StatCard icon={ShieldAlert} label="Missing Consent" value={h.missing_consent} color="red" testId="stat-missing-consent" />
        <StatCard icon={Activity} label="Audit Entries" value={stats?.total_audit_entries} color="blue" testId="stat-audit-entries" />
      </div>

      {/* Compliance Progress */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Consent Coverage</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-600">Candidate Profiles</span>
              <span className="font-medium">{h.consent_recorded}/{h.total_profiles}</span>
            </div>
            <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-emerald-500 rounded-full transition-all" style={{ width: `${h.compliance_percentage || 0}%` }} data-testid="consent-progress-bar" />
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-600">Applications with Consent</span>
              <span className="font-medium">{h.applications_with_consent}/{h.total_applications}</span>
            </div>
            <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${h.total_applications ? Math.round((h.applications_with_consent / h.total_applications) * 100) : 0}%` }} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Data Risk Alerts */}
      {alerts.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" /> Data Risk Alerts
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {alerts.map((a, i) => {
              const cfg = SEVERITY_CONFIG[a.severity] || SEVERITY_CONFIG.LOW;
              return (
                <div key={i} className={`p-3 rounded-lg border ${cfg.bg} ${cfg.border}`} data-testid={`risk-alert-${a.type}`}>
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <Badge className={`${cfg.badge} text-[10px] px-1.5 py-0`}>{a.severity}</Badge>
                        <span className={`text-sm font-medium ${cfg.text}`}>{a.title}</span>
                      </div>
                      <p className="text-xs text-slate-500">{a.description}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* Audit Log */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="w-4 h-4" /> Consent Audit Log
            </CardTitle>
            <div className="flex items-center gap-2">
              <Select value={auditFilter.action} onValueChange={v => { setAuditFilter(p => ({ ...p, action: v === '_all' ? '' : v })); setAuditPage(1); }}>
                <SelectTrigger className="w-36 h-8 text-xs" data-testid="audit-filter-action">
                  <SelectValue placeholder="All Actions" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">All Actions</SelectItem>
                  <SelectItem value="consent_given">Consent Given</SelectItem>
                  <SelectItem value="consent_withdrawn">Withdrawn</SelectItem>
                  <SelectItem value="cookie_accept">Cookie Accept</SelectItem>
                </SelectContent>
              </Select>
              <Select value={auditFilter.source} onValueChange={v => { setAuditFilter(p => ({ ...p, source: v === '_all' ? '' : v })); setAuditPage(1); }}>
                <SelectTrigger className="w-36 h-8 text-xs" data-testid="audit-filter-source">
                  <SelectValue placeholder="All Sources" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">All Sources</SelectItem>
                  <SelectItem value="career_page">Career Page</SelectItem>
                  <SelectItem value="mandate_link">Mandate Link</SelectItem>
                  <SelectItem value="talent_pool">Talent Pool</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {auditLogs.length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-sm" data-testid="audit-empty">
              <FileText className="w-8 h-8 mx-auto mb-2 opacity-40" />
              No audit entries yet. Consent actions will appear here.
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-slate-500">
                      <th className="pb-2 pr-4">Timestamp</th>
                      <th className="pb-2 pr-4">Action</th>
                      <th className="pb-2 pr-4">Source</th>
                      <th className="pb-2 pr-4">Candidate</th>
                      <th className="pb-2">IP Address</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.map((log, i) => (
                      <tr key={log.id || i} className="border-b border-slate-50 hover:bg-slate-50" data-testid={`audit-row-${i}`}>
                        <td className="py-2 pr-4 text-xs text-slate-500">{new Date(log.timestamp).toLocaleString()}</td>
                        <td className="py-2 pr-4"><Badge variant="outline" className="text-[10px]">{log.action}</Badge></td>
                        <td className="py-2 pr-4 text-xs">{log.source}</td>
                        <td className="py-2 pr-4 text-xs font-mono">{(log.candidate_id || '').slice(0, 12)}...</td>
                        <td className="py-2 text-xs text-slate-400">{log.ip_address}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between mt-3 text-xs text-slate-500">
                <span>{auditTotal} total entries</span>
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0" disabled={auditPage <= 1} onClick={() => setAuditPage(p => p - 1)} data-testid="audit-prev">
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span>Page {auditPage}</span>
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0" disabled={auditPage * 20 >= auditTotal} onClick={() => setAuditPage(p => p + 1)} data-testid="audit-next">
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, color, testId }) {
  const colors = {
    slate: 'bg-slate-50 text-slate-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    red: 'bg-red-50 text-red-600',
    blue: 'bg-blue-50 text-blue-600',
  };
  return (
    <Card data-testid={testId}>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${colors[color]}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs text-slate-500">{label}</p>
            <p className="text-xl font-bold text-slate-900">
              {value ?? '—'} {sub && <span className="text-sm font-normal text-slate-400">({sub})</span>}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
