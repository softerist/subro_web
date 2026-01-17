// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mfaApi } from "../features/auth/api/mfa";
import { api } from "../lib/apiClient";

vi.mock("../lib/apiClient", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("mfaApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getStatus calls correct endpoint", async () => {
    const mockData = { mfa_enabled: true, trusted_devices_count: 0 };
    (api.get as any).mockResolvedValue({ data: mockData });

    const res = await mfaApi.getStatus();
    expect(api.get).toHaveBeenCalledWith("/v1/auth/mfa/status");
    expect(res).toEqual(mockData);
  });

  it("setup calls correct endpoint", async () => {
    const mockData = {
      secret: "secret",
      qr_code: "qr_code",
      backup_codes: ["code1"],
    };
    (api.post as any).mockResolvedValue({ data: mockData });

    const res = await mfaApi.setup();
    expect(api.post).toHaveBeenCalledWith("/v1/auth/mfa/setup");
    expect(res).toEqual(mockData);
  });

  it("verifySetup calls correct endpoint with data", async () => {
    const input = {
      secret: "secret",
      code: "123456",
      backup_codes: ["code1"],
    };
    const mockData = { mfa_enabled: true, trusted_devices_count: 0 };
    (api.post as any).mockResolvedValue({ data: mockData });

    const res = await mfaApi.verifySetup(input);
    expect(api.post).toHaveBeenCalledWith("/v1/auth/mfa/verify-setup", input);
    expect(res).toEqual(mockData);
  });

  it("verify calls correct endpoint with data", async () => {
    const input = { code: "123456", trust_device: true };
    const mockData = { access_token: "token", token_type: "bearer" };
    (api.post as any).mockResolvedValue({ data: mockData });

    const res = await mfaApi.verify(input);
    expect(api.post).toHaveBeenCalledWith("/v1/auth/mfa/verify", input);
    expect(res).toEqual(mockData);
  });

  it("disable calls correct endpoint using DELETE with payload", async () => {
    const password = "password123";
    const mockData = { mfa_enabled: false, trusted_devices_count: 0 };
    // Usually axios delete has config as 2nd arg
    (api.delete as any).mockResolvedValue({ data: mockData });

    const res = await mfaApi.disable(password);
    expect(api.delete).toHaveBeenCalledWith("/v1/auth/mfa", {
      data: { password },
    });
    expect(res).toEqual(mockData);
  });

  it("getTrustedDevices calls correct endpoint", async () => {
    const mockData = [
      {
        id: "1",
        device_name: "Chrome",
        ip_address: "1.1.1.1",
        created_at: "now",
        last_used_at: "now",
        expires_at: "later",
        is_expired: false,
      },
    ];
    (api.get as any).mockResolvedValue({ data: mockData });

    const res = await mfaApi.getTrustedDevices();
    expect(api.get).toHaveBeenCalledWith("/v1/auth/mfa/devices");
    expect(res).toEqual(mockData);
  });

  it("revokeTrustedDevice calls correct endpoint with ID", async () => {
    const deviceId = "dev-123";
    (api.delete as any).mockResolvedValue({ data: {} });

    await mfaApi.revokeTrustedDevice(deviceId);
    expect(api.delete).toHaveBeenCalledWith(`/v1/auth/mfa/devices/${deviceId}`);
  });
});
