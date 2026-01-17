// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
  within,
  act,
} from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { toast } from "sonner";
import { UsersTable } from "../features/admin/components/UsersTable";
import { User } from "../features/admin/types";
import { adminApi } from "../features/admin/api/admin";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "../store/authStore";

// Polyfill ResizeObserver for Radix UI
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock dependencies
vi.mock("../features/admin/api/admin", () => ({
  adminApi: {
    deleteUser: vi.fn(),
    updateUser: vi.fn(),
    getUsers: vi.fn(),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("../features/admin/components/EditUserDialog", () => ({
  EditUserDialog: ({ open, onOpenChange }: any) => {
    if (!open) return null;
    return (
      <div role="dialog" aria-label="Edit User Dialog">
        <h2>Edit User</h2>
        <button onClick={() => onOpenChange(false)}>Cancel</button>
      </div>
    );
  },
}));

// Mock ConfirmDialog to capture handler for coverage
vi.mock("@/components/common/ConfirmDialog", () => ({
  ConfirmDialog: (props: any) => {
    (global as any).triggerExecuteDelete = props.onConfirm;
    if (props.open && props.onOpenChange)
      (global as any).lastOnOpenChange = props.onOpenChange;
    if (!props.open) return null;
    return (
      <div role="dialog" aria-labelledby="confirm-title">
        <h2 id="confirm-title">{props.title}</h2>
        <p>{props.description}</p>
        <button onClick={props.onConfirm}>
          {props.confirmLabel || "Confirm"}
        </button>
        <button onClick={() => props.onOpenChange(false)}>Cancel</button>
      </div>
    );
  },
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open, onOpenChange }: any) => {
    const force = (global as any).forceRenderForCoverage;
    if (open && onOpenChange) (global as any).lastOnOpenChange = onOpenChange;

    if (!open && !force) return null;
    return (
      <div
        data-testid="dialog-root"
        style={{ display: open ? "block" : "none" }}
        onKeyDown={(e) => {
          if (e.key === "Escape" && onOpenChange) onOpenChange(false);
        }}
      >
        {children}
      </div>
    );
  },
  DialogContent: ({ children }: any) => {
    return (
      <div role="dialog" aria-label="Reset Password">
        {children}
      </div>
    );
  },
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogDescription: ({ children }: any) => <div>{children}</div>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
}));

vi.mock("react-hook-form", async () => {
  const actual =
    await vi.importActual<typeof import("react-hook-form")>("react-hook-form");
  return {
    ...actual,
    useForm: (args: any) => {
      const form = actual.useForm(args);
      const originalHandleSubmit = form.handleSubmit;
      form.handleSubmit = (onValid: any, onInvalid: any) => {
        (global as any).triggerExecuteReset = onValid;
        return originalHandleSubmit(onValid, onInvalid);
      };
      return form;
    },
  };
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

const mockUsers: User[] = [
  {
    id: "user-1",
    email: "user1@example.com",
    first_name: "John",
    last_name: "Doe",
    role: "standard",
    is_active: true,
    is_superuser: false,
    is_verified: true,
    created_at: "2023-01-01",
    updated_at: "2023-01-01",
    mfa_enabled: false,
  },
  {
    id: "admin-1",
    email: "admin@example.com",
    first_name: "Admin",
    last_name: "User",
    role: "admin",
    is_active: true,
    is_superuser: true,
    is_verified: true,
    created_at: "2023-01-01",
    updated_at: "2023-01-01",
    mfa_enabled: true,
  },
];

const renderTable = (users = mockUsers, isLoading = false) => {
  return render(
    <QueryClientProvider client={queryClient}>
      <UsersTable users={users} isLoading={isLoading} />
    </QueryClientProvider>,
  );
};

describe("UsersTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (global as any).forceRenderForCoverage = false;
    (global as any).lastOnOpenChange = undefined;
    (global as any).triggerExecuteReset = undefined;
    (adminApi.deleteUser as any).mockResolvedValue({});
    (adminApi.updateUser as any).mockResolvedValue({});
    (adminApi.getUsers as any).mockResolvedValue(mockUsers);
    useAuthStore.setState({ user: { ...mockUsers[1] } });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders loading state", () => {
    renderTable([], true);
    expect(screen.queryByText("user1@example.com")).not.toBeInTheDocument();
  });

  it("renders users list", () => {
    renderTable();
    expect(screen.getByText("user1@example.com")).toBeInTheDocument();
    expect(screen.getByText("admin@example.com")).toBeInTheDocument();
    expect(screen.getByText("Superuser")).toBeInTheDocument();
  });

  it("shows placeholder name and inactive badge when data missing", () => {
    const nameless = {
      ...mockUsers[0],
      first_name: "",
      last_name: "",
      is_active: false,
    };
    renderTable([nameless]);
    expect(screen.getByText(/Not set/i)).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("opens edit dialog on click", () => {
    renderTable();
    const editButtons = screen.getAllByTitle("Edit User");
    fireEvent.click(editButtons[0]);
    expect(screen.getByText("Edit User")).toBeInTheDocument();
  });

  it("disables edit for superusers if current user is not superuser", () => {
    useAuthStore.setState({
      user: { ...mockUsers[0], role: "admin", is_superuser: false } as any,
    });
    renderTable();
    const rows = screen.getAllByRole("row");
    const superuserRow = rows.find((row) =>
      row.textContent?.includes("admin@example.com"),
    );
    const editBtn = superuserRow?.querySelector(
      "button[title='Cannot modify Superuser']",
    );
    expect(editBtn).toBeDisabled();
  });

  it("shows empty state", () => {
    renderTable([]);
    expect(screen.getByText("No users found.")).toBeInTheDocument();
  });

  it("opens delete confirmation and deletes user", async () => {
    renderTable();
    const deleteBtns = screen.getAllByTitle("Delete User");
    fireEvent.click(deleteBtns[0]);
    expect(
      screen.getByText(/Are you sure you want to delete/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText("Delete"));
    await waitFor(() =>
      expect(adminApi.deleteUser).toHaveBeenCalledWith(
        "user-1",
        expect.anything(),
      ),
    );
  });

  it("toggles user active status", async () => {
    renderTable();
    const toggleBtn = screen.getAllByTitle("Deactivate")[0];
    fireEvent.click(toggleBtn);
    await waitFor(() =>
      expect(adminApi.updateUser).toHaveBeenCalledWith("user-1", {
        is_active: false,
      }),
    );
  });

  it("shows toast on toggle failure", async () => {
    (adminApi.updateUser as any).mockRejectedValue(new Error("fail"));
    renderTable();
    fireEvent.click(screen.getAllByTitle("Deactivate")[0]);
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining("Failed to update user: fail"),
      ),
    );
  });

  it("opens reset password dialog and submits form", async () => {
    renderTable();
    fireEvent.click(screen.getAllByTitle("Reset Password")[0]);
    const dialog = screen.getByRole("dialog", { name: "Reset Password" });
    fireEvent.change(within(dialog).getByLabelText("New Password"), {
      target: { value: "newpass123" },
    });
    fireEvent.change(within(dialog).getByLabelText("Confirm Password"), {
      target: { value: "newpass123" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Reset Password" }),
    );
    await waitFor(() =>
      expect(adminApi.updateUser).toHaveBeenCalledWith(
        "user-1",
        expect.anything(),
      ),
    );
  });

  it("respects force password change and disable MFA toggles", async () => {
    renderTable();
    fireEvent.click(screen.getAllByTitle("Reset Password")[0]);
    const dialog = screen.getByRole("dialog", { name: "Reset Password" });
    fireEvent.change(within(dialog).getByLabelText("New Password"), {
      target: { value: "newpass123" },
    });
    fireEvent.change(within(dialog).getByLabelText("Confirm Password"), {
      target: { value: "newpass123" },
    });
    const checkboxes = within(dialog).getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]); // forcePasswordChange -> false
    fireEvent.click(checkboxes[1]); // disableMFA -> true
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Reset Password" }),
    );
    await waitFor(() =>
      expect(adminApi.updateUser).toHaveBeenCalledWith(
        "user-1",
        expect.objectContaining({ mfa_enabled: false }),
      ),
    );
  });

  it("shows toast on password reset failure", async () => {
    (adminApi.updateUser as any).mockRejectedValue(new Error("reset-fail"));
    renderTable();
    fireEvent.click(screen.getAllByTitle("Reset Password")[0]);
    const dialog = screen.getByRole("dialog", { name: "Reset Password" });
    fireEvent.change(within(dialog).getByLabelText("New Password"), {
      target: { value: "validpass123" },
    });
    fireEvent.change(within(dialog).getByLabelText("Confirm Password"), {
      target: { value: "validpass123" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Reset Password" }),
    );
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining("Failed to reset password: reset-fail"),
      ),
    );
  });

  it("shows delete error toast on failure", async () => {
    (adminApi.deleteUser as any).mockRejectedValue(new Error("boom"));
    renderTable();
    fireEvent.click(screen.getAllByTitle("Delete User")[0]);
    fireEvent.click(screen.getByText("Delete"));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining("Failed to delete user: boom"),
      ),
    );
  });

  it("handles dialog cancellation and closure", async () => {
    renderTable();
    fireEvent.click(screen.getAllByTitle("Delete User")[0]);
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() =>
      expect(screen.queryByText(/Are you sure/)).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getAllByTitle("Reset Password")[0]);
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Reset Password" }),
      ).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getAllByTitle("Edit User")[0]);
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() =>
      expect(screen.queryByText("Edit User")).not.toBeInTheDocument(),
    );
  });

  it("handles partial member names correctly", () => {
    const users: User[] = [
      { ...mockUsers[0], first_name: "OnlyFirst", last_name: "" },
      { ...mockUsers[1], first_name: "", last_name: "OnlyLast" },
    ];
    renderTable(users);
    expect(screen.getByText("OnlyFirst")).toBeInTheDocument();
    expect(screen.getByText("OnlyLast")).toBeInTheDocument();
  });

  it("handles mutation loading state for a different user", async () => {
    (adminApi.deleteUser as any).mockReturnValue(new Promise(() => {}));
    renderTable();
    fireEvent.click(screen.getAllByTitle("Delete User")[0]);
    fireEvent.click(screen.getByText("Delete"));
    await waitFor(() => {
      const rows = screen.getAllByRole("row");
      const user1Row = rows.find((r) =>
        r.textContent?.includes("user1@example.com"),
      );
      expect(user1Row!.querySelector(".animate-spin")).toBeInTheDocument();
    });
  });

  it("handles user with missing role and shows standard", () => {
    const noRoleUser = { ...mockUsers[0], role: "" as any };
    renderTable([noRoleUser]);
    expect(screen.getByText("standard")).toBeInTheDocument();
  });

  it("allows superuser to edit another superuser", async () => {
    useAuthStore.setState({
      user: { id: "admin-1", role: "superuser", is_superuser: true } as any,
    });
    const superuser2 = {
      ...mockUsers[0],
      id: "super-2",
      role: "admin" as const,
      is_superuser: true,
      email: "super2@example.com",
    };
    renderTable([superuser2]);
    const editBtn = screen.getByTitle("Edit User");
    expect(editBtn).not.toBeDisabled();
    fireEvent.click(editBtn);
    expect(
      screen.getByRole("dialog", { name: "Edit User Dialog" }),
    ).toBeInTheDocument();
  });

  it("handles null currentUser gracefully", () => {
    useAuthStore.setState({ user: null });
    renderTable();
    expect(screen.getByText("user1@example.com")).toBeInTheDocument();
  });

  it("covers branch edge cases for null state handlers", async () => {
    (global as any).forceRenderForCoverage = true;
    (global as any).triggerExecuteReset = undefined; // reset
    renderTable();

    if ((global as any).triggerExecuteDelete) {
      await (global as any).triggerExecuteDelete();
    }
    expect(adminApi.deleteUser).not.toHaveBeenCalled();

    if ((global as any).triggerExecuteReset) {
      (global as any).triggerExecuteReset({
        password: "1",
        confirmPassword: "1",
        forcePasswordChange: true,
        disableMFA: false,
      });
    }
    expect(adminApi.updateUser).not.toHaveBeenCalled();
    (global as any).forceRenderForCoverage = false;
  });

  it("covers onOpenChange for Reset Password dialog and Delete Dialog", async () => {
    renderTable();
    // 1. Reset Password Dialog
    fireEvent.click(screen.getAllByTitle("Reset Password")[0]);
    const resetOpenChange = (global as any).lastOnOpenChange;
    expect(resetOpenChange).toBeDefined();
    await act(async () => {
      resetOpenChange(false);
    });
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Reset Password" }),
      ).not.toBeInTheDocument(),
    );

    // 2. Delete Dialog
    fireEvent.click(screen.getAllByTitle("Delete User")[0]);
    const deleteOpenChange = (global as any).lastOnOpenChange;
    expect(deleteOpenChange).toBeDefined();
    await act(async () => {
      deleteOpenChange(false);
    });
    await waitFor(() =>
      expect(
        screen.queryByText(/Are you sure you want to delete/),
      ).not.toBeInTheDocument(),
    );
  });
});
