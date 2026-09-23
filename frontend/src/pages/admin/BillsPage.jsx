/**
 * BillsPage — Phase 55.6 (May 2026)
 *
 * Admin / Employer / Account-Manager workflow:
 *  1. New Bill — pick client company → add line items (CTC × commercial%) → save draft
 *  2. Preview PDF (inline iframe)
 *  3. Compose & send — LLM-generated mail body (Qwen), edit before sending,
 *     CC = accounts@vhc.in (locked) + employer + bsy@ + rohit@ + admin extras
 *  4. Track status: draft → sent → paid (or cancelled)
 *  5. Reminders auto-fire from `scripts/run_bill_reminders.py` cron (T+7/14/30)
 */
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Tabs, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { InvoiceWorklist } from '../../components/revenue/InvoiceWorklist';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Card, CardContent } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import {
  Plus,
  Send,
  FileText,
  CheckCircle2,
  Trash2,
  RotateCcw,
  Eye,
  Sparkles,
  XCircle,
  Landmark,
} from 'lucide-react';
import { billsAPI, companyAPI } from '../../lib/api';

const STATUS_COLORS = {
  draft: 'bg-slate-100 text-slate-700',
  sent: 'bg-blue-100 text-blue-700',
  paid: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-red-100 text-red-700',
  viewed: 'bg-indigo-100 text-indigo-700',
};

const inr = (n) =>
  '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function emptyLine() {
  return {
    candidate_name: '',
    designation: '',
    joining_date: new Date().toISOString().slice(0, 10),
    annual_ctc: 0,
    commercial_rate_pct: 8.33,
    line_amount: 0,
    hsn_sac: '998512',
  };
}

export default function BillsPage() {
  const [bills, setBills] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showSendDialog, setShowSendDialog] = useState(null);
  const [previewBill, setPreviewBill] = useState(null);
  // fix.docx (2026-09-15): bank accounts + client email override
  const [bankAccounts, setBankAccounts] = useState([]);
  const [mainTab, setMainTab] = useState('invoices');
  const [showBankDialog, setShowBankDialog] = useState(false);
  const [bankForm, setBankForm] = useState({
    id: null, label: '', bank_name: '', beneficiary_name: '',
    branch: '', account_number: '', ifsc: '', is_default: false,
  });
  // Fix 5.14 (spec 2026-09-08): the iframe cannot pass the Bearer token so
  // the PDF endpoint returned 401 and the modal rendered blank. Fetch the
  // PDF as an authenticated blob and hand the iframe an object URL.
  const [previewBlobUrl, setPreviewBlobUrl] = useState(null);

  useEffect(() => {
    let cancelled = false;
    let currentUrl = null;
    if (previewBill) {
      const token = localStorage.getItem('vhc_token');
      fetch(billsAPI.pdfUrl(previewBill.id), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then(r => {
          if (!r.ok) throw new Error(`PDF fetch failed (${r.status})`);
          return r.blob();
        })
        .then(blob => {
          if (cancelled) return;
          currentUrl = URL.createObjectURL(blob);
          setPreviewBlobUrl(currentUrl);
        })
        .catch(e => {
          if (!cancelled) toast.error(e.message || 'Preview failed');
        });
    } else {
      setPreviewBlobUrl(null);
    }
    return () => {
      cancelled = true;
      if (currentUrl) URL.revokeObjectURL(currentUrl);
    };
  }, [previewBill]);

  const downloadPreviewPdf = async () => {
    if (!previewBill) return;
    try {
      const token = localStorage.getItem('vhc_token');
      const r = await fetch(billsAPI.pdfUrl(previewBill.id), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!r.ok) throw new Error(`Download failed (${r.status})`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${previewBill.bill_number || 'bill'}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e.message || 'Download failed');
    }
  };
  const [sendForm, setSendForm] = useState({ to_email: '', extra_cc: '', subject: '', body: '', test_mode: false });
  const [generating, setGenerating] = useState(false);

  // New bill form state
  const [newBill, setNewBill] = useState({
    client_company_id: '',
    sender_variant: 'VENTURE HRD CENTER',
    bill_date: new Date().toISOString().slice(0, 10),
    due_date: '',
    gst_kind: '',
    bank_account_id: '',
    line_items: [emptyLine()],
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [bs, cs, banks] = await Promise.all([
        billsAPI.list(),
        companyAPI.getAll().catch(() => ({ data: [] })),
        billsAPI.listBankAccounts().catch(() => ({ data: { items: [] } })),
      ]);
      setBills(bs.data?.items || []);
      setCompanies(cs.data || []);
      setBankAccounts(banks.data?.items || []);
    } catch (e) {
      toast.error('Failed to load bills');
    } finally {
      setLoading(false);
    }
  };

  const openEditBank = (b) => {
    setBankForm(b ? { ...b } : {
      id: null, label: '', bank_name: '', beneficiary_name: '',
      branch: '', account_number: '', ifsc: '', is_default: false,
    });
    setShowBankDialog(true);
  };

  const saveBank = async () => {
    if (!bankForm.label || !bankForm.bank_name || !bankForm.account_number || !bankForm.ifsc) {
      toast.error('Label, Bank name, A/C number and IFSC are required.');
      return;
    }
    try {
      if (bankForm.id) {
        await billsAPI.updateBankAccount(bankForm.id, bankForm);
        toast.success('Bank account updated');
      } else {
        await billsAPI.createBankAccount(bankForm);
        toast.success('Bank account added');
      }
      setShowBankDialog(false);
      loadData();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    }
  };

  const deleteBank = async (id) => {
    if (!confirm('Delete this bank account? Existing bills that already reference it keep their frozen copy.')) return;
    try {
      await billsAPI.deleteBankAccount(id);
      toast.success('Deleted');
      loadData();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Delete failed');
    }
  };

  const recalcLine = (idx, patch) => {
    const items = [...newBill.line_items];
    const next = { ...items[idx], ...patch };
    next.line_amount = Number(((next.annual_ctc || 0) * (next.commercial_rate_pct || 0)) / 100).toFixed(2);
    items[idx] = next;
    setNewBill({ ...newBill, line_items: items });
  };

  const totals = useMemo(() => {
    const taxable = newBill.line_items.reduce((s, li) => s + Number(li.line_amount || 0), 0);
    const tax = +(taxable * 0.18).toFixed(2);
    return { taxable, tax, grand: +(taxable + tax).toFixed(2) };
  }, [newBill.line_items]);

  const createBill = async () => {
    if (!newBill.client_company_id) {
      toast.error('Pick a client company');
      return;
    }
    const items = newBill.line_items.filter((li) => li.candidate_name && li.annual_ctc > 0);
    if (!items.length) {
      toast.error('Add at least one candidate line');
      return;
    }
    try {
      const payload = { ...newBill, line_items: items };
      if (!payload.gst_kind) delete payload.gst_kind;
      if (!payload.due_date) delete payload.due_date;
      const res = await billsAPI.create(payload);
      toast.success(`Bill ${res.data.bill_number} created`);
      setShowCreate(false);
      setNewBill({
        client_company_id: '',
        sender_variant: 'VENTURE HRD CENTER',
        bill_date: new Date().toISOString().slice(0, 10),
        due_date: '',
        gst_kind: '',
        bank_account_id: '',
        line_items: [emptyLine()],
      });
      loadData();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Bill creation failed');
    }
  };

  const openSendDialog = async (bill) => {
    setShowSendDialog(bill);
    setSendForm({
      to_email: bill.client_billing_email || '',
      extra_cc: '',
      subject: `Invoice ${bill.bill_number} — ${bill.sender_legal_name}`,
      body: '',
      test_mode: false,
    });
    // Generate LLM body upfront
    setGenerating(true);
    try {
      const res = await billsAPI.previewMail(bill.id);
      setSendForm((f) => ({ ...f, body: res.data.plain || '' }));
    } catch (e) {
      toast.error('Mail body LLM call failed — you can write it manually');
    } finally {
      setGenerating(false);
    }
  };

  const regenerateBody = async () => {
    if (!showSendDialog) return;
    setGenerating(true);
    try {
      const res = await billsAPI.previewMail(showSendDialog.id);
      setSendForm((f) => ({ ...f, body: res.data.plain || '' }));
      toast.success('Mail body regenerated');
    } catch (e) {
      toast.error('LLM call failed');
    } finally {
      setGenerating(false);
    }
  };

  const sendBill = async () => {
    if (!showSendDialog) return;
    try {
      const extras = sendForm.extra_cc
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter((s) => /^[^@]+@[^@]+\.[^@]+$/.test(s));
      const res = await billsAPI.send(showSendDialog.id, {
        to_email: sendForm.to_email || undefined,
        extra_cc: extras,
        mail_subject: sendForm.subject,
        mail_body_plain: sendForm.body,
        test_mode: sendForm.test_mode,
      });
      toast.success(sendForm.test_mode ? `Test sent to ${res.data.to}` : `Sent to ${res.data.to}`);
      setShowSendDialog(null);
      loadData();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Send failed');
    }
  };

  const markPaid = async (bill) => {
    if (!confirm(`Mark ${bill.bill_number} as paid?`)) return;
    try {
      await billsAPI.markPaid(bill.id);
      toast.success(`${bill.bill_number} marked paid`);
      loadData();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed');
    }
  };

  const cancelBill = async (bill) => {
    if (!confirm(`Cancel ${bill.bill_number}? This cannot be undone.`)) return;
    try {
      await billsAPI.cancel(bill.id);
      toast.success('Cancelled');
      loadData();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl lg:text-3xl font-bold text-slate-900">Bills & Invoices</h1>
          <p className="text-slate-500 mt-1">Generate GST tax invoices, send to clients, track payment.</p>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => openEditBank(null)}
            variant="outline"
            data-testid="add-bank-btn"
          >
            <Landmark className="w-4 h-4 mr-2" /> Bank Accounts
          </Button>
          <Button onClick={() => setShowCreate(true)} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="new-bill-btn">
            <Plus className="w-4 h-4 mr-2" /> New Bill
          </Button>
        </div>
      </div>

      <Tabs value={mainTab} onValueChange={setMainTab}>
        <TabsList>
          <TabsTrigger value="invoices" data-testid="bills-tab-invoices">Invoices</TabsTrigger>
          <TabsTrigger value="worklist" data-testid="bills-tab-worklist">Invoices &amp; Payments</TabsTrigger>
        </TabsList>
      </Tabs>

      {mainTab === 'worklist' ? <InvoiceWorklist /> : (<>

      {/* Bank accounts strip — always visible so users know they exist */}
      {bankAccounts.length > 0 && (
        <Card data-testid="bank-accounts-strip">
          <CardContent className="p-3">
            <div className="flex items-center gap-2 flex-wrap text-sm">
              <span className="text-xs font-medium text-slate-500 flex items-center gap-1 mr-1">
                <Landmark className="w-3.5 h-3.5" /> Saved bank accounts:
              </span>
              {bankAccounts.map((b) => (
                <div
                  key={b.id}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200"
                  data-testid={`bank-chip-${b.id}`}
                >
                  <span>{b.label}{b.is_default && <span className="text-emerald-600 ml-1">•default</span>}</span>
                  <button onClick={() => openEditBank(b)} className="text-slate-400 hover:text-slate-700 ml-1" title="Edit">✎</button>
                  <button onClick={() => deleteBank(b.id)} className="text-slate-400 hover:text-red-600" title="Delete">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* List */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-slate-500">Loading…</div>
          ) : bills.length === 0 ? (
            <div className="p-8 text-center text-slate-500">No bills yet. Click <b>New Bill</b> to create one.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-700">
                <tr>
                  <th className="text-left p-3">Bill #</th>
                  <th className="text-left p-3">Date</th>
                  <th className="text-left p-3">Client</th>
                  <th className="text-right p-3">Amount</th>
                  <th className="text-left p-3">Status</th>
                  <th className="text-right p-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {bills.map((b) => (
                  <tr key={b.id} className="border-t" data-testid={`bill-row-${b.id}`}>
                    <td className="p-3 font-mono">{b.bill_number}</td>
                    <td className="p-3">{b.bill_date}</td>
                    <td className="p-3">{b.client_legal_name}</td>
                    <td className="p-3 text-right font-medium">{inr(b.totals?.grand_total)}</td>
                    <td className="p-3">
                      <Badge className={STATUS_COLORS[b.status] || 'bg-slate-100'}>{b.status}</Badge>
                    </td>
                    <td className="p-3">
                      <div className="flex gap-1 justify-end">
                        <Button size="sm" variant="ghost" title="Preview PDF" onClick={() => setPreviewBill(b)} data-testid={`preview-${b.id}`}>
                          <Eye className="w-4 h-4" />
                        </Button>
                        {b.status === 'draft' && (
                          <Button size="sm" variant="ghost" title="Send to client" onClick={() => openSendDialog(b)} data-testid={`send-${b.id}`}>
                            <Send className="w-4 h-4 text-blue-600" />
                          </Button>
                        )}
                        {b.status === 'sent' && (
                          <Button size="sm" variant="ghost" title="Mark as paid" onClick={() => markPaid(b)} data-testid={`mark-paid-${b.id}`}>
                            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                          </Button>
                        )}
                        {b.status !== 'cancelled' && b.status !== 'paid' && (
                          <Button size="sm" variant="ghost" title="Cancel" onClick={() => cancelBill(b)} data-testid={`cancel-${b.id}`}>
                            <XCircle className="w-4 h-4 text-red-600" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
      </>)}

      {/* ── New Bill Dialog ── */}
      <Dialog open={showCreate} onOpenChange={(o) => !o && setShowCreate(false)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Create New Bill</DialogTitle>
            <DialogDescription>Add candidates billed. GST is auto-calculated based on client GSTIN state.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Client Company</Label>
                <Select value={newBill.client_company_id} onValueChange={(v) => setNewBill({ ...newBill, client_company_id: v })}>
                  <SelectTrigger data-testid="bill-client-select"><SelectValue placeholder="Select…" /></SelectTrigger>
                  <SelectContent>
                    {companies.map((c) => (
                      <SelectItem key={c.id} value={c.id}>{c.legal_name || c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Sender Variant</Label>
                <Select value={newBill.sender_variant} onValueChange={(v) => setNewBill({ ...newBill, sender_variant: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="VENTURE HRD CENTER">Ventures HRD Centre (07AAMPY9883D2ZT)</SelectItem>
                    <SelectItem value="VENTURES HRD PVT LTD">Ventures HRD Centre Pvt. Ltd. (07AACCV6268J1ZW)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Bill Date</Label>
                <Input type="date" value={newBill.bill_date} onChange={(e) => setNewBill({ ...newBill, bill_date: e.target.value })} />
              </div>
              <div>
                <Label>Due Date (optional)</Label>
                <Input type="date" value={newBill.due_date} onChange={(e) => setNewBill({ ...newBill, due_date: e.target.value })} />
              </div>
              <div className="col-span-2">
                <Label>Bank Account (printed on the PDF)</Label>
                <Select
                  value={newBill.bank_account_id || '_default'}
                  onValueChange={(v) => setNewBill({ ...newBill, bank_account_id: v === '_default' ? '' : v })}
                >
                  <SelectTrigger data-testid="bill-bank-select">
                    <SelectValue placeholder="Default account" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_default">Use default account</SelectItem>
                    {bankAccounts.map((b) => (
                      <SelectItem key={b.id} value={b.id}>
                        {b.label} — {b.bank_name} ({b.account_number?.slice(-4).padStart(4, '•')})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {bankAccounts.length === 0 && (
                  <p className="text-xs text-amber-600 mt-1">
                    No saved bank accounts — the invoice PDF will omit the bank block. Add one via the “Bank Accounts” button.
                  </p>
                )}
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <Label>Line Items (each candidate billed)</Label>
                <Button size="sm" variant="outline" onClick={() => setNewBill({ ...newBill, line_items: [...newBill.line_items, emptyLine()] })}>
                  <Plus className="w-3 h-3 mr-1" /> Add row
                </Button>
              </div>
              <div className="border rounded overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left p-2">Candidate</th>
                      <th className="text-left p-2">Designation</th>
                      <th className="text-left p-2">DOJ</th>
                      <th className="text-right p-2">Annual CTC</th>
                      <th className="text-right p-2">Rate %</th>
                      <th className="text-right p-2">Amount</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {newBill.line_items.map((li, idx) => (
                      <tr key={idx} className="border-t">
                        <td className="p-1"><Input value={li.candidate_name} onChange={(e) => recalcLine(idx, { candidate_name: e.target.value })} placeholder="Name" /></td>
                        <td className="p-1"><Input value={li.designation} onChange={(e) => recalcLine(idx, { designation: e.target.value })} placeholder="Designation" /></td>
                        <td className="p-1"><Input type="date" value={li.joining_date} onChange={(e) => recalcLine(idx, { joining_date: e.target.value })} /></td>
                        <td className="p-1"><Input type="number" value={li.annual_ctc} onChange={(e) => recalcLine(idx, { annual_ctc: Number(e.target.value) })} className="text-right" /></td>
                        <td className="p-1"><Input type="number" step="0.01" value={li.commercial_rate_pct} onChange={(e) => recalcLine(idx, { commercial_rate_pct: Number(e.target.value) })} className="text-right" /></td>
                        <td className="p-1"><Input type="number" value={li.line_amount} onChange={(e) => recalcLine(idx, { line_amount: Number(e.target.value) })} className="text-right" /></td>
                        <td className="p-1">
                          {newBill.line_items.length > 1 && (
                            <Button size="sm" variant="ghost" onClick={() => setNewBill({ ...newBill, line_items: newBill.line_items.filter((_, i) => i !== idx) })}>
                              <Trash2 className="w-3 h-3 text-red-500" />
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex justify-end gap-6 mt-3 text-sm">
                <div><span className="text-slate-500">Taxable:</span> {inr(totals.taxable)}</div>
                <div><span className="text-slate-500">GST 18%:</span> {inr(totals.tax)}</div>
                <div className="font-bold">Grand Total: {inr(totals.grand)}</div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={createBill} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="create-bill-submit">
              <FileText className="w-4 h-4 mr-1" /> Save Draft
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Preview Dialog ── */}
      <Dialog open={!!previewBill} onOpenChange={(o) => !o && setPreviewBill(null)}>
        <DialogContent className="max-w-4xl h-[88vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{previewBill?.bill_number} — Preview</DialogTitle>
          </DialogHeader>
          {previewBill && previewBlobUrl ? (
            <iframe
              key={previewBill.id}
              src={previewBlobUrl}
              className="flex-1 w-full border rounded"
              title="Bill PDF"
              data-testid="bill-preview-iframe"
            />
          ) : previewBill ? (
            <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">Loading PDF…</div>
          ) : null}
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={downloadPreviewPdf}
              disabled={!previewBlobUrl}
              data-testid="bill-preview-download"
            >
              Download PDF
            </Button>
            <Button
              onClick={() => { const b = previewBill; setPreviewBill(null); setShowSendDialog(b); }}
              disabled={!previewBill}
              className="bg-[#7CB342] hover:bg-[#689F38]"
              data-testid="bill-preview-email"
            >
              Email to Client
            </Button>
            <Button variant="outline" onClick={() => setPreviewBill(null)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Send Dialog ── */}
      <Dialog open={!!showSendDialog} onOpenChange={(o) => !o && setShowSendDialog(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Send Bill {showSendDialog?.bill_number}</DialogTitle>
            <DialogDescription>
              CC: accounts@vhc.in + employer + bsy@ + rohit@ + any extras below.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Client email (To)</Label>
              <Input
                type="email"
                value={sendForm.to_email}
                onChange={(e) => setSendForm({ ...sendForm, to_email: e.target.value })}
                placeholder="finance@client.com"
                data-testid="send-to-email"
              />
              <p className="text-xs text-slate-400 mt-1">
                Overrides the company's saved billing email for this send only.
              </p>
            </div>
            <div>
              <Label>Subject</Label>
              <Input value={sendForm.subject} onChange={(e) => setSendForm({ ...sendForm, subject: e.target.value })} data-testid="send-subject" />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <Label>Mail Body (AI-generated, edit freely)</Label>
                <Button size="sm" variant="outline" onClick={regenerateBody} disabled={generating} data-testid="regenerate-body">
                  <Sparkles className="w-3 h-3 mr-1" /> {generating ? 'Generating…' : 'Regenerate'}
                </Button>
              </div>
              <Textarea
                value={sendForm.body}
                onChange={(e) => setSendForm({ ...sendForm, body: e.target.value })}
                className="min-h-[260px] font-mono text-xs"
                data-testid="send-body"
              />
            </div>
            <div>
              <Label>Extra CC (comma or space-separated)</Label>
              <Input value={sendForm.extra_cc} onChange={(e) => setSendForm({ ...sendForm, extra_cc: e.target.value })} placeholder="extra1@vhc.in, extra2@vhc.in" data-testid="send-extra-cc" />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={sendForm.test_mode} onChange={(e) => setSendForm({ ...sendForm, test_mode: e.target.checked })} data-testid="send-test-mode" />
              Test mode — send only to me (skip client + CC)
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSendDialog(null)}>Cancel</Button>
            <Button onClick={sendBill} className="bg-blue-600 hover:bg-blue-700" data-testid="send-bill-submit">
              <Send className="w-4 h-4 mr-1" /> {sendForm.test_mode ? 'Send Test' : 'Send Now'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Bank Account edit dialog ── */}
      <Dialog open={showBankDialog} onOpenChange={(o) => !o && setShowBankDialog(false)}>
        <DialogContent className="max-w-lg" data-testid="bank-dialog">
          <DialogHeader>
            <DialogTitle>{bankForm.id ? 'Edit bank account' : 'Add bank account'}</DialogTitle>
            <DialogDescription>
              Add every account you might invoice from. The chosen account is
              snapshotted onto each bill so later edits never rewrite past
              invoices.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>Label</Label>
              <Input
                value={bankForm.label}
                onChange={(e) => setBankForm({ ...bankForm, label: e.target.value })}
                placeholder="HDFC Current — Delhi"
                data-testid="bank-label"
              />
            </div>
            <div>
              <Label>Bank name</Label>
              <Input value={bankForm.bank_name} onChange={(e) => setBankForm({ ...bankForm, bank_name: e.target.value })} data-testid="bank-name" />
            </div>
            <div>
              <Label>Beneficiary name</Label>
              <Input value={bankForm.beneficiary_name} onChange={(e) => setBankForm({ ...bankForm, beneficiary_name: e.target.value })} data-testid="bank-beneficiary" />
            </div>
            <div>
              <Label>Branch</Label>
              <Input value={bankForm.branch} onChange={(e) => setBankForm({ ...bankForm, branch: e.target.value })} data-testid="bank-branch" />
            </div>
            <div>
              <Label>A/C number</Label>
              <Input value={bankForm.account_number} onChange={(e) => setBankForm({ ...bankForm, account_number: e.target.value })} data-testid="bank-account-number" />
            </div>
            <div>
              <Label>IFSC</Label>
              <Input value={bankForm.ifsc} onChange={(e) => setBankForm({ ...bankForm, ifsc: e.target.value.toUpperCase() })} data-testid="bank-ifsc" />
            </div>
            <label className="col-span-2 flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={!!bankForm.is_default}
                onChange={(e) => setBankForm({ ...bankForm, is_default: e.target.checked })}
                data-testid="bank-is-default"
              />
              Make this the default account (picked automatically when no account is chosen on a bill)
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBankDialog(false)}>Cancel</Button>
            <Button onClick={saveBank} className="bg-[#7CB342] hover:bg-[#689F38]" data-testid="bank-save">
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
