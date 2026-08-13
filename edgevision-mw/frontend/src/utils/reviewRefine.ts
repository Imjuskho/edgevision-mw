/** TurboReview QA refine helpers — normalized 0..1 coords in analyzed-frame space. */

export type ReviewAction = 'approve' | 'reject' | 'flag';
export type ReviewDecision = 'approved' | 'rejected' | 'flagged';

const ACTION_TO_DECISION: Record<ReviewAction, ReviewDecision> = {
  approve: 'approved',
  reject: 'rejected',
  flag: 'flagged',
};

const LEGACY_ACTION_ALIASES: Record<string, ReviewDecision> = {
  approve: 'approved',
  reject: 'rejected',
  flag: 'flagged',
  approved: 'approved',
  rejected: 'rejected',
  flagged: 'flagged',
};

/** Map TurboReview batch action to API decision string. */
export function actionToDecision(action: ReviewAction): ReviewDecision {
  return ACTION_TO_DECISION[action];
}

/** Resolve decision from submit payload (prefer `decision`, fall back to legacy `action`). */
export function resolveDecision(payload: {
  decision?: string;
  action?: string;
}): ReviewDecision | null {
  const decision = payload.decision;
  if (decision && decision in LEGACY_ACTION_ALIASES) {
    return LEGACY_ACTION_ALIASES[decision] as ReviewDecision;
  }
  const action = payload.action;
  if (action && action in LEGACY_ACTION_ALIASES) {
    return LEGACY_ACTION_ALIASES[action] as ReviewDecision;
  }
  return null;
}

export interface ObjectRefine {
  object_index: number;
  mask?: number[][];
  bbox_3d?: { corners: number[][] };
}

/** Merge per-object refines by object_index (later updates win per field). */
export function mergeRefines(
  existing: ObjectRefine[] | undefined,
  updates: ObjectRefine[],
): ObjectRefine[] {
  const byIndex = new Map<number, ObjectRefine>();
  for (const r of existing ?? []) {
    byIndex.set(r.object_index, { ...r });
  }
  for (const u of updates) {
    const prev = byIndex.get(u.object_index) ?? { object_index: u.object_index };
    byIndex.set(u.object_index, {
      object_index: u.object_index,
      mask: u.mask ?? prev.mask,
      bbox_3d: u.bbox_3d ?? prev.bbox_3d,
    });
  }
  return Array.from(byIndex.values()).sort((a, b) => a.object_index - b.object_index);
}

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function clampPoint(x: number, y: number): [number, number] {
  return [clamp01(x), clamp01(y)];
}

export function updateMaskVertex(
  mask: number[][],
  vertexIndex: number,
  x: number,
  y: number,
): number[][] {
  const [cx, cy] = clampPoint(x, y);
  return mask.map((p, i) => (i === vertexIndex ? [cx, cy] : [p[0], p[1]]));
}

export function updateCuboidCorner(
  corners: number[][],
  cornerIndex: number,
  x: number,
  y: number,
): number[][] {
  const [cx, cy] = clampPoint(x, y);
  return corners.map((c, i) =>
    i === cornerIndex ? [cx, cy, c[2] ?? 0] : [c[0], c[1], c[2] ?? 0],
  );
}

/** True when any refine differs from baseline detected_objects for an image. */
export function hasRefineChanges(
  refines: ObjectRefine[] | undefined,
  baseline: ObjectRefine[] | undefined,
): boolean {
  if (!refines?.length) return false;
  if (!baseline?.length) return refines.some((r) => r.mask || r.bbox_3d);
  return refines.some((r) => {
    const base = baseline.find((b) => b.object_index === r.object_index);
    if (!base) return Boolean(r.mask || r.bbox_3d);
    if (r.mask && JSON.stringify(r.mask) !== JSON.stringify(base.mask)) return true;
    if (r.bbox_3d && JSON.stringify(r.bbox_3d) !== JSON.stringify(base.bbox_3d)) return true;
    return false;
  });
}
