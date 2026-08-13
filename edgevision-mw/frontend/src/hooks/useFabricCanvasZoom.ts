import { useCallback, useEffect, useRef, useState } from "react";
import { Canvas, Point } from "fabric";
import {
  clampZoom,
  computeFitViewportTransform,
  identityViewportTransform,
  stepZoom,
} from "../utils/fabricZoom";

interface UseFabricCanvasZoomOptions {
  containerRef?: React.RefObject<HTMLElement | null>;
  enabled?: boolean;
}

export function useFabricCanvasZoom(
  canvasRef: React.RefObject<Canvas | null>,
  options: UseFabricCanvasZoomOptions = {},
) {
  const { containerRef, enabled = true } = options;
  const [zoom, setZoom] = useState(1);
  const [isSpacePressed, setIsSpacePressed] = useState(false);
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<{ x: number; y: number } | null>(null);
  const spaceRef = useRef(false);
  const panningRef = useRef(false);

  const syncZoomState = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    setZoom(canvas.getZoom());
  }, [canvasRef]);

  const applyZoomAtPoint = useCallback(
    (nextZoom: number, point: Point) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.zoomToPoint(point, clampZoom(nextZoom));
      canvas.requestRenderAll();
      syncZoomState();
    },
    [canvasRef, syncZoomState],
  );

  const zoomIn = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const center = new Point(canvas.getWidth() / 2, canvas.getHeight() / 2);
    applyZoomAtPoint(stepZoom(canvas.getZoom(), "in"), center);
  }, [applyZoomAtPoint, canvasRef]);

  const zoomOut = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const center = new Point(canvas.getWidth() / 2, canvas.getHeight() / 2);
    applyZoomAtPoint(stepZoom(canvas.getZoom(), "out"), center);
  }, [applyZoomAtPoint, canvasRef]);

  const resetZoom = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.setViewportTransform(identityViewportTransform());
    canvas.setZoom(1);
    canvas.requestRenderAll();
    syncZoomState();
  }, [canvasRef, syncZoomState]);

  const fitToScreen = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef?.current;
    if (!canvas || !container) {
      resetZoom();
      return;
    }

    const vpt = computeFitViewportTransform(
      canvas.getWidth(),
      canvas.getHeight(),
      container.clientWidth,
      container.clientHeight,
    );
    canvas.setViewportTransform(vpt);
    canvas.setZoom(vpt[0]);
    canvas.requestRenderAll();
    syncZoomState();
  }, [canvasRef, containerRef, resetZoom, syncZoomState]);

  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.code === "Space" && !e.repeat) {
        e.preventDefault();
        spaceRef.current = true;
        setIsSpacePressed(true);
        const canvas = canvasRef.current;
        if (canvas) canvas.defaultCursor = "grab";
      }
    };

    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        spaceRef.current = false;
        setIsSpacePressed(false);
        panningRef.current = false;
        panStartRef.current = null;
        setIsPanning(false);
        const canvas = canvasRef.current;
        if (canvas && !panningRef.current) canvas.defaultCursor = "default";
      }
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [canvasRef, enabled]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !enabled) return;

    const upperCanvas = canvas.upperCanvasEl;
    if (!upperCanvas) return;

    const getDistance = (
      p1: { x: number; y: number },
      p2: { x: number; y: number },
    ) => Math.hypot(p1.x - p2.x, p1.y - p2.y);

    const getCenter = (
      p1: { x: number; y: number },
      p2: { x: number; y: number },
    ) => ({ x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 });

    const pointers = new Map<number, { x: number; y: number }>();
    let lastPinchDistance = 0;
    let lastPinchCenter: { x: number; y: number } | null = null;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const point = new Point(e.offsetX, e.offsetY);
      const nextZoom = canvas.getZoom() + e.deltaY * -0.001;
      applyZoomAtPoint(nextZoom, point);
    };

    const handlePointerDown = (e: PointerEvent) => {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (pointers.size === 2) {
        const pts = Array.from(pointers.values());
        lastPinchDistance = getDistance(pts[0], pts[1]);
        lastPinchCenter = getCenter(pts[0], pts[1]);
        e.preventDefault();
        return;
      }

      const isMiddleButton = e.button === 1;
      const isSpacePan = e.button === 0 && spaceRef.current;
      if (isMiddleButton || isSpacePan) {
        e.preventDefault();
        e.stopImmediatePropagation();
        panningRef.current = true;
        setIsPanning(true);
        panStartRef.current = { x: e.clientX, y: e.clientY };
        canvas.defaultCursor = "grabbing";
      }
    };

    const handlePointerMove = (e: PointerEvent) => {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (pointers.size === 2 && lastPinchCenter) {
        e.preventDefault();
        const pts = Array.from(pointers.values());
        const distance = getDistance(pts[0], pts[1]);
        const center = getCenter(pts[0], pts[1]);
        const nextZoom = canvas.getZoom() * (distance / lastPinchDistance);
        applyZoomAtPoint(nextZoom, new Point(center.x, center.y));

        const dx = center.x - lastPinchCenter.x;
        const dy = center.y - lastPinchCenter.y;
        const vpt = canvas.viewportTransform;
        if (vpt) {
          vpt[4] += dx;
          vpt[5] += dy;
          canvas.setViewportTransform(vpt);
        }

        lastPinchDistance = distance;
        lastPinchCenter = center;
        return;
      }

      if (panningRef.current && panStartRef.current) {
        e.preventDefault();
        const dx = e.clientX - panStartRef.current.x;
        const dy = e.clientY - panStartRef.current.y;
        const vpt = canvas.viewportTransform;
        if (vpt) {
          vpt[4] += dx;
          vpt[5] += dy;
          canvas.setViewportTransform(vpt);
          canvas.requestRenderAll();
        }
        panStartRef.current = { x: e.clientX, y: e.clientY };
      }
    };

    const endPan = () => {
      panningRef.current = false;
      panStartRef.current = null;
      setIsPanning(false);
      if (!spaceRef.current) canvas.defaultCursor = "default";
      else canvas.defaultCursor = "grab";
    };

    const handlePointerUp = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) {
        lastPinchDistance = 0;
        lastPinchCenter = null;
      }
      if (pointers.size === 0) endPan();
    };

    upperCanvas.style.touchAction = "none";
    upperCanvas.addEventListener("wheel", handleWheel, { passive: false });
    upperCanvas.addEventListener("pointerdown", handlePointerDown, true);
    upperCanvas.addEventListener("pointermove", handlePointerMove);
    upperCanvas.addEventListener("pointerup", handlePointerUp);
    upperCanvas.addEventListener("pointercancel", handlePointerUp);

    syncZoomState();

    return () => {
      upperCanvas.removeEventListener("wheel", handleWheel);
      upperCanvas.removeEventListener("pointerdown", handlePointerDown, true);
      upperCanvas.removeEventListener("pointermove", handlePointerMove);
      upperCanvas.removeEventListener("pointerup", handlePointerUp);
      upperCanvas.removeEventListener("pointercancel", handlePointerUp);
    };
  }, [applyZoomAtPoint, canvasRef, enabled, syncZoomState]);

  return {
    zoom,
    zoomIn,
    zoomOut,
    resetZoom,
    fitToScreen,
    isSpacePressed,
    isPanning,
  };
}
