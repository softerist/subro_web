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

const renderDialog = (open = true, user = mockUser) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

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
});
