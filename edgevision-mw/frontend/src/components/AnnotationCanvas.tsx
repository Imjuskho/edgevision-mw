import { useEffect, useRef, useState, useCallback } from "react";
import { Canvas, Rect, Polygon, Point, FabricImage, FabricText, ActiveSelection, util, type TPointerEventInfo } from "fabric";
import type { BBox } from "../types";
import { getCategoryColor, getCategoryForLabel, ALL_LABELS } from "../constants/taxonomy";
import { AGRI_CROP_DISPLAY_NAMES, AGRI_HEALTH_DISPLAY_NAMES } from "../constants/agriTaxonomy";
import { toStyle } from "../utils/toStyle";
import { FabricPolygonManager } from "./RoadSegPanel/FabricPolygonManager";
import { bboxFromPolygon, clampPolygon, polygonFromCanvas, type NormalizedPoint } from "../utils/annotationCoords";
import { useFabricCanvasZoom } from "../hooks/useFabricCanvasZoom";
import { FabricZoomRegistrar } from "./FabricZoomRegistrar";

export type DrawTool = "bbox" | "polygon";

interface Props {
  imageUrl: string;
  boxes: BBox[];
  onBoxesChange: (boxes: BBox[]) => void;
  label: string;
  taxonomyContext?: "road" | "agri";
  drawTool?: DrawTool;
}

interface LabelOption {
  label: string;
  name: string;
  color: string;
}

function getAllLabels(ctx: "road" | "agri"): LabelOption[] {
  if (ctx === "agri") {
    return [
      ...Object.entries(AGRI_CROP_DISPLAY_NAMES).map(([k, v]) => ({ label: k, name: v.en, color: "#4CAF50" })),
      ...Object.entries(AGRI_HEALTH_DISPLAY_NAMES).map(([k, v]) => ({ label: k, name: v.en, color: "#FF9800" })),
    ];
  }
  return ALL_LABELS.map((l) => ({ label: l.label, name: l.name, color: l.color }));
}

function getImageDisplaySize(canvas: Canvas): { w: number; h: number } {
  const bg = canvas.backgroundImage as FabricImage | undefined;
  if (bg && typeof bg.width === "number" && typeof bg.height === "number") {
    return { w: bg.width * (bg.scaleX ?? 1), h: bg.height * (bg.scaleY ?? 1) };
  }
  return { w: canvas.getWidth(), h: canvas.getHeight() };
}

function labelColor(label: string, ctx: "road" | "agri"): string {
  if (ctx === "agri") {
    const crop = AGRI_CROP_DISPLAY_NAMES[label];
    const health = AGRI_HEALTH_DISPLAY_NAMES[label];
    return crop ? "#4CAF50" : health ? "#FF9800" : "#64748b";
  }
  return getCategoryColor(label);
}

function fabricPolygonToNormalized(poly: Polygon, imgW: number, imgH: number): NormalizedPoint[] {
  const matrix = poly.calcTransformMatrix();
  const pathOffset = poly.pathOffset ?? { x: 0, y: 0 };
  return (poly.points as Point[]).map((p) => {
    const local = new Point(p.x - pathOffset.x, p.y - pathOffset.y);
    const transformed = util.transformPoint(local, matrix);
    return [
      Math.max(0, Math.min(1, transformed.x / imgW)),
      Math.max(0, Math.min(1, transformed.y / imgH)),
    ] as NormalizedPoint;
  });
}

export default function AnnotationCanvas({
  imageUrl,
  boxes,
  onBoxesChange,
  label,
  taxonomyContext = "road",
  drawTool = "bbox",
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fabricRef = useRef<Canvas | null>(null);
  const polyManagerRef = useRef<FabricPolygonManager | null>(null);
  const boxesRef = useRef(boxes);
  const labelRef = useRef(label);
  const onBoxesChangeRef = useRef(onBoxesChange);
  const drawingRef = useRef(false);
  const startRef = useRef({ x: 0, y: 0 });
  const tempRectRef = useRef<Rect | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [editPopup, setEditPopup] = useState<{
    boxIndex: number;
    x: number;
    y: number;
    currentLabel: string;
    search: string;
  } | null>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const zoomApi = useFabricCanvasZoom(fabricRef, {
    containerRef,
    enabled: loaded,
  });

  useEffect(() => {
    boxesRef.current = boxes;
  }, [boxes]);

  useEffect(() => {
    labelRef.current = label;
  }, [label]);

  useEffect(() => {
    onBoxesChangeRef.current = onBoxesChange;
  }, [onBoxesChange]);

  const syncFromCanvas = useCallback(() => {
    const canvas = fabricRef.current;
    if (!canvas) return;
    const { w: imgW, h: imgH } = getImageDisplaySize(canvas);
    const objects = canvas
      .getObjects()
      .filter((o) => (o as Rect & { _isBox?: boolean })._isBox)
      .sort(
        (a, b) =>
          ((a as Rect & { _boxIndex?: number })._boxIndex ?? 0) -
          ((b as Rect & { _boxIndex?: number })._boxIndex ?? 0),
      );

    const updated = objects.map((obj, i) => {
      const prev = boxesRef.current[i] ?? boxesRef.current[(obj as Rect & { _boxIndex?: number })._boxIndex ?? i];
      const baseLabel = prev?.label ?? labelRef.current;
      const cat = getCategoryForLabel(baseLabel);

      if (obj instanceof Polygon) {
        const polygon = clampPolygon(fabricPolygonToNormalized(obj, imgW, imgH));
        if (polygon.length < 3) return prev;
        return {
          ...prev,
          ...bboxFromPolygon(polygon),
          label: baseLabel,
          category: cat?.id,
          confidence: prev?.confidence ?? 1.0,
          polygon,
        };
      }

      const rect = obj as Rect;
      return {
        ...prev,
        x: (rect.left ?? 0) / imgW,
        y: (rect.top ?? 0) / imgH,
        width: (rect.width ?? 0) / imgW,
        height: (rect.height ?? 0) / imgH,
        label: baseLabel,
        category: cat?.id,
        confidence: prev?.confidence ?? 1.0,
        polygon: undefined,
      };
    });

    onBoxesChangeRef.current(updated);
  }, []);

  const deleteSelected = useCallback(() => {
    const canvas = fabricRef.current;
    if (!canvas) return;
    const active = canvas.getActiveObject();
    if (!active) return;

    let indices: number[] = [];
    if (active instanceof ActiveSelection) {
      indices = active.getObjects()
        .map((o) => (o as Rect & { _boxIndex?: number })._boxIndex)
        .filter((i): i is number => i !== undefined);
    } else {
      const idx = (active as Rect & { _boxIndex?: number })._boxIndex;
      if (idx !== undefined) indices = [idx];
    }

    if (indices.length === 0) return;
    const updated = boxes.filter((_, i) => !indices.includes(i));
    onBoxesChange(updated);
    canvas.discardActiveObject();
    canvas.renderAll();
  }, [boxes, onBoxesChange]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Delete" || e.key === "Backspace") {
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        e.preventDefault();
        deleteSelected();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [deleteSelected]);

  useEffect(() => {
    if (!canvasRef.current) return;
    const canvas = new Canvas(canvasRef.current, {
      backgroundColor: "#1a1a2e",
      selection: true,
      width: 900,
      height: 600,
    });
    fabricRef.current = canvas;

    return () => {
      canvas.dispose();
      fabricRef.current = null;
    };
  }, []);

  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas || loaded) return;

    const imgEl = new Image();
    imgEl.crossOrigin = "anonymous";
    imgEl.onload = () => {
      const maxW = 900;
      const maxH = 600;
      const scale = Math.min(maxW / imgEl.width, maxH / imgEl.height, 1);

      const bg = new FabricImage(imgEl, {
        selectable: false,
        evented: false,
      });
      bg.scale(scale);
      canvas.backgroundImage = bg;
      canvas.renderAll();
      setLoaded(true);
    };
    imgEl.src = imageUrl;
  }, [imageUrl, loaded]);

  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas || !loaded) return;

    if (polyManagerRef.current) {
      polyManagerRef.current.destroy();
    }

    polyManagerRef.current = new FabricPolygonManager(canvas, {
      objectTag: "_isBox",
      resolveColor: () => labelColor(labelRef.current, taxonomyContext),
      onFinalize: (points) => {
        const { w: imgW, h: imgH } = getImageDisplaySize(canvas);
        const polygon = clampPolygon(polygonFromCanvas(points, imgW, imgH));
        if (polygon.length < 3) return;
        const bounds = bboxFromPolygon(polygon);
        const activeLabel = labelRef.current;
        const cat = getCategoryForLabel(activeLabel);
        onBoxesChangeRef.current([
          ...boxesRef.current,
          {
            ...bounds,
            label: activeLabel,
            category: cat?.id,
            confidence: 1.0,
            polygon,
          },
        ]);
      },
      onModified: () => syncFromCanvas(),
    });

    const onModified = () => syncFromCanvas();
    canvas.on("object:modified", onModified);

    return () => {
      canvas.off("object:modified", onModified);
      polyManagerRef.current?.destroy();
      polyManagerRef.current = null;
    };
  }, [loaded, taxonomyContext, syncFromCanvas]);

  useEffect(() => {
    const manager = polyManagerRef.current;
    if (!manager) return;
    if (drawTool === "polygon") {
      manager.setMode("draw_polygon");
    } else {
      manager.setMode("select");
    }
  }, [drawTool, loaded]);

  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas || !loaded) return;

    const existing = canvas.getObjects().filter((o) => (o as Rect & { _isBox?: boolean })._isBox);
    existing.forEach((o) => canvas.remove(o));

    const { w: imgW, h: imgH } = getImageDisplaySize(canvas);

    boxes.forEach((box, i) => {
      const color = labelColor(box.label, taxonomyContext);

      if (box.polygon && box.polygon.length >= 3) {
        const pts = box.polygon.map(([nx, ny]) => ({
          x: nx * imgW,
          y: ny * imgH,
        }));
        const poly = new Polygon(pts, {
          fill: `${color}22`,
          stroke: color,
          strokeWidth: 2,
          selectable: true,
          evented: true,
          objectCaching: false,
        });
        (poly as Polygon & { _isBox?: boolean })._isBox = true;
        (poly as Polygon & { _boxIndex?: number })._boxIndex = i;

        const text = new FabricText(box.label, {
          left: box.x * imgW + 4,
          top: box.y * imgH - 16,
          fontSize: 12,
          fill: color,
          selectable: false,
          evented: false,
        });
        (text as FabricText & { _isLabel?: boolean })._isLabel = true;
        canvas.add(poly, text);
        return;
      }

      const rect = new Rect({
        left: box.x * imgW,
        top: box.y * imgH,
        width: box.width * imgW,
        height: box.height * imgH,
        fill: `${color}22`,
        stroke: color,
        strokeWidth: 2,
        selectable: true,
        evented: true,
      });
      (rect as Rect & { _isBox?: boolean })._isBox = true;
      (rect as Rect & { _boxIndex?: number })._boxIndex = i;

      const text = new FabricText(box.label, {
        left: box.x * imgW + 4,
        top: box.y * imgH - 16,
        fontSize: 12,
        fill: color,
        selectable: false,
        evented: false,
      });
      (text as FabricText & { _isLabel?: boolean })._isLabel = true;

      canvas.add(rect, text);
    });
    canvas.renderAll();
  }, [boxes, loaded, taxonomyContext]);

  const handleMouseDown = useCallback(
    (opt: TPointerEventInfo) => {
      if (drawTool === "polygon") return;
      const canvas = fabricRef.current;
      if (!canvas) return;

      const e = opt.e as MouseEvent;
      if (zoomApi.isPanning || zoomApi.isSpacePressed || e.button === 1) return;

      if (opt.target && (opt.target as Rect & { _isBox?: boolean })._isBox) return;

      drawingRef.current = true;
      const pointer = canvas.getPointer(opt.e);
      startRef.current = { x: pointer.x, y: pointer.y };

      const rect = new Rect({
        left: pointer.x,
        top: pointer.y,
        width: 0,
        height: 0,
        fill: `${labelColor(label, taxonomyContext)}22`,
        stroke: labelColor(label, taxonomyContext),
        strokeWidth: 2,
        selectable: false,
        evented: false,
      });
      (rect as Rect & { _isTemp?: boolean })._isTemp = true;
      tempRectRef.current = rect;
      canvas.add(rect);
    },
    [label, taxonomyContext, drawTool, zoomApi.isPanning, zoomApi.isSpacePressed]
  );

  const handleMouseMove = useCallback(
    (opt: TPointerEventInfo) => {
      if (drawTool === "polygon") return;
      if (!drawingRef.current || !tempRectRef.current) return;
      const canvas = fabricRef.current;
      if (!canvas) return;

      const pointer = canvas.getPointer(opt.e);
      const x = Math.min(startRef.current.x, pointer.x);
      const y = Math.min(startRef.current.y, pointer.y);
      const w = Math.abs(pointer.x - startRef.current.x);
      const h = Math.abs(pointer.y - startRef.current.y);

      tempRectRef.current.set({ left: x, top: y, width: w, height: h });
      canvas.renderAll();
    },
    [drawTool]
  );

  const handleMouseUp = useCallback(
    (_opt: TPointerEventInfo) => {
      if (drawTool === "polygon") return;
      if (!drawingRef.current) return;
      drawingRef.current = false;

      const canvas = fabricRef.current;
      if (!canvas || !tempRectRef.current) return;

      const rect = tempRectRef.current;
      canvas.remove(rect);
      tempRectRef.current = null;

      const { w: imgW, h: imgH } = getImageDisplaySize(canvas);
      const boxW = rect.width ?? 0;
      const boxH = rect.height ?? 0;

      if (boxW < 5 || boxH < 5) return;

      const cat = getCategoryForLabel(label);
      const newBox: BBox = {
        x: (rect.left ?? 0) / imgW,
        y: (rect.top ?? 0) / imgH,
        width: boxW / imgW,
        height: boxH / imgH,
        label,
        category: cat?.id,
        confidence: 1.0,
      };

      onBoxesChange([...boxes, newBox]);
    },
    [boxes, label, onBoxesChange, drawTool]
  );

  const handleDblClick = useCallback(
    (opt: TPointerEventInfo) => {
      const canvas = fabricRef.current;
      if (!canvas) return;
      const target = opt.target;
      if (!target || !(target as Rect & { _isBox?: boolean })._isBox) return;
      const idx = (target as Rect & { _boxIndex?: number })._boxIndex;
      if (idx === undefined || idx >= boxes.length) return;
      const box = boxes[idx];
      const { w: imgW, h: imgH } = getImageDisplaySize(canvas);
      const vpt = canvas.viewportTransform;
      const canvasEl = canvasRef.current;
      if (!canvasEl || !vpt) return;
      const rect = canvasEl.getBoundingClientRect();
      const px = (box.x + box.width / 2) * imgW;
      const py = box.y * imgH - 8;
      const screenX = px * vpt[0] + vpt[4] + rect.left;
      const screenY = py * vpt[3] + vpt[5] + rect.top;
      setEditPopup({ boxIndex: idx, x: screenX, y: screenY, currentLabel: box.label, search: "" });
    },
    [boxes]
  );

  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas) return;
    canvas.on("mouse:down", handleMouseDown);
    canvas.on("mouse:move", handleMouseMove);
    canvas.on("mouse:up", handleMouseUp);
    canvas.on("mouse:dblclick", handleDblClick);
    return () => {
      canvas.off("mouse:down", handleMouseDown);
      canvas.off("mouse:move", handleMouseMove);
      canvas.off("mouse:up", handleMouseUp);
      canvas.off("mouse:dblclick", handleDblClick);
    };
  }, [handleMouseDown, handleMouseMove, handleMouseUp, handleDblClick]);

  const allLabels = getAllLabels(taxonomyContext);
  const filteredLabels = editPopup
    ? allLabels.filter((l) =>
        l.label.includes(editPopup.search.toLowerCase()) ||
        l.name.toLowerCase().includes(editPopup.search.toLowerCase())
      )
    : [];

  const handleEditSelect = (newLabel: string) => {
    if (!editPopup) return;
    const updated = [...boxes];
    const box = { ...updated[editPopup.boxIndex], label: newLabel };
    const cat = getCategoryForLabel(newLabel);
    box.category = cat?.id;
    updated[editPopup.boxIndex] = box;
    onBoxesChange(updated);
    setEditPopup(null);
  };

  return (
    <div className="annotation-canvas" ref={containerRef}>
      <FabricZoomRegistrar api={zoomApi} />
      <canvas ref={canvasRef} />
      {editPopup && (
        <div
          ref={popupRef}
          className="annotation-edit-popup"
          style={toStyle({ left: editPopup.x, top: editPopup.y })}
        >
          <div className="annotation-edit-search-wrap">
            <input
              autoFocus
              type="text"
              className="annotation-edit-search"
              placeholder="Search label..."
              value={editPopup.search}
              onChange={(e) => setEditPopup({ ...editPopup, search: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === "Escape") setEditPopup(null);
                if (e.key === "Enter" && filteredLabels.length > 0) handleEditSelect(filteredLabels[0].label);
              }}
            />
          </div>
          <div className="annotation-edit-list">
            {filteredLabels.length === 0 && (
              <div className="annotation-edit-empty">No matches</div>
            )}
            {filteredLabels.map((item) => (
              <button
                key={item.label}
                className={`annotation-edit-item${item.label === editPopup.currentLabel ? " annotation-edit-item--selected" : ""}`}
                style={toStyle({ "--item-color": item.color })}
                onClick={() => handleEditSelect(item.label)}
              >
                <span className="annotation-edit-item-dot" style={toStyle({ backgroundColor: item.color })} />
                <span className="annotation-edit-item-name">{item.name}</span>
                <span className="annotation-edit-item-code">{item.label}</span>
              </button>
            ))}
          </div>
          <div className="annotation-edit-footer">
            Esc to close · {filteredLabels.length} labels
          </div>
        </div>
      )}
      <div className="annotation-canvas-hint">
        {drawTool === "polygon"
          ? "Click to add vertices · Double-click to close polygon · Delete to remove selected"
          : "Click/drag to draw · Double-click box to edit label · Shift+click to multi-select · Delete/Backspace to remove"}{" "}
        · Scroll to zoom · Space+drag or middle-click to pan ·{" "}
        | {boxes.length} annotations
      </div>
    </div>
  );
}
