import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useJobLogs } from "../hooks/useJobLogs";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Loader2 } from "lucide-react";

interface LogViewerProps {
  jobId: string | null;
  className?: string;
}

export function LogViewer({ jobId, className }: LogViewerProps) {
  const { logs, status } = useJobLogs(jobId);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    const viewport = scrollAreaRef.current?.querySelector(
      "[data-radix-scroll-area-viewport]",
    ) as HTMLElement | null;
    if (viewport) {
      viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
    }
  }, [logs]);

  if (!jobId) {
    return (
      <div
        className={cn(
          "flex h-full items-center justify-center text-muted-foreground",
          className,
        )}
      >
        Select a job to view logs
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col rounded-lg overflow-hidden font-mono text-[11px] sm:text-sm",
        "bg-slate-50 text-slate-900 border border-border/60",
        "dark:bg-black dark:text-white dark:border-gray-800",
        className,
      )}
    >
      {/* Header / Status Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-slate-100 to-slate-50 border-b border-border/40 dark:from-gray-900 dark:to-gray-900 dark:border-gray-800">
        <span className="text-xs font-semibold text-slate-600 dark:text-gray-400 uppercase tracking-wide">
          Logs •{" "}
          <span className="font-mono text-primary">{jobId.slice(0, 8)}</span>
        </span>
        <div className="flex items-center gap-2">
          {status === "CONNECTED" || status === "RUNNING" ? (
            <Badge
              variant="outline"
              className="text-xs text-emerald-600 border-emerald-200 bg-emerald-50 shadow-sm dark:text-green-400 dark:border-green-900 dark:bg-green-900/20"
            >
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              Live
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="text-xs text-slate-500 border-slate-200 bg-slate-50 shadow-sm dark:text-gray-400 dark:border-gray-700 dark:bg-gray-800"
            >
              {status}
            </Badge>
          )}
        </div>
      </div>

      {/* Log Content */}
      <ScrollArea ref={scrollAreaRef} className="flex-1 p-4">
        <div className="space-y-1">
          {logs.length === 0 && (
            <div className="text-slate-400 dark:text-gray-500 italic">
              Waiting for logs...
            </div>
          )}
          {logs.map((log, index) => (
            <div key={index} className="break-all whitespace-pre-wrap">
              <span className="text-slate-400 dark:text-gray-500 mr-2 select-none">
                {log.payload.ts
                  ? new Date(log.payload.ts).toLocaleTimeString()
                  : ""}
              </span>
              <span
                className={cn(
                  log.type === "error"
                    ? "text-red-600 dark:text-red-400"
                    : log.type === "info"
                      ? "text-blue-600 dark:text-blue-400"
                      : log.type === "status"
                        ? "text-amber-600 dark:text-yellow-400"
                        : "text-slate-700 dark:text-gray-300",
                )}
              >
                {log.payload.message || JSON.stringify(log.payload)}
              </span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
