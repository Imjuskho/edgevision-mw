import { describe, expect, it } from "vitest";
import {
  clampZoom,
  computeFitViewportTransform,
  formatZoomPercent,
  MAX_ZOOM,
  MIN_ZOOM,
  stepZoom,
} from "./fabricZoom";

describe("fabricZoom", () => {
  it("clamps zoom to configured bounds", () => {
    expect(clampZoom(0.1)).toBe(MIN_ZOOM);
    expect(clampZoom(20)).toBe(MAX_ZOOM);
    expect(clampZoom(1.5)).toBe(1.5);
  });

  it("steps zoom in and out", () => {
    expect(stepZoom(1, "in")).toBeGreaterThan(1);
    expect(stepZoom(2, "out")).toBeLessThan(2);
    expect(stepZoom(MIN_ZOOM, "out")).toBe(MIN_ZOOM);
    expect(stepZoom(MAX_ZOOM, "in")).toBe(MAX_ZOOM);
  });

  it("formats zoom as a percentage", () => {
    expect(formatZoomPercent(1)).toBe("100%");
    expect(formatZoomPercent(1.5)).toBe("150%");
  });

  it("computes a centered fit transform", () => {
    const vpt = computeFitViewportTransform(800, 600, 400, 300, 0);
    expect(vpt[0]).toBe(0.5);
    expect(vpt[3]).toBe(0.5);
    expect(vpt[4]).toBe(0);
    expect(vpt[5]).toBe(0);
  });

  it("returns identity transform for invalid dimensions", () => {
    expect(computeFitViewportTransform(0, 600, 400, 300)).toEqual([
      1, 0, 0, 1, 0, 0,
    ]);
  });
});
