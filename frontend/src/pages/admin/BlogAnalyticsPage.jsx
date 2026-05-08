import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Switch } from '../../components/ui/switch';
import { Label } from '../../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { BarChart3, Eye, MousePointerClick, FileText, Clock, Rss, Play, Loader2, TrendingUp, Mail, Map } from 'lucide-react';
import { blogAPI } from '../../lib/api';

const API_URL = '';

export default function BlogAnalyticsPage() {
  const [activeTab, setActiveTab] = useState('overview');
  const [days, setDays] = useState('30');
  const [stats, setStats] = useState(null);
  const [viewsData, setViewsData] = useState([]);
  const [topBlogs, setTopBlogs] = useState([]);
  const [topClicks, setTopClicks] = useState([]);
  const [schedule, setSchedule] = useState(null);
  const [draftQueue, setDraftQueue] = useState(null);
  const [scheduleLog, setScheduleLog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState('');
  const [sendingDigest, setSendingDigest] = useState(false);

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const d = parseInt(days);
      const [statsRes, viewsRes, topRes, clicksRes] = await Promise.all([
        blogAPI.analyticsStats(d),
        blogAPI.analyticsViews(d),
        blogAPI.analyticsTopBlogs(d, 10),
        blogAPI.analyticsTopClicks(d, 10),
      ]);
      setStats(statsRes.data);
      setViewsData(viewsRes.data.data || []);
      setTopBlogs(topRes.data.data || []);
      setTopClicks(clicksRes.data.data || []);
    } catch { toast.error('Failed to load analytics'); }
    finally { setLoading(false); }
  }, [days]);

  const loadSchedule = useCallback(async () => {
    try {
      const [configRes, logRes] = await Promise.all([
        blogAPI.getSchedule(),
        blogAPI.getScheduleLog(20),
      ]);
      setSchedule(configRes.data.config || {});
      setDraftQueue(configRes.data.draft_queue || {});
      setScheduleLog(logRes.data.logs || []);
    } catch { toast.error('Failed to load schedule'); }
  }, []);

  useEffect(() => { loadAnalytics(); }, [loadAnalytics]);
  useEffect(() => { if (activeTab === 'schedule') loadSchedule(); }, [activeTab, loadSchedule]);

  const handleToggleSchedule = async (blogType, enabled) => {
    try {
      await blogAPI.updateSchedule({ [blogType]: { enabled } });
      setSchedule(prev => ({ ...prev, [blogType]: { ...prev[blogType], enabled } }));
      toast.success(`${blogType} scheduling ${enabled ? 'enabled' : 'disabled'}`);
    } catch { toast.error('Failed to update schedule'); }
  };

  const handleTriggerPublish = async (blogType) => {
    setTriggering(blogType);
    try {
      const res = await blogAPI.triggerPublish(blogType);
      toast.success(res.data.message);
      loadSchedule();
    } catch { toast.error('Trigger failed'); }
    finally { setTriggering(''); }
  };

  const handleSendDigest = async () => {
    setSendingDigest(true);
    try {
      const res = await blogAPI.sendDigest();
      toast.success(res.data.message);
    } catch { toast.error('Digest send failed'); }
    finally { setSendingDigest(false); }
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }) : '-';

  return (
    <div className="space-y-5" data-testid="blog-analytics-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Blog Analytics & Scheduling</h1>
          <p className="text-slate-500 mt-1">Performance metrics, auto-scheduling, and RSS feeds</p>
        </div>
        <div className="flex items-center gap-3">
          <a href={`${API_URL}/api/blog/rss`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm text-orange-600 hover:text-orange-700 font-medium" data-testid="rss-feed-link">
            <Rss className="w-4 h-4" /> RSS Feed
          </a>
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger className="w-28" data-testid="period-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview" data-testid="tab-overview"><BarChart3 className="w-3.5 h-3.5 mr-1.5" />Overview</TabsTrigger>
          <TabsTrigger value="schedule" data-testid="tab-schedule"><Clock className="w-3.5 h-3.5 mr-1.5" />Auto-Schedule</TabsTrigger>
        </TabsList>

        {/* ── OVERVIEW TAB ── */}
        <TabsContent value="overview" className="mt-4 space-y-5">
          {loading ? <p className="text-center py-12 text-slate-400">Loading analytics...</p> : (
            <>
              {/* KPI Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="kpi-cards">
                <KPICard icon={<FileText className="w-5 h-5 text-blue-600" />} label="Published" value={(stats?.employer_published || 0) + (stats?.candidate_published || 0)} sub={`${stats?.employer_published || 0} employer · ${stats?.candidate_published || 0} candidate`} />
                <KPICard icon={<Eye className="w-5 h-5 text-emerald-600" />} label="Total Views" value={stats?.total_views || 0} sub={`Last ${stats?.period_days || 30} days`} />
                <KPICard icon={<MousePointerClick className="w-5 h-5 text-purple-600" />} label="CTA Clicks" value={stats?.total_cta_clicks || 0} sub={`CTR: ${stats?.ctr || 0}%`} />
                <KPICard icon={<TrendingUp className="w-5 h-5 text-amber-600" />} label="Draft Queue" value={(stats?.employer_drafts || 0) + (stats?.candidate_drafts || 0)} sub={`${stats?.employer_drafts || 0} employer · ${stats?.candidate_drafts || 0} candidate`} />
              </div>

              {/* Views Over Time Chart */}
              {viewsData.length > 0 && (
                <Card data-testid="views-chart-card">
                  <CardContent className="p-5">
                    <h3 className="font-semibold text-slate-800 mb-4">Daily Page Views</h3>
                    <ResponsiveContainer width="100%" height={280}>
                      <LineChart data={viewsData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                        <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                        <YAxis tick={{ fontSize: 12 }} />
                        <Tooltip />
                        <Line type="monotone" dataKey="views" stroke="#7CB342" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {/* Top Blogs & Top Clicks */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {topBlogs.length > 0 && (
                  <Card data-testid="top-blogs-card">
                    <CardContent className="p-5">
                      <h3 className="font-semibold text-slate-800 mb-4">Top Blogs by Views</h3>
                      <ResponsiveContainer width="100%" height={260}>
                        <BarChart data={topBlogs.slice(0, 5)} layout="vertical">
                          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                          <XAxis type="number" tick={{ fontSize: 12 }} />
                          <YAxis type="category" dataKey="title" width={160} tick={{ fontSize: 11 }} />
                          <Tooltip />
                          <Bar dataKey="views" fill="#7CB342" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}
                {topClicks.length > 0 && (
                  <Card data-testid="top-clicks-card">
                    <CardContent className="p-5">
                      <h3 className="font-semibold text-slate-800 mb-4">Top Blogs by CTA Clicks</h3>
                      <ResponsiveContainer width="100%" height={260}>
                        <BarChart data={topClicks.slice(0, 5)} layout="vertical">
                          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                          <XAxis type="number" tick={{ fontSize: 12 }} />
                          <YAxis type="category" dataKey="title" width={160} tick={{ fontSize: 11 }} />
                          <Tooltip />
                          <Bar dataKey="clicks" fill="#7C3AED" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* Top Blogs Table */}
              {topBlogs.length > 0 && (
                <Card data-testid="top-blogs-table">
                  <CardContent className="p-5">
                    <h3 className="font-semibold text-slate-800 mb-4">Blog Performance Table</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead><tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">Title</th>
                          <th className="pb-2 pr-4">Type</th>
                          <th className="pb-2 pr-4 text-right">Views</th>
                        </tr></thead>
                        <tbody>
                          {topBlogs.map((b, i) => (
                            <tr key={i} className="border-b last:border-0">
                              <td className="py-2 pr-4 font-medium text-slate-800 truncate max-w-[300px]">{b.title}</td>
                              <td className="py-2 pr-4"><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${b.blog_type === 'employer' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'}`}>{b.blog_type}</span></td>
                              <td className="py-2 pr-4 text-right font-semibold">{b.views}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Empty state */}
              {!topBlogs.length && !viewsData.length && (
                <Card><CardContent className="py-16 text-center text-slate-400">
                  <BarChart3 className="w-8 h-8 mx-auto mb-3 opacity-40" />
                  <p>No analytics data yet. Views and clicks will appear once blogs are published and visited.</p>
                </CardContent></Card>
              )}
            </>
          )}
        </TabsContent>

        {/* ── SCHEDULE TAB ── */}
        <TabsContent value="schedule" className="mt-4 space-y-5">
          {!schedule ? <p className="text-center py-12 text-slate-400">Loading schedule...</p> : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Employer Schedule */}
                <Card data-testid="employer-schedule-card">
                  <CardContent className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-slate-800">Employer Blog Schedule</h3>
                      <Switch
                        checked={schedule?.employer?.enabled ?? false}
                        onCheckedChange={(v) => handleToggleSchedule('employer', v)}
                        data-testid="employer-schedule-toggle"
                      />
                    </div>
                    <div className="text-sm text-slate-500 space-y-1">
                      <p>Frequency: <strong>3/week</strong> (Mon, Wed, Fri)</p>
                      <p>Time: <strong>9:00 AM IST</strong></p>
                      <p>Drafts in queue: <strong className="text-blue-600">{draftQueue?.employer || 0}</strong></p>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => handleTriggerPublish('employer')} disabled={triggering === 'employer'} data-testid="trigger-employer-btn">
                      {triggering === 'employer' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Play className="w-3.5 h-3.5 mr-1.5" />}
                      Publish Now
                    </Button>
                  </CardContent>
                </Card>

                {/* Candidate Schedule */}
                <Card data-testid="candidate-schedule-card">
                  <CardContent className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-slate-800">Candidate Blog Schedule</h3>
                      <Switch
                        checked={schedule?.candidate?.enabled ?? false}
                        onCheckedChange={(v) => handleToggleSchedule('candidate', v)}
                        data-testid="candidate-schedule-toggle"
                      />
                    </div>
                    <div className="text-sm text-slate-500 space-y-1">
                      <p>Frequency: <strong>2/week</strong> (Tue, Thu)</p>
                      <p>Time: <strong>10:00 AM IST</strong></p>
                      <p>Drafts in queue: <strong className="text-purple-600">{draftQueue?.candidate || 0}</strong></p>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => handleTriggerPublish('candidate')} disabled={triggering === 'candidate'} data-testid="trigger-candidate-btn">
                      {triggering === 'candidate' ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Play className="w-3.5 h-3.5 mr-1.5" />}
                      Publish Now
                    </Button>
                  </CardContent>
                </Card>
              </div>

              {/* RSS Feed & Sitemap Card */}
              <Card data-testid="rss-feed-card">
                <CardContent className="p-5">
                  <div className="flex items-center gap-3 mb-3">
                    <Rss className="w-5 h-5 text-orange-500" />
                    <h3 className="font-semibold text-slate-800">RSS Feeds & Sitemap</h3>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                      <span className="text-slate-700">All Blogs RSS</span>
                      <a href={`${API_URL}/api/blog/rss`} target="_blank" rel="noopener noreferrer" className="text-orange-600 hover:underline font-medium" data-testid="rss-link-all">{API_URL}/api/blog/rss</a>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                      <span className="text-slate-700">Employer RSS</span>
                      <a href={`${API_URL}/api/blog/rss?blog_type=employer`} target="_blank" rel="noopener noreferrer" className="text-orange-600 hover:underline font-medium" data-testid="rss-link-employer">{API_URL}/api/blog/rss?blog_type=employer</a>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                      <span className="text-slate-700">Candidate RSS</span>
                      <a href={`${API_URL}/api/blog/rss?blog_type=candidate`} target="_blank" rel="noopener noreferrer" className="text-orange-600 hover:underline font-medium" data-testid="rss-link-candidate">{API_URL}/api/blog/rss?blog_type=candidate</a>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg">
                      <span className="text-slate-700 flex items-center gap-1.5"><Map className="w-3.5 h-3.5 text-blue-500" />XML Sitemap</span>
                      <a href={`${API_URL}/api/blog/sitemap.xml`} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline font-medium" data-testid="sitemap-link">{API_URL}/api/blog/sitemap.xml</a>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Weekly Digest Card */}
              <Card data-testid="digest-card">
                <CardContent className="p-5">
                  <div className="flex items-center gap-3 mb-3">
                    <Mail className="w-5 h-5 text-violet-500" />
                    <h3 className="font-semibold text-slate-800">Weekly Blog Digest</h3>
                  </div>
                  <p className="text-sm text-slate-500 mb-3">Send a digest email of this week's published blogs to all registered candidates.</p>
                  <Button variant="outline" size="sm" onClick={handleSendDigest} disabled={sendingDigest} data-testid="send-digest-btn">
                    {sendingDigest ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />Sending...</> : <><Mail className="w-3.5 h-3.5 mr-1.5" />Send Digest Now</>}
                  </Button>
                </CardContent>
              </Card>

              {/* Schedule Log */}
              <Card data-testid="schedule-log-card">
                <CardContent className="p-5">
                  <h3 className="font-semibold text-slate-800 mb-4">Auto-Publish History</h3>
                  {scheduleLog.length === 0 ? (
                    <p className="text-sm text-slate-400 text-center py-6">No auto-publish events yet.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead><tr className="border-b text-left text-slate-500">
                          <th className="pb-2 pr-4">Title</th>
                          <th className="pb-2 pr-4">Type</th>
                          <th className="pb-2 pr-4">Action</th>
                          <th className="pb-2 pr-4">Time</th>
                        </tr></thead>
                        <tbody>
                          {scheduleLog.map((l, i) => (
                            <tr key={i} className="border-b last:border-0">
                              <td className="py-2 pr-4 font-medium text-slate-800 truncate max-w-[250px]">{l.title}</td>
                              <td className="py-2 pr-4 capitalize">{l.blog_type}</td>
                              <td className="py-2 pr-4"><span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">{l.action}</span></td>
                              <td className="py-2 pr-4 text-slate-500">{fmtDate(l.timestamp)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function KPICard({ icon, label, value, sub }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3 mb-2">
          {icon}
          <span className="text-sm text-slate-500">{label}</span>
        </div>
        <p className="text-2xl font-bold text-slate-900">{typeof value === 'number' ? value.toLocaleString() : value}</p>
        {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}
