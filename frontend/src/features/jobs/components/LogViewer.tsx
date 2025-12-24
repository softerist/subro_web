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
          "flex h-full items-center justify-center text-muted-foreground border rounded-md bg-muted/10",
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
        "flex flex-col border rounded-md overflow-hidden bg-black text-white font-mono text-sm shadow-sm",
        className,
      )}
    >
      {/* Header / Status Bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-800">
        <span className="font-semibold text-gray-300">
          Logs: {jobId.slice(0, 8)}...
        </span>
        <div className="flex items-center gap-2">
          {status === "CONNECTED" || status === "RUNNING" ? (
            <Badge
              variant="outline"
              className="text-green-400 border-green-900 bg-green-900/20"
            >
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              Live
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="text-gray-400 border-gray-700 bg-gray-800"
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
            <div className="text-gray-500 italic">Waiting for logs...</div>
          )}
          {logs.map((log, index) => (
            <div key={index} className="break-all whitespace-pre-wrap">
              <span className="text-gray-500 mr-2 select-none">
                {log.payload.ts
                  ? new Date(log.payload.ts).toLocaleTimeString()
                  : ""}
              </span>
              <span
                className={cn(
                  log.type === "error"
                    ? "text-red-400"
                    : log.type === "info"
                      ? "text-blue-400"
                      : log.type === "status"
                        ? "text-yellow-400"
                        : "text-gray-300",
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
