// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Polyfill ResizeObserver for Radix UI
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
import { toast } from "sonner";
import { EditUserDialog } from "../features/admin/components/EditUserDialog";
import { adminApi } from "../features/admin/api/admin";
import { User } from "../features/admin/types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock the admin API
vi.mock("../features/admin/api/admin", () => ({
  adminApi: {
    updateUser: vi.fn(),
  },
}));

// Mock Sonner toast
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const updateUserMock = adminApi.updateUser as unknown as ReturnType<
  typeof vi.fn
>;

const mockUser: User = {
  id: "user-1",
  email: "test@example.com",
  first_name: "Test",
  last_name: "User",
  role: "standard",
  is_active: true,
  is_superuser: false,
  is_verified: true,
  created_at: "2023-01-01T00:00:00Z",
  updated_at: "2023-01-01T00:00:00Z",
  mfa_enabled: false,
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

const renderDialog = (open = true, user = mockUser) => {
  const onOpenChange = vi.fn();
  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <EditUserDialog open={open} onOpenChange={onOpenChange} user={user} />
      </QueryClientProvider>,
    ),
    onOpenChange,
    user: userEvent.setup(),
    onOpenChangeMock: onOpenChange,
  };
};

describe("EditUserDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
  });

  it("renders correctly with user data", () => {
    renderDialog();
    expect(screen.getByText("Edit User")).toBeInTheDocument();
    expect(screen.getByDisplayValue("test@example.com")).toBeInTheDocument();
  });

  it("updates user successfully", async () => {
    updateUserMock.mockResolvedValue({
      ...mockUser,
      role: "admin",
    });
    const { onOpenChangeMock, user } = renderDialog(true, { ...mockUser });

    // Wait for population
    const inputs = screen.getAllByDisplayValue("test@example.com");
    expect(inputs.length).toBeGreaterThan(0);

    // Toggle "Active Account" checkbox
    const activeCheckboxes = screen.getAllByTestId("active-checkbox");
    const activeCheckbox = activeCheckboxes[activeCheckboxes.length - 1];
    await user.click(activeCheckbox);

    const submitBtns = screen.getAllByText("Save Changes");
    const submitBtn = submitBtns[submitBtns.length - 1];
    await user.click(submitBtn);

    await waitFor(() => {
      expect(adminApi.updateUser).toHaveBeenCalledWith(
        "user-1",
        expect.objectContaining({
          is_active: false,
        }),
      );
    });

    expect(onOpenChangeMock).toHaveBeenCalledWith(false);
  });

  it("validates password mismatch", async () => {
    const { user } = renderDialog(true, { ...mockUser });

    // Wait for population
    const inputs = screen.getAllByDisplayValue("test@example.com");
    expect(inputs.length).toBeGreaterThan(0);

    // Fill password fields
    const passwordInputs = screen.getAllByTestId("new-password-input");
    const confirmInputs = screen.getAllByTestId("confirm-password-input");

    // Radix may render duplicates, grab the LAST one (active)
    const passwordInput = passwordInputs[passwordInputs.length - 1];
    const confirmInput = confirmInputs[confirmInputs.length - 1];

    await user.type(passwordInput, "password123");
    await user.type(confirmInput, "mismatch");

    expect(passwordInput).toHaveValue("password123");
    expect(confirmInput).toHaveValue("mismatch");

    const submitBtns = screen.getAllByText("Save Changes");
    const submitBtn = submitBtns[submitBtns.length - 1];
    await user.click(submitBtn);

    // Verify submission is blocked
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(adminApi.updateUser).not.toHaveBeenCalled();
  });

  it("sends password only if provided", async () => {
    updateUserMock.mockResolvedValue(mockUser);
    const { user } = renderDialog(true, { ...mockUser });

    // Wait for population
    const inputs = screen.getAllByDisplayValue("test@example.com");
    expect(inputs.length).toBeGreaterThan(0);

    // No password change
    const submitBtns = screen.getAllByText("Save Changes");
    const submitBtn = submitBtns[submitBtns.length - 1];
    await user.click(submitBtn);

    await waitFor(() => {
      // Assert password field is NOT in the call
      const callArgs = updateUserMock.mock.calls[0]?.[1] as {
        password?: string;
      };
      expect(callArgs.password).toBeUndefined();
    });
  });

  it("sends password if provided and valid", async () => {
    updateUserMock.mockResolvedValue(mockUser);
    const { user } = renderDialog(true, { ...mockUser });

    // Wait for population
    const inputs = screen.getAllByDisplayValue("test@example.com");
    expect(inputs.length).toBeGreaterThan(0);

    const passwordInputs = screen.getAllByTestId("new-password-input");
    const confirmInputs = screen.getAllByTestId("confirm-password-input");

    const passwordInput = passwordInputs[passwordInputs.length - 1];
    const confirmInput = confirmInputs[confirmInputs.length - 1];

    await user.type(passwordInput, "newpassword123");
    await user.type(confirmInput, "newpassword123");

    const submitBtns = screen.getAllByText("Save Changes");
    const submitBtn = submitBtns[submitBtns.length - 1];
    await user.click(submitBtn);

    await waitFor(() => {
      expect(adminApi.updateUser).toHaveBeenCalledWith(
        "user-1",
        expect.objectContaining({
          password: "newpassword123",
        }),
      );
    });
  });

  it("handles update error", async () => {
    updateUserMock.mockRejectedValue(new Error("API Error"));
    const { user } = renderDialog();

    const submitBtn = screen.getByText("Save Changes");
    await user.click(submitBtn);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining("Failed to update user: API Error"),
      );
    });
  });

  it("shows loading state when mutation is pending", async () => {
    let resolveMutation: (value: any) => void;
    const promise = new Promise((resolve) => {
      resolveMutation = resolve;
    });
    updateUserMock.mockReturnValue(promise);

    const { user } = renderDialog();
    const submitBtn = screen.getByText("Save Changes");
    await user.click(submitBtn);

    // Should show loader (line 442)
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
    expect(submitBtn).toBeDisabled();

    // Clean up
    resolveMutation!(mockUser);
  });

  it("calls onOpenChange(false) when clicking cancel", async () => {
    const { onOpenChangeMock, user } = renderDialog();

    const cancelBtn = screen.getByText("Cancel");
    await user.click(cancelBtn);

    expect(onOpenChangeMock).toHaveBeenCalledWith(false);
  });

  it("shows MFA enabled badge and warning when user has MFA", () => {
    renderDialog(true, { ...mockUser, mfa_enabled: true });

    expect(screen.getByText("Enabled")).toBeInTheDocument();
    expect(
      screen.getByText(/Unchecking will disable 2FA for this user/i),
    ).toBeInTheDocument();
  });

  it("handles initial null values in constructor-like phase and reset useEffect", () => {
    const userWithNulls: User = {
      ...mockUser,
      first_name: null,
      last_name: null,
      role: undefined as any,
      is_active: undefined as any,
      is_verified: undefined as any,
      force_password_change: undefined as any,
      mfa_enabled: undefined as any,
    };
    // Trigger initial state (lines 99-106)
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <EditUserDialog
          open={false}
          onOpenChange={vi.fn()}
          user={userWithNulls}
        />
      </QueryClientProvider>,
    );

    // Trigger reset useEffect branches (lines 117-123)
    rerender(
      <QueryClientProvider client={queryClient}>
        <EditUserDialog
          open={true}
          onOpenChange={vi.fn()}
          user={userWithNulls}
        />
      </QueryClientProvider>,
    );
  });

  it("handles user with null names in update payload", async () => {
    updateUserMock.mockResolvedValue(mockUser);
    const userWithNulls = { ...mockUser, first_name: null, last_name: null };
    const { user } = renderDialog(true, userWithNulls);

    const submitBtn = screen.getByText("Save Changes");
    await user.click(submitBtn);

    await waitFor(() => {
      expect(adminApi.updateUser).toHaveBeenCalledWith(
        "user-1",
        expect.objectContaining({
          first_name: null,
          last_name: null,
        }),
      );
    });
  });

  it("handles case where user is null initially", () => {
    // Trigger branch on line 99: email: user?.email || ""
    render(
      <QueryClientProvider client={queryClient}>
        <EditUserDialog open={true} onOpenChange={vi.fn()} user={null} />
      </QueryClientProvider>,
    );
    expect(
      screen.queryByDisplayValue("test@example.com"),
    ).not.toBeInTheDocument();
  });
});
