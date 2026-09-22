import { describe, expect, it } from "vitest";
import { shallowEqualBoxes, cloneBoxes } from "./shallowEqualBoxes";
import type { BBox } from "../types";

const box = (overrides: Partial<BBox> = {}): BBox => ({
  x: 0.1,
  y: 0.2,
  width: 0.3,
  height: 0.4,
  label: "car_private",
  confidence: 0.9,
  ...overrides,
});

describe("shallowEqualBoxes", () => {
  it("returns true for identical empty arrays", () => {
    expect(shallowEqualBoxes([], [])).toBe(true);
  });

  it("returns true for identical single boxes", () => {
    const a = [box()];
    const b = [box()];
    expect(shallowEqualBoxes(a, b)).toBe(true);
  });

  it("returns true for identical multi-box arrays", () => {
    const a = [box({ label: "car_private" }), box({ label: "pedestrian", x: 0.5 })];
    const b = [box({ label: "car_private" }), box({ label: "pedestrian", x: 0.5 })];
    expect(shallowEqualBoxes(a, b)).toBe(true);
  });

  it("returns false for different lengths", () => {
    expect(shallowEqualBoxes([box()], [box(), box()])).toBe(false);
    expect(shallowEqualBoxes([box(), box()], [box()])).toBe(false);
  });

  it("returns false when label differs", () => {
    const a = [box({ label: "car_private" })];
    const b = [box({ label: "truck" })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
  });

  it("returns false when x differs", () => {
    const a = [box({ x: 0.1 })];
    const b = [box({ x: 0.11 })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
  });

  it("returns false when y differs", () => {
    const a = [box({ y: 0.2 })];
    const b = [box({ y: 0.21 })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
  });

  it("returns false when width differs", () => {
    const a = [box({ width: 0.3 })];
    const b = [box({ width: 0.31 })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
  });

  it("returns false when height differs", () => {
    const a = [box({ height: 0.4 })];
    const b = [box({ height: 0.41 })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
  });

  it("returns false when confidence differs", () => {
    const a = [box({ confidence: 0.9 })];
    const b = [box({ confidence: 0.91 })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
  });

  it("returns false when one has polygon and other does not", () => {
    const a = [box({ polygon: [[0, 0], [1, 0], [0.5, 1]] })];
    const b = [box({ polygon: undefined })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
    expect(shallowEqualBoxes(b, a)).toBe(false);
  });

  it("returns false when polygon lengths differ", () => {
    const a = [box({ polygon: [[0, 0], [1, 0], [0.5, 1]] })];
    const b = [box({ polygon: [[0, 0], [1, 0]] })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
  });

  it("returns false when polygon coord differs", () => {
    const a = [box({ polygon: [[0, 0], [1, 0], [0.5, 1]] })];
    const b = [box({ polygon: [[0, 0], [1, 0], [0.5, 0.9]] })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
  });

  it("returns true for identical polygons", () => {
    const a = [box({ polygon: [[0, 0], [1, 0], [0.5, 1]] })];
    const b = [box({ polygon: [[0, 0], [1, 0], [0.5, 1]] })];
    expect(shallowEqualBoxes(a, b)).toBe(true);
  });

  it("does not false-positive on object identity changes with same values", () => {
    const a = [box()];
    const b = [{ ...a[0] }];
    expect(shallowEqualBoxes(a, b)).toBe(true);
    expect(a).not.toBe(b);
    expect(a[0]).not.toBe(b[0]);
  });

  it("returns false for completely different boxes", () => {
    const a = [box({ x: 0, y: 0, width: 1, height: 1, label: "car" })];
    const b = [box({ x: 0.5, y: 0.5, width: 0.1, height: 0.1, label: "ped" })];
    expect(shallowEqualBoxes(a, b)).toBe(false);
  });
});

describe("cloneBoxes", () => {
  it("returns a deep copy — modifying clone does not affect original", () => {
    const original = [box({ polygon: [[0, 0], [1, 0], [0.5, 1]] })];
    const cloned = cloneBoxes(original);
    cloned[0].label = "mutated";
    cloned[0].x = 999;
    if (cloned[0].polygon) cloned[0].polygon[0] = [0.9, 0.9];
    expect(original[0].label).toBe("car_private");
    expect(original[0].x).toBe(0.1);
    expect(original[0].polygon![0]).toEqual([0, 0]);
  });

  it("preserves all fields", () => {
    const original = [box({ polygon: [[0.1, 0.2], [0.3, 0.4]], confidence: 0.95 })];
    const cloned = cloneBoxes(original);
    expect(cloned[0]).toEqual(original[0]);
  });

  it("handles boxes without polygon", () => {
    const original = [box({ polygon: undefined })];
    const cloned = cloneBoxes(original);
    expect(cloned[0].polygon).toBeUndefined();
  });

  it("handles empty array", () => {
    expect(cloneBoxes([])).toEqual([]);
  });
});
