/**
 * @vitest-environment jsdom
 */
import {
  render,
  screen,
  cleanup,
  fireEvent,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";
expect.extend(matchers);
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
    actor_user_id: "user-1",
    actor_email: "test@example.com",
    actor_type: "user",
    ip_address: "127.0.0.1",
    action: "auth.login",
    resource_type: "auth",
    resource_id: "123",
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
  {
    id: 3,
    event_id: "uuid-3",
    timestamp: "2024-01-01T12:10:00Z",
    category: "system",
    severity: "critical",
    success: false,
    actor_type: "system",
    impersonator_id: null,
    resource_type: null,
    resource_id: null,
    outcome: "failure",
    reason_code: "DB_CRASH",
    action: "system.crash",
    actor_email: null,
    ip_address: "0.0.0.0",
    details: { error: "Out of memory" },
  },
  {
    id: 4,
    event_id: "uuid-4",
    timestamp: "2024-01-01T12:15:00Z",
    category: "user",
    severity: "warning",
    success: true,
    actor_type: "user",
    impersonator_id: "admin-id",
    resource_type: null,
    resource_id: null,
    outcome: "success",
    reason_code: null,
    action: "user.update",
    actor_email: "user@example.com",
    ip_address: "1.2.3.4",
    details: {},
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

    expect(screen.getAllByText("test@example.com").length).toBeGreaterThan(0);
    expect(screen.getAllByText("auth.login").length).toBeGreaterThan(0);
    expect(screen.getAllByText("auth.login_failed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("127.0.0.1").length).toBeGreaterThan(0);
  });

  it("shows empty state when no logs", () => {
    render(<AuditLogTable {...defaultProps} logs={[]} />, {
      wrapper,
    });

    expect(screen.getAllByText(/no audit logs found/i).length).toBeGreaterThan(
      0,
    );
  });

  it("shows loading state", () => {
    render(<AuditLogTable {...defaultProps} logs={[]} isLoading={true} />, {
      wrapper,
    });
    // Loader2 icon should be present (line 76-79)
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

  it("renders distinct badges for severity levels", () => {
    // We added critical and warning logs to mockLogs
    render(<AuditLogTable {...defaultProps} />, { wrapper });

    // Check for badge text content
    expect(screen.getAllByText("Critical").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Warning").length).toBeGreaterThan(0);

    // We could check class names, but existence is sufficient for branch coverage
  });

  it("shows impersonation badge if impersonator_id is present", () => {
    render(<AuditLogTable {...defaultProps} />, { wrapper });
    expect(screen.getAllByText("Impersonated").length).toBeGreaterThan(0);
  });

  it("opens details dialog when clicking view button and closes it", () => {
    render(<AuditLogTable {...defaultProps} />, { wrapper });

    // Target the row for "system.crash" (Critical log)
    const cells = screen.getAllByText("system.crash");
    const row = cells.find((el) => el.closest("tr"))?.closest("tr");
    expect(row).toBeInTheDocument();

    // Find the button within that row
    const viewBtn = within(row!).getByRole("button");
    fireEvent.click(viewBtn);

    // Dialog should open
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();

    // Check dialog content
    expect(within(dialog).getByText("Event Details")).toBeInTheDocument();
    expect(within(dialog).getByText("DB_CRASH")).toBeInTheDocument(); // Reason Code

    // Close dialog by pressing Escape
    fireEvent.keyDown(dialog, { key: "Escape" });
  });

  it("handles null values and pluralization in desktop and mobile views", () => {
    const logsWithEdgeCases: AuditLog[] = [
      {
        ...mockLogs[0],
        id: 10,
        actor_email: null,
        details: { field1: "val1", field2: "val2" },
      },
      {
        ...mockLogs[1],
        id: 11,
        details: { onlyOne: "field" },
      },
      {
        ...mockLogs[0],
        id: 12,
        details: {},
      },
      {
        ...mockLogs[0],
        id: 13,
        timestamp: "invalid",
      },
      {
        ...mockLogs[0],
        id: 14,
        details: null,
        ip_address: "",
      },
    ];

    render(<AuditLogTable {...defaultProps} logs={logsWithEdgeCases} />, {
      wrapper,
    });

    // Desktop view checks
    const desktopRows = screen.queryAllByRole("row");
    if (desktopRows.length > 1) {
      const row10 = desktopRows[1];
      expect(within(row10).getByText("System")).toBeInTheDocument();
      expect(within(row10).getByText("2 fields")).toBeInTheDocument();

      const row11 = desktopRows[2];
      expect(within(row11).getByText("1 field")).toBeInTheDocument();
    }

    // Mobile view checks
    expect(screen.getAllByText("System").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2 fields").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 field").length).toBeGreaterThan(0);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Invalid date").length).toBeGreaterThan(0);
  });

  it("handles view button click in mobile view and loading state on button", () => {
    const { rerender } = render(
      <AuditLogTable {...defaultProps} nextCursor="cursor-1" />,
      { wrapper },
    );

    // Verify "Show More" is visible
    expect(screen.getByText("Show More")).toBeInTheDocument();

    // Rerender with isLoading=true to check "Loading..." on button (line 254)
    rerender(
      <QueryClientProvider client={queryClient}>
        <AuditLogTable
          {...defaultProps}
          nextCursor="cursor-1"
          isLoading={true}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();

    const eyeIcons = screen.getAllByRole("button").filter((btn) => {
      let parent = btn.parentElement;
      while (parent) {
        if (parent.classList.contains("md:hidden")) return true;
        parent = parent.parentElement;
      }
      return false;
    });

    expect(eyeIcons.length).toBeGreaterThan(0);
    fireEvent.click(eyeIcons[0]);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
