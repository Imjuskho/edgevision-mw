export const MIN_ZOOM = 0.25;
export const MAX_ZOOM = 8;
export const ZOOM_STEP = 1.25;

export function clampZoom(zoom: number): number {
  return Math.min(Math.max(zoom, MIN_ZOOM), MAX_ZOOM);
}

export function stepZoom(current: number, direction: "in" | "out"): number {
  const next =
    direction === "in" ? current * ZOOM_STEP : current / ZOOM_STEP;
  return clampZoom(next);
}

export function formatZoomPercent(zoom: number): string {
  return `${Math.round(zoom * 100)}%`;
}

/** Uniform viewport transform that fits content inside a container with optional padding. */
export function computeFitViewportTransform(
  contentW: number,
  contentH: number,
  containerW: number,
  containerH: number,
  padding = 8,
): [number, number, number, number, number, number] {
  if (contentW <= 0 || contentH <= 0 || containerW <= 0 || containerH <= 0) {
    return [1, 0, 0, 1, 0, 0];
  }

  const availW = Math.max(containerW - padding * 2, 1);
  const availH = Math.max(containerH - padding * 2, 1);
  const zoom = clampZoom(Math.min(availW / contentW, availH / contentH));
  const panX = (containerW - contentW * zoom) / 2;
  const panY = (containerH - contentH * zoom) / 2;
  return [zoom, 0, 0, zoom, panX, panY];
}

export function identityViewportTransform(): [
  number,
  number,
  number,
  number,
  number,
  number,
] {
  return [1, 0, 0, 1, 0, 0];
}
