// frontend/src/features/auth/api/mfa.ts
/**
 * MFA (Multi-Factor Authentication) API client
 */

import { api } from "@/lib/apiClient";

export interface MfaStatus {
  mfa_enabled: boolean;
  trusted_devices_count: number;
}

export interface MfaSetupResponse {
  secret: string;
  qr_code: string;
  backup_codes: string[];
}

export interface TrustedDevice {
  id: string;
  device_name: string | null;
  ip_address: string | null;
  created_at: string;
  last_used_at: string | null;
  expires_at: string;
  is_expired: boolean;
}

export const mfaApi = {
  /**
   * Get current MFA status
   */
  getStatus: async (): Promise<MfaStatus> => {
    const response = await api.get("/v1/auth/mfa/status");
    return response.data;
  },

  /**
   * Initialize MFA setup - returns QR code and backup codes
   */
  setup: async (): Promise<MfaSetupResponse> => {
    const response = await api.post("/v1/auth/mfa/setup");
    return response.data;
  },

  /**
   * Verify setup code and enable MFA
   */
  verifySetup: async (data: {
    secret: string;
    code: string;
    backup_codes: string[];
  }): Promise<MfaStatus> => {
    const response = await api.post("/v1/auth/mfa/verify-setup", data);
    return response.data;
  },

  /**
   * Verify MFA code during login
   */
  verify: async (data: {
    code: string;
    trust_device: boolean;
  }): Promise<{ access_token: string; token_type: string }> => {
    const response = await api.post("/v1/auth/mfa/verify", data);
    return response.data;
  },

  /**
   * Disable MFA (requires password)
   */
  disable: async (password: string): Promise<MfaStatus> => {
    const response = await api.delete("/v1/auth/mfa", {
      data: { password },
    });
    return response.data;
  },

  /**
   * List trusted devices
   */
  getTrustedDevices: async (): Promise<TrustedDevice[]> => {
    const response = await api.get("/v1/auth/mfa/devices");
    return response.data;
  },

  /**
   * Revoke a trusted device
   */
  revokeTrustedDevice: async (deviceId: string): Promise<void> => {
    await api.delete(`/v1/auth/mfa/devices/${deviceId}`);
  },
};
