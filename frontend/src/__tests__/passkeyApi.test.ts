// frontend/src/__tests__/passkeyApi.test.ts
/**
 * Unit tests for passkey API client
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { passkeyApi, isWebAuthnSupported } from "@/features/auth/api/passkey";
import * as simpleWebAuthn from "@simplewebauthn/browser";

// Mock the API client
vi.mock("@/lib/apiClient", () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

// Mock @simplewebauthn/browser
vi.mock("@simplewebauthn/browser", () => ({
  startRegistration: vi.fn(),
  startAuthentication: vi.fn(),
  browserSupportsWebAuthn: vi.fn(),
}));

import { api } from "@/lib/apiClient";

describe("passkeyApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("isWebAuthnSupported", () => {
    it("returns true when browser supports WebAuthn", () => {
      vi.mocked(simpleWebAuthn.browserSupportsWebAuthn).mockReturnValue(true);
      expect(isWebAuthnSupported()).toBe(true);
    });

    it("returns false when browser does not support WebAuthn", () => {
      vi.mocked(simpleWebAuthn.browserSupportsWebAuthn).mockReturnValue(false);
      expect(isWebAuthnSupported()).toBe(false);
    });
  });

  describe("getRegistrationOptions", () => {
    it("calls correct endpoint and returns options", async () => {
      const mockOptions = {
        challenge: "test-challenge",
        rp: { name: "Test", id: "example.com" },
        user: { id: "user-123", name: "test@example.com", displayName: "Test User" },
        pubKeyCredParams: [],
        timeout: 60000,
        attestation: "none" as const,
      };

      vi.mocked(api.post).mockResolvedValue({ data: mockOptions });

      const result = await passkeyApi.getRegistrationOptions();

      expect(api.post).toHaveBeenCalledWith("/v1/auth/passkey/register/options");
      expect(result).toEqual(mockOptions);
    });
  });

  describe("register", () => {
    it("completes full registration flow successfully", async () => {
      const mockOptions = { challenge: "test-challenge" };
      const mockCredential = { id: "cred-123", rawId: "raw-123" };
      const mockPasskey = {
        id: "passkey-123",
        device_name: "Test Device",
        created_at: "2026-01-18T00:00:00Z",
        last_used_at: null,
        backup_eligible: false,
        backup_state: false,
      };

      vi.mocked(api.post)
        .mockResolvedValueOnce({ data: mockOptions })
        .mockResolvedValueOnce({ data: mockPasskey });

      vi.mocked(simpleWebAuthn.startRegistration).mockResolvedValue(
        mockCredential as any
      );

      const result = await passkeyApi.register("Test Device");

      expect(api.post).toHaveBeenCalledTimes(2);
      expect(api.post).toHaveBeenNthCalledWith(
        2,
        "/v1/auth/passkey/register/verify",
        {
          credential: mockCredential,
          device_name: "Test Device",
        }
      );
      expect(result).toEqual(mockPasskey);
    });

    it("throws error when user cancels registration", async () => {
      const mockOptions = { challenge: "test-challenge" };
      vi.mocked(api.post).mockResolvedValue({ data: mockOptions });

      const notAllowedError = new Error("User cancelled");
      notAllowedError.name = "NotAllowedError";
      vi.mocked(simpleWebAuthn.startRegistration).mockRejectedValue(
        notAllowedError
      );

      await expect(passkeyApi.register("Test")).rejects.toThrow(
        "Registration was cancelled or not allowed."
      );
    });

    it("throws generic error for other registration failures", async () => {
      const mockOptions = { challenge: "test-challenge" };
      vi.mocked(api.post).mockResolvedValue({ data: mockOptions });

      vi.mocked(simpleWebAuthn.startRegistration).mockRejectedValue(
        new Error("Unknown error")
      );

      await expect(passkeyApi.register("Test")).rejects.toThrow("Unknown error");
    });

    it("throws generic message when registration fails with non-Error value", async () => {
      const mockOptions = { challenge: "test-challenge" };
      vi.mocked(api.post).mockResolvedValue({ data: mockOptions });

      // Reject with a string instead of an Error object
      vi.mocked(simpleWebAuthn.startRegistration).mockRejectedValue(
        "Some non-error rejection"
      );

      await expect(passkeyApi.register("Test")).rejects.toThrow("Registration failed.");
    });
  });


  describe("getAuthenticationOptions", () => {
    it("calls endpoint without email", async () => {
      const mockOptions = { challenge: "auth-challenge" };
      vi.mocked(api.post).mockResolvedValue({ data: mockOptions });

      const result = await passkeyApi.getAuthenticationOptions();

      expect(api.post).toHaveBeenCalledWith("/v1/auth/passkey/login/options", {});
      expect(result).toEqual(mockOptions);
    });

    it("calls endpoint with email", async () => {
      const mockOptions = { challenge: "auth-challenge" };
      vi.mocked(api.post).mockResolvedValue({ data: mockOptions });

      const result = await passkeyApi.getAuthenticationOptions("test@example.com");

      expect(api.post).toHaveBeenCalledWith("/v1/auth/passkey/login/options", {
        email: "test@example.com",
      });
      expect(result).toEqual(mockOptions);
    });
  });

  describe("authenticate", () => {
    it("completes authentication flow successfully", async () => {
      const mockOptions = { challenge: "auth-challenge" };
      const mockCredential = { id: "cred-123", rawId: "raw-123" };
      const mockResult = {
        access_token: "test-token",
        token_type: "bearer",
      };

      vi.mocked(api.post)
        .mockResolvedValueOnce({ data: mockOptions })
        .mockResolvedValueOnce({ data: mockResult });

      vi.mocked(simpleWebAuthn.startAuthentication).mockResolvedValue(
        mockCredential as any
      );

      const result = await passkeyApi.authenticate("test@example.com");

      expect(api.post).toHaveBeenNthCalledWith(
        2,
        "/v1/auth/passkey/login/verify",
        { credential: mockCredential }
      );
      expect(result).toEqual(mockResult);
    });

    it("throws error when user cancels authentication", async () => {
      const mockOptions = { challenge: "auth-challenge" };
      vi.mocked(api.post).mockResolvedValue({ data: mockOptions });

      const notAllowedError = new Error("User cancelled");
      notAllowedError.name = "NotAllowedError";
      vi.mocked(simpleWebAuthn.startAuthentication).mockRejectedValue(
        notAllowedError
      );

      await expect(passkeyApi.authenticate()).rejects.toThrow(
        "Authentication was cancelled or not allowed."
      );
    });

    it("throws generic message when authentication fails with non-Error value", async () => {
      const mockOptions = { challenge: "auth-challenge" };
      vi.mocked(api.post).mockResolvedValue({ data: mockOptions });

      // Reject with a string instead of an Error object
      vi.mocked(simpleWebAuthn.startAuthentication).mockRejectedValue(
        "Some non-error rejection"
      );

      await expect(passkeyApi.authenticate()).rejects.toThrow("Authentication failed.");
    });

    it("throws the original error when authentication fails with regular Error", async () => {
      const mockOptions = { challenge: "auth-challenge" };
      vi.mocked(api.post).mockResolvedValue({ data: mockOptions });

      // Regular Error (not NotAllowedError) should be re-thrown
      vi.mocked(simpleWebAuthn.startAuthentication).mockRejectedValue(
        new Error("Some other authentication error")
      );

      await expect(passkeyApi.authenticate()).rejects.toThrow("Some other authentication error");
    });
  });



  describe("listPasskeys", () => {
    it("fetches and returns passkey list", async () => {
      const mockResponse = {
        passkey_count: 2,
        passkeys: [
          { id: "1", device_name: "Device 1" },
          { id: "2", device_name: "Device 2" },
        ],
      };

      vi.mocked(api.get).mockResolvedValue({ data: mockResponse });

      const result = await passkeyApi.listPasskeys();

      expect(api.get).toHaveBeenCalledWith("/v1/auth/passkey/list");
      expect(result).toEqual(mockResponse);
    });
  });

  describe("renamePasskey", () => {
    it("sends rename request with correct parameters", async () => {
      vi.mocked(api.put).mockResolvedValue({ data: {} });

      await passkeyApi.renamePasskey("passkey-123", "New Name");

      expect(api.put).toHaveBeenCalledWith("/v1/auth/passkey/passkey-123/name", {
        name: "New Name",
      });
    });
  });

  describe("deletePasskey", () => {
    it("sends delete request to correct endpoint", async () => {
      vi.mocked(api.delete).mockResolvedValue({ data: {} });

      await passkeyApi.deletePasskey("passkey-123");

      expect(api.delete).toHaveBeenCalledWith("/v1/auth/passkey/passkey-123");
    });
  });
});
