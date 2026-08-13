import { Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOptionalFabricCanvasZoomApi } from "../context/FabricCanvasZoomContext";
import { formatZoomPercent } from "../utils/fabricZoom";
import { IconButton } from "./ui/IconButton";

export function CanvasZoomToolbar() {
  const { t } = useTranslation();
  const api = useOptionalFabricCanvasZoomApi();

  if (!api) return null;

  return (
    <div className="canvas-zoom-toolbar" role="group" aria-label={t("canvas.zoomControls")}>
      <IconButton label={t("canvas.zoomOut")} size="sm" onClick={api.zoomOut}>
        <ZoomOut size={16} />
      </IconButton>
      <span className="canvas-zoom-level text-mono" aria-live="polite">
        {formatZoomPercent(api.zoom)}
      </span>
      <IconButton label={t("canvas.zoomIn")} size="sm" onClick={api.zoomIn}>
        <ZoomIn size={16} />
      </IconButton>
      <IconButton label={t("canvas.fitToScreen")} size="sm" onClick={api.fitToScreen}>
        <Maximize2 size={16} />
      </IconButton>
      <IconButton label={t("canvas.resetView")} size="sm" onClick={api.resetZoom}>
        <span className="canvas-zoom-reset-label">100%</span>
      </IconButton>
    </div>
  );
}
