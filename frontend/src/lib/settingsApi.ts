import { api } from "@/lib/apiClient";
import axios from "axios";

// Types for settings API
export interface SetupStatus {
  setup_completed: boolean;
}

export interface SettingsUpdate {
  tmdb_api_key?: string | null;
  omdb_api_key?: string | null;
  opensubtitles_api_key?: string | null;
  opensubtitles_username?: string | null;
  opensubtitles_password?: string | null;
  deepl_api_keys?: string[];
  qbittorrent_host?: string | null;
  qbittorrent_port?: number | null;
  qbittorrent_username?: string | null;
  qbittorrent_password?: string | null;
  allowed_media_folders?: string[];
  google_cloud_credentials?: string | null;
}

export interface DeepLUsage {
  key_alias: string;
  character_count: number;
  character_limit: number;
  valid: boolean | null | undefined;
}

export interface GoogleUsage {
  total_characters: number;
  this_month_characters: number;
  source: "google_cloud_monitoring" | "google_cloud_monitoring_cached";
  last_updated?: string | null;
}

export interface SettingsRead extends SettingsUpdate {
  setup_completed: boolean;
  deepl_usage?: DeepLUsage[];
  google_usage?: GoogleUsage;
  // Validation status from backend
  tmdb_valid?: string; // "valid", "invalid", "limit_reached", or undefined
  omdb_valid?: string; // "valid", "invalid", "limit_reached", or undefined
  opensubtitles_valid?: boolean;
  opensubtitles_key_valid?: boolean;
  // OpenSubtitles subscription info
  opensubtitles_level?: string; // e.g. "VIP Member", "Standard"
  opensubtitles_vip?: boolean;
  opensubtitles_allowed_downloads?: number;
  opensubtitles_rate_limited?: boolean;
  // Google Cloud status
  google_cloud_configured?: boolean;
  google_cloud_project_id?: string | null;
  google_cloud_valid?: boolean | null;
  google_cloud_error?: string | null;
}

export interface SetupComplete {
  admin_email: string;
  admin_password: string;
  settings?: SettingsUpdate | null;
}

// Public endpoint - no auth required
export const getSetupStatus = async (): Promise<SetupStatus> => {
  // Use axios directly (no auth interceptor needed for public endpoint)
  const response = await axios.get<SetupStatus>("/api/v1/setup/status");
  return response.data;
};

// Public endpoint - complete setup (only works if setup_completed is false)
export const completeSetup = async (
  data: SetupComplete,
): Promise<SetupStatus> => {
  const response = await axios.post<SetupStatus>(
    "/api/v1/setup/complete",
    data,
  );
  return response.data;
};

// Public endpoint - skip setup
export const skipSetup = async (
  adminEmail?: string,
  adminPassword?: string,
): Promise<SetupStatus> => {
  const response = await axios.post<SetupStatus>("/api/v1/setup/skip", {
    admin_email: adminEmail || null,
    admin_password: adminPassword || null,
  });
  return response.data;
};

// Admin endpoint - get current settings (masked)
export const getSettings = async (): Promise<SettingsRead> => {
  const response = await api.get<SettingsRead>("/v1/settings");
  return response.data;
};

// Admin endpoint - update settings
export const updateSettings = async (
  data: SettingsUpdate,
): Promise<SettingsRead> => {
  const response = await api.put<SettingsRead>("/v1/settings", data);
  return response.data;
};

// Admin endpoint - test DeepL API key
export interface DeepLTestResult {
  valid: boolean;
  key_type?: "free" | "pro";
  character_count?: number;
  character_limit?: number;
  remaining?: number;
  usage_percent?: number;
  error?: string;
}

export const testDeepLKey = async (
  apiKey: string,
): Promise<DeepLTestResult> => {
  const response = await api.post<DeepLTestResult>(
    "/v1/settings/test-deepl-key",
    {
      api_key: apiKey,
    },
  );
  return response.data;
};

// --- Translation Stats API ---

export interface AggregateStats {
  total_translations: number;
  total_characters: number;
  deepl_characters: number;
  google_characters: number;
  success_count: number;
  failure_count: number;
}

export interface TranslationStatsResponse {
  all_time: AggregateStats;
  last_30_days: AggregateStats;
  last_7_days: AggregateStats;
}

export interface TranslationLogEntry {
  id: number;
  timestamp: string;
  file_name: string;
  source_language?: string;
  target_language: string;
  service_used: string;
  characters_billed: number;
  deepl_characters: number;
  google_characters: number;
  status: string;
  output_file_path?: string | null;
}

export interface TranslationHistoryResponse {
  items: TranslationLogEntry[];
  total: number;
  page: number;
  page_size: number;
}

// Admin endpoint - get translation statistics
export const getTranslationStats =
  async (): Promise<TranslationStatsResponse> => {
    const response = await api.get<TranslationStatsResponse>(
      "/v1/translation-stats",
    );
    return response.data;
  };

// Admin endpoint - get translation history
export const getTranslationHistory = async (
  page: number = 1,
  pageSize: number = 10,
): Promise<TranslationHistoryResponse> => {
  const response = await api.get<TranslationHistoryResponse>(
    `/v1/translation-stats/history?page=${page}&page_size=${pageSize}`,
  );
  return response.data;
};
