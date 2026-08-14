import { Canvas, Polygon, Point, type TPointerEventInfo, type TPointerEvent } from "fabric";
import { getRoadClassColor } from "../../constants/roadTaxonomy";

export interface FabricPolygonManagerOptions {
  onModified?: () => void;
  objectTag?: string;
  resolveColor?: () => string;
  /** When set, caller owns adding the finalized polygon to app state. */
  onFinalize?: (points: PolygonVertex[]) => void;
}

interface PolygonVertex {
  x: number;
  y: number;
}

interface ActivePolygon {
  points: PolygonVertex[];
  fabricPolygon: Polygon | null;
}

type ToolMode = "select" | "draw_polygon" | "edit_polygon";

export class FabricPolygonManager {
  private canvas: Canvas;
  private activePolygon: ActivePolygon = { points: [], fabricPolygon: null };
  private mode: ToolMode = "select";
  private vertexHandles: Polygon[] = [];
  private midpointHandles: Polygon[] = [];
  private objectTag: string;
  private resolveColor: () => string;
  private onFinalize?: (points: PolygonVertex[]) => void;

  constructor(canvas: Canvas, opts?: FabricPolygonManagerOptions) {
    this.canvas = canvas;
    this.onModified = opts?.onModified;
    this.objectTag = opts?.objectTag ?? "_isRoadPolygon";
    this.resolveColor = opts?.resolveColor ?? (() => "#4CAF50");
    this.onFinalize = opts?.onFinalize;
    this.bindEvents();
  }

  private onModified?: () => void;

  setMode(mode: ToolMode): void {
    this.mode = mode;
    if (mode === "draw_polygon") {
      this.canvas.selection = false;
      this.canvas.defaultCursor = "crosshair";
      this.clearDrawingState();
    } else if (mode === "select") {
      this.canvas.selection = true;
      this.canvas.defaultCursor = "default";
      this.cancelDrawing();
      this.removeHandles();
    }
  }

  getMode(): ToolMode {
    return this.mode;
  }

  private bindEvents(): void {
    this.canvas.on("mouse:down", (opt: TPointerEventInfo<TPointerEvent>) => {
      if (this.mode !== "draw_polygon") return;
      const pointer = this.canvas.getScenePoint(opt.e);
      this.addVertex(pointer.x, pointer.y);
    });

    this.canvas.on("mouse:dblclick", () => {
      if (this.mode === "draw_polygon") {
        this.finalizePolygon();
      }
    });
  }

  private addVertex(x: number, y: number): void {
    this.activePolygon.points.push({ x, y });

    const point = this.createVertexHandle(x, y, "#ff0");
    this.canvas.add(point);
    this.vertexHandles.push(point);

    if (this.activePolygon.points.length > 2) {
      this.updatePreviewPolygon();
    }
  }

  private updatePreviewPolygon(): void {
    if (this.activePolygon.fabricPolygon) {
      this.canvas.remove(this.activePolygon.fabricPolygon);
    }

    if (this.activePolygon.points.length < 3) return;

    const pts = this.activePolygon.points.map(
      (p) => new Point(p.x, p.y)
    );

    const poly = new Polygon(pts, {
      fill: "rgba(255, 255, 0, 0.15)",
      stroke: "#ff0",
      strokeWidth: 2,
      strokeDashArray: [5, 5],
      selectable: false,
      evented: false,
    }) as unknown as Polygon;

    this.canvas.add(poly);
    (this.canvas as unknown as Record<string, (obj: Polygon, index: number) => void>).moveTo?.(poly, 0);
    this.activePolygon.fabricPolygon = poly;
    this.canvas.renderAll();
  }

  private finalizePolygon(): void {
    if (this.activePolygon.points.length < 3) {
      this.cancelDrawing();
      return;
    }

    if (this.activePolygon.fabricPolygon) {
      this.canvas.remove(this.activePolygon.fabricPolygon);
    }

    const points = [...this.activePolygon.points];

    if (this.onFinalize) {
      this.onFinalize(points);
      this.clearDrawingState();
      this.onModified?.();
      return;
    }

    const pts = points.map((p) => new Point(p.x, p.y));
    const color = this.resolveColor();

    const poly = new Polygon(pts, {
      fill: `${color}22`,
      stroke: color,
      strokeWidth: 2,
      selectable: true,
      evented: true,
    }) as unknown as Polygon;

    (poly as unknown as Record<string, unknown>)[this.objectTag] = true;
    this.canvas.add(poly);
    this.canvas.renderAll();

    this.clearDrawingState();
    this.onModified?.();
  }

  private createVertexHandle(x: number, y: number, color: string): Polygon {
    const size = 6;
    const pts = [
      new Point(0, 0),
      new Point(size, 0),
      new Point(size, size),
      new Point(0, size),
    ];
    const handle = new Polygon(pts, {
      left: x - size / 2,
      top: y - size / 2,
      fill: color,
      stroke: "#fff",
      strokeWidth: 1,
      selectable: false,
      evented: false,
      originX: "center",
      originY: "center",
    }) as unknown as Polygon;
    return handle;
  }

  private removeHandles(): void {
    this.vertexHandles.forEach((h) => this.canvas.remove(h));
    this.vertexHandles = [];
    this.midpointHandles.forEach((h) => this.canvas.remove(h));
    this.midpointHandles = [];
  }

  private cancelDrawing(): void {
    if (this.activePolygon.fabricPolygon) {
      this.canvas.remove(this.activePolygon.fabricPolygon);
    }
    this.clearDrawingState();
  }

  private clearDrawingState(): void {
    this.activePolygon = { points: [], fabricPolygon: null };
    this.removeHandles();
  }

  getCanvasPolygons(): Polygon[] {
    return this.canvas
      .getObjects()
      .filter(
        (obj) =>
          obj.type === "polygon" &&
          (obj as unknown as Record<string, unknown>)[this.objectTag]
      ) as unknown as Polygon[];
  }

  clearAllPolygons(): void {
    const polys = this.getCanvasPolygons();
    polys.forEach((p) => this.canvas.remove(p));
    this.clearDrawingState();
    this.canvas.renderAll();
  }

  addPolygonFromPoints(
    points: [number, number][],
    classId: number,
    className: string
  ): void {
    const color = getRoadClassColor(classId);
    const pts = points.map(([x, y]) => new Point(x, y));

    const poly = new Polygon(pts, {
      fill: `${color}33`,
      stroke: color,
      strokeWidth: 2,
      selectable: true,
      evented: true,
    }) as unknown as Polygon;

    (poly as unknown as Record<string, unknown>)[this.objectTag] = true;
    (poly as unknown as Record<string, unknown>)._roadClassId = classId;
    (poly as unknown as Record<string, unknown>)._roadClassName = className;

    this.canvas.add(poly);
    this.canvas.renderAll();
    this.onModified?.();
  }

  destroy(): void {
    this.cancelDrawing();
    this.canvas.off("mouse:down");
    this.canvas.off("mouse:dblclick");
    this.canvas.off("selection:created");
    this.canvas.off("selection:cleared");
  }
}
