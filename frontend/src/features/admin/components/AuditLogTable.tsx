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
  DialogDescription,
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
  nextCursor: string | null;
  onPageChange: (page: number) => void;
}

export function AuditLogTable({
  logs,
  isLoading,
  page,
  nextCursor,
  onPageChange,
}: AuditLogTableProps) {
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);
  const hasNextPage = Boolean(nextCursor);

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

  return (
    <>
      <Card className="flex flex-col h-full soft-hover overflow-hidden border-border">
        <div className="flex-1 overflow-auto">
          <div className="hidden md:block">
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
                      <TableCell className="py-2">
                        <div className="flex items-center justify-end gap-2">
                          {log.details &&
                          Object.keys(log.details).length > 0 ? (
                            <span className="text-xs text-muted-foreground font-mono">
                              {Object.keys(log.details).length}{" "}
                              {Object.keys(log.details).length === 1
                                ? "field"
                                : "fields"}
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              —
                            </span>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => setSelectedLog(log)}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <div className="md:hidden">
            {logs.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                No audit logs found.
              </div>
            ) : (
              <div className="divide-y divide-border/40">
                {logs.map((log) => {
                  const detailsCount = log.details
                    ? Object.keys(log.details).length
                    : 0;
                  return (
                    <div key={log.id} className="p-3 space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 space-y-1">
                          <p className="text-xs text-muted-foreground">
                            {format(
                              new Date(log.timestamp),
                              "MMM dd, HH:mm:ss",
                            )}
                          </p>
                          <p className="text-sm font-mono break-all">
                            {log.action}
                          </p>
                        </div>
                        {getSeverityBadge(log.severity)}
                      </div>
                      <div className="flex items-start justify-between gap-3 text-xs text-muted-foreground">
                        <div className="min-w-0">
                          <p className="truncate">
                            {log.actor_email || "System"}
                          </p>
                          {log.impersonator_id && (
                            <span className="text-[10px] text-yellow-500">
                              Impersonated
                            </span>
                          )}
                        </div>
                        <span className="font-mono">
                          {log.ip_address || "—"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        {detailsCount > 0 ? (
                          <span className="text-xs text-muted-foreground font-mono">
                            {detailsCount}{" "}
                            {detailsCount === 1 ? "field" : "fields"}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            —
                          </span>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => setSelectedLog(log)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Show More Button */}
        {hasNextPage && (
          <div className="flex items-center justify-center px-4 py-4 border-t border-border/40">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(page + 1)}
              disabled={isLoading}
            >
              {isLoading ? "Loading..." : "Show More"}
            </Button>
          </div>
        )}

        {/* Show Less Button (if not on first page) */}
        {page > 1 && (
          <div className="flex items-center justify-center px-4 py-2 border-t border-border/40">
            <Button variant="ghost" size="sm" onClick={() => onPageChange(1)}>
              Show Less (Back to Top)
            </Button>
          </div>
        )}
      </Card>

      {/* Detail Dialog */}
      <Dialog
        open={!!selectedLog}
        onOpenChange={(open) => !open && setSelectedLog(null)}
      >
        <DialogContent className="w-[calc(100%-2rem)] sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Info className="h-5 w-5 text-primary" />
              <span>Event Details</span>
            </DialogTitle>
            <DialogDescription className="sr-only">
              Audit log event metadata and raw details.
            </DialogDescription>
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
