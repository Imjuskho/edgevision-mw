import { describe, expect, it } from "vitest";
import { postprocessYoloSeg } from "../ai/yoloSeg";

describe("yoloSeg postprocess", () => {
  it("returns empty when no predictions pass threshold", () => {
    const output0 = new Float32Array(116 * 8400);
    const output0Dims = [1, 116, 8400];
    const output1 = new Float32Array(32 * 160 * 160);

    const results = postprocessYoloSeg(
      output0,
      output0Dims,
      output1,
      320,
      240,
      80,
      60,
      0.5,
      0.1,
      0.99,
    );
    expect(results).toEqual([]);
  });

  it("golden test: single car detection with mask polygon", () => {
    const numPreds = 8400;
    const featDim = 116;
    const output0 = new Float32Array(featDim * numPreds);

    // Place one detection at index 100
    const i = 100;
    output0[0 + i * featDim] = 0.5 * 640;
    output0[1 + i * featDim] = 0.5 * 640;
    output0[2 + i * featDim] = 0.4 * 640;
    output0[3 + i * featDim] = 0.4 * 640;
    output0[4 + 2 + i * featDim] = 0.9; // class 2 = car

    for (let p = 0; p < 32; p++) {
      output0[84 + p + i * featDim] = p === 0 ? 1.0 : 0.0;
    }

    const output0Dims = [1, 116, 8400];
    const output1 = new Float32Array(32 * 160 * 160);
    output1[0] = 2.0; // strong proto activation

    const padX = 80;
    const padY = 60;
    const scale = 0.5;

    const results = postprocessYoloSeg(
      output0,
      output0Dims,
      output1,
      320,
      240,
      padX,
      padY,
      scale,
      0.35,
      0.45,
    );

    expect(results.length).toBeGreaterThanOrEqual(1);
    const car = results.find((r) => r.className === "car") ?? results[0];
    expect(car.confidence).toBeGreaterThan(0.35);
    expect(car.className).toBe("car");
    expect(car.bbox).toHaveLength(4);
    expect(Number.isFinite(car.bbox[0])).toBe(true);
  });
});
