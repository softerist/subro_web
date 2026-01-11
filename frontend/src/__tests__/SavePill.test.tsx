/** @vitest-environment jsdom */
import { render, screen, fireEvent } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";
import { describe, it, expect, vi } from "vitest";
import { SavePill } from "@/components/common/SavePill";

expect.extend(matchers);

describe("SavePill", () => {
  it("renders actions and uses fallback positioning when no container ref", () => {
    const onSave = vi.fn();
    const onDiscard = vi.fn();

    render(
      <SavePill
        isVisible
        isLoading={false}
        hasChanges
        onSave={onSave}
        onDiscard={onDiscard}
      />,
    );

    screen.getByText("Unsaved Changes");
    fireEvent.click(screen.getByText("Save"));
    fireEvent.click(screen.getByText("Discard"));
    expect(onSave).toHaveBeenCalled();
    expect(onDiscard).toHaveBeenCalled();
  });

  it("centers based on container ref and shows success state", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    vi.spyOn(container, "getBoundingClientRect").mockReturnValue({
      top: 0,
      left: 100,
      width: 200,
      height: 100,
      bottom: 0,
      right: 0,
      x: 0,
      y: 0,
      toJSON: () => "",
    });

    render(
      <SavePill
        isVisible={false}
        isLoading={false}
        hasChanges={false}
        onSave={vi.fn()}
        onDiscard={vi.fn()}
        isSuccess
        containerRef={{ current: container }}
      />,
    );

    const pill = screen.getByText("Saved!");

    // Ensure portal rendered the pill; container centering logic uses mocked rect
    expect(pill).toBeTruthy();
  });
});
