import { useTranslation } from "react-i18next";
import type { OverlayDisplayMode } from "../AnnotationOverlay";
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
}

export function LiveAnnotateInspector({
  modelType,
  onModelTypeChange,
  displayMode,
  onDisplayModeChange,
  mirrored,
  onMirrorToggle,
  mirrorAllowed,
  depthAvailable,
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

      <div className="live-annotate-inspector-status">
        <span className="text-caption">{t("liveAnnotate.depthStatus", "Depth")}</span>
        <Badge variant={depthAvailable ? "success" : "warning"}>
          {depthAvailable
            ? t("liveAnnotate.depthOnnx", "ONNX depth")
            : t("liveAnnotate.depthHeuristic", "Heuristic")}
        </Badge>
      </div>
    </div>
  );
}
