import { useState, useEffect } from 'react';
import { trackerAPI, jobAPI } from '../../lib/api';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../../components/ui/dialog';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import { ChevronRight, ChevronLeft, Check, Loader2 } from 'lucide-react';

import BasicSetupStep from './tracker-steps/BasicSetupStep';
import ColumnSelectionStep from './tracker-steps/ColumnSelectionStep';
import CustomColumnsStep from './tracker-steps/CustomColumnsStep';
import RequiredFieldsStep from './tracker-steps/RequiredFieldsStep';
import UploadStep from './tracker-steps/UploadStep';
import MappingStep from './tracker-steps/MappingStep';
import ReviewStep from './tracker-steps/ReviewStep';

const STEPS = ['Basic Setup', 'Select Columns', 'Custom Columns', 'Configure Fields', 'Review'];
const UPLOAD_STEPS = ['Basic Setup', 'Upload File', 'Map Columns', 'Review'];

export default function CreateTrackerWizard({ open, onClose, onCreated }) {
  const [step, setStep] = useState(0);
  const [jobs, setJobs] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [masterCols, setMasterCols] = useState([]);
  const [categories, setCategories] = useState([]);
  const [creating, setCreating] = useState(false);

  const [name, setName] = useState('');
  const [mandateId, setMandateId] = useState('');
  const [templateMode, setTemplateMode] = useState('new');
  const [existingTemplateId, setExistingTemplateId] = useState('');
  const [selectedColumns, setSelectedColumns] = useState([]);
  const [customColumns, setCustomColumns] = useState([]);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadParsing, setUploadParsing] = useState(false);
  const [uploadMapping, setUploadMapping] = useState(null);

  useEffect(() => {
    if (!open) return;
    Promise.all([jobAPI.getAll(), trackerAPI.getTemplates(), trackerAPI.getColumns()])
      .then(([jb, tp, cols]) => {
        setJobs(Array.isArray(jb.data) ? jb.data : jb.data.jobs || []);
        setTemplates(tp.data.templates || []);
        setMasterCols(cols.data.columns || []);
        setCategories(cols.data.categories || []);
      })
      .catch(() => toast.error('Failed to load data'));
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
    } else {
      if (step === 1) return selectedColumns.length > 0;
    }
    return true;
  };

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
              required: m.required || false, order: i, is_custom: !m.matched,
            }));
        } else {
          const masterSelected = selectedColumns.map((key, i) => {
            const mc = masterCols.find(c => c.key === key);
            return {
              key, label: mc?.label || key, category: mc?.category || 'Custom',
              field_type: mc?.field_type || 'text', required: mc?._required ?? mc?.default_required ?? false,
              order: i, is_custom: false, dropdown_options: mc?.dropdown_options || null,
            };
          });
          const customs = customColumns.map((c, i) => ({
            key: c.key, label: c.label, category: 'Custom', field_type: c.field_type,
            required: c.required, order: masterSelected.length + i, is_custom: true,
            dropdown_options: c.dropdown_options?.length > 0 ? c.dropdown_options : null,
          }));
          columns = [...masterSelected, ...customs];
        }
        const mandate = jobs.find(j => j.id === mandateId);
        const tplRes = await trackerAPI.createTemplate({
          name: `${name} Template`, description: `Auto-created for ${mandate?.title || 'mandate'}`, columns,
        });
        templateId = tplRes.data.id;
      }
      const res = await trackerAPI.createTracker({ name, mandate_id: mandateId, template_id: templateId });
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
          <div className="flex items-center gap-1 mt-3">
            {activeSteps.map((s, i) => (
              <div key={s} className="flex items-center gap-1">
                <button onClick={() => i < step && setStep(i)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                    i === step ? 'bg-blue-600 text-white' : i < step ? 'bg-emerald-100 text-emerald-700 cursor-pointer hover:bg-emerald-200' : 'bg-slate-100 text-slate-400'
                  }`} data-testid={`wizard-step-${i}`}>
                  {i < step ? <Check className="w-3 h-3" /> : <span>{i + 1}</span>}
                  <span className="hidden sm:inline">{s}</span>
                </button>
                {i < activeSteps.length - 1 && <ChevronRight className="w-3 h-3 text-slate-300" />}
              </div>
            ))}
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-4 min-h-[320px]">
          {step === 0 && <BasicSetupStep name={name} setName={setName} mandateId={mandateId} setMandateId={setMandateId} templateMode={templateMode} setTemplateMode={setTemplateMode} existingTemplateId={existingTemplateId} setExistingTemplateId={setExistingTemplateId} jobs={jobs} templates={templates} />}
          {templateMode !== 'upload' && step === 1 && <ColumnSelectionStep masterCols={masterCols} categories={categories} selectedColumns={selectedColumns} setSelectedColumns={setSelectedColumns} />}
          {templateMode !== 'upload' && step === 2 && <CustomColumnsStep customColumns={customColumns} setCustomColumns={setCustomColumns} existingKeys={new Set([...selectedColumns, ...customColumns.map(c => c.key)])} />}
          {templateMode !== 'upload' && step === 3 && <RequiredFieldsStep masterCols={masterCols} selectedColumns={selectedColumns} setSelectedColumns={setSelectedColumns} customColumns={customColumns} setCustomColumns={setCustomColumns} />}
          {templateMode !== 'upload' && step === 4 && <ReviewStep name={name} mandateId={mandateId} jobs={jobs} templateMode={templateMode} existingTemplateId={existingTemplateId} templates={templates} masterCols={masterCols} selectedColumns={selectedColumns} customColumns={customColumns} />}
          {templateMode === 'upload' && step === 1 && <UploadStep uploadFile={uploadFile} setUploadFile={setUploadFile} uploadParsing={uploadParsing} setUploadParsing={setUploadParsing} uploadMapping={uploadMapping} setUploadMapping={setUploadMapping} />}
          {templateMode === 'upload' && step === 2 && <MappingStep uploadMapping={uploadMapping} setUploadMapping={setUploadMapping} masterCols={masterCols} />}
          {templateMode === 'upload' && step === 3 && <ReviewStep name={name} mandateId={mandateId} jobs={jobs} templateMode="upload" uploadMapping={uploadMapping} masterCols={masterCols} selectedColumns={[]} customColumns={[]} templates={templates} />}
        </div>

        <DialogFooter className="px-6 py-3 border-t border-slate-100 flex justify-between">
          <div className="flex gap-2">
            {step > 0 && <Button variant="outline" onClick={() => setStep(s => Math.max(0, s - 1))} data-testid="wizard-back"><ChevronLeft className="w-4 h-4 mr-1" /> Back</Button>}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleClose}>Cancel</Button>
            {(templateMode === 'existing' && step === 0) || isLastStep ? (
              <Button onClick={handleCreate} disabled={!canNext() || creating} data-testid="wizard-create">
                {creating ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Check className="w-4 h-4 mr-1" />} Create Tracker
              </Button>
            ) : (
              <Button onClick={() => { if (canNext()) setStep(s => s + 1); }} disabled={!canNext()} data-testid="wizard-next">
                Next <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
