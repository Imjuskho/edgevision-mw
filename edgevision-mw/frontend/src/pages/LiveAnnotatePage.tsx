import { useRef, useState, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, MonitorUp, Pencil, Wifi, WifiOff, FlipHorizontal2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLiveAnnotation } from "../hooks/useLiveAnnotation";
import { useLiveFrameQueue } from "../hooks/useLiveFrameQueue";
import AnnotationOverlay, { type OverlayDisplayMode } from "../components/AnnotationOverlay";
import { AnnotateWorkspace } from "../components/annotate/AnnotateWorkspace";
import { LiveAnnotateInspector } from "../components/annotate/LiveAnnotateInspector";
import { acquireCamera, acquireScreen, releaseCamera } from "../utils/cameraManager";
import { useToast } from "../components/Toast";
import { useNetworkStatus } from "../hooks/useNetworkStatus";
import {
  isMirrored,
  loadMirrorPreference,
  ORIENTATION_DEBUG_ENABLED,
  saveMirrorPreference,
} from "../utils/orientation";
import { captureFrame, isVideoReady } from "../utils/captureFrame";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { IconButton } from "../components/ui/IconButton";
import { Select } from "../components/ui/Select";
import { Switch } from "../components/ui/Switch";
import { buildPath } from "../routes/paths";
import type { SaveFrameResult } from "../hooks/useLiveAnnotation";

interface Props {
  datasetId?: string;
  onSaved?: () => void;
  onNavigateToAnnotate?: (imageIndex: number) => void;
}

export default function LiveAnnotatePage({ datasetId, onSaved, onNavigateToAnnotate }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const isOnline = useNetworkStatus();
  const { pending: pendingFrames, refreshPending } = useLiveFrameQueue();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [source, setSource] = useState<"camera" | "screen" | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [videoReady, setVideoReady] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [mirrored, setMirrored] = useState(() => loadMirrorPreference());
  const [prevStream, setPrevStream] = useState<MediaStream | null>(null);
  if (stream !== prevStream) {
    setPrevStream(stream);
    setVideoReady(false);
    setSourceError(null);
  }
  const [prevSource, setPrevSource] = useState<"camera" | "screen" | null>(null);
  if (source !== prevSource) {
    setPrevSource(source);
    if (source === "screen") setMirrored(false);
  }
  const [modelType, setModelType] = useState("object_detection");
  const [displayMode, setDisplayMode] = useState<OverlayDisplayMode>("all");
  const [autoSave, setAutoSave] = useState(false);
  const [selectedLabel, setSelectedLabel] = useState("");
  const [selectedAnnIdx, setSelectedAnnIdx] = useState<number | null>(null);
  const lastAutoSavedEventRef = useRef<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [lastSave, setLastSave] = useState<SaveFrameResult | null>(null);

  const mirrorAllowed = source === "camera";
  const effectiveMirrored = isMirrored(mirrorAllowed, mirrored);

  const { annotations, liveEvents, isInferencing, lastInferenceMs, error, saveFrame, frameSize, depthAvailable } = useLiveAnnotation({
    videoRef,
    enabled: source !== null && videoReady,
    modelType,
    mirrored: effectiveMirrored,
    fps: 2,
    maxWidth: 448,
    eventsEnabled: true,
    autoSave,
    datasetId,
  });

  useEffect(() => {
    return () => { releaseCamera(); };
  }, []);

  useEffect(() => {
    const saved = liveEvents.find((e) => e.auto_saved && e.event_id !== lastAutoSavedEventRef.current);
    if (!saved) return;
    lastAutoSavedEventRef.current = saved.event_id;
    showToast(t("liveAnnotate.autoSaveSuccess", "Event clip auto-saved to dataset"), "success");
  }, [liveEvents, showToast, t]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (!stream) {
      video.srcObject = null;
      return;
    }

    const handleCanPlay = () => {
      setVideoReady(true);
    };

    video.srcObject = stream;
    video.addEventListener("canplay", handleCanPlay);

    video.play().catch(() => {
      // ignore autoplay failures; canplay will still update readiness
    });

    return () => {
      video.removeEventListener("canplay", handleCanPlay);
    };
  }, [stream]);

  useEffect(() => {
    if (!ORIENTATION_DEBUG_ENABLED || !videoReady || !effectiveMirrored) return;

    const video = videoRef.current;
    if (!video || !isVideoReady(video)) return;

    let cancelled = false;

    const probe = async () => {
      try {
        const blob = await captureFrame(video, 0.5, "image/jpeg", effectiveMirrored);
        const bitmap = await createImageBitmap(blob);
        const canvas = document.createElement("canvas");
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.drawImage(bitmap, 0, 0);
        bitmap.close();

        const w = canvas.width;
        const h = canvas.height;
        const markers = [
          { name: "left", expectedX: Math.round(w * 0.25) },
          { name: "right", expectedX: Math.round(w * 0.75) },
        ];

        for (const m of markers) {
          const col = ctx.getImageData(m.expectedX, Math.round(h / 2), 1, 1).data;
          const brightness = (col[0] + col[1] + col[2]) / 3;
          if (annotations.length > 0) {
            const ann = annotations[0];
            const overlayX = ann.bbox[0];
            const delta = Math.abs(overlayX - m.expectedX);
            if (delta > w * 0.05) {
              console.warn("orientation_mismatch", {
                marker: m.name,
                expectedX: m.expectedX,
                overlayBboxX: overlayX,
                delta,
                brightness,
              });
            }
          }
        }
      } catch {
        /* probe is best-effort */
      }
    };

    const id = setInterval(() => {
      if (!cancelled) void probe();
    }, 3000);

    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [videoReady, effectiveMirrored, annotations]);

  const handleMirrorToggle = useCallback((checked: boolean) => {
    if (!mirrorAllowed) return;
    setMirrored(checked);
    saveMirrorPreference(checked);
  }, [mirrorAllowed]);

  const handleStartCamera = useCallback(async () => {
    setSourceError(null);
    try {
      const acquired = await acquireCamera();
      setSource("camera");
      setStream(acquired);
    } catch (err) {
      setSourceError(String(err));
    }
  }, []);

  const handleStartScreen = useCallback(async () => {
    setSourceError(null);
    try {
      const acquired = await acquireScreen();
      setSource("screen");
      setStream(acquired);
    } catch (err) {
      setSourceError(String(err));
    }
  }, []);

  const handleStop = useCallback(() => {
    releaseCamera();
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setSource(null);
    setStream(null);
    setVideoReady(false);
    setSourceError(null);
  }, []);

  const isStarting = source !== null && !videoReady;

  const handleSave = useCallback(async () => {
    if (!datasetId) {
      showToast(t("liveAnnotate.datasetRequired", "Select a dataset before saving frames"), "error");
      return;
    }
    if (annotations.length === 0) {
      showToast(
        t("liveAnnotate.noAnnotationsHint", "No detections — saving frame only (no AI prelabels)"),
        "warning",
      );
    }
    setSaving(true);
    try {
      const result = await saveFrame(datasetId);
      if (result?.queued) {
        showToast(t("liveAnnotate.saveQueued"), "info");
        await refreshPending();
        setLastSave(result);
      } else if (result) {
        setLastSave(result);
        showToast(t("liveAnnotate.saveSuccess"), "success");
        onSaved?.();
      } else {
        showToast(t("liveAnnotate.saveFailed"), "error");
      }
    } finally {
      setSaving(false);
    }
  }, [saveFrame, datasetId, annotations.length, showToast, t, refreshPending, onSaved]);

  const handleOpenInStudio = useCallback(() => {
    if (!datasetId || lastSave?.image_index == null) return;
    if (onNavigateToAnnotate) {
      onNavigateToAnnotate(lastSave.image_index);
      return;
    }
    navigate(buildPath("annotate", { datasetId }));
  }, [datasetId, lastSave, onNavigateToAnnotate, navigate]);

  const ocrBlocked = modelType === "text_detection" && effectiveMirrored;
  const statusError = ocrBlocked ? t("liveAnnotate.ocrMirrorBlocked") : error;

  const liveStats = (
    <div className="live-annotate-toolbar-stats">
      <div className="live-annotate-toolbar-inline-controls">
        <div className="live-annotate-toolbar-control">
          <span className="text-caption">{t("liveAnnotate.modelShort", "Model")}</span>
          <Select
            value={modelType}
            onChange={setModelType}
            aria-label={t("liveAnnotate.modelType")}
            options={[
              { value: "object_detection", label: t("liveAnnotate.modelObjectDetection") },
              { value: "road_segmentation", label: t("liveAnnotate.modelRoadSegmentation") },
              { value: "agri_crop_classification", label: t("liveAnnotate.modelAgriCrop") },
              { value: "agri_health_classification", label: t("liveAnnotate.modelAgriHealth") },
              { value: "text_detection", label: t("liveAnnotate.modelTextDetection") },
            ]}
          />
        </div>
        <div className="live-annotate-toolbar-control">
          <span className="text-caption">{t("liveAnnotate.displayShort", "Display")}</span>
          <Select
            value={displayMode}
            onChange={(v) => setDisplayMode(v as OverlayDisplayMode)}
            aria-label={t("liveAnnotate.displayMode")}
            options={[
              { value: "both", label: t("liveAnnotate.displayBoth") },
              { value: "boxes", label: t("liveAnnotate.displayBoxes") },
              { value: "masks", label: t("liveAnnotate.displayMasks") },
              { value: "3d", label: t("liveAnnotate.display3d") },
              { value: "all", label: t("liveAnnotate.displayAll") },
            ]}
          />
        </div>
        {mirrorAllowed && (
          <div className="live-annotate-toolbar-control" title={t("liveAnnotate.mirrorPreview")}>
            <IconButton
              label={t("liveAnnotate.mirrorPreview")}
              size="sm"
              aria-pressed={mirrored}
              className={mirrored ? "live-annotate-toolbar-control--active" : undefined}
              onClick={() => {
                const next = !mirrored;
                setMirrored(next);
                saveMirrorPreference(next);
              }}
            >
              <FlipHorizontal2 size={14} />
            </IconButton>
          </div>
        )}
        <div className="live-annotate-toolbar-control" title={t("liveAnnotate.autoSave")}>
          <Switch
            id="live-toolbar-autosave"
            checked={autoSave}
            onChange={setAutoSave}
            label={t("liveAnnotate.autoSaveShort", "Auto")}
          />
        </div>
      </div>

      <div className="live-annotate-toolbar-badges">
        {isInferencing && (
          <Badge variant="info" className="live-annotate-pulse">{t("liveAnnotate.inferencing", "Inferencing...")}</Badge>
        )}
        {!isInferencing && lastInferenceMs > 0 && (
          <Badge variant="default">{lastInferenceMs}ms</Badge>
        )}
        {annotations.length > 0 && (
          <Badge variant="success">
            {annotations.length} {t("liveAnnotate.objects", "object(s)")}
          </Badge>
        )}
        {pendingFrames > 0 && (
          <Badge variant="warning">{t("liveAnnotate.pendingFrames", { count: pendingFrames })}</Badge>
        )}
        {!isOnline && (
          <Badge variant="warning">{t("liveAnnotate.offlineNotice")}</Badge>
        )}
        <span className="live-annotate-depth-badge">
          {depthAvailable
            ? <Badge variant="success">{t("liveAnnotate.depthOnnxShort", "Depth: ONNX")}</Badge>
            : <Badge variant="warning">{t("liveAnnotate.depthHeuristicShort", "Depth: Est.")}</Badge>
          }
        </span>
      </div>
    </div>
  );

  return (
    <div className="page-shell live-annotate-page">
      <div className="page-heading">
        <h1>{t("liveAnnotate.title", "Live Annotation")}</h1>
        <p>{t("liveAnnotate.subtitle", "AI-assisted real-time object detection via camera or screen share")}</p>
        {datasetId && (
          <p className="text-caption">
            {t("liveAnnotate.datasetLabel", "Dataset")}: <span className="text-mono">{datasetId}</span>
          </p>
        )}
        {!datasetId && (
          <p className="live-annotate-offline-notice" role="status">
            {t("liveAnnotate.datasetRequiredHint", "Open live annotate from a dataset to save AI labels into the studio.")}
          </p>
        )}
      </div>

      <div className="live-annotate-body">
        {!source ? (
          <div className="live-annotate-setup">
            <div className="live-annotate-setup-main">
              <div className="live-annotate-picker">
                <h2 className="live-annotate-setup-heading">
                  {t("liveAnnotate.setupHeading", "Select Input Source")}
                </h2>
                <div className="live-annotate-picker-actions">
                  <Button variant="primary" icon={<Camera size={16} />} onClick={() => void handleStartCamera()}>
                    {t("liveAnnotate.startCamera", "Start Camera")}
                  </Button>
                  <Button variant="secondary" icon={<MonitorUp size={16} />} onClick={() => void handleStartScreen()}>
                    {t("liveAnnotate.startScreen", "Share Screen")}
                  </Button>
                </div>
                {sourceError && (
                  <div className="live-annotate-error" role="alert">
                    {sourceError}
                  </div>
                )}

                <div className="live-annotate-connection-status">
                  {isOnline ? (
                    <>
                      <Wifi size={14} />
                      <span className="text-caption">{t("liveAnnotate.connected", "Connected — inference via server")}</span>
                    </>
                  ) : (
                    <>
                      <WifiOff size={14} />
                      <span className="text-caption">{t("liveAnnotate.offlineMode", "Offline — on-device inference if available")}</span>
                    </>
                  )}
                </div>

                {pendingFrames > 0 && (
                  <Badge variant="warning">
                    {t("liveAnnotate.pendingFrames", { count: pendingFrames })} {t("liveAnnotate.pendingFlushHint", "— will sync when connected")}
                  </Badge>
                )}
              </div>

              <div className="live-annotate-setup-info">
                {datasetId ? (
                  <div className="live-annotate-dataset-badge">
                    <Badge variant="success">{t("liveAnnotate.datasetLabel", "Dataset")}: {datasetId}</Badge>
                    <span className="text-caption">
                      {t("liveAnnotate.datasetHint", "Saved frames will be added to this dataset.")}
                    </span>
                  </div>
                ) : (
                  <p className="live-annotate-offline-notice" role="status">
                    {t("liveAnnotate.datasetRequiredHint", "Open live annotate from a dataset to save AI labels into the studio.")}
                  </p>
                )}
              </div>
            </div>

            <div className="live-annotate-setup-sidebar">
              <LiveAnnotateInspector
                modelType={modelType}
                onModelTypeChange={setModelType}
                displayMode={displayMode}
                onDisplayModeChange={setDisplayMode}
                mirrored={mirrored}
                onMirrorToggle={handleMirrorToggle}
                mirrorAllowed={mirrorAllowed}
                depthAvailable={depthAvailable}
                autoSave={autoSave}
                onAutoSaveToggle={setAutoSave}
                events={liveEvents}
                annotations={annotations}
                selectedAnnIdx={selectedAnnIdx}
                onSelectAnn={setSelectedAnnIdx}
              />
            </div>
          </div>
        ) : (
          <AnnotateWorkspace
            workspaceMode="live"
            taxonomyContext="road"
            datasetId={datasetId}
            currentIndex={0}
            totalImages={1}
            selectedLabel={selectedLabel}
            onLabelChange={setSelectedLabel}
            onPrev={() => {}}
            onNext={() => {}}
            onSave={() => void handleSave()}
            saving={saving}
            hideAutoLabel
            saveLabel={t("liveAnnotate.save", "Save Frame")}
            hideSaveKbd
            toolbarExtra={liveStats}
            secondaryToolbarAction={
              <>
                {lastSave?.image_index != null && datasetId && (
                  <Button variant="secondary" size="sm" icon={<Pencil size={14} />} onClick={handleOpenInStudio}>
                    {t("liveAnnotate.openInStudio", "Edit in studio")}
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={handleStop}>
                  {t("liveAnnotate.stop", "Stop")}
                </Button>
              </>
            }
            inspector={
              <LiveAnnotateInspector
                modelType={modelType}
                onModelTypeChange={setModelType}
                displayMode={displayMode}
                onDisplayModeChange={setDisplayMode}
                mirrored={mirrored}
                onMirrorToggle={handleMirrorToggle}
                mirrorAllowed={mirrorAllowed}
                depthAvailable={depthAvailable}
                autoSave={autoSave}
                onAutoSaveToggle={setAutoSave}
                events={liveEvents}
                annotations={annotations}
                selectedAnnIdx={selectedAnnIdx}
                onSelectAnn={setSelectedAnnIdx}
              />
            }
          >
            <div className="live-annotate-video-wrapper">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className={`live-annotate-video${effectiveMirrored ? " live-annotate-video-mirror" : ""}`}
              />
              {ORIENTATION_DEBUG_ENABLED && effectiveMirrored && (
                <>
                  <div className="orientation-debug-marker orientation-debug-marker--left" aria-hidden />
                  <div className="orientation-debug-marker orientation-debug-marker--right" aria-hidden />
                </>
              )}
              <AnnotationOverlay
                annotations={annotations}
                videoWidth={frameSize?.width ?? 0}
                videoHeight={frameSize?.height ?? 0}
                displayMode={displayMode}
                previewMirrored={effectiveMirrored}
                depthAvailable={depthAvailable}
                selectedTrackId={
                  selectedAnnIdx != null && annotations[selectedAnnIdx]?.track_id != null
                    ? annotations[selectedAnnIdx].track_id!
                    : null
                }
              />
              {isStarting && (
                <div className="live-annotate-loading">
                  {t("liveAnnotate.initializing", "Initializing live stream...")}
                </div>
              )}
            </div>
          </AnnotateWorkspace>
        )}

        {source && statusError && (
          <div className="live-annotate-error" role="alert">
            {statusError}
          </div>
        )}
      </div>
    </div>
  );
}
