import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { LogMessage } from "../types";

export function useJobLogs(jobId: string | null) {
  const [logs, setLogs] = useState<LogMessage[]>([]);
  const [status, setStatus] = useState<string>("CONNECTING");
  const wsRef = useRef<WebSocket | null>(null);
  const token = useAuthStore((state) => state.accessToken);

  useEffect(() => {
    if (!jobId || !token) return;

    // Reset logs on new job
    setLogs([]);
    setStatus("CONNECTING");

    // Construct URL
    // Use relative path for proxying or absolute if env var set
    const baseUrl = import.meta.env.VITE_WS_BASE_URL
      ? import.meta.env.VITE_WS_BASE_URL
      : `ws://${window.location.hostname}:8000/api/v1`;

    // Note: We are bypassing the proxy for WS usually because vite proxy WS support can be tricky if not set up with ws: true.
    const url = `${baseUrl}/ws/jobs/${jobId}/logs?token=${token}`;

    // In production we would want to respect window.location protocol (wss vs ws)
    // For now hardcoding localhost:8000 is safer for the dev environment we set up.

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("CONNECTED");
      console.log(`Connected to logs for job ${jobId}`);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as LogMessage;
        setLogs((prev) => [...prev, data]);

        if (data.type === "status" && data.payload.status) {
          setStatus(data.payload.status);
        }
      } catch (err) {
        console.error("Failed to parse WS message", err);
      }
    };

    ws.onclose = (event) => {
      console.log(`WS Closed: ${event.code} - ${event.reason}`);
      if (event.code === 1000) {
        setStatus("COMPLETED");
      } else {
        setStatus("DISCONNECTED");
      }
    };

    ws.onerror = (error) => {
      console.error("WS Error", error);
      setStatus("ERROR");
    };

    return () => {
      if (
        ws.readyState === WebSocket.OPEN ||
        ws.readyState === WebSocket.CONNECTING
      ) {
        ws.close();
      }
    };
  }, [jobId, token]);

  return { logs, status };
}
