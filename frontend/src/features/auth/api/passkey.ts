// frontend/src/features/auth/api/passkey.ts
/**
 * Passkey (WebAuthn) API client for passwordless authentication.
 *
 * Uses @simplewebauthn/browser for WebAuthn browser API interaction.
 */

import {
  startRegistration,
  startAuthentication,
  browserSupportsWebAuthn,
} from "@simplewebauthn/browser";
import type {
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
  RegistrationResponseJSON,
  AuthenticationResponseJSON,
} from "@simplewebauthn/types";

import { api } from "@/lib/apiClient";

// --- Types ---

export interface PasskeyInfo {
  id: string;
  device_name: string | null;
  created_at: string | null;
  last_used_at: string | null;
  backup_eligible: boolean;
  backup_state: boolean;
}

export interface PasskeyStatusResponse {
  passkey_count: number;
  passkeys: PasskeyInfo[];
}

export interface AuthenticationResult {
  access_token: string;
  token_type: string;
}

// --- Helper Functions ---

/**
 * Check if WebAuthn is supported in the current browser.
 */
export function isWebAuthnSupported(): boolean {
  return browserSupportsWebAuthn();
}

// --- API Client ---

export const passkeyApi = {
  /**
   * Get registration options from the server.
   * Requires authentication.
   */
  getRegistrationOptions: async (): Promise<PublicKeyCredentialCreationOptionsJSON> => {
    const response = await api.post<PublicKeyCredentialCreationOptionsJSON>(
      "/v1/auth/passkey/register/options"
    );
    return response.data;
  },

  /**
   * Complete passkey registration with the browser.
   * Returns the newly registered passkey info.
   */
  register: async (deviceName?: string): Promise<PasskeyInfo> => {
    // Step 1: Get registration options from server
    const options = await passkeyApi.getRegistrationOptions();

    // Step 2: Start WebAuthn registration (browser prompt)
    let credential: RegistrationResponseJSON;
    try {
      credential = await startRegistration({ optionsJSON: options });
    } catch (error) {
      // User cancelled or error
      if (error instanceof Error) {
        if (error.name === "NotAllowedError") {
          throw new Error("Registration was cancelled or not allowed.");
        }
        throw error;
      }
      throw new Error("Registration failed.");
    }

    // Step 3: Send credential to server for verification
    const response = await api.post<PasskeyInfo>("/v1/auth/passkey/register/verify", {
      credential,
      device_name: deviceName,
    });

    return response.data;
  },

  /**
   * Get authentication options from the server.
   * Public endpoint (no auth required).
   * Uses discoverable credentials flow (no user-specific credentials exposed).
   */
  getAuthenticationOptions: async (): Promise<PublicKeyCredentialRequestOptionsJSON> => {
    const response = await api.post<PublicKeyCredentialRequestOptionsJSON>(
      "/v1/auth/passkey/login/options",
      {}
    );
    return response.data;
  },

  /**
   * Authenticate with a passkey.
   * Returns access token on success.
   * Uses discoverable credentials - browser finds matching passkeys by RP ID.
   */
  authenticate: async (): Promise<AuthenticationResult> => {
    // Step 1: Get authentication options from server (discoverable flow)
    const options = await passkeyApi.getAuthenticationOptions();

    // Step 2: Start WebAuthn authentication (browser prompt)
    let credential: AuthenticationResponseJSON;
    try {
      credential = await startAuthentication({ optionsJSON: options });
    } catch (error) {
      if (error instanceof Error) {
        if (error.name === "NotAllowedError") {
          throw new Error("Authentication was cancelled or not allowed.");
        }
        throw error;
      }
      throw new Error("Authentication failed.");
    }

    // Step 3: Send credential to server for verification
    const response = await api.post<AuthenticationResult>(
      "/v1/auth/passkey/login/verify",
      { credential }
    );

    return response.data;
  },

  /**
   * List all passkeys for the current user.
   * Requires authentication.
   */
  listPasskeys: async (): Promise<PasskeyStatusResponse> => {
    const response = await api.get<PasskeyStatusResponse>("/v1/auth/passkey/list");
    return response.data;
  },

  /**
   * Rename a passkey.
   * Requires authentication.
   */
  renamePasskey: async (passkeyId: string, name: string): Promise<void> => {
    await api.put(`/v1/auth/passkey/${passkeyId}/name`, { name });
  },

  /**
   * Delete a passkey.
   * Requires authentication.
   */
  deletePasskey: async (passkeyId: string): Promise<void> => {
    await api.delete(`/v1/auth/passkey/${passkeyId}`);
  },
};
