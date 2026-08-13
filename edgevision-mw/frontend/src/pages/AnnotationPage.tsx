import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
import { useUnsavedWork } from "../context/UnsavedWorkContext";
import { studioApi } from "../services/api";
import type { ImageItem, BBox } from "../types";
import AnnotationCanvas from "../components/AnnotationCanvas";
import { AnnotateWorkspace, type WorkspaceDrawTool } from "../components/annotate/AnnotateWorkspace";
import { BatchInferenceAction } from "../components/BatchInferenceAction";
import { Button } from "../components/ui/Button";
import { Modal } from "../components/ui/Modal";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import { useAIAssist } from "../hooks/useAIAssist";
import { useResilientSave } from "../hooks/useResilientSave";
import { useAnnotateKeyboard } from "../hooks/useAnnotateKeyboard";
import { useOfflineSync } from "../hooks/useOfflineSync";
import { Upload } from "lucide-react";
import { detectedObjectsToBoxes } from "../utils/annotationCoords";

const PAGE_SIZE = 50;

interface Props {
  sessionId: string;
  datasetId: string;
  imageIndex: number;
  onSaved: () => void;
  onNavigate?: (index: number) => void;
  onGoToUpload?: () => void;
  taxonomyContext?: "road" | "agri";
}

export default function AnnotationPage({
  sessionId,
  datasetId,
  imageIndex,
  onSaved,
  onNavigate,
  onGoToUpload,
  taxonomyContext = "road",
}: Props) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const { setDirty } = useUnsavedWork();
  const { saveBboxAnnotations } = useResilientSave(sessionId);
  const { stats } = useOfflineSync(sessionId);
  const savedSnapshotRef = useRef("[]");
  const [images, setImages] = useState<ImageItem[]>([]);
  const [currentIndex, setCurrentIndex] = useState(imageIndex);
  const [boxes, setBoxes] = useState<BBox[]>([]);
  const [selectedLabel, setSelectedLabel] = useState(taxonomyContext === "agri" ? "maize" : "car_private");
  const [saving, setSaving] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [message, setMessage] = useState("");
  const [page, setPage] = useState(1);
  const [totalImages, setTotalImages] = useState(0);
  const [loadingAnnotations, setLoadingAnnotations] = useState(false);
  const [preLabels, setPreLabels] = useState<BBox[] | null>(null);
  const [drawTool, setDrawTool] = useState<WorkspaceDrawTool>("bbox");
  const [aiDraft, setAiDraft] = useState(false);

  const {
    isModelLoading,
    loadProgress,
    isInferencing,
    lastError,
    modelUsed,
    initModels,
    aiDetectAll,
  } = useAIAssist(taxonomyContext);

  const isDirty = JSON.stringify(boxes) !== savedSnapshotRef.current;

  useEffect(() => {
    setDirty(isDirty);
  }, [isDirty, setDirty]);

  useEffect(() => {
    setDirty(false);
    savedSnapshotRef.current = "[]";
  }, [sessionId, datasetId, setDirty]);

  const markSaved = useCallback(
    (nextBoxes: BBox[]) => {
      savedSnapshotRef.current = JSON.stringify(nextBoxes);
      setDirty(false);
    },
    [setDirty],
  );

  const loadImages = useCallback(async (p: number) => {
    try {
      const resp = await studioApi.listImages(datasetId, p, PAGE_SIZE);
      const data = resp.data;
      const newImages = data.images || data || [];
      setTotalImages(data.total ?? newImages.length);
      if (p === 1) {
        setImages(newImages);
      } else {
        setImages((prev) => [...prev, ...newImages]);
      }
    } catch {
      showToast(t("annotation.loadFailed"), "error");
    }
  }, [datasetId, showToast, t]);

  useEffect(() => {
    setPage(1);
    loadImages(1);
  }, [loadImages]);

  useEffect(() => {
    setCurrentIndex(imageIndex);
  }, [imageIndex]);

  const currentImage = images[currentIndex];

  const loadAnnotations = useCallback(async (annotationId: string) => {
    setLoadingAnnotations(true);
    setBoxes([]);
    try {
      const resp = await studioApi.getAnnotationData(annotationId);
      const data = resp.data as {
        annotations: BBox[];
        detected_objects?: Parameters<typeof detectedObjectsToBoxes>[0];
        frame_width?: number;
        frame_height?: number;
        label_source?: string;
        ai_draft?: boolean;
      };
      let loaded = data.annotations?.length > 0 ? data.annotations : [];
      if (loaded.length === 0 && data.detected_objects?.length) {
        loaded = detectedObjectsToBoxes(
          data.detected_objects,
          data.frame_width,
          data.frame_height,
        );
      }
      setAiDraft(Boolean(data.ai_draft || data.label_source === "live_ai_assisted"));
      setBoxes(loaded);
      if (loaded.some((b) => b.polygon && b.polygon.length >= 3)) {
        setDrawTool("polygon");
      }
      markSaved(loaded);
    } catch {
      markSaved([]);
      setAiDraft(false);
    } finally {
      setLoadingAnnotations(false);
    }
  }, [markSaved]);

  useEffect(() => {
    if (currentImage?.annotation_id) {
      void loadAnnotations(currentImage.annotation_id);
    } else {
      setBoxes([]);
      markSaved([]);
    }
  }, [currentIndex, currentImage?.annotation_id, loadAnnotations, markSaved]);

  useEffect(() => {
    if (currentIndex >= images.length - 2 && totalImages > images.length) {
      loadImages(page + 1).then(() => setPage((p) => p + 1));
    }
  }, [currentIndex, images.length, totalImages, page, loadImages]);

  const imageUrl = currentImage ? studioApi.serveImage(currentImage.annotation_id) : "";

  const handleSave = useCallback(async () => {
    if (!currentImage) return;
    setSaving(true);
    setMessage("");
    try {
      const toolUsed =
        boxes.some((b) => b.polygon && b.polygon.length >= 3) ? "polygon" : "bbox";
      const result = await saveBboxAnnotations(
        currentImage.annotation_id,
        currentImage.index,
        boxes,
        toolUsed,
      );
      markSaved(boxes);
      setAiDraft(false);
      showToast(
        result.queued ? t("annotation.savedOffline", "Saved offline — will sync when online") : t("annotation.saved"),
        result.queued ? "info" : "success",
      );
      onSaved();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: unknown }; message?: string };
      let msg = t("annotation.saveFailed");
      const data = axiosErr.response?.data;
      if (data && typeof data === "object") {
        const obj = data as Record<string, unknown>;
        const detail = obj.detail ?? obj.message ?? obj.error;
        if (detail) msg = typeof detail === "string" ? detail : JSON.stringify(detail);
      } else if (axiosErr.message) {
        msg = axiosErr.message;
      }
      setMessage(msg);
      showToast(msg, "error");
    } finally {
      setSaving(false);
    }
  }, [currentImage, boxes, saveBboxAnnotations, markSaved, showToast, t, onSaved]);

  const goNext = useCallback(() => {
    if (currentIndex < totalImages - 1) {
      const next = currentIndex + 1;
      setCurrentIndex(next);
      onNavigate?.(next);
    }
  }, [currentIndex, totalImages, onNavigate]);

  const goPrev = useCallback(() => {
    if (currentIndex > 0) {
      const prev = currentIndex - 1;
      setCurrentIndex(prev);
      onNavigate?.(prev);
    }
  }, [currentIndex, onNavigate]);

  const goNextUnlabeled = useCallback(() => {
    const next = images.findIndex((img, idx) => idx > currentIndex && !img.has_human_labels);
    if (next >= 0) {
      setCurrentIndex(next);
      onNavigate?.(next);
    } else {
      showToast(t("annotation.noMoreUnlabeled", "No more unlabeled images in this batch"), "info");
    }
  }, [images, currentIndex, onNavigate, showToast, t]);

  useAnnotateKeyboard({
    enabled: Boolean(currentImage),
    taxonomyContext,
    selectedLabel,
    onLabelChange: setSelectedLabel,
    onSave: () => void handleSave(),
    onNext: goNext,
    onPrev: goPrev,
    onNextUnlabeled: goNextUnlabeled,
  });

  const handleAiDetectAll = async () => {
    if (!aiEnabled) {
      try {
        await initModels();
        setAiEnabled(true);
      } catch {
        setMessage(t("annotation.aiLoadFailed", "Failed to load AI models"));
        return;
      }
    }

    setMessage(t("annotation.aiRunning", "Running AI detection…"));
    try {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.src = imageUrl;
      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = () => reject(new Error("Failed to load image"));
      });

      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0);
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

      const detected = await aiDetectAll(imageData);
      setMessage("");
      if (detected.length === 0) {
        showToast(t("annotation.preLabelEmpty"), "info");
      } else {
        setPreLabels(detected);
      }
    } catch {
      setMessage("");
      showToast(t("annotation.preLabelFailed"), "error");
    }
  };

  const acceptPreLabels = () => {
    if (preLabels) {
      setBoxes(preLabels);
      showToast(t("annotation.preLabelAccepted"), "success");
    }
    setPreLabels(null);
  };

  const dismissPreLabels = () => {
    setPreLabels(null);
    showToast(t("annotation.preLabelDismissed"), "info");
  };

  if (!currentImage) {
    const emptyMessage =
      images.length === 0 && totalImages === 0
        ? t("annotation.noImages")
        : loadingAnnotations
          ? t("annotation.loadingAnnotations", "Loading annotations…")
          : t("annotation.loading");

    return (
      <EmptyState
        icon={<Upload size={32} />}
        title={emptyMessage}
        body={images.length === 0 && totalImages === 0 ? t("annotation.noImagesDetail") : undefined}
        action={
          images.length === 0 && totalImages === 0 && onGoToUpload ? (
            <Button variant="primary" onClick={onGoToUpload}>
              {t("annotation.goToUpload")}
            </Button>
          ) : undefined
        }
      />
    );
  }

  return (
    <>
      <AnnotateWorkspace
        taxonomyContext={taxonomyContext}
        datasetId={datasetId}
        currentIndex={currentIndex}
        totalImages={totalImages}
        onImageSelect={onNavigate}
        selectedLabel={selectedLabel}
        onLabelChange={setSelectedLabel}
        onPrev={goPrev}
        onNext={goNext}
        onSave={() => void handleSave()}
        onAutoLabel={() => void handleAiDetectAll()}
        saving={saving}
        loadingAnnotations={loadingAnnotations}
        isModelLoading={isModelLoading}
        isInferencing={isInferencing}
        loadProgress={loadProgress}
        modelUsed={modelUsed ?? undefined}
        isDirty={isDirty}
        pendingSync={stats.pending}
        drawTool={drawTool}
        onDrawToolChange={setDrawTool}
        saveStatus={
          aiDraft ? (
            <Badge variant="info">{t("annotation.liveAiDraft", "AI prelabels — edit & save to confirm")}</Badge>
          ) : null
        }
        secondaryToolbarAction={
          <BatchInferenceAction
            mode="detection"
            datasetId={datasetId}
            disabled={saving || loadingAnnotations}
            onComplete={(summary) => {
              showToast(
                t("batchInference.complete", {
                  processed: (summary.processed as number) ?? 0,
                }),
                "success",
              );
              if (currentImage?.annotation_id) {
                void loadAnnotations(currentImage.annotation_id);
              }
            }}
            onError={(msg) => showToast(msg, "error")}
          />
        }
      >
        <AnnotationCanvas
          imageUrl={imageUrl}
          boxes={boxes}
          onBoxesChange={setBoxes}
          label={selectedLabel}
          taxonomyContext={taxonomyContext}
          drawTool={drawTool}
        />
      </AnnotateWorkspace>

      {(message || lastError) && (
        <div className={`annotate-status-banner${message.includes("fail") || lastError ? " annotate-status-banner--error" : ""}`}>
          {lastError === "AI_MODELS_UNAVAILABLE"
            ? t("annotation.aiModelsUnavailable")
            : lastError || message}
        </div>
      )}

      <Modal
        open={preLabels !== null}
        onClose={dismissPreLabels}
        title={t("annotation.preLabelTitle")}
        footer={
          <>
            <Button variant="ghost" onClick={dismissPreLabels}>
              {t("annotation.preLabelDismiss")}
            </Button>
            <Button variant="primary" onClick={acceptPreLabels}>
              {t("annotation.preLabelAccept")}
            </Button>
          </>
        }
      >
        <p className="text-body">
          {t("annotation.preLabelBody", { count: preLabels?.length ?? 0 })}
        </p>
        <Badge variant="info">{t("annotation.preLabelHint")}</Badge>
      </Modal>
    </>
  );
}
