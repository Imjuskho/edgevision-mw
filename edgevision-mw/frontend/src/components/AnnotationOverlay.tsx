import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { LiveAnnotation } from "../hooks/useLiveAnnotation";
import {
  cuboidEdges2D,
  cuboidTopFace2D,
  maskToSvgPoints,
} from "../utils/drawAnnotations";

export type OverlayDisplayMode = "boxes" | "masks" | "both" | "3d" | "all";

interface Props {
  annotations: LiveAnnotation[];
  videoWidth: number;
  videoHeight: number;
  displayMode?: OverlayDisplayMode;
  depthAvailable?: boolean;
  previewMirrored?: boolean;
  selectedTrackId?: number | null;
}

const PALETTE = [
  "#FF3838", "#FF9D00", "#FFD726", "#36D64A", "#00C2FF",
  "#006BFF", "#8B5CF6", "#FF63B7", "#FF448F", "#00E5FF",
  "#A3E635", "#F472B6", "#C084FC", "#38BDF8", "#FB923C",
];

const TRACK_COLORS = [
  "#FF3838", "#00C2FF", "#36D64A", "#FFD726", "#8B5CF6",
  "#FF63B7", "#FF9D00", "#006BFF", "#00E5FF", "#FF448F",
];

function getClassColor(label: string): string {
  let hash = 0;
  for (let i = 0; i < label.length; i++) {
    hash = label.charCodeAt(i) + ((hash << 5) - hash);
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

function getTrackColor(trackId: number): string {
  return TRACK_COLORS[Math.abs(trackId) % TRACK_COLORS.length];
}

function formatCompactLabel(ann: LiveAnnotation): string {
  const pct = (ann.confidence * 100).toFixed(0);
  const label = ann.taxonomy_label || ann.class_name;
  return `${label} ${pct}%`;
}

/** Exponential ease-out: fast drop near camera, gentle fade for distant objects. */
function computeDepthOpacity(distanceM?: number, bboxY?: number, bboxH?: number, videoH?: number): number {
  if (distanceM != null && distanceM > 0) {
    const norm = Math.min(distanceM / 80, 1);
    const curved = 1 - Math.pow(norm, 1.8);
    return 0.45 + curved * 0.55;
  }
  if (bboxY != null && bboxH != null && videoH && videoH > 0) {
    const bottomRatio = (bboxY + bboxH) / videoH;
    return 0.55 + bottomRatio * 0.45;
  }
  return 0.88;
}

interface LabelRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

function rectsOverlap(a: LabelRect, b: LabelRect): boolean {
  return !(a.x + a.w < b.x || b.x + b.w < a.x || a.y + a.h < b.y || b.y + b.h < a.y);
}

function pickBestLabelPosition(
  boxX: number,
  boxY: number,
  boxW: number,
  boxH: number,
  labelW: number,
  labelH: number,
  placed: LabelRect[],
  vw: number,
  vh: number,
): { lx: number; ly: number } {
  const gap = 4;
  const candidates: { x: number; y: number; score: number }[] = [
    { x: boxX, y: boxY - labelH - gap, score: 0 },
    { x: boxX + boxW - labelW, y: boxY - labelH - gap, score: 1 },
    { x: boxX, y: boxY + boxH + gap, score: 2 },
    { x: boxX + boxW - labelW, y: boxY + boxH + gap, score: 3 },
    { x: boxX + boxW + gap, y: boxY, score: 4 },
    { x: boxX - labelW - gap, y: boxY, score: 5 },
  ];

  let bestX = candidates[0].x;
  let bestY = candidates[0].y;
  let bestScore = Infinity;

  for (const c of candidates) {
    const rect: LabelRect = {
      x: Math.max(0, Math.min(c.x, vw - labelW)),
      y: Math.max(0, Math.min(c.y, vh - labelH)),
      w: labelW,
      h: labelH,
    };
    let collisions = 0;
    for (const p of placed) {
      if (rectsOverlap(rect, p)) collisions++;
    }
    const onScreen = rect.x >= 0 && rect.y >= 0 && rect.x + rect.w <= vw && rect.y + rect.h <= vh;
    const score = collisions * 100 + (onScreen ? 0 : 50) + c.score;
    if (score < bestScore) {
      bestScore = score;
      bestX = rect.x;
      bestY = rect.y;
    }
  }
  return { lx: bestX, ly: bestY };
}

export default function AnnotationOverlay({
  annotations,
  videoWidth,
  videoHeight,
  displayMode = "both",
  depthAvailable = false,
  previewMirrored = false,
  selectedTrackId = null,
}: Props) {
  const overlayRef = useRef<SVGSVGElement>(null);
  const { t } = useTranslation();

  useEffect(() => {
    const el = overlayRef.current;
    if (!el) return;
    const style = window.getComputedStyle(el);
    if (style.transform && style.transform !== "none") {
      console.error("AnnotationOverlay invariant: overlay must not have CSS transform", { transform: style.transform });
    }
  }, [previewMirrored, annotations.length]);

  const sorted = useMemo(() => {
    return [...annotations].sort((a, b) => {
      const aBottom = a.bbox[1] + a.bbox[3];
      const bBottom = b.bbox[1] + b.bbox[3];
      return bBottom - aBottom;
    });
  }, [annotations]);

  const summary = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const ann of sorted) {
      const label = ann.taxonomy_label || ann.class_name;
      counts[label] = (counts[label] || 0) + 1;
    }
    return Object.entries(counts)
      .map(([k, v]) => (v > 1 ? `${v}×${k}` : k))
      .join("  ");
  }, [sorted]);

  if (annotations.length === 0 || videoWidth === 0 || videoHeight === 0) return null;

  const showBoxes = displayMode === "boxes" || displayMode === "both" || displayMode === "all";
  const showMasks = displayMode === "masks" || displayMode === "both" || displayMode === "all";
  const show3d = displayMode === "3d" || displayMode === "all";
  const has3d = annotations.some((a) => a.bbox_3d?.corners?.length === 8);
  const showBoxFallback = show3d && !showBoxes && !has3d;
  const isFocus = selectedTrackId != null;

  const placedLabels: LabelRect[] = [];

  const pulseAnimId = "sel-pulse";

  return (
    <svg
      ref={overlayRef}
      className="live-annotate-overlay"
      data-preview-mirrored={previewMirrored ? "true" : "false"}
      data-coordinate-space="analyzed"
      viewBox={`0 0 ${videoWidth} ${videoHeight}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <filter id="ann-shadow" x="-10%" y="-10%" width="120%" height="120%">
          <feDropShadow dx="0" dy="1" stdDeviation="1.5" floodColor="#000" floodOpacity="0.6" />
        </filter>
        <filter id="badge-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor="#fff" floodOpacity="0.35" />
        </filter>
        <linearGradient id="ground-shadow-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#000" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#000" stopOpacity="0" />
        </linearGradient>
        <style>{`
          @keyframes ${pulseAnimId} {
            0%, 100% { stroke-opacity: 0.9; stroke-width: 2.5; }
            50% { stroke-opacity: 0.5; stroke-width: 1.5; }
          }
          .ann-selected { animation: ${pulseAnimId} 1.5s ease-in-out infinite; }
        `}</style>
      </defs>

      {show3d && has3d && (
        <text x={8} y={videoHeight - 8} fill="rgba(255,255,255,0.55)" fontSize={9} filter="url(#ann-shadow)">
          {depthAvailable ? t("liveAnnotate.bbox3dDepthOnnx") : t("liveAnnotate.bbox3dLimitation")}
        </text>
      )}

      {sorted.map((ann) => {
        const isTrack = ann.track_id != null;
        const isThisSelected = isTrack && ann.track_id === selectedTrackId;
        const color = isTrack ? getTrackColor(ann.track_id!) : getClassColor(ann.taxonomy_label || ann.class_name);
        const [x, y, w, h] = ann.bbox;
        const depthAlpha = computeDepthOpacity(ann.distance_m, y, h, videoHeight);
        const dimmed = isFocus && !isThisSelected;
        const alpha = dimmed ? 0.18 : depthAlpha;

        const maskPoints = ann.mask?.length ? maskToSvgPoints(ann.mask, videoWidth, videoHeight) : null;
        const cuboid = ann.bbox_3d?.corners;
        const edges = cuboid && show3d && cuboid.length >= 8 ? cuboidEdges2D(cuboid, videoWidth, videoHeight) : [];
        const topFace = cuboid && show3d && cuboid.length >= 8 ? cuboidTopFace2D(cuboid, videoWidth, videoHeight) : [];
        const drawBoxes = showBoxes || showBoxFallback;

        const labelText = formatCompactLabel(ann);
        const labelW = labelText.length * 6.2 + 14;
        const labelH = 17;
        const { lx, ly } = drawBoxes
          ? pickBestLabelPosition(x, y, w, h, labelW, labelH, placedLabels, videoWidth, videoHeight)
          : { lx: x, ly: y };
        if (drawBoxes) {
          placedLabels.push({ x: lx, y: ly, w: labelW, h: labelH });
        }

        return (
          <g key={isTrack ? `t${ann.track_id}` : `${ann.class_name}-${ann.bbox.join(",")}`} opacity={alpha} style={{ transition: "opacity 0.15s ease-out" }}>
            {showMasks && maskPoints && (
              <polygon
                points={maskPoints}
                fill={color}
                fillOpacity={dimmed ? 0.03 : 0.1}
                stroke={color}
                strokeWidth={0.8}
                strokeOpacity={dimmed ? 0.1 : 0.35}
                strokeDasharray="4 2"
              />
            )}

            {show3d && edges.map(([a, b], ei) => {
              const isHidden = ei >= 8;
              return (
                <line
                  key={`edge-${ei}`}
                  x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke={color}
                  strokeWidth={isHidden ? 0.6 : 1.4}
                  strokeDasharray={isHidden ? "2 2" : undefined}
                  strokeOpacity={dimmed ? 0.12 : (isHidden ? 0.35 : 0.75)}
                />
              );
            })}
            {show3d && topFace.length === 4 && (
              <polygon
                points={topFace.map((p) => `${p.x},${p.y}`).join(" ")}
                fill={color}
                fillOpacity={dimmed ? 0.02 : 0.1}
                stroke={color}
                strokeWidth={0.8}
                strokeOpacity={dimmed ? 0.08 : 0.45}
              />
            )}

            {drawBoxes && (
              <>
                <rect
                  x={x} y={y} width={w} height={h}
                  stroke={color}
                  strokeWidth={isThisSelected ? 2.5 : 1.6}
                  fill="none"
                  strokeLinecap="round"
                  strokeDasharray={isTrack ? undefined : "4 2"}
                  rx={2}
                  className={isThisSelected ? "ann-selected" : undefined}
                />

                <rect
                  x={lx} y={ly}
                  width={labelW} height={labelH}
                  fill="#111"
                  fillOpacity={0.82}
                  rx={3}
                />
                <rect
                  x={lx} y={ly}
                  width={3} height={labelH}
                  fill={color}
                  fillOpacity={0.9}
                  rx={1.5}
                />

                {isTrack && (
                  <circle
                    cx={lx + 10} cy={ly + labelH / 2} r={6.5}
                    fill={color}
                    fillOpacity={isThisSelected ? 1 : 0.85}
                    stroke={isThisSelected ? "#fff" : "none"}
                    strokeWidth={isThisSelected ? 1.5 : 0}
                    filter={isThisSelected ? "url(#badge-glow)" : undefined}
                  />
                )}
                {isTrack && (
                  <text
                    x={lx + 10} y={ly + labelH / 2}
                    fill="#fff" fontSize={7.5} fontWeight={700}
                    textAnchor="middle" dominantBaseline="central"
                  >
                    {ann.track_id}
                  </text>
                )}

                <text
                  x={isTrack ? lx + 20 : lx + 7}
                  y={ly + labelH / 2}
                  fill="#fff"
                  fontSize={9.5}
                  fontWeight={500}
                  dominantBaseline="central"
                  filter="url(#ann-shadow)"
                >
                  {labelText}
                </text>

                {ann.distance_m != null && ann.distance_m > 0 && (
                  <>
                    <rect
                      x={lx + labelW + 3} y={ly + 1}
                      width={30} height={labelH - 2}
                      fill={color}
                      fillOpacity={0.18}
                      rx={3}
                    />
                    <text
                      x={lx + labelW + 18} y={ly + labelH / 2}
                      fill={color} fontSize={8.5} fontWeight={600}
                      textAnchor="middle" dominantBaseline="central"
                    >
                      {ann.distance_m < 10 ? ann.distance_m.toFixed(1) : Math.round(ann.distance_m)}m
                    </text>
                  </>
                )}
              </>
            )}
          </g>
        );
      })}

      <g>
        <rect
          x={8} y={videoHeight - 30}
          width={Math.min(summary.length * 6.2 + 20, videoWidth - 16)}
          height={22}
          fill="#111" fillOpacity={0.72}
          rx={4}
        />
        <text
          x={16} y={videoHeight - 16}
          fill="rgba(255,255,255,0.8)"
          fontSize={9.5}
          fontWeight={500}
        >
          {annotations.length} {summary && `· ${summary}`}
        </text>
      </g>
    </svg>
  );
}
