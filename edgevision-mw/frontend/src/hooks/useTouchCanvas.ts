// src/hooks/useTouchCanvas.ts
// Pinch zoom, two-finger pan, and stylus support for Fabric.js on tablets

import { useEffect, useRef, useCallback } from 'react';
import { Canvas, Point } from 'fabric';

interface TouchState {
  pointers: Map<number, { x: number; y: number }>;
  lastDistance: number;
  lastCenter: { x: number; y: number } | null;
  isPinching: boolean;
  isPanning: boolean;
}

export function useTouchCanvas(canvasRef: React.RefObject<Canvas | null>) {
  const touchState = useRef<TouchState>({
    pointers: new Map(),
    lastDistance: 0,
    lastCenter: null,
    isPinching: false,
    isPanning: false,
  });

  const getDistance = useCallback((p1: { x: number; y: number }, p2: { x: number; y: number }) => {
    return Math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2);
  }, []);

  const getCenter = useCallback((p1: { x: number; y: number }, p2: { x: number; y: number }) => {
    return { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
  }, []);

  const handlePointerDown = useCallback((e: PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const state = touchState.current;
    state.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (state.pointers.size === 2) {
      const points = Array.from(state.pointers.values());
      state.lastDistance = getDistance(points[0], points[1]);
      state.lastCenter = getCenter(points[0], points[1]);
      state.isPinching = true;
      state.isPanning = false;
      e.preventDefault();
    } else if (state.pointers.size === 1 && e.pointerType === 'pen') {
      // Stylus: let Fabric handle it, but track for pressure
      state.isPanning = false;
    }
  }, [canvasRef, getDistance, getCenter]);

  const handlePointerMove = useCallback((e: PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const state = touchState.current;
    if (!state.pointers.has(e.pointerId)) return;

    state.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (state.pointers.size === 2 && state.isPinching) {
      e.preventDefault();
      const points = Array.from(state.pointers.values());
      const distance = getDistance(points[0], points[1]);
      const center = getCenter(points[0], points[1]);

      // Zoom
      const zoom = canvas.getZoom() * (distance / state.lastDistance);
      const clampedZoom = Math.min(Math.max(zoom, 0.5), 4);

      canvas.zoomToPoint(
        new Point(center.x, center.y),
        clampedZoom
      );

      // Pan to keep center stable
      if (state.lastCenter) {
        const dx = center.x - state.lastCenter.x;
        const dy = center.y - state.lastCenter.y;
        const vpt = canvas.viewportTransform;
        if (vpt) {
          vpt[4] += dx;
          vpt[5] += dy;
          canvas.setViewportTransform(vpt);
        }
      }

      state.lastDistance = distance;
      state.lastCenter = center;
    } else if (state.pointers.size === 1 && state.isPanning) {
      // Single finger pan (when not drawing)
      const point = state.pointers.get(e.pointerId);
      if (point) {
        const dx = e.clientX - point.x;
        const dy = e.clientY - point.y;
        const vpt = canvas.viewportTransform;
        if (vpt) {
          vpt[4] += dx;
          vpt[5] += dy;
          canvas.setViewportTransform(vpt);
        }
        state.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      }
    }
  }, [canvasRef, getDistance, getCenter]);

  const handlePointerUp = useCallback((e: PointerEvent) => {
    const state = touchState.current;
    state.pointers.delete(e.pointerId);

    if (state.pointers.size < 2) {
      state.isPinching = false;
      state.lastDistance = 0;
      state.lastCenter = null;
    }
    if (state.pointers.size === 0) {
      state.isPanning = false;
    }
  }, []);

  const handleWheel = useCallback((e: WheelEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    e.preventDefault();
    const zoom = canvas.getZoom() + e.deltaY * -0.001;
    const clampedZoom = Math.min(Math.max(zoom, 0.5), 4);
    canvas.zoomToPoint(new Point(e.offsetX, e.offsetY), clampedZoom);
  }, [canvasRef]);

  // Stylus pressure support
  const handleStylus = useCallback((e: PointerEvent) => {
    if (e.pointerType !== 'pen') return;
    const canvas = canvasRef.current;
    if (canvas) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (canvas as any)._stylusPressure = e.pressure || 0.5;
    }
  }, [canvasRef]);

  useEffect(() => {
    const el = canvasRef.current?.upperCanvasEl;
    if (!el) return;

    el.style.setProperty('touch-action', 'none'); // Disable default browser touch actions

    el.addEventListener('pointerdown', handlePointerDown);
    el.addEventListener('pointermove', handlePointerMove);
    el.addEventListener('pointerup', handlePointerUp);
    el.addEventListener('pointercancel', handlePointerUp);
    el.addEventListener('wheel', handleWheel, { passive: false });
    el.addEventListener('pointermove', handleStylus);

    return () => {
      el.removeEventListener('pointerdown', handlePointerDown);
      el.removeEventListener('pointermove', handlePointerMove);
      el.removeEventListener('pointerup', handlePointerUp);
      el.removeEventListener('pointercancel', handlePointerUp);
      el.removeEventListener('wheel', handleWheel);
      el.removeEventListener('pointermove', handleStylus);
    };
  }, [handlePointerDown, handlePointerMove, handlePointerUp, handleWheel, handleStylus, canvasRef]);

  return {
    resetView: useCallback(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.setViewportTransform([1, 0, 0, 1, 0, 0]);
      canvas.setZoom(1);
    }, [canvasRef]),
  };
}
