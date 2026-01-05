// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

// Polyfill ResizeObserver for Radix UI
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
import { UsersTable } from "../features/admin/components/UsersTable";
import { User } from "../features/admin/types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "../store/authStore";

// Mock dependencies
vi.mock("../features/admin/api/admin", () => ({
  adminApi: {
    deleteUser: vi.fn(),
    updateUser: vi.fn(),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

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
  it("renders loading state", () => {
    renderTable([], true);
    // Loader2 typically renders as an svg, we can check for a container or just absence of table rows
    // Because Loader2 has no text, checking for container class is brittle, but let's check for "Email" header at least
    expect(screen.queryByText("user1@example.com")).not.toBeInTheDocument();
  });

  it("renders users list", () => {
    useAuthStore.setState({ user: { ...mockUsers[1] } }); // Set current user as admin
    renderTable();
    expect(screen.getByText("user1@example.com")).toBeInTheDocument();
    expect(screen.getByText("admin@example.com")).toBeInTheDocument();
    expect(screen.getByText("Superuser")).toBeInTheDocument();
  });

  it("opens edit dialog on click", () => {
    useAuthStore.setState({ user: { ...mockUsers[1] } }); // Admin
    renderTable();

    // Find edit button for first user (standard)
    // The table has multiple edit buttons, let's grab the first one
    const editButtons = screen.getAllByTitle("Edit User");
    fireEvent.click(editButtons[0]);

    // Check if Dialog Title appears
    expect(screen.getByText("Edit User")).toBeInTheDocument();
    expect(screen.getByDisplayValue("user1@example.com")).toBeInTheDocument();
  });

  it("disables edit for superusers if current user is not superuser", () => {
    // Current user is standard admin
    useAuthStore.setState({
      user: { ...mockUsers[0], role: "admin", is_superuser: false },
    });

    renderTable();

    // Find the row for admin@example.com
    // Use getAllByText in case it appears multiple times and take the last one (likely the row)
    // Or better, search within rows.
    const rows = screen.getAllByRole("row");
    const superuserRow = rows.find((row) =>
      row.textContent?.includes("admin@example.com"),
    );

    expect(superuserRow).toBeDefined();
    const editBtn = superuserRow?.querySelector(
      "button[title='Cannot modify Superuser']",
    );
    expect(editBtn).toBeDisabled();
  });

  it("shows empty state", () => {
    renderTable([]);
    expect(screen.getByText("No users found.")).toBeInTheDocument();
  });
});
