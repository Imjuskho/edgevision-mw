import type { BBox } from "../types";

export function shallowEqualBoxes(a: BBox[], b: BBox[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const ai = a[i], bi = b[i];
    if (ai.label !== bi.label ||
        ai.x !== bi.x || ai.y !== bi.y || ai.width !== bi.width || ai.height !== bi.height ||
        ai.confidence !== bi.confidence) return false;
    const ap = ai.polygon, bp = bi.polygon;
    if ((!ap && bp) || (ap && !bp)) return false;
    if (ap && bp && ap.length !== bp.length) return false;
    if (ap && bp) {
      for (let j = 0; j < ap.length; j++) {
        if (ap[j][0] !== bp[j][0] || ap[j][1] !== bp[j][1]) return false;
      }
    }
  }
  return true;
}

export function cloneBoxes(boxes: BBox[]): BBox[] {
  return boxes.map((b) => ({
    ...b,
    polygon: b.polygon ? b.polygon.map((p) => [p[0], p[1]] as [number, number]) : undefined,
  }));
}
