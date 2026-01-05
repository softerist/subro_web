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
  actor_user_id: z.string().nullable().optional(),
  actor_email: z.string().nullable(),
  actor_type: z.string(),
  ip_address: z.string(),
  request_id: z.string().nullable().optional(),
  source: z.string().optional(),
  user_agent: z.string().nullable().optional(),
  resource_type: z.string().nullable(),
  resource_id: z.string().nullable(),
  details: z.record(z.string(), z.any()).nullable(),
  target_user_id: z.string().nullable().optional(),
  error_code: z.string().nullable().optional(),
  http_status: z.number().nullable().optional(),
  impersonator_id: z.string().nullable().optional(),
  outcome: z.string().optional(),
  reason_code: z.string().nullable().optional(),
});

export type AuditLog = z.infer<typeof AuditLogSchema>;

export const AuditStatsSchema = z.object({
  total_events: z.number(),
  events_by_category: z.record(z.string(), z.number()),
  events_by_severity: z.record(z.string(), z.number()),
  events_last_24h: z.number(),
  failed_logins_24h: z.number(),
  critical_events_24h: z.number(),
});

export type AuditStats = z.infer<typeof AuditStatsSchema>;

const AuditVerifyResponseSchema = z.object({
  verified: z.boolean(),
  details: z.object({
    issues: z.array(z.string()).optional(),
    checked_count: z.number().optional(),
    corrupted_count: z.number().optional(),
  }),
});

export type AuditVerifyResult = {
  verified: boolean;
  issues: string[];
  checkedCount: number | null;
  corruptedCount: number | null;
};

export type AuditLogFilters = {
  page?: number;
  per_page?: number;
  cursor?: string | null;
  include_count?: boolean;
  category?: string;
  action?: string;
  severity?: string;
  actor_user_id?: string;
  actor_email?: string;
  target_user_id?: string;
  resource_type?: string;
  resource_id?: string;
  ip_address?: string;
  success?: boolean;
  start_date?: string;
  end_date?: string;
};

export type AuditLogResponse = {
  items: AuditLog[];
  next_cursor: string | null;
  total_count: number | null;
};

// --- API ---

export const getAuditLogs = async (
  filters: AuditLogFilters,
): Promise<AuditLogResponse> => {
  const response = await api.get("/v1/admin/audit", {
    params: {
      limit: filters.per_page,
      cursor: filters.cursor ?? undefined,
      include_count: filters.include_count ?? true,
      category: filters.category,
      action: filters.action,
      severity: filters.severity,
      actor_user_id: filters.actor_user_id,
      actor_email: filters.actor_email,
      target_user_id: filters.target_user_id,
      resource_type: filters.resource_type,
      resource_id: filters.resource_id,
      ip_address: filters.ip_address,
      success: filters.success,
      start_date: filters.start_date,
      end_date: filters.end_date,
    },
  });
  return response.data;
};

export const getAuditStats = async (): Promise<AuditStats> => {
  const response = await api.get("/v1/admin/audit/stats");
  return AuditStatsSchema.parse(response.data);
};

export const getAuditEvent = async (eventId: string): Promise<AuditLog> => {
  const response = await api.get(`/v1/admin/audit/${eventId}`);
  return AuditLogSchema.parse(response.data);
};

export const exportAuditLogs = async (
  filters: AuditLogFilters,
): Promise<{ job_id: string }> => {
  const response = await api.post("/v1/admin/audit/export", {
    category: filters.category,
    action: filters.action,
    severity: filters.severity,
    start_date: filters.start_date,
    end_date: filters.end_date,
  });
  return response.data;
};

export const verifyAuditIntegrity = async (): Promise<AuditVerifyResult> => {
  const response = await api.post("/v1/admin/audit/verify");
  const parsed = AuditVerifyResponseSchema.parse(response.data);
  return {
    verified: parsed.verified,
    issues: parsed.details.issues ?? [],
    checkedCount: parsed.details.checked_count ?? null,
    corruptedCount: parsed.details.corrupted_count ?? null,
  };
};
