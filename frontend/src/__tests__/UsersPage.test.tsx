/** @vitest-environment jsdom */
import type { ReactNode } from "react";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UsersPage } from "../features/admin/pages/UsersPage";
import { useAuthStore } from "@/store/authStore";
import { adminApi } from "../features/admin/api/admin";

interface User {
  id: string;
  email: string;
  role: string | null;
  is_superuser: boolean;
}

interface AuthState {
  item?: string;
  user: User | null;
}

// Mock the components and API
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
    getUsers: vi.fn().mockResolvedValue([]),
    getOpenSignup: vi.fn(),
    setOpenSignup: vi.fn(),
  },
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

// Mock Tooltip components since they require a special setup in some environments
vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  TooltipContent: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  TooltipProvider: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
}));

describe("UsersPage", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the page and shows Open Signup toggle for superusers", async () => {
    // Arrange
    vi.mocked(useAuthStore).mockImplementation(
      (selector: (state: AuthState) => unknown) =>
        selector({
          user: {
            id: "1",
            email: "s@e.com",
            role: "admin",
            is_superuser: true,
          },
        }),
    );
    vi.mocked(adminApi.getOpenSignup).mockResolvedValue(true);

    // Act
    render(
      <QueryClientProvider client={queryClient}>
        <UsersPage />
      </QueryClientProvider>,
    );

    // Assert
    expect(screen.getAllByText("User Management").length).toBeGreaterThan(0);
    expect(screen.getByTestId("users-table")).toBeDefined();

    // Wait for the query to resolve and the switch to be checked
    await waitFor(
      () => {
        const switchElement = screen.getByRole("switch", {
          name: /open signup/i,
        });
        expect(switchElement.getAttribute("aria-checked")).toBe("true");
      },
      { timeout: 2000 },
    );
  });

  it("does not show Open Signup toggle for non-superusers", async () => {
    // Arrange
    vi.mocked(useAuthStore).mockImplementation(
      (selector: (state: AuthState) => unknown) =>
        selector({
          user: {
            id: "2",
            email: "a@e.com",
            role: "admin",
            is_superuser: false,
          },
        }),
    );

    // Act
    render(
      <QueryClientProvider client={queryClient}>
        <UsersPage />
      </QueryClientProvider>,
    );

    // Assert
    expect(screen.getAllByText("User Management").length).toBeGreaterThan(0);
    expect(screen.queryByText("Open Signup")).toBeNull();
  });
});
