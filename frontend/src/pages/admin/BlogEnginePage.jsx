import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Switch } from '../../components/ui/switch';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../components/ui/dialog';
import { blogAPI } from '../../lib/api';
import { toast } from 'sonner';
import {
  FileText, Zap, Clock, BarChart3, Activity, Settings, Eye,
  Trash2, CheckCircle, AlertCircle, Loader2, Wand2, RefreshCw,
  ChevronRight, ExternalLink, Pencil, ArrowUp, ArrowDown,
} from 'lucide-react';

const TABS = [
  { id: 'pipeline', label: 'Pipeline', icon: Activity },
  { id: 'blogs', label: 'All Blogs', icon: FileText },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export default function BlogEnginePage() {
  const [activeTab, setActiveTab] = useState('pipeline');
  const [blogs, setBlogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pipeline, setPipeline] = useState(null);
  const [filterType, setFilterType] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [generating, setGenerating] = useState(false);
  const [bulkCount, setBulkCount] = useState(5);
  const [bulkType, setBulkType] = useState('mixed');
  const [showBulkDialog, setShowBulkDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editBlog, setEditBlog] = useState(null);
  const [config, setConfig] = useState(null);

  const loadBlogs = useCallback(async () => {
    try {
      setLoading(true);
      const params = {};
      if (filterType) params.blog_type = filterType;
      if (filterStatus) params.status = filterStatus;
      const res = await blogAPI.adminList(params);
      setBlogs(res.data.blogs || []);
    } catch { toast.error('Failed to load blogs'); }
    finally { setLoading(false); }
  }, [filterType, filterStatus]);

  const loadPipeline = useCallback(async () => {
    try {
      const res = await blogAPI.getPipelineStatus();
      setPipeline(res.data);
      setConfig(res.data.config);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { loadBlogs(); }, [loadBlogs]);
  useEffect(() => { loadPipeline(); }, [loadPipeline]);

  const handleBulkGenerate = async () => {
    setGenerating(true);
    try {
      const res = await blogAPI.bulkGenerate({ count: bulkCount, blog_type: bulkType });
      toast.success(res.data.message);
      setShowBulkDialog(false);
      loadBlogs();
      loadPipeline();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Generation failed');
    } finally { setGenerating(false); }
  };

  const handleRefillPipeline = async () => {
    setGenerating(true);
    try {
      const res = await blogAPI.triggerPipeline();
      toast.success(`Pipeline generated ${res.data.generated} blogs`);
      loadBlogs();
      loadPipeline();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Pipeline trigger failed');
    } finally { setGenerating(false); }
  };

  const handlePublish = async (id) => {
    try {
      await blogAPI.publish(id);
      toast.success('Published');
      loadBlogs();
      loadPipeline();
    } catch { toast.error('Publish failed'); }
  };

  const handleUnpublish = async (id) => {
    try {
      await blogAPI.unpublish(id);
      toast.success('Unpublished');
      loadBlogs();
      loadPipeline();
    } catch { toast.error('Unpublish failed'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this blog?')) return;
    try {
      await blogAPI.adminDelete(id);
      toast.success('Deleted');
      loadBlogs();
      loadPipeline();
    } catch { toast.error('Delete failed'); }
  };

  const handleSaveEdit = async () => {
    if (!editBlog) return;
    try {
      await blogAPI.adminUpdate(editBlog.id, {
        title: editBlog.title,
        content: editBlog.content,
        meta_description: editBlog.meta_description,
      });
      toast.success('Updated');
      setShowEditDialog(false);
      setEditBlog(null);
      loadBlogs();
    } catch { toast.error('Update failed'); }
  };

  const handleSaveConfig = async (newConfig) => {
    try {
      await blogAPI.updateSchedule(newConfig);
      toast.success('Settings saved');
      loadPipeline();
    } catch { toast.error('Failed to save settings'); }
  };

  return (
    <div className="space-y-6" data-testid="blog-engine-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight" style={{ fontFamily: 'Manrope, sans-serif' }}>
            Blog Engine
          </h1>
          <p className="text-sm text-slate-500 mt-1">Automated content pipeline for SEO traffic</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleRefillPipeline}
            disabled={generating}
            data-testid="refill-pipeline-btn"
            className="text-sm"
          >
            {generating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
            Refill Queue
          </Button>
          <Button
            onClick={() => setShowBulkDialog(true)}
            className="bg-[#7CB342] hover:bg-[#689F38] text-sm"
            data-testid="bulk-generate-btn"
          >
            <Wand2 className="w-4 h-4 mr-2" /> Generate Blogs
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-lg w-fit" data-testid="blog-tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            data-testid={`tab-${tab.id}`}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === tab.id
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'pipeline' && <PipelineTab pipeline={pipeline} generating={generating} onRefill={handleRefillPipeline} />}
      {activeTab === 'blogs' && (
        <BlogsTab
          blogs={blogs}
          loading={loading}
          filterType={filterType}
          filterStatus={filterStatus}
          onFilterType={setFilterType}
          onFilterStatus={setFilterStatus}
          onPublish={handlePublish}
          onUnpublish={handleUnpublish}
          onDelete={handleDelete}
          onEdit={(blog) => { setEditBlog({ ...blog }); setShowEditDialog(true); }}
        />
      )}
      {activeTab === 'settings' && <SettingsTab config={config} onSave={handleSaveConfig} />}

      {/* Bulk Generate Dialog */}
      <Dialog open={showBulkDialog} onOpenChange={setShowBulkDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: 'Manrope, sans-serif' }}>Bulk Generate Blogs</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium text-slate-700 mb-1 block">Number of blogs</label>
              <Input
                type="number"
                min={1}
                max={10}
                value={bulkCount}
                onChange={(e) => setBulkCount(parseInt(e.target.value) || 1)}
                data-testid="bulk-count-input"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 mb-1 block">Blog type</label>
              <div className="flex gap-2">
                {['mixed', 'employer', 'candidate'].map(t => (
                  <button
                    key={t}
                    onClick={() => setBulkType(t)}
                    data-testid={`bulk-type-${t}`}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium border transition-all ${
                      bulkType === t
                        ? 'bg-[#7CB342] text-white border-[#7CB342]'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <p className="text-xs text-slate-400">
              AI will research trending topics and generate SEO-optimized blog drafts across different industries.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBulkDialog(false)}>Cancel</Button>
            <Button
              onClick={handleBulkGenerate}
              disabled={generating}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="confirm-bulk-generate"
            >
              {generating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Wand2 className="w-4 h-4 mr-2" />}
              Generate {bulkCount} Blogs
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Blog Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle style={{ fontFamily: 'Manrope, sans-serif' }}>Edit Blog</DialogTitle>
          </DialogHeader>
          {editBlog && (
            <div className="space-y-4 py-4">
              <div>
                <label className="text-sm font-medium text-slate-700 mb-1 block">Title</label>
                <Input
                  value={editBlog.title}
                  onChange={(e) => setEditBlog({ ...editBlog, title: e.target.value })}
                  data-testid="edit-blog-title"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700 mb-1 block">Meta Description</label>
                <Input
                  value={editBlog.meta_description || ''}
                  onChange={(e) => setEditBlog({ ...editBlog, meta_description: e.target.value })}
                  data-testid="edit-blog-meta"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700 mb-1 block">Content (HTML)</label>
                <textarea
                  value={editBlog.content || ''}
                  onChange={(e) => setEditBlog({ ...editBlog, content: e.target.value })}
                  rows={12}
                  className="w-full px-3 py-2 border rounded-md text-sm font-mono"
                  data-testid="edit-blog-content"
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>Cancel</Button>
            <Button onClick={handleSaveEdit} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="save-edit-btn">
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ── Pipeline Tab ──

function PipelineTab({ pipeline, generating, onRefill }) {
  if (!pipeline) return <div className="text-center py-12 text-slate-400">Loading pipeline...</div>;

  const { queue, total_published, total_drafts, published_this_week, pipeline_healthy, recent_activity, auto_generate } = pipeline;
  const minEmp = auto_generate?.min_employer_drafts || 6;
  const minCand = auto_generate?.min_candidate_drafts || 4;

  return (
    <div className="space-y-6">
      {/* Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Published"
          value={total_published}
          icon={<CheckCircle className="w-5 h-5 text-[#7CB342]" />}
          sub="Total blogs live"
          testId="stat-published"
        />
        <StatCard
          label="Drafts in Queue"
          value={total_drafts}
          icon={<FileText className="w-5 h-5 text-amber-500" />}
          sub="Ready to publish"
          testId="stat-drafts"
        />
        <StatCard
          label="This Week"
          value={published_this_week}
          icon={<BarChart3 className="w-5 h-5 text-blue-500" />}
          sub="Published last 7 days"
          testId="stat-week"
        />
        <StatCard
          label="Pipeline Health"
          value={pipeline_healthy ? 'Healthy' : 'Low'}
          icon={pipeline_healthy
            ? <CheckCircle className="w-5 h-5 text-[#7CB342]" />
            : <AlertCircle className="w-5 h-5 text-red-500" />
          }
          sub={pipeline_healthy ? 'Queue is sufficient' : 'Queue needs refill'}
          testId="stat-health"
          valueClass={pipeline_healthy ? 'text-[#7CB342]' : 'text-red-500'}
        />
      </div>

      {/* Draft Queue Gauges */}
      <Card className="border border-slate-200">
        <CardContent className="p-6">
          <h3 className="text-sm font-semibold text-slate-900 mb-4" style={{ fontFamily: 'Manrope, sans-serif' }}>
            Draft Queue
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <QueueGauge label="Employer Drafts" current={queue.employer} target={minEmp} testId="gauge-employer" />
            <QueueGauge label="Candidate Drafts" current={queue.candidate} target={minCand} testId="gauge-candidate" />
          </div>
          {!pipeline_healthy && (
            <div className="mt-4 flex items-center gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0" />
              <span className="text-sm text-amber-700">Draft queue is below target. Auto-pipeline runs daily at 2:00 AM UTC, or click "Refill Queue" to generate now.</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Activity Feed */}
      <Card className="border border-slate-200">
        <CardContent className="p-6">
          <h3 className="text-sm font-semibold text-slate-900 mb-4" style={{ fontFamily: 'Manrope, sans-serif' }}>
            Recent Activity
          </h3>
          {recent_activity && recent_activity.length > 0 ? (
            <div className="space-y-3 max-h-[300px] overflow-y-auto">
              {recent_activity.map((log, i) => (
                <div key={i} className="flex items-start gap-3 text-sm" data-testid={`activity-${i}`}>
                  <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                    log.action === 'auto_published' ? 'bg-[#7CB342]' :
                    log.action === 'auto_generated' ? 'bg-blue-400' :
                    'bg-slate-300'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <span className="font-medium text-slate-700">
                      {log.action === 'auto_published' ? 'Published' : log.action === 'auto_generated' ? 'Generated' : log.action}
                    </span>
                    <span className="text-slate-500"> &mdash; </span>
                    <span className="text-slate-600 truncate">{log.title}</span>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-slate-400">{new Date(log.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        log.blog_type === 'employer' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'
                      }`}>
                        {log.blog_type}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-slate-400">
              <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No activity yet. Generate some blogs to get started!</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}


// ── Blogs Tab ──

function BlogsTab({ blogs, loading, filterType, filterStatus, onFilterType, onFilterStatus, onPublish, onUnpublish, onDelete, onEdit }) {
  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-2" data-testid="blog-filters">
        <FilterPill label="All Types" active={!filterType} onClick={() => onFilterType('')} />
        <FilterPill label="Employer" active={filterType === 'employer'} onClick={() => onFilterType('employer')} />
        <FilterPill label="Candidate" active={filterType === 'candidate'} onClick={() => onFilterType('candidate')} />
        <div className="w-px bg-slate-200 mx-1" />
        <FilterPill label="All Status" active={!filterStatus} onClick={() => onFilterStatus('')} />
        <FilterPill label="Published" active={filterStatus === 'published'} onClick={() => onFilterStatus('published')} />
        <FilterPill label="Draft" active={filterStatus === 'draft'} onClick={() => onFilterStatus('draft')} />
      </div>

      {/* Blog List */}
      {loading ? (
        <div className="text-center py-12">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-slate-400" />
        </div>
      ) : blogs.length === 0 ? (
        <div className="text-center py-12 text-slate-400">
          <FileText className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p>No blogs found</p>
        </div>
      ) : (
        <div className="space-y-2">
          {blogs.map(blog => (
            <BlogRow
              key={blog.id}
              blog={blog}
              onPublish={onPublish}
              onUnpublish={onUnpublish}
              onDelete={onDelete}
              onEdit={onEdit}
            />
          ))}
        </div>
      )}
    </div>
  );
}


// ── Settings Tab ──

function SettingsTab({ config, onSave }) {
  const [local, setLocal] = useState(null);

  useEffect(() => {
    if (config) setLocal(JSON.parse(JSON.stringify(config)));
  }, [config]);

  if (!local) return <div className="text-center py-12 text-slate-400">Loading settings...</div>;

  const emp = local.employer || {};
  const cand = local.candidate || {};
  const ag = local.auto_generate || {};

  const update = (section, key, value) => {
    setLocal(prev => ({
      ...prev,
      [section]: { ...prev[section], [key]: value },
    }));
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Auto-Generate Settings */}
      <Card className="border border-slate-200">
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-900" style={{ fontFamily: 'Manrope, sans-serif' }}>Auto-Generation Pipeline</h3>
              <p className="text-xs text-slate-500 mt-0.5">AI generates drafts automatically when queue is low</p>
            </div>
            <Switch
              checked={ag.enabled !== false}
              onCheckedChange={(v) => update('auto_generate', 'enabled', v)}
              data-testid="toggle-auto-generate"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-slate-600">Min Employer Drafts</label>
              <Input
                type="number"
                min={1}
                max={20}
                value={ag.min_employer_drafts || 6}
                onChange={(e) => update('auto_generate', 'min_employer_drafts', parseInt(e.target.value) || 6)}
                data-testid="min-employer-drafts"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600">Min Candidate Drafts</label>
              <Input
                type="number"
                min={1}
                max={20}
                value={ag.min_candidate_drafts || 4}
                onChange={(e) => update('auto_generate', 'min_candidate_drafts', parseInt(e.target.value) || 4)}
                data-testid="min-candidate-drafts"
              />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600">Batch Size (per run)</label>
            <Input
              type="number"
              min={1}
              max={10}
              value={ag.batch_size || 3}
              onChange={(e) => update('auto_generate', 'batch_size', parseInt(e.target.value) || 3)}
              data-testid="batch-size-input"
            />
          </div>
        </CardContent>
      </Card>

      {/* Schedule Settings */}
      <Card className="border border-slate-200">
        <CardContent className="p-6 space-y-4">
          <h3 className="text-sm font-semibold text-slate-900" style={{ fontFamily: 'Manrope, sans-serif' }}>Publish Schedule</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ScheduleSection
              label="Employer Blogs"
              enabled={emp.enabled !== false}
              onToggle={(v) => update('employer', 'enabled', v)}
              days={emp.days?.join(', ') || 'Mon, Wed, Fri'}
              time={emp.time_utc || '03:30'}
              testPrefix="emp"
            />
            <ScheduleSection
              label="Candidate Blogs"
              enabled={cand.enabled !== false}
              onToggle={(v) => update('candidate', 'enabled', v)}
              days={cand.days?.join(', ') || 'Tue, Thu'}
              time={cand.time_utc || '04:30'}
              testPrefix="cand"
            />
          </div>
        </CardContent>
      </Card>

      <Button
        onClick={() => onSave(local)}
        className="bg-[#7CB342] hover:bg-[#689F38]"
        data-testid="save-settings-btn"
      >
        Save Settings
      </Button>
    </div>
  );
}


// ── Shared Components ──

function StatCard({ label, value, icon, sub, testId, valueClass = '' }) {
  return (
    <Card className="border border-slate-200 hover:shadow-sm transition-shadow" data-testid={testId}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</span>
          {icon}
        </div>
        <div className={`text-2xl font-bold ${valueClass || 'text-slate-900'}`} style={{ fontFamily: 'Manrope, sans-serif' }}>
          {value}
        </div>
        <p className="text-xs text-slate-400 mt-1">{sub}</p>
      </CardContent>
    </Card>
  );
}

function QueueGauge({ label, current, target, testId }) {
  const pct = Math.min((current / target) * 100, 100);
  const color = pct >= 75 ? '#7CB342' : pct >= 40 ? '#F59E0B' : '#EF4444';

  return (
    <div data-testid={testId}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <span className="text-sm font-semibold" style={{ color }}>
          {current} / {target}
        </span>
      </div>
      <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function FilterPill({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
        active
          ? 'bg-slate-900 text-white border-slate-900'
          : 'bg-white text-slate-500 border-slate-200 hover:border-slate-300 hover:text-slate-700'
      }`}
    >
      {label}
    </button>
  );
}

function BlogRow({ blog, onPublish, onUnpublish, onDelete, onEdit }) {
  const isPublished = blog.status === 'published';
  const isAutoGen = blog.generated_by === 'auto_pipeline';

  return (
    <div
      className="flex items-center gap-4 p-4 bg-white border border-slate-200 rounded-lg hover:shadow-sm transition-shadow group"
      data-testid={`blog-row-${blog.id}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <h4 className="text-sm font-semibold text-slate-900 truncate">{blog.title}</h4>
          {isAutoGen && (
            <span className="text-[10px] px-1.5 py-0.5 bg-violet-50 text-violet-600 rounded font-medium flex-shrink-0">
              AI
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            isPublished ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
          }`}>
            {blog.status}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            blog.blog_type === 'employer' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'
          }`}>
            {blog.blog_type}
          </span>
          {blog.industry && (
            <span className="text-xs text-slate-400">{blog.industry}</span>
          )}
          <span className="text-xs text-slate-400">
            {blog.created_at ? new Date(blog.created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' }) : ''}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button variant="ghost" size="sm" onClick={() => onEdit(blog)} data-testid={`edit-${blog.id}`}>
          <Pencil className="w-4 h-4" />
        </Button>
        {isPublished ? (
          <Button variant="ghost" size="sm" onClick={() => onUnpublish(blog.id)} data-testid={`unpublish-${blog.id}`}>
            <ArrowDown className="w-4 h-4" />
          </Button>
        ) : (
          <Button variant="ghost" size="sm" onClick={() => onPublish(blog.id)} data-testid={`publish-${blog.id}`}>
            <ArrowUp className="w-4 h-4 text-[#7CB342]" />
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => onDelete(blog.id)} data-testid={`delete-${blog.id}`}>
          <Trash2 className="w-4 h-4 text-red-400" />
        </Button>
      </div>
    </div>
  );
}

function ScheduleSection({ label, enabled, onToggle, days, time, testPrefix }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <Switch checked={enabled} onCheckedChange={onToggle} data-testid={`toggle-${testPrefix}`} />
      </div>
      <div className="text-xs text-slate-500 space-y-1">
        <div className="flex items-center gap-2">
          <Clock className="w-3 h-3" />
          <span>Publishes at {time} UTC</span>
        </div>
        <div className="flex items-center gap-2">
          <ChevronRight className="w-3 h-3" />
          <span>{days}</span>
        </div>
      </div>
    </div>
  );
}


