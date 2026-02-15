import { useState, useEffect } from 'react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { toast } from 'sonner';
import { Sparkles, FileText, Globe, MapPin, Trash2, Eye, Pencil, Send, Loader2, ArrowLeft, RotateCcw, Search } from 'lucide-react';
import { blogAPI } from '../../lib/api';

const STATUS_BADGE = {
  draft: 'bg-amber-100 text-amber-700',
  published: 'bg-green-100 text-green-700',
};

const CANDIDATE_CATEGORIES = [
  { value: 'career-growth', label: 'Career Growth' },
  { value: 'job-switching', label: 'Stability & Job Switching' },
  { value: 'resume-interview', label: 'Resume & Interview' },
  { value: 'salary-trends', label: 'Salary Trends' },
  { value: 'industry-opportunities', label: 'Industry Opportunities' },
];

export default function BlogEnginePage() {
  const [activeTab, setActiveTab] = useState('employer');
  const [blogs, setBlogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  // Generate form
  const [showGenerate, setShowGenerate] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genForm, setGenForm] = useState({ topic: '', industry: '', keywords: '', region: 'india', category: 'career-growth' });
  // AI Topic Research
  const [researching, setResearching] = useState(false);
  const [topicSuggestions, setTopicSuggestions] = useState([]);
  // Edit/Preview
  const [editBlog, setEditBlog] = useState(null);
  const [previewBlog, setPreviewBlog] = useState(null);
  const [saving, setSaving] = useState(false);

  const loadBlogs = async () => {
    try {
      setLoading(true);
      const params = { blog_type: activeTab };
      if (filterStatus) params.status = filterStatus;
      const res = await blogAPI.adminList(params);
      setBlogs(res.data.blogs || []);
    } catch { toast.error('Failed to load blogs'); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadBlogs(); }, [activeTab, filterStatus]);

  const handleGenerate = async () => {
    if (!genForm.topic || !genForm.industry) { toast.error('Topic and industry are required'); return; }
    setGenerating(true);
    try {
      const payload = { blog_type: activeTab, topic: genForm.topic, industry: genForm.industry, keywords: genForm.keywords };
      if (activeTab === 'employer') payload.region = genForm.region;
      else payload.category = genForm.category;
      const res = await blogAPI.generate(payload);
      toast.success('Blog generated! Saved as draft.');
      setShowGenerate(false);
      setGenForm({ topic: '', industry: '', keywords: '', region: 'india', category: 'career-growth' });
      loadBlogs();
      setEditBlog(res.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Generation failed');
    } finally { setGenerating(false); }
  };

  const handlePublish = async (id) => {
    try { await blogAPI.publish(id); toast.success('Blog published!'); loadBlogs(); if (editBlog?.id === id) setEditBlog(prev => ({ ...prev, status: 'published' })); }
    catch { toast.error('Publish failed'); }
  };

  const handleUnpublish = async (id) => {
    try { await blogAPI.unpublish(id); toast.success('Blog unpublished'); loadBlogs(); if (editBlog?.id === id) setEditBlog(prev => ({ ...prev, status: 'draft' })); }
    catch { toast.error('Unpublish failed'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this blog permanently?')) return;
    try { await blogAPI.adminDelete(id); toast.success('Blog deleted'); loadBlogs(); if (editBlog?.id === id) setEditBlog(null); }
    catch { toast.error('Delete failed'); }
  };

  const handleSaveEdit = async () => {
    if (!editBlog) return;
    setSaving(true);
    try {
      await blogAPI.adminUpdate(editBlog.id, {
        title: editBlog.title, meta_description: editBlog.meta_description,
        slug: editBlog.slug, content: editBlog.content,
        keywords: editBlog.keywords, internal_links: editBlog.internal_links,
      });
      toast.success('Changes saved');
      loadBlogs();
    } catch { toast.error('Save failed'); }
    finally { setSaving(false); }
  };

  const openEdit = async (id) => {
    try {
      const res = await blogAPI.adminGet(id);
      setEditBlog(res.data);
    } catch { toast.error('Failed to load blog'); }
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '-';

  // ─── EDITOR VIEW ───
  if (editBlog) {
    return (
      <div className="space-y-4" data-testid="blog-editor">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => setEditBlog(null)} data-testid="back-to-list"><ArrowLeft className="w-4 h-4 mr-1" />Back</Button>
          <h2 className="font-heading text-lg font-bold flex-1 truncate">{editBlog.title || 'Untitled'}</h2>
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE[editBlog.status] || ''}`}>{editBlog.status}</span>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Main content editor */}
          <div className="lg:col-span-2 space-y-3">
            <div>
              <Label className="text-xs text-slate-500">Title</Label>
              <Input value={editBlog.title || ''} onChange={e => setEditBlog(p => ({ ...p, title: e.target.value }))} data-testid="edit-title" />
            </div>
            <div>
              <Label className="text-xs text-slate-500">Meta Description</Label>
              <Textarea value={editBlog.meta_description || ''} rows={2} onChange={e => setEditBlog(p => ({ ...p, meta_description: e.target.value }))} data-testid="edit-meta" />
              <p className="text-xs text-slate-400 mt-1">{(editBlog.meta_description || '').length}/160 chars</p>
            </div>
            <div>
              <Label className="text-xs text-slate-500">Slug</Label>
              <Input value={editBlog.slug || ''} onChange={e => setEditBlog(p => ({ ...p, slug: e.target.value }))} data-testid="edit-slug" />
            </div>
            <div>
              <Label className="text-xs text-slate-500">Content (HTML)</Label>
              <Textarea value={editBlog.content || ''} rows={20} className="font-mono text-xs" onChange={e => setEditBlog(p => ({ ...p, content: e.target.value }))} data-testid="edit-content" />
            </div>
          </div>
          {/* Sidebar */}
          <div className="space-y-3">
            <Card><CardContent className="p-4 space-y-3">
              <div className="flex gap-2 flex-wrap">
                <Button size="sm" onClick={handleSaveEdit} disabled={saving} data-testid="save-blog-btn">
                  {saving ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <FileText className="w-3.5 h-3.5 mr-1" />}Save
                </Button>
                <Button size="sm" variant="outline" onClick={() => setPreviewBlog(editBlog)} data-testid="preview-blog-btn"><Eye className="w-3.5 h-3.5 mr-1" />Preview</Button>
                {editBlog.status === 'draft' ? (
                  <Button size="sm" className="bg-[#7CB342] hover:bg-[#689F38]" onClick={() => handlePublish(editBlog.id)} data-testid="publish-blog-btn"><Send className="w-3.5 h-3.5 mr-1" />Publish</Button>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => handleUnpublish(editBlog.id)} data-testid="unpublish-blog-btn"><RotateCcw className="w-3.5 h-3.5 mr-1" />Unpublish</Button>
                )}
              </div>
              <div className="text-xs text-slate-500 space-y-1">
                <p>Type: <strong className="capitalize">{editBlog.blog_type}</strong></p>
                {editBlog.region && <p>Region: <strong className="capitalize">{editBlog.region}</strong></p>}
                {editBlog.category && <p>Category: <strong>{editBlog.category}</strong></p>}
                <p>Industry: <strong>{editBlog.industry}</strong></p>
                <p>Words: ~{editBlog.word_count_estimate}</p>
                <p>CTA: <strong>{editBlog.cta_type}</strong></p>
                <p>Created: {fmtDate(editBlog.created_at)}</p>
              </div>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <Label className="text-xs text-slate-500">Keywords</Label>
              <Input value={(editBlog.keywords || []).join(', ')} onChange={e => setEditBlog(p => ({ ...p, keywords: e.target.value.split(',').map(k => k.trim()).filter(Boolean) }))} data-testid="edit-keywords" />
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <Label className="text-xs text-slate-500">Internal Links</Label>
              {(editBlog.internal_links || []).map((l, i) => <p key={i} className="text-xs text-blue-600 mt-1">{l}</p>)}
            </CardContent></Card>
            {editBlog.generation_log && (
              <Card><CardContent className="p-4">
                <Label className="text-xs text-slate-500 block mb-1">Generation Log</Label>
                <div className="text-xs text-slate-500 space-y-0.5">
                  <p>Topic: {editBlog.generation_log.topic_source}</p>
                  <p>Model: {editBlog.generation_log.model_used}</p>
                  <p>Generated: {fmtDate(editBlog.generation_log.generated_at)}</p>
                </div>
              </CardContent></Card>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ─── LIST VIEW ───
  return (
    <div className="space-y-5" data-testid="blog-engine-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900">Blog Engine</h1>
          <p className="text-slate-500 mt-1">Generate, manage, and publish SEO-optimized blog content</p>
        </div>
        <Button className="bg-[#7CB342] hover:bg-[#689F38] shrink-0" onClick={() => setShowGenerate(true)} data-testid="generate-blog-btn">
          <Sparkles className="w-4 h-4 mr-2" />Generate New Blog
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="flex items-center gap-4 flex-wrap">
          <TabsList>
            <TabsTrigger value="employer" data-testid="tab-employer">Employer Blogs</TabsTrigger>
            <TabsTrigger value="candidate" data-testid="tab-candidate">Candidate Blogs</TabsTrigger>
          </TabsList>
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-32" data-testid="blog-status-filter"><SelectValue placeholder="All" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="draft">Drafts</SelectItem>
              <SelectItem value="published">Published</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <TabsContent value={activeTab} className="mt-4">
          {loading ? <p className="text-center py-12 text-slate-400">Loading blogs...</p> :
            blogs.length === 0 ? (
              <Card><CardContent className="py-16 text-center text-slate-400">
                <Sparkles className="w-8 h-8 mx-auto mb-3 opacity-40" />
                <p>No {activeTab} blogs yet. Generate your first one!</p>
              </CardContent></Card>
            ) : (
              <div className="space-y-3">
                {blogs.map(b => (
                  <Card key={b.id} className="hover:shadow-md transition-shadow" data-testid={`blog-card-${b.id}`}>
                    <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <h3 className="font-semibold text-slate-900 truncate max-w-[400px]">{b.title}</h3>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE[b.status]}`}>{b.status}</span>
                          {b.region && <span className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded flex items-center gap-1">{b.region === 'global' ? <Globe className="w-3 h-3" /> : <MapPin className="w-3 h-3" />}{b.region}</span>}
                          {b.category && <span className="text-xs bg-purple-50 text-purple-600 px-1.5 py-0.5 rounded">{b.category}</span>}
                        </div>
                        <p className="text-sm text-slate-500 truncate">{b.meta_description}</p>
                        <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                          <span>{b.industry}</span>
                          <span>~{b.word_count_estimate} words</span>
                          <span>{fmtDate(b.published_at || b.created_at)}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Button variant="outline" size="sm" onClick={() => openEdit(b.id)} data-testid={`edit-btn-${b.id}`}><Pencil className="w-3.5 h-3.5 mr-1" />Edit</Button>
                        {b.status === 'draft' && <Button size="sm" className="bg-[#7CB342] hover:bg-[#689F38]" onClick={() => handlePublish(b.id)} data-testid={`publish-btn-${b.id}`}><Send className="w-3.5 h-3.5" /></Button>}
                        <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-700" onClick={() => handleDelete(b.id)} data-testid={`delete-btn-${b.id}`}><Trash2 className="w-3.5 h-3.5" /></Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )
          }
        </TabsContent>
      </Tabs>

      {/* Generate Dialog */}
      <Dialog open={showGenerate} onOpenChange={setShowGenerate}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle className="font-heading flex items-center gap-2"><Sparkles className="w-5 h-5 text-[#7CB342]" />Generate {activeTab === 'employer' ? 'Employer' : 'Candidate'} Blog</DialogTitle></DialogHeader>
          <div className="space-y-4" data-testid="generate-dialog">
            <div>
              <Label>Topic / Title Idea *</Label>
              <Input placeholder={activeTab === 'employer' ? 'e.g. How to hire plant managers in Gujarat' : 'e.g. 5 signs it is time to switch jobs in manufacturing'} value={genForm.topic} onChange={e => setGenForm(p => ({ ...p, topic: e.target.value }))} data-testid="gen-topic" />
            </div>
            <div>
              <Label>Industry Focus *</Label>
              <Input placeholder="e.g. Automotive, Steel, Pharma" value={genForm.industry} onChange={e => setGenForm(p => ({ ...p, industry: e.target.value }))} data-testid="gen-industry" />
            </div>
            <div>
              <Label>Target Keywords</Label>
              <Input placeholder="comma separated keywords" value={genForm.keywords} onChange={e => setGenForm(p => ({ ...p, keywords: e.target.value }))} data-testid="gen-keywords" />
            </div>
            {activeTab === 'employer' ? (
              <div>
                <Label>Region</Label>
                <Select value={genForm.region} onValueChange={v => setGenForm(p => ({ ...p, region: v }))}>
                  <SelectTrigger data-testid="gen-region"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="india">India</SelectItem>
                    <SelectItem value="global">Global</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <div>
                <Label>Category</Label>
                <Select value={genForm.category} onValueChange={v => setGenForm(p => ({ ...p, category: v }))}>
                  <SelectTrigger data-testid="gen-category"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CANDIDATE_CATEGORIES.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
            <Button className="w-full bg-[#7CB342] hover:bg-[#689F38]" onClick={handleGenerate} disabled={generating} data-testid="confirm-generate-btn">
              {generating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Generating (~30s)...</> : <><Sparkles className="w-4 h-4 mr-2" />Generate Blog</>}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Preview Dialog */}
      <Dialog open={!!previewBlog} onOpenChange={() => setPreviewBlog(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="font-heading">{previewBlog?.title}</DialogTitle></DialogHeader>
          {previewBlog && (
            <div data-testid="preview-dialog">
              <p className="text-sm text-slate-500 mb-4">{previewBlog.meta_description}</p>
              <div className="prose prose-slate max-w-none" dangerouslySetInnerHTML={{ __html: previewBlog.content }} />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
