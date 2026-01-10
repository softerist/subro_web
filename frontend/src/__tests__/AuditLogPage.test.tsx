/**
 * @vitest-environment jsdom
 */
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AuditLogPage from "../features/admin/pages/AuditLogPage";

// Mock the API module
const mockGetAuditLogs = vi.fn();
vi.mock("../features/admin/api/audit", () => ({
  getAuditLogs: (...args: any[]) => mockGetAuditLogs(...args),
}));

// Mock Components
vi.mock("../features/admin/components/AuditLogTable", () => ({
  AuditLogTable: ({ onPageChange, page, nextCursor }: any) => (
    <div data-testid="mock-audit-table">
      Audit Table
      <button
        data-testid="next-page-btn"
        onClick={() => onPageChange(page + 1)}
      >
        Next
      </button>
      <button
        data-testid="prev-page-btn"
        onClick={() => onPageChange(page - 1)}
      >
        Prev
      </button>
      <button data-testid="page-zero-btn" onClick={() => onPageChange(0)}>
        Page 0
      </button>
      <div data-testid="cursor-display">{nextCursor}</div>
      <div data-testid="page-display">{page}</div>
    </div>
  ),
}));

vi.mock("../features/admin/components/AuditLogFilters", () => ({
  AuditLogFilters: ({ onFilterChange, onClear }: any) => (
    <div data-testid="mock-audit-filters">
      Filters
      <button
        data-testid="filter-btn"
        onClick={() => onFilterChange({ action: "test" })}
      >
        Apply Filter
      </button>
      <button data-testid="clear-btn" onClick={onClear}>
        Clear Filter
      </button>
    </div>
  ),
}));

vi.mock("../features/admin/components/ExportAuditLogDialog", () => ({
  ExportAuditLogDialog: () => (
    <div data-testid="mock-export-dialog">Export Dialog</div>
  ),
}));

vi.mock("../features/admin/components/VerifyIntegrityDialog", () => ({
  VerifyIntegrityDialog: () => (
    <div data-testid="mock-verify-dialog">Verify Dialog</div>
  ),
}));

vi.mock("@/components/common/PageHeader", () => ({
  PageHeader: ({ action, title }: any) => (
    <div data-testid="mock-page-header">
      <h1>{title}</h1>
      <div data-testid="header-actions">{action}</div>
    </div>
  ),
}));

vi.mock("react-router-dom", () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

describe("AuditLogPage", () => {
  let queryClient: QueryClient;

  const createWrapper = () => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: 0 },
      },
    });
    return ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };

  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the main layout components", async () => {
    mockGetAuditLogs.mockResolvedValue({
      items: [],
      next_cursor: null,
      total_count: 0,
    });

    render(<AuditLogPage />, { wrapper: createWrapper() });

    expect(screen.getByText("Audit Logs")).toBeTruthy();
    expect(screen.getByTestId("mock-audit-table")).toBeTruthy();
  });

  it("displays error alert when fetch fails", async () => {
    const errorMsg = "Network Error";
    mockGetAuditLogs.mockRejectedValue(new Error(errorMsg));

    render(<AuditLogPage />, { wrapper: createWrapper() });

    const alert = await screen.findByRole("alert");
    const text = alert.textContent || "";
    expect(text.includes("Failed to load audit logs")).toBe(true);
    expect(text.includes(errorMsg)).toBe(true);
  });

  it("shows fallback error message when error lacks a message", async () => {
    mockGetAuditLogs.mockRejectedValue({});

    render(<AuditLogPage />, { wrapper: createWrapper() });

    const alert = await screen.findByRole("alert");
    const text = alert.textContent || "";
    expect(text.includes("Internal Server Error")).toBe(true);
  });

  it("handles pagination correctly and updates cursor cache", async () => {
    const user = userEvent.setup();
    mockGetAuditLogs
      .mockResolvedValueOnce({
        items: [{ id: 1 }],
        next_cursor: "cursor-page-2",
        total_count: 50,
      })
      .mockResolvedValueOnce({
        items: [{ id: 2 }],
        next_cursor: "cursor-page-3",
        total_count: 50,
      });

    render(<AuditLogPage />, { wrapper: createWrapper() });

    await waitFor(() =>
      expect(mockGetAuditLogs).toHaveBeenCalledWith(
        expect.objectContaining({ cursor: null }),
      ),
    );

    await waitFor(() =>
      expect(screen.getByTestId("cursor-display").textContent).toBe(
        "cursor-page-2",
      ),
    );

    // Click next page
    await user.click(screen.getByTestId("next-page-btn"));

    await waitFor(() => expect(mockGetAuditLogs).toHaveBeenCalledTimes(2));
    const secondCall = mockGetAuditLogs.mock.calls[1]?.[0] as any;
    expect(secondCall.page).toBe(2);
    expect(secondCall.cursor).toBe("cursor-page-2");

    // Go back
    await user.click(screen.getByTestId("prev-page-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("page-display").textContent).toBe("1"),
    );
  });

  it("prevents invalid page change", async () => {
    const user = userEvent.setup();
    mockGetAuditLogs.mockResolvedValue({
      items: [],
      next_cursor: null,
      total_count: 0,
    });
    render(<AuditLogPage />, { wrapper: createWrapper() });
    await waitFor(() => expect(mockGetAuditLogs).toHaveBeenCalled());

    // Try go to page 0
    await user.click(screen.getByTestId("page-zero-btn"));
    expect(screen.getByTestId("page-display").textContent).toBe("1");

    // Try go to page 2 when no next_cursor
    await user.click(screen.getByTestId("next-page-btn"));
    expect(screen.getByTestId("page-display").textContent).toBe("1");
  });

  it("updates filters and resets page", async () => {
    const user = userEvent.setup();
    mockGetAuditLogs.mockResolvedValue({
      items: [],
      next_cursor: null,
      total_count: 0,
    });
    render(<AuditLogPage />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId("filter-btn"));

    await waitFor(() => {
      expect(mockGetAuditLogs).toHaveBeenCalledWith(
        expect.objectContaining({ action: "test" }),
      );
    });
  });

  it("clears filters and resets page", async () => {
    const user = userEvent.setup();
    mockGetAuditLogs.mockResolvedValue({
      items: [],
      next_cursor: null,
      total_count: 0,
    });
    render(<AuditLogPage />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId("clear-btn"));

    await waitFor(() => {
      expect(mockGetAuditLogs).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1 }),
      );
    });
  });

  it("refetches data when refresh button is clicked", async () => {
    const user = userEvent.setup();
    mockGetAuditLogs.mockResolvedValue({
      items: [],
      next_cursor: null,
      total_count: 0,
    });
    render(<AuditLogPage />, { wrapper: createWrapper() });

    const refreshBtn = await screen.findByRole("button", {
      name: /refresh audit logs/i,
    });
    await waitFor(() => expect(mockGetAuditLogs).toHaveBeenCalled());

    mockGetAuditLogs.mockClear();

    await user.click(refreshBtn);

    await waitFor(
      () => {
        expect(mockGetAuditLogs).toHaveBeenCalledTimes(1);
      },
      { timeout: 2000 },
    );
  });
});
