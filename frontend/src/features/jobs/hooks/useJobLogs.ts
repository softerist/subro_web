import { useEffect, useRef, useState, useCallback } from "react";
import { useAuthStore } from "@/store/authStore";
import { LogMessage, Job } from "../types";
import { jobsApi } from "../api/jobs";

// Cache logs per job to preserve context when switching
const logsCache = new Map<string, LogMessage[]>();
const statusCache = new Map<string, string>();

// Terminal statuses that indicate a job is complete
const TERMINAL_STATUSES = ["SUCCEEDED", "FAILED", "CANCELLED", "COMPLETED"];

export function useJobLogs(jobId: string | null) {
  const [logs, setLogs] = useState<LogMessage[]>([]);
  const [status, setStatus] = useState<string>("IDLE");
  const wsRef = useRef<WebSocket | null>(null);
  const token = useAuthStore((state) => state.accessToken);
  // Track which job the current logs belong to
  const activeJobIdRef = useRef<string | null>(null);
  // Track logs synchronously to avoid state update race conditions
  const currentLogsRef = useRef<LogMessage[]>([]);
  // Track if we've already fetched historical logs
  const fetchedHistoricalRef = useRef<string | null>(null);

  // Fetch job details to get log_snippet for historical logs
  const fetchHistoricalLogs = useCallback(
    async (
      jobIdToFetch: string,
    ): Promise<{
      logs: LogMessage[];
      status: string;
      isComplete: boolean;
    } | null> => {
      try {
        const job: Job = await jobsApi.getOne(jobIdToFetch);
        const isComplete = TERMINAL_STATUSES.includes(job.status);

        // Only return logs for completed jobs
        if (!isComplete) {
          return { logs: [], status: job.status, isComplete: false };
        }

        // Create synthetic log messages from the stored data
        const historicalLogs: LogMessage[] = [];

        if (job.log_snippet) {
          // Split log_snippet into individual lines and create log messages
          const lines = job.log_snippet
            .split("\n")
            .filter((line) => line.trim());
          lines.forEach((line) => {
            historicalLogs.push({
              type: "log",
              payload: {
                message: line,
                ts: job.completed_at || job.started_at || job.submitted_at,
              },
            });
          });
        }

        // Add result message if available
        if (job.result_message) {
          historicalLogs.push({
            type: job.status === "FAILED" ? "error" : "info",
            payload: {
              message: job.result_message,
              ts: job.completed_at || undefined,
            },
          });
        }

        // Add final status
        historicalLogs.push({
          type: "status",
          payload: {
            status: job.status,
            exit_code: job.exit_code ?? undefined,
            ts: job.completed_at || undefined,
          },
        });

        return { logs: historicalLogs, status: job.status, isComplete };
      } catch (err) {
        console.error("Failed to fetch historical logs:", err);
        return null;
      }
    },
    [],
  );

  useEffect(() => {
    // Clean up previous WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Save logs of the previous job before switching
    if (
      activeJobIdRef.current &&
      activeJobIdRef.current !== jobId &&
      currentLogsRef.current.length > 0
    ) {
      logsCache.set(activeJobIdRef.current, [...currentLogsRef.current]);
      statusCache.set(activeJobIdRef.current, status);
    }

    // Reset state for new job
    activeJobIdRef.current = jobId;
    currentLogsRef.current = []; // Synchronously reset logs
    setLogs([]); // Schedule UI update

    if (!jobId || !token) {
      setStatus("IDLE");
      return;
    }

    // Check cache first - restore logs if we have them
    const cachedLogs = logsCache.get(jobId);
    const cachedStatus = statusCache.get(jobId);

    if (cachedLogs && cachedLogs.length > 0) {
      currentLogsRef.current = [...cachedLogs]; // Restore Sync Ref
      setLogs([...cachedLogs]); // Restore UI
      setStatus(cachedStatus || "COMPLETED");

      // If job is completed, don't reconnect WebSocket - just show cached logs
      if (TERMINAL_STATUSES.includes(cachedStatus || "")) {
        return;
      }

      // Job not complete but we have cached logs - connect WebSocket to continue streaming
      connectWebSocket(jobId);
      return;
    }

    // No cache - start fresh
    setStatus("CONNECTING");

    // First, check if job is already completed before connecting WebSocket
    if (fetchedHistoricalRef.current !== jobId) {
      fetchHistoricalLogs(jobId).then((result) => {
        // Only update if still the active job
        if (activeJobIdRef.current !== jobId) return;

        fetchedHistoricalRef.current = jobId;

        if (result && result.isComplete && result.logs.length > 0) {
          // Job is complete, show historical logs
          currentLogsRef.current = result.logs;
          setLogs(result.logs);
          setStatus(result.status);
          logsCache.set(jobId, result.logs);
          statusCache.set(jobId, result.status);
          return;
        }

        // Job is not complete, connect WebSocket if not already connected (or early connected)
        // Note: We already call connectWebSocket below, so purely rely on that.
      });
    }

    // Connect WebSocket
    connectWebSocket(jobId);

    function connectWebSocket(wsJobId: string) {
      // Don't connect if component unmounted or job changed
      if (activeJobIdRef.current !== wsJobId) return;

      // Construct WebSocket URL
      const baseUrl = import.meta.env.VITE_WS_BASE_URL
        ? import.meta.env.VITE_WS_BASE_URL
        : `ws://${window.location.hostname}:8000/api/v1`;

      const url = `${baseUrl}/ws/jobs/${wsJobId}/logs?token=${token}`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      // Capture jobId in closure for the callbacks
      const capturedJobId = wsJobId;

      ws.onopen = () => {
        // Only update if this is still the active job
        if (activeJobIdRef.current === capturedJobId) {
          setStatus("CONNECTED");
          console.log(`Connected to logs for job ${capturedJobId}`);
        }
      };

      ws.onmessage = (event) => {
        // Only process if this is still the active job
        if (activeJobIdRef.current !== capturedJobId) {
          return;
        }

        try {
          const data = JSON.parse(event.data) as LogMessage;

          // Skip system messages (like "Log streaming started.") to prevent duplicates
          if (data.type === "system") {
            return;
          }

          // Use Ref to check for duplicates and append
          const exists = currentLogsRef.current.some(
            (log) =>
              log.payload.message === data.payload.message &&
              log.payload.ts === data.payload.ts,
          );

          if (!exists) {
            currentLogsRef.current.push(data);
            // Trigger React update with new array
            setLogs([...currentLogsRef.current]);

            // Update cache
            logsCache.set(capturedJobId, [...currentLogsRef.current]);
          }

          if (data.type === "status" && data.payload.status) {
            setStatus(data.payload.status);
            statusCache.set(capturedJobId, data.payload.status);
          }
        } catch (err) {
          console.error("Failed to parse WS message", err);
        }
      };

      ws.onclose = (event) => {
        console.log(
          `WS Closed for job ${capturedJobId}: ${event.code} - ${event.reason}`,
        );

        // Only update status if this is still the active job
        if (activeJobIdRef.current !== capturedJobId) {
          return;
        }

        if (event.code === 1000) {
          setStatus((prev) => {
            const finalStatus = prev === "CONNECTED" ? "COMPLETED" : prev;
            statusCache.set(capturedJobId, finalStatus);
            return finalStatus;
          });
        } else {
          setStatus("DISCONNECTED");
        }
      };

      ws.onerror = (error) => {
        console.error("WS Error", error);
        if (activeJobIdRef.current === capturedJobId) {
          setStatus("ERROR");
        }
      };
    }

    return () => {
      if (
        wsRef.current &&
        (wsRef.current.readyState === WebSocket.OPEN ||
          wsRef.current.readyState === WebSocket.CONNECTING)
      ) {
        wsRef.current.close();
      }
    };
  }, [jobId, token, fetchHistoricalLogs]);

  // Cleanup effect
  useEffect(() => {
    return () => {
      // On unmount/change, ensure we saved the latest logs from Ref
      if (activeJobIdRef.current && currentLogsRef.current.length > 0) {
        logsCache.set(activeJobIdRef.current, [...currentLogsRef.current]);
        statusCache.set(activeJobIdRef.current, status);
      }
    };
  }, [status]); // Only depend on status, logs are in ref

  return { logs, status };
}
