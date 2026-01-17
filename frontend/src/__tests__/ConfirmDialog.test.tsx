/** @vitest-environment jsdom */
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { vi, describe, it, expect, afterEach } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";
expect.extend(matchers);
import { ConfirmDialog } from "@/components/common/ConfirmDialog";

// ConfirmDialog uses createPortal, which works in jsdom.

describe("ConfirmDialog", () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    title: "Confirm Action",
    description: "Are you sure?",
    onConfirm: vi.fn(),
  };

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders when open", () => {
    render(<ConfirmDialog {...defaultProps} />);
    expect(screen.getByText("Confirm Action")).toBeInTheDocument();
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(<ConfirmDialog {...defaultProps} open={false} />);
    expect(screen.queryByText("Confirm Action")).not.toBeInTheDocument();
  });

  it("calls onConfirm when confirm button is clicked", () => {
    render(<ConfirmDialog {...defaultProps} />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(defaultProps.onConfirm).toHaveBeenCalled();
  });

  it("calls onOpenChange(false) when cancel button is clicked", () => {
    render(<ConfirmDialog {...defaultProps} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("calls onOpenChange(false) when backdrop is clicked", () => {
    render(<ConfirmDialog {...defaultProps} />);
    // The backdrop is the fixed inset div with onClick.
    // It's the sibling of the dialog container? Or parent?
    // Structure:
    // <div ...> (container)
    //   <motion.div onClick=...> (Backdrop)
    //   <motion.div role="dialog"> (Modal)
    // </div>
    // We can't query by role "backdrop" easily unless we added it (we didn't).
    // But it has class "backdrop-blur-sm".
    // Alternatively, it's the element covering the screen.
    // Let's assume it's the first div that is NOT the dialog.

    // Actually, createPortal renders it in document.body.
    // We can find the container by class or structure.
    // Or we can assume clicking outside the dialog triggers it.
    // Since jsdom doesn't simulate layout, we need to find the element.
    const dialog = screen.getByRole("dialog");
    const backdrop = dialog.parentElement?.querySelector(".backdrop-blur-sm");

    expect(backdrop).toBeTruthy();
    fireEvent.click(backdrop!);
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("positions correctly with targetRect (Desktop)", () => {
    // Determine window size
    window.innerWidth = 1024;
    window.innerHeight = 768;

    const targetRect = { top: 100, left: 100, width: 50, height: 20 };
    render(<ConfirmDialog {...defaultProps} targetRect={targetRect} />);

    const dialog = screen.getByRole("dialog");
    const style = window.getComputedStyle(dialog);

    // Logic:
    // left = target.left + target.width - dialogWidth (260)
    // 100 + 50 - 260 = -110.
    // Clamped left < 16 -> 16.

    // top = target.top + target.height + margin (8)
    // 100 + 20 + 8 = 128.

    expect(style.position).toBe("fixed");
    // Since expected Left is clamped to 16px (viewportPadding)
    expect(style.left).toBe("16px");
    expect(style.top).toBe("128px");
  });

  it("clamps to right edge if confirming near right side", () => {
    window.innerWidth = 1000;
    const dialogWidth = 260; // used in style expectation below?

    // Target at right edge
    const targetRect = { top: 100, left: 950, width: 50, height: 20 };
    // left calc: 950 + 50 - 260 = 740.
    // Check right edge: 740 + 260 = 1000. 1000 > 1000 - 16 (984).
    // Should clamp to 984.

    render(<ConfirmDialog {...defaultProps} targetRect={targetRect} />);
    const dialog = screen.getByRole("dialog");
    const style = window.getComputedStyle(dialog);

    const padding = 16;
    expect(style.left).toBe(`${1000 - dialogWidth - padding}px`); // 724px
  });

  it("clamps to bottom edge if confirming near bottom", () => {
    window.innerHeight = 800;

    // Target near bottom
    const targetRect = { top: 750, left: 100, width: 50, height: 20 };
    // top calc: 750 + 20 + 8 = 778.
    // 778 + 150 (828) > 800 - 16 (784).
    // Should flip to above: target.top (750) - dialogHeight (150) - margin (8) = 592.

    render(<ConfirmDialog {...defaultProps} targetRect={targetRect} />);
    const dialog = screen.getByRole("dialog");
    const style = window.getComputedStyle(dialog);

    expect(style.top).toBe("592px");
  });

  it("switches to centered layout on mobile", () => {
    // Emulate mobile
    window.innerWidth = 400;
    window.dispatchEvent(new Event("resize"));

    render(
      <ConfirmDialog
        {...defaultProps}
        targetRect={{ top: 100, left: 100, width: 20, height: 20 }}
      />,
    );

    const dialog = screen.getByRole("dialog");
    // On mobile (isMobile=true), hasPosition becomes false.
    // Class should contain "relative", not fixed positioning styles (or style object is empty).
    // Line 58: return {} if !hasPosition.

    const style = window.getComputedStyle(dialog);
    expect(style.position).not.toBe("fixed");
    // Class check?
    expect(dialog.className).toContain("relative");
  });
});
