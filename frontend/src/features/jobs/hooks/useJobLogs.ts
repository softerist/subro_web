import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { LogMessage } from "../types";

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

    // Note: For completed jobs, we could skip WebSocket and just fetch from DB
    // But the WebSocket endpoint already handles sending historical logs from Redis
    // So we just connect to WebSocket - it will send history + job complete message if done

    // Connect WebSocket for both running and completed jobs
    // WebSocket sends historical logs from Redis, so no need to fetch from DB separately
    connectWebSocket(jobId);

    function connectWebSocket(wsJobId: string) {
      // Don't connect if component unmounted or job changed
      if (activeJobIdRef.current !== wsJobId) return;

      // Construct WebSocket URL - use window.location to work with proxies/Caddy
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const baseUrl = import.meta.env.VITE_WS_BASE_URL
        ? import.meta.env.VITE_WS_BASE_URL
        : `${protocol}//${window.location.host}/api/v1`;

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
  }, [jobId, token]);

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
