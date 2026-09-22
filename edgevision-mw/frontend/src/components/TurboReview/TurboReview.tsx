import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pencil } from 'lucide-react';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import axios from 'axios';
import { Button } from '../ui/Button';
import {
  actionToDecision,
  clampPoint,
  hasRefineChanges,
  mergeRefines,
  type ObjectRefine,
  type ReviewAction,
  updateCuboidCorner,
  updateMaskVertex,
} from '../../utils/reviewRefine';
import { toStyle } from '../../utils/toStyle';

const api = axios.create({ baseURL: '/api/v1' });

interface DetectedObject {
  class_name?: string;
  confidence?: number;
  track_id?: number;
  mask?: number[][];
  bbox_3d?: { corners: number[][] };
  bbox?: number[];
}

interface ReviewImage {
  id: string;
  imageIndex: number;
  url: string;
  thumbnailUrl: string;
  annotations: ReviewAnnotation[];
  detectedObjects: DetectedObject[];
  status: 'pending' | 'approved' | 'rejected' | 'flagged';
  iaaScore: number;
  prelabelConfidence: number;
  nodeId: string;
  captureTime: string;
  liveCapture?: boolean;
  aiDraft?: boolean;
  labelSource?: string;
  orientation?: string;
  depthAvailable?: boolean;
  hasHumanLabels?: boolean;
}

interface ReviewAnnotation {
  id: string;
  className: string;
  confidence: number;
  bbox: [number, number, number, number];
  mask?: number[][];
  bbox_3d?: { corners: number[][]; distance_quality?: string };
}

interface TurboReviewProps {
  sessionId: string;
  datasetId?: string;
  batchSize?: number;
  onComplete?: (stats: ReviewStats) => void;
  onOpenInStudio?: (imageIndex: number) => void;
}

interface ReviewStats {
  total: number;
  approved: number;
  rejected: number;
  flagged: number;
  avgIaa: number;
  durationSeconds: number;
}

type DragTarget =
  | { kind: 'mask'; objectIndex: number; vertexIndex: number }
  | { kind: 'cuboid'; objectIndex: number; cornerIndex: number };

function baselineRefines(objects: DetectedObject[]): ObjectRefine[] {
  return objects.map((obj, object_index) => ({
    object_index,
    mask: obj.mask ? obj.mask.map((p) => [...p]) : undefined,
    bbox_3d: obj.bbox_3d?.corners
      ? { corners: obj.bbox_3d.corners.map((c) => [...c]) }
      : undefined,
  }));
}

function applyRefinesToObjects(
  objects: DetectedObject[],
  refines: ObjectRefine[] | undefined,
): DetectedObject[] {
  if (!refines?.length) return objects;
  return objects.map((obj, idx) => {
    const refine = refines.find((r) => r.object_index === idx);
    if (!refine) return obj;
    return {
      ...obj,
      mask: refine.mask ?? obj.mask,
      bbox_3d: refine.bbox_3d
        ? { corners: refine.bbox_3d.corners }
        : obj.bbox_3d,
    };
  });
}

export const TurboReview: React.FC<TurboReviewProps> = ({
  sessionId,
  datasetId,
  batchSize = 50,
  onComplete,
  onOpenInStudio,
}) => {
  const { t } = useTranslation();
  const [images, setImages] = useState<ReviewImage[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'low_iaa' | 'prelabeled' | 'live_captures'>('all');
  const [sortBy, setSortBy] = useState<'iaa_asc' | 'confidence_desc' | 'time'>('iaa_asc');
  const [showHelp, setShowHelp] = useState(false);
  const [batchActions, setBatchActions] = useState<Record<string, ReviewAction>>({});
  const [refinesByImage, setRefinesByImage] = useState<Record<string, ObjectRefine[]>>({});
  const [baselineByImage, setBaselineByImage] = useState<Record<string, ObjectRefine[]>>({});
  const [refineMode, setRefineMode] = useState(true);
  const [dragTarget, setDragTarget] = useState<DragTarget | null>(null);
  const startTime = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const imageContainerRef = useRef<HTMLDivElement>(null);

  const loadBatch = async () => {
    setIsLoading(true);
    try {
      const res = await api.get(`/studio/sessions/${sessionId}/review-queue?limit=${batchSize}`);
      const raw = res.data.images ?? [];
      const mapped: ReviewImage[] = raw.map((img: Record<string, unknown>) => {
        const detected: DetectedObject[] = (img.detected_objects as DetectedObject[]) ?? [];
        const imageIndex = Number(img.image_index ?? img.index ?? 0);
        return {
          id: String(img.id),
          imageIndex,
          url: `/api/v1/studio/images/${img.id}/serve`,
          thumbnailUrl: `/api/v1/studio/images/${img.id}/serve`,
          annotations: (img.annotations as ReviewAnnotation[]) ?? [],
          detectedObjects: detected,
          status: (img.status as ReviewImage['status']) ?? 'pending',
          iaaScore: 0.95,
          prelabelConfidence: detected[0]?.confidence ?? 0.5,
          nodeId: 'studio',
          captureTime: new Date().toISOString(),
          liveCapture: Boolean(img.live_capture),
          aiDraft: Boolean(img.ai_draft),
          labelSource: typeof img.label_source === 'string' ? img.label_source : undefined,
          orientation: typeof img.orientation === 'string' ? img.orientation : undefined,
          depthAvailable: Boolean(img.depth_available),
          hasHumanLabels: Boolean(img.has_human_labels),
        };
      });
      setImages(mapped);
      const baselines: Record<string, ObjectRefine[]> = {};
      mapped.forEach((img) => {
        baselines[img.id] = baselineRefines(img.detectedObjects);
      });
      setBaselineByImage(baselines);
      setRefinesByImage({});
      setBatchActions({});
      setCurrentIndex(0);
      startTime.current = Date.now();
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const run = async () => {
      await loadBatch();
    };
    void run();
  }, [sessionId]);

  const filteredImages = useMemo(() => {
    let result = [...images];

    if (filter === 'low_iaa') {
      result = result.filter((img) => img.iaaScore < 0.9);
    } else if (filter === 'prelabeled') {
      result = result.filter((img) => img.annotations.length > 0);
    } else if (filter === 'live_captures') {
      result = result.filter((img) => img.liveCapture);
    }

    result.sort((a, b) => {
      if (sortBy === 'iaa_asc') return a.iaaScore - b.iaaScore;
      if (sortBy === 'confidence_desc') return b.prelabelConfidence - a.prelabelConfidence;
      return new Date(a.captureTime).getTime() - new Date(b.captureTime).getTime();
    });

    return result;
  }, [images, filter, sortBy]);

  const currentImage = filteredImages[currentIndex];
  const currentRefines = currentImage ? refinesByImage[currentImage.id] : undefined;
  const currentBaseline = currentImage ? baselineByImage[currentImage.id] : undefined;
  const displayObjects = currentImage
    ? applyRefinesToObjects(
        currentImage.detectedObjects,
        currentRefines ?? currentBaseline,
      )
    : [];
  const isDirty = currentImage
    ? hasRefineChanges(refinesByImage[currentImage.id], baselineByImage[currentImage.id])
    : false;

  const pendingCount = images.filter((img) => img.status === 'pending').length;
  const approvedCount = Object.values(batchActions).filter((a) => a === 'approve').length;
  const rejectedCount = Object.values(batchActions).filter((a) => a === 'reject').length;
  const flaggedCount = Object.values(batchActions).filter((a) => a === 'flag').length;

  const updateRefine = useCallback(
    (imageId: string, objectIndex: number, updater: (prev: ObjectRefine) => ObjectRefine) => {
      setRefinesByImage((prev) => {
        const base = baselineByImage[imageId] ?? [];
        const existing = prev[imageId] ?? base;
        const current = existing.find((r) => r.object_index === objectIndex) ?? {
          object_index: objectIndex,
        };
        const updated = updater(current);
        const merged = mergeRefines(existing, [updated]);
        return { ...prev, [imageId]: merged };
      });
    },
    [baselineByImage],
  );

  const handleOpenInStudio = useCallback(() => {
    if (!currentImage || !onOpenInStudio) return;
    if (isDirty && !window.confirm(t('turboReview.openInStudioDirty'))) {
      return;
    }
    onOpenInStudio(currentImage.imageIndex);
  }, [currentImage, isDirty, onOpenInStudio, t]);

  const clientToNormalized = useCallback((clientX: number, clientY: number): [number, number] | null => {
    const el = imageContainerRef.current;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    return clampPoint(
      (clientX - rect.left) / rect.width,
      (clientY - rect.top) / rect.height,
    );
  }, []);

  const handlePointerDown = (
    e: React.PointerEvent,
    target: DragTarget,
  ) => {
    if (!refineMode || !currentImage) return;
    e.preventDefault();
    e.stopPropagation();
    setDragTarget(target);
    (e.target as Element).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!dragTarget || !currentImage) return;
    const pt = clientToNormalized(e.clientX, e.clientY);
    if (!pt) return;
    const [x, y] = pt;
    const imageId = currentImage.id;

    if (dragTarget.kind === 'mask') {
      updateRefine(imageId, dragTarget.objectIndex, (prev) => ({
        ...prev,
        object_index: dragTarget.objectIndex,
        mask: updateMaskVertex(
          prev.mask ?? currentImage.detectedObjects[dragTarget.objectIndex]?.mask ?? [],
          dragTarget.vertexIndex,
          x,
          y,
        ),
      }));
    } else {
      updateRefine(imageId, dragTarget.objectIndex, (prev) => ({
        ...prev,
        object_index: dragTarget.objectIndex,
        bbox_3d: {
          corners: updateCuboidCorner(
            prev.bbox_3d?.corners
              ?? currentImage.detectedObjects[dragTarget.objectIndex]?.bbox_3d?.corners
              ?? [],
            dragTarget.cornerIndex,
            x,
            y,
          ),
        },
      }));
    }
  };

  const handlePointerUp = () => {
    setDragTarget(null);
  };

  const submitBatch = async () => {
    const actions = Object.entries(batchActions).map(([imageId, action]) => {
      const payload: Record<string, unknown> = {
        image_id: imageId,
        decision: actionToDecision(action),
      };
      const refines = refinesByImage[imageId];
      if (refines?.length && hasRefineChanges(refines, baselineByImage[imageId])) {
        payload.refines = refines;
      }
      return payload;
    });

    await api.post(`/studio/sessions/${sessionId}/review-submit`, { actions });

    const stats: ReviewStats = {
      total: images.length,
      approved: approvedCount,
      rejected: rejectedCount,
      flagged: flaggedCount,
      avgIaa: images.reduce((sum, img) => sum + img.iaaScore, 0) / Math.max(images.length, 1),
      durationSeconds: Math.round((Date.now() - startTime.current) / 1000),
    };

    onComplete?.(stats);
    loadBatch();
  };

  const advance = () => {
    setCurrentIndex((i) => {
      if (i >= filteredImages.length - 1) return i;
      return i + 1;
    });
  };

  const playSound = (type: 'approve' | 'reject' | 'flag') => {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === 'approve') {
      osc.frequency.value = 880;
      gain.gain.value = 0.05;
    } else if (type === 'reject') {
      osc.frequency.value = 220;
      gain.gain.value = 0.05;
    } else {
      osc.frequency.value = 440;
      gain.gain.value = 0.05;
    }

    osc.start();
    osc.stop(ctx.currentTime + 0.1);
  };

  const handleKey = useCallback(
    (key: string, e: KeyboardEvent) => {
      if (!currentImage) return;

      switch (key) {
        case 'ArrowUp':
          e.preventDefault();
          setBatchActions((prev) => ({ ...prev, [currentImage.id]: 'approve' }));
          advance();
          playSound('approve');
          break;
        case 'ArrowDown':
          e.preventDefault();
          setBatchActions((prev) => ({ ...prev, [currentImage.id]: 'reject' }));
          advance();
          playSound('reject');
          break;
        case 'ArrowRight':
          e.preventDefault();
          setCurrentIndex((i) => Math.min(filteredImages.length - 1, i + 1));
          break;
        case 'ArrowLeft':
          e.preventDefault();
          setCurrentIndex((i) => Math.max(0, i - 1));
          break;
        case 'f':
        case 'F':
          setBatchActions((prev) => ({ ...prev, [currentImage.id]: 'flag' }));
          advance();
          playSound('flag');
          break;
        case 'Enter':
          submitBatch();
          break;
        case 'e':
        case 'E':
          if (onOpenInStudio) {
            e.preventDefault();
            handleOpenInStudio();
          }
          break;
        case 'Escape':
          setShowHelp(false);
          break;
        case '?':
          setShowHelp((prev) => !prev);
          break;
      }
    },
    [currentImage, filteredImages.length, batchActions, refinesByImage, baselineByImage, onOpenInStudio, handleOpenInStudio],
  );

  useKeyboardShortcuts(handleKey, { capture: true });

  if (isLoading) {
    return <div className="turbo-review loading">{t('turboReview.loading')}</div>;
  }

  return (
    <div className="turbo-review" ref={containerRef} tabIndex={0}>
      <div className="turbo-header">
        <div>
          <h2>{t('turboReview.title', { batch: sessionId.slice(-4) })}</h2>
          {datasetId && (
            <p className="turbo-dataset-id text-caption text-mono">{datasetId}</p>
          )}
        </div>
        <div className="stats-bar">
          <span className="stat">{currentIndex + 1} / {filteredImages.length}</span>
          <span className="stat approved">✓ {approvedCount}</span>
          <span className="stat rejected">✗ {rejectedCount}</span>
          <span className="stat flagged">⚑ {flaggedCount}</span>
          <span className="stat pending">○ {pendingCount}</span>
          {isDirty && <span className="stat dirty">{t('turboReview.refineDirty')}</span>}
        </div>
      </div>

      <div className="turbo-filters">
        <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
          <option value="all">{t('turboReview.filterAll')}</option>
          <option value="low_iaa">{t('turboReview.filterLowIaa')}</option>
          <option value="prelabeled">{t('turboReview.filterPrelabeled')}</option>
          <option value="live_captures">{t('turboReview.liveCaptures')}</option>
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)}>
          <option value="iaa_asc">{t('turboReview.sortIaa')}</option>
          <option value="confidence_desc">{t('turboReview.sortConfidence')}</option>
          <option value="time">{t('turboReview.sortTime')}</option>
        </select>
        <label className="refine-toggle">
          <input
            type="checkbox"
            checked={refineMode}
            onChange={(e) => setRefineMode(e.target.checked)}
          />
          {t('turboReview.refineMode')}
        </label>
      </div>

      <p className="refine-hint">{t('turboReview.refineProjectionNote')}</p>

      <div className="turbo-main">
        <div className="turbo-current">
          {currentImage && (
            <>
              <div
                className="image-container"
                ref={imageContainerRef}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerLeave={handlePointerUp}
              >
                <img src={currentImage.url} alt="Review" draggable={false} />
                {currentImage.liveCapture && (
                  <p className="live-reviewer-note">{t('turboReview.singleReviewerNote')}</p>
                )}

                <svg
                  className="refine-overlay refine-overlay-svg"
                  viewBox="0 0 1 1"
                  preserveAspectRatio="none"
                >
                  {displayObjects.map((obj, objIdx) => {
                    const mask = obj.mask;
                    const corners = obj.bbox_3d?.corners;
                    return (
                      <g key={`obj-${objIdx}`}>
                        {mask && mask.length >= 3 && mask.length <= 32 && (
                          <>
                            <polygon
                              points={mask.map((p) => `${p[0]},${p[1]}`).join(' ')}
                              fill="rgba(0,200,255,0.15)"
                              stroke="cyan"
                              strokeWidth={0.003}
                            />
                            {refineMode &&
                              mask.map((p, vi) => (
                                <circle
                                  key={`m-${objIdx}-${vi}`}
                                  cx={p[0]}
                                  cy={p[1]}
                                  r={0.012}
                                  fill="#00e5ff"
                                  stroke="#fff"
                                  strokeWidth={0.002}
                                  className="refine-handle"
                                  onPointerDown={(e) =>
                                    handlePointerDown(e, {
                                      kind: 'mask',
                                      objectIndex: objIdx,
                                      vertexIndex: vi,
                                    })
                                  }
                                />
                              ))}
                          </>
                        )}
                        {corners && corners.length === 8 && (
                          <>
                            <polygon
                              points={corners.slice(0, 4).map((c) => `${c[0]},${c[1]}`).join(' ')}
                              fill="none"
                              stroke="orange"
                              strokeWidth={0.003}
                            />
                            {refineMode &&
                              corners.map((c, ci) => (
                                <circle
                                  key={`c-${objIdx}-${ci}`}
                                  cx={c[0]}
                                  cy={c[1]}
                                  r={0.012}
                                  fill="#ff9800"
                                  stroke="#fff"
                                  strokeWidth={0.002}
                                  className="refine-handle"
                                  onPointerDown={(e) =>
                                    handlePointerDown(e, {
                                      kind: 'cuboid',
                                      objectIndex: objIdx,
                                      cornerIndex: ci,
                                    })
                                  }
                                />
                              ))}
                          </>
                        )}
                      </g>
                    );
                  })}
                </svg>

                {currentImage.annotations.map((ann, annIdx) => (
                  <div
                    key={ann.id ?? `ann-${annIdx}`}
                    className="annotation-overlay"
                    style={toStyle({
                      left: `${ann.bbox[0] * 100}%`,
                      top: `${ann.bbox[1] * 100}%`,
                      width: `${ann.bbox[2] * 100}%`,
                      height: `${ann.bbox[3] * 100}%`,
                    })}
                  >
                    <span className="ann-label">
                      {ann.className} ({(ann.confidence * 100).toFixed(0)}%)
                    </span>
                  </div>
                ))}

                {batchActions[currentImage.id] && (
                  <div className={`action-indicator ${batchActions[currentImage.id]}`}>
                    {batchActions[currentImage.id] === 'approve' && t('turboReview.approved')}
                    {batchActions[currentImage.id] === 'reject' && t('turboReview.rejected')}
                    {batchActions[currentImage.id] === 'flag' && t('turboReview.flagged')}
                  </div>
                )}
              </div>

              <div className="image-meta">
                <span>Node: {currentImage.nodeId}</span>
                <span>IAA: {(currentImage.iaaScore * 100).toFixed(1)}%</span>
                <span>Confidence: {(currentImage.prelabelConfidence * 100).toFixed(1)}%</span>
                <span>{new Date(currentImage.captureTime).toLocaleString()}</span>
                {currentImage.aiDraft && (
                  <span className="chip chip-info">{t('turboReview.aiDraftChip')}</span>
                )}
                {currentImage.orientation && (
                  <span className="chip">{t('turboReview.orientationChip', { mode: currentImage.orientation })}</span>
                )}
                {currentImage.liveCapture && (
                  <span className="chip">
                    {t('turboReview.depthChip', {
                      quality: currentImage.depthAvailable ? 'onnx' : 'heuristic',
                    })}
                  </span>
                )}
                {onOpenInStudio && (
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Pencil size={14} />}
                    onClick={handleOpenInStudio}
                  >
                    {t('turboReview.openInStudio')}
                  </Button>
                )}
              </div>
            </>
          )}
        </div>

        <div className="turbo-strip">
          {filteredImages.map((img, idx) => (
            <div
              key={img.id}
              className={`strip-thumb ${idx === currentIndex ? 'active' : ''} ${batchActions[img.id] || ''}`}
              onClick={() => setCurrentIndex(idx)}
            >
              <img src={img.thumbnailUrl} alt="" />
              {batchActions[img.id] && (
                <div className={`thumb-badge ${batchActions[img.id]}`}>
                  {batchActions[img.id] === 'approve' ? '✓' : batchActions[img.id] === 'reject' ? '✗' : '⚑'}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="turbo-actions">
        {onOpenInStudio && currentImage && (
          <Button variant="outline" size="sm" icon={<Pencil size={14} />} onClick={handleOpenInStudio}>
            {t('turboReview.openInStudio')}
          </Button>
        )}
        <button className="btn-approve" onClick={() => handleKey('ArrowUp', new KeyboardEvent('keydown'))}>
          ↑ {t('turboReview.approve')}
        </button>
        <button className="btn-reject" onClick={() => handleKey('ArrowDown', new KeyboardEvent('keydown'))}>
          ↓ {t('turboReview.reject')}
        </button>
        <button className="btn-flag" onClick={() => handleKey('f', new KeyboardEvent('keydown'))}>
          F {t('turboReview.flag')}
        </button>
        <button className="btn-submit" onClick={submitBatch}>
          {t('turboReview.submitBatch', { count: Object.keys(batchActions).length })}
        </button>
      </div>

      {showHelp && (
        <div className="help-overlay" onClick={() => setShowHelp(false)}>
          <div className="help-content">
            <h3>{t('turboReview.helpTitle')}</h3>
            <table>
              <tbody>
                <tr><td><kbd>↑</kbd></td><td>{t('turboReview.helpApprove')}</td></tr>
                <tr><td><kbd>↓</kbd></td><td>{t('turboReview.helpReject')}</td></tr>
                <tr><td><kbd>←</kbd></td><td>{t('turboReview.helpPrev')}</td></tr>
                <tr><td><kbd>→</kbd></td><td>{t('turboReview.helpNext')}</td></tr>
                <tr><td><kbd>F</kbd></td><td>{t('turboReview.helpFlag')}</td></tr>
                <tr><td><kbd>Enter</kbd></td><td>{t('turboReview.helpSubmit')}</td></tr>
                <tr><td><kbd>?</kbd></td><td>{t('turboReview.helpToggle')}</td></tr>
                {onOpenInStudio && (
                  <tr><td><kbd>E</kbd></td><td>{t('turboReview.helpOpenStudio')}</td></tr>
                )}
                <tr><td><kbd>Esc</kbd></td><td>{t('turboReview.helpClose')}</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {currentIndex >= filteredImages.length - 1 && Object.keys(batchActions).length > 0 && (
        <div className="completion-modal">
          <h3>{t('turboReview.batchComplete')}</h3>
          <p>{t('turboReview.batchCompleteDesc', { count: filteredImages.length })}</p>
          <div className="completion-stats">
            <div>✓ {t('turboReview.approved')}: {approvedCount}</div>
            <div>✗ {t('turboReview.rejected')}: {rejectedCount}</div>
            <div>⚑ {t('turboReview.flagged')}: {flaggedCount}</div>
          </div>
          <button onClick={submitBatch}>{t('turboReview.submitAndNext')}</button>
        </div>
      )}
    </div>
  );
};
