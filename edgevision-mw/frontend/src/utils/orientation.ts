export type Orientation = "normal" | "mirrored";

/** Flip a pixel-space bbox [x, y, w, h] horizontally. */
export function flipBBoxX(
  bbox: [number, number, number, number],
  width: number,
): [number, number, number, number] {
  const [x, y, w, h] = bbox;
  return [width - x - w, y, w, h];
}

/** Flip normalized polygon points [[x,y], ...] horizontally (0..1 coords). */
export function flipPolygonX(points: number[][]): number[][] {
  return points.map(([x, y]) => [1 - x, y]);
}

/** Flip normalized 3D cuboid corners [[x,y,z], ...] horizontally (0..1 x). */
export function flipCuboidX(corners: number[][]): number[][] {
  return corners.map(([x, y, z]) => [1 - x, y, z]);
}

/** Alias for mask polygon horizontal flip. */
export const flipMaskPolygonX = flipPolygonX;

/** Draw a video frame mirrored horizontally onto a canvas context. */
export function mirrorFrame(
  ctx: CanvasRenderingContext2D,
  width: number,
  source: CanvasImageSource,
): void {
  ctx.save();
  ctx.translate(width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(source, 0, 0);
  ctx.restore();
}

export function orientationFromMirror(mirrored: boolean): Orientation {
  return mirrored ? "mirrored" : "normal";
}

/** Single source of truth for mirror state feeding video CSS, capture, and refs. */
export function isMirrored(mirrorAllowed: boolean, mirrored: boolean): boolean {
  return mirrorAllowed && mirrored;
}

export const MIRROR_STORAGE_KEY = "edgevision.liveAnnotate.mirrored";

export function loadMirrorPreference(): boolean {
  try {
    return localStorage.getItem(MIRROR_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function saveMirrorPreference(mirrored: boolean): void {
  try {
    localStorage.setItem(MIRROR_STORAGE_KEY, mirrored ? "true" : "false");
  } catch {
    /* ignore quota errors */
  }
}

export const ORIENTATION_DEBUG_ENABLED =
  import.meta.env.VITE_ENABLE_ORIENTATION_DEBUG === "true";
