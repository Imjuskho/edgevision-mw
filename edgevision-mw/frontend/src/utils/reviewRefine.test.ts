import { describe, expect, it } from 'vitest';
import {
  actionToDecision,
  clampPoint,
  hasRefineChanges,
  mergeRefines,
  resolveDecision,
  updateCuboidCorner,
  updateMaskVertex,
} from './reviewRefine';

describe('reviewRefine', () => {
  it('maps batch actions to API decisions', () => {
    expect(actionToDecision('approve')).toBe('approved');
    expect(actionToDecision('reject')).toBe('rejected');
    expect(actionToDecision('flag')).toBe('flagged');
  });

  it('resolveDecision prefers decision over legacy action', () => {
    expect(resolveDecision({ decision: 'approved', action: 'reject' })).toBe('approved');
    expect(resolveDecision({ action: 'approve' })).toBe('approved');
    expect(resolveDecision({ action: 'flag' })).toBe('flagged');
    expect(resolveDecision({})).toBeNull();
  });

  it('mergeRefines replaces refines key only per object_index', () => {
    const merged = mergeRefines(
      [{ object_index: 0, mask: [[0.1, 0.2]] }],
      [{ object_index: 0, mask: [[0.3, 0.4]] }, { object_index: 1, bbox_3d: { corners: [[0, 0, 0]] } }],
    );
    expect(merged).toHaveLength(2);
    expect(merged[0].mask).toEqual([[0.3, 0.4]]);
    expect(merged[1].bbox_3d?.corners).toEqual([[0, 0, 0]]);
  });

  it('clampPoint keeps coords in 0..1', () => {
    expect(clampPoint(-0.1, 1.5)).toEqual([0, 1]);
  });

  it('updateMaskVertex updates one vertex', () => {
    const mask = [
      [0, 0],
      [1, 0],
      [1, 1],
    ];
    const next = updateMaskVertex(mask, 1, 0.5, 0.25);
    expect(next[1]).toEqual([0.5, 0.25]);
    expect(next[0]).toEqual([0, 0]);
  });

  it('updateCuboidCorner preserves z', () => {
    const corners = Array.from({ length: 8 }, (_, i) => [0.1 * i, 0.2, 0.5]);
    const next = updateCuboidCorner(corners, 3, 0.9, 0.1);
    expect(next[3]).toEqual([0.9, 0.1, 0.5]);
  });

  it('hasRefineChanges detects mask edits', () => {
    const baseline = [{ object_index: 0, mask: [[0, 0], [1, 1]] }];
    const edited = [{ object_index: 0, mask: [[0.1, 0], [1, 1]] }];
    expect(hasRefineChanges(edited, baseline)).toBe(true);
    expect(hasRefineChanges(baseline, baseline)).toBe(false);
  });
});
