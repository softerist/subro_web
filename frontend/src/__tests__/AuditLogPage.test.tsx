/**
 * @vitest-environment jsdom
 */
import { render, screen, cleanup } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AuditLogPage from "../features/admin/pages/AuditLogPage";

vi.mock("../features/admin/api/audit", () => ({
  getAuditLogs: vi.fn().mockResolvedValue({
    items: [],
    next_cursor: null,
    total_count: 0,
  }),
}));

// Mock Components
vi.mock("../features/admin/components/AuditLogTable", () => ({
  AuditLogTable: () => <div data-testid="mock-audit-table">Audit Table</div>,
}));

vi.mock("../features/admin/components/AuditLogFilters", () => ({
  AuditLogFilters: () => <div data-testid="mock-audit-filters">Filters</div>,
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

// Mock Router
vi.mock("react-router-dom", () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

describe("AuditLogPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the main layout components", () => {
    render(<AuditLogPage />, { wrapper });

    expect(screen.getByText("Audit Logs")).toBeDefined();
    expect(screen.getByText(/Track administrative actions/i)).toBeDefined();
    expect(screen.getByTestId("mock-audit-table")).toBeDefined();
    expect(screen.getByTestId("mock-audit-filters")).toBeDefined();
    expect(screen.getByTestId("mock-export-dialog")).toBeDefined();
    expect(screen.getByTestId("mock-verify-dialog")).toBeDefined();
  });
});
