import { useState, useEffect } from "react";
import { Download, Loader2, FileJson, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/apiClient";
import { exportAuditLogs, type AuditLogFilters } from "../api/audit";

interface ExportAuditLogDialogProps {
  filters: AuditLogFilters;
}

export function ExportAuditLogDialog({ filters }: ExportAuditLogDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  // Poll for job completion
  useEffect(() => {
    if (!jobId || !isPolling) return;

    const pollInterval = setInterval(async () => {
      try {
        const response = await api.get(
          `/v1/admin/audit/export/status/${jobId}`,
        );
        const status = response.data.status;

        if (status === "COMPLETED") {
          clearInterval(pollInterval);
          setIsPolling(false);

          // Trigger download
          const filename = response.data.result?.filename;
          if (filename) {
            window.location.href = `/api/v1/admin/audit/export/download/${filename}`;
            toast.success("Download started!");
            setTimeout(() => setIsOpen(false), 1500);
          }
        } else if (status === "FAILED") {
          clearInterval(pollInterval);
          setIsPolling(false);
          toast.error("Export failed. Please try again.");
        }
      } catch (error) {
        console.error("Polling error:", error);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(pollInterval);
  }, [jobId, isPolling]);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const response = await exportAuditLogs(filters);
      setJobId(response.job_id);
      setIsPolling(true);
      toast.success("Export started! Preparing download...");
    } catch (error) {
      toast.error("Failed to start export. Please try again.");
      console.error(error);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Download className="mr-2 h-4 w-4" />
          Export Logs
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Export Audit Logs</DialogTitle>
          <DialogDescription>
            This will generate a JSON audit trail based on your current filters.
          </DialogDescription>
        </DialogHeader>

        <div className="py-6 flex flex-col items-center justify-center space-y-4">
          {!jobId ? (
            <div className="p-4 rounded-full bg-primary/10">
              <FileJson className="h-10 w-10 text-primary" />
            </div>
          ) : isPolling ? (
            <>
              <Loader2 className="h-10 w-10 animate-spin text-primary" />
              <div className="text-center space-y-2">
                <p className="text-sm font-medium">Preparing export...</p>
                <p className="text-xs text-muted-foreground">
                  Your download will start automatically
                </p>
              </div>
            </>
          ) : (
            <>
              <div className="p-4 rounded-full bg-emerald-500/10">
                <CheckCircle2 className="h-10 w-10 text-emerald-500" />
              </div>
              <div className="text-center space-y-2">
                <p className="text-sm font-medium">Download complete!</p>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            {jobId && !isPolling ? "Close" : "Cancel"}
          </Button>
          {!jobId && (
            <Button onClick={handleExport} disabled={isExporting}>
              {isExporting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Starting...
                </>
              ) : (
                "Start Export"
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
