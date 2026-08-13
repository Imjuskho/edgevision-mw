import { useEffect, useRef } from "react";
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
  orientation?: "normal" | "mirrored";
  /**
   * When true, the video element uses CSS scaleX(-1) for user comfort.
   * The overlay must NOT receive the same CSS mirror: captureFrame() already
   * flips pixels before inference/save, so annotation coords are in analyzed
   * frame space and align with the mirrored preview without overlay CSS flip.
   */
  previewMirrored?: boolean;
}

const COLORS = [
  "#FF3838", "#FF9D00", "#FFD726", "#36D64A", "#00C2FF",
  "#006BFF", "#8B5CF6", "#FF63B7", "#FF448F", "#00E5FF",
];

function getColor(label: string): string {
  let hash = 0;
  for (let i = 0; i < label.length; i++) {
    hash = label.charCodeAt(i) + ((hash << 5) - hash);
  }
  return COLORS[Math.abs(hash) % COLORS.length];
}

function formatLabel(ann: LiveAnnotation): string {
  const pct = (ann.confidence * 100).toFixed(0);
  if (ann.taxonomy_label && ann.taxonomy_label !== ann.class_name) {
    return `${ann.taxonomy_label} (${ann.class_name}) ${pct}%`;
  }
  return `${ann.class_name} ${pct}%`;
}

export default function AnnotationOverlay({
  annotations,
  videoWidth,
  videoHeight,
  displayMode = "both",
  depthAvailable = false,
  orientation = "normal",
  previewMirrored = false,
}: Props) {
  const overlayRef = useRef<SVGSVGElement>(null);
  const { t } = useTranslation();

  useEffect(() => {
    const el = overlayRef.current;
    if (!el) return;
    const style = window.getComputedStyle(el);
    const transform = style.transform;
    if (transform && transform !== "none") {
      console.error(
        "AnnotationOverlay invariant violated: overlay root must not have CSS transform",
        { transform },
      );
    }
  }, [previewMirrored, annotations.length]);

  if (annotations.length === 0 || videoWidth === 0 || videoHeight === 0) return null;

  const showBoxes = displayMode === "boxes" || displayMode === "both" || displayMode === "all";
  const showMasks = displayMode === "masks" || displayMode === "both" || displayMode === "all";
  const show3d = displayMode === "3d" || displayMode === "all";
  const has3d = annotations.some((a) => a.bbox_3d?.corners?.length === 8);
  const showBoxFallback = show3d && !showBoxes && !has3d;

  return (
    <svg
      ref={overlayRef}
      className="live-annotate-overlay"
      data-preview-mirrored={previewMirrored ? "true" : "false"}
      data-coordinate-space="analyzed"
      viewBox={`0 0 ${videoWidth} ${videoHeight}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {show3d && has3d && (
        <text
          x={8}
          y={videoHeight - 8}
          fill="rgba(255,255,255,0.7)"
          fontSize={10}
        >
          {depthAvailable
            ? t("liveAnnotate.bbox3dDepthOnnx")
            : t("liveAnnotate.bbox3dLimitation")}
        </text>
      )}
      {showBoxFallback && (
        <text x={8} y={videoHeight - 8} fill="rgba(255,200,80,0.9)" fontSize={10}>
          {t("liveAnnotate.bbox3dNone", "No 3D-eligible objects — showing 2D boxes")}
        </text>
      )}
      {(orientation === "mirrored" || !depthAvailable) && (
        <g>
          {orientation === "mirrored" && (
            <text x={8} y={14} fill="rgba(255,200,80,0.9)" fontSize={10}>
              {t("liveAnnotate.chipOrientationMirrored")}
            </text>
          )}
          {!depthAvailable && has3d && (
            <text x={8} y={orientation === "mirrored" ? 28 : 14} fill="rgba(255,200,80,0.9)" fontSize={10}>
              {t("liveAnnotate.chipDepthHeuristic")}
            </text>
          )}
        </g>
      )}
      {annotations.map((ann) => {
        const color = getColor(ann.taxonomy_label || ann.class_name);
        const [x, y, w, h] = ann.bbox;
        const label = formatLabel(ann);
        const key = ann.track_id != null ? ann.track_id : `${ann.class_name}-${ann.bbox.join(",")}`;

        const maskPoints = ann.mask?.length
          ? maskToSvgPoints(ann.mask, videoWidth, videoHeight)
          : null;

        const cuboid = ann.bbox_3d?.corners;
        const edges = cuboid && show3d && cuboid.length >= 8 ? cuboidEdges2D(cuboid, videoWidth, videoHeight) : [];
        const topFace = cuboid && show3d && cuboid.length >= 8 ? cuboidTopFace2D(cuboid, videoWidth, videoHeight) : [];
        const drawBoxes = showBoxes || showBoxFallback;

        return (
          <g key={key}>
            {showMasks && maskPoints && (
              <polygon
                points={maskPoints}
                fill={color}
                fillOpacity={0.25}
                stroke={color}
                strokeWidth={1.5}
              />
            )}
            {show3d && edges.map(([a, b], ei) => (
              <line
                key={`edge-${ei}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={color}
                strokeWidth={1.5}
                strokeDasharray={ei >= 8 ? "4 2" : undefined}
              />
            ))}
            {show3d && topFace.length === 4 && (
              <polygon
                points={topFace.map((p) => `${p.x},${p.y}`).join(" ")}
                fill={color}
                fillOpacity={0.15}
                stroke={color}
                strokeWidth={1}
              />
            )}
            {drawBoxes && (
              <>
                <rect
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  stroke={color}
                  strokeWidth={2}
                  fill="none"
                  strokeLinecap="round"
                />
                <rect
                  x={x}
                  y={y - 20 < 0 ? y + h : y - 20}
                  width={label.length * 7 + 10}
                  height={20}
                  fill={color}
                  rx={3}
                />
                <text
                  x={x + 5}
                  y={y - 20 < 0 ? y + h + 14 : y - 5}
                  fill="#fff"
                  fontSize={12}
                  fontWeight={600}
                >
                  {label}
                </text>
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
