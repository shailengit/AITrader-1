import { describe, it, expect } from "vitest";
import { clampPanelState } from "./FloatingPanel";

describe("clampPanelState", () => {
  it("clamps x so the panel stays within the right edge", () => {
    const next = clampPanelState(
      { x: 9999, y: 100, width: 600, height: 400, minimized: false },
      { width: 1200, height: 800 }
    );
    expect(next.x).toBe(1200 - 600); // x + width <= viewport.width
  });

  it("clamps y so the panel stays within the bottom edge", () => {
    const next = clampPanelState(
      { x: 0, y: 9999, width: 600, height: 400, minimized: false },
      { width: 1200, height: 800 }
    );
    expect(next.y).toBe(800 - 400);
  });

  it("respects min size 320x200", () => {
    const next = clampPanelState(
      { x: 0, y: 0, width: 100, height: 50, minimized: false },
      { width: 2000, height: 2000 }
    );
    expect(next.width).toBe(320);
    expect(next.height).toBe(200);
  });

  it("respects max size 90% of viewport", () => {
    const next = clampPanelState(
      { x: 0, y: 0, width: 9999, height: 9999, minimized: false },
      { width: 1000, height: 800 }
    );
    expect(next.width).toBe(900); // 0.9 * 1000
    expect(next.height).toBe(720); // 0.9 * 800
  });

  it("does not change when already valid", () => {
    const next = clampPanelState(
      { x: 100, y: 100, width: 600, height: 400, minimized: false },
      { width: 2000, height: 2000 }
    );
    expect(next).toEqual({
      x: 100,
      y: 100,
      width: 600,
      height: 400,
      minimized: false,
    });
  });

  it("clamps x to 0 when negative", () => {
    const next = clampPanelState(
      { x: -50, y: 0, width: 600, height: 400, minimized: false },
      { width: 2000, height: 2000 }
    );
    expect(next.x).toBe(0);
  });

  it("clamps y to 0 when negative", () => {
    const next = clampPanelState(
      { x: 0, y: -10, width: 600, height: 400, minimized: false },
      { width: 2000, height: 2000 }
    );
    expect(next.y).toBe(0);
  });

  it("preserves minimized flag through clamping", () => {
    const next = clampPanelState(
      { x: 0, y: 0, width: 600, height: 400, minimized: true },
      { width: 1000, height: 1000 }
    );
    expect(next.minimized).toBe(true);
  });

  it("handles viewport smaller than min size gracefully", () => {
    // Edge case: viewport is too small even for the min size. The
    // function still returns 320x200, which would overflow but is
    // better than returning negative sizes.
    const next = clampPanelState(
      { x: 0, y: 0, width: 600, height: 400, minimized: false },
      { width: 100, height: 100 }
    );
    expect(next.width).toBe(320);
    expect(next.height).toBe(200);
  });
});
