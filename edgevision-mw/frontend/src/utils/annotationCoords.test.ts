import { describe, expect, it } from "vitest";
import {
  bboxFromPolygon,
  clampPolygon,
  detectedObjectsToBoxes,
  polygonFromCanvas,
  polygonToCanvas,
} from "./annotationCoords";

describe("annotationCoords", () => {
  it("computes bbox from normalized polygon", () => {
    const polygon: [number, number][] = [
      [0.1, 0.2],
      [0.4, 0.2],
      [0.4, 0.5],
      [0.1, 0.5],
    ];
    const bbox = bboxFromPolygon(polygon);
    expect(bbox.x).toBe(0.1);
    expect(bbox.y).toBe(0.2);
    expect(bbox.width).toBeCloseTo(0.3);
    expect(bbox.height).toBeCloseTo(0.3);
  });

  it("round-trips canvas polygon coords", () => {
    const polygon: [number, number][] = [
      [0.25, 0.25],
      [0.75, 0.25],
      [0.5, 0.75],
    ];
    const canvasPts = polygonToCanvas(polygon, 800, 600);
    const restored = polygonFromCanvas(canvasPts, 800, 600);
    expect(restored).toEqual(polygon);
  });

  it("clamps polygon points to 0..1", () => {
    expect(clampPolygon([[1.2, -0.1], [0.5, 0.5]])).toEqual([
      [1, 0],
      [0.5, 0.5],
    ]);
  });

  it("maps detected objects with masks to boxes", () => {
    const boxes = detectedObjectsToBoxes([
      {
        class_name: "car_private",
        confidence: 0.9,
        mask: [
          [0.1, 0.1],
          [0.4, 0.1],
          [0.4, 0.4],
        ],
      },
    ]);
    expect(boxes).toHaveLength(1);
    expect(boxes[0].polygon).toHaveLength(3);
    expect(boxes[0].label).toBe("car_private");
  });
});
