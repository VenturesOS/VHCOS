import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { trackerAPI, jobAPI } from '../../lib/api';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Switch } from '../../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import {
  ChevronRight, ChevronLeft, Check, Plus, X, Search,
  Upload, FileSpreadsheet, Loader2, GripVertical, Trash2, ArrowRight,
} from 'lucide-react';

const FIELD_TYPE_LABELS = { text: 'Text', number: 'Number', currency: 'Currency', date: 'Date', dropdown: 'Dropdown' };
const STEPS = ['Basic Setup', 'Select Columns', 'Custom Columns', 'Configure Fields', 'Review'];
const UPLOAD_STEPS = ['Basic Setup', 'Upload File', 'Map Columns', 'Review'];

export default function CreateTrackerWizard({ open, onClose, onCreated }) {
  const [step, setStep] = useState(0);
  const [jobs, setJobs] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [masterCols, setMasterCols] = useState([]);
  const [categories, setCategories] = useState([]);
  const [creating, setCreating] = useState(false);

  // Step 1 state
  const [name, setName] = useState('');
  const [mandateId, setMandateId] = useState('');
  const [templateMode, setTemplateMode] = useState('new'); // 'existing' | 'new' | 'upload'
  const [existingTemplateId, setExistingTemplateId] = useState('');

  // Step 2 state - column selection
  const [selectedColumns, setSelectedColumns] = useState([]);

  // Step 3 state - custom columns
  const [customColumns, setCustomColumns] = useState([]);

  // Step 5 / Upload state
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadParsing, setUploadParsing] = useState(false);
  const [uploadMapping, setUploadMapping] = useState(null);

  useEffect(() => {
    if (!open) return;
    Promise.all([
      jobAPI.getAll(),
      trackerAPI.getTemplates(),
      trackerAPI.getColumns(),
    ]).then(([jb, tp, cols]) => {
      setJobs(Array.isArray(jb.data) ? jb.data : jb.data.jobs || []);
      setTemplates(tp.data.templates || []);
      setMasterCols(cols.data.columns || []);
      setCategories(cols.data.categories || []);
    }).catch(() => toast.error('Failed to load data'));
  }, [open]);

  const reset = () => {
    setStep(0); setName(''); setMandateId(''); setTemplateMode('new');
    setExistingTemplateId(''); setSelectedColumns([]); setCustomColumns([]);
    setUploadFile(null); setUploadParsing(false); setUploadMapping(null);
  };

  const handleClose = () => { reset(); onClose(); };
  const activeSteps = templateMode === 'upload' ? UPLOAD_STEPS : STEPS;

  const canNext = () => {
    if (step === 0) return name.trim() && mandateId && (templateMode === 'existing' ? existingTemplateId : true);
    if (templateMode === 'upload') {
      if (step === 1) return uploadMapping?.mapping?.length > 0;
      if (step === 2) return true;
    } else {
      if (step === 1) return selectedColumns.length > 0;
    }
    return true;
  };

  const handleNext = () => { if (canNext()) setStep(s => s + 1); };
  const handleBack = () => setStep(s => Math.max(0, s - 1));

  // ── FINALIZE: Create template + tracker ──
  const handleCreate = async () => {
    setCreating(true);
    try {
      let templateId = existingTemplateId;

      if (templateMode === 'new' || templateMode === 'upload') {
        let columns;
        if (templateMode === 'upload' && uploadMapping) {
          columns = uploadMapping.mapping
            .filter(m => m.matched || m.custom)
            .map((m, i) => ({
              key: m.master_column?.key || m.customKey || `col_${i}`,
              label: m.master_column?.label || m.header,
              category: m.master_column?.category || 'Custom',
              field_type: m.master_column?.field_type || 'text',
              required: m.required || false,
              order: i,
              is_custom: !m.matched,
            }));
        } else {
          const masterSelected = selectedColumns.map((key, i) => {
            const mc = masterCols.find(c => c.key === key);
            return {
              key, label: mc?.label || key, category: mc?.category || 'Custom',
              field_type: mc?.field_type || 'text',
              required: mc?._required ?? mc?.default_required ?? false,
              order: i, is_custom: false,
              dropdown_options: mc?.dropdown_options || null,
            };
          });
          const customs = customColumns.map((c, i) => ({
            key: c.key, label: c.label, category: 'Custom',
            field_type: c.field_type, required: c.required,
            order: masterSelected.length + i, is_custom: true,
            dropdown_options: c.dropdown_options?.length > 0 ? c.dropdown_options : null,
          }));
          columns = [...masterSelected, ...customs];
        }

        const mandate = jobs.find(j => j.id === mandateId);
        const tplRes = await trackerAPI.createTemplate({
          name: `${name} Template`,
          description: `Auto-created for ${mandate?.title || 'mandate'}`,
          columns,
        });
        templateId = tplRes.data.id;
      }

      const res = await trackerAPI.createTracker({
        name, mandate_id: mandateId, template_id: templateId,
      });
      toast.success('Tracker created successfully');
      handleClose();
      onCreated(res.data.id);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to create tracker');
    } finally { setCreating(false); }
  };

  const isLastStep = step === activeSteps.length - 1;

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) handleClose(); }}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col p-0 gap-0" data-testid="create-tracker-wizard">
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-slate-100">
          <DialogTitle className="text-lg" data-testid="wizard-title">Create New Tracker</DialogTitle>
          <DialogDescription className="sr-only">Multi-step wizard to configure and create a new submission tracker</DialogDescription>
          {/* Step indicator */}
          <div className="flex items-center gap-1 mt-3">
            {activeSteps.map((s, i) => (
              <div key={s} className="flex items-center gap-1">
                <button
                  onClick={() => i < step && setStep(i)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                    i === step ? 'bg-blue-600 text-white' :
                    i < step ? 'bg-emerald-100 text-emerald-700 cursor-pointer hover:bg-emerald-200' :
                    'bg-slate-100 text-slate-400'
                  }`}
                  data-testid={`wizard-step-${i}`}
                >
                  {i < step ? <Check className="w-3 h-3" /> : <span>{i + 1}</span>}
                  <span className="hidden sm:inline">{s}</span>
                </button>
                {i < activeSteps.length - 1 && <ChevronRight className="w-3 h-3 text-slate-300" />}
              </div>
            ))}
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-4 min-h-[320px]">
          {step === 0 && (
            <BasicSetupStep
              name={name} setName={setName}
              mandateId={mandateId} setMandateId={setMandateId}
              templateMode={templateMode} setTemplateMode={setTemplateMode}
              existingTemplateId={existingTemplateId} setExistingTemplateId={setExistingTemplateId}
              jobs={jobs} templates={templates}
            />
          )}
          {templateMode !== 'upload' && step === 1 && (
            <ColumnSelectionStep
              masterCols={masterCols} categories={categories}
              selectedColumns={selectedColumns} setSelectedColumns={setSelectedColumns}
            />
          )}
          {templateMode !== 'upload' && step === 2 && (
            <CustomColumnsStep
              customColumns={customColumns} setCustomColumns={setCustomColumns}
              existingKeys={new Set([...selectedColumns, ...customColumns.map(c => c.key)])}
            />
          )}
          {templateMode !== 'upload' && step === 3 && (
            <RequiredFieldsStep
              masterCols={masterCols}
              selectedColumns={selectedColumns} setSelectedColumns={setSelectedColumns}
              customColumns={customColumns} setCustomColumns={setCustomColumns}
            />
          )}
          {templateMode !== 'upload' && step === 4 && (
            <ReviewStep
              name={name} mandateId={mandateId} jobs={jobs}
              templateMode={templateMode} existingTemplateId={existingTemplateId}
              templates={templates} masterCols={masterCols}
              selectedColumns={selectedColumns} customColumns={customColumns}
            />
          )}
          {templateMode === 'upload' && step === 1 && (
            <UploadStep
              uploadFile={uploadFile} setUploadFile={setUploadFile}
              uploadParsing={uploadParsing} setUploadParsing={setUploadParsing}
              uploadMapping={uploadMapping} setUploadMapping={setUploadMapping}
            />
          )}
          {templateMode === 'upload' && step === 2 && (
            <MappingStep
              uploadMapping={uploadMapping} setUploadMapping={setUploadMapping}
              masterCols={masterCols}
            />
          )}
          {templateMode === 'upload' && step === 3 && (
            <ReviewStep
              name={name} mandateId={mandateId} jobs={jobs}
              templateMode="upload" uploadMapping={uploadMapping}
              masterCols={masterCols} selectedColumns={[]} customColumns={[]}
              templates={templates}
            />
          )}
        </div>

        <DialogFooter className="px-6 py-3 border-t border-slate-100 flex justify-between">
          <div className="flex gap-2">
            {step > 0 && <Button variant="outline" onClick={handleBack} data-testid="wizard-back"><ChevronLeft className="w-4 h-4 mr-1" /> Back</Button>}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleClose}>Cancel</Button>
            {templateMode === 'existing' && step === 0 ? (
              <Button onClick={handleCreate} disabled={!canNext() || creating} data-testid="wizard-create">
                {creating ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Check className="w-4 h-4 mr-1" />}
                Create Tracker
              </Button>
            ) : isLastStep ? (
              <Button onClick={handleCreate} disabled={creating} data-testid="wizard-create">
                {creating ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Check className="w-4 h-4 mr-1" />}
                Create Tracker
              </Button>
            ) : (
              <Button onClick={handleNext} disabled={!canNext()} data-testid="wizard-next">
                Next <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ═══════════════════════════════════════
// STEP 1: Basic Setup
// ═══════════════════════════════════════
function BasicSetupStep({ name, setName, mandateId, setMandateId, templateMode, setTemplateMode, existingTemplateId, setExistingTemplateId, jobs, templates }) {
  return (
    <div className="space-y-5" data-testid="step-basic-setup">
      <div>
        <Label className="text-sm font-medium">Tracker Name *</Label>
        <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Senior Python Dev — ABC Corp" className="mt-1.5" data-testid="wizard-tracker-name" />
      </div>
      <div>
        <Label className="text-sm font-medium">Mandate / Job *</Label>
        <Select value={mandateId} onValueChange={setMandateId}>
          <SelectTrigger className="mt-1.5" data-testid="wizard-mandate-select"><SelectValue placeholder="Select a mandate" /></SelectTrigger>
          <SelectContent>
            {jobs.map(j => <SelectItem key={j.id} value={j.id}>{j.title}{j.company_name ? ` — ${j.company_name}` : ''}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="text-sm font-medium">Template</Label>
        <div className="grid grid-cols-3 gap-3 mt-2">
          {[
            { key: 'existing', label: 'Use Existing', icon: FileSpreadsheet, desc: 'Pick a saved template' },
            { key: 'new', label: 'Create New', icon: Plus, desc: 'Build from column library' },
            { key: 'upload', label: 'Upload File', icon: Upload, desc: 'Import from Excel/CSV' },
          ].map(opt => (
            <button key={opt.key} onClick={() => setTemplateMode(opt.key)}
              className={`p-3 rounded-xl border-2 text-left transition-all ${
                templateMode === opt.key
                  ? 'border-blue-500 bg-blue-50/80 ring-1 ring-blue-200'
                  : 'border-slate-200 hover:border-slate-300 bg-white'
              }`}
              data-testid={`template-mode-${opt.key}`}
            >
              <opt.icon className={`w-5 h-5 mb-1.5 ${templateMode === opt.key ? 'text-blue-600' : 'text-slate-400'}`} />
              <p className="text-sm font-medium">{opt.label}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">{opt.desc}</p>
            </button>
          ))}
        </div>
      </div>
      {templateMode === 'existing' && (
        <div>
          <Label className="text-sm font-medium">Select Template *</Label>
          <Select value={existingTemplateId} onValueChange={setExistingTemplateId}>
            <SelectTrigger className="mt-1.5" data-testid="wizard-existing-template"><SelectValue placeholder="Choose template" /></SelectTrigger>
            <SelectContent>
              {templates.map(t => (
                <SelectItem key={t.id} value={t.id}>
                  {t.name} <span className="text-muted-foreground ml-1">({t.columns?.length || 0} cols)</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// STEP 2: Column Selection
// ═══════════════════════════════════════
function ColumnSelectionStep({ masterCols, categories, selectedColumns, setSelectedColumns }) {
  const [search, setSearch] = useState('');

  const grouped = useMemo(() => {
    const g = {};
    for (const cat of categories) g[cat] = [];
    masterCols.forEach(c => {
      if (search && !c.label.toLowerCase().includes(search.toLowerCase()) && !c.key.toLowerCase().includes(search.toLowerCase())) return;
      (g[c.category] = g[c.category] || []).push(c);
    });
    return g;
  }, [masterCols, categories, search]);

  const toggle = (key) => {
    setSelectedColumns(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  };

  const selectAll = (cat) => {
    const keys = (grouped[cat] || []).map(c => c.key);
    const allSelected = keys.every(k => selectedColumns.includes(k));
    if (allSelected) setSelectedColumns(prev => prev.filter(k => !keys.includes(k)));
    else setSelectedColumns(prev => [...new Set([...prev, ...keys])]);
  };

  return (
    <div className="space-y-4" data-testid="step-column-selection">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">{selectedColumns.length} columns selected</p>
      </div>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search columns..." className="pl-9" data-testid="column-search" />
      </div>
      <div className="space-y-3 max-h-[340px] overflow-y-auto pr-1">
        {Object.entries(grouped).map(([cat, cols]) => {
          if (cols.length === 0) return null;
          const allSel = cols.every(c => selectedColumns.includes(c.key));
          return (
            <div key={cat} data-testid={`category-${cat}`}>
              <button onClick={() => selectAll(cat)}
                className="flex items-center gap-2 w-full text-left mb-1.5 group">
                <span className={`w-4 h-4 rounded border flex items-center justify-center text-[10px] transition-colors ${
                  allSel ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-300 group-hover:border-slate-400'
                }`}>{allSel && <Check className="w-3 h-3" />}</span>
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{cat}</span>
                <span className="text-[10px] text-slate-400 ml-auto">{cols.filter(c => selectedColumns.includes(c.key)).length}/{cols.length}</span>
              </button>
              <div className="grid grid-cols-2 gap-1 ml-6">
                {cols.sort((a, b) => a.label.localeCompare(b.label)).map(c => {
                  const sel = selectedColumns.includes(c.key);
                  return (
                    <button key={c.key} onClick={() => toggle(c.key)}
                      className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left text-xs transition-all ${
                        sel ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200' : 'hover:bg-slate-50 text-slate-600'
                      }`}
                      data-testid={`col-${c.key}`}
                    >
                      <span className={`w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 ${
                        sel ? 'bg-blue-600 border-blue-600' : 'border-slate-300'
                      }`}>{sel && <Check className="w-2.5 h-2.5 text-white" />}</span>
                      <span className="truncate">{c.label}</span>
                      <Badge variant="outline" className="ml-auto text-[9px] px-1 py-0 shrink-0">{c.field_type}</Badge>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// STEP 3: Custom Columns
// ═══════════════════════════════════════
function CustomColumnsStep({ customColumns, setCustomColumns, existingKeys }) {
  const [showAdd, setShowAdd] = useState(false);
  const [newLabel, setNewLabel] = useState('');
  const [newType, setNewType] = useState('text');
  const [newRequired, setNewRequired] = useState(false);
  const [newDropdownOpts, setNewDropdownOpts] = useState('');

  const addColumn = () => {
    if (!newLabel.trim()) return toast.error('Column name required');
    const key = `custom_${newLabel.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_')}`;
    if (existingKeys.has(key)) return toast.error('Column already exists');

    setCustomColumns(prev => [...prev, {
      key, label: newLabel.trim(), field_type: newType, required: newRequired,
      dropdown_options: newType === 'dropdown' ? newDropdownOpts.split(',').map(o => o.trim()).filter(Boolean) : [],
    }]);
    setNewLabel(''); setNewType('text'); setNewRequired(false); setNewDropdownOpts('');
    setShowAdd(false);
  };

  const removeColumn = (key) => setCustomColumns(prev => prev.filter(c => c.key !== key));

  return (
    <div className="space-y-4" data-testid="step-custom-columns">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">Add custom fields that aren't in the master column library</p>
        <Button size="sm" variant="outline" onClick={() => setShowAdd(true)} data-testid="add-custom-col-btn">
          <Plus className="w-3.5 h-3.5 mr-1" /> Add Column
        </Button>
      </div>

      {showAdd && (
        <div className="p-4 rounded-xl border border-blue-200 bg-blue-50/40 space-y-3" data-testid="add-custom-form">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Column Name *</Label>
              <Input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="e.g. Interview Feedback" className="mt-1 text-sm" data-testid="custom-col-name" />
            </div>
            <div>
              <Label className="text-xs">Field Type</Label>
              <Select value={newType} onValueChange={setNewType}>
                <SelectTrigger className="mt-1" data-testid="custom-col-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(FIELD_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          {newType === 'dropdown' && (
            <div>
              <Label className="text-xs">Dropdown Options (comma-separated)</Label>
              <Input value={newDropdownOpts} onChange={e => setNewDropdownOpts(e.target.value)} placeholder="Option 1, Option 2, Option 3" className="mt-1 text-sm" data-testid="custom-col-options" />
            </div>
          )}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Switch checked={newRequired} onCheckedChange={setNewRequired} data-testid="custom-col-required" />
              <Label className="text-xs">Required field</Label>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button size="sm" onClick={addColumn} data-testid="confirm-add-custom">Add</Button>
            </div>
          </div>
        </div>
      )}

      {customColumns.length === 0 && !showAdd && (
        <div className="text-center py-8 text-sm text-slate-400 border border-dashed rounded-xl">
          No custom columns added yet. This step is optional.
        </div>
      )}

      {customColumns.length > 0 && (
        <div className="space-y-2">
          {customColumns.map(c => (
            <div key={c.key} className="flex items-center gap-3 p-3 bg-white rounded-lg border border-slate-200" data-testid={`custom-col-${c.key}`}>
              <GripVertical className="w-4 h-4 text-slate-300 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-800 truncate">{c.label}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <Badge variant="outline" className="text-[9px]">{FIELD_TYPE_LABELS[c.field_type]}</Badge>
                  {c.required && <Badge className="text-[9px] bg-red-50 text-red-600 border-red-200">Required</Badge>}
                  {c.dropdown_options?.length > 0 && <span className="text-[9px] text-slate-400">{c.dropdown_options.length} options</span>}
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => removeColumn(c.key)} className="text-slate-400 hover:text-red-500 shrink-0" data-testid={`remove-custom-${c.key}`}>
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// STEP 4: Required Fields Configuration
// ═══════════════════════════════════════
function RequiredFieldsStep({ masterCols, selectedColumns, setSelectedColumns, customColumns, setCustomColumns }) {
  const allCols = useMemo(() => {
    const master = selectedColumns.map(key => {
      const mc = masterCols.find(c => c.key === key);
      return { key, label: mc?.label || key, type: 'master', required: mc?._required ?? mc?.default_required ?? false };
    });
    const custom = customColumns.map(c => ({ key: c.key, label: c.label, type: 'custom', required: c.required }));
    return [...master, ...custom];
  }, [masterCols, selectedColumns, customColumns]);

  const toggleRequired = (key, type) => {
    if (type === 'master') {
      const mc = masterCols.find(c => c.key === key);
      if (mc) mc._required = !mc._required;
      setSelectedColumns([...selectedColumns]); // force re-render
    } else {
      setCustomColumns(prev => prev.map(c => c.key === key ? { ...c, required: !c.required } : c));
    }
  };

  const requiredCount = allCols.filter(c => c.required).length;

  return (
    <div className="space-y-4" data-testid="step-required-fields">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">Mark fields as required for download validation</p>
        <Badge variant="outline" className="text-xs">{requiredCount} required / {allCols.length} total</Badge>
      </div>
      <div className="space-y-1.5 max-h-[360px] overflow-y-auto pr-1">
        {allCols.map(c => (
          <div key={c.key} className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 transition-colors" data-testid={`req-${c.key}`}>
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm text-slate-700 truncate">{c.label}</span>
              {c.type === 'custom' && <Badge variant="outline" className="text-[9px] shrink-0">Custom</Badge>}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-[10px] ${c.required ? 'text-red-500 font-medium' : 'text-slate-400'}`}>
                {c.required ? 'Required' : 'Optional'}
              </span>
              <Switch checked={c.required} onCheckedChange={() => toggleRequired(c.key, c.type)} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// Upload Step
// ═══════════════════════════════════════
function UploadStep({ uploadFile, setUploadFile, uploadParsing, setUploadParsing, uploadMapping, setUploadMapping }) {
  const fileRef = useRef(null);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadFile(file);
    setUploadParsing(true);
    try {
      const res = await trackerAPI.parseTemplateFile(file);
      setUploadMapping(res.data);
      toast.success(`Parsed ${res.data.total_headers} columns, ${res.data.matched_count} auto-matched`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to parse file');
      setUploadFile(null);
    } finally { setUploadParsing(false); }
  };

  return (
    <div className="space-y-4" data-testid="step-upload">
      <p className="text-sm text-slate-600">Upload an Excel or CSV file to auto-detect column structure</p>
      <div
        className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-all"
        onClick={() => fileRef.current?.click()}
        data-testid="upload-dropzone"
      >
        <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleFile} className="hidden" />
        {uploadParsing ? (
          <Loader2 className="w-8 h-8 mx-auto text-blue-500 animate-spin" />
        ) : uploadFile ? (
          <>
            <FileSpreadsheet className="w-8 h-8 mx-auto text-emerald-500 mb-2" />
            <p className="text-sm font-medium text-slate-700">{uploadFile.name}</p>
            {uploadMapping && (
              <p className="text-xs text-emerald-600 mt-1">
                {uploadMapping.matched_count}/{uploadMapping.total_headers} columns auto-matched
              </p>
            )}
          </>
        ) : (
          <>
            <Upload className="w-8 h-8 mx-auto text-slate-300 mb-2" />
            <p className="text-sm text-slate-500">Click to upload .xlsx or .csv</p>
          </>
        )}
      </div>

      {uploadMapping?.sample_rows?.length > 0 && (
        <div className="overflow-x-auto">
          <p className="text-xs font-medium text-slate-500 mb-1.5">Sample Data Preview</p>
          <table className="w-full text-xs border border-slate-200 rounded">
            <thead>
              <tr className="bg-slate-50">
                {uploadMapping.headers.map((h, i) => (
                  <th key={i} className="px-2 py-1.5 text-left font-medium text-slate-600 border-b">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {uploadMapping.sample_rows.map((row, i) => (
                <tr key={i} className="border-b border-slate-100">
                  {row.map((cell, j) => (
                    <td key={j} className="px-2 py-1 text-slate-500 max-w-[120px] truncate">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// Mapping Step (Upload flow)
// ═══════════════════════════════════════
function MappingStep({ uploadMapping, setUploadMapping, masterCols }) {
  if (!uploadMapping) return null;

  const updateMapping = (idx, masterKey) => {
    setUploadMapping(prev => {
      const newMapping = prev.mapping.map(m => {
        if (m.index === idx) {
          if (masterKey === '_skip') return { ...m, matched: false, master_column: null, custom: false };
          if (masterKey === '_custom') return { ...m, matched: false, master_column: null, custom: true, customKey: `upload_${m.header.toLowerCase().replace(/[^a-z0-9]+/g, '_')}` };
          const mc = masterCols.find(c => c.key === masterKey);
          return { ...m, matched: true, master_column: mc, custom: false };
        }
        return m;
      });
      return { ...prev, mapping: newMapping, matched_count: newMapping.filter(m => m.matched).length };
    });
  };

  const toggleRequired = (idx) => {
    setUploadMapping(prev => ({
      ...prev,
      mapping: prev.mapping.map(m => m.index === idx ? { ...m, required: !m.required } : m),
    }));
  };

  return (
    <div className="space-y-4" data-testid="step-mapping">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">Map file columns to master fields</p>
        <Badge variant="outline" className="text-xs">{uploadMapping.matched_count}/{uploadMapping.total_headers} matched</Badge>
      </div>
      <div className="space-y-2 max-h-[340px] overflow-y-auto pr-1">
        {uploadMapping.mapping.map(m => (
          <div key={m.index} className={`flex items-center gap-3 p-2.5 rounded-lg border ${
            m.matched ? 'border-emerald-200 bg-emerald-50/40' :
            m.custom ? 'border-blue-200 bg-blue-50/40' :
            'border-slate-200'
          }`} data-testid={`map-row-${m.index}`}>
            <div className="w-32 shrink-0">
              <p className="text-xs font-medium text-slate-700 truncate">{m.header}</p>
            </div>
            <ArrowRight className="w-3 h-3 text-slate-300 shrink-0" />
            <Select value={m.matched ? m.master_column?.key : m.custom ? '_custom' : '_skip'} onValueChange={v => updateMapping(m.index, v)}>
              <SelectTrigger className="h-8 text-xs flex-1"><SelectValue placeholder="Map to..." /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_skip"><span className="text-slate-400">Skip column</span></SelectItem>
                <SelectItem value="_custom"><span className="text-blue-600">Keep as custom</span></SelectItem>
                {masterCols.map(c => <SelectItem key={c.key} value={c.key}>{c.label} ({c.category})</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-1.5 shrink-0">
              <Switch checked={m.required || false} onCheckedChange={() => toggleRequired(m.index)} />
              <span className="text-[9px] text-slate-400 w-8">{m.required ? 'Req' : 'Opt'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// Review Step
// ═══════════════════════════════════════
function ReviewStep({ name, mandateId, jobs, templateMode, existingTemplateId, templates, masterCols, selectedColumns, customColumns, uploadMapping }) {
  const mandate = jobs.find(j => j.id === mandateId);

  let columnSummary = [];
  if (templateMode === 'existing') {
    const tpl = templates.find(t => t.id === existingTemplateId);
    columnSummary = tpl?.columns?.map(c => ({ label: c.label, required: c.required, type: c.is_custom ? 'Custom' : c.category })) || [];
  } else if (templateMode === 'upload' && uploadMapping) {
    columnSummary = uploadMapping.mapping
      .filter(m => m.matched || m.custom)
      .map(m => ({
        label: m.master_column?.label || m.header,
        required: m.required || false,
        type: m.matched ? (m.master_column?.category || 'Master') : 'Custom',
      }));
  } else {
    const mc = selectedColumns.map(key => {
      const c = masterCols.find(col => col.key === key);
      return { label: c?.label || key, required: c?._required ?? c?.default_required ?? false, type: c?.category || 'Master' };
    });
    const cc = customColumns.map(c => ({ label: c.label, required: c.required, type: 'Custom' }));
    columnSummary = [...mc, ...cc];
  }

  const requiredCount = columnSummary.filter(c => c.required).length;

  return (
    <div className="space-y-4" data-testid="step-review">
      <p className="text-sm text-slate-600">Review your tracker configuration before creating</p>

      <div className="grid grid-cols-2 gap-4">
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Tracker</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">{name}</p>
        </div>
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Mandate</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">{mandate?.title || 'Unknown'}</p>
        </div>
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Template</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">
            {templateMode === 'existing' ? templates.find(t => t.id === existingTemplateId)?.name : 'New (auto-created)'}
          </p>
        </div>
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Columns</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">{columnSummary.length} total, {requiredCount} required</p>
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-slate-500 mb-2">Column List</p>
        <div className="max-h-[200px] overflow-y-auto space-y-1 pr-1">
          {columnSummary.map((c, i) => (
            <div key={i} className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-white border border-slate-100 text-xs">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-slate-700 truncate">{c.label}</span>
                <Badge variant="outline" className="text-[8px] px-1 shrink-0">{c.type}</Badge>
              </div>
              {c.required && <Badge className="text-[8px] bg-red-50 text-red-600 border-red-200 shrink-0">Required</Badge>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
