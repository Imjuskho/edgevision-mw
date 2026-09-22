import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import AnnotationCanvas from "./AnnotationCanvas";
import { FabricCanvasZoomProvider } from "../context/FabricCanvasZoomContext";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: { language: "en" },
  }),
}));

vi.mock("fabric", () => {
  const mockCanvasInstance = {
    dispose: vi.fn(),
    getObjects: vi.fn(() => []),
    renderAll: vi.fn(),
    getWidth: vi.fn(() => 900),
    getHeight: vi.fn(() => 600),
    on: vi.fn(),
    off: vi.fn(),
    setBackgroundImage: vi.fn(),
    backgroundImage: null,
    viewportTransform: [1, 0, 0, 1, 0, 0],
    getScenePoint: vi.fn(() => ({ x: 0, y: 0 })),
    add: vi.fn(),
    remove: vi.fn(),
    discardActiveObject: vi.fn(),
    getActiveObject: vi.fn(() => null),
    getZoom: vi.fn(() => 1),
    setViewportTransform: vi.fn(),
  };

  class MockCanvas {
    constructor() {
      return mockCanvasInstance;
    }
  }

  return {
    Canvas: MockCanvas,
    Rect: vi.fn().mockImplementation((opts) => ({
      ...opts,
      _isBox: false,
      set: vi.fn(),
      calcTransformMatrix: vi.fn(() => [1, 0, 0, 1, 0, 0]),
    })),
    Polygon: vi.fn().mockImplementation((pts, opts) => ({
      ...(opts || {}),
      points: pts,
      _isBox: false,
      calcTransformMatrix: vi.fn(() => [1, 0, 0, 1, 0, 0]),
      pathOffset: { x: 0, y: 0 },
    })),
    Point: vi.fn(),
    FabricImage: vi.fn().mockImplementation(() => ({
      scale: vi.fn(),
      set: vi.fn(),
    })),
    FabricText: vi.fn(),
    ActiveSelection: vi.fn(),
    util: { transformPoint: vi.fn((_pt, _m) => _pt) },
  };
});

function renderCanvas(props: Record<string, unknown> = {}) {
  return render(
    <FabricCanvasZoomProvider>
      <AnnotationCanvas
        imageUrl=""
        boxes={[]}
        onBoxesChange={vi.fn()}
        label="car_private"
        {...props}
      />
    </FabricCanvasZoomProvider>
  );
}

describe("AnnotationCanvas accessibility", () => {
  it("canvas element has role='img' and aria-label", () => {
    const { container } = renderCanvas();
    const canvas = container.querySelector("canvas");
    expect(canvas).toBeTruthy();
    expect(canvas!.getAttribute("role")).toBe("img");
    expect(canvas!.getAttribute("aria-label")).toBeTruthy();
    expect(canvas!.getAttribute("aria-label")!.length).toBeGreaterThan(0);
  });

  it("canvas wrapper has annotation-canvas class", () => {
    const { container } = renderCanvas();
    const wrapper = container.querySelector(".annotation-canvas");
    expect(wrapper).toBeTruthy();
  });
});
