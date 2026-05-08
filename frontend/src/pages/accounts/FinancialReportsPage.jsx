import { useState, useCallback } from 'react';
import { financeAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import { Download, IndianRupee, Loader2, FileText, AlertCircle, TrendingUp, TrendingDown } from 'lucide-react';

const fmt = (n) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n || 0);

const downloadAsCSV = (rows, filename) => {
  if (!rows?.length) return toast.info('No data to export');
  const headers = Object.keys(rows[0]);
  const csv = [headers.join(','), ...rows.map(r => headers.map(h => `"${r[h] ?? ''}"`).join(','))].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = filename; a.click();
};

export default function FinancialReportsPage() {
  return (
    <div className="space-y-6 p-4 sm:p-6" data-testid="financial-reports-page">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Financial Reports</h1>
        <p className="text-sm text-slate-500">P&L, Aging Report, and GST Summary — all downloadable</p>
      </div>

      <Tabs defaultValue="pnl">
        <TabsList className="grid w-full grid-cols-3 max-w-md">
          <TabsTrigger value="pnl" data-testid="tab-pnl">P&L Statement</TabsTrigger>
          <TabsTrigger value="aging" data-testid="tab-aging">Aging Report</TabsTrigger>
          <TabsTrigger value="gst" data-testid="tab-gst">GST Summary</TabsTrigger>
        </TabsList>

        <TabsContent value="pnl"><PnLReport /></TabsContent>
        <TabsContent value="aging"><AgingReport /></TabsContent>
        <TabsContent value="gst"><GSTReport /></TabsContent>
      </Tabs>
    </div>
  );
}

function PnLReport() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [startDate, setStartDate] = useState(new Date().getFullYear() + '-01-01');
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await financeAPI.reportPnL({ start_date: startDate, end_date: endDate });
      setData(res.data);
    } catch { toast.error('Failed to load P&L'); }
    finally { setLoading(false); }
  }, [startDate, endDate]);

  const downloadPnL = () => {
    if (!data) return;
    const rows = [
      ...data.revenue_by_month.map(m => ({ Type: 'Revenue', Period: m.month, Category: 'Collections', Amount: m.amount })),
      ...data.expenses_by_category.map(e => ({ Type: 'Expense', Period: data.period.start + ' to ' + data.period.end, Category: e.category, Amount: -e.amount })),
      { Type: 'NET', Period: '', Category: 'Net Profit', Amount: data.net_profit },
    ];
    downloadAsCSV(rows, `pnl_${startDate}_${endDate}.csv`);
  };

  return (
    <div className="space-y-4 mt-4">
      <div className="flex flex-wrap items-end gap-3">
        <div><Label className="text-xs">From</Label><Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="h-9 w-40" /></div>
        <div><Label className="text-xs">To</Label><Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="h-9 w-40" /></div>
        <Button onClick={load} disabled={loading} className="h-9 bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="load-pnl-btn">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Generate'}
        </Button>
        {data && <Button variant="outline" size="sm" onClick={downloadPnL} data-testid="download-pnl-btn"><Download className="w-4 h-4 mr-1" />Download CSV</Button>}
      </div>

      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="border-green-200">
            <CardContent className="p-4 text-center">
              <TrendingUp className="w-6 h-6 text-green-600 mx-auto" />
              <p className="text-xs text-slate-500 mt-2">Total Revenue</p>
              <p className="text-2xl font-bold text-green-700">{fmt(data.total_revenue)}</p>
            </CardContent>
          </Card>
          <Card className="border-red-200">
            <CardContent className="p-4 text-center">
              <TrendingDown className="w-6 h-6 text-red-600 mx-auto" />
              <p className="text-xs text-slate-500 mt-2">Total Expenses</p>
              <p className="text-2xl font-bold text-red-700">{fmt(data.total_expenses)}</p>
            </CardContent>
          </Card>
          <Card className={`border-${data.net_profit >= 0 ? 'blue' : 'red'}-200`}>
            <CardContent className="p-4 text-center">
              <IndianRupee className="w-6 h-6 text-blue-600 mx-auto" />
              <p className="text-xs text-slate-500 mt-2">Net Profit</p>
              <p className={`text-2xl font-bold ${data.net_profit >= 0 ? 'text-blue-700' : 'text-red-700'}`}>{fmt(data.net_profit)}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Revenue by Month */}
          <Card className="border-slate-200">
            <CardHeader className="pb-2"><CardTitle className="text-sm">Revenue by Month</CardTitle></CardHeader>
            <CardContent>
              {data.revenue_by_month.length > 0 ? (
                <div className="space-y-2">
                  {data.revenue_by_month.map(m => (
                    <div key={m.month} className="flex justify-between items-center py-1 border-b border-slate-100">
                      <span className="text-sm text-slate-600">{m.month}</span>
                      <span className="text-sm font-medium text-green-700">{fmt(m.amount)}</span>
                    </div>
                  ))}
                </div>
              ) : <p className="text-sm text-slate-400 text-center py-4">No revenue data</p>}
            </CardContent>
          </Card>

          {/* Expenses by Category */}
          <Card className="border-slate-200">
            <CardHeader className="pb-2"><CardTitle className="text-sm">Expenses by Category</CardTitle></CardHeader>
            <CardContent>
              {data.expenses_by_category.length > 0 ? (
                <div className="space-y-2">
                  {data.expenses_by_category.map(e => {
                    const pct = data.total_expenses > 0 ? (e.amount / data.total_expenses) * 100 : 0;
                    return (
                      <div key={e.category}>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-slate-600">{e.category}</span>
                          <span className="font-medium text-red-600">{fmt(e.amount)} ({pct.toFixed(0)}%)</span>
                        </div>
                        <div className="h-1.5 bg-slate-100 rounded-full"><div className="h-full bg-red-400 rounded-full" style={{ width: `${pct}%` }} /></div>
                      </div>
                    );
                  })}
                </div>
              ) : <p className="text-sm text-slate-400 text-center py-4">No expense data</p>}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function AgingReport() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await financeAPI.reportAging(); setData(res.data); }
    catch { toast.error('Failed'); }
    finally { setLoading(false); }
  }, []);

  const downloadAging = () => {
    if (!data) return;
    const rows = [];
    Object.entries(data.buckets).forEach(([bucket, invoices]) => {
      invoices.forEach(inv => rows.push({ Bucket: bucket, Invoice: inv.invoice_number, Client: inv.client_name, Amount: inv.total, 'Days Overdue': inv.days_overdue }));
    });
    downloadAsCSV(rows, 'aging_report.csv');
  };

  return (
    <div className="space-y-4 mt-4">
      <div className="flex gap-3">
        <Button onClick={load} disabled={loading} className="bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="load-aging-btn">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Generate'}
        </Button>
        {data && <Button variant="outline" onClick={downloadAging} data-testid="download-aging-btn"><Download className="w-4 h-4 mr-1" />Download</Button>}
      </div>

      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Current', key: 'current', color: 'green' },
              { label: '1-30 Days', key: '30_days', color: 'amber' },
              { label: '31-60 Days', key: '60_days', color: 'orange' },
              { label: '90+ Days', key: '90_plus', color: 'red' },
            ].map(b => (
              <Card key={b.key} className={`border-${b.color}-200`}>
                <CardContent className="p-3 text-center">
                  <p className="text-xs text-slate-500">{b.label}</p>
                  <p className={`text-lg font-bold text-${b.color}-700`}>{fmt(data.totals[b.key])}</p>
                  <p className="text-xs text-slate-400">{data.buckets[b.key]?.length || 0} invoices</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card className="border-slate-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-500" />Grand Total Outstanding: {fmt(data.grand_total)}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead><tr className="border-b bg-slate-50"><th className="p-2 text-left">Invoice</th><th className="p-2 text-left">Client</th><th className="p-2 text-right">Amount</th><th className="p-2 text-right">Days Overdue</th></tr></thead>
                <tbody>
                  {Object.entries(data.buckets).flatMap(([, invoices]) => invoices).sort((a, b) => b.days_overdue - a.days_overdue).slice(0, 20).map(inv => (
                    <tr key={inv.id} className="border-b hover:bg-slate-50">
                      <td className="p-2 font-medium">{inv.invoice_number}</td>
                      <td className="p-2 text-slate-600">{inv.client_name}</td>
                      <td className="p-2 text-right">{fmt(inv.total)}</td>
                      <td className="p-2 text-right"><Badge className={`text-xs ${inv.days_overdue > 60 ? 'bg-red-50 text-red-700' : inv.days_overdue > 30 ? 'bg-amber-50 text-amber-700' : 'bg-green-50 text-green-700'}`}>{inv.days_overdue}d</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function GSTReport() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [startDate, setStartDate] = useState(new Date().getFullYear() + '-01-01');
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10));

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await financeAPI.reportGST({ start_date: startDate, end_date: endDate }); setData(res.data); }
    catch { toast.error('Failed'); }
    finally { setLoading(false); }
  }, [startDate, endDate]);

  const downloadGST = () => {
    if (!data) return;
    const rows = data.invoices.map(inv => ({
      Invoice: inv.invoice_number, Client: inv.client_name, 'Taxable Value': inv.subtotal,
      'GST %': inv.gst_percent, 'GST Amount': inv.gst_amount, Total: inv.subtotal + inv.gst_amount, Status: inv.status, Date: inv.created_at?.slice(0, 10),
    }));
    rows.push({ Invoice: 'TOTAL', Client: '', 'Taxable Value': data.total_taxable_value, 'GST %': '', 'GST Amount': data.total_gst_collected, Total: data.total_with_gst, Status: '', Date: '' });
    downloadAsCSV(rows, `gst_summary_${startDate}_${endDate}.csv`);
  };

  return (
    <div className="space-y-4 mt-4">
      <div className="flex flex-wrap items-end gap-3">
        <div><Label className="text-xs">From</Label><Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="h-9 w-40" /></div>
        <div><Label className="text-xs">To</Label><Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="h-9 w-40" /></div>
        <Button onClick={load} disabled={loading} className="h-9 bg-[#2563eb] hover:bg-[#1d4ed8]" data-testid="load-gst-btn">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Generate'}
        </Button>
        {data && <Button variant="outline" size="sm" onClick={downloadGST} data-testid="download-gst-btn"><Download className="w-4 h-4 mr-1" />Download</Button>}
      </div>

      {data && (
        <>
          <div className="grid grid-cols-3 gap-4">
            <Card className="border-slate-200"><CardContent className="p-4 text-center">
              <p className="text-xs text-slate-500">Taxable Value</p>
              <p className="text-xl font-bold text-slate-700 mt-1">{fmt(data.total_taxable_value)}</p>
            </CardContent></Card>
            <Card className="border-blue-200"><CardContent className="p-4 text-center">
              <p className="text-xs text-blue-600">GST Collected</p>
              <p className="text-xl font-bold text-blue-700 mt-1">{fmt(data.total_gst_collected)}</p>
            </CardContent></Card>
            <Card className="border-green-200"><CardContent className="p-4 text-center">
              <p className="text-xs text-green-600">Total with GST</p>
              <p className="text-xl font-bold text-green-700 mt-1">{fmt(data.total_with_gst)}</p>
            </CardContent></Card>
          </div>

          <Card className="border-slate-200">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b bg-slate-50">
                  <th className="p-2 text-left">Invoice</th><th className="p-2 text-left">Client</th>
                  <th className="p-2 text-right">Taxable</th><th className="p-2 text-right">GST%</th>
                  <th className="p-2 text-right">GST Amt</th><th className="p-2 text-left">Status</th>
                </tr></thead>
                <tbody>
                  {data.invoices.map((inv, i) => (
                    <tr key={inv.id || `inv-${i}`} className="border-b hover:bg-slate-50">
                      <td className="p-2 font-medium">{inv.invoice_number}</td>
                      <td className="p-2 text-slate-600">{inv.client_name}</td>
                      <td className="p-2 text-right">{fmt(inv.subtotal)}</td>
                      <td className="p-2 text-right">{inv.gst_percent}%</td>
                      <td className="p-2 text-right">{fmt(inv.gst_amount)}</td>
                      <td className="p-2"><Badge className="text-xs">{inv.status}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
