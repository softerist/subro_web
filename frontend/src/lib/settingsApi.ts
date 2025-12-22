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
}

export interface DeepLUsage {
  key_alias: string;
  character_count: number;
  character_limit: number;
  valid: boolean;
}

export interface SettingsRead extends SettingsUpdate {
  setup_completed: boolean;
  deepl_usage?: DeepLUsage[];
  // Validation status from backend
  tmdb_valid?: boolean;
  omdb_valid?: boolean;
  opensubtitles_valid?: boolean;
  opensubtitles_key_valid?: boolean;
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
