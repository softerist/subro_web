/**
 * @vitest-environment jsdom
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
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
  });
});
