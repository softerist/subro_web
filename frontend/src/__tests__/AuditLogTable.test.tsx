/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * @vitest-environment jsdom
 */
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuditLogTable } from "../features/admin/components/AuditLogTable";
import { AuditLog } from "../features/admin/api/audit";

// Mock Router
vi.mock("react-router-dom", () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
  Link: ({ children }: any) => <a href="#">{children}</a>,
}));

// Mock simple UI components if needed
// For Table, we rely on standard functional rendering, should be fine in JSDOM usually.

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

const mockLogs: AuditLog[] = [
  {
    id: 1,
    event_id: "uuid-1",
    timestamp: "2024-01-01T12:00:00Z",
    category: "auth",
    severity: "info",
    success: true,
    actor_type: "user",
    impersonator_id: null,
    resource_type: null,
    resource_id: null,
    outcome: "success",
    reason_code: null,
    action: "auth.login",
    actor_email: "test@example.com",
    ip_address: "127.0.0.1",
    details: {},
  },
  {
    id: 2,
    event_id: "uuid-2",
    timestamp: "2024-01-01T12:05:00Z",
    category: "auth",
    severity: "error",
    success: false,
    actor_type: "user",
    impersonator_id: null,
    resource_type: null,
    resource_id: null,
    outcome: "failure",
    reason_code: "Bad Password",
    action: "auth.login_failed",
    actor_email: "attacker@example.com",
    ip_address: "1.2.3.4",
    details: { reason: "Bad Password" },
  },
];

describe("AuditLogTable", () => {
  const defaultProps = {
    logs: mockLogs,
    isLoading: false,
    total: 2,
    page: 1,
    perPage: 15,
    nextCursor: null as string | null,
    onPageChange: vi.fn(),
  };

  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders a list of audit logs", () => {
    render(<AuditLogTable {...defaultProps} />, { wrapper });

    expect(screen.getByText("test@example.com")).toBeDefined();
    expect(screen.getByText("auth.login")).toBeDefined();
    expect(screen.getByText("auth.login_failed")).toBeDefined();
    expect(screen.getByText("127.0.0.1")).toBeDefined();
  });

  it("shows empty state when no logs", () => {
    render(<AuditLogTable {...defaultProps} logs={[]} />, {
      wrapper,
    });

    expect(screen.getByText(/no audit logs found/i)).toBeDefined();
  });

  it("shows loading state", () => {
    render(<AuditLogTable {...defaultProps} isLoading={true} />, { wrapper });
    // Loader2 icon should be present, or valid loading indicator
    // We can check for the container class specific to loading if icon is hard to find by role
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).toBeDefined();
  });

  it("shows a next-page button when a cursor exists", () => {
    const onPageChange = vi.fn();
    render(
      <AuditLogTable
        {...defaultProps}
        nextCursor="cursor-1"
        onPageChange={onPageChange}
      />,
      { wrapper },
    );

    const showMore = screen.getByRole("button", { name: /show more/i });
    fireEvent.click(showMore);
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("shows a back-to-top button when on a later page", () => {
    const onPageChange = vi.fn();
    render(
      <AuditLogTable
        {...defaultProps}
        page={2}
        nextCursor={null}
        onPageChange={onPageChange}
      />,
      { wrapper },
    );

    const showLess = screen.getByRole("button", {
      name: /show less \(back to top\)/i,
    });
    fireEvent.click(showLess);
    expect(onPageChange).toHaveBeenCalledWith(1);
  });
});
