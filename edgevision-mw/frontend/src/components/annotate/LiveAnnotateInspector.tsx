import { useTranslation } from "react-i18next";
import type { OverlayDisplayMode } from "../AnnotationOverlay";
import type { LiveAnnotation, LiveEvent } from "../../hooks/useLiveAnnotation";
import { FormField } from "../ui/FormField";
import { Select } from "../ui/Select";
import { Switch } from "../ui/Switch";
import { Badge } from "../ui/Badge";

const MODEL_TYPES = [
  { value: "object_detection", labelKey: "liveAnnotate.modelObjectDetection" },
  { value: "road_segmentation", labelKey: "liveAnnotate.modelRoadSegmentation" },
  { value: "agri_crop_classification", labelKey: "liveAnnotate.modelAgriCrop" },
  { value: "agri_health_classification", labelKey: "liveAnnotate.modelAgriHealth" },
  { value: "text_detection", labelKey: "liveAnnotate.modelTextDetection" },
] as const;

const DISPLAY_MODES: { value: OverlayDisplayMode; labelKey: string }[] = [
  { value: "both", labelKey: "liveAnnotate.displayBoth" },
  { value: "boxes", labelKey: "liveAnnotate.displayBoxes" },
  { value: "masks", labelKey: "liveAnnotate.displayMasks" },
  { value: "3d", labelKey: "liveAnnotate.display3d" },
  { value: "all", labelKey: "liveAnnotate.displayAll" },
];

interface LiveAnnotateInspectorProps {
  modelType: string;
  onModelTypeChange: (value: string) => void;
  displayMode: OverlayDisplayMode;
  onDisplayModeChange: (value: OverlayDisplayMode) => void;
  mirrored: boolean;
  onMirrorToggle: (checked: boolean) => void;
  mirrorAllowed: boolean;
  depthAvailable: boolean;
  autoSave?: boolean;
  onAutoSaveToggle?: (checked: boolean) => void;
  events?: LiveEvent[];
  annotations?: LiveAnnotation[];
  selectedAnnIdx?: number | null;
  onSelectAnn?: (idx: number | null) => void;
}

const EVENT_TYPE_KEYS: Record<string, string> = {
  dwell: "liveAnnotate.eventType.dwell",
  presence: "liveAnnotate.eventType.presence",
  confidence_drop: "liveAnnotate.eventType.confidenceDrop",
  close_approach: "liveAnnotate.eventType.closeApproach",
};

export function LiveAnnotateInspector({
  modelType,
  onModelTypeChange,
  displayMode,
  onDisplayModeChange,
  mirrored,
  onMirrorToggle,
  mirrorAllowed,
  depthAvailable,
  autoSave = false,
  onAutoSaveToggle,
  events = [],
  annotations = [],
  selectedAnnIdx,
  onSelectAnn,
}: LiveAnnotateInspectorProps) {
  const { t } = useTranslation();

  return (
    <div className="live-annotate-inspector">
      <h3 className="text-h3">{t("liveAnnotate.inspectorTitle", "Live settings")}</h3>

      <FormField label={t("liveAnnotate.modelType")}>
        <Select
          value={modelType}
          onChange={onModelTypeChange}
          aria-label={t("liveAnnotate.modelType")}
          options={MODEL_TYPES.map((m) => ({
            value: m.value,
            label: t(m.labelKey),
          }))}
        />
      </FormField>

      <FormField label={t("liveAnnotate.displayMode")}>
        <Select
          value={displayMode}
          onChange={(v) => onDisplayModeChange(v as OverlayDisplayMode)}
          aria-label={t("liveAnnotate.displayMode")}
          options={DISPLAY_MODES.map((m) => ({
            value: m.value,
            label: t(m.labelKey),
          }))}
        />
      </FormField>

      {mirrorAllowed && (
        <FormField label={t("liveAnnotate.mirrorPreview")}>
          <Switch
            id="live-mirror-toggle"
            checked={mirrored}
            onChange={onMirrorToggle}
            label={t("liveAnnotate.mirrorPreview")}
          />
        </FormField>
      )}

      {onAutoSaveToggle && (
        <FormField label={t("liveAnnotate.autoSave")}>
          <Switch
            id="live-autosave-toggle"
            checked={autoSave}
            onChange={onAutoSaveToggle}
            label={t("liveAnnotate.autoSave")}
          />
        </FormField>
      )}

      <div className="live-annotate-inspector-status">
        <span className="text-caption">{t("liveAnnotate.depthStatus", "Depth")}</span>
        <Badge variant={depthAvailable ? "success" : "warning"}>
          {depthAvailable
            ? t("liveAnnotate.depthOnnx", "ONNX depth")
            : t("liveAnnotate.depthHeuristic", "Heuristic")}
        </Badge>
      </div>

      {annotations.length > 0 && (
        <div className="live-annotate-inspector-detections">
          <span className="text-caption">{t("liveAnnotate.detections", "Detections")}</span>
          <ul className="live-annotate-detection-list">
            {annotations.map((ann, idx) => {
              const dist = ann.distance_m != null ? `${ann.distance_m.toFixed(1)}m` : "";
              const pct = `${(ann.confidence * 100).toFixed(0)}%`;
              const isSelected = selectedAnnIdx === idx;
              return (
                <li
                  key={idx}
                  className={`live-annotate-detection-item${isSelected ? " live-annotate-detection-item--selected" : ""}`}
                  onClick={() => onSelectAnn?.(isSelected ? null : idx)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onSelectAnn?.(isSelected ? null : idx);
                  }}
                >
                  <Badge variant={isSelected ? "info" : "default"}>
                    {ann.taxonomy_label || ann.class_name}
                  </Badge>
                  <span className="text-caption">{pct}</span>
                  {dist && <span className="text-caption">{dist}</span>}
                  {ann.track_id != null && (
                    <span className="text-caption">#{ann.track_id}</span>
                  )}
                </li>
              );
            })}
          </ul>
          {selectedAnnIdx != null && (
            <div className="live-annotate-relabel">
              <span className="text-caption">{t("liveAnnotate.relabelHint", "Tap detection to deselect. Open in Studio to relabel.")}</span>
            </div>
          )}
        </div>
      )}

      <div className="live-annotate-inspector-events">
        <span className="text-caption">{t("liveAnnotate.events", "Events")}</span>
        {events.length === 0 ? (
          <p className="text-caption">{t("liveAnnotate.noEvents", "No events yet")}</p>
        ) : (
          <ul className="live-annotate-event-feed">
            {events.map((ev) => (
              <li key={ev.event_id} className="live-annotate-event-feed-item">
                <Badge variant={ev.auto_saved ? "success" : "info"}>
                  {t(EVENT_TYPE_KEYS[ev.event_type] ?? "liveAnnotate.eventType.rule", ev.rule_name)}
                </Badge>
                <span className="text-caption">
                  {ev.track_id != null ? `#${ev.track_id}` : ""}
                  {ev.details?.distance_m != null
                    ? ` · ${Number(ev.details.distance_m).toFixed(1)}m`
                    : ""}
                  {ev.duration_seconds != null ? ` · ${ev.duration_seconds.toFixed(1)}s` : ""}
                  {ev.auto_saved ? ` · ${t("liveAnnotate.eventSaved")}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
