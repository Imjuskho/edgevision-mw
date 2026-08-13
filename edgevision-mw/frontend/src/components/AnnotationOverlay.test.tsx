import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import AnnotationOverlay from "./AnnotationOverlay";

describe("AnnotationOverlay invariants", () => {
  it("does not apply CSS transform to overlay root (Phase 9 mirror guard)", () => {
    const { container } = render(
      <AnnotationOverlay
        annotations={[
          {
            class_name: "car",
            taxonomy_label: "car_private",
            confidence: 0.9,
            bbox: [10, 20, 100, 80],
          },
        ]}
        videoWidth={640}
        videoHeight={480}
        previewMirrored
        orientation="normal"
      />,
    );

    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    const transform = svg?.style.transform ?? window.getComputedStyle(svg!).transform;
    expect(transform === "" || transform === "none").toBe(true);
  });

  it("renders nothing when video dimensions are zero", () => {
    const { container } = render(
      <AnnotationOverlay annotations={[]} videoWidth={0} videoHeight={0} />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });
});
