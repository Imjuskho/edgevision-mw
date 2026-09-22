/**
 * Pure annotation coordinate helpers for overlay rendering and round-trip tests.
 * All coords are in analyzed-frame space (post pixel-level mirror, pre CSS flip).
 */

import { flipBBoxX, flipCuboidX, flipPolygonX } from "./orientation";

export interface DrawAnnotation {
  bbox: [number, number, number, number];
  mask?: number[][];
  bbox_3d?: { corners: number[][] };
}

export interface OverlayPoint {
  x: number;
  y: number;
}

/** Map pixel bbox to overlay SVG coords (1:1 in analyzed space). */
export function bboxToOverlay(
  bbox: [number, number, number, number],
): { x: number; y: number; w: number; h: number } {
  const [x, y, w, h] = bbox;
  return { x, y, w, h };
}

/** Map normalized polygon to overlay pixel points. */
export function polygonToOverlay(
  points: number[][],
  videoWidth: number,
  videoHeight: number,
): OverlayPoint[] {
  return points.map(([nx, ny]) => ({
    x: nx * videoWidth,
    y: ny * videoHeight,
  }));
}

/** Reverse overlay pixel point to normalized coords. */
export function overlayToNormalized(
  point: OverlayPoint,
  videoWidth: number,
  videoHeight: number,
): [number, number] {
  return [point.x / videoWidth, point.y / videoHeight];
}

/** Simulate WS round-trip: mirror capture → flip coords back for storage. */
export function wsCoordinateRoundTrip(
  bbox: [number, number, number, number],
  polygon: number[][] | undefined,
  cuboid: number[][] | undefined,
  frameWidth: number,
  mirrored: boolean,
): {
  bbox: [number, number, number, number];
  polygon?: number[][];
  cuboid?: number[][];
} {
  if (!mirrored) {
    return { bbox, polygon, cuboid };
  }
  const flippedBbox = flipBBoxX(bbox, frameWidth);
  const flippedPoly = polygon ? flipPolygonX(polygon) : undefined;
  const flippedCuboid = cuboid ? flipCuboidX(cuboid) : undefined;
  // round-trip: flip twice restores original analyzed-space coords
  const restoredBbox = flipBBoxX(flippedBbox, frameWidth);
  const restoredPoly = flippedPoly ? flipPolygonX(flippedPoly) : undefined;
  const restoredCuboid = flippedCuboid ? flipCuboidX(flippedCuboid) : undefined;
  return { bbox: restoredBbox, polygon: restoredPoly, cuboid: restoredCuboid };
}

/** Build SVG polygon points string from annotation mask. */
export function maskToSvgPoints(
  mask: number[][],
  videoWidth: number,
  videoHeight: number,
): string {
  return polygonToOverlay(mask, videoWidth, videoHeight)
    .map((p) => `${p.x},${p.y}`)
    .join(" ");
}

/** Project 3D cuboid corners (normalized x,y) to overlay 2D edges. */
export function cuboidEdges2D(
  corners: number[][],
  videoWidth: number,
  videoHeight: number,
): [OverlayPoint, OverlayPoint][] {
  if (corners.length < 8) return [];
  const pts = corners.map(([nx, ny]) => ({
    x: nx * videoWidth,
    y: ny * videoHeight,
  }));
  const edgeIdx: [number, number][] = [
    [0, 1], [1, 2], [2, 3], [3, 0],
    [4, 5], [5, 6], [6, 7], [7, 4],
    [0, 4], [1, 5], [2, 6], [3, 7],
  ];
  return edgeIdx.map(([a, b]) => [pts[a], pts[b]]);
}

/** Top face indices for 3D cuboid highlight. */
export function cuboidTopFace2D(
  corners: number[][],
  videoWidth: number,
  videoHeight: number,
): OverlayPoint[] {
  if (corners.length < 8) return [];
  return [4, 5, 6, 7].map((i) => ({
    x: corners[i][0] * videoWidth,
    y: corners[i][1] * videoHeight,
  }));
}
