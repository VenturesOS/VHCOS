import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import {
  Shield, ShieldCheck, ShieldAlert, ShieldOff,
  CheckCircle2, XCircle, AlertTriangle, Copy, RefreshCw,
  Lock, Scan, Bot, Zap, Eye, FileWarning, ClipboardList,
  ArrowLeft, Loader2,
} from 'lucide-react';
import { Link } from 'react-router-dom';

const API_URL = '';
function getToken() { return localStorage.getItem('vhc_token'); }

const LAYER_ICONS = {
  file_validation: FileWarning,
  rate_limiting: Zap,
  security_logging: Eye,
  xss_prevention: Shield,
  turnstile: Bot,
  zero_trust: Lock,
  clamav: Scan,
};

const CATEGORY_COLORS = {
  'Upload Security': 'bg-blue-100 text-blue-700',
  'API Protection': 'bg-violet-100 text-violet-700',
  'Monitoring': 'bg-teal-100 text-teal-700',
  'Content Safety': 'bg-amber-100 text-amber-700',
  'Bot Protection': 'bg-rose-100 text-rose-700',
  'Admin Protection': 'bg-indigo-100 text-indigo-700',
  'Malware Protection': 'bg-red-100 text-red-700',
};

function ScoreRing({ score, size = 160 }) {
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 80 ? '#059669' : score >= 50 ? '#d97706' : '#dc2626';

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size/2} cy={size/2} r={radius} stroke="#e2e8f0" strokeWidth="8" fill="none" />
        <circle
          cx={size/2} cy={size/2} r={radius}
          stroke={color} strokeWidth="8" fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold" style={{ color }} data-testid="posture-score">{score}</span>
        <span className="text-xs text-slate-500 font-medium mt-0.5">/ 100</span>
      </div>
    </div>
  );
}

function LayerCard({ layer }) {
  const Icon = LAYER_ICONS[layer.id] || Shield;
  const catColor = CATEGORY_COLORS[layer.category] || 'bg-slate-100 text-slate-700';

  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-lg border transition-all ${
        layer.active
          ? 'border-emerald-200 bg-emerald-50/50'
          : 'border-slate-200 bg-slate-50/50'
      }`}
      data-testid={`layer-${layer.id}`}
    >
      <div className={`p-2 rounded-md ${layer.active ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-100 text-slate-400'}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm text-slate-900 truncate">{layer.name}</span>
          <Badge variant="secondary" className={`text-[10px] px-1.5 py-0 ${catColor}`}>
            {layer.category}
          </Badge>
        </div>
        <p className="text-xs text-slate-500 mt-0.5">{layer.detail}</p>
      </div>
      <div className="flex-shrink-0">
        {layer.active ? (
          <CheckCircle2 className="w-5 h-5 text-emerald-500" />
        ) : (
          <ShieldOff className="w-5 h-5 text-slate-400" />
        )}
      </div>
    </div>
  );
}

function EventRow({ event }) {
  const sevColors = {
    CRITICAL: 'bg-red-100 text-red-700 border-red-200',
    HIGH: 'bg-orange-100 text-orange-700 border-orange-200',
    MEDIUM: 'bg-amber-100 text-amber-700 border-amber-200',
    LOW: 'bg-blue-100 text-blue-700 border-blue-200',
  };
  const sev = event.severity || 'LOW';
  const ts = event.timestamp ? new Date(event.timestamp).toLocaleString() : '';

  return (
    <div className="flex items-start gap-3 py-2 border-b border-slate-100 last:border-0">
      <Badge className={`text-[10px] px-1.5 py-0 border ${sevColors[sev] || sevColors.LOW}`}>
        {sev}
      </Badge>
      <div className="flex-1 min-w-0">
        <span className="text-sm font-medium text-slate-800">{event.event_type}</span>
        <p className="text-xs text-slate-500 truncate">{event.detail}</p>
      </div>
      <span className="text-xs text-slate-400 whitespace-nowrap">{ts}</span>
    </div>
  );
}

export default function SecurityAuditDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copying, setCopying] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/system-health/security-posture`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) {
        setData(await res.json());
      } else {
        toast.error('Failed to load security posture data');
      }
    } catch {
      toast.error('Failed to connect to security service');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleCopyChecklist = async () => {
    if (!data) return;
    setCopying(true);
    const lines = data.compliance_checklist.map(
      (c) => `${c.status ? '[x]' : '[ ]'} ${c.item}`
    );
    const text = `VHC Talent OS — Security Compliance Checklist\nDate: ${new Date().toISOString().slice(0, 10)}\nCompliance Score: ${data.compliance_score}%\nPosture Score: ${data.posture_score}/100\n\n${lines.join('\n')}\n\nActive Layers: ${data.active_count}/${data.total_layers}\nInactive Layers: ${data.inactive_count}/${data.total_layers}`;
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Compliance checklist copied to clipboard');
    } catch {
      toast.error('Failed to copy — please use manual selection');
    } finally {
      setCopying(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 gap-2 text-slate-500">
        <Loader2 className="w-5 h-5 animate-spin" /> Loading security posture...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        Failed to load security data. Please try again.
      </div>
    );
  }

  const activeL = data.protection_layers.filter((l) => l.active);
  const inactiveL = data.protection_layers.filter((l) => !l.active);
  const scoreColor = data.posture_score >= 80 ? 'text-emerald-600' : data.posture_score >= 50 ? 'text-amber-600' : 'text-red-600';
  const ScoreIcon = data.posture_score >= 80 ? ShieldCheck : data.posture_score >= 50 ? ShieldAlert : ShieldOff;

  return (
    <div className="space-y-6" data-testid="security-audit-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/admin/system-health" className="text-slate-400 hover:text-slate-600 transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-900" data-testid="security-audit-title">Security Audit</h1>
            <p className="text-sm text-slate-500">Enterprise security posture assessment</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchData} data-testid="refresh-security-btn">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={handleCopyChecklist} disabled={copying} data-testid="copy-checklist-btn">
            {copying ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Copy className="w-4 h-4 mr-1" />}
            Copy Checklist
          </Button>
        </div>
      </div>

      {/* Score + Summary Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Posture Score Ring */}
        <Card className="border-slate-200">
          <CardContent className="flex flex-col items-center justify-center py-6">
            <ScoreRing score={data.posture_score} />
            <div className="flex items-center gap-1.5 mt-3">
              <ScoreIcon className={`w-5 h-5 ${scoreColor}`} />
              <span className={`font-semibold text-sm ${scoreColor}`}>
                {data.posture_score >= 80 ? 'Strong' : data.posture_score >= 50 ? 'Moderate' : 'Weak'} Posture
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              {data.active_count}/{data.total_layers} layers active
            </p>
          </CardContent>
        </Card>

        {/* Active Layers */}
        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-emerald-700 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4" /> Active Protections ({activeL.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[220px] overflow-y-auto">
            {activeL.map((l) => <LayerCard key={l.id} layer={l} />)}
          </CardContent>
        </Card>

        {/* Inactive / Missing Layers */}
        <Card className={`border-slate-200 ${inactiveL.length > 0 ? 'ring-1 ring-amber-300' : ''}`}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-amber-700 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4" /> Missing Protections ({inactiveL.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[220px] overflow-y-auto">
            {inactiveL.length === 0 ? (
              <p className="text-sm text-slate-500 py-4 text-center">All protection layers active</p>
            ) : (
              inactiveL.map((l) => <LayerCard key={l.id} layer={l} />)
            )}
          </CardContent>
        </Card>
      </div>

      {/* Events + Compliance Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recent Security Events */}
        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
                <Eye className="w-4 h-4" /> Recent Security Events
              </CardTitle>
              <div className="flex gap-2 text-xs">
                <span className="text-slate-500">24h: <b>{data.summary_24h.total}</b></span>
                <span className="text-slate-500">7d: <b>{data.summary_7d.total}</b></span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="max-h-[340px] overflow-y-auto" data-testid="recent-security-events">
            {data.recent_events.length === 0 ? (
              <p className="text-sm text-slate-500 py-4 text-center">No security events in the last 7 days</p>
            ) : (
              data.recent_events.map((e, i) => <EventRow key={e.id || i} event={e} />)
            )}
          </CardContent>
        </Card>

        {/* Compliance Checklist */}
        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
                <ClipboardList className="w-4 h-4" /> Compliance Checklist
              </CardTitle>
              <Badge
                variant="secondary"
                className={`text-xs ${
                  data.compliance_score >= 80 ? 'bg-emerald-100 text-emerald-700'
                    : data.compliance_score >= 50 ? 'bg-amber-100 text-amber-700'
                    : 'bg-red-100 text-red-700'
                }`}
                data-testid="compliance-score-badge"
              >
                {data.compliance_score}% compliant
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="max-h-[340px] overflow-y-auto" data-testid="compliance-checklist">
            <div className="space-y-1.5">
              {data.compliance_checklist.map((c, i) => (
                <div key={i} className="flex items-start gap-2 py-1">
                  {c.status ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                  ) : (
                    <XCircle className="w-4 h-4 text-slate-300 mt-0.5 flex-shrink-0" />
                  )}
                  <span className={`text-xs leading-relaxed ${c.status ? 'text-slate-700' : 'text-slate-400'}`}>
                    {c.item}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Event Type Breakdown */}
      {data.summary_7d.total > 0 && (
        <Card className="border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-800">Event Breakdown (7 days)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2" data-testid="event-breakdown">
              {Object.entries(data.summary_7d.by_type || {}).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                <div key={type} className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 rounded-md border border-slate-200">
                  <span className="text-xs font-medium text-slate-700">{type.replace(/_/g, ' ')}</span>
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-slate-200">{count}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
