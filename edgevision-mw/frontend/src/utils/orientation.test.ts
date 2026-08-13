import { describe, expect, it } from "vitest";
import {
  flipBBoxX,
  flipCuboidX,
  flipMaskPolygonX,
  flipPolygonX,
  isMirrored,
  orientationFromMirror,
} from "./orientation";
import { wsCoordinateRoundTrip } from "./drawAnnotations";

describe("orientation helpers", () => {
  it("flipBBoxX twice returns the original bbox", () => {
    const bbox: [number, number, number, number] = [100, 50, 80, 120];
    const width = 640;
    expect(flipBBoxX(flipBBoxX(bbox, width), width)).toEqual(bbox);
  });

  it("flipPolygonX twice returns the original points", () => {
    const points = [
      [0.1, 0.2],
      [0.3, 0.4],
      [0.5, 0.6],
    ];
    const flipped = flipPolygonX(points);
    const restored = flipPolygonX(flipped);
    for (let i = 0; i < points.length; i++) {
      expect(restored[i][0]).toBeCloseTo(points[i][0], 5);
      expect(restored[i][1]).toBeCloseTo(points[i][1], 5);
    }
  });

  it("flipCuboidX twice returns the original corners", () => {
    const corners = [
      [0.2, 0.3, 0.5],
      [0.8, 0.3, 0.5],
      [0.8, 0.7, 0.5],
      [0.2, 0.7, 0.5],
    ];
    const flipped = flipCuboidX(corners);
    const restored = flipCuboidX(flipped);
    for (let i = 0; i < corners.length; i++) {
      expect(restored[i][0]).toBeCloseTo(corners[i][0], 5);
      expect(restored[i][1]).toBeCloseTo(corners[i][1], 5);
      expect(restored[i][2]).toBeCloseTo(corners[i][2], 5);
    }
  });

  it("flipMaskPolygonX is an alias for flipPolygonX", () => {
    const points = [[0.2, 0.4], [0.6, 0.8]];
    expect(flipMaskPolygonX(points)).toEqual(flipPolygonX(points));
  });

  it("orientationFromMirror maps boolean to orientation string", () => {
    expect(orientationFromMirror(false)).toBe("normal");
    expect(orientationFromMirror(true)).toBe("mirrored");
  });

  it("isMirrored respects mirrorAllowed gate", () => {
    expect(isMirrored(false, true)).toBe(false);
    expect(isMirrored(true, true)).toBe(true);
    expect(isMirrored(true, false)).toBe(false);
  });
});

describe("wsCoordinateRoundTrip", () => {
  it("preserves coords through mirror round-trip", () => {
    const bbox: [number, number, number, number] = [120, 80, 200, 160];
    const polygon = [[0.1, 0.2], [0.5, 0.2], [0.5, 0.8]];
    const cuboid = [[0.3, 0.4, 0.5], [0.7, 0.4, 0.5]];

    const result = wsCoordinateRoundTrip(bbox, polygon, cuboid, 640, true);

    expect(result.bbox[0]).toBeCloseTo(bbox[0], 3);
    expect(result.bbox[1]).toBeCloseTo(bbox[1], 3);
    expect(result.polygon![0][0]).toBeCloseTo(polygon[0][0], 5);
    expect(result.cuboid![0][0]).toBeCloseTo(cuboid[0][0], 5);
  });

  it("passes through unchanged when not mirrored", () => {
    const bbox: [number, number, number, number] = [10, 20, 30, 40];
    const result = wsCoordinateRoundTrip(bbox, undefined, undefined, 640, false);
    expect(result.bbox).toEqual(bbox);
  });
});
