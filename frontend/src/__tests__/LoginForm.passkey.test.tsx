// frontend/src/__tests__/LoginForm.passkey.test.tsx
/** @vitest-environment jsdom */
/**
 * Tests for LoginForm passkey integration.
 * Tests the email-first passkey flow with security-hardened error handling.
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
    </QueryClientProvider>,
  );
};

// Helper to navigate to password step
const goToPasswordStep = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByLabelText(/email/i), "test@example.com");
  await user.click(screen.getByRole("button", { name: /next/i }));
  await waitFor(() => {
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });
};

describe("LoginForm - Passkey Integration (Email-First Flow)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
  });

  describe("Passkey button placement", () => {
    it("hides passkey button on email step (email-first flow)", () => {
      vi.mocked(isWebAuthnSupported).mockReturnValue(true);

      renderLoginForm();

      // Email step - passkey button should NOT be visible (email-first flow)
      expect(
        screen.queryByText(/Sign in with Passkey/i),
      ).not.toBeInTheDocument();
    });

    it("shows passkey button on password step when WebAuthn is supported", async () => {
      const user = userEvent.setup();
      vi.mocked(isWebAuthnSupported).mockReturnValue(true);

      renderLoginForm();

      // Navigate to password step
      await goToPasswordStep(user);

      // Password step - passkey button should be visible
      expect(screen.getByText(/Sign in with Passkey/i)).toBeInTheDocument();
    });

    it("hides passkey button when WebAuthn is not supported", async () => {
      const user = userEvent.setup();
      vi.mocked(isWebAuthnSupported).mockReturnValue(false);

      renderLoginForm();

      // Navigate to password step
      await user.type(screen.getByLabelText(/email/i), "test@example.com");
      await user.click(screen.getByRole("button", { name: /next/i }));

      await waitFor(() => {
        expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      });

      // Passkey button should not be visible
      expect(
        screen.queryByText(/Sign in with Passkey/i),
      ).not.toBeInTheDocument();
    });
  });

  describe("Passkey authentication", () => {
    it("successfully authenticates with passkey", async () => {
      const user = userEvent.setup();
      vi.mocked(isWebAuthnSupported).mockReturnValue(true);

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
      await goToPasswordStep(user);

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
        () => new Promise(() => {}),
      );

      renderLoginForm();
      await goToPasswordStep(user);

      await user.click(screen.getByText(/Sign in with Passkey/i));

      // Button should show loading and be disabled
      await waitFor(() => {
        const button = screen.getByRole("button", {
          name: /Sign in with Passkey/i,
        });
        expect(button).toBeDisabled();
      });
    });
  });

  describe("Security: Silent error handling", () => {
    it("SECURITY: silently handles user cancellation (no error shown)", async () => {
      const user = userEvent.setup();
      vi.mocked(isWebAuthnSupported).mockReturnValue(true);

      // User cancelled the passkey prompt
      vi.mocked(passkeyApi.authenticate).mockRejectedValue(
        new Error("Authentication was cancelled or not allowed."),
      );

      renderLoginForm();
      await goToPasswordStep(user);

      await user.click(screen.getByText(/Sign in with Passkey/i));

      // Should NOT show any error - silent fallback to password
      await waitFor(() => {
        expect(screen.queryByText(/cancelled/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
      });
    });

    it("SECURITY: shows generic error for other failures (no passkey info leaked)", async () => {
      const user = userEvent.setup();
      vi.mocked(isWebAuthnSupported).mockReturnValue(true);

      // Generic failure (could be "no passkeys" but we don't reveal that)
      vi.mocked(passkeyApi.authenticate).mockRejectedValue(
        new Error("Some internal error"),
      );

      renderLoginForm();
      await goToPasswordStep(user);

      await user.click(screen.getByText(/Sign in with Passkey/i));

      // Should show generic message, not specific error
      await waitFor(() => {
        expect(
          screen.getByText(
            "Passkey sign-in unavailable. Please use your password.",
          ),
        ).toBeInTheDocument();
      });
    });

    it("SECURITY: handles NotAllowedError silently", async () => {
      const user = userEvent.setup();
      vi.mocked(isWebAuthnSupported).mockReturnValue(true);

      vi.mocked(passkeyApi.authenticate).mockRejectedValue(
        new Error("NotAllowedError: User denied"),
      );

      renderLoginForm();
      await goToPasswordStep(user);

      await user.click(screen.getByText(/Sign in with Passkey/i));

      // Should NOT show any error
      await waitFor(() => {
        expect(screen.queryByText(/NotAllowedError/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/denied/i)).not.toBeInTheDocument();
      });
    });

    it("SECURITY: handles error with no message property (|| fallback)", async () => {
      const user = userEvent.setup();
      vi.mocked(isWebAuthnSupported).mockReturnValue(true);

      // Error object with no message property (covers || "" fallback on line 59)
      vi.mocked(passkeyApi.authenticate).mockRejectedValue({});

      renderLoginForm();
      await goToPasswordStep(user);

      await user.click(screen.getByText(/Sign in with Passkey/i));

      // Should show generic message when error has no message
      await waitFor(() => {
        expect(
          screen.getByText(
            "Passkey sign-in unavailable. Please use your password.",
          ),
        ).toBeInTheDocument();
      });
    });
  });

  describe("Button states", () => {
    it("disables sign in button during passkey authentication", async () => {
      const user = userEvent.setup();
      vi.mocked(isWebAuthnSupported).mockReturnValue(true);

      vi.mocked(passkeyApi.authenticate).mockImplementation(
        () => new Promise(() => {}),
      );

      renderLoginForm();
      await goToPasswordStep(user);

      await user.click(screen.getByText(/Sign in with Passkey/i));

      await waitFor(() => {
        const passkeyButton = screen.getByRole("button", {
          name: /Sign in with Passkey/i,
        });
        const signInButton = screen.getByRole("button", { name: /^Sign In$/i });

        expect(passkeyButton).toBeDisabled();
        expect(signInButton).toBeDisabled();
      });
    });
  });
});
