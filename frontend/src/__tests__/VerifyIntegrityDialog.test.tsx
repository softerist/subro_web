/**
 * @vitest-environment jsdom
 */
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Polyfill ResizeObserver for Radix UI
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
import { VerifyIntegrityDialog } from "../features/admin/components/VerifyIntegrityDialog";
import { verifyAuditIntegrity } from "../features/admin/api/audit";

vi.mock("../features/admin/api/audit", () => ({
  verifyAuditIntegrity: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe("VerifyIntegrityDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows verified status with checked count", async () => {
    vi.mocked(verifyAuditIntegrity).mockResolvedValue({
      verified: true,
      issues: [],
      checkedCount: 5,
      corruptedCount: 0,
    });

    render(<VerifyIntegrityDialog />);

    fireEvent.click(screen.getByRole("button", { name: /verify integrity/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /start verification/i }),
    );

    expect(await screen.findByText(/checked 5 entries/i)).toBeDefined();
    expect(screen.getByText(/verified/i)).toBeDefined();
  });

  it("renders issues when integrity check fails", async () => {
    vi.mocked(verifyAuditIntegrity).mockResolvedValue({
      verified: false,
      issues: ["Hash mismatch at ID 12"],
      checkedCount: 12,
      corruptedCount: 1,
    });

    render(<VerifyIntegrityDialog />);

    fireEvent.click(screen.getByRole("button", { name: /verify integrity/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /start verification/i }),
    );

    expect(await screen.findByText(/integrity breach/i)).toBeDefined();
    expect(screen.getByText(/hash mismatch at id 12/i)).toBeDefined();

    // Verify button changes to "Re-verify"
    expect(screen.getByRole("button", { name: /re-verify/i })).toBeDefined();
  });

  it("shows loading state during verification", async () => {
    // Return a promise that doesn't resolve immediately
    vi.mocked(verifyAuditIntegrity).mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                verified: true,
                issues: [],
                checkedCount: 0,
                corruptedCount: 0,
              }),
            100,
          ),
        ),
    );

    render(<VerifyIntegrityDialog />);

    fireEvent.click(screen.getByRole("button", { name: /verify integrity/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /start verification/i }),
    );

    expect(screen.getByText(/hashing event chains/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /verifying/i })).toBeDisabled();

    // Wait for finish
    expect(await screen.findByText(/verified/i)).toBeDefined();
  });

  it("handles API errors gracefully", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(verifyAuditIntegrity).mockRejectedValue(
      new Error("Network error"),
    );
    const { toast } = await import("sonner");

    render(<VerifyIntegrityDialog />);
    fireEvent.click(screen.getByRole("button", { name: /verify integrity/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /start verification/i }),
    );

    // Should return to ready state or show error?
    // Code says: toast.error, and finally { isVerifying(false) }
    // It stays in "Ready to scan logs" state if result is null?
    // Yes, setResult(null) at start. If error, result remains null.

    // Wait for isVerifying to be false
    expect(await screen.findByText(/ready to scan logs/i)).toBeDefined();
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining("Failed to perform integrity check"),
    );
  });

  it("resets state when closed", async () => {
    vi.mocked(verifyAuditIntegrity).mockResolvedValue({
      verified: true,
      issues: [],
      checkedCount: 1,
      corruptedCount: 0,
    });

    render(<VerifyIntegrityDialog />);
    fireEvent.click(screen.getByRole("button", { name: /verify integrity/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /start verification/i }),
    );
    expect(await screen.findByText(/verified/i)).toBeDefined();

    // Close dialog
    // "Close" button has variant="ghost" - Select non-absolute one (X button is absolute)
    const closeBtns = screen.getAllByRole("button", { name: /close/i });
    const closeBtn = closeBtns.find((b) => !b.className.includes("absolute"));
    fireEvent.click(closeBtn!);

    // Open again
    fireEvent.click(screen.getByRole("button", { name: /verify integrity/i }));

    // Should be back to start
    // Wait for the closing animation to finish and potential duplicates to be removed
    // In JSDOM, the closing dialog might persist, so we accept multiple matches as long as state is reset
    await waitFor(() => {
      const readyTexts = screen.getAllByText(/ready to scan logs/i);
      expect(readyTexts.length).toBeGreaterThanOrEqual(1);
      expect(readyTexts[readyTexts.length - 1]).toBeVisible();
    });
  });
});
