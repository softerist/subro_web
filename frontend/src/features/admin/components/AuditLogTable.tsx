import { format } from "date-fns";
import { Loader2, Eye, Info } from "lucide-react";
import { useState } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AuditLog } from "../api/audit";

interface AuditLogTableProps {
  logs: AuditLog[];
  isLoading: boolean;
  total: number;
  page: number;
  perPage: number;
  onPageChange: (page: number) => void;
}

export function AuditLogTable({
  logs,
  isLoading,
  total,
  page,
  perPage,
  onPageChange,
}: AuditLogTableProps) {
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const getSeverityBadge = (severity: string) => {
    switch (severity.toLowerCase()) {
      case "critical":
        return (
          <Badge className="bg-red-600/20 text-red-500 border-red-600/20 hover:bg-red-600/30">
            Critical
          </Badge>
        );
      case "error":
        return (
          <Badge className="bg-orange-600/20 text-orange-500 border-orange-600/20 hover:bg-orange-600/30">
            Error
          </Badge>
        );
      case "warning":
        return (
          <Badge className="bg-yellow-500/20 text-yellow-500 border-yellow-500/20 hover:bg-yellow-500/30">
            Warning
          </Badge>
        );
      case "info":
      default:
        return (
          <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/20 hover:bg-blue-500/30">
            Info
          </Badge>
        );
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const totalPages = Math.ceil(total / perPage);

  return (
    <>
      <Card className="soft-hover overflow-hidden border-border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent border-b border-border/40">
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground">
                Timestamp
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground">
                Severity
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground">
                Action
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground">
                Actor
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground hidden md:table-cell">
                IP Address
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground text-right">
                Details
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center">
                  No audit logs found.
                </TableCell>
              </TableRow>
            ) : (
              logs.map((log) => (
                <TableRow key={log.id} className="group">
                  <TableCell className="py-2 text-xs text-muted-foreground">
                    {format(new Date(log.timestamp), "MMM dd, HH:mm:ss")}
                  </TableCell>
                  <TableCell className="py-2">
                    {getSeverityBadge(log.severity)}
                  </TableCell>
                  <TableCell className="py-2 font-mono text-xs">
                    {log.action}
                  </TableCell>
                  <TableCell className="py-2 text-sm">
                    <div className="flex flex-col">
                      <span>{log.actor_email || "System"}</span>
                      {log.impersonator_id && (
                        <span className="text-[10px] text-yellow-500">
                          Impersonated
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="py-2 text-xs text-muted-foreground hidden md:table-cell font-mono">
                    {log.ip_address}
                  </TableCell>
                  <TableCell className="py-2 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={() => setSelectedLog(log)}
                    >
                      <Eye className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border/40">
            <div className="text-xs text-muted-foreground">
              Showing {(page - 1) * perPage + 1} to{" "}
              {Math.min(page * perPage, total)} of {total} results
            </div>
            <div className="flex space-x-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onPageChange(page - 1)}
                disabled={page === 1}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onPageChange(page + 1)}
                disabled={page === totalPages}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Detail Dialog */}
      <Dialog
        open={!!selectedLog}
        onOpenChange={(open) => !open && setSelectedLog(null)}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Info className="h-5 w-5 text-primary" />
              <span>Event Details</span>
            </DialogTitle>
          </DialogHeader>
          {selectedLog && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="space-y-1">
                  <p className="text-muted-foreground font-semibold">
                    Event ID
                  </p>
                  <p className="font-mono text-xs">{selectedLog.event_id}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-muted-foreground font-semibold">Outcome</p>
                  <Badge
                    variant={selectedLog.success ? "default" : "destructive"}
                  >
                    {selectedLog.outcome}
                  </Badge>
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-muted-foreground font-semibold text-sm">
                  Raw Details
                </p>
                <div className="bg-slate-950 rounded-md p-4 overflow-auto max-h-[300px]">
                  <pre className="text-xs text-blue-300 font-mono">
                    {JSON.stringify(selectedLog.details, null, 2)}
                  </pre>
                </div>
              </div>

              {selectedLog.reason_code && (
                <div className="p-3 bg-muted rounded border border-border">
                  <p className="text-xs font-semibold text-muted-foreground mb-1 uppercase tracking-tight">
                    Reason Code
                  </p>
                  <p className="text-sm font-medium">
                    {selectedLog.reason_code}
                  </p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
