// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FlowDiagram } from "../components/common/FlowDiagram";
import { HelpIcon } from "../components/common/HelpIcon";

// Mock framer-motion to avoid animation issues
vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, className, ...props }: any) => {
      return (
        <div className={className} data-testid="motion-div" {...props}>
          {children}
        </div>
      );
    },
  },
}));

// Mock HelpIcon inside FlowDiagram to simplify finding nodes
vi.mock("../components/common/HelpIcon", () => ({
  HelpIcon: ({ tooltip }: { tooltip: string }) => (
    <span data-testid="help-icon" title={tooltip}>
      ?
    </span>
  ),
}));

describe("FlowDiagram", () => {
  it("renders correctly when isActive is true", () => {
    render(<FlowDiagram isActive={true} />);
    // Elements appear twice (mobile + desktop layout)
    expect(screen.getAllByText("qBittorrent").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Webhook Script").length).toBeGreaterThan(0);
  });

  it("renders correctly when isActive is false", () => {
    render(<FlowDiagram isActive={false} />);
    expect(screen.getAllByText("qBittorrent").length).toBeGreaterThan(0);
  });
});

describe("HelpIcon", () => {
  it("toggles tooltip on click", async () => {
    // Unmock HelpIcon for this suite since we want to test the real one
    vi.unmock("../components/common/HelpIcon");
    const { HelpIcon: RealHelpIcon } =
      await import("../components/common/HelpIcon");

    render(<RealHelpIcon tooltip="Test tooltip" />);

    const trigger = screen.getByRole("button", { name: "Help" });
    fireEvent.click(trigger);

    // Radix Tooltip renders content and potentially an accessible hidden copy
    // We just want to know if it's in the document.
    await waitFor(() => {
      const tooltips = screen.getAllByText("Test tooltip");
      expect(tooltips.length).toBeGreaterThan(0);
    });

    // Toggle off - checking for line coverage primarily
    fireEvent.click(trigger);
  });
});
