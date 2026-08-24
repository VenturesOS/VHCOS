import { useState } from "react";
import { Download, BookOpen, Loader2, CheckCircle2 } from "lucide-react";
import { Button } from "../../components/ui/button";
import { toast } from "sonner";

export default function AdminResourcesPage() {
  const [downloading, setDownloading] = useState(false);

  const handleDownloadManual = async () => {
    setDownloading(true);
    try {
      const token = localStorage.getItem("vhc_token");
      const res = await fetch(`/api/system-health/training-manual/download`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Download failed");
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "VHC_Training_Manual.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Training manual downloaded");
    } catch (e) {
      toast.error(e.message || "Failed to download manual");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="space-y-8" data-testid="admin-resources-page">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900" data-testid="resources-page-title">
          Resources &amp; Documentation
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Download training materials, guides, and reference documents for your team.
        </p>
      </div>

      {/* Resources Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* Training Manual Card */}
        <div
          className="bg-white border border-slate-200 rounded-xl p-6 flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow"
          data-testid="training-manual-card"
        >
          <div>
            <div className="w-12 h-12 rounded-lg bg-emerald-50 flex items-center justify-center mb-4">
              <BookOpen className="w-6 h-6 text-emerald-600" />
            </div>
            <h3 className="text-base font-semibold text-slate-900">Portal Training Manual</h3>
            <p className="text-sm text-slate-500 mt-1 leading-relaxed">
              Comprehensive guide for Employer and Recruiter roles covering all portal features, pipeline management, and best practices.
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              <span className="inline-flex items-center text-xs font-medium bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full">
                <CheckCircle2 className="w-3 h-3 mr-1" /> Employer Guide
              </span>
              <span className="inline-flex items-center text-xs font-medium bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">
                <CheckCircle2 className="w-3 h-3 mr-1" /> Recruiter Guide
              </span>
              <span className="inline-flex items-center text-xs font-medium bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full">
                <CheckCircle2 className="w-3 h-3 mr-1" /> Trainer&apos;s Guide
              </span>
            </div>
          </div>
          <Button
            className="mt-5 w-full bg-emerald-600 hover:bg-emerald-700 text-white"
            onClick={handleDownloadManual}
            disabled={downloading}
            data-testid="download-training-manual-btn"
          >
            {downloading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Generating PDF…
              </>
            ) : (
              <>
                <Download className="w-4 h-4 mr-2" />
                Download PDF
              </>
            )}
          </Button>
        </div>

        {/* Placeholder cards removed — add real resources here as they're built */}
      </div>
    </div>
  );
}
