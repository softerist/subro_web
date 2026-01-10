/** @vitest-environment jsdom */
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UsersPage } from "../features/admin/pages/UsersPage";
import { useAuthStore, type AuthState } from "@/store/authStore";
import { toast } from "sonner";
import { adminApi } from "../features/admin/api/admin";

vi.mock("../features/admin/components/UsersTable", () => ({
  UsersTable: () => <div data-testid="users-table">Users Table</div>,
}));

vi.mock("../features/admin/components/CreateUserDialog", () => ({
  CreateUserDialog: () => (
    <div data-testid="create-user-dialog">Create User Dialog</div>
  ),
}));

vi.mock("../features/admin/api/admin", () => ({
  adminApi: {
    getUsers: vi.fn(),
    getOpenSignup: vi.fn(),
    setOpenSignup: vi.fn(),
  },
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: any) => children,
  TooltipTrigger: ({ children }: any) => children,
  TooltipContent: ({ children }: any) => children,
  TooltipProvider: ({ children }: any) => children,
}));

describe("UsersPage", () => {
  let queryClient: QueryClient;

  const createWrapper = () => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    return ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };

  const mockAuthState = (isSuperuser: boolean) => {
    vi.mocked(useAuthStore).mockImplementation(
      (selector: (state: AuthState) => unknown) =>
        selector({
          user: {
            id: "1",
            email: "user@example.com",
            role: "admin",
            is_superuser: isSuperuser,
          },
          accessToken: "mock-token",
          isAuthenticated: true,
          setAccessToken: vi.fn(),
          setUser: vi.fn(),
          login: vi.fn(),
          logout: vi.fn(),
        } as AuthState),
    );
  };

  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.mocked(adminApi.getUsers).mockResolvedValue([]);
    vi.mocked(adminApi.getOpenSignup).mockResolvedValue(true);
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("renders the page and shows Open Signup toggle for superusers", async () => {
    mockAuthState(true);
    render(<UsersPage />, { wrapper: createWrapper() });

    expect(screen.getAllByText("User Management").length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /open signup/i })).toBeTruthy();
    });
  });

  it("does not show Open Signup toggle for non-superusers", async () => {
    mockAuthState(false);
    render(<UsersPage />, { wrapper: createWrapper() });

    expect(screen.getAllByText("User Management").length).toBeGreaterThan(0);
    expect(screen.queryByText("Open Signup")).toBeNull();
  });

  it("displays error toast when fetching users fails", async () => {
    mockAuthState(true);
    vi.mocked(adminApi.getUsers).mockRejectedValue(
      new Error("Failed to fetch"),
    );

    render(<UsersPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining("Failed to load users"),
      );
    });
  });

  it("toggles open signup successfully", async () => {
    const user = userEvent.setup();
    mockAuthState(true);
    vi.mocked(adminApi.getOpenSignup).mockResolvedValue(true);
    vi.mocked(adminApi.setOpenSignup).mockImplementation(
      async (val: boolean) => val,
    );

    render(<UsersPage />, { wrapper: createWrapper() });

    const switchEl = await screen.findByRole("switch", {
      name: /open signup/i,
    });

    await waitFor(() =>
      expect(switchEl.getAttribute("aria-checked")).toBe("true"),
    );

    await user.click(switchEl);

    await waitFor(() => {
      expect(adminApi.setOpenSignup).toHaveBeenCalledWith(
        false,
        expect.anything(),
      );
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining("Open signup disabled"),
      );
    });

    await user.click(switchEl);
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining("Open signup enabled"),
      );
    });
  });

  it("shows error toast when toggling open signup fails", async () => {
    const user = userEvent.setup();
    mockAuthState(true);
    vi.mocked(adminApi.getOpenSignup).mockResolvedValue(true);
    vi.mocked(adminApi.setOpenSignup).mockRejectedValue(
      new Error("Unlock failed"),
    );

    render(<UsersPage />, { wrapper: createWrapper() });

    const switchEl = await screen.findByRole("switch", {
      name: /open signup/i,
    });

    await user.click(switchEl);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining("Failed to update"),
      );
    });
  });
});
