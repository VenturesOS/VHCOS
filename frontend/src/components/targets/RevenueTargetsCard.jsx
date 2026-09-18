import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Progress } from '../ui/progress';
import { Loader2, Save, Target } from 'lucide-react';
import { toast } from 'sonner';
import { targetsAPI } from '../../lib/api';

const fmtINR = (n) => (n || n === 0)
  ? `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
  : '—';

/**
 * Revenue targets for a calendar year (1 Jan → 31 Dec).
 *
 * mode="team"    → employer / team lead: set each member's target and the
 *                  revenue they had already achieved before tracking began.
 * mode="company" → admin: same per member, plus a target for the team
 *                  itself (the employer's number). Team totals roll up from
 *                  the members; the company total rolls up from the teams.
 */
export const RevenueTargetsCard = ({ mode = 'team' }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [year, setYear] = useState(new Date().getFullYear());
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = mode === 'company'
        ? await targetsAPI.companySummary({ year })
        : await targetsAPI.teamSummary({ year });
      setData(data);
      setDraft({});
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load targets');
    } finally {
      setLoading(false);
    }
  }, [mode, year]);

  useEffect(() => { load(); }, [load]);

  const save = async (scope, scopeId, fallback) => {
    const key = `${scope}:${scopeId}`;
    const d = draft[key] || {};
    const target = d.target_amount ?? fallback.target_amount;
    const opening = d.opening_achieved ?? fallback.opening_achieved;
    setSaving((s) => ({ ...s, [key]: true }));
    try {
      await targetsAPI.upsert({
        scope, scope_id: scopeId, year,
        target_amount: target === '' || target === undefined ? 0 : Number(target),
        opening_achieved: opening === '' || opening === undefined ? 0 : Number(opening),
      });
      toast.success('Target saved');
      // Re-read so the member row AND the roll-up totals reflect the new
      // number without a page refresh.
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save the target');
    } finally {
      setSaving((s) => ({ ...s, [key]: false }));
    }
  };

  const field = (scope, scopeId, name, fallback) => {
    const key = `${scope}:${scopeId}`;
    const d = draft[key] || {};
    return {
      value: d[name] ?? (fallback ?? ''),
      onChange: (e) => setDraft({ ...draft, [key]: { ...d, [name]: e.target.value } }),
    };
  };

  const teams = data?.teams || [];
  const totalTarget = data?.total_target || 0;
  const totalAchieved = data?.total_achieved || 0;

  return (
    <Card className="border-slate-200" data-testid={`revenue-targets-${mode}`}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Target className="w-4 h-4 text-[#7CB342]" />
              Revenue targets — {year} (Jan–Dec)
            </CardTitle>
            <p className="text-xs text-slate-500 mt-1">
              {mode === 'company'
                ? 'Set a target for each team and its members. Recruiter revenue rolls into the team; every team rolls into the company total.'
                : 'Set a target for each team member. Their revenue rolls into your team total.'}
            </p>
          </div>
          <div className="flex items-end gap-2">
            <div>
              <Label className="text-xs text-slate-500 mb-1 block">Year</Label>
              <Input type="number" className="h-9 w-24" value={year}
                     onChange={(e) => setYear(Number(e.target.value) || new Date().getFullYear())}
                     data-testid="targets-year" />
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-lg border p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">
              {mode === 'company' ? 'Company target' : 'Team target'}
            </p>
            <p className="text-xl font-semibold" data-testid="targets-total-target">{loading ? '…' : fmtINR(totalTarget)}</p>
          </div>
          <div className="rounded-lg border p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Achieved</p>
            <p className="text-xl font-semibold" data-testid="targets-total-achieved">{loading ? '…' : fmtINR(totalAchieved)}</p>
          </div>
          <div className="rounded-lg border p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Achievement</p>
            <p className="text-xl font-semibold" data-testid="targets-total-pct">{loading ? '…' : `${data?.achievement_pct ?? 0}%`}</p>
            <Progress value={Math.min(data?.achievement_pct ?? 0, 100)} className="h-1.5 mt-2" />
          </div>
        </div>

        {loading ? (
          <div className="py-10 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
        ) : teams.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500" data-testid="targets-empty">
            No teams found for this login yet.
          </p>
        ) : (
          teams.map((t) => (
            <div key={t.team_id} className="rounded-lg border" data-testid={`targets-team-${t.team_id}`}>
              <div className="flex items-center justify-between flex-wrap gap-3 px-4 py-3 bg-slate-50/70 border-b">
                <div>
                  <p className="font-medium text-slate-900">{t.team_name}</p>
                  <p className="text-xs text-slate-500">
                    {t.members.length} members · achieved {fmtINR(t.achieved)} of {fmtINR(t.target_amount)}
                  </p>
                </div>
                <div className="flex items-end gap-2">
                  {mode === 'company' && (
                    <>
                      <div>
                        <Label className="text-xs text-slate-500 mb-1 block">Team target (₹)</Label>
                        <Input type="number" className="h-9 w-36"
                               placeholder={String(t.members_target || 0)}
                               data-testid={`team-target-input-${t.team_id}`}
                               {...field('team', t.team_id, 'target_amount', t.team_target || '')} />
                      </div>
                      <div>
                        <Label className="text-xs text-slate-500 mb-1 block">Already achieved (₹)</Label>
                        <Input type="number" className="h-9 w-36"
                               data-testid={`team-opening-input-${t.team_id}`}
                               {...field('team', t.team_id, 'opening_achieved', t.team_opening_achieved || '')} />
                      </div>
                      <Button size="sm" variant="outline" className="h-9"
                              disabled={saving[`team:${t.team_id}`]}
                              onClick={() => save('team', t.team_id, {
                                target_amount: t.team_target || 0,
                                opening_achieved: t.team_opening_achieved || 0,
                              })}
                              data-testid={`team-target-save-${t.team_id}`}>
                        {saving[`team:${t.team_id}`] ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                      </Button>
                    </>
                  )}
                  <Badge variant="outline" className="h-9 flex items-center">{t.achievement_pct}%</Badge>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-slate-500">
                      <th className="text-left px-4 py-2">Member</th>
                      <th className="text-left px-4 py-2">Target (₹)</th>
                      <th className="text-left px-4 py-2">Already achieved (₹)</th>
                      <th className="text-left px-4 py-2">Booked revenue</th>
                      <th className="text-left px-4 py-2">Total achieved</th>
                      <th className="text-left px-4 py-2">%</th>
                      <th className="text-right px-4 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.members.map((m) => (
                      <tr key={m.user_id} className="border-b last:border-0" data-testid={`target-row-${m.user_id}`}>
                        <td className="px-4 py-2">
                          <p className="font-medium text-slate-800">{m.name || m.email}</p>
                          <p className="text-xs text-slate-400">{m.joinings} joinings</p>
                        </td>
                        <td className="px-4 py-2">
                          <Input type="number" className="h-8 w-32"
                                 data-testid={`target-input-${m.user_id}`}
                                 {...field('user', m.user_id, 'target_amount', m.target_amount || '')} />
                        </td>
                        <td className="px-4 py-2">
                          <Input type="number" className="h-8 w-32"
                                 data-testid={`opening-input-${m.user_id}`}
                                 {...field('user', m.user_id, 'opening_achieved', m.opening_achieved || '')} />
                        </td>
                        <td className="px-4 py-2">{fmtINR(m.revenue_booked)}</td>
                        <td className="px-4 py-2 font-medium">{fmtINR(m.achieved)}</td>
                        <td className="px-4 py-2">
                          <Badge variant="outline">{m.achievement_pct}%</Badge>
                        </td>
                        <td className="px-4 py-2 text-right">
                          <Button size="sm" variant="outline" className="h-8"
                                  disabled={saving[`user:${m.user_id}`]}
                                  onClick={() => save('user', m.user_id, {
                                    target_amount: m.target_amount || 0,
                                    opening_achieved: m.opening_achieved || 0,
                                  })}
                                  data-testid={`target-save-${m.user_id}`}>
                            {saving[`user:${m.user_id}`] ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Save'}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
};

export default RevenueTargetsCard;
