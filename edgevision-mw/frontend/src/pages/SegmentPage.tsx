import { useState, useCallback, useEffect, useRef } from "react";
import { Canvas, Polygon, Point, FabricImage } from "fabric";
import { useTranslation } from "react-i18next";
import { studioApi } from "../services/api";
import { useUnsavedWork } from "../context/UnsavedWorkContext";
import { useRoadSegmentation } from "../hooks/useRoadSegmentation";
import { useResilientSave } from "../hooks/useResilientSave";
import { useFabricCanvasZoom } from "../hooks/useFabricCanvasZoom";
import { FabricPolygonManager } from "../components/RoadSegPanel/FabricPolygonManager";
import { FabricZoomRegistrar } from "../components/FabricZoomRegistrar";
import { RoadSegPanel } from "../components/RoadSegPanel/RoadSegPanel";
import { AnnotateWorkspace } from "../components/annotate/AnnotateWorkspace";
import { BatchInferenceAction } from "../components/BatchInferenceAction";
import { EmptyState } from "../components/ui/EmptyState";
import { Badge } from "../components/ui/Badge";
import { Select } from "../components/ui/Select";
import { ROAD_CLASS_ARRAY, ROAD_CLASS_DISPLAY_NAMES } from "../constants/roadTaxonomy";
import type { ImageItem, InstanceMask, RoadSegAnnotation } from "../types";

interface SegmentPageProps {
  sessionId: string;
  datasetId: string;
  imageIndex: number;
  onSaved?: () => void;
  onNavigate?: (index: number) => void;
}

export default function SegmentPage({
  sessionId,
  datasetId,
  imageIndex,
  onSaved,
  onNavigate,
}: SegmentPageProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as "en" | "ny";
  const { setDirty } = useUnsavedWork();
  const { saveRoadAnnotations } = useResilientSave(sessionId);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fabricRef = useRef<Canvas | null>(null);
  const polyManagerRef = useRef<FabricPolygonManager | null>(null);
  const canvasReadyRef = useRef(false);
  const [canvasReady, setCanvasReady] = useState(false);
  const zoomApi = useFabricCanvasZoom(fabricRef, {
    containerRef,
    enabled: canvasReady,
  });

  const [images, setImages] = useState<ImageItem[]>([]);
  const [imagesLoading, setImagesLoading] = useState(true);
  const [imagesError, setImagesError] = useState<string | null>(null);
  const [prevImgDatasetId, setPrevImgDatasetId] = useState(datasetId);
  if (datasetId !== prevImgDatasetId) {
    setPrevImgDatasetId(datasetId);
    setImagesLoading(true);
    setImagesError(null);
  }
  const [currentIndex, setCurrentIndex] = useState(imageIndex);
  const [isSegmentActive, setIsSegmentActive] = useState(false);
  const [selectedClass, setSelectedClass] = useState<number>(1);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const {
    isSegmenting,
    annotations,
    instances,
    error,
    segmentViaApi,
    acceptInstance,
    rejectInstance,
    acceptAll,
    rejectAll,
    clearInstances,
    setAnnotations,
  } = useRoadSegmentation();

  useEffect(() => {
    studioApi
      .listImages(datasetId)
      .then((resp) => {
        setImages(resp.data.images ?? []);
      })
      .catch(() => {
        setImages([]);
        setImagesError("Failed to load images for this dataset.");
      })
      .finally(() => setImagesLoading(false));
  }, [datasetId]);

  const currentImage = images[currentIndex];

  const markDirty = useCallback(() => setDirty(true), [setDirty]);

  useEffect(() => {
    setDirty(false);
  }, [sessionId, datasetId, currentIndex, setDirty]);

  useEffect(() => {
    if (!canvasRef.current || !currentImage) return;

    canvasReadyRef.current = false;
    setCanvasReady(false);

    if (fabricRef.current) {
      polyManagerRef.current?.destroy();
      fabricRef.current.dispose();
    }

    const canvas = new Canvas(canvasRef.current, {
      selection: false,
      preserveObjectStacking: true,
    });
    fabricRef.current = canvas;

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = studioApi.serveImage(currentImage.annotation_id);
    img.onload = () => {
      const fImg = new FabricImage(img, { selectable: false, evented: false });
      const container = canvasRef.current!.parentElement!;
      const scale = Math.min(
        container.clientWidth / img.width,
        container.clientHeight / img.height,
        1
      );
      fImg.scale(scale);
      canvas.setDimensions({ width: img.width * scale, height: img.height * scale });
      canvas.add(fImg);
      canvas.renderAll();

      polyManagerRef.current = new FabricPolygonManager(canvas, { onModified: markDirty });
      canvasReadyRef.current = true;
      setCanvasReady(true);
      if (isSegmentActive) {
        polyManagerRef.current.setMode("draw_polygon");
      }
    };

    return () => {
      canvasReadyRef.current = false;
      setCanvasReady(false);
      polyManagerRef.current?.destroy();
      canvas.dispose();
      fabricRef.current = null;
    };
  }, [currentImage, currentIndex, datasetId, markDirty]);

  useEffect(() => {
    if (isSegmentActive && polyManagerRef.current) {
      polyManagerRef.current.setMode("draw_polygon");
    } else if (!isSegmentActive && polyManagerRef.current) {
      polyManagerRef.current.setMode("select");
    }
  }, [isSegmentActive]);

  const waitForCanvasReady = useCallback(async () => {
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
      const canvasEl = fabricRef.current;
      const hasImage = canvasEl
        ?.getObjects()
        .some((obj) => obj.type === "image");
      if (canvasReadyRef.current && polyManagerRef.current && hasImage) {
        return;
      }
      await new Promise((resolve) => requestAnimationFrame(resolve));
    }
    throw new Error(t("segment.canvasNotReady"));
  }, [t]);

  const renderSegmentResults = useCallback(
    (result: InstanceMask[]) => {
      if (!polyManagerRef.current || !fabricRef.current) return 0;

      polyManagerRef.current.clearAllPolygons();
      let rendered = 0;

      for (const inst of result) {
        if (!inst.polygon || inst.polygon.length <= 2) continue;

        const imgObj = fabricRef.current
          .getObjects()
          .find((o) => o.type === "image") as FabricImage | undefined;
        if (!imgObj) continue;

        const scaleX = imgObj.scaleX || 1;
        const scaleY = imgObj.scaleY || 1;
        const canvasPts = inst.polygon.map(
          ([x, y]) =>
            [
              x * (imgObj.width || 640) * scaleX,
              y * (imgObj.height || 480) * scaleY,
            ] as [number, number],
        );
        polyManagerRef.current.addPolygonFromPoints(
          canvasPts,
          inst.class_id,
          inst.class_name,
        );
        rendered += 1;
      }

      if (rendered > 0) {
        markDirty();
      }
      return rendered;
    },
    [markDirty],
  );

  const loadExistingRoadResult = useCallback(async () => {
    if (!currentImage || !canvasReady) return;
    clearInstances();
    try {
      const resp = await studioApi.getRoadResult(currentImage.annotation_id);
      const data = resp.data as {
        instances: InstanceMask[];
        auto_generated: boolean;
        reviewed: boolean;
      };
      if (!data.instances?.length || data.reviewed) return;

      renderSegmentResults(data.instances);
      const anns: RoadSegAnnotation[] = data.instances.map((inst) => ({
        id: `road_batch_${inst.class_id}_${Math.random().toString(36).slice(2, 8)}`,
        class_id: inst.class_id,
        class_name: inst.class_name,
        confidence: inst.confidence,
        polygon: inst.polygon ?? [],
        accepted: true,
      }));
      setAnnotations(anns);
      if (data.auto_generated) {
        setIsSegmentActive(true);
      }
    } catch {
      // No road result yet — normal for unlabeled frames
    }
  }, [canvasReady, currentImage, clearInstances, renderSegmentResults, setAnnotations]);

  useEffect(() => {
    const load = async () => {
      await loadExistingRoadResult();
    };
    void load();
  }, [loadExistingRoadResult]);

  const handleAutoSegment = useCallback(async () => {
    if (!currentImage) return;
    setIsSegmentActive(true);

    try {
      await waitForCanvasReady();
      const result = await segmentViaApi(currentImage.annotation_id);
      const rendered = renderSegmentResults(result);
      if (rendered === 0 && result.length === 0) {
        setSaveMessage(t("roadSegmentation.noInstances"));
      } else {
        setSaveMessage(null);
      }
    } catch (err) {
      setSaveMessage(
        err instanceof Error ? err.message : t("roadSegmentation.segmentFailed"),
      );
    }
  }, [currentImage, renderSegmentResults, segmentViaApi, t, waitForCanvasReady]);

  const handleSave = useCallback(async () => {
    if (!currentImage || !fabricRef.current) return;
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const canvas = fabricRef.current;
      const imgObj = canvas
        .getObjects()
        .find((o) => o.type === "image") as FabricImage | undefined;
      if (!imgObj) {
        setSaveMessage(t("segment.noImageLoaded"));
        return;
      }

      const scaleX = imgObj.scaleX || 1;
      const scaleY = imgObj.scaleY || 1;
      const imgW = imgObj.width || 640;
      const imgH = imgObj.height || 480;

      const savedAnnotations = canvas
        .getObjects()
        .filter(
          (obj) =>
            (obj as unknown as Record<string, unknown>)._isRoadPolygon
        )
        .map((obj) => {
          const poly = obj as unknown as Polygon;
          const pts = (poly.points as Point[]) ?? [];
          const normPts = pts.map((p) => ({
            x: p.x / (imgW * scaleX),
            y: p.y / (imgH * scaleY),
          }));
          const xs = normPts.map((p) => p.x);
          const ys = normPts.map((p) => p.y);
          const minX = Math.min(...xs);
          const minY = Math.min(...ys);
          const maxX = Math.max(...xs);
          const maxY = Math.max(...ys);
          return {
            x: Math.max(0, minX),
            y: Math.max(0, minY),
            width: Math.min(1, maxX - minX),
            height: Math.min(1, maxY - minY),
            label: (obj as unknown as Record<string, unknown>)._roadClassName as string || "pothole",
            category: "road_surface",
            confidence: 1.0,
          };
        });

      const result = await saveRoadAnnotations(
        currentImage.annotation_id,
        currentImage.index,
        savedAnnotations,
        "polygon",
      );

      if (!result.queued) {
        const acceptedInstances = annotations
          .filter((a) => a.accepted)
          .map((a) => ({
            class_id: a.class_id,
            class_name: a.class_name,
            confidence: a.confidence,
            bbox: [0, 0, 0, 0] as [number, number, number, number],
            mask_rle: "",
            polygon: a.polygon,
          }));

        if (acceptedInstances.length > 0) {
          await studioApi.updateRoadResult(currentImage.annotation_id, {
            instances: acceptedInstances,
            reviewed: true,
          });
        }
      }

      setSaveMessage(
        result.queued ? t("segment.savedOffline") : t("segment.savedSuccess"),
      );
      setDirty(false);
      onSaved?.();
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : t("segment.saveFailed"));
    } finally {
      setIsSaving(false);
    }
  }, [currentImage, annotations, onSaved, setDirty, saveRoadAnnotations, t]);

  const handlePrev = useCallback(() => {
    if (currentIndex > 0) {
      const newIndex = currentIndex - 1;
      setCurrentIndex(newIndex);
      onNavigate?.(newIndex);
      clearInstances();
    }
  }, [currentIndex, onNavigate, clearInstances]);

  const handleNext = useCallback(() => {
    if (currentIndex < images.length - 1) {
      const newIndex = currentIndex + 1;
      setCurrentIndex(newIndex);
      onNavigate?.(newIndex);
      clearInstances();
    }
  }, [currentIndex, images.length, onNavigate, clearInstances]);

  if (imagesLoading) {
    return (
      <div className="annotate-layout">
        <EmptyState title={t("segment.loadingImages")} />
      </div>
    );
  }

  if (imagesError || images.length === 0) {
    return (
      <div className="annotate-layout">
        <EmptyState
          title={imagesError ? t("segment.loadFailed") : t("segment.emptyTitle")}
          body={t("segment.emptyHint")}
        />
      </div>
    );
  }

  const selectedRoadClass =
    ROAD_CLASS_ARRAY.find((cls) => cls.id === selectedClass)?.name ?? "pothole";

  return (
    <AnnotateWorkspace
      workspaceMode="segment"
      taxonomyContext="road"
      datasetId={datasetId}
      currentIndex={currentIndex}
      totalImages={images.length}
      onImageSelect={(idx) => {
        setCurrentIndex(idx);
        onNavigate?.(idx);
        clearInstances();
      }}
      selectedLabel={selectedRoadClass}
      onLabelChange={() => {}}
      onPrev={handlePrev}
      onNext={handleNext}
      onSave={handleSave}
      saving={isSaving}
      hideAutoLabel
      hideLabelSelector
      isDirty={false}
      secondaryToolbarAction={
        <BatchInferenceAction
          mode="road"
          datasetId={datasetId}
          disabled={isSegmenting || isSaving}
          onComplete={() => {
            setSaveMessage(t("batchInference.reviewHint"));
            void loadExistingRoadResult();
          }}
          onError={(msg) => setSaveMessage(msg)}
        />
      }
      saveStatus={
        saveMessage ? (
          <Badge variant={saveMessage === t("segment.savedSuccess") ? "success" : "warning"}>
            {saveMessage}
          </Badge>
        ) : null
      }
      toolbarExtra={
        isSegmentActive ? (
          <label className="annotate-segment-class">
            <span className="text-caption">{t("segment.classLabel")}</span>
            <Select
              value={String(selectedClass)}
              onChange={(value) => setSelectedClass(Number(value))}
              options={ROAD_CLASS_ARRAY.map((cls) => ({
                value: String(cls.id),
                label: ROAD_CLASS_DISPLAY_NAMES[cls.name]?.[lang] ?? cls.name,
              }))}
            />
          </label>
        ) : null
      }
      inspector={
        <RoadSegPanel
          isActive={isSegmentActive}
          annotations={annotations}
          instances={instances}
          isProcessing={isSegmenting}
          isSegmenting={isSegmenting}
          error={error}
          onToggleActive={() => setIsSegmentActive(!isSegmentActive)}
          onAutoSegment={handleAutoSegment}
          onAcceptInstance={acceptInstance}
          onRejectInstance={rejectInstance}
          onAcceptAll={acceptAll}
          onRejectAll={rejectAll}
          onClearInstances={clearInstances}
          onSave={handleSave}
        />
      }
    >
      <FabricZoomRegistrar api={zoomApi} />
      <div ref={containerRef} className="segment-canvas-wrap">
        <canvas ref={canvasRef} className="segment-fabric-canvas" />
      </div>
    </AnnotateWorkspace>
  );
}
