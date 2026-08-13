/**
 * Normalized (0..1) annotation coordinate helpers for Fabric canvas round-trips.
 */

export type NormalizedPoint = [number, number];

export interface NormalizedBBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function bboxFromPolygon(polygon: NormalizedPoint[]): NormalizedBBox {
  if (polygon.length === 0) {
    return { x: 0, y: 0, width: 0.01, height: 0.01 };
  }
  const xs = polygon.map(([x]) => x);
  const ys = polygon.map(([, y]) => y);
  const minX = Math.max(0, Math.min(...xs));
  const minY = Math.max(0, Math.min(...ys));
  const maxX = Math.min(1, Math.max(...xs));
  const maxY = Math.min(1, Math.max(...ys));
  return {
    x: minX,
    y: minY,
    width: Math.max(0.001, maxX - minX),
    height: Math.max(0.001, maxY - minY),
  };
}

export function polygonToCanvas(
  polygon: NormalizedPoint[],
  imgW: number,
  imgH: number,
): { x: number; y: number }[] {
  return polygon.map(([nx, ny]) => ({ x: nx * imgW, y: ny * imgH }));
}

export function polygonFromCanvas(
  points: { x: number; y: number }[],
  imgW: number,
  imgH: number,
): NormalizedPoint[] {
  if (imgW <= 0 || imgH <= 0) return [];
  return points.map((p) => [
    Math.max(0, Math.min(1, p.x / imgW)),
    Math.max(0, Math.min(1, p.y / imgH)),
  ]);
}

export function clampPolygon(polygon: NormalizedPoint[]): NormalizedPoint[] {
  return polygon.map(([x, y]) => [
    Math.max(0, Math.min(1, x)),
    Math.max(0, Math.min(1, y)),
  ]);
}

export interface DetectedObjectPreview {
  class_name?: string;
  taxonomy_label?: string;
  label?: string;
  confidence?: number;
  bbox?: number[];
  mask?: number[][];
}

function normalizePixelBbox(
  bbox: number[],
  frameWidth?: number,
  frameHeight?: number,
): { x: number; y: number; width: number; height: number } | null {
  if (bbox.length < 4) return null;
  const [a, b, c, d] = bbox;
  const fw = frameWidth && frameWidth > 0 ? frameWidth : undefined;
  const fh = frameHeight && frameHeight > 0 ? frameHeight : undefined;

  if (fw && fh) {
    if (c > a && (c > 1 || d > 1 || a > 1 || b > 1)) {
      return {
        x: a / fw,
        y: b / fh,
        width: (c - a) / fw,
        height: (d - b) / fh,
      };
    }
    if (c > 1 || d > 1 || a > 1 || b > 1) {
      return { x: a / fw, y: b / fh, width: c / fw, height: d / fh };
    }
  }

  if (c > 1 || d > 1 || a > 1 || b > 1) {
    return null;
  }

  return { x: a, y: b, width: c, height: d };
}

/** Convert server detected_objects entries into editable studio boxes (with optional mask polygon). */
export function detectedObjectsToBoxes(
  objects: DetectedObjectPreview[],
  frameWidth?: number,
  frameHeight?: number,
): import("../types").BBox[] {
  return objects
    .map((obj) => {
      const label = obj.taxonomy_label || obj.class_name || obj.label || "object";
      const confidence = obj.confidence ?? 1;
      const category = label.split("_")[0];
      const mask = obj.mask;
      const polygon =
        Array.isArray(mask) && mask.length >= 3
          ? clampPolygon(mask.map((p) => [p[0], p[1]] as NormalizedPoint))
          : undefined;

      if (polygon) {
        return {
          ...bboxFromPolygon(polygon),
          label,
          category,
          confidence,
          polygon,
          engine: "live_ai",
        };
      }

      const bbox = obj.bbox;
      if (Array.isArray(bbox) && bbox.length >= 4) {
        const normalized = normalizePixelBbox(bbox, frameWidth, frameHeight);
        if (!normalized) return null;
        return {
          x: Math.max(0, Math.min(1, normalized.x)),
          y: Math.max(0, Math.min(1, normalized.y)),
          width: Math.max(0.001, Math.min(1, normalized.width)),
          height: Math.max(0.001, Math.min(1, normalized.height)),
          label,
          category,
          confidence,
          engine: "live_ai",
        };
      }

      return null;
    })
    .filter((b): b is NonNullable<typeof b> => b !== null);
}
