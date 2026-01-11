/** @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { LoginForm } from "@/features/auth/components/LoginForm";
import { authApi } from "@/features/auth/api/auth";
import { useAuthStore } from "@/store/authStore";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/lib/apiClient";

expect.extend(matchers);

// Mock dependencies
vi.mock("@/features/auth/api/auth", () => ({
  authApi: {
    login: vi.fn(),
    getMe: vi.fn(),
  },
}));

vi.mock("@/lib/apiClient", () => ({
  api: {
    post: vi.fn(),
  },
}));

// Mock localStorage
const localStorageMock = (function () {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value.toString();
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();
Object.defineProperty(window, "localStorage", { value: localStorageMock });

// Mock ResizeObserver for Radix UI components
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Setup QueryClient
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
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

describe("LoginForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
    useAuthStore.getState().logout();
    localStorage.clear();
  });

  it("renders email step initially", () => {
    renderLoginForm();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /next/i })).toBeInTheDocument();
  });

  it("validates empty email on next", async () => {
    renderLoginForm();
    // Use fireEvent.submit to bypass HTML5 'required' attribute validation which blocks the submit handler
    const form = screen.getByLabelText(/email/i).closest("form");
    if (form) fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText(/please enter your email/i)).toBeInTheDocument();
    });
  });

  it("validates invalid email format", async () => {
    const user = userEvent.setup();
    renderLoginForm();
    const emailInput = screen.getByLabelText(/email/i);
    await user.type(emailInput, "invalid-email");
    // Bypass HTML5 validation to test custom regex logic
    const form = screen.getByLabelText(/email/i).closest("form");
    if (form) fireEvent.submit(form);

    await waitFor(() => {
      expect(
        screen.getByText(/please enter a valid email address/i),
      ).toBeInTheDocument();
    });
  });

  it("transitions to password step on valid email", async () => {
    const user = userEvent.setup();
    renderLoginForm();
    const emailInput = screen.getByLabelText(/email/i);
    await user.type(emailInput, "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /sign in/i }),
      ).toBeInTheDocument();
      // Email should be displayed as text
      expect(screen.getByText("test@example.com")).toBeInTheDocument();
    });
  });

  it("allows going back to email step", async () => {
    const user = userEvent.setup();
    renderLoginForm();
    // Go to step 2
    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /back/i })).toBeInTheDocument();
    });

    // Go back
    await user.click(screen.getByRole("button", { name: /back/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
      expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    });
  });

  it("submits login with email and password", async () => {
    const user = userEvent.setup();
    const mockLogin = vi.mocked(authApi.login).mockResolvedValue({
      access_token: "fake-token",
      token_type: "bearer",
    });
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: "123",
      email: "test@example.com",
      role: "user",
      preferences: {},
    } as any);

    renderLoginForm();

    // Step 1
    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));

    // Step 2
    await waitFor(() => {
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      // Check the first argument of the first call
      expect(mockLogin.mock.calls[0][0]).toEqual({
        username: "test@example.com",
        password: "password123",
      });
    });
  });

  it("handles login errors correctly", async () => {
    const user = userEvent.setup();
    const mockLogin = vi.mocked(authApi.login);

    const errorCases = [
      { code: "LOGIN_BAD_CREDENTIALS", msg: "Invalid email or password." },
      {
        code: "LOGIN_ACCOUNT_SUSPENDED",
        msg: "Account suspended. Please contact support.",
      },
      {
        code: "LOGIN_USER_INACTIVE",
        msg: "This account has been deactivated.",
      },
      { code: "Some locked message", msg: "Some locked message" }, // Special handling for 'locked' string
      {
        code: "Rate limit reached",
        msg: "Too many attempts. Please wait a moment and try again.",
      }, // Special handling for 'Rate limit'
      { code: "Unknown Error", msg: "Unknown Error" }, // Fallback to detail string
      { code: undefined, msg: "Login failed. Please try again." }, // Fallback default
    ];

    for (const { code, msg } of errorCases) {
      mockLogin.mockRejectedValueOnce({
        response: { data: { detail: code } },
      });

      renderLoginForm();

      // Navigate to password step
      await user.type(screen.getByLabelText(/email/i), "test@example.com");
      await user.click(screen.getByRole("button", { name: /next/i }));

      await waitFor(() => screen.getByLabelText(/password/i));

      await user.type(screen.getByLabelText(/password/i), "password");
      await user.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(screen.getByText(msg)).toBeInTheDocument();
      });

      // Cleanup for next iteration
      vi.clearAllMocks();
      queryClient.clear();
      // Need to unmount to reset internal component state (step)
      document.body.innerHTML = "";
    }
  });

  it("handles handleLoginSuccess failure", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "fake-token",
      token_type: "bearer",
    });
    // getMe throws error
    vi.mocked(authApi.getMe).mockRejectedValue(new Error("Fetch failed"));

    renderLoginForm();

    // Step 1
    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));

    // Step 2
    await waitFor(() => screen.getByLabelText(/password/i));
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Failed to fetch user profile."),
      ).toBeInTheDocument();
    });
  });

  it("handles admin MFA setup required flag", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "fake-token",
      token_type: "bearer",
      // @ts-ignore - simulating extra field from API
      mfa_setup_required: true,
    });
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: "123",
      email: "test@example.com",
      role: "admin",
      preferences: {},
    } as any);

    renderLoginForm();

    // Perform Login
    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => screen.getByLabelText(/password/i));
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(localStorage.setItem).toHaveBeenCalledWith(
        "mfa_setup_required",
        "true",
      );
    });
  });

  it("handles standard login success clears mfa flag", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "fake-token",
      token_type: "bearer",
      // mfa_setup_required not present or false
    });
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: "123",
      email: "test@example.com",
      role: "user",
      preferences: {},
    } as any);

    renderLoginForm();

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => screen.getByLabelText(/password/i));
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(localStorage.removeItem).toHaveBeenCalledWith(
        "mfa_setup_required",
      );
    });
  });

  it("handles MFA required flow and verification", async () => {
    const user = userEvent.setup();
    // 1. Login returns requires_mfa
    vi.mocked(authApi.login).mockResolvedValue({
      requires_mfa: true,
    });
    // 2. MFA Verify returns token
    vi.mocked(api.post).mockResolvedValue({
      data: { access_token: "mfa-token" },
    });
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: "123",
      email: "test@example.com",
      role: "user",
      preferences: {},
    } as any);

    renderLoginForm();

    // Login Step
    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => screen.getByLabelText(/password/i));
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    // Verify MFA Form Appears
    await waitFor(() => {
      expect(screen.getByText("Two-Factor Authentication")).toBeInTheDocument();
      expect(screen.getByLabelText("Verification Code")).toBeInTheDocument();
    });

    // Enter Code
    await user.type(screen.getByLabelText("Verification Code"), "123456");
    await user.click(screen.getByLabelText("Trust this device for 30 days")); // toggle trust
    await user.click(screen.getByRole("button", { name: /verify/i }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/v1/auth/mfa/verify", {
        code: "123456",
        trust_device: true,
      });
      // Should eventually fetch user
      expect(authApi.getMe).toHaveBeenCalled();
    });
  });

  it("handles MFA verification errors and back navigation", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.login).mockResolvedValue({
      requires_mfa: true,
    });
    vi.mocked(api.post).mockRejectedValue({
      response: { data: { detail: "Invalid verification code." } },
    });

    renderLoginForm();

    // Reach MFA screen
    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => screen.getByLabelText(/password/i));
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText("Two-Factor Authentication")).toBeInTheDocument();
    });

    // Try bad code
    await user.type(screen.getByLabelText("Verification Code"), "000000");
    await user.click(screen.getByRole("button", { name: /verify/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Invalid verification code."),
      ).toBeInTheDocument();
    });

    // Test Back button
    await user.click(screen.getByRole("button", { name: /back to login/i }));

    await waitFor(() => {
      expect(
        screen.queryByText("Two-Factor Authentication"),
      ).not.toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });
  });

  it("handles MFA session expired error", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.login).mockResolvedValue({
      requires_mfa: true,
    });
    vi.mocked(api.post).mockRejectedValue({
      response: {
        data: { detail: "MFA session not found. Please start login again." },
      },
    });

    renderLoginForm();

    // Reach MFA screen
    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => screen.getByLabelText(/password/i));
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => screen.getByText("Two-Factor Authentication"));

    // Submit code
    await user.type(screen.getByLabelText("Verification Code"), "123456");
    await user.click(screen.getByRole("button", { name: /verify/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Session expired. Please login again."),
      ).toBeInTheDocument();
      // Implementation sets mfaRequired=false on session expiry error
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });
  });

  it("handles generic MFA verification error", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.login).mockResolvedValue({
      requires_mfa: true,
    });
    // Mock error without detail to trigger fallback
    vi.mocked(api.post).mockRejectedValue({
      response: { data: {} },
    });

    renderLoginForm();

    // Reach MFA screen
    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => screen.getByLabelText(/password/i));
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => screen.getByText("Two-Factor Authentication"));

    // Submit code
    await user.type(screen.getByLabelText("Verification Code"), "123456");
    await user.click(screen.getByRole("button", { name: /verify/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Invalid verification code."),
      ).toBeInTheDocument();
    });
  });

  it("covers null-coalescing branches in handleLoginSuccess", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "fake-token",
    });
    // Return user with missing optional fields
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: "123",
      email: "test@example.com",
      role: null,
      api_key_preview: null,
      is_superuser: null,
      force_password_change: null,
      preferences: {},
    } as any);

    renderLoginForm();

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => screen.getByLabelText(/password/i));
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(authApi.getMe).toHaveBeenCalled();
    });
  });

  it("covers implicit else branch in login onSuccess", async () => {
    const user = userEvent.setup();
    // Return response with no actionable fields
    vi.mocked(authApi.login).mockResolvedValue({});

    renderLoginForm();

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => screen.getByLabelText(/password/i));
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalled();
      // Nothing should happen (no navigate, no MFA)
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });
  });
});
