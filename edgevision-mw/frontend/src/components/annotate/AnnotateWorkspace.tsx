import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, Hexagon, Sparkles, Square } from "lucide-react";
import { useTranslation } from "react-i18next";
import ImageSidebar from "../ImageSidebar";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { IconButton } from "../ui/IconButton";
import { Kbd } from "../ui/Kbd";
import { getAllLabelsForContext } from "../../utils/annotateLabels";
import { toStyle } from "../../utils/toStyle";
import LabelSelector from "../LabelSelector";
import { FabricCanvasZoomProvider } from "../../context/FabricCanvasZoomContext";
import { CanvasZoomToolbar } from "../CanvasZoomToolbar";

export type WorkspaceDrawTool = "bbox" | "polygon";
export type WorkspaceMode = "bbox" | "segment" | "live";

interface AnnotateWorkspaceProps {
  taxonomyContext: "road" | "agri";
  workspaceMode?: WorkspaceMode;
  datasetId?: string;
  currentIndex: number;
  totalImages: number;
  onImageSelect?: (index: number) => void;
  selectedLabel: string;
  onLabelChange: (label: string) => void;
  onPrev: () => void;
  onNext: () => void;
  onSave: () => void;
  onAutoLabel?: () => void;
  saving: boolean;
  loadingAnnotations?: boolean;
  isModelLoading?: boolean;
  isInferencing?: boolean;
  loadProgress?: number;
  modelUsed?: string;
  isDirty?: boolean;
  pendingSync?: number;
  hideAutoLabel?: boolean;
  hideLabelSelector?: boolean;
  inspector?: ReactNode;
  saveStatus?: ReactNode;
  drawTool?: WorkspaceDrawTool;
  onDrawToolChange?: (tool: WorkspaceDrawTool) => void;
  saveLabel?: string;
  hideSaveKbd?: boolean;
  secondaryToolbarAction?: ReactNode;
  children: ReactNode;
  toolbarExtra?: ReactNode;
}

export function AnnotateWorkspace({
  taxonomyContext,
  workspaceMode = "bbox",
  datasetId,
  currentIndex,
  totalImages,
  onImageSelect,
  selectedLabel,
  onLabelChange,
  onPrev,
  onNext,
  onSave,
  onAutoLabel,
  saving,
  loadingAnnotations = false,
  isModelLoading = false,
  isInferencing = false,
  loadProgress = 0,
  modelUsed,
  isDirty,
  pendingSync = 0,
  hideAutoLabel = false,
  hideLabelSelector = false,
  inspector,
  saveStatus,
  drawTool,
  onDrawToolChange,
  saveLabel,
  hideSaveKbd = false,
  secondaryToolbarAction,
  children,
  toolbarExtra,
}: AnnotateWorkspaceProps) {
  const { t } = useTranslation();
  const palette = getAllLabelsForContext(taxonomyContext);
  const isLive = workspaceMode === "live";
  const modeBannerKey = isLive
    ? "annotation.liveModeBanner"
    : workspaceMode === "segment"
      ? "annotation.segmentModeBanner"
      : taxonomyContext === "agri"
        ? "annotation.agriModeBanner"
        : "annotation.roadModeBanner";
  const bannerClass = isLive
    ? "live"
    : workspaceMode === "segment"
      ? "segment"
      : taxonomyContext === "agri"
        ? "agri"
        : "road";

  return (
    <FabricCanvasZoomProvider>
    <div className="annotate-layout">
      {datasetId && onImageSelect && (
        <ImageSidebar datasetId={datasetId} currentIndex={currentIndex} onSelect={onImageSelect} />
      )}
      <div className={`annotate-main annotate-page annotate-workspace${workspaceMode === "segment" ? " annotate-workspace--segment" : ""}`}>
      <div
        className={`annotate-mode-banner annotate-mode-banner-${bannerClass}`}
        role="status"
      >
        {t(modeBannerKey)}
      </div>

      {isModelLoading && (
        <div className="ai-model-loading-banner" role="status" aria-live="polite">
          <strong>{t("annotation.aiLoading", { progress: loadProgress })}</strong>
          <span>{t("annotation.aiLoadingHint")}</span>
        </div>
      )}

      <div className="annotate-toolbar">
        {!isLive ? (
          <div className="annotate-toolbar-nav">
            <IconButton label={t("canvas.prev")} size="sm" onClick={onPrev} disabled={currentIndex === 0}>
              <ChevronLeft size={16} />
            </IconButton>
            <span className="annotate-toolbar-index text-mono">
              {currentIndex + 1} / {totalImages}
            </span>
            <IconButton
              label={t("canvas.next")}
              size="sm"
              onClick={onNext}
              disabled={currentIndex >= totalImages - 1}
            >
              <ChevronRight size={16} />
            </IconButton>
            {isDirty && (
              <Badge variant="warning">{t("annotation.unsaved")}</Badge>
            )}
            {pendingSync > 0 && (
              <Badge variant="info">{t("sync.pending", { count: pendingSync })}</Badge>
            )}
            {!isLive && <CanvasZoomToolbar />}
            {onDrawToolChange && drawTool && workspaceMode === "bbox" && (
              <div className="annotate-tool-toggle" role="group" aria-label={t("annotation.drawTool")}>
                <IconButton
                  label={t("annotation.toolBbox")}
                  size="sm"
                  aria-pressed={drawTool === "bbox"}
                  className={drawTool === "bbox" ? "annotate-tool-toggle--active" : undefined}
                  onClick={() => onDrawToolChange("bbox")}
                >
                  <Square size={16} />
                </IconButton>
                <IconButton
                  label={t("annotation.toolPolygon")}
                  size="sm"
                  aria-pressed={drawTool === "polygon"}
                  className={drawTool === "polygon" ? "annotate-tool-toggle--active" : undefined}
                  onClick={() => onDrawToolChange("polygon")}
                >
                  <Hexagon size={16} />
                </IconButton>
              </div>
            )}
          </div>
        ) : (
          <div className="annotate-toolbar-nav annotate-toolbar-nav--live">{toolbarExtra}</div>
        )}

        <div className="annotate-toolbar-actions">
          {!isLive && !hideLabelSelector && (
            <LabelSelector value={selectedLabel} onChange={onLabelChange} taxonomyContext={taxonomyContext} />
          )}

          {!isLive && !hideAutoLabel && onAutoLabel && (
            <Button
              variant="secondary"
              size="sm"
              onClick={onAutoLabel}
              disabled={isModelLoading || isInferencing || loadingAnnotations}
              loading={isInferencing}
              icon={<Sparkles size={14} />}
            >
              {isModelLoading
                ? t("annotation.aiLoading", { progress: loadProgress })
                : t("canvas.autoDetect")}
            </Button>
          )}

          {modelUsed && (
            <span title={t("annotation.aiModelSource")}>
              <Badge variant="info">AI: {modelUsed}</Badge>
            </span>
          )}

          {saveStatus}

          <Button variant="primary" size="sm" onClick={onSave} loading={saving} disabled={loadingAnnotations}>
            {saving ? t("annotation.saving") : (saveLabel ?? t("annotation.save"))}
            {!hideSaveKbd && <Kbd>⌘S</Kbd>}
          </Button>

          {secondaryToolbarAction}

          {!isLive && toolbarExtra}
        </div>
      </div>

      <div className={`annotate-workspace-body${isLive ? " annotate-workspace-body--live" : ""}`}>
        <div className={`annotate-canvas-wrap${isLive ? " annotate-canvas-wrap--live" : ""}`}>{children}</div>
        <aside className="annotate-inspector" aria-label={t("annotation.inspector")}>
          {inspector ?? (
            <>
              <h3 className="text-h3">{t("annotation.classPalette")}</h3>
              <p className="text-caption">{t("annotation.shortcutHint")}</p>
              <div className="annotate-palette-grid">
                {palette.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    className={`annotate-palette-item${selectedLabel === item.label ? " annotate-palette-item--active" : ""}`}
                    onClick={() => onLabelChange(item.label)}
                    style={toStyle({ borderColor: item.color })}
                  >
                    <Kbd>{item.shortcut}</Kbd>
                    <span className="annotate-palette-item__name">{item.name}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </aside>
      </div>
      </div>
    </div>
    </FabricCanvasZoomProvider>
  );
}
