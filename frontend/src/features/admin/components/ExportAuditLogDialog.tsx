import { useState } from "react";
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
import { AuditLogFilters, exportAuditLogs } from "../api/audit";

interface ExportAuditLogDialogProps {
  filters: AuditLogFilters;
}

export function ExportAuditLogDialog({ filters }: ExportAuditLogDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const response = await exportAuditLogs(filters);
      setJobId(response.job_id);
      toast.success("Export job started successfully!");
    } catch (error) {
      toast.error("Failed to start export job. Please try again.");
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
            Large reports may take a few minutes to process.
          </DialogDescription>
        </DialogHeader>

        <div className="py-6 flex flex-col items-center justify-center space-y-4">
          {!jobId ? (
            <div className="p-4 rounded-full bg-primary/10">
              <FileJson className="h-10 w-10 text-primary" />
            </div>
          ) : (
            <div className="p-4 rounded-full bg-emerald-500/10">
              <CheckCircle2 className="h-10 w-10 text-emerald-500" />
            </div>
          )}

          {jobId && (
            <div className="text-center space-y-1">
              <p className="text-sm font-medium">
                Job ID:{" "}
                <span className="font-mono text-muted-foreground">{jobId}</span>
              </p>
              <p className="text-xs text-muted-foreground">
                You will receive a notification when your download is ready.
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            {jobId ? "Close" : "Cancel"}
          </Button>
          {!jobId && (
            <Button onClick={handleExport} disabled={isExporting}>
              {isExporting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing...
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
