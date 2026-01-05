import { z } from "zod";
import { api } from "@/lib/apiClient";

// --- Types ---

export const AuditLogSchema = z.object({
  id: z.number(),
  event_id: z.string(),
  timestamp: z.string(),
  category: z.string(),
  action: z.string(),
  severity: z.string(), // info, warning, error, critical
  success: z.boolean(),
  actor_email: z.string().nullable(),
  actor_type: z.string(),
  impersonator_id: z.string().nullable(),
  ip_address: z.string(),
  resource_type: z.string().nullable(),
  resource_id: z.string().nullable(),
  details: z.record(z.string(), z.any()).nullable(),
  outcome: z.string(),
  reason_code: z.string().nullable(),
});

export type AuditLog = z.infer<typeof AuditLogSchema>;

export const AuditStatsSchema = z.object({
  total_events: z.number(),
  events_today: z.number(),
  failure_rate_24h: z.number(),
  top_actions: z.array(
    z.object({
      action: z.string(),
      count: z.number(),
    }),
  ),
  severity_counts: z.record(z.string(), z.number()),
});

export type AuditStats = z.infer<typeof AuditStatsSchema>;

export type AuditLogFilters = {
  page?: number;
  per_page?: number;
  category?: string;
  action?: string;
  severity?: string;
  actor_email?: string; // Partial match
  start_date?: string;
  end_date?: string;
};

export type AuditLogResponse = {
  items: AuditLog[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
};

// --- API ---

export const getAuditLogs = async (
  filters: AuditLogFilters,
): Promise<AuditLogResponse> => {
  const response = await api.get("/v1/admin/audit/logs", { params: filters });
  return response.data;
};

export const getAuditStats = async (): Promise<AuditStats> => {
  const response = await api.get("/v1/admin/audit/stats");
  return AuditStatsSchema.parse(response.data);
};

export const getAuditEvent = async (eventId: string): Promise<AuditLog> => {
  const response = await api.get(`/v1/admin/audit/logs/${eventId}`);
  return AuditLogSchema.parse(response.data);
};

export const exportAuditLogs = async (
  filters: AuditLogFilters,
): Promise<{ job_id: string }> => {
  const response = await api.post("/v1/admin/audit/export", filters);
  return response.data;
};

export const verifyAuditIntegrity = async (): Promise<{
  verified: boolean;
  issues: string[];
}> => {
  const response = await api.post("/v1/admin/audit/verify");
  return response.data;
};
