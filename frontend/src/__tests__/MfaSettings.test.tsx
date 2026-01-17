/** @vitest-environment jsdom */
import {
  render,
  screen,
  waitFor,
  cleanup,
  fireEvent,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MfaSettings } from "@/features/auth/components/MfaSettings";

const mockMfaApi = vi.hoisted(() => ({
  getStatus: vi.fn(),
  getTrustedDevices: vi.fn(),
  setup: vi.fn(),
  verifySetup: vi.fn(),
  disable: vi.fn(),
  revokeTrustedDevice: vi.fn(),
}));

vi.mock("@/features/auth/api/mfa", () => ({
  mfaApi: mockMfaApi,
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: vi.fn().mockImplementation((selector: any) =>
    selector({
      user: { id: "user-1" },
      setUser: vi.fn(),
    }),
  ),
}));

vi.mock("lucide-react", () => ({
  Loader2: () => <div data-testid="Loader2" />,
  Trash2: () => <div data-testid="Trash2" />,
  Smartphone: () => <div data-testid="Smartphone" />,
  ShieldCheck: () => <div data-testid="ShieldCheck" />,
  ShieldOff: () => <div data-testid="ShieldOff" />,
  QrCode: () => <div data-testid="QrCode" />,
  Copy: () => <div data-testid="Copy" />,
  Check: () => <div data-testid="Check" />,
  X: () => <div data-testid="X" />,
}));

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe("MfaSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // default status disabled
    mockMfaApi.getStatus.mockResolvedValue({ mfa_enabled: false });
    mockMfaApi.getTrustedDevices.mockResolvedValue([]);
    mockMfaApi.setup.mockResolvedValue({
      qr_code: "data:image/png;base64,abc",
      secret: "SECRET123",
      backup_codes: ["111111", "222222"],
    });
    mockMfaApi.verifySetup.mockResolvedValue({});
    mockMfaApi.disable.mockResolvedValue({});
    mockMfaApi.revokeTrustedDevice.mockResolvedValue({});
    // clipboard mock
    vi.stubGlobal("navigator", {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("renders enable button when MFA is disabled", async () => {
    render(<MfaSettings />, { wrapper: createWrapper() });
    await waitFor(() => expect(mockMfaApi.getStatus).toHaveBeenCalled());
    expect(
      await screen.findByRole("button", {
        name: /enable two-factor authentication/i,
      }),
    ).toBeTruthy();
  });

  it("starts setup flow and verifies code", async () => {
    const user = userEvent.setup();
    render(<MfaSettings />, { wrapper: createWrapper() });
    await waitFor(() => expect(mockMfaApi.getStatus).toHaveBeenCalled());

    const enableBtn = await screen.findByRole("button", {
      name: /enable two-factor/i,
    });
    await user.click(enableBtn);
    await waitFor(() => expect(mockMfaApi.setup).toHaveBeenCalled());

    expect(
      await screen.findByText("Set Up Two-Factor Authentication"),
    ).toBeTruthy();
    expect(screen.getByText("SECRET123")).toBeTruthy();
    expect(screen.getByText("111111")).toBeTruthy();

    await user.type(screen.getByLabelText(/enter code/i), "123456");
    await user.click(screen.getByRole("button", { name: /enable mfa/i }));

    await waitFor(() => {
      expect(mockMfaApi.verifySetup).toHaveBeenCalledWith({
        secret: "SECRET123",
        code: "123456",
        backup_codes: ["111111", "222222"],
      });
    });
  });

  it("shows setup error message when starting fails", async () => {
    mockMfaApi.setup.mockRejectedValue({
      response: { data: { detail: "cannot start" } },
    });
    render(<MfaSettings />, { wrapper: createWrapper() });
    await waitFor(() => expect(mockMfaApi.getStatus).toHaveBeenCalled());

    const btn = await screen.findByRole("button", {
      name: /enable two-factor/i,
    });
    fireEvent.click(btn);

    expect(await screen.findByText("cannot start")).toBeTruthy();
  });

  it("renders enabled state, revokes device, and disables mfa", async () => {
    mockMfaApi.getStatus.mockResolvedValue({ mfa_enabled: true });
    mockMfaApi.getTrustedDevices.mockResolvedValue([
      {
        id: "dev-1",
        device_name: "Laptop",
        last_used_at: null,
        is_expired: false,
      },
    ]);
    const user = userEvent.setup();

    render(<MfaSettings />, { wrapper: createWrapper() });
    await waitFor(() => expect(mockMfaApi.getStatus).toHaveBeenCalled());

    expect(await screen.findByText("MFA is enabled")).toBeTruthy();
    expect(screen.getByText("Laptop")).toBeTruthy();

    // revoke first device
    const deviceRow = screen.getByText("Laptop").closest("div")?.parentElement;
    const revokeBtn = deviceRow?.querySelector("button");
    if (revokeBtn) {
      await user.click(revokeBtn);
      await waitFor(() =>
        expect(mockMfaApi.revokeTrustedDevice).toHaveBeenCalledWith(
          "dev-1",
          expect.anything(),
        ),
      );
    }

    // disable flow
    await user.click(screen.getByRole("button", { name: /disable/i }));
    const passwordInput = await screen.findByLabelText("Password");
    await user.type(passwordInput, "pass1234");
    await user.click(screen.getByRole("button", { name: /disable mfa/i }));

    await waitFor(() =>
      expect(mockMfaApi.disable).toHaveBeenCalledWith("pass1234"),
    );
  });

  it("shows error message when verification fails", async () => {
    mockMfaApi.verifySetup.mockRejectedValue({
      response: { data: { detail: "invalid token" } },
    });
    const user = userEvent.setup();
    render(<MfaSettings />, { wrapper: createWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /enable two-factor/i }),
    );
    await user.type(screen.getByLabelText(/enter code/i), "123456");
    await user.click(screen.getByRole("button", { name: /enable mfa/i }));

    expect(await screen.findByText("invalid token")).toBeTruthy();
  });

  it("shows error message when disabling fails", async () => {
    mockMfaApi.getStatus.mockResolvedValue({ mfa_enabled: true });
    mockMfaApi.disable.mockRejectedValue({
      response: { data: { detail: "wrong password" } },
    });
    const user = userEvent.setup();
    render(<MfaSettings />, { wrapper: createWrapper() });

    await user.click(await screen.findByRole("button", { name: /disable/i }));
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: /disable mfa/i }));

    expect(await screen.findByText("wrong password")).toBeTruthy();
  });

  it("copies backup codes to clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", {
      clipboard: { writeText },
    });
    render(<MfaSettings />, { wrapper: createWrapper() });

    fireEvent.click(
      await screen.findByRole("button", { name: /enable two-factor/i }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /copy all/i }));

    expect(writeText).toHaveBeenCalledWith("111111\n222222");
    expect(screen.getByText("Copied!")).toBeTruthy();

    // The message disappears after 2000ms
    await waitFor(() => expect(screen.queryByText("Copied!")).toBeNull(), {
      timeout: 3000,
    });
  });

  it("cancels setup flow", async () => {
    const user = userEvent.setup();
    render(<MfaSettings />, { wrapper: createWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /enable two-factor/i }),
    );
    expect(
      await screen.findByText("Set Up Two-Factor Authentication"),
    ).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Set Up Two-Factor Authentication")).toBeNull();
  });

  it("cancels disable dialog", async () => {
    mockMfaApi.getStatus.mockResolvedValue({ mfa_enabled: true });
    const user = userEvent.setup();
    render(<MfaSettings />, { wrapper: createWrapper() });

    await user.click(await screen.findByRole("button", { name: /disable/i }));
    expect(
      await screen.findByText("Disable Two-Factor Authentication?"),
    ).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(
        screen.queryByText("Disable Two-Factor Authentication?"),
      ).toBeNull();
    });
  });

  it("filters out expired trusted devices", async () => {
    mockMfaApi.getStatus.mockResolvedValue({ mfa_enabled: true });
    mockMfaApi.getTrustedDevices.mockResolvedValue([
      {
        id: "dev-1",
        device_name: "Active Laptop",
        last_used_at: null,
        is_expired: false,
      },
      {
        id: "dev-2",
        device_name: "Old Phone",
        last_used_at: null,
        is_expired: true,
      },
    ]);

    render(<MfaSettings />, { wrapper: createWrapper() });
    await waitFor(() => expect(mockMfaApi.getStatus).toHaveBeenCalled());

    expect(await screen.findByText("Active Laptop")).toBeTruthy();
    expect(screen.queryByText("Old Phone")).toBeNull();
    expect(screen.getByText(/Trusted Devices \(1\)/)).toBeTruthy();
  });

  it("handles devices with missing name or last_used_at", async () => {
    mockMfaApi.getStatus.mockResolvedValue({ mfa_enabled: true });
    mockMfaApi.getTrustedDevices.mockResolvedValue([
      { id: "dev-1", device_name: null, last_used_at: null, is_expired: false },
    ]);

    render(<MfaSettings />, { wrapper: createWrapper() });

    expect(await screen.findByText("Unknown device")).toBeTruthy();
    expect(screen.getByText(/Last used: Never/)).toBeTruthy();
  });

  it("shows generic error message when detail is missing", async () => {
    mockMfaApi.setup.mockRejectedValue(new Error("Generic error"));
    const user = userEvent.setup();
    render(<MfaSettings />, { wrapper: createWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /enable two-factor/i }),
    );
    expect(await screen.findByText("Failed to start MFA setup")).toBeTruthy();
  });

  it("shows generic error message when detail is missing during verify/disable", async () => {
    // 1. Verify generic error
    mockMfaApi.verifySetup.mockRejectedValue(new Error("Verify fail"));
    const user = userEvent.setup();
    render(<MfaSettings />, { wrapper: createWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /enable two-factor/i }),
    );
    await user.type(screen.getByLabelText(/enter code/i), "123456");
    await user.click(screen.getByRole("button", { name: /enable mfa/i }));
    expect(await screen.findByText("Invalid code")).toBeTruthy();

    // 2. Disable generic error
    mockMfaApi.getStatus.mockResolvedValue({ mfa_enabled: true });
    mockMfaApi.disable.mockRejectedValue(new Error("Disable fail"));
    render(<MfaSettings />, { wrapper: createWrapper() });

    await user.click(await screen.findByRole("button", { name: /disable/i }));
    await user.type(screen.getByLabelText("Password"), "pass");
    await user.click(screen.getByRole("button", { name: /disable mfa/i }));
    expect(await screen.findByText("Failed to disable MFA")).toBeTruthy();
  });

  it("renders device with last_used_at date", async () => {
    mockMfaApi.getStatus.mockResolvedValue({ mfa_enabled: true });
    mockMfaApi.getTrustedDevices.mockResolvedValue([
      {
        id: "dev-1",
        device_name: "Laptop",
        last_used_at: "2023-01-01T12:00:00Z",
        is_expired: false,
      },
    ]);

    render(<MfaSettings />, { wrapper: createWrapper() });
    expect(await screen.findByText(/Last used:/)).toBeTruthy();
    expect(screen.queryByText("Never")).toBeNull();
  });
});
