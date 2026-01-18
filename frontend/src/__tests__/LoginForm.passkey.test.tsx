// frontend/src/__tests__/LoginForm.passkey.test.tsx
/** @vitest-environment jsdom */
/**
 * Additional tests for LoginForm passkey integration.
 * These supplement the existing LoginForm.test.tsx with passkey-specific test cases.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { LoginForm } from "@/features/auth/components/LoginForm";
import { authApi } from "@/features/auth/api/auth";
import { passkeyApi, isWebAuthnSupported } from "@/features/auth/api/passkey";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

expect.extend(matchers);

// Mock dependencies
vi.mock("@/features/auth/api/auth", () => ({
  authApi: {
    login: vi.fn(),
    getMe: vi.fn(),
  },
}));

vi.mock("@/features/auth/api/passkey");

vi.mock("@/lib/apiClient", () => ({
  api: {
    post: vi.fn(),
  },
}));

// Mock ResizeObserver for Radix UI
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

const renderLoginForm = () => {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <LoginForm />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

describe("LoginForm - Passkey Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
  });

  it("shows passkey button when WebAuthn is supported", () => {
    vi.mocked(isWebAuthnSupported).mockReturnValue(true);

    renderLoginForm();

    expect(screen.getByText(/Sign in with Passkey/i)).toBeInTheDocument();
  });

  it("hides passkey button when WebAuthn is not supported", () => {
    vi.mocked(isWebAuthnSupported).mockReturnValue(false);

    renderLoginForm();

    expect(screen.queryByText(/Sign in with Passkey/i)).not.toBeInTheDocument();
  });

  it("only shows passkey button on email step, not password step", async () => {
    const user = userEvent.setup();
    vi.mocked(isWebAuthnSupported).mockReturnValue(true);

    renderLoginForm();

    // Email step - should show passkey button
    expect(screen.getByText(/Sign in with Passkey/i)).toBeInTheDocument();

    // Go to password step
    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });

    // Password step - should not show passkey button
    expect(screen.queryByText(/Sign in with Passkey/i)).not.toBeInTheDocument();
  });

  it("successfully authenticates with passkey", async () => {
    const user = userEvent.setup();
    vi.mocked(isWebAuthnSupported).mockReturnValue(true);

    // Mock passkey authentication flow
    vi.mocked(passkeyApi.authenticate).mockResolvedValue({
      access_token: "passkey-token",
      token_type: "bearer",
    });

    vi.mocked(authApi.getMe).mockResolvedValue({
      id: "123",
      email: "test@example.com",
      role: "user",
      preferences: {},
    } as any);

    renderLoginForm();

    // Click passkey button
    await user.click(screen.getByText(/Sign in with Passkey/i));

    await waitFor(() => {
      expect(passkeyApi.authenticate).toHaveBeenCalled();
      expect(authApi.getMe).toHaveBeenCalled();
    });
  });

  it("shows loading state during passkey authentication", async () => {
    const user = userEvent.setup();
    vi.mocked(isWebAuthnSupported).mockReturnValue(true);

    // Make authentication hang
    vi.mocked(passkeyApi.authenticate).mockImplementation(
      () => new Promise(() => {})
    );

    renderLoginForm();

    await user.click(screen.getByText(/Sign in with Passkey/i));

    // Button should show loading
    await waitFor(() => {
      const button = screen.getByRole("button", { name: /Sign in with Passkey/i });
      expect(button).toBeDisabled();
    });
  });

  it("handles passkey authentication error with detail", async () => {
    const user = userEvent.setup();
    vi.mocked(isWebAuthnSupported).mockReturnValue(true);

    vi.mocked(passkeyApi.authenticate).mockRejectedValue({
      response: {
        data: { detail: "Passkey verification failed" },
      },
    });

    renderLoginForm();

    await user.click(screen.getByText(/Sign in with Passkey/i));

    await waitFor(() => {
      expect(screen.getByText("Passkey verification failed")).toBeInTheDocument();
    });
  });

  it("handles passkey authentication error without detail", async () => {
    const user = userEvent.setup();
    vi.mocked(isWebAuthnSupported).mockReturnValue(true);

    vi.mocked(passkeyApi.authenticate).mockRejectedValue(
      new Error("Network error")
    );

    renderLoginForm();

    await user.click(screen.getByText(/Sign in with Passkey/i));

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("handles passkey authentication with generic fallback error", async () => {
    const user = userEvent.setup();
    vi.mocked(isWebAuthnSupported).mockReturnValue(true);

    vi.mocked(passkeyApi.authenticate).mockRejectedValue({});

    renderLoginForm();

    await user.click(screen.getByText(/Sign in with Passkey/i));

    await waitFor(() => {
      expect(screen.getByText("Passkey authentication failed.")).toBeInTheDocument();
    });
  });

  it("disables regular login buttons during passkey authentication", async () => {
    const user = userEvent.setup();
    vi.mocked(isWebAuthnSupported).mockReturnValue(true);

    vi.mocked(passkeyApi.authenticate).mockImplementation(
      () => new Promise(() => {})
    );

    renderLoginForm();

    await user.click(screen.getByText(/Sign in with Passkey/i));

    await waitFor(() => {
      const nextButton = screen.getByRole("button", { name: /next/i });
      const passkeyButton = screen.getByRole("button", {
        name: /Sign in with Passkey/i,
      });

      expect(nextButton).toBeDisabled();
      expect(passkeyButton).toBeDisabled();
    });
  });
});
